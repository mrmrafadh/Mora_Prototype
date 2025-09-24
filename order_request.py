import json
import sys
import llm_order
from flask import session
import chat_history
from session_manager import get_session_id
from db_config import db_conn   # Make sure db_conn() now returns a psycopg2 connection
from psycopg2 import sql, Error
from psycopg2.extras import RealDictCursor

session_id = get_session_id()

def dish_info(dish, restaurant_name, dish_selected=None):
    """
    Fetches dish details (name, variant, size, price) from the PostgreSQL database.

    Args:
        dish: Name of the dish (e.g., "Pizza")
        restaurant_name: Name of the restaurant (e.g., "Pizza Hut")
        dish_selected: Optional specific dish name to narrow search

    Returns:
        result_dict: {id: {dish, variant, size, price}}
        variants: set of variants
        sizes: set of sizes
        dish_options: set of possible dish names
        or
        error dict if not found
    """
    cnx = None
    cursor = None
    try:
        # Connect to PostgreSQL
        cnx = db_conn()
        cursor = cnx.cursor(cursor_factory=RealDictCursor)

        # Base query
        base_query = """
            SELECT fi.id, fi.food_name, fi.variant, fi.size, fi.price
            FROM food_items fi
            JOIN restaurants r ON fi.restaurant_id = r.restaurant_id
            WHERE r.name = %s
        """

        # Search for exact dish name first
        search_query = base_query + " AND fi.food_name = %s"
        cursor.execute(search_query, (restaurant_name, dish))
        results = cursor.fetchall()

        # If no exact match, broaden the search
        if not results:
            if dish_selected:
                cursor.execute(base_query + " AND fi.food_name = %s", (restaurant_name, dish))
                results = cursor.fetchall()
            else:
                cursor.execute(base_query + " AND fi.food_name ILIKE %s", (restaurant_name, f'%{dish}%'))
                results = cursor.fetchall()

        if not results:
            return {"status": "error",
                    "message": f"Dish '{dish}' not found in {restaurant_name}"}, set(), set(), set()

        result_dict = {}
        variants = set()
        sizes = set()
        dish_options = set()

        for row in results:
            variant = row["variant"].lower().strip() if row["variant"] else None
            size = row["size"].lower().strip() if row["size"] else None
            dish_options.add(row["food_name"].lower().strip())

            result_dict[row["id"]] = {
                "dish": row["food_name"],
                "variant": variant,
                "size": size,
                "price": row["price"]
            }
            if variant:
                variants.add(variant)
            if size:
                sizes.add(size)

        return result_dict, variants, sizes, dish_options

    except Error as err:
        print(f"Database Error: {err}")
        return {"status": "error", "message": f"Database error: {err}"}, set(), set(), set()

    finally:
        if cursor:
            cursor.close()
        if cnx:
            cnx.close()


def normalize(value):
    """
    Cleans up a value by converting it to lowercase and removing spaces.
    If the value is empty or meaningless (e.g., "null"), returns None.
    
    Args:
        value: The value to clean (e.g., "Spicy ", "null")
    
    Returns:
        Cleaned value (e.g., "spicy") or None
    """
    if value is None or value.lower() in ["null", "n/a", "none", ""]:
        return None
    return value.lower().strip()

def get_next_incomplete_item(items_info, user_selections):
    """
    Finds the next item that needs user input (dish, variant, or size).
    
    Args:
        items_info: List of items with their details (dish, variants, sizes, etc.)
        user_selections: Dictionary of user choices so far
    
    Returns:
        item: The item needing input (or None if all complete)
        selection_type: What needs to be selected ("dish_option", "variant", "size", or None)
    """
    for item in items_info:
        item_key = item["item_key"]  # Unique identifier for the item
        user_choice = user_selections.get(item_key, {})  # Get user's choices for this item

        # Step 1: Check if we need to select a dish
        dish_options = item["dish_options"]
        current_dish = user_choice.get("dish", item["dish"])
        if len(dish_options) > 1 and "dish" not in user_choice:
            return item, "dish_option"  # Multiple dish options, user needs to choose

        # Step 2: If dish is selected, update dish info
        if "dish" in user_choice:
            db_dish_info, available_variants, available_sizes, _ = dish_info(
                current_dish, item["restaurant_name"], dish_selected=True
            )
            item["db_dish_info"] = db_dish_info
            item["available_variants"] = available_variants
            item["available_sizes"] = available_sizes

        # Step 3: Check if we need to select a variant
        variant = user_choice.get("variant", item["variant"])
        available_variants = item["available_variants"]
        if available_variants and (not variant or variant not in available_variants):
            return item, "variant"  # Variants available, user needs to choose

        # Step 4: Check if we need to select a size
        size = user_choice.get("size", item["size"])
        available_sizes = item["available_sizes"]
        if available_sizes and (not size or size not in available_sizes):
            return item, "size"  # Sizes available, user needs to choose

    return None, None  # All selections complete

