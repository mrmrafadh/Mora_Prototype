from flask import Flask, render_template, request, jsonify, session
import json
import pandas as pd
from datetime import datetime
import uuid
from functools import wraps

# Import your existing modules
import llm
from user_intent_handler import UserIntentHandler
import chat_history
from session_manager import get_session_id
import order_request  # Your order processing module

from collections import defaultdict
import asyncio

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # Change this to a secure secret key
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False  # Enable in production with HTTPS


# Constants
ERROR_MESSAGES = {
    'no_input': 'Please provide a message',
    'llm_failure': 'Failed to process your request',
    'invalid_response': 'Received invalid response format',
    'server_error': 'An unexpected error occurred'
}

def json_response(f):
    """Decorator to standardize JSON responses"""
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            result = f(*args, **kwargs)
            if isinstance(result, tuple):
                data, status_code = result
            else:
                data, status_code = result, 200
            
            response = jsonify(data)
            response.status_code = status_code
            return response
        except Exception as e:
            app.logger.error(f"Error in {f.__name__}: {str(e)}")
            return jsonify({'error': ERROR_MESSAGES['server_error']}), 500
    return wrapper

def initialize_session():
    """Initialize or retrieve session ID"""
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    return session['session_id']

def get_formatted_chat_history(session_id):
    """Retrieve and format chat history from database"""
    db_chat_history = chat_history.get_chat_history(session_id)
    messages = []
    
    if db_chat_history:
        for record in db_chat_history:
            if record and isinstance(record, dict):
                if user_query := record.get("user_query"):
                    messages.append({"role": "user", "content": user_query})
                if gpt_response := record.get("gpt_response"):
                    messages.append({"role": "assistant", "content": gpt_response})
    
    return messages

def group_by_restaurant(items):
    """Group menu items by restaurant and variant, nesting sizes under each variant"""
    if not isinstance(items, (list, pd.DataFrame)):
        return {}

    # Convert DataFrame to list of dicts if needed
    items_list = items.to_dict('records') if isinstance(items, pd.DataFrame) else items

    restaurants = {}

    for item in items_list:
        if not isinstance(item, dict):
            continue

        restaurant_name = item.get('Restaurant', 'Unknown Restaurant')
        status = item.get('Restaurant Status', 'Status Unknown')
        dish = item.get('Dish', 'Unknown Dish')
        variant = item.get('Variant', 'Unknown Variant')
        size = item.get('Size', 'Unknown Size')

        # Initialize restaurant entry if not present
        if restaurant_name not in restaurants:
            restaurants[restaurant_name] = {
                'status': status,
                'dish': dish,
                'variants': defaultdict(dict)
            }

        # Prepare size-level data
        size_info = {
            'Price': item.get('Price', 'N/A'),
            'Availability': item.get('Availability', 'Availability unknown'),
            'Available Time': item.get('Available Time', '')
        }

        # Assign size info under the appropriate variant
        restaurants[restaurant_name]['variants'][variant][size] = size_info

    # Convert defaultdicts to regular dicts for JSON compatibility
    for restaurant in restaurants.values():
        restaurant['variants'] = dict(restaurant['variants'])

    return restaurants

def process_llm_response(user_input):
    """Process user input with LLM and handle response"""
    try:
        llm_response = llm.llm_intent_entity(user_input)
        return json.loads(llm_response) if llm_response else {}
    except json.JSONDecodeError as e:
        app.logger.error(f"LLM JSON decode error: {str(e)}")
        return {'error': ERROR_MESSAGES['invalid_response']}
    except Exception as e:
        app.logger.error(f"LLM processing error: {str(e)}")
        return {'error': ERROR_MESSAGES['llm_failure']}

