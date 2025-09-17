import json
from queue import PriorityQueue
import itertools
import traceback
from contextlib import asynccontextmanager
import threading
import time
from typing import List
from main import TestAgent
from fastapi import FastAPI, BackgroundTasks, HTTPException
from db_utils import connect_to_db, get_generation_status, get_question_sets, get_usage, insert_record, save_generated_questions_to_db, set_generation_status, clear_table, get_records_with_generation_status, set_usage
from config import prompt, json_format, queue_limit, max_requests_per_day, max_questions_per_req
from utils import MockTest, Question, Sets, Status, get_client, priorities


generation_queue = PriorityQueue(maxsize=queue_limit)
client = get_client(client_name='google')
counter = itertools.count()

# -------------------------------------------------------------------------------
already_generated_questions = []
with open("chapter1.txt", "r") as f1:
    chapter1 = f1.read()

with open("chapter2.txt", "r", encoding="utf-8") as f2:
    chapter2 = f2.read()

# -------------------------------------------------------------------------------
def generate_questions(db, cursor, subject:str, standard:str, chapter_ids:List[str], number_of_questions:int, test_id:str):
    """
    We will extract the student's study material and generate the mock test based on the following args:
        - subject : For what subject we are generating the mock test. Ex: Hindi, Telugu etc.
        - standard : What is the student's class. Ex: LKG, 5th class etc.
        - chapter_ids : Chapter ids are used to fetch the study material information from the db.
        - number_of_sets : Specifies the number of exam papers we need to generate.
        - number_of_questions : Specifies the number of questions per paper/set.
        - test_id : Primary key of the MockTest table. We have to update the row with the given test_id after the test is generated.
    """
    chapters_text = [chapter1, chapter2] # get the text from the database for the required chapters using subject, standard, chapter_ids
    test_creator = TestAgent(db, cursor, client=client, system_prompt=prompt, json_format=json_format, questions_per_batch=max_questions_per_req)
    mock_test_set = test_creator(chapters_text=chapters_text, total_number_of_questions=number_of_questions, max_consecutive_chunks=10)
    return mock_test_set
# -------------------------------------------------------------------------------
class BackGroundWorker(threading.Thread):
    def __init__(self, generation_queue:PriorityQueue):
        super().__init__(daemon=True) # stops when the app stops
        self.generation_queue = generation_queue

    def check_if_complete(self, db, cursor, test_id, generated_mock_tests, number_of_questions):
        all_questions_generated = True
        for test_set in generated_mock_tests:
            if test_set:
                if len(test_set) != number_of_questions:
                    all_questions_generated = False
            else:
                    all_questions_generated = False
        if all_questions_generated:
            set_generation_status(db=db, cursor=cursor, test_id=test_id, generation_status=Status.COMPLETED.value)

    def check_number_of_questions_to_generate(self, number_of_sets, number_of_questions, generated_sets):
        number_of_questions_to_generate_per_set = []
        for i in range(number_of_sets):
            generated_questions_per_set = len(generated_sets[i]) if generated_sets[i] else 0
            number_of_questions_to_generate_per_set.append(number_of_questions - generated_questions_per_set)
        return number_of_questions_to_generate_per_set

    def process(self, req:MockTest):
        """This method should process for a single mocktest no matter the number of sets"""
        try:
            db = connect_to_db()
            cursor = db.cursor()
            test_id = req.test_id
            subject = req.subject
            standard = req.standard
            chapter_ids = req.chapter_ids
            number_of_questions = req.number_of_questions
            number_of_sets = req.number_of_sets
            generated_sets_string_from_db = get_question_sets(cursor=cursor, test_id=test_id)[0]
            loaded_json = json.loads(generated_sets_string_from_db)
            generated_sets = [[Question(**question) for question in mock_test_set] for mock_test_set in loaded_json ]
            num_questions_to_generate_per_set = self.check_number_of_questions_to_generate(number_of_sets, number_of_questions, generated_sets)
            save_to_db = False
            for i in range(len(generated_sets)):
                if num_questions_to_generate_per_set[i] > 0:
                    generated_mock_tests = generate_questions(db, cursor, subject, standard, chapter_ids , num_questions_to_generate_per_set[i], test_id)
                    if generated_sets[i]:
                        generated_sets[i].extend([Question(**question) for question in generated_mock_tests])
                    else:
                        generated_sets[i] = [Question(**question) for question in generated_mock_tests]
                    save_to_db = True
            if save_to_db:
                save_generated_questions_to_db(db=db, cursor=cursor, test_id=test_id, questions=generated_sets)
            else:
                print("No saving/updating needed")
            self.check_if_complete(db, cursor, test_id, generated_sets, number_of_questions)
        except Exception:
            print(f"Exception in process(server.py): {traceback.print_exc()}")
        finally:
            cursor.close()
            db.close()

    def run(self):
        print("Worker started...")
        while True:
            try:
                db = connect_to_db()
                cursor = db.cursor()
                current_usage = get_usage(cursor=cursor)
                remaining_requests = max_requests_per_day - current_usage
                if remaining_requests > 0:
                    if not self.generation_queue.empty():
                        test_details = self.generation_queue.get()[-1]
                        if test_details.generation_status != Status.PENDING:
                            set_generation_status(db=db, cursor=cursor, test_id=test_details.test_id, generation_status=Status.PENDING.value)
                        print(f"Started Processing for {test_details.test_id}")
                        self.process(test_details)
                        # time.sleep(10)
                        print(f"Process is completed for {test_details.test_id}")
                        # set_usage(db, cursor, new_usage=current_usage+1) # we are setting the usage in the agent side
                        # set_generation_status(db=db, cursor=cursor, test_id=test_details.test_id, generation_status=Status.COMPLETED.value)
                        # print(f"Updated generation status for {test_details.test_id}")
                        time.sleep(2)
                    else:
                        time.sleep(5)
                        print("Waited 5 secs before rechecking...")
                        mock_tests = get_records_with_generation_status(cursor=cursor, generation_status=(Status.PENDING.value, Status.QUEUED.value))
                        if mock_tests:
                            if len(mock_tests)>0:
                                print(f"Added {len(mock_tests)} requests to queue.")
                                for test in mock_tests:
                                    self.generation_queue.put(item=(priorities[test.generation_status], next(counter), test))
                else:
                    print("rate limit hit for today...")
                    time.sleep(10) # usually sleeps upto midnight
                    set_usage(db, cursor, new_usage=0) # this needs to be done just after the midnight
                    print("limit is reset")
            except Exception:
                print(f"Exception in run(server.py): {traceback.print_exc()}")
            finally:
                cursor.close()
                db.close()
            

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("lifespan started!!!")
    db = connect_to_db()
    cursor = db.cursor()
    worker = BackGroundWorker(generation_queue)
    worker.start()
    yield
    for _ in range(generation_queue.qsize()):
        test_details = generation_queue.get()[-1]
        set_generation_status(db=db, cursor=cursor, test_id=test_details.test_id, generation_status=Status.PENDING.value)
    cursor.close()
    db.close()
    print("lifespan ended!!!")
