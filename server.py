from queue import PriorityQueue
import itertools
import traceback
from contextlib import asynccontextmanager
import threading
import time
from main import TestAgent
from fastapi import FastAPI, HTTPException
from db_utils import connect_to_db, get_question_sets, get_usage, insert_record, save_generated_questions_to_db, set_generation_status, clear_table, get_records_with_generation_status, set_usage
from config import prompt, json_format, queue_limit, max_requests_per_day, max_questions_per_req, max_consecutive_chunks
from utils import MockTest, Question, Status, get_client, get_sleep_time_until_midnight, priorities, question_sets_db_to_json
import uvicorn

already_generated_questions = []
generation_queue = PriorityQueue(maxsize=queue_limit)
client = get_client(client_name='google')
counter = itertools.count()
languages = set(["hindi", "telugu"])

def generate_questions(db, cursor, Subject:str, Class:str, chapter_context, number_of_questions:int, generation_language:str):
    """
    We will extract the student's study material and generate the mock test based on the following args:
        - Subject : For what Subject we are generating the mock test. Ex: Hindi, Telugu etc.
        - Class : What is the student's class. Ex: LKG, 5th class etc.
        - chapter_context : Chapter Context is the Syllabus from which the questions need to be generated.
        - number_of_sets : Specifies the number of exam papers we need to generate.
        - number_of_questions : Specifies the number of questions per paper/set.
        - TestID : Primary key of the MockTests table. We have to update the row with the given TestID after the test is generated.
    """
    # chapters_text = get_chapters(cursor=cursor, Subject=Subject, Class=Class, chapter_context=chapter_context) # get the text from the database for the required chapters using Subject, Class, chapter_ids
    test_creator = TestAgent(db, cursor, client=client, system_prompt=prompt, json_format=json_format, questions_per_batch=max_questions_per_req, generation_language=generation_language)
    mock_test_set = test_creator(chapters_text=chapter_context, total_number_of_questions=number_of_questions, max_consecutive_chunks=max_consecutive_chunks)
    return mock_test_set
# -------------------------------------------------------------------------------
class BackGroundWorker(threading.Thread):
    def __init__(self, generation_queue:PriorityQueue):
        super().__init__(daemon=True) # stops when the app stops
        self.generation_queue = generation_queue

    def check_if_complete(self, db, cursor, TestID, generated_mock_tests, number_of_questions):
        all_questions_generated = True
        for test_set in generated_mock_tests:
            if test_set:
                print(f"Comparision b/w num questions generated and actual {len(test_set)} {number_of_questions}")
                if len(test_set) != number_of_questions:
                    if len(test_set) > number_of_questions: # This is a safe check to stop enerating unecessarily
                        test_set = test_set[-number_of_questions:]
                    else:
                        all_questions_generated = False
            else:
                    print("Nothing to see.")
                    all_questions_generated = False
        print(f"{all_questions_generated = }")
        if all_questions_generated:
            set_generation_status(db=db, cursor=cursor, TestID=TestID, generation_status=Status.COMPLETED.value)
            print(f"Generation is completed for the test id: {TestID}")
        else:
            print(f"Generation is in-progress for the test id: {TestID}")

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
            TestID = req.TestID
            Subject = req.Subject
            generation_language = Subject.upper() if Subject.lower() in languages else 'ENGLISH'
            Class = req.Class
            chapter_context = req.chapter_context
            number_of_questions = req.number_of_questions
            number_of_sets = req.number_of_sets
            generated_sets_string_from_db = get_question_sets(cursor=cursor, TestID=TestID)
            print('generated_sets_string_from_db',generated_sets_string_from_db)
            generated_sets = question_sets_db_to_json(generated_sets_string_from_db)
            num_questions_to_generate_per_set = self.check_number_of_questions_to_generate(number_of_sets, number_of_questions, generated_sets)
            save_to_db = Falseprint("======== DEBUG VALUES ========")
            print("TestID:", TestID)
            print("Subject:", Subject)
            print("generation_language:", generation_language)
            print("Class:", Class)
            print("chapter_context:", chapter_context)
            print("number_of_questions:", number_of_questions)
            print("number_of_sets:", number_of_sets)
            print("generated_sets_string_from_db:", generated_sets_string_from_db)
            print("generated_sets:", generated_sets)
            print("num_questions_to_generate_per_set:", num_questions_to_generate_per_set)
            print("save_to_db:", save_to_db)
            print("================================")
            for i in range(len(generated_sets)):
                if num_questions_to_generate_per_set[i] > 0:
                    generated_mock_tests = generate_questions(db, cursor, Subject, Class, chapter_context , num_questions_to_generate_per_set[i], generation_language)
                    print("33",generated_mock_tests)
                    if generated_sets[i]:
                        generated_sets[i].extend([Question(**question) for question in generated_mock_tests])
                    else:
                        generated_sets[i] = [Question(**question) for question in generated_mock_tests]
                    save_to_db = True
            if save_to_db:
                save_generated_questions_to_db(db=db, cursor=cursor, TestID=TestID, questions=generated_sets)
            else:
                print("No saving/updating needed")
            self.check_if_complete(db, cursor, TestID, generated_sets, number_of_questions)
        except Exception:
            print(f"Exception in process(server.py): {traceback.print_exc()}")
            save_generated_questions_to_db(db=db, cursor=cursor, TestID=TestID, questions=None)
            set_generation_status(db=db, cursor=cursor, TestID=TestID, generation_status=Status.FAILED.value)
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
                print('2',remaining_requests)
                if remaining_requests > 0:
                    print('22',generation_queue.empty())
                    if not self.generation_queue.empty():
                        test_details = self.generation_queue.get()[-1]
                        print('222',test_details)
                        if test_details.generation_status != Status.PENDING:
                            set_generation_status(db=db, cursor=cursor, TestID=test_details.TestID, generation_status=Status.PENDING.value)
                        print(f"Started Processing for {test_details.TestID}")
                        self.process(test_details)
                    else:
                        time.sleep(10)
                        print("Waited 10 secs before rechecking...")
                        mock_tests = get_records_with_generation_status(cursor=cursor, generation_status=(Status.PENDING.value, Status.QUEUED.value))
                        if mock_tests:
                            if len(mock_tests) > 0:
                                print(f"Added {len(mock_tests)} requests to queue.")
                                for test in mock_tests:
                                    self.generation_queue.put(item=(priorities[test.generation_status], next(counter), test))
                else:
                    print("rate limit hit for today...")
                    time.sleep(get_sleep_time_until_midnight()) # sleeps unitl 12:35 AM midnight
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
        set_generation_status(db=db, cursor=cursor, TestID=test_details.TestID, generation_status=Status.PENDING.value)
    cursor.close()
    db.close()
    print("lifespan ended!!!")
