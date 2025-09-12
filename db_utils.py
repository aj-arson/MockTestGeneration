import os
import json
import logging
from typing import Tuple
from mysql.connector import pooling
from dotenv import load_dotenv
from config import queue_limit
from utils import MockTest, Status

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

host_name = os.getenv("HOST_NAME")
user_name = os.getenv("USER_NAME")
password = os.getenv("PASSWORD")
database = os.getenv("DATABASE")

def connect_to_db():
    try:
        db_config = {
        "host":host_name,
        "user":user_name,
        "passwd":password,
        "database":database
        }
        connection_pool = pooling.MySQLConnectionPool(pool_size=5, pool_name="my_sql_pool", **db_config)
        print("DB is connected....")
        return connection_pool.get_connection()
    except Exception as e:
        print(e)

def get_generation_status(cursor, test_id):
    try:
        q = f"select generation_status from mocktest where test_id = '{test_id}'"
        cursor.execute(q)
        gen_status = cursor.fetchone()
        if gen_status:
            return gen_status[0]
        else:
            return None
    except Exception as e:
        print(e)

def log_status(generation_status, test_id):
    if generation_status == Status.QUEUED.value:
            logger.info(f"Added {test_id} to generation queue")
    elif generation_status == Status.COMPLETED.value:
            logger.info(f"Completed generation for test with Test ID: {test_id}")
    elif generation_status == Status.FAILED.value:
            logger.error(f"Failed the generation for test with Test ID: {test_id}")
    elif generation_status == Status.PENDING.value:
            logger.info(f"Generation is pending for test with Test ID: {test_id}")

def set_generation_status(db, cursor, test_id, generation_status):
    """To update the generation_status for the given test_id"""
    try:
        q = f"update mocktest set generation_status = '{generation_status}' where test_id = '{test_id}'"
        cursor.execute(q)
        db.commit()
        log_status(generation_status, test_id)
    except Exception as e:
        print(e)

def save_generated_questions_to_db(db, cursor, test_id, questions):
    """To update the generation_status for the given test_id"""
    try:
        q = f"update mocktest set questions = '{questions}' where test_id = '{test_id}'"
        cursor.execute(q)
        db.commit()
    except Exception as e:
        print(e)

def get_records_with_generation_status(cursor, generation_status:Tuple[str]):
    """To fetch records based on the given status"""
    try:
        mock_tests = []
        q1 = f"select * from mocktest where generation_status in {generation_status} order by generation_status limit {queue_limit}"
        cursor.execute(q1)
        records =  cursor.fetchall()
        q2 = "show columns from mocktest"
        cursor.execute(q2)
        column_names = [col[0] for col in cursor.fetchall()]
        for record in records:
            mock_test = dict()
            for i in range(len(record)):
                if column_names[i] in ('questions', 'chapter_ids'):
                    mock_test[column_names[i]] = json.loads(record[i])
                else:
                    mock_test[column_names[i]] = record[i]
            mock_tests.append(MockTest(**mock_test))
        return mock_tests
    except Exception as e:
        print(e)
    
def get_max_requests_per_day():
     ...
    
def get_usage(cursor, system_id=1):
    try:
        q = f"select requests_used from ratelimit where system_id = '{system_id}'"
        cursor.execute(q)
        usage = cursor.fetchone()
        return int(usage[0])
    except Exception as e:
        print(e)

def set_usage(db, cursor, new_usage, system_id=1):
    try:
        q = f"update ratelimit set requests_used = {new_usage} where system_id = {system_id}"
        cursor.execute(q)
        db.commit()
        print(f"Updated Rate limit usage to {new_usage}")
    except Exception as e:
        print(e)

def insert_record(db, cursor, number_of_sets, questions=[], generation_status='CREATED', number_of_questions=0, subject='', standard='', chapter_ids=[]):
    try:
        questions_json_string = json.dumps(questions)
        chapter_ids_json_string = json.dumps(chapter_ids)
        Q1 = "INSERT INTO MockTest (number_of_sets, questions, generation_status, number_of_questions, subject, standard, chapter_ids) VALUES (%s, %s, %s, %s, %s, %s, %s)"
        cursor.execute(Q1, (number_of_sets, questions_json_string, generation_status, number_of_questions, subject, standard, chapter_ids_json_string))
        db.commit()
        logger.info("New record is created...")
        print("Inserted into Table")
    except Exception as e:
        print(e)


def clear_table(db, cursor):
    try:
        q = "truncate table mocktest"
        print("this happened")
        cursor.execute(q)
        print("cursor executed")
        db.commit()
    except Exception as e:
        print(e)