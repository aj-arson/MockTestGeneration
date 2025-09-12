from queue import PriorityQueue
import itertools
from contextlib import asynccontextmanager
import threading
import time
from typing import List
from main import TestAgent
from fastapi import FastAPI, BackgroundTasks, HTTPException
from db_utils import connect_to_db, get_generation_status, get_usage, insert_record, save_generated_questions_to_db, set_generation_status, clear_table, get_records_with_generation_status, set_usage
from config import prompt, json_format, queue_limit, max_requests_per_day, max_questions_per_req
from utils import MockTest, Status, get_client, priorities


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
def generate_questions(db, cursor, subject:str, standard:str, chapter_ids:List[str], number_of_sets:int, number_of_questions:int, test_id:str):
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
    agent = TestAgent(db, cursor, client=client, system_prompt=prompt, json_format=json_format, questions_per_batch=max_questions_per_req)
    mock_test_sets = agent(chapters_text=chapters_text, total_number_of_questions=number_of_questions, number_of_sets=number_of_sets, max_consecutive_chunks=10)
    return mock_test_sets
# -------------------------------------------------------------------------------
class BackGroundWorker(threading.Thread):
    def __init__(self, generation_queue:PriorityQueue):
        super().__init__(daemon=True) # stops when the app stops
        self.generation_queue = generation_queue

    def process(self, req:MockTest):
        try:
            db = connect_to_db()
            cursor = db.cursor()
            test_id = req.test_id
            subject = req.subject
            standard = req.standard
            chapter_ids = req.chapter_ids
            number_of_questions = req.number_of_questions
            number_of_sets = req.number_of_sets
            mock_tests = generate_questions(subject, standard, chapter_ids, number_of_sets, number_of_questions, test_id)
            save_generated_questions_to_db(db= db, cursor=cursor, test_id=test_id, questions=mock_tests)
            set_generation_status(db=db, cursor=cursor, test_id=test_id, generation_status=Status.COMPLETED.value)
        except Exception as e:
            print(e)
        finally:
            cursor.close()
            db.close()

    def run(self):
        print("Worker started...")
        while True:
            try:
                db = connect_to_db()
                cursor = db.cursor()
                print("Connected to Cursor!!!")
                current_usage = get_usage(cursor=cursor)
                remaining_requests = max_requests_per_day - current_usage
                if remaining_requests > 0:
                    if not self.generation_queue.empty():
                        test_details = self.generation_queue.get()[-1]
                        print(f"remaining jobs: {self.generation_queue.qsize()}")
                        if test_details.test_id != Status.PENDING:
                            set_generation_status(db=db, cursor=cursor, test_id=test_details.test_id, generation_status=Status.PENDING.value)
                        print(f"Started Processing for {test_details.test_id}")
                        # self.process(test_details)
                        time.sleep(10)
                        print(f"Process is completed for {test_details.test_id}")
                        set_usage(db, cursor, new_usage=current_usage+1)
                        print(f"Used: {get_usage(cursor)}")
                        set_generation_status(db=db, cursor=cursor, test_id=test_details.test_id, generation_status=Status.COMPLETED.value)
                        print(f"Updated generation status for {test_details.test_id}")
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
            except Exception as e:
                print(e)
            finally:
                cursor.close()
                db.close()
            

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("lifespan started!!!")
    db = connect_to_db()
    cursor = db.cursor()
    print("Connected to Cursor!!!")
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

        if current_status:
            if current_status == Status.CREATED.value or current_status == Status.FAILED.value:
                """Need to generate questions from scratch"""
                # generation_queue.put(item=(priorities[Status.CREATED if current_status == Status.CREATED.value else Status.FAILED], next(counter), req))
                insert_record(db, cursor, number_of_sets=number_of_sets, generation_status='CREATED', number_of_questions=number_of_questions, subject=subject, standard=standard, chapter_ids=chapter_ids)
                set_generation_status(db, cursor, test_id, Status.QUEUED.value)
                return {"message":f"Test Generation is Queued for Test ID: {req.test_id}."}
            
            elif current_status == Status.COMPLETED.value or current_status == Status.QUEUED.value:
                """We should refuse the requests that are already queued and or completed"""
                raise HTTPException(status_code=400, detail=f"The current status is already {current_status}. Hence this request is invalid.")
            
            elif current_status == Status.PENDING.value:
                """Should get the already generated questions from the db and then append the new generations"""
                insert_record(db, cursor, number_of_sets=number_of_sets, generation_status='PENDING', number_of_questions=number_of_questions, subject=subject, standard=standard, chapter_ids=chapter_ids)
                generation_queue.put(item=(priorities[Status.PENDING], next(counter), req))
                return {"message":f"Test Generation is inprogress for Test ID: {req.test_id}"}
        else:
            raise HTTPException(status_code=404, detail=f"Record with Test ID: {test_id} is not found in the DB.")
    except Exception as e:
        print(e)
    finally:
        cursor.close()
        db.close()

@app.get("/")
def test():
    try:
        db = connect_to_db()
        cursor = db.cursor()
        test_id = get_usage(cursor)
    except Exception as e:
        print(e)
    finally:
        cursor.close()
        db.close()
    raise HTTPException(status_code=404, detail=f"Record with Test ID: {test_id} is not found in the DB.")

@app.delete("/")
def clear_table_records():
    try:
        db = connect_to_db()
        cursor = db.cursor()
        print("cursor created")
        clear_table(db, cursor)
        print("Table cleared")
    except Exception as e:
        print(e)
    finally:
        cursor.close()
        db.close()
    return {"message": "MockTest Table got cleared"}