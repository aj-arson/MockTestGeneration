import requests
import random
from utils import Status

domain = "http://127.0.0.1:8000"

# possible_status = [Status.PENDING, Status.CREATED]
possible_status = [Status.CREATED]

def construct_new_body(test_id):
    choice = random.choice((0, len(possible_status)-1))
    print(f"Sending Req with status : {possible_status[choice]}")
    questions = [
            [
    {
      "answer": 3,
      "options": [
        "At the focal point",
        "At the center of curvature",
        "At infinity",
        "Between the focal point and the center  of curvature"
      ],
      "question": "question_0 -> 0.9941264512100203",
      "explaination": "When an object is placed at the focal point of a concave mirror, the reflected rays become parallel to the principal axis and meet at infinity, thus forming the image at infinity."
    }
  ]
  ]
    test_details = {
        "test_id":test_id,
        "subject":"",
        "standard":"",
        "chapter_ids":[""],
        "questions":questions if possible_status[choice].value == "PENDING" else None,
        "number_of_questions":2,
        "number_of_sets":20,
        "generation_status": possible_status[choice].value
    }
    return test_details

def post_multiple_requests(num_reqs = 2):
    for i  in range(num_reqs):
        req_body = construct_new_body(i+1)
        response = requests.post(url=domain+"/mocktest", json=req_body)
        print(response)
        print(f"Response: {response.json()['message']}")

def delete():
    response = requests.delete(domain+"/")
    print(response.json()["message"])

delete()
num_reqs = int(input("Num Requests: "))
post_multiple_requests(num_reqs)