def handle_order(order_data, user_selections=None):
    """
    Processes the order, asking for user input (dish, variant, size) one item at a time.
    
    Args:
        order_data: The order data from the LLM (contains restaurant and items)
        user_selections: User's choices so far (e.g., {item_key: {"dish": "pizza", "variant": "spicy"}})
    
    Returns:
        Dictionary with status and details:
        - "complete": Order is fully processed with final orders and unavailable dishes
        - "needs_dish_selection": User needs to choose a dish
        - "needs_variant": User needs to choose a variant
        - "needs_size": User needs to choose a size
        - "error": If a dish is not found
    """
    restaurant = order_data["restaurant_name"]
    final_orders = []
    unavailable_dishes = []  # Track dishes not found in the database
    
    if user_selections is None:
        user_selections = {}  # Initialize empty selections if none provided

    # Step 1: Collect info for all items
    items_info = []
    for item_key, item_info in order_data["entities"].items():
        dish = normalize(item_info["dish"])  # Clean dish name
        variant = normalize(item_info["variant"])  # Clean variant
        size = normalize(item_info["size"])  # Clean size
        qty = item_info.get("qty", 1)  # Default quantity is 1

        if not dish:
            continue  # Skip if no dish specified

        # Get dish details from database
        db_dish_info, available_variants, available_sizes, dish_options = dish_info(dish, restaurant)

        # Check if dish_info returned an error
        if isinstance(db_dish_info, dict) and db_dish_info.get("status") == "error":
            unavailable_dishes.append({"dish": dish, "message": db_dish_info["message"]})
            continue

        items_info.append({
            "item_key": item_key,
            "original_dish": item_info["dish"],
            "dish": dish,
            "variant": variant,
            "size": size,
            "quantity": qty,
            "restaurant_name": restaurant,
            "db_dish_info": db_dish_info,
            "available_variants": available_variants,
            "available_sizes": available_sizes,
            "dish_options": dish_options
        })

    # If no valid items were found, return error with unavailable dishes
    if not items_info and unavailable_dishes:
        return {
            "status": "error",
            "message": "No valid dishes found",
            "unavailable_dishes": unavailable_dishes
        }

    # Step 2: Find the next item needing selection
    next_item, selection_type = get_next_incomplete_item(items_info, user_selections)
    
    if next_item and selection_type:
        item_key = next_item["item_key"]
        user_choice = user_selections.get(item_key, {})
        
        # Count how many items still need selections
        remaining_items = sum(1 for item, _ in 
                            [get_next_incomplete_item([item], user_selections) 
                             for item in items_info] if item is not None)

        # Handle dish selection
        if selection_type == "dish_option":
            session['awaiting_selection'] = True
            session['selection_type'] = 'dish_option'
            session['current_item'] = {
                "item_key": item_key,
                "dish": next_item["original_dish"],
                "available_dishes_options": list(next_item["dish_options"])
            }
            session['order_data'] = order_data
            session['user_selections'] = user_selections
            session['pending_items_count'] = remaining_items
            
            return {
                "status": "needs_dish_selection",
                "item": {
                    "item_key": item_key,
                    "dish": next_item["original_dish"],
                    "available_dishes_options": list(next_item["dish_options"]),
                    "message": f"I found multiple options for {next_item['original_dish']}. Please select one:",
                    "error": None,
                    "remaining_items": remaining_items,
                    "current_step": f"Dish selection for {next_item['original_dish']}"
                }
            }

        # Handle variant selection
        elif selection_type == "variant":
            current_dish = user_choice.get("dish", next_item["dish"])
            variant_error = None
            current_variant = user_choice.get("variant", next_item["variant"])
            
            if current_variant and current_variant not in next_item["available_variants"]:
                variant_error = f"The variant '{current_variant}' is not available for {current_dish}"
            
            session['awaiting_selection'] = True
            session['selection_type'] = 'variant'
            session['current_item'] = {
                "item_key": item_key,
                "dish": current_dish,
                "current_variant": current_variant,
                "available_variants": list(next_item["available_variants"])
            }
            session['order_data'] = order_data
            session['user_selections'] = user_selections
            session['pending_items_count'] = remaining_items
            
            return {
                "status": "needs_variant",
                "item": {
                    "item_key": item_key,
                    "dish": current_dish,
                    "current_variant": current_variant,
                    "available_variants": list(next_item["available_variants"]),
                    "message": f"Please choose a variant for {current_dish}",
                    "error": variant_error,
                    "remaining_items": remaining_items,
                    "current_step": f"Variant selection for {current_dish}"
                }
            }

        # Handle size selection
        elif selection_type == "size":
            current_dish = user_choice.get("dish", next_item["dish"])
            size_error = None
            current_size = user_choice.get("size", next_item["size"])
            
            if current_size and current_size not in next_item["available_sizes"]:
                size_error = f"The size '{current_size}' is not available for {current_dish}"
            
            session['awaiting_selection'] = True
            session['selection_type'] = 'size'
            session['current_item'] = {
                "item_key": item_key,
                "dish": current_dish,
                "current_size": current_size,
                "available_sizes": list(next_item["available_sizes"])
            }
            session['order_data'] = order_data
            session['user_selections'] = user_selections
            session['pending_items_count'] = remaining_items
            
            return {
                "status": "needs_size",
                "item": {
                    "item_key": item_key,
                    "dish": current_dish,
                    "current_size": current_size,
                    "available_sizes": list(next_item["available_sizes"]),
                    "message": f"Please choose a size for {current_dish}",
                    "error": size_error,
                    "remaining_items": remaining_items,
                    "current_step": f"Size selection for {current_dish}"
                }
            }

    # Step 3: If all selections are complete, finalize the order
    for item in items_info:
        item_key = item["item_key"]
        user_choice = user_selections.get(item_key, {})
        
        # Get final choices
        final_dish = user_choice.get("dish", item["dish"])
        final_variant = user_choice.get("variant", item["variant"])
        final_size = user_choice.get("size", item["size"])
        
        # Update dish info if dish was changed
        if "dish" in user_choice:
            db_dish_info, _, _, _ = dish_info(final_dish, restaurant)
            # Check if dish_info returned an error
            if isinstance(db_dish_info, dict) and db_dish_info.get("status") == "error":
                unavailable_dishes.append({"dish": final_dish, "message": db_dish_info["message"]})
                continue
        else:
            db_dish_info = item["db_dish_info"]
        
        # Find the matching food item in the database
        selected_food_id = None
        for food_id, db_item in db_dish_info.items():
            item_variant = db_item["variant"]
            item_size = db_item["size"]
            if (final_variant == item_variant or not item_variant) and (final_size == item_size or not item_size):
                selected_food_id = food_id
                break

        if selected_food_id:
            final_orders.append({
                "food_id": selected_food_id,
                "dish": final_dish,
                "variant": final_variant or 'N/A',
                "size": final_size or 'N/A',
                "price": db_dish_info[selected_food_id]["price"],
                "quantity": item["quantity"]
            })

    return {
        "status": "complete",
        "orders": final_orders,
        "unavailable_dishes": unavailable_dishes  # Include unavailable dishes in the response
    }

