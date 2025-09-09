from typing import List
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from  main import generate_questions

class MockTest(BaseModel):
    subject : str
    standard : str
    chapter_ids : List[str]
    number_of_questions : int
    test_id : int
    number_of_sets : int


app = FastAPI()

@app.post("/mocktest")
async def request_mock_test(request:MockTest, background_tasks:BackgroundTasks):
    background_tasks.add_task(generate_questions, request.subject, request.standard, request.chapter_ids, request.number_of_sets, request.number_of_questions, request.test_id)
    return {"message":"generation started..."}