import json
import re
import time
import traceback
from langchain_google_genai import ChatGoogleGenerativeAI
from typing import List, Union
from langchain_core.prompts import PromptTemplate
from langchain_text_splitters import RecursiveCharacterTextSplitter
from db_utils import get_usage, set_usage
from config import max_requests_per_day, max_rpm, max_rpm_buffer, max_chunk_size_for_splitting, num_options_per_question
from utils import Duplicate_checker, Question, clean_text
from colorama import Fore, init
import random

checker = Duplicate_checker()

init(autoreset=True)

class TestAgent:
    def __init__(self, db, cursor, client:ChatGoogleGenerativeAI, system_prompt:str=None, json_format:str=None, questions_per_batch:int=5, generation_language="ENGLISH", format_examples:str=""):
        self.db = db
        self.cursor = cursor
        self.mcqs = []
        self.client = client
        self.questions_per_batch = questions_per_batch
        self.already_generated_questions = []
        template = PromptTemplate(template=system_prompt, input_variables=["json_format", "already_generated_questions", "context", "Number_of_questions", "format_examples"])
        self.prompt_template = template.partial(json_format=json_format, generation_language=generation_language, format_examples=format_examples)

    def parse_json(self, result) -> List[Question]:
        result = result.content
        if "```json" in result:
            result = result[len("```json"):]
        if "```" in result:
            result = result[:-len("```")]
        # Fix invalid JSON escape sequences (e.g. \alpha, \unit from math/chemistry content)
        # Keep valid JSON escapes: \", \\, \/, \b, \f, \n, \r, \t, and \uXXXX (4 hex digits only)
        result = re.sub(r'\\(?!["\\/bfnrt]|u[0-9a-fA-F]{4})', r'\\\\', result)
        print(result)
        parsed_result = json.loads(result)
        return parsed_result
    
    def is_valid_generation(self, parsed_result):
        if parsed_result['question'] != "" and len(parsed_result['options']) == num_options_per_question and parsed_result['explaination'] != "" and parsed_result['answer'] != "":
            print(Fore.GREEN+"Validation Check Passed!!!")
            return True
        print(Fore.RED+"Validation Check Failed!!!")
        return False
        
    def update_questions_data(self, parsed_result: List[Question], k_recent:int=10):
        for i in range(len(parsed_result)):
            if self.is_valid_generation(parsed_result[i]):
                if checker.is_not_duplicate(parsed_result[i]['question']):
                    self.already_generated_questions.append(parsed_result[i]['question'])
                    self.mcqs.append(parsed_result[i])
            else:
                print(Fore.RED+f"Invalid generation detected : {Fore.CYAN}{parsed_result[i]}")
        self.already_generated_questions = self.already_generated_questions[-k_recent:]

    def text_to_chunks(self, context:str) -> List[str]:
        splitter = RecursiveCharacterTextSplitter(chunk_size=max_chunk_size_for_splitting, length_function=len)
        splits = splitter.split_text(context)
        return splits
    
    def execute(self, context:str, total_Number_of_questions:int) -> str:
        """
        Takes context and total number of questions as args and executes batch generation to ensure the better use of model's context length.
        """
        if (total_Number_of_questions - len(self.mcqs) >= self.questions_per_batch) and (total_Number_of_questions != len(self.mcqs)):
            Number_of_questions_per_iter = self.questions_per_batch
        else:
            Number_of_questions_per_iter = total_Number_of_questions - len(self.mcqs)

        prompt = self.prompt_template.format(already_generated_questions=self.already_generated_questions, context=context, Number_of_questions=Number_of_questions_per_iter)
        try:
            result = self.client.invoke(prompt)
            time.sleep((60//max_rpm)+max_rpm_buffer)
        except Exception:
            print(f"Exception in execute(main.py): {traceback.print_exc()}")
        return result

    def __call__(self, chapters_text:Union[List[str], str], total_Number_of_questions:int, max_consecutive_chunks:int=5):         
            # contexts = []
            # for chapter in chapters_text:
            #     contexts.append(self.text_to_chunks(chapter))
            count = 0
            # print(len(contexts), contexts)
            while count < total_Number_of_questions:
                current_usage = get_usage(cursor=self.cursor)
                remaining_usage = max_requests_per_day - current_usage
                if remaining_usage > 0:
                    # chapter_choice = random.choice(range(len(chapters_text)))
                    # context_choice = contexts[chapter_choice]
                    context_choice = self.text_to_chunks(chapters_text)
                    # Handle case where text is too short to split into max_consecutive_chunks
                    if len(context_choice) <= max_consecutive_chunks:
                        context_start_index = 0
                        context = " ".join(context_choice)
                    else:
                        context_start_index = random.choice(range(len(context_choice)-max_consecutive_chunks))
                        context = " ".join(context_choice[context_start_index : context_start_index+max_consecutive_chunks])
                    context = clean_text(context)
                    # print("context: ",context)
                    result = self.execute(context, total_Number_of_questions)
                    set_usage(self.db, self.cursor, new_usage=current_usage+1)
                    parsed_result = self.parse_json(result)
                    self.update_questions_data(parsed_result)
                    count = len(self.mcqs)
                    print("Already generated questions: ", self.already_generated_questions)
                else:
                    self.already_generated_questions.clear()
                    # contexts.clear()
                    return self.mcqs
            # contexts.clear()
            self.already_generated_questions.clear()
            return self.mcqs
# -------------------------------------------------------------------------------