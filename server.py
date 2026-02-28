from queue import PriorityQueue
import itertools
import json
import os
import traceback
from contextlib import asynccontextmanager
import threading
import time
from main import TestAgent
from fastapi import FastAPI, HTTPException
from db_utils import connect_to_db, get_question_sets, get_usage, insert_record, save_generated_questions_to_db, set_generation_status, clear_table, get_records_with_generation_status, set_usage, upsert_eamcet160_record, get_eamcet160_records_with_status
from config import prompt, json_format, queue_limit, max_requests_per_day, max_questions_per_req, max_consecutive_chunks, eamcet_questions_per_batch, ENGINEERING_SECTIONS, AGRICULTURE_SECTIONS
from utils import MockTest, Question, Status, get_client, get_sleep_time_until_midnight, priorities, question_sets_db_to_json, load_sample_questions, EAMCET160Test, extract_subject_syllabus
import uvicorn

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Per-subject sample questions: loaded once at startup, keyed by subject name
_engineering_subject_examples = {
    s["name"]: load_sample_questions(
        os.path.join(_BASE_DIR, "PreviousQuestionPaper", "Engineering-STREAM", s["name"])
    )
    for s in ENGINEERING_SECTIONS
}
_agriculture_subject_examples = {
    s["name"]: load_sample_questions(
        os.path.join(_BASE_DIR, "PreviousQuestionPaper", "Agriculture_and_Pharmacy-Stream", s["name"])
    )
    for s in AGRICULTURE_SECTIONS
}

already_generated_questions = []
generation_queue = PriorityQueue(maxsize=queue_limit)
eamcet160_generation_queue = PriorityQueue(maxsize=queue_limit)
client = get_client(client_name='google')
counter = itertools.count()
languages = set(["hindi", "telugu"])

def generate_questions(db, cursor, Subject:str, Class:str, Chapter_context, Number_of_questions:int, generation_language:str, format_examples:str=""):
    """
    We will extract the student's study material and generate the mock test based on the following args:
        - Subject : For what Subject we are generating the mock test. Ex: Hindi, Telugu etc.
        - Class : What is the student's class. Ex: LKG, 5th class etc.
        - Chapter_context : Chapter Context is the Syllabus from which the questions need to be generated.
        - Number_of_sets : Specifies the number of exam papers we need to generate.
        - Number_of_questions : Specifies the number of questions per paper/set.
        - TestID : Primary key of the MockTests table. We have to update the row with the given TestID after the test is generated.
        - format_examples : Sample previous year questions for the LLM to understand EAMCET difficulty and style.
    """
    test_creator = TestAgent(db, cursor, client=client, system_prompt=prompt, json_format=json_format, questions_per_batch=max_questions_per_req, generation_language=generation_language, format_examples=format_examples)
    mock_test_set = test_creator(chapters_text=Chapter_context, total_Number_of_questions=Number_of_questions, max_consecutive_chunks=max_consecutive_chunks)
    return mock_test_set
