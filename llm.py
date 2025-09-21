import asyncio
from langchain_core.prompts import PromptTemplate
from langchain.chains import LLMChain
import json
# from fuzzywuzzy import process
import re
import ast
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.prompts import MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_core.messages import HumanMessage, AIMessage
from langchain_openai import ChatOpenAI
import chat_history
from session_manager import get_session_id
from groq import Groq
import time
import datetime
from langchain_groq import ChatGroq
import os

session_id = get_session_id()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
llm = ChatGroq(model="qwen-qwq-32b", temperature=0)
llm1 = ChatGroq(model="deepseek-r1-distill-llama-70b", temperature=0)
# llm2 = ChatOpenAI(
#     model="deepseek/deepseek-chat:free",  # Specify DeepSeek model
#     # model="deepseek/deepseek-chat-v3-0324:free",
#     openai_api_base="https://openrouter.ai/api/v1",  # OpenRouter API base
#     openai_api_key="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",  # Replace with your OpenRouter API key
#     temperature=0,
#     response_format={ "type": "json_object" }
# )
llm3 = Groq(api_key=GROQ_API_KEY)
llm4 = ChatGroq(model="llama3-70b-8192", temperature=0, response_format={"type": "json_object"})
llm5 = ChatGroq(model="deepseek-r1-distill-llama-70b", temperature=0.5,
    response_format={"type": "json_object"},
    )

def refine_result(answer, sql=False):
    """Refines the raw answer from LLM by cleaning and parsing"""
    try:
        if isinstance(answer, dict) and "text" in answer:
            raw_text = answer["text"]
        else:
            raw_text = str(answer)
            
        cleaned_text = re.sub(r'<think>.*?</think>\s*', '', raw_text, flags=re.DOTALL).strip()
    except Exception as e:
        print(f"Initial cleaning error: {e}")
        return answer

    if sql:
        try:
            match = re.search(r'\$(.*?)\$', cleaned_text, flags=re.DOTALL)
            if match:
                query = match.group(1)
                query = ' '.join(query.replace('\n', ' ').split())
                return query
            return ' '.join(cleaned_text.replace('\n', ' ').split())
        except Exception as e:
            print(f"SQL extraction error: {e}")
            return cleaned_text

    return cleaned_text.strip()

async def get_intent_classification(user_input, chat_history_db):
    """Async function to get intent classification"""
    base_template = """
        You are a multilingual AI assistant working for a food delivery platform called Foodstation.lk . The platform offers food from multiple restaurants, each with its own menu of dishes.# Foodstation.lk Assistant

        ## System Instructions
        You are an AI assistant for Foodstation.lk food delivery platform. You understand multiple languages including Sinhala(Singlish) and Tamil(Tanglish). Process user messages according to these exact steps.

        ## Step 1: Message Rewriting
        Transform the user's latest message into a standalone query:
        - If the latest message refers to previous messages (the chat history), rephrase it into a complete and self-contained sentence.
        - Preserve original meaning and intent

        ## Step 2: Classification
        Classify the rewritten message into ONE category only:

        **Greetings** - User saying hello, hi, good morning, etc.

        **Restaurant Info & Menu** - User asking about:
        - Restaurant menus
        - Restaurant details, hours, location
        - Restaurant status (open/closed)

        **Dish Price Inquiry & Availability** - User asking:
        - Price of specific dishes
        - If a dish is available
        - Where to find a specific dish

        **Order** - User wants to place food order (actual ordering intent only)

        **General Inquiry** - User asking about:
        - Food recommendations
        - Operating hours
        - Food categories
        - General suggestions

        **Unknown** - Message is unclear or unrelated to food delivery or unrelated to above any categories.

        ## Step 3: Fallback Response
        Generate response only for these cases:
        - Greetings: Respond politely
        - Unknown category: Ask for clarification
        - All other cases: Set to null

        ## Output Requirements
        Return ONLY this JSON format with no additional text:

        {{
            "corrected_input": "rewritten message or original",
            "category": "exact category name from list above",
            "fallback_response": "response text or null"
        }}

        ## Critical Rules
        1. Output must be valid JSON only
        2. No markdown formatting or explanations
        3. Use exact category names as written above  
        4. Set empty fields to null (not empty string)
    """

    base_prompt = ChatPromptTemplate.from_messages([
        ("system", base_template),
        MessagesPlaceholder("chat_history"),
        ("user", "{user_input}"),
    ])

    classification_chain = LLMChain(llm=llm5, prompt=base_prompt)
    slice_last_two = lambda lst: lst[-3:] if len(lst) > 1 else lst
    
    # Use ainvoke for async execution
    result = await classification_chain.ainvoke({
        "user_input": user_input, 
        "chat_history": slice_last_two(chat_history_db)
    })
    
    return refine_result(result)

