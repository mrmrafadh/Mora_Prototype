import requests
from sqlalchemy import create_engine, MetaData, Table,text
import llm
import chat_history
import pandas as pd
from session_manager import get_session_id
import json


session_id = get_session_id()  # Use the same session ID everywhere
def llm_order(question):
    """
    This function takes a user query and returns a structured JSON response
    containing the restaurant name and entities extracted from the query.
    It uses a language model to refine the query into a specific format.
    """
    
    # Example data for entity extraction
    example = [
        {
            "input": "Can I get a medium beef kothu in bluripples?",
            "restaurant_name": "bluripples",
            "entities": {
                "item1": {
                    "dish": "kottu",
                    "variant": "beef",
                    "size": "medium",
                    "qty": "null"
                }
            }
        },
        {
            "input": "Order six beef rolls and six chicken rolls.",
            "restaurant_name": "default",
            "entities": {
                "item1": {
                    "dish": "roll",
                    "variant": "beef",
                    "size": "null",
                    "qty": 6
                },
                "item2": {
                    "dish": "roll",
                    "variant": "chicken",
                    "size": "null",
                    "qty": 6
                }
            }
        },
        {
            "input": "I need one rice and curry from ice talk, can you?",
            "restaurant_name": "ice talk",
            "entities": {
                "item1": {
                    "dish": "rice and curry",
                    "variant": "null",
                    "size": "null",
                    "qty": 1
                }
            }
        },
        {
            "input": "Order normal-sized fried rice with chicken.",
            "restaurant_name": "default",
            "entities": {
                "item1": {
                    "dish": "fried rice",
                    "variant": "chicken",
                    "size": "normal",
                    "qty": "1"
                }
            }
        },
        {
            "input": "Order chicken full kotthu 2.",
            "restaurant_name": "default",
            "entities": {
                "item1": {
                    "dish": "kotthu",
                    "variant": "chicken",
                    "size": "full",
                    "qty": 2
                }
            }
        },
        {
            "input": "order two medium and 1 large chicken kotthu rotti",
            "restaurant_name": "default",
            "entities": {
                "item1": {
                    "dish": "kotthu rotti",
                    "variant": "beef",
                    "size": "medium",
                    "qty": 2
                },
                "item2": {
                    "dish": "kotthu rotti",
                    "variant": "chicken",
                    "size": "large",
                    "qty": 1
                }
            }
        },
        {
            "input": "order cheese large kotthu chicken from moms food",
            "restaurant_name": "moms food",
            "entities": {
                "item1": {
                    "dish": "cheese kotthu",
                    "variant": "chicken",
                    "size": "large",
                    "qty": 1
                }
            }
        }
    ]

    refine_result_template = """
    You are a multilangual chat assistant for a food delivery platform specializing in taking orders from customers.
    Especially, understand Tanglish, Singlish and English.
    Your task is to:
    - extract relevant entities from user input.
    - if the user query does not contain a restaurant name, use "ourselection" as the default restaurant.
    - generate fallback messages in below situations:
        - If no food item is found in the query:
            "Sorry, I couldn’t find any food items in your request. Could you please mention what you'd like to order?"
        - If more than one restaurant name is present:
            "I can assist with placing an order from one restaurant at a time. Please select a single restaurant so we can continue."

    ### Extraction Rules and steps:
        step 1: Extract restaurant name
        - Find restaurant/dish names using the provided lists.
        - if entities misspelled correct them to the closest match in the list.
        - if the dish not found and the dish mentioned in Tanglish or Singlish, translate it to the exact spelling in the list.
        - If no match found in lists, try to match most relevant entity or set to null
        - Extract quantity numbers (two → 2, three → 3, etc.)
        - if user asking in singlish or tanglish, you should translate it if dish not found in list to the exact spelling in the list
        - Extract size as "small", "medium", "large", or "null" if not specified
        - customer may mention sizes like "normal", "full", "half" etc. you should refine the size to the following:
            - normal → 1 person → small
            - half → 1 person → small
            - full → 2 person → medium
            - large → 4 person → large
        
    Extract and correct restaurant using these lists:
    Kandiah, Ice Talk, Bluberry, Jollybeez, Mum’s Food, ourselection

    Extract and correct food using these lists:
    ['Kotthu', 'Kotthu Rotti', 'Cheese Kotthu', 'Dolphin', 'Pittu Kotthu', 'Noodles', 'Pasta', 'String Hopper Kotthu', 'Bread Kotthu', 'Rice & Curry', 'Schezwan Rice', 'Mongolian Rice', 'Chopsuey Rice', 'Nasi Goreng', 'Biriyani', 'Fried Rice', 'Fry', 'Bbq', 'Tandoori', 'Grill', 'Devilled', 'Hot Butter', 'Curry', 'Kuruma', 'Parata', 'Mums Special Lime With Mint', 'Mums Special', 'Fresh Juice', 'Milk Shakes', 'Ice Cream', 'Nescafe', 'Milk Tea', 'Milo', 'Fruit Salad ', 'Wattalappam', 'Biscuit Pudding', 'Naan', 'French Fries', 'Soup', 'Salad', 'Mayyer Kelangu Fry', 'Hopper', 'Rolls', 'Samosa', 'Corn', 'Vadai', 'Shawarma', 'Bun', 'Kanji / Kenda', 'Chips', 'Mixture', 'Manyokka Fry']

    For reference, here’s an example to illustrate the extraction pattern:
    Example—
    {example}

    The example is **only** for capturing the entity extraction pattern. **Do not** correct or modify any entities.

    If the user query contains multiple items, extract each item separately with its details.

    Return the refined query **only** in JSON format, structured as follows:

    {{
        "user_query": "{question}",
        "restaurant_name": "restaurant name or ourselection",
        "entities": {{
            "item_number": {{
                "dish": "food name or null",
                "variant": "variant or null",
                "size": "size or null",
                "qty": "qty or 1"
                }}
            }}
        "fallback_message": "No food item found in the query." if no food item is present, or "I can place order for one restaurant at a time" if more than one restaurant name is present.
    }}

    **Return only the JSON output. Do not include explanations, reasoning, or extra text.**

    User query:
    {question}
    """


    # Assuming OpenAI's GPT model for execution
    chat_completion =  llm.llm3.chat.completions.create(
        model="deepseek-r1-distill-llama-70b",  # Ensure this is the correct model name
        messages=[
            {"role": "user", "content": refine_result_template.format(example=example, question=question)},
        ],
        temperature=0.5,
        max_completion_tokens=4096,
        top_p=0.95,
        stream=False,
        response_format={"type": "json_object"},
        stop=None,
    )

    order_data = chat_completion.choices[0].message.content.strip()
    order_data = json.loads(order_data)
    print(f"Order data: {order_data}")
    return order_data