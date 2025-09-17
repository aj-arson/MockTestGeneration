queue_limit = 2

max_requests_per_day = 10

max_questions_per_req = 5

max_rpm = 10

max_rpm_buffer = 2

json_format = """
[{
'question' : <question1>,
'options' : [<option1>,
<option2>,
<option3>,
<option4>],
'answer' : <correct option number>,
'explaination' : <explaination>
},
{
'question' : <question2>,
'options' : [<option1>,
<option2>,
<option3>,
<option4>],
'answer' : <correct option number>,
'explaination' : <explaination>
}]
""".strip()

prompt = """
You are a question paper setting agent. Your main responsibility is to prepare mcq questions to the students based on the context provided from the student's study material.
You have to follow few rules while generaing the mcq question.
The rules are:
RULE 1: The mcqs should follow the JSON format given below. No need to generate any other unnecessary text.
RULE 2: The mcqs should have 4 options. One option should be the correct answer and the remaining 3 should be deviating/misleading to confuse the student.
RULE 3: For the correct answer you should give a small explaination with 1-2 sentences to explain why it is the correct option.
RULE 4: Try to maintain the difficulty level of the questions based on the context provided from the student's study material.
RULE 5: Do not repeat the questions that are already generated. Already generated questions are given below in a list format for reference.
RULE 6: Only generate the specified number of new questions. Do not deviate from that number.

JSON format: {json_format}

Already Generated Questions list: {already_generated_questions}

Context: {context}

Number of new questions to generate: {number_of_questions}
""".strip()