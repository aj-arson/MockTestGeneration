import json
import unicodedata
import hashlib
import os
from enum import Enum
from typing import List, Optional
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
from pydantic import BaseModel
from datetime import datetime, timedelta

load_dotenv()

class Status(Enum):
    CREATED = 'CREATED'
    QUEUED = 'QUEUED'
    PENDING = 'PENDING'
    COMPLETED = 'COMPLETED'
    FAILED = 'FAILED'

# lower value = high priority
priorities = {
    Status.PENDING : 1,
    Status.QUEUED : 2,
    Status.FAILED : 3,
    Status.CREATED : 3,
    Status.COMPLETED : 4,
}

class Question(BaseModel):
    question : str
    options : List[str]
    answer : int
    explaination : str

class Sets(BaseModel):
    sets : Optional[List[List[Question]]]

class MockTest(BaseModel):
    subject : str
    standard : str
    chapter_ids : List[str|int]
    questions : Optional[List[List[Question]]]
    number_of_questions : int
    test_id : int
    number_of_sets : int
    generation_status : Status

def get_client(client_name:str):
    if client_name == 'google':
        api_key = os.getenv("GOOGLE_API_KEY")
        client = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", api_key = api_key)
    elif client_name == 'openai':
        api_key = os.getenv("OPENAI_API_KEY")
        client = ChatOpenAI(model="", api_key=api_key)
    return client

class Duplicate_checker():
    def __init__(self):
        self.seen = set()
    
    def normalize(self, question:str) -> str:
        q = unicodedata.normalize("NFKC", question)
        q = q.casefold()
        q = "".join(question.lower().split())
        return q
    
    def is_not_duplicate(self, question:str) -> bool:
        norm_question = self.normalize(question)
        hashed_question = hashlib.md5(norm_question.encode('utf-8')).hexdigest()
        if hashed_question in self.seen:
            return False
        else:
            self.seen.add(hashed_question)
            return True

def question_sets_db_to_json(json_string):
    loaded_json = json.loads(json_string)
    generated_sets_json = [[Question(**question) for question in mock_test_set] for mock_test_set in loaded_json ]
    return generated_sets_json

def get_sleep_time_until_midnight():
    now = datetime.now()
    print(datetime.min.time())
    midnight = datetime.combine(now.date() + timedelta(days=1), datetime.min.time())
    seconds_until_midnight = (midnight - now).total_seconds()
    buffer = 35*60
    return seconds_until_midnight + buffer


def clean_text(t):
    return ''.join(ch for ch in unicodedata.normalize('NFC', t))