# -------------------------------------------------------------------------------
app = FastAPI(lifespan=lifespan)

@app.post("/mocktest")
async def queue_mock_test(req:MockTest):
    try:
        db = connect_to_db()
        cursor = db.cursor()
        TestID = req.TestID
        Subject = req.Subject
        Class = req.Class
        chapter_context = req.chapter_context
        number_of_questions = req.number_of_questions
        number_of_sets = req.number_of_sets
        current_status = req.generation_status.value
        question_sets = req.questions
        print("1",current_status,Status.CREATED.value,Status.FAILED.value,Status.COMPLETED.value,Status.QUEUED.value,Status.PENDING.value)
        if current_status:
            if current_status == Status.CREATED.value or current_status == Status.FAILED.value:
                """Need to generate questions from scratch"""
                question_sets = [[] for _ in range(number_of_sets)]
                # insert_record(db, cursor, number_of_sets=number_of_sets, generation_status='CREATED', question_sets=question_sets, number_of_questions=number_of_questions, Subject=Subject, Class=Class, chapter_context=chapter_context)
                set_generation_status(db, cursor, TestID, Status.QUEUED.value)
                return {"message":f"Test Generation is Queued for Test ID: {req.TestID}."}
            
            elif current_status == Status.COMPLETED.value or current_status == Status.QUEUED.value or current_status == Status.PENDING.value:
                """We should refuse the requests that are already queued/completed/pending"""
                raise HTTPException(status_code=400, detail=f"The current status is already {current_status}. Hence this request is invalid.")
        else:
            raise HTTPException(status_code=404, detail=f"Record with Test ID: {TestID} is not found in the DB.")
    except Exception:
        print(f"Exception in queue_test(server.py): {traceback.print_exc()}")
    finally:
        cursor.close()
        db.close()

@app.get("/mocktest/{TestID}")
def get_mock_test(TestID):
    try:
        db = connect_to_db()
        cursor = db.cursor()
        question_sets_string = get_question_sets(cursor, TestID)
        if question_sets_string:
            response = question_sets_db_to_json(question_sets_string)
            return {"question_sets" : response}
        else:
            raise HTTPException(status_code=404, detail=f"Record with Test ID: {TestID} is not found in the DB.")
    finally:
        cursor.close()
        db.close()

@app.delete("/")
def clear_table_records():
    try:
        db = connect_to_db()
        cursor = db.cursor()
        clear_table(db, cursor)
    except Exception:
        # print(f"Exception in clear_table_records(server.py): {traceback.print_exc()}")
        print("Db delete excepetion.")
    finally:
        cursor.close()
        db.close()
    return {"message": "MockTest Table got cleared"}

if __name__ == "__main__":
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)