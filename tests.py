import requests
import random
from utils import Status

domain = "http://127.0.0.1:8000"
possible_subjects = ["physics", "social"]
possible_status = ["CREATED", "FAILED"]

chapters = {
    "social": [
        "The French Revolution",
        "Industrial Revolution",
        "Indian Freedom Struggle",
        "World War II",
        "United Nations"
    ],
    "physics": [
        "Motion and Laws of Motion",
        "Work, Energy and Power",
        "Gravitation",
        "Light – Reflection and Refraction",
        "Electricity and Magnetism"
    ],
    "telugu": [
        "వ్యాకరణం (Grammar)",
        "కథలు (Short Stories)",
        "పద్యాలు (Poems)",
        "ప్రసంగాలు (Speeches)",
        "నవలలు (Novels)"
    ]
}

def construct_new_body(test_id):
    choice = random.choice(possible_subjects)
    # choice = "telugu"
    status_choice = random.choice(possible_status)
    num_sets = random.choice((1, 4))
    num_questions = random.choice((1,5))
    print(f"Sending Req with Subject : {choice}")
    print(f"Sending Req with Status : {status_choice}")
    print(f"Sending Req with Num_stets : {num_sets}")
    print(f"Sending Req with Num_questions : {num_questions}")

    with open(r"sample_text_books\chapter1.txt", encoding='utf-8') as f:
        chapter_context = f.read()

    test_details = {
        "test_id":test_id,
        "subject":choice,
        "standard":"10",
        "chapter_context": chapter_context,
        "questions": None,
        "number_of_questions":num_questions,
        "number_of_sets":num_sets,
        "generation_status": status_choice
    }
    return test_details

def post_multiple_requests(num_reqs = 2):
    for i  in range(num_reqs):
        req_body = construct_new_body(i+1)
        response = requests.post(url=domain+"/mocktest", json=req_body)
        print(response)
        print(f"Response: {response.json()['message']}")
        print("="*10)

def delete():
    response = requests.delete(domain+"/")
    print(response.json()["message"])

delete()
num_reqs = int(input("Num Requests: "))
post_multiple_requests(num_reqs)