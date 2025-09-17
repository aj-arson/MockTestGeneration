import unicodedata
import hashlib
import os
from enum import Enum
from typing import List, Optional
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
from pydantic import BaseModel

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
    chapter_ids : List[str]
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
        q = unicodedata.normalize("NFKC")
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