def clear_selection_session():
    """
    Clears all session data related to the order selection process.
    """
    session.pop('awaiting_selection', None)
    session.pop('selection_type', None)
    session.pop('current_item', None)
    session.pop('order_data', None)
    session.pop('user_selections', None)
    session.pop('pending_items_count', None)

def is_awaiting_selection():
    """
    Checks if the system is waiting for a user to make a selection.
    
    Returns:
        True if waiting for a selection, False otherwise
    """
    return session.get('awaiting_selection', False)

def get_selection_context():
    """
    Gets the current selection context from the session.
    
    Returns:
        Dictionary with selection details or None if not waiting for a selection
    """
    if not is_awaiting_selection():
        return None
    
    return {
        'selection_type': session.get('selection_type'),
        'current_item': session.get('current_item'),
        'order_data': session.get('order_data'),
        'user_selections': session.get('user_selections', {}),
        'pending_items_count': session.get('pending_items_count', 0)
    }

def preprocess_order_request(json_output, user_selections=None):
    """
    Main function to start processing an order.
    
    Args:
        json_output: The user's input in JSON format
        user_selections: User's previous selections (if any)
    
    Returns:
        Result from handle_order or an error message
    """
    try:
        user_input = json_output["corrected_input"]
        llm_order_json = llm_order.llm_order(user_input)  # Convert user input to order data
        
        if not llm_order_json or "entities" not in llm_order_json:
            # Log error if order data is invalid
            chat_history.insert_application_logs(session_id, json_output["corrected_input"], 
                                                "Invalid order data received", "qwen", "str")
            return {"status": "error", "message": "Invalid order data received"}
        
        # Process the order
        order_result = handle_order(llm_order_json, user_selections)
        chat_history.insert_application_logs(session_id, json_output["corrected_input"], 
                                            str(order_result), "qwen", "str")
        return order_result
    except Exception as e:
        print(f"Error in preprocess_order_request: {e}")
        return {"status": "error", "message": "Sorry, there was an error processing your selection. Please try again."}

