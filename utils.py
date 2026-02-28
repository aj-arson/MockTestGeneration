import json
import re
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
    Subject : str
    Class : str
    Chapter_context : str
    questions : Optional[List[List[Question]]] = None
    Number_of_questions : int
    TestID : int
    Number_of_sets : int
    Generation_status : Status

    class Config:
        extra = "ignore"  # Ignore extra fields not defined in the model

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
    if json_string is None:
        return []
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

class EAMCET160Test(BaseModel):
    """Request body for the new EAMCET 160-question endpoints.
    Field names match the C# payload exactly (capitalized)."""
    TestID: int
    Stream: str  # 'Engineering' or 'Agriculture_and_Pharmacy'
    Section_contexts: str  # JSON dict string {"Mathematics": "...", ...} or plain chapter text

    class Config:
        extra = "ignore"


def extract_subject_syllabus(full_syllabus: str, subject_name: str) -> str:
    """Extract a single subject's section from a combined syllabus file.
    Syllabus sections are delimited by 'SUBJECT: <NAME>' headers.
    Falls back to the full syllabus text if the subject header is not found."""
    pattern = rf'(SUBJECT:\s*{re.escape(subject_name.upper())}\s*\n.*?)(?=SUBJECT:\s|\Z)'
    match = re.search(pattern, full_syllabus, re.DOTALL | re.IGNORECASE)
    # print(re.escape(subject_name.upper()), pattern, full_syllabus)
    # print("its a match", match)
    if match:
        # print("its a matchoooooooooo", match)
        return match.group(1).strip()
    return full_syllabus


def load_sample_questions(file_path: str, sample_chars: int = 3000) -> str:
    """Load a sample of previous year questions from a file for LLM format/difficulty reference.
    Returns an empty string on failure so the prompt is unaffected for non-EAMCET tests."""
    try:
        try:
            with open(file_path, 'r', encoding='utf-16') as f:
                content = f.read()
        except (UnicodeDecodeError, UnicodeError):
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        sample = content[:sample_chars].strip()
        if sample:
            return f"Sample Exam Questions (difficulty and style reference only — do NOT copy):\n{sample}\n"
        return ""
    except Exception as e:
        print(f"Error loading sample questions from {file_path}: {e}")
        return ""
