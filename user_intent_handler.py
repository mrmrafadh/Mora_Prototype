from langchain_core.messages import HumanMessage, AIMessage
import get_unique_entity
import pandas as pd
import json
import chat_history
from session_manager import get_session_id
import general_inquiry
import order_request

session_id = get_session_id()  # Use the same session ID everywhere

class UserIntentHandler:
    def __init__(self):
        self.chat_history = []
        self.MAX_RECURSION_DEPTH = 1  # Class-level constant for recursion limit

    def _log_response(self, session_id, input_text, response, response_type):
        chat_history.insert_application_logs(
            session_id,
            input_text,
            response,
            "qwen",
            response_type
        )
        
    def _make_error_response(self, message, results=None):
        """Standardized error response format"""
        return {
            "error_message": message,
            "results": results
        }, "error"

    def _process_dataframe_price(self, data, columns, session_id, corrected_input):
        """Helper to process successful dataframe responses"""
        try:
            df = pd.DataFrame(data, columns=columns)
            json_data = df.to_json(orient="records")
            result = json.loads(json_data)
            self._log_response(session_id, corrected_input, json_data, "json")
            # print(result)
            return result, "price data"
        except Exception as e:
            error_message = f"Error processing data: {str(e)}"
            self._log_response(session_id, corrected_input, error_message, "str")
            return self._make_error_response(error_message)
        


    def _process_dataframe_restaurant(self, data, columns, session_id, corrected_input):
        """Processes restaurant data and formats it into structured JSON."""
        try:
            df = pd.DataFrame(data, columns=columns)

            df_categories = df.groupby("name")["categories"].agg(lambda x: list(set(x))).reset_index()

            # Merge back with the main DataFrame to ensure correct indexing
            df = df.drop(columns=["categories"]).drop_duplicates()
            df = df.merge(df_categories, on="name", how="left")

            # Drop duplicate rows, keeping only unique restaurant entries
            df = df.drop_duplicates(subset=["name", "timings", "status", "menuLink"])

            # Convert DataFrame to JSON
            json_data = df.to_json(orient="records")  # Converts directly to structured JSON
            result = json.loads(json_data)  # Parses JSON string into Python dictionary

            # Log and return response
            self._log_response(session_id, corrected_input, json_data, "json")
            # print(result)  # Debugging output
            return result, "restaurant data"

        except Exception as e:
            error_message = f"Error processing data: {str(e)}"
            self._log_response(session_id, corrected_input, error_message, "str")
            return self._make_error_response(error_message)


    def greeting_handler(self, json_output):
        greeting_response = json_output.get("fallback_response", "Hello! How can I assist you today?")
        self._log_response(session_id, json_output["corrected_input"], greeting_response, "str")
        return greeting_response, "text"

    def handle_menu_request(self, json_output):
        # Validate restaurant exists
        if not json_output.get("restaurant"):
            error_message = "Sorry, I couldn't find the restaurant. Please provide the restaurant name."
            self._log_response(session_id, json_output["corrected_input"], error_message, "str")
            return self._make_error_response(error_message)

        # Get menu items
        menu_items = get_unique_entity.db_menu_request(json_output["restaurant"])
        print(menu_items)
        # Handle empty results
        if not menu_items:
            error_message = json_output.get("fallback_response", f"Sorry, no menu items found for {json_output['restaurant']}.")
            self._log_response(session_id, json_output["corrected_input"], error_message, "str")
            return self._make_error_response(error_message)

        # Process successful results
        columns = ['name', 'timings', 'status', 'menuLink', 'categories']
        return self._process_dataframe_restaurant(menu_items, columns, session_id, json_output["corrected_input"])

    def handle_price_inquiry(self, json_output, recursion_depth=0):
        # Validate dish exists
        if not json_output.get("dish"):
            error_message = (json_output.get("fallback_response") or 
                           "I couldn't identify the dish. Please verify the dish name and try again.")
            self._log_response(session_id, json_output["corrected_input"], error_message, "str")
            return self._make_error_response(error_message)

        # Get inquiry details
        restaurant = json_output.get("restaurant")
        dish = json_output["dish"]
        variant = json_output.get("variant")
        size = json_output.get("size")
        price_data = get_unique_entity.db_price_inquiry(restaurant, dish, variant, size)

        # Handle empty results
        if not price_data:
            if recursion_depth < self.MAX_RECURSION_DEPTH and restaurant:
                error_message = f"Unfortunately {restaurant} doesn't serve {dish}. Here is {dish} information from other places."
                self._log_response(session_id, json_output["corrected_input"], error_message, "str")
                
                # Prepare for recursive call
                json_output['corrected_input'] = f"provide me the prices of {dish}"
                json_output['restaurant'] = None
                
                # Make recursive call and handle response
                recursive_result = self.handle_price_inquiry(json_output, recursion_depth + 1)
                
                if isinstance(recursive_result, tuple):
                    recursive_data, _ = recursive_result
                    if isinstance(recursive_data, dict) and "error_message" in recursive_data:
                        return self._make_error_response(
                            f"{error_message} {recursive_data['error_message']}",
                            recursive_data.get('results')
                        )
                    return {
                        "error_message": error_message,
                        "results": recursive_data
                    }, "price data"
                return self._make_error_response(error_message, recursive_result)
            
            error_message = f"Unfortunately no restaurants serve {dish}."
            self._log_response(session_id, json_output["corrected_input"], error_message, "str")
            return self._make_error_response(error_message)

        # Process successful results
        columns = ['Dish', 'Variant','Size', 'Price', 'Restaurant', 'Availability', 'Restaurant Status', 'Available Time']
        return self._process_dataframe_price(price_data, columns, session_id, json_output["corrected_input"])


    def handle_general_inquiry(self, json_output):
        try:
            return general_inquiry.generate_sql_query(json_output),""
        except Exception as e:
            error_message = f"Error processing general inquiry: {str(e)}"
            self._log_response(session_id, json_output["corrected_input"], error_message, "str")
            return self._make_error_response(error_message)


    def order_request(self, json_output):
        try:
            clean_order = order_request.preprocess_order_request(json_output)
            self._log_response(session_id, json_output["corrected_input"], clean_order, "json")
            return clean_order,""
        except Exception as e:
            error_message = f"Error processing order inquiry: {str(e)}"
            self._log_response(session_id, json_output["corrected_input"], error_message, "str")
            return self._make_error_response(error_message)


    def route_user_intent(self, json_output):
        try:
            if not isinstance(json_output, dict):
                return self._make_error_response("Invalid request format")
            
            category = json_output.get("category", "").lower()
            print(f"Routing category: {category}")  # Debugging output
            
            if category == "greetings":
                return self.greeting_handler(json_output)
            elif category == "restaurant info & menu":
                return self.handle_menu_request(json_output)
            elif category == "dish price inquiry & availability":
                return self.handle_price_inquiry(json_output)
            elif category == "general inquiry":
                return self.handle_general_inquiry(json_output)
            elif category == "order":
                return self.order_request(json_output)
            else:
                return self._make_error_response("Sorry, I couldn't understand the request.")
                
        except Exception as e:
            error_message = f"Error routing intent: {str(e)}"
            self._log_response(session_id, json_output.get("corrected_input", ""), error_message, "str")
            return self._make_error_response(error_message)