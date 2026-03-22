import os
import json
import logging
import threading
from typing import Tuple
from mysql.connector import pooling
from dotenv import load_dotenv
from config import queue_limit, max_pool_size
import traceback
from utils import MockTest, Status

_rate_limit_lock = threading.Lock()
_pool_lock = threading.Lock()

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

host_name = os.getenv("HOST_NAME")
user_name = os.getenv("USER_NAME")
password = os.getenv("PASSWORD")
database = os.getenv("DATABASE")

_db_pool = None

def connect_to_db():
    global _db_pool
    try:
        if _db_pool is None:
            with _pool_lock:
                if _db_pool is None:  # double-checked locking — only one thread creates the pool
                    db_config = {
                        "host": host_name,
                        "user": user_name,
                        "passwd": password,
                        "database": database,
                        "charset": "utf8mb4",
                        "use_unicode": True,
                        "init_command": "SET SESSION wait_timeout=28800, interactive_timeout=28800, net_read_timeout=3600, net_write_timeout=3600"
                    }
                    _db_pool = pooling.MySQLConnectionPool(pool_size=max_pool_size, pool_name="my_sql_pool", **db_config)
                    print("DB connection pool created.")
        return _db_pool.get_connection()
    except Exception:
        print(f"Exception in connect_to_db(db_utils.py): {traceback.format_exc()}")
        raise

def get_generation_status(cursor, TestID):
    try:
        q = "select Generation_status from MockTests where TestID = %s"
        cursor.execute(q, (TestID,))
        gen_status = cursor.fetchone()
        if gen_status:
            return gen_status[0]
        else:
            return None
    except Exception:
        print(f"Exception in get_generation_status(db_utils.py): {traceback.format_exc()}")

def log_status(Generation_status, TestID):
    if Generation_status == Status.QUEUED.value:
            logger.info(f"Added {TestID} to generation queue")
    elif Generation_status == Status.COMPLETED.value:
            logger.info(f"Completed generation for test with Test ID: {TestID}")
    elif Generation_status == Status.FAILED.value:
            logger.error(f"Failed the generation for test with Test ID: {TestID}")
    elif Generation_status == Status.PENDING.value:
            logger.info(f"Generation is pending for test with Test ID: {TestID}")

def set_generation_status(db, cursor, TestID, Generation_status):
    """To update the Generation_status for the given TestID"""
    try:
        q = "update MockTests set Generation_status = %s where TestID = %s"
        cursor.execute(q, (Generation_status, TestID))
        db.commit()
        log_status(Generation_status, TestID)
    except Exception:
        print(f"Exception in set_generation_status(db_utils.py): {traceback.format_exc()}")

def save_generated_questions_to_db(db, cursor, TestID, questions):
    """To update the Generation_status for the given TestID"""
    try:
        if questions:
            questions_json_string = [[question.model_dump() for question in sets] for sets in questions]
            sets_json_string = json.dumps(questions_json_string)
        else:
            sets_json_string = None 
        q = "update MockTests set questions = %s where TestID = %s"
        cursor.execute(q,(sets_json_string, TestID))
        db.commit()
    except Exception:
        print(f"Exception in save_generated_questions_to_db(db_utils.py): {traceback.format_exc()}")

def get_records_with_generation_status(cursor, Generation_status:Tuple[str]):
    """To fetch records based on the given status"""
    try:
        mock_tests = []
        # Only select columns that exist in MockTest model
        q1 = """select TestID, Subject, Class, Chapter_context, questions,
                Number_of_questions, Number_of_sets, Generation_status
                from MockTests where Generation_status in {Generation_status}
                AND Class != 'EAPCET'
                order by Generation_status limit %s"""
        q1 = q1.format(Generation_status = Generation_status)
        cursor.execute(q1, (queue_limit, ))
        records =  cursor.fetchall()
        # Define the column names to match the selected columns
        column_names = ['TestID', 'Subject', 'Class', 'Chapter_context', 'questions',
                       'Number_of_questions', 'Number_of_sets', 'Generation_status']
        # print("======== DEBUG DB FETCH ========")

        # print("\nQuery Used (q1):")
        # print(q1)

        # print("\nQueue Limit:")
        # print(queue_limit)

        # print("\nRecords Fetched:")
        # for r in records:
        #     print(r)

        # print("\nColumn Names From MockTests Table:")
        # print(column_names)

        # print("=================================")

        # # Mapping from database column names to MockTest model field names
        # column_mapping = {
        #     'Subject': 'Subject',
        #     'Questions': 'questions',
        #     'Class': 'Class',
        #     'Chapter_context': 'Chapter_context',
        #     'Number_of_questions': 'Number_of_questions',
        #     'TestID': 'TestID',
        #     'Number_of_sets': 'Number_of_sets',
        #     'Generation_status': 'Generation_status'
        # }

        for record in records:
            mock_test = dict()
            for i in range(len(record)):
                # db_column = column_names[i]
                # # Only process columns that are in the MockTest model
                # if db_column in column_mapping:
                #     model_field = column_mapping[db_column]
                #     if model_field == 'questions':
                #         # Handle NULL values for questions column
                #         if record[i] is not None:
                #             mock_test[model_field] = json.loads(record[i])
                #         else:
                #             mock_test[model_field] = None
                #     elif model_field == 'Generation_status':
                #         # Convert string to Status enum
                #         mock_test[model_field] = Status(record[i])
                #     else:
                #         mock_test[model_field] = record[i]
                column_name = column_names[i]
                if column_name == 'questions':
                    # Handle NULL and empty string values for questions column
                    if record[i] is not None and record[i] != "":
                        mock_test[column_name] = json.loads(record[i])
                    else:
                        mock_test[column_name] = None
                elif column_name == 'Generation_status':
                    # Convert string to Status enum
                    mock_test[column_name] = Status(record[i])
                else:
                    mock_test[column_name] = record[i]
            mock_tests.append(MockTest(**mock_test))
        return mock_tests
    except Exception:
        print(f"Exception in get_records_with_generation_status(db_utils.py): {traceback.format_exc()}")
        raise
    