async def get_entity_extraction(user_input, chat_history_db):
    """Async function to get entity extraction"""
    base_template = """
        You are a multilingual AI assistant working for a food delivery platform called Foodstation.lk . The platform offers food from multiple restaurants, each with its own menu of dishes.# Foodstation.lk Assistant

        ## System Instructions
        You are an AI assistant for Foodstation.lk food delivery platform. You understand multiple languages including Sinhala(Singlish) and Tamil(Tanglish). Process user messages according to these exact steps.

        ## Step 1: Message Rewriting
        Transform the user's latest message into a standalone query:
        - If the latest message refers to previous messages (the chat history), rephrase it into a complete and self-contained sentence.
        - Preserve original meaning and intent
 
        ## Step 2: Entity Extraction
        Extract and correct names using these lists:

        ### Restaurants (exact spelling):
        Kandiah, Ice Talk, Bluberry, Jollybeez, Mum’s Food, ourselection

        ### Dishes (exact spelling):
        ['Kotthu Rotti', 'Cheese Kotthu', 'Dolphin', 'Pittu Kotthu', 'Noodles', 'Pasta', 'String Hopper Kotthu', 'Bread Kotthu', 'Rice & Curry', 'Schezwan Rice', 'Mongolian Rice', 'Chopsuey Rice', 'Nasi Goreng', 'Biriyani', 'Fried Rice', 'Fry', 'Bbq', 'Tandoori', 'Grill', 'Devilled', 'Hot Butter', 'Curry', 'Kuruma', 'Parata', 'Mums Special Lime With Mint', 'Mums Special', 'Fresh Juice', 'Milk Shakes', 'Ice Cream', 'Nescafe', 'Milk Tea', 'Milo', 'Fruit Salad ', 'Wattalappam', 'Biscuit Pudding', 'Naan', 'French Fries', 'Soup', 'Salad', 'Mayyer Kelangu Fry', 'Hopper', 'Rolls', 'Samosa', 'Corn', 'Vadai', 'Shawarma', 'Bun', 'Kanji / Kenda', 'Chips', 'Mixture', 'Manyokka Fry']

        ### Extraction Rules:
        - Find misspelled restaurant/dish names and correct to exact match from lists
        - If no match found in lists, set to null
        - Extract quantity numbers (two → 2, three → 3, etc.)
        - if user asking in singlish or tanglish, you should correct it to the exact spelling in the list
        - Extract size as "Small", "Medium", "Large", or "null" if not specified
        - customer may mention sizes like "normal", "full", "half" etc. you should refine the size to the following:
        
        ### Mapping rules:

            If the customer mentions "normal" or "half" → treat as 1 person → Small
            If the customer mentions "full" or "2 person" → treat as 2 person → Medium
            If the customer mentions "large" or "4 person" → treat as 4 person → Large
            If no size indicator is mentioned, return "null".
        

        ## Output Requirements
        Return ONLY this JSON format with no additional text:

        {{
            "corrected_input": "rewritten message or original",
            "restaurant": "restaurant name from list or null",
            "dish": "dish name from list or null",
            "size": "small/medium/large or null",
            "variant": "variant name or null",
            "order_qty": "number or null",
        }}

        ## Critical Rules
        1. Output must be valid JSON only
        2. No markdown formatting or explanations
        3. Restaurant/dish names must match reference lists exactly
        4. Set empty fields to null (not empty string)
        5. Extract numbers for quantities (1, 2, 3, etc.)

        ## Example Processing
        User: "price of beef biriyani normal from Kandiah"

        Step 1: "Can I get 2 burgers from Kandiah?"
        Step 2: restaurant = "Kandiah", dish = "Biriyani", size = "Small", variant = "Beef" , order_qty = "2"

        Output:
        {{
            "corrected_input": "Can I get 2 burgers from Kandiah?",
            "restaurant": "Kandiah",
            "dish": "Biriyani",
            "size": "Small",
            "variant": "Beef",
            "order_qty": 2,
        }}
    """

    base_prompt = ChatPromptTemplate.from_messages([
        ("system", base_template),
        MessagesPlaceholder("chat_history"),
        ("user", "{user_input}"),
    ])

    classification_chain = LLMChain(llm=llm5, prompt=base_prompt)
    slice_last_two = lambda lst: lst[-3:] if len(lst) > 1 else lst
    
    # Use ainvoke for async execution
    result = await classification_chain.ainvoke({
        "user_input": user_input, 
        "chat_history": slice_last_two(chat_history_db)
    })
    
    return refine_result(result)


async def llm_intent_entity_async(user_input):
    """Main function to get intent and entities together"""
    print(f"Starting processing for: {user_input}")
    
    # In a real app, this would get actual chat history
    chat_history = []  
    
    try:
        # Run both tasks at the same time
        intent_task = get_intent_classification(user_input, chat_history)
        entity_task = get_entity_extraction(user_input, chat_history)
        
        # Wait for both to finish
        intent, entities = await asyncio.gather(intent_task, entity_task)
        
        print("Processing completed successfully")
        result = {
            'intent': intent,
            'entities': entities
        }

        intent = json.loads(result["intent"])
        entities = json.loads(result["entities"])

        llm_output = {
                    "corrected_input": intent.get("corrected_input", ""),
                    "category": intent.get("category", ""),
                    "fallback_response": intent.get("fallback_response", ""),
                    "restaurant": entities.get("restaurant", ""),
                    "dish": entities.get("dish", ""),
                    "size": entities.get("size", ""),
                    "variant": entities.get("variant", ""),
                    "order_qty": entities.get("order_qty", "")
                }
        
        llm_output = json.dumps(llm_output, ensure_ascii=False)

        print(f"LLM Output: {llm_output}")
        # llm_output = json.dumps(llm_output, ensure_ascii=False)
        return llm_output
        
    except Exception as e:
        print(f"Something went wrong: {e}")
        return {
            'intent': {"error": str(e)},
            'entities': {"error": str(e)}
        }

# Helper to run the async function from synchronous code
def llm_intent_entity(user_input):
    """Simple way to run async code from synchronous context"""
    return asyncio.run(llm_intent_entity_async(user_input))

# # Example usage
# if __name__ == "__main__":
#     result = llm_intent_entity("How do I use async in Python?")
#     print(result)