# -------------------------------------------------------------------------------

app = FastAPI(lifespan=lifespan)

@app.post("/mocktest")
async def queue_test(req:MockTest):
    try:
        db = connect_to_db()
        cursor = db.cursor()
        test_id = req.test_id
        subject = req.subject
        standard = req.standard
        chapter_ids = req.chapter_ids
        number_of_questions = req.number_of_questions
        number_of_sets = req.number_of_sets
        current_status = req.generation_status.value
        question_sets = req.questions

        if current_status:
            if current_status == Status.CREATED.value or current_status == Status.FAILED.value:
                """Need to generate questions from scratch"""
                # generation_queue.put(item=(priorities[Status.CREATED if current_status == Status.CREATED.value else Status.FAILED], next(counter), req))
                question_sets = [[] for _ in range(number_of_sets)]
                insert_record(db, cursor, number_of_sets=number_of_sets, generation_status='CREATED', question_sets=question_sets, number_of_questions=number_of_questions, subject=subject, standard=standard, chapter_ids=chapter_ids)
                set_generation_status(db, cursor, test_id, Status.QUEUED.value)
                return {"message":f"Test Generation is Queued for Test ID: {req.test_id}."}
            
            elif current_status == Status.COMPLETED.value or current_status == Status.QUEUED.value:
                """We should refuse the requests that are already queued and or completed"""
                raise HTTPException(status_code=400, detail=f"The current status is already {current_status}. Hence this request is invalid.")
            
            elif current_status == Status.PENDING.value:
                """Should get the already generated questions from the db and then append the new generations"""
                question_sets.extend([[] for _ in range(number_of_sets-len(question_sets))])
                print(f"{question_sets = }")
                insert_record(db, cursor, number_of_sets=number_of_sets, questions=question_sets, generation_status='PENDING', number_of_questions=number_of_questions, subject=subject, standard=standard, chapter_ids=chapter_ids)
                generation_queue.put(item=(priorities[Status.PENDING], next(counter), req))
                print("req is inside the db")
                return {"message":f"Test Generation is inprogress for Test ID: {req.test_id}"}
        else:
            raise HTTPException(status_code=404, detail=f"Record with Test ID: {test_id} is not found in the DB.")
    except Exception:
        print(f"Exception in queue_test(server.py): {traceback.print_exc()}")
    finally:
        cursor.close()
        db.close()

@app.get("/")
def test():
    try:
        db = connect_to_db()
        cursor = db.cursor()
        test_id = get_usage(cursor)
    except Exception:
        print(f"Exception in test(server.py): {traceback.print_exc}")
    finally:
        cursor.close()
        db.close()
    raise HTTPException(status_code=404, detail=f"Record with Test ID: {test_id} is not found in the DB.")

@app.delete("/")
def clear_table_records():
    try:
        db = connect_to_db()
        cursor = db.cursor()
        clear_table(db, cursor)
    except Exception:
        print(f"Exception in clear_table_records(server.py): {traceback.print_exc}")
    finally:
        cursor.close()
        db.close()
    return {"message": "MockTest Table got cleared"}