import ast
import json
import re
import time
import traceback
from langchain_google_genai import ChatGoogleGenerativeAI
from typing import List, Union
from langchain_text_splitters import RecursiveCharacterTextSplitter
from db_utils import get_usage, set_usage, _rate_limit_lock
from config import max_requests_per_day, max_rpm, max_rpm_buffer, max_chunk_size_for_splitting, num_options_per_question
from utils import Duplicate_checker, Question, clean_text
from colorama import Fore, init
import random

init(autoreset=True)

class TestAgent:
    def __init__(self, db, cursor, client:ChatGoogleGenerativeAI, system_prompt:str=None, json_format:str=None, questions_per_batch:int=5, generation_language="ENGLISH", format_examples:str=""):
        self.db = db
        self.cursor = cursor
        self.mcqs = []
        self.client = client
        self.questions_per_batch = questions_per_batch
        self.already_generated_questions = []
        self.checker = Duplicate_checker()
        # Pre-embed all static values directly into the prompt string.
        # Using .replace() instead of str.format() avoids KeyErrors from {curly braces}
        # in syllabus content, format_examples, or json_format (e.g. chemistry formulas).
        self.static_prompt = (system_prompt
            .replace("{json_format}", json_format)
            .replace("{generation_language}", generation_language)
            .replace("{format_examples}", format_examples)
        )

    def _fix_escapes(self, text: str) -> str:
        """Fix invalid JSON escape sequences from math/chemistry content (e.g. \alpha, \Delta)."""
        return re.sub(
            r'\\\\|\\(?!["\\/bfnrt]|u[0-9a-fA-F]{4})',
            lambda m: m.group(0) if m.group(0) == '\\\\' else '\\\\',
            text
        )

    def parse_json(self, result) -> List[Question]:
        text = result.content

        # Strip markdown code fences anywhere in the output
        text = re.sub(r'```json', '', text)
        text = re.sub(r'```', '', text)

        # Extract just the JSON array — discard any prose the LLM adds before/after
        start = text.find('[')
        end = text.rfind(']')
        if start == -1 or end == -1 or end <= start:
            raise ValueError(f"No JSON array found in LLM output: {text[:200]}")
        text = text[start:end + 1]

        # Fix invalid backslash escape sequences from math/chemistry/physics content
        text = self._fix_escapes(text)

        # Attempt 1: parse as-is
        try:
            return json.loads(text, strict=False)
        except json.JSONDecodeError:
            pass

        # Attempt 2: fix trailing commas before } or ] (common LLM mistake)
        text_fixed = re.sub(r',\s*([}\]])', r'\1', text)
        try:
            return json.loads(text_fixed, strict=False)
        except json.JSONDecodeError:
            pass

        # Attempt 3: extract individual question objects and parse each one separately
        # This salvages valid questions even when one malformed question breaks the whole batch
        questions = []
        for match in re.finditer(r'\{[^{}]*\}', text, re.DOTALL):
            try:
                q = json.loads(self._fix_escapes(match.group(0)), strict=False)
                questions.append(q)
            except json.JSONDecodeError:
                continue
        if questions:
            print(f"parse_json: recovered {len(questions)} questions via per-object fallback.")
            return questions

        # Attempt 4: Python literal eval — handles single-quoted output from the LLM
        try:
            result = ast.literal_eval(text)
            if isinstance(result, list):
                print(f"parse_json: recovered {len(result)} questions via ast.literal_eval fallback.")
                return result
        except Exception:
            pass

        # All attempts failed — log enough to diagnose and raise
        print(f"parse_json failed. Raw output (first 500 chars): {text[:500]}")
        raise ValueError("Failed to parse LLM JSON output after all attempts.")
    
    def is_valid_generation(self, parsed_result):
        if parsed_result.get('question', '') != "" and len(parsed_result.get('options', [])) == num_options_per_question and parsed_result.get('explaination', '') != "" and parsed_result.get('answer', '') != "":
            print(Fore.GREEN+"Validation Check Passed!!!")
            return True
        print(Fore.RED+"Validation Check Failed!!!")
        return False
        
    def update_questions_data(self, parsed_result: List[Question], k_recent:int=10):
        for i in range(len(parsed_result)):
            if self.is_valid_generation(parsed_result[i]):
                if self.checker.is_not_duplicate(parsed_result[i]['question']):
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

        prompt = (self.static_prompt
            .replace("{already_generated_questions}", str(self.already_generated_questions))
            .replace("{context}", context)
            .replace("{Number_of_questions}", str(Number_of_questions_per_iter))
        )
        retry_delays = [60, 120, 180]
        for attempt, retry_delay in enumerate(retry_delays + [None]):
            try:
                result = self.client.invoke(prompt)
                time.sleep((60 // max_rpm) + max_rpm_buffer if max_rpm > 0 else max_rpm_buffer)
                return result
            except Exception as e:
                err_str = str(e)
                is_quota_error = "429" in err_str or "RESOURCE_EXHAUSTED" in err_str
                is_server_error = "503" in err_str or "UNAVAILABLE" in err_str
                if (is_quota_error or is_server_error) and retry_delay is not None:
                    error_type = "Quota exceeded" if is_quota_error else "Server unavailable (503)"
                    print(f"{error_type} (attempt {attempt+1}/{len(retry_delays)}). Waiting {retry_delay}s before retry...")
                    time.sleep(retry_delay)
                else:
                    print(f"Exception in execute(main.py): {traceback.format_exc()}")
                    raise

    def __call__(self, chapters_text:Union[List[str], str], total_Number_of_questions:int, max_consecutive_chunks:int=5):         
            # contexts = []
            # for chapter in chapters_text:
            #     contexts.append(self.text_to_chunks(chapter))
            count = 0
            no_progress_streak = 0
            while count < total_Number_of_questions:
                with _rate_limit_lock:
                    current_usage = get_usage(cursor=self.cursor)
                    if max_requests_per_day - current_usage <= 0:
                        self.already_generated_questions.clear()
                        return self.mcqs
                    set_usage(self.db, self.cursor, new_usage=current_usage + 1)
                context_choice = self.text_to_chunks(chapters_text)
                if len(context_choice) <= max_consecutive_chunks:
                    context_start_index = 0
                    context = " ".join(context_choice)
                else:
                    context_start_index = random.choice(range(len(context_choice) - max_consecutive_chunks))
                    context = " ".join(context_choice[context_start_index : context_start_index + max_consecutive_chunks])
                context = clean_text(context)
                result = self.execute(context, total_Number_of_questions)
                parsed_result = self.parse_json(result)
                self.update_questions_data(parsed_result)
                new_count = len(self.mcqs)
                if new_count == count:
                    no_progress_streak += 1
                    if no_progress_streak >= 3:
                        print(f"No progress after 3 consecutive attempts — stopping generation with {count}/{total_Number_of_questions} questions.")
                        break
                else:
                    no_progress_streak = 0
                count = new_count
            self.already_generated_questions.clear()
            return self.mcqs
# -------------------------------------------------------------------------------