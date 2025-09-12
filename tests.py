import requests
import random
from utils import Status

domain = "http://127.0.0.1:8000"

possible_status = [Status.PENDING, Status.CREATED]

def construct_new_body(test_id):
    choice = random.choice((0, len(possible_status)-1))
    print(f"Sending Req with status : {possible_status[choice]}")
    test_details = {
        "test_id":test_id,
        "subject":"",
        "standard":"",
        "chapter_ids":[""],
        "questions":[],
        "number_of_questions":0,
        "number_of_sets":0,
        "generation_status": possible_status[choice].value
    }
    return test_details

def post_multiple_requests(num_reqs = 2):
    for i  in range(num_reqs):
        req_body = construct_new_body(i+1)
        response = requests.post(url=domain+"/mocktest", json=req_body)
        print(f"Response: {response.json()['message']}")

def delete():
    response = requests.delete(domain+"/")
    print(response.json()["message"])

print("""Choose Options :\n1) Generate new req\n2) Clear Db""")
choice = int(input("\nEnter your choice: "))
if choice == 1:
    num_reqs = int(input("Num Requests: "))
    post_multiple_requests(num_reqs)
else:
    delete()