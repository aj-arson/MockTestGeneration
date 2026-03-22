queue_limit = 5 # defines the number of requests that can be loaded into worker's queue
num_options_per_question = 4 # used for validating the generated content
max_requests_per_day = 950 # to limit the number of requests per day
max_questions_per_req = 5 # max number of questions per generation
max_rpm = 10 # max number of requests per min
max_rpm_buffer = 2 # just a buffer for max_rpm, just for safe side
max_chunk_size_for_splitting = 1000 # chunking size for chapters
max_consecutive_chunks = 10 #  number of consecutive chunks to make a context
max_pool_size = 10  # 2 workers (when active) + up to 8 concurrent API requests; pool created once at startup so only costs 10 of the hourly connection limit
json_format = """
[{
'question' : <English question1>\n<Telugu question1>,
'options' : [<English option1>\n<Telugu option1>,
<English option2>\n<Telugu option2>,
<English option3>\n<Telugu option3>,
<English option4>\n<Telugu option4>],
'answer' : <correct option number>,
'explaination' : <explaination>
},
{
'question' : <English question2>\n<Telugu question2>,
'options' : [<English option1>\n<Telugu option1>,
<English option2>\n<Telugu option2>,
<English option3>\n<Telugu option3>,
<English option4>\n<Telugu option4>],
'answer' : <correct option number>,
'explaination' : <explaination>
}]
""".strip()

prompt = """
You are a question paper setting agent. Your main responsibility is to prepare mcq questions to the students based on the context provided from the student's study material.
You have to follow few rules while generaing the mcq question.
The rules are:
RULE 1: The mcqs should follow the JSON format given below. No need to generate any other unnecessary text.
RULE 2: The mcqs should have 4 different options(No repetation) per question. One option should be the correct answer and the remaining 3 should be deviating/misleading to confuse the student.
RULE 3: For the correct answer you should give a small explaination with 1-2 sentences to explain why it is the correct option.
RULE 4: The generation language should be based on the below parameter with name Generation Language.
RULE 5: Try to maintain the difficulty level of the questions based on the context provided from the student's study material.
RULE 6: Do not repeat the questions that are already generated. Already generated questions are given below in a list format for reference.
RULE 7: Only generate the specified number of new questions. Do not deviate from that number.
RULE 8: Never use the already generated questions as the context to generate new questions. Strictly use them as guide to generate unique questions.
RULE 9: If sample exam questions are provided below, use them ONLY as a reference to match the difficulty level, complexity, and question style. Do NOT copy or rephrase those sample questions.
RULE 10: Always wrap any mathematical expression, formula, symbol, or equation inside dollar signs using LaTeX notation. For inline math use $...$ (e.g., $a \times b$, $\theta$, $\vec{a}$, $x^2 + y^2 = r^2$). Never write raw LaTeX commands outside of dollar signs.
RULE 11: Every question and every option must contain both the English text and its Telugu translation, separated by a newline character (\n). Format: "<English text>\n<Telugu text>". Apply this to both the 'question' field and every item in the 'options' list. The 'answer' and 'explaination' fields should remain in English only.

JSON format: {json_format}

Generation Language: {generation_language}

{format_examples}
Already Generated Questions list: {already_generated_questions}

Context: {context}

Number of new questions to generate: {Number_of_questions}
""".strip()

# ==================== EAMCET 160-question config ====================
eamcet_questions_per_batch = 20  # LLM generates 20 questions per call for EAMCET-160

ENGINEERING_SECTIONS = [
    {"name": "Mathematics", "start": 0,   "end": 79},
    {"name": "Physics",     "start": 80,  "end": 119},
    {"name": "Chemistry",   "start": 120, "end": 159},
]

AGRICULTURE_SECTIONS = [
    {"name": "Botany",   "start": 0,   "end": 39},
    {"name": "Zoology", "start": 40,  "end": 79},
    {"name": "Physics",    "start": 80,  "end": 119},
    {"name": "Chemistry",   "start": 120, "end": 159},
]