# -------------------------------------------------------------------------------
class BackGroundWorker(threading.Thread):
    def __init__(self, generation_queue:PriorityQueue):
        super().__init__(daemon=True) # stops when the app stops
        self.generation_queue = generation_queue

    def check_if_complete(self, db, cursor, TestID, generated_mock_tests, Number_of_questions):
        all_questions_generated = True
        for test_set in generated_mock_tests:
            if test_set:
                print(f"Comparision b/w num questions generated and actual {len(test_set)} {Number_of_questions}")
                if len(test_set) != Number_of_questions:
                    if len(test_set) > Number_of_questions: # This is a safe check to stop enerating unecessarily
                        test_set = test_set[-Number_of_questions:]
                    else:
                        all_questions_generated = False
            else:
                    print("Nothing to see.")
                    all_questions_generated = False
        print(f"{all_questions_generated = }")
        if all_questions_generated:
            set_generation_status(db=db, cursor=cursor, TestID=TestID, Generation_status=Status.COMPLETED.value)
            print(f"Generation is completed for the test id: {TestID}")
        else:
            print(f"Generation is in-progress for the test id: {TestID}")

    def check_Number_of_questions_to_generate(self, Number_of_sets, Number_of_questions, generated_sets):
        Number_of_questions_to_generate_per_set = []
        for i in range(Number_of_sets):
            generated_questions_per_set = len(generated_sets[i]) if generated_sets[i] else 0
            Number_of_questions_to_generate_per_set.append(Number_of_questions - generated_questions_per_set)
        return Number_of_questions_to_generate_per_set

    def process(self, req:MockTest):
        """This method should process for a single mocktest no matter the number of sets"""
        try:
            db = connect_to_db()
            cursor = db.cursor()
            TestID = req.TestID
            Subject = req.Subject
            generation_language = Subject.upper() if Subject.lower() in languages else 'ENGLISH'
            Class = req.Class
            Chapter_context = req.Chapter_context
            Number_of_questions = req.Number_of_questions
            Number_of_sets = req.Number_of_sets
            generated_sets_string_from_db = get_question_sets(cursor=cursor, TestID=TestID)
            print('generated_sets_string_from_db',generated_sets_string_from_db)
            generated_sets = question_sets_db_to_json(generated_sets_string_from_db)
            # If questions column is NULL, initialize empty sets based on Number_of_sets
            if not generated_sets or len(generated_sets) == 0:
                generated_sets = [[] for _ in range(Number_of_sets)]
            num_questions_to_generate_per_set = self.check_Number_of_questions_to_generate(Number_of_sets, Number_of_questions, generated_sets)
            save_to_db = False
            # print("======== DEBUG VALUES ========")
            # print("TestID:", TestID)
            # print("Subject:", Subject)
            # print("generation_language:", generation_language)
            # print("Class:", Class)
            # print("Chapter_context:", Chapter_context)
            # print("Number_of_questions:", Number_of_questions)
            # print("Number_of_sets:", Number_of_sets)
            # print("generated_sets_string_from_db:", generated_sets_string_from_db)
            # print("generated_sets:", generated_sets)
            # print("num_questions_to_generate_per_set:", num_questions_to_generate_per_set)
            # print("save_to_db:", save_to_db)
            # print("================================")
            format_examples = ""
            for i in range(len(generated_sets)):
                if num_questions_to_generate_per_set[i] > 0:
                    generated_mock_tests = generate_questions(db, cursor, Subject, Class, Chapter_context , num_questions_to_generate_per_set[i], generation_language, format_examples)
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
            self.check_if_complete(db, cursor, TestID, generated_sets, Number_of_questions)
        except Exception:
            print(f"Exception in process(server.py): {traceback.print_exc()}")
            save_generated_questions_to_db(db=db, cursor=cursor, TestID=TestID, questions=None)
            set_generation_status(db=db, cursor=cursor, TestID=TestID, Generation_status=Status.FAILED.value)
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
                        if test_details.Generation_status != Status.PENDING:
                            set_generation_status(db=db, cursor=cursor, TestID=test_details.TestID, Generation_status=Status.PENDING.value)
                        print(f"Started Processing for {test_details.TestID}")
                        self.process(test_details)
                    else:
                        time.sleep(20)
                        print("Waited 20 secs before rechecking...")
                        mock_tests = get_records_with_generation_status(cursor=cursor, Generation_status=(Status.PENDING.value, Status.QUEUED.value))
                        if mock_tests:
                            if len(mock_tests) > 0:
                                print(f"Added {len(mock_tests)} requests to queue.")
                                for test in mock_tests:
                                    self.generation_queue.put(item=(priorities[test.Generation_status], next(counter), test))
                else:
                    print("rate limit hit for today...")
                    time.sleep(get_sleep_time_until_midnight()) # sleeps unitl 12:35 AM midnight
                    set_usage(db, cursor, new_usage=0) # this needs to be done just after the midnight
                    print("limit is reset")
            except Exception:
                print(f"Exception in run(server.py): {traceback.print_exc()}")
            finally:
                try:
                    cursor.close()
                    db.close()
                except Exception as e:
                    print(f"Error closing connection (this is usually harmless): {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("lifespan started!!!")
    worker = BackGroundWorker(generation_queue)
    worker.start()
    eamcet_worker = EAMCET160BackgroundWorker(eamcet160_generation_queue)
    eamcet_worker.start()
    yield
#        # On shutdown: get a fresh connection to mark in-flight tests back to 
#      -PENDING                                                                   
#  189 -    try:                                                                  
#  190 -        db = connect_to_db()                                              
#  191 -        cursor = db.cursor()                                              
#  192 -        for _ in range(generation_queue.qsize()):                         
#  193 -            test_details = generation_queue.get()[-1]                     
#  194 -            set_generation_status(db=db, cursor=cursor, TestID=test_detail
#      -s.TestID, Generation_status=Status.PENDING.value)                         
#  195 -        for _ in range(eamcet160_generation_queue.qsize()):               
#  196 -            eamcet_test = eamcet160_generation_queue.get()[-1]            
#  197 -            set_generation_status(db=db, cursor=cursor, TestID=eamcet_test
#      -.TestID, Generation_status=Status.PENDING.value)                          
#  198 -        cursor.close()                                                    
#  199 -        db.close()                                                        
#  200 -    except Exception:                                                     
#  201 -        print(f"Exception during lifespan shutdown (non-fatal): {traceback
#      -.print_exc()}")  
    print("lifespan ended!!!")
    # Records are already QUEUED/PENDING in DB — the restarted worker will pick them up.
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
        Chapter_context = req.Chapter_context
        Number_of_questions = req.Number_of_questions
        Number_of_sets = req.Number_of_sets
        Generation_status = req.Generation_status.value
        question_sets = req.questions
        print("1",Generation_status,Status.CREATED.value,Status.FAILED.value,Status.COMPLETED.value,Status.QUEUED.value,Status.PENDING.value)
        if Generation_status:
            if Generation_status == Status.CREATED.value or Generation_status == Status.FAILED.value:
                """Need to generate questions from scratch"""
                question_sets = [[] for _ in range(Number_of_sets)]
                # insert_record(db, cursor, Number_of_sets=Number_of_sets, Generation_status='CREATED', question_sets=question_sets, Number_of_questions=Number_of_questions, Subject=Subject, Class=Class, Chapter_context=Chapter_context)
                set_generation_status(db, cursor, TestID, Status.QUEUED.value)
                return {"message":f"Test Generation is Queued for Test ID: {req.TestID}."}
            
            elif Generation_status == Status.COMPLETED.value or Generation_status == Status.QUEUED.value or Generation_status == Status.PENDING.value:
                """We should refuse the requests that are already queued/completed/pending"""
                raise HTTPException(status_code=400, detail=f"The current status is already {Generation_status}. Hence this request is invalid.")
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

@app.post("/mocktest/engineering-stream")
async def queue_engineering_stream_test(req: MockTest):
    try:
        db = connect_to_db()
        cursor = db.cursor()
        TestID = req.TestID
        Number_of_sets = req.Number_of_sets
        Generation_status = req.Generation_status.value
        question_sets = req.questions
        print("1",Generation_status,Status.CREATED.value,Status.FAILED.value,Status.COMPLETED.value,Status.QUEUED.value,Status.PENDING.value)
        if Generation_status:
            if Generation_status == Status.CREATED.value or Generation_status == Status.FAILED.value:
                question_sets = [[] for _ in range(Number_of_sets)]
                set_generation_status(db, cursor, TestID, Status.QUEUED.value)
                return {"message": f"Engineering Stream test generation is queued for Test ID: {req.TestID}."}
            elif Generation_status == Status.COMPLETED.value or Generation_status == Status.QUEUED.value or Generation_status == Status.PENDING.value:
                raise HTTPException(status_code=400, detail=f"The current status is already {Generation_status}. Hence this request is invalid.")
        else:
            raise HTTPException(status_code=404, detail=f"Record with Test ID: {TestID} is not found in the DB.")
    except Exception:
        print(f"Exception in queue_engineering_stream_test(server.py): {traceback.print_exc()}")
    finally:
        cursor.close()
        db.close()

@app.post("/mocktest/agriculture-pharmacy-stream")
async def queue_agriculture_pharmacy_stream_test(req: MockTest):
    try:
        db = connect_to_db()
        cursor = db.cursor()
        TestID = req.TestID
        Number_of_sets = req.Number_of_sets
        Generation_status = req.Generation_status.value
        question_sets = req.questions
        print("1",Generation_status,Status.CREATED.value,Status.FAILED.value,Status.COMPLETED.value,Status.QUEUED.value,Status.PENDING.value)
        if Generation_status:
            if Generation_status == Status.CREATED.value or Generation_status == Status.FAILED.value:
                question_sets = [[] for _ in range(Number_of_sets)]
                set_generation_status(db, cursor, TestID, Status.QUEUED.value)
                return {"message": f"Agriculture & Pharmacy Stream test generation is queued for Test ID: {req.TestID}."}
            elif Generation_status == Status.COMPLETED.value or Generation_status == Status.QUEUED.value or Generation_status == Status.PENDING.value:
                raise HTTPException(status_code=400, detail=f"The current status is already {Generation_status}. Hence this request is invalid.")
        else:
            raise HTTPException(status_code=404, detail=f"Record with Test ID: {TestID} is not found in the DB.")
    except Exception:
        print(f"Exception in queue_agriculture_pharmacy_stream_test(server.py): {traceback.print_exc()}")
    finally:
        cursor.close()
        db.close()

# ==================== EAMCET 160-question worker ====================

class EAMCET160BackgroundWorker(threading.Thread):
    def __init__(self, generation_queue: PriorityQueue):
        super().__init__(daemon=True)
        self.generation_queue = generation_queue

    def process(self, req: MockTest):
        """
        req is a MockTest row where:
          - req.Subject  = stream ('Engineering' or 'Agriculture_and_Pharmacy')
          - req.Chapter_context = JSON string of {section_name: chapter_text, ...}
          - req.TestID, req.Number_of_questions == 160
        Generates questions section-by-section in the defined order, 40 per LLM call.
        """
        db = None
        cursor = None
        try:
            db = connect_to_db()
            cursor = db.cursor()
            TestID = req.TestID
            stream = req.Subject
            section_contexts = json.loads(req.Chapter_context)

            sections = ENGINEERING_SECTIONS if stream == 'Engineering' else AGRICULTURE_SECTIONS
            subject_examples = _engineering_subject_examples if stream == 'Engineering' else _agriculture_subject_examples

            ordered_questions = []

            for section in sections:
                section_name = section["name"]
                num_questions = section["end"] - section["start"] + 1
                context = extract_subject_syllabus(section_contexts.get(section_name, ""), section_name)
                format_examples = subject_examples.get(section_name, "")

                section_agent = TestAgent(
                    db, cursor, client=client,
                    system_prompt=prompt,
                    json_format=json_format,
                    questions_per_batch=eamcet_questions_per_batch,
                    generation_language='ENGLISH',
                    format_examples=format_examples
                )

                section_questions = section_agent(
                    chapters_text=context,
                    total_Number_of_questions=num_questions,
                    max_consecutive_chunks=max_consecutive_chunks
                )
                section_questions = section_questions[:num_questions]

                ordered_questions.extend([Question(**q) for q in section_questions])
                print(f"EAMCET160 [{TestID}] {section_name}: {len(section_questions)} questions generated. Total: {len(ordered_questions)}")

            total_expected = sum(s["end"] - s["start"] + 1 for s in sections)
            save_generated_questions_to_db(db=db, cursor=cursor, TestID=TestID, questions=[ordered_questions])

            if len(ordered_questions) == total_expected:
                set_generation_status(db=db, cursor=cursor, TestID=TestID, Generation_status=Status.COMPLETED.value)
                print(f"EAMCET160: Completed for TestID {TestID} ({len(ordered_questions)} questions)")
            else:
                print(f"EAMCET160: Incomplete for TestID {TestID} — expected {total_expected}, got {len(ordered_questions)}")
                set_generation_status(db=db, cursor=cursor, TestID=TestID, Generation_status=Status.FAILED.value)

        except Exception:
            print(f"Exception in EAMCET160 process(server.py): {traceback.print_exc()}")
            try:
                if db and cursor:
                    save_generated_questions_to_db(db=db, cursor=cursor, TestID=req.TestID, questions=None)
                    set_generation_status(db=db, cursor=cursor, TestID=req.TestID, Generation_status=Status.FAILED.value)
            except Exception:
                pass
        finally:
            if cursor:
                cursor.close()
            if db:
                db.close()

    def run(self):
        print("EAMCET160 Worker started...")
        while True:
            try:
                db = connect_to_db()
                cursor = db.cursor()
                current_usage = get_usage(cursor=cursor)
                remaining_requests = max_requests_per_day - current_usage
                if remaining_requests > 0:
                    if not self.generation_queue.empty():
                        test_details = self.generation_queue.get()[-1]
                        if test_details.Generation_status != Status.PENDING:
                            set_generation_status(db=db, cursor=cursor, TestID=test_details.TestID, Generation_status=Status.PENDING.value)
                        print(f"EAMCET160: Processing TestID {test_details.TestID}")
                        self.process(test_details)
                    else:
                        time.sleep(20)
                        print("EAMCET160: Waited 20 secs before rechecking...")
                        eamcet_tests = get_eamcet160_records_with_status(cursor=cursor, Generation_status=(Status.PENDING.value, Status.QUEUED.value))
                        if eamcet_tests:
                            print(f"EAMCET160: Added {len(eamcet_tests)} requests to queue.")
                            for test in eamcet_tests:
                                self.generation_queue.put(item=(priorities[test.Generation_status], next(counter), test))
                else:
                    print("EAMCET160 worker: rate limit hit for today...")
                    time.sleep(get_sleep_time_until_midnight())
                    set_usage(db, cursor, new_usage=0)
                    print("EAMCET160 worker: limit reset")
            except Exception:
                print(f"Exception in EAMCET160 run(server.py): {traceback.print_exc()}")
            finally:
                try:
                    cursor.close()
                    db.close()
                except Exception as e:
                    print(f"Error closing EAMCET160 connection (usually harmless): {e}")


# ==================== EAMCET 160-question endpoints ====================

@app.post("/eamcet/engineering")
async def queue_eamcet160_engineering(req: EAMCET160Test):
    """Queue an EAMCET Engineering 160-question test (Math 80q, Physics 40q, Chemistry 40q)."""
    db, cursor = None, None
    try:
        print(f"EAMCET160 Engineering: received request for TestID {req.TestID}")
        section_contexts = {s["name"]: req.Section_contexts for s in ENGINEERING_SECTIONS}
        db = connect_to_db()
        cursor = db.cursor()
        upsert_eamcet160_record(db, cursor, req.TestID, req.Stream, section_contexts, Status.QUEUED.value)
        print(f"EAMCET160 Engineering: TestID {req.TestID} queued successfully")
        return {"message": f"EAMCET Engineering 160-question test is queued for Test ID: {req.TestID}."}
    except Exception:
        print(f"Exception in queue_eamcet160_engineering(server.py): {traceback.print_exc()}")
        raise HTTPException(status_code=500, detail="Failed to queue EAMCET Engineering test.")
    finally:
        if cursor: cursor.close()
        if db: db.close()


@app.post("/eamcet/agriculture-pharmacy")
async def queue_eamcet160_agriculture(req: EAMCET160Test):
    """Queue an EAMCET Agriculture & Pharmacy 160-question test (Physics/Chemistry/Botany/Zoology 40q each)."""
    db, cursor = None, None
    try:
        print(f"EAMCET160 Agriculture: received request for TestID {req.TestID}")
        section_contexts = {s["name"]: req.Section_contexts for s in AGRICULTURE_SECTIONS}
        db = connect_to_db()
        cursor = db.cursor()
        upsert_eamcet160_record(db, cursor, req.TestID, req.Stream, section_contexts, Status.QUEUED.value)
        print(f"EAMCET160 Agriculture: TestID {req.TestID} queued successfully")
        return {"message": f"EAMCET Agriculture & Pharmacy 160-question test is queued for Test ID: {req.TestID}."}
    except Exception:
        print(f"Exception in queue_eamcet160_agriculture(server.py): {traceback.print_exc()}")
        raise HTTPException(status_code=500, detail="Failed to queue EAMCET Agriculture & Pharmacy test.")
    finally:
        if cursor: cursor.close()
        if db: db.close()



if __name__ == "__main__":
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
