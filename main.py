import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from typing import List
from pydantic import BaseModel
import json

load_dotenv()

api_key = os.getenv("GOOGLE_API_KEY")
client = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", api_key = api_key)

# -------------------------------------------------------------------------------
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

already_generated_questions = []
with open("chapter1.txt", "r") as f1:
    chapter1 = f1.read()

with open("chapter2.txt", "r", encoding="utf-8") as f2:
    chapter2 = f2.read()


number_of_questions = 3

# -------------------------------------------------------------------------------

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

# -------------------------------------------------------------------------------

from langchain_core.prompts import PromptTemplate
from langchain.text_splitter import RecursiveCharacterTextSplitter
import random

class Question(BaseModel):
    question : str
    options : List[str]
    answer : str
    explaination : str

class TestAgent:
    """
    TODO: 
    - need to fetch all the chunks from the database for the related chapters in the form of list of lists. Outer list for chapters and inner list for chunks in that chapter
    - now randomly sample the chapter and then randomly sample the chunks from the sampled chapter, this is our context.
    - maybe when sampling the chunks try to have a threshold, say 10 if total chunks in a chapter are 50. randomly sample from 1-40. say we got 4. Then our context chunks will be from 4 to 10+4 => 4-14
      this will keep the context better and on topic. If this is the case then we don't need to have overlaps.
    - now with the context we will make request to llm. This is a single request. For a single request we will generate some N number of questions, where N <= total number of questions and N is the
      max number of questions to generate per request. This makes it easy and faster.
    - for every generation we will update the questions list and the mcqs list. First one to prevent duplicate questions and the second one is for the actual test
    - after all the questions are generated, we will iterate through the mcqs list and store in db
    """

    def __init__(self, client:ChatGoogleGenerativeAI, system_prompt:str = None, json_format:str=None, already_generated_questions:List[str]=[], mcqs:List[Question]=[], questions_per_batch:int=5):
        self.prompt_template = PromptTemplate(template=system_prompt, input_variables=["json_format", "already_generated_questions", "context", "number_of_questions"])
        self.prompt_template = self.prompt_template.partial(json_format=json_format)
        self.already_generated_questions = already_generated_questions
        self.mcqs = mcqs
        self.client = client
        self.questions_per_batch = questions_per_batch

    def parse_json(self, result) -> List[Question]:
        result = result.content
        if "```json" in result:
            result = result[len("```json"):]
        if "```" in result:
            result = result[:-len("```")]
        parsed_result = json.loads(str(result))
        return parsed_result
        
    def update_questions_data(self, parsed_result: List[Question]):
        for i in range(len(parsed_result)):
            self.already_generated_questions.append(parsed_result[i]['question'])
            self.mcqs.append(parsed_result[i])

    def text_to_chunks(self, context:str) -> List[str]:
        splitter = RecursiveCharacterTextSplitter(chunk_size=1000, length_function=len)
        splits = splitter.split_text(context)
        return splits
    
    def execute(self, context:str, total_number_of_questions:int) -> str:
        """
        Takes context and total number of questions as args and executes batch generation to ensure the better use of model's context length.
        """
        if (total_number_of_questions - len(self.mcqs)) & (total_number_of_questions != len(self.mcqs))>= self.questions_per_batch:
            number_of_questions_per_iter = self.questions_per_batch
        else:
            number_of_questions_per_iter = total_number_of_questions - len(self.mcqs)

        prompt = self.prompt_template.format(already_generated_questions=self.already_generated_questions, context=context, number_of_questions=number_of_questions_per_iter)
        try:
            result = self.client.invoke(prompt)
        except Exception as e:
            print(f"Encountered Exception: {e}")
        return result

    def __call__(self, chapters_text:List[str], total_number_of_questions:int, number_of_sets:int=1, max_consecutive_chunks:int=5):
        contexts = []
        mock_test_sets = []
        for chapter in chapters_text:
            contexts.append(self.text_to_chunks(chapter))
        for _ in range(number_of_sets):
            count = 0
            while count<total_number_of_questions:
                chapter_choice = random.choice(range(len(chapters_text)))
                context_choice = contexts[chapter_choice]
                context_start_index = random.choice(range(len(context_choice)-max_consecutive_chunks))
                context = " ".join(context_choice[context_start_index : context_start_index+max_consecutive_chunks])
                result = self.execute(context, total_number_of_questions)
                parsed_result = self.parse_json(result)
                self.update_questions_data(parsed_result)
                count += len(self.mcqs)
                print(count, len(self.mcqs))
            mock_test_sets.append(self.mcqs)
            self.mcqs = []
        return mock_test_sets
    
# -------------------------------------------------------------------------------

def generate_questions(subject:str, standard:str, chapter_ids:List[str], number_of_sets:int, number_of_questions:int, test_id:str):
    """
    We will extract the student's study material and generate the mock test based on the following args:
        - subject : For what subject we are generating the mock test. Ex: Hindi, Telugu etc.
        - standard : What is the student's class. Ex: LKG, 5th class etc.
        - chapter_ids : Chapter ids are used to fetch the study material information from the db.
        - number_of_sets : Specifies the number of exam papers we need to generate.
        - number_of_questions : Specifies the number of questions per paper/set.
        - test_id : Primary key of the MockTest table. We have to update the row with the given test_id after the test is generated.
    """
    def save_to_db():
        """
        Saves the mcqs to db
        """
        ...

    def save_to_file(mock_test_sets):
        with open("test.json", "w") as file:
            file.write(json.dumps(mock_test_sets))
        print("Saved to json!")
    
    chapters_text = [chapter1, chapter2] # get the text from the database for the required chapters using subject, standard, chapter_ids
    agent = TestAgent(client=client, system_prompt=prompt, json_format=json_format, questions_per_batch=5)
    mock_test_sets = agent(chapters_text=chapters_text, total_number_of_questions=number_of_questions, number_of_sets=number_of_sets, max_consecutive_chunks=10)
    save_to_file(mock_test_sets=mock_test_sets)
    print("Mock Test is ready!!!")
    