def format_bot_response(bot_reply, output_type):
    """Format the bot response for the frontend"""
    response_data = {'messages': []}
    
    if not bot_reply:
        response_data['messages'].append({
            "role": "assistant",
            "content": ERROR_MESSAGES['invalid_response'],
            "type": "text"
        })
        return response_data
    
    # Handle error message with results case
    if isinstance(bot_reply, dict) and "error_message" in bot_reply and "results" in bot_reply:
        response_data['messages'].append({
            "role": "assistant",
            "content": bot_reply["error_message"],
            "type": "text"
        })
        bot_reply = bot_reply["results"]
    
    # Process the actual data
    if isinstance(bot_reply, (list, pd.DataFrame)):
        if output_type == "price data":
            restaurants = group_by_restaurant(bot_reply)
            if restaurants:
                response_data['messages'].append({
                    "role": "assistant",
                    "content": restaurants,
                    "type": "restaurant_data"
                })
        elif output_type == "restaurant data":
            records = bot_reply.to_dict('records') if isinstance(bot_reply, pd.DataFrame) else bot_reply
            if records:
                response_data['messages'].append({
                    "role": "assistant",
                    "content": records,
                    "type": "restaurant_data1"
                })
        else:
            records = bot_reply.to_dict('records') if isinstance(bot_reply, pd.DataFrame) else bot_reply
            if records:
                response_data['messages'].append({
                    "role": "assistant",
                    "content": records,
                    "type": "table_data"
                })
    else:
        response_data['messages'].append({
            "role": "assistant",
            "content": str(bot_reply),
            "type": "text"
        })
    # print(response_data)
    return response_data


def format_order_selection_response(item_data, selection_type):
    """Format order selection response for frontend"""
    if selection_type == "dish_option":
        options = item_data.get("available_dishes_options", [])
        message = f"Please choose an option for {item_data.get('dish', 'your dish')}:"
    elif selection_type == "variant":
        options = item_data.get("available_variants", [])
        message = f"Please choose a variant for {item_data.get('dish', 'your dish')}:"
    elif selection_type == "size":
        options = item_data.get("available_sizes", [])
        message = f"Please choose a size for {item_data.get('dish', 'your dish')}:"
    
    # Add error message if present
    error_msg = item_data.get("error")
    if error_msg:
        message = f"{error_msg}\n\n{message}"
    
    # Format options as numbered list
    options_text = "\n".join([f"{i+1}. {option.capitalize()}" for i, option in enumerate(options)])
    full_message = f"{message}\n\n{options_text}\n\nPlease enter the number of your choice or type the option name."
    
    return {
        'messages': [{
            "role": "assistant",
            "content": full_message,
            "type": "text"
        }]
    }


def format_order_complete_response(order_data):

    orders = order_data.get('orders', [])
    unavailable_dishes = order_data.get('unavailable_dishes', [])
    """Format completed order response for frontend"""
    if not orders:
        return {
            'messages': [{
                "role": "assistant",
                "content": "No valid orders could be processed.",
                "type": "text"
            }]
        }
    
    # Format order summary
    order_summary = "✅ Your order has been processed:\n\n"
    total_items = 0
    
    for order in orders:
        dish_id = order.get('food_id')
        dish = order.get('dish', 'Unknown')
        variant = order.get('variant', 'N/A')
        size = order.get('size', 'N/A')
        quantity = int(order.get('quantity', 1))
        price = order.get('price', 'N/A')
        qty_price = float(price) * float(quantity)
        
        order_line = f" • {dish}"
        if variant != 'N/A':
            order_line += f" ({variant})"
        if size != 'N/A':
            order_line += f" - {size}"
        order_line += f" {float(price)} X {float(quantity)} = {qty_price}"
        
        order_summary += order_line + "\n"
        total_items += quantity
    
    if unavailable_dishes:
        order_summary += f"\nTotal items: {total_items}\n\n Requested dishes not available in our menu:\n{unavailable_dishes}"
    else:
        order_summary += f"\nTotal items: {total_items}\n"
    
    return {
        'messages': [{
            "role": "assistant",
            "content": order_summary,
            "type": "text"
        }]
    }

def is_order_intent(llm_data):
    """Check if the user intent is related to ordering"""
    # Check the 'category' field first (most reliable)
    category = llm_data.get('category', '').lower()
    if category == 'order':
        return True
    
    return False

@app.route('/')
def index():
    """Main chat interface route"""
    session_id = initialize_session()
    messages = get_formatted_chat_history(session_id)
    return render_template('chat.html', messages=messages)

@app.route('/send_message', methods=['POST'])
@json_response
def send_message():
    """Handle user messages and return bot responses"""
    user_input = request.json.get('message', '').strip()
    if not user_input:
        return {'error': ERROR_MESSAGES['no_input']}, 400
    
    session_id = session.get('session_id')
    response_data = None
    
    # Check if we're currently awaiting a selection
    if order_request.is_awaiting_selection():
        try:
            # Handle user's selection response
            result = order_request.handle_user_selection_response(user_input)
            
            if result.get('status') == 'error':
                response_data = {
                    'messages': [{
                        "role": "assistant",
                        "content": result.get('message', 'Invalid selection'),
                        "type": "text"
                    }]
                }
            elif result.get('status') == 'needs_dish_selection':
                response_data = format_order_selection_response(result['item'], 'dish_option')
            elif result.get('status') == 'needs_variant':
                response_data = format_order_selection_response(result['item'], 'variant')
            elif result.get('status') == 'needs_size':
                response_data = format_order_selection_response(result['item'], 'size')
            elif result.get('status') == 'complete':
                response_data = format_order_complete_response(result)
            
        except Exception as e:
            app.logger.error(f"Order selection processing error: {str(e)}")
            # Clear session and fall back to normal processing
            order_request.clear_selection_session()
            response_data = {
                'messages': [{
                    "role": "assistant",
                    "content": "Sorry, there was an error processing your selection. Please try again.",
                    "type": "text"
                }]
            }
    
    # Normal message processing (not awaiting selection)
    if response_data is None:
        try:
            llm_data = process_llm_response(user_input)
            if 'error' in llm_data:
                return {'error': llm_data['error']}, 500

            if is_order_intent(llm_data):
                try:
                    result = order_request.preprocess_order_request(llm_data)
                    print(f"Preprocessed result: {result}")
                    # Correct status mapping
                    if result.get('status') == 'needs_dish_selection':
                        response_data = format_order_selection_response(result['item'], 'dish_option')
                    elif result.get('status') == 'needs_variant':
                        response_data = format_order_selection_response(result['item'], 'variant')
                    elif result.get('status') == 'needs_size':
                        response_data = format_order_selection_response(result['item'], 'size')
                    elif result.get('status') == 'complete':
                        response_data = format_order_complete_response(result)
                    else:
                        handler = UserIntentHandler()
                        bot_reply, output_type = handler.route_user_intent(llm_data)
                        response_data = format_bot_response(bot_reply, output_type)
                
                except Exception as e:
                    app.logger.error(f"Order processing error: {str(e)}")
                    handler = UserIntentHandler()
                    bot_reply, output_type = handler.route_user_intent(llm_data)
                    response_data = format_bot_response(bot_reply, output_type)
            else:
                # 👇 Handle non-order messages normally
                handler = UserIntentHandler()
                bot_reply, output_type = handler.route_user_intent(llm_data)
                response_data = format_bot_response(bot_reply, output_type)
        
        except Exception as e:
            app.logger.error(f"Message processing error: {str(e)}")
            return {'error': ERROR_MESSAGES['server_error']}, 500
    
    return response_data

@app.route('/cancel_order', methods=['POST'])
@json_response
def cancel_order():
    """Cancel current order process and clear session"""
    if order_request.is_awaiting_selection():
        order_request.clear_selection_session()
        return {
            'messages': [{
                "role": "assistant",
                "content": "Order process has been cancelled. How can I help you?",
                "type": "text"
            }]
        }
    else:
        return {
            'messages': [{
                "role": "assistant",
                "content": "No active order process to cancel.",
                "type": "text"
            }]
        }

@app.route('/order_status', methods=['GET'])
@json_response
def order_status():
    """Get current order process status"""
    if order_request.is_awaiting_selection():
        context = order_request.get_selection_context()
        if context:
            selection_type = context.get('selection_type', 'unknown')
            current_item = context.get('current_item', {})
            dish = current_item.get('dish', 'unknown item')
            
            return {
                'awaiting_selection': True,
                'selection_type': selection_type,
                'dish': dish,
                'message': f"Waiting for {selection_type} selection for {dish}"
            }
    
    return {
        'awaiting_selection': False,
        'message': "No active order process"
    }

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)