def process_user_selection(original_order_data, item_key, selection_type, selected_value, user_selections=None):
    """
    Processes a user's selection (e.g., choosing a dish, variant, or size).
    
    Args:
        original_order_data: The original order data
        item_key: The item being selected for
        selection_type: Type of selection ("dish", "variant", "size")
        selected_value: The user's choice
        user_selections: Previous user selections
    
    Returns:
        Result from handle_order or an error message
    """
    try:
        if user_selections is None:
            user_selections = {}
        
        # Update user selections
        if item_key not in user_selections:
            user_selections[item_key] = {}
        
        user_selections[item_key][selection_type] = selected_value
        
        # Continue processing the order
        return handle_order(original_order_data, user_selections)
    except Exception as e:
        print(f"Error in process_user_selection: {e}")
        return {"status": "error", "message": "Sorry, there was an error processing your selection. Please try again."}

def handle_user_selection_response(user_choice):
    """
    Handles the user's response when they select an option.
    
    Args:
        user_choice: The user's selected option (e.g., "1" or "spicy")
    
    Returns:
        Result from process_user_selection or an error message
    """
    try:
        if not is_awaiting_selection():
            return {"status": "error", "message": "No selection process is currently active"}
        
        context = get_selection_context()
        if not context:
            return {"status": "error", "message": "Selection context not found"}
            
        selection_type = context['selection_type']
        current_item = context['current_item']
        order_data = context['order_data']
        user_selections = context['user_selections']
        
        # Get available options based on selection type
        if selection_type == 'dish_option':
            available_options = current_item['available_dishes_options']
        elif selection_type == 'variant':
            available_options = current_item['available_variants']
        elif selection_type == 'size':
            available_options = current_item['available_sizes']
        
        if not available_options:
            return {"status": "error", "message": "No options available for selection"}
        
        # Handle numeric choice (e.g., user enters "1" for first option)
        if user_choice.isdigit():
            choice_index = int(user_choice) - 1
            if 0 <= choice_index < len(available_options):
                selected_value = available_options[choice_index]
            else:
                return {
                    "status": "error", 
                    "message": f"Invalid choice. Please select a number between 1 and {len(available_options)}"
                }
        # Handle text choice (e.g., user enters "spicy")
        elif user_choice.lower() in [option.lower() for option in available_options]:
            selected_value = user_choice.lower()
        else:
            return {
                "status": "error", 
                "message": f"Invalid choice. Available options: {', '.join(available_options)}"
            }
        
        # Map selection type to field name
        field_mapping = {
            'dish_option': 'dish',
            'variant': 'variant',
            'size': 'size'
        }
        
        field_name = field_mapping.get(selection_type, selection_type)
        
        # Process the user's selection
        result = process_user_selection(
            order_data, 
            current_item['item_key'], 
            field_name,
            selected_value, 
            user_selections
        )

        # Log the user's selection
        chat_history.insert_application_logs(
            session_id,
            user_choice,
            f"User selected {selected_value} for {current_item['item_key']} ({selection_type})",
            "qwen",
            "str"
        )
        
        # Clear session if order is complete or there's an error
        if result.get('status') in ['complete', 'error']:
            clear_selection_session()
        print(result)
        return result
        
    except Exception as e:
        print(f"Error in handle_user_selection_response: {e}")
        clear_selection_session()
        return {"status": "error", "message": "Sorry, there was an error processing your selection. Please try again."}