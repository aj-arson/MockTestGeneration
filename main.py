import json
import time
import traceback
from langchain_google_genai import ChatGoogleGenerativeAI
from typing import List
from langchain_core.prompts import PromptTemplate
from langchain.text_splitter import RecursiveCharacterTextSplitter
from db_utils import get_usage, set_usage
from config import max_requests_per_day, max_rpm, max_rpm_buffer
from utils import Duplicate_checker, Question
import random

x = '{"question": "zzz", "options": ["At the focal point", "At the center of curvature", "At infinity", "Between the focal point and the center of curvature"], "answer": 3, "explaination": "When an object is placed at the focal point of a concave mirror, the reflected rays become parallel to the principal axis and meet at infinity, thus forming the image at infinity."}'
checker = Duplicate_checker()

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

    def __init__(self, db, cursor, client:ChatGoogleGenerativeAI, system_prompt:str=None, json_format:str=None, already_generated_questions:List[str]=[], questions_per_batch:int=5):
        self.db = db
        self.cursor = cursor
        self.mcqs = []
        self.client = client
        self.questions_per_batch = questions_per_batch
        self.already_generated_questions = already_generated_questions
        template = PromptTemplate(template=system_prompt, input_variables=["json_format", "already_generated_questions", "context", "number_of_questions"])
        self.prompt_template = template.partial(json_format=json_format)

    def parse_json(self, result) -> List[Question]:
        print(result)
        result = result.content
        if "```json" in result:
            result = result[len("```json"):]
        if "```" in result:
            result = result[:-len("```")]
        parsed_result = json.loads(str(result))
        # parsed_result = list(map(lambda x :json.loads(str(x)), result))
        return parsed_result
        # return result
        
    def update_questions_data(self, parsed_result: List[Question], k_recent:int=10):
        print(f"{parsed_result =}")
        for i in range(len(parsed_result)):
            if checker.is_not_duplicate(parsed_result[i]['question']):
                self.already_generated_questions.append(parsed_result[i]['question'])
                self.mcqs.append(parsed_result[i])
        self.already_generated_questions = self.already_generated_questions[-k_recent:]

    def text_to_chunks(self, context:str) -> List[str]:
        splitter = RecursiveCharacterTextSplitter(chunk_size=1000, length_function=len)
        splits = splitter.split_text(context)
        return splits
    
    def execute(self, context:str, total_number_of_questions:int) -> str:
        """
        Takes context and total number of questions as args and executes batch generation to ensure the better use of model's context length.
        """
        
        if (total_number_of_questions - len(self.mcqs) >= self.questions_per_batch) and (total_number_of_questions != len(self.mcqs)):
            number_of_questions_per_iter = self.questions_per_batch
        else:
            number_of_questions_per_iter = total_number_of_questions - len(self.mcqs)

        prompt = self.prompt_template.format(already_generated_questions=self.already_generated_questions, context=context, number_of_questions=number_of_questions_per_iter)
        print(f"{number_of_questions_per_iter = }")
        try:
            result = self.client.invoke(prompt)
            time.sleep((60//max_rpm)+max_rpm_buffer)
            # result = [x.replace("zzz", f"question_{i} -> {random.random()}") for i in range(number_of_questions_per_iter)]
        except Exception:
            print(f"Exception in execute(main.py): {traceback.print_exc()}")
        return result

    def __call__(self, chapters_text:List[str], total_number_of_questions:int, max_consecutive_chunks:int=5):         
            contexts = []
            for chapter in chapters_text:
                contexts.append(self.text_to_chunks(chapter))
                count = 0
                iter_count = 0
            while count<total_number_of_questions:
                current_usage = get_usage(cursor=self.cursor)
                remaining_usage = max_requests_per_day - current_usage
                if remaining_usage > 0:
                    chapter_choice = random.choice(range(len(chapters_text)))
                    context_choice = contexts[chapter_choice]
                    context_start_index = random.choice(range(len(context_choice)-max_consecutive_chunks))
                    context = " ".join(context_choice[context_start_index : context_start_index+max_consecutive_chunks])
                    result = self.execute(context, total_number_of_questions)
                    iter_count += 1
                    print(f"Iterated for {iter_count}")
                    set_usage(self.db, self.cursor, new_usage=current_usage+1)
                    parsed_result = self.parse_json(result)
                    self.update_questions_data(parsed_result)
                    count += len(self.mcqs)
                    print(count, len(self.mcqs))
                else:
                    return self.mcqs
            return self.mcqs
# -------------------------------------------------------------------------------