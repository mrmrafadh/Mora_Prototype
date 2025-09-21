import requests
from sqlalchemy import create_engine, MetaData, Table,text
import llm
import chat_history
import pandas as pd
from session_manager import get_session_id
import json


session_id = get_session_id() 

db_url = "mysql+mysqlconnector://root:root@localhost:3306/foodstation"

few_shot_examples="""
                {
    question : what are the food avilable now
    answer : Sorry, There is no food Avilable this time.
    }
"""

# SQL prompt template
sql_prompt_template = """
You are an expert SQL query writer. 
Your task is to generate a SQL query based on the provided question and the database schema.
Also i provided the entities extracted from the user input for your reference.
Instructions:
- If the inquiry is about food item, generate a SQL query to fetch the food name, size, price, restaurant name, and availability status.
    columns name should be formatted as follows:
    - `Dish` for food name
    - `Size` for food size
    - `Price` for food price
    - `Restaurant` for restaurant name
    - `Availablity` food available now or not
    - `Available Time` from what time to what time
- If the inquiry is about restaurant, generate a SQL query to fetch the restaurant name and open/close status for that restaurant.
    columns name should be formatted as follows:
    - `Restaurant` for restaurant name
    - `Status` Staus of restaurant Open Now/Closed
    - `Open/Close Time` for restaurant open/close time
always use like operator only for food name.
Here is the entities extracted from the user input:
{entities}

Here is the database schema:
{schema}

Here is the question:
{question}

Respond with a valid SQL query, no explanations or additional text.
"""

few_shot_template="""
                
"""


def _log_response(self, session_id, input_text, response, response_type):
        chat_history.insert_application_logs(
            session_id,
            input_text,
            response,
            "qwen",
            response_type
    )


def fetch_schema_from_db(db_url):
    """
    Fetch the database schema from the given database URL.
    """
    engine = create_engine(db_url)
    metadata = MetaData()
    metadata.reflect(bind=engine)

    schema = ""
    for table in metadata.tables.values():
        schema += f"Table: {table.name}\nColumns: {', '.join([col.name + ' (' + str(col.type) + ')' for col in table.columns])}\n\n"

    return schema.strip()

def execute_sql(engine, query, json_output, retry_count=0):
    """
    Execute the SQL query and return results in a pandas DataFrame.
    If there's an error, it will retry once by regenerating the SQL query.
    """
    max_retries = 1  # Maximum number of retries
    
    with engine.connect() as connection:
        try:
            result = connection.execute(text(query))
            df = pd.DataFrame(result.fetchall(), columns=result.keys())
            
            if df.empty:
                error_message = "No results found for the given query."
                _log_response(session_id, json_output.get("corrected_input"), error_message, "qwen", "str")
                return error_message
            
            json_data = df.to_json(orient="records")
            parsed_json = json.loads(json_data)
            print(parsed_json)
            _log_response(session_id, json_output.get("corrected_input"), json_data, "qwen", "json")
            return parsed_json
            
        except Exception as e:
            if retry_count < max_retries:
                # Log the error and retry
                print(f"SQL execution error (attempt {retry_count + 1}): {str(e)}")
                print(f"Problematic query: {query}")
                
                # Regenerate the SQL query and try again
                new_query = generate_sql_query(json_output, is_retry=True)
                return execute_sql(engine, new_query, json_output, retry_count + 1)
            else:
                error_message = "There is some problem from my side to run your query. Please try again or rephrase your question."
                _log_response(session_id, json_output.get("corrected_input"), error_message, "qwen", "str")
                return error_message

def generate_sql_query(json_output, is_retry=False):
    engine = create_engine(db_url)

    # Fetch the database schema
    schema = fetch_schema_from_db(db_url)

    # Add context if this is a retry
    additional_context = ""
    if is_retry:
        additional_context = "\n\nThe previous generated query had syntax errors. Please carefully review the database schema and generate a correct SQL query."

    # Generate SQL query using Groq LLM
    chat_completion = llm.llm3.chat.completions.create(
        messages=[
            {
                "role": "user", 
                "content": sql_prompt_template.format(
                    entities=json_output, 
                    schema=schema, 
                    question=json_output.get("corrected_input"),
                    additional_context=additional_context
                )
            },
        ],
        model="qwen-qwq-32b",
        temperature=0.3 if not is_retry else 0.1,  # Lower temperature for retry to be more conservative
    )

    # Extract query from the LLM response
    sql_query = llm.refine_result(chat_completion.choices[0].message.content.strip(), True)
    return sql_query if is_retry else execute_sql(engine, sql_query, json_output)