def get_max_requests_per_day():
     """Should return max rate limit per day"""
     ...

# def get_chapters(cursor, Subject:str, Class:str, chapter_ids:Tuple[str]):
#     """Should return list of chapters text"""
#     try:
#         q = "select chapter_text from syllabus where Subject = %s and Class = %s and chapter_id in {chapter_ids}"
#         q = q.format(chapter_ids=chapter_ids if len(chapter_ids)>1 else f"({chapter_ids[0]})")
#         cursor.execute(q, (Subject, Class))
#         chapters = cursor.fetchall()
#         chapters  = list(map(lambda x: x[0], chapters))
#         return chapters
#     except Exception:
#         print(f"Exception in get_usage(db_utils.py): {traceback.format_exc()}")
    
def get_usage(cursor, system_id=1):
    q = "select requests_used from ratelimit where system_id = %s"
    cursor.execute(q, (system_id,))
    usage = cursor.fetchone()
    if usage is None:
        raise RuntimeError(f"No ratelimit row found for system_id={system_id}")
    return int(usage[0])

def set_usage(db, cursor, new_usage, system_id=1):
    q = "update ratelimit set requests_used = %s where system_id = %s"
    cursor.execute(q, (new_usage, system_id))
    db.commit()
    print(f"Updated Rate limit usage to {new_usage}")

def get_question_sets(cursor, TestID):
    try:
        q = "select questions from MockTests where TestID = %s"
        cursor.execute(q, (TestID,))
        questions = cursor.fetchone()
        if questions:
            return questions[0]
        else:
            return None
    except Exception:
        print(f"Exception in get_questions(db_utils.py): {traceback.format_exc()}")

def insert_record(db, cursor, Number_of_sets, question_sets, Generation_status='CREATED', Number_of_questions=0, Subject='', Class='', Chapter_context='', TestID=None):
    try:
        if Generation_status == Status.PENDING.value:
            # print([print(isinstance(question, Question), question) for sets in question_sets for question in sets])
            questions_json_string = [question.model_dump() for sets in question_sets for question in sets]
            sets_json_string = json.dumps([questions_json_string])
        else:
            sets_json_string = json.dumps(question_sets)

        if TestID is not None:
            Q1 = "INSERT INTO MockTests (TestID, Number_of_sets, questions, Generation_status, Number_of_questions, Subject, Class, Chapter_context) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
            cursor.execute(Q1, (TestID, Number_of_sets, sets_json_string, Generation_status, Number_of_questions, Subject, Class, Chapter_context))
        else:
            Q1 = "INSERT INTO MockTests (Number_of_sets, questions, Generation_status, Number_of_questions, Subject, Class, Chapter_context) VALUES (%s, %s, %s, %s, %s, %s, %s)"
            cursor.execute(Q1, (Number_of_sets, sets_json_string, Generation_status, Number_of_questions, Subject, Class, Chapter_context))
        db.commit()
        logger.info("New record is created...")
        print("Inserted into Table")
    except Exception:
        print(f"Exception in insert_record(db_utils.py): {traceback.format_exc()}")


def clear_table(db, cursor):
    try:
        q = "truncate table MockTests"
        cursor.execute(q)
        db.commit()
    except Exception:
        print(f"Exception in clear_table(db_utils.py): {traceback.format_exc()}")


# ==================== EAMCET 160-question DB helpers ====================

def upsert_eamcet160_record(db, cursor, TestID, stream, section_contexts, Generation_status='QUEUED'):
    """Update the pre-existing MockTests row for an EAMCET-160 test.
    Sets Class='EAPCET' so the EAMCET worker (not the existing worker) picks it up."""
    try:
        section_contexts_json = json.dumps(section_contexts)
        q = """UPDATE MockTests
               SET Subject = %s, Class = 'EAPCET', Chapter_context = %s, Generation_status = %s
               WHERE TestID = %s"""
        cursor.execute(q, (stream, section_contexts_json, Generation_status, TestID))
        db.commit()
        log_status(Generation_status, TestID)
    except Exception:
        print(f"Exception in upsert_eamcet160_record(db_utils.py): {traceback.format_exc()}")


def get_eamcet160_records_with_status(cursor, Generation_status: tuple):
    """Fetch only EAPCET rows from MockTests with the given status(es)."""
    try:
        records = []
        q = """select TestID, Subject, Class, Chapter_context, questions,
                Number_of_questions, Number_of_sets, Generation_status
                from MockTests where Generation_status in {Generation_status}
                AND Class = 'EAPCET'
                order by Generation_status limit %s"""
        q = q.format(Generation_status=Generation_status)
        cursor.execute(q, (queue_limit,))
        rows = cursor.fetchall()
        column_names = ['TestID', 'Subject', 'Class', 'Chapter_context', 'questions',
                        'Number_of_questions', 'Number_of_sets', 'Generation_status']
        for row in rows:
            record = {}
            for i, col_name in enumerate(column_names):
                if col_name == 'questions':
                    record[col_name] = json.loads(row[i]) if (row[i] is not None and row[i] != "") else None
                elif col_name == 'Generation_status':
                    record[col_name] = Status(row[i])
                else:
                    record[col_name] = row[i]
            records.append(MockTest(**record))
        return records
    except Exception:
        print(f"Exception in get_eamcet160_records_with_status(db_utils.py): {traceback.format_exc()}")
        raise