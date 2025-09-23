# from db_config import db_conn

# def get_unique_entity():
#     # Establish connection
#     conn = db_conn()
#     cursor = conn.cursor()

#     # Execute query to get unique restaurant names
#     query = "SELECT DISTINCT name FROM Restaurants;"
#     cursor.execute(query)
#     unique_restaurant_names = [row[0] for row in cursor.fetchall()]

#     # Execute query to get unique dish names
#     query = "SELECT DISTINCT name FROM menu;" # Assuming 'name' is the dish name column in 'menu'
#     cursor.execute(query)
#     unique_dish_names = [row[0] for row in cursor.fetchall()]

#     # Close cursor and connection properly
#     cursor.close()
#     conn.close() # Closing here ensures resource release even if an error occurs later
#     return unique_restaurant_names, unique_dish_names


# def db_menu_request(restaurant_name):
#     # Establish connection
#     conn = db_conn()
#     cursor = conn.cursor()
#     # No f-string for para1, as it's a tuple for parameterized query
#     para1 = (f"{restaurant_name}",)
#     # Execute query to get menu items for the specified restaurant
#     query = """SELECT
#     r.name,
#     CONCAT(TIME_FORMAT(r.opening_time, '%h:%i'), '-', TIME_FORMAT(r.closing_time, '%h:%i')) AS timings,
#     CASE
#         WHEN CURRENT_TIME BETWEEN r.opening_time AND r.closing_time THEN 'Open'
#         ELSE 'Closed'
#     END AS status,
#     r.menu_link AS menuLink,
#     m.category
#     FROM restaurants r
#     JOIN menu m ON r.restaurant_id = m.restaurant_id
#     WHERE r.name LIKE %s
#     AND m.category IS NOT NULL AND m.category <> '';
# """
#     cursor.execute(query, para1)
#     menu_items = cursor.fetchall()

#     # Close cursor and connection properly
#     cursor.close()
#     conn.close()
#     return menu_items

# def db_price_inquiry(restaurant_name, dish_name, variant=None, size=None):
#     # Establish connection
#     conn = db_conn()
#     cursor = conn.cursor()

#     # Prepare parameters with wildcards for LIKE clauses
#     # The '%' wildcard needs to be part of the string that is passed as a parameter.
#     # The database driver will then correctly quote the entire string including the wildcards.
#     search_dish_name = f"%{dish_name}%"
#     search_restaurant_name = f"{restaurant_name}" # If you want exact match, no '%' here.
#                                                 # If partial match, add '%' like f"%{restaurant_name}%"

#     para1 = (search_dish_name,)
#     para2 = (search_dish_name, search_restaurant_name)

#     # Execute query to get menu items for the specified restaurant
#     query1 = """SELECT
#     m.`food_name` AS food_name,
#     m.variant AS variant,
#     m.`size` AS size,
#     m.`price`,
#     r.`name` AS restaurant_name,
#     CASE
#         WHEN m.`available_from` <= CURTIME() AND m.`available_until` >= CURTIME()
#         THEN 'Available Now'
#         ELSE 'Not Available Now'
#     END AS food_availability,
#     CASE
#         WHEN r.`opening_time` <= CURTIME() AND r.`closing_time` >= CURTIME()
#         THEN 'Open Now'
#         ELSE 'Closed Now'
#     END AS restaurant_status,
#     CONCAT(TIME_FORMAT(m.`available_from`, '%H:%i'), ' - ', TIME_FORMAT(m.`available_until`, '%H:%i')) AS available_time
#     FROM `food_items` m
#     JOIN `restaurants` r ON m.`restaurant_id` = r.`restaurant_id`
#     WHERE m.`food_name` LIKE %s
#     ORDER BY
#         r.`name` ASC,
#         m.`price` ASC;
#     """
#     query2 = """SELECT
#     m.`food_name` AS food_name,
#     m.variant AS variant,
#     m.`size` AS size,
#     m.`price`,
#     r.`name` AS restaurant_name,
#     CASE
#         WHEN m.`available_from` <= CURTIME() AND m.`available_until` >= CURTIME()
#         THEN 'Available Now'
#         ELSE 'Not Available Now'
#     END AS food_availability,
#     CASE
#         WHEN r.`opening_time` <= CURTIME() AND r.`closing_time` >= CURTIME()
#         THEN 'Open Now'
#         ELSE 'Closed Now'
#     END AS restaurant_status,
#     CONCAT(TIME_FORMAT(m.`available_from`, '%H:%i'), ' - ', TIME_FORMAT(m.`available_until`, '%H:%i')) AS available_time
#     FROM `food_items` m
#     JOIN `restaurants` r ON m.`restaurant_id` = r.`restaurant_id`
#     WHERE m.`food_name` LIKE %s
#         AND r.`name` LIKE %s
#     ORDER BY
#         r.`name` ASC,
#         m.`price` ASC;
#     """

#     try:
#         if not restaurant_name:
#             cursor.execute(query1, para1)
#         else:
#             # Here, the driver will correctly quote 'Mum's Food' or 'Kotthu Rotti'
#             # including any internal apostrophes, as long as they are part of the
#             # string passed in the tuple.
#             cursor.execute(query2, para2)

#         variants = set()
#         sizes = set()
#         price_list = cursor.fetchall()
#         keys = ['dish', 'variant', 'size', 'price', 'restaurant', 'availability', 'restaurant_status', 'available_time']
#         formatted_data = [dict(zip(keys, item)) for item in price_list]
#         for item in formatted_data:
#             variant_val = item.get('variant')
#             size_val = item.get('size')
#             if variant_val:
#                 variants.add(variant_val.lower().strip())
#             # if size_val:
#             #     sizes.add(size_val.lower().strip())

#         # Filter by variant and size if they exist
#         if variant and variant.lower().strip() in variants:
#             formatted_data = [item for item in formatted_data
#                             if item['variant'].lower().strip() == variant.lower().strip()]

#         # if size and size.lower().strip() in sizes:
#         #     formatted_data = [item for item in formatted_data
#         #                     if item['size'].lower().strip() == size.lower().strip()]
        
#         price_list = [tuple(item[key] for key in keys) for item in formatted_data]
#         print(price_list)
#         return price_list
#     finally:
#         # Ensure resources are always closed
        
#         cursor.close()
#         conn.close()

from db_config import db_conn
from psycopg2.extras import RealDictCursor

def get_unique_entity():
    """
    Fetch unique restaurant names and dish names from PostgreSQL.
    Returns:
        tuple: (unique_restaurant_names, unique_dish_names)
    """
    conn = db_conn()
    cursor = conn.cursor()

    try:
        # Unique restaurant names
        cursor.execute("SELECT DISTINCT name FROM restaurants;")
        unique_restaurant_names = [row[0] for row in cursor.fetchall()]

        # Unique dish names
        cursor.execute("SELECT DISTINCT name FROM menu;")  # adjust table/column names
        unique_dish_names = [row[0] for row in cursor.fetchall()]

        return unique_restaurant_names, unique_dish_names
    finally:
        cursor.close()
        conn.close()


def db_menu_request(restaurant_name):
    """
    Fetch menu items for a specific restaurant.
    Args:
        restaurant_name (str): Name of the restaurant
    Returns:
        list: Rows of menu items
    """
    conn = db_conn()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        query = """
        SELECT
            r.name,
            TO_CHAR(r.opening_time, 'HH24:MI') || '-' || TO_CHAR(r.closing_time, 'HH24:MI') AS timings,
            CASE
                WHEN CURRENT_TIME BETWEEN r.opening_time AND r.closing_time THEN 'Open'
                ELSE 'Closed'
            END AS status,
            r.menu_link AS menuLink,
            m.category
        FROM restaurants r
        JOIN menu m ON r.restaurant_id = m.restaurant_id
        WHERE r.name ILIKE %s
          AND m.category IS NOT NULL AND m.category <> '';
        """
        cursor.execute(query, (restaurant_name,))
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def db_price_inquiry(restaurant_name, dish_name, variant=None, size=None):
    """
    Fetch price and availability information for a dish at a specific restaurant.
    Args:
        restaurant_name (str or None): Restaurant name (None for all)
        dish_name (str): Dish name
        variant (str or None): Optional variant filter
        size (str or None): Optional size filter
    Returns:
        list of tuples: (dish, variant, size, price, restaurant, availability, restaurant_status, available_time)
    """
    conn = db_conn()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        search_dish_name = f"%{dish_name}%"
        search_restaurant_name = f"%{restaurant_name}%" if restaurant_name else None

        query_all = """
        SELECT
            m.food_name AS dish,
            m.variant,
            m.size,
            m.price,
            r.name AS restaurant,
            CASE
                WHEN m.available_from <= CURRENT_TIME AND m.available_until >= CURRENT_TIME
                THEN 'Available Now'
                ELSE 'Not Available Now'
            END AS availability,
            CASE
                WHEN r.opening_time <= CURRENT_TIME AND r.closing_time >= CURRENT_TIME
                THEN 'Open Now'
                ELSE 'Closed Now'
            END AS restaurant_status,
            TO_CHAR(m.available_from, 'HH24:MI') || ' - ' || TO_CHAR(m.available_until, 'HH24:MI') AS available_time
        FROM food_items m
        JOIN restaurants r ON m.restaurant_id = r.restaurant_id
        WHERE m.food_name ILIKE %s
        ORDER BY r.name ASC, m.price ASC;
        """

        query_specific = """
        SELECT
            m.food_name AS dish,
            m.variant,
            m.size,
            m.price,
            r.name AS restaurant,
            CASE
                WHEN m.available_from <= CURRENT_TIME AND m.available_until >= CURRENT_TIME
                THEN 'Available Now'
                ELSE 'Not Available Now'
            END AS availability,
            CASE
                WHEN r.opening_time <= CURRENT_TIME AND r.closing_time >= CURRENT_TIME
                THEN 'Open Now'
                ELSE 'Closed Now'
            END AS restaurant_status,
            TO_CHAR(m.available_from, 'HH24:MI') || ' - ' || TO_CHAR(m.available_until, 'HH24:MI') AS available_time
        FROM food_items m
        JOIN restaurants r ON m.restaurant_id = r.restaurant_id
        WHERE m.food_name ILIKE %s
          AND r.name ILIKE %s
        ORDER BY r.name ASC, m.price ASC;
        """

        if restaurant_name:
            cursor.execute(query_specific, (search_dish_name, search_restaurant_name))
        else:
            cursor.execute(query_all, (search_dish_name,))

        results = cursor.fetchall()

        # Filter by variant and size if provided
        if variant:
            results = [row for row in results if row['variant'] and row['variant'].lower().strip() == variant.lower().strip()]
        # if size:
        #     results = [row for row in results if row['size'] and row['size'].lower().strip() == size.lower().strip()]

        # Convert to list of tuples for consistency with your previous code
        keys = ['dish', 'variant', 'size', 'price', 'restaurant', 'availability', 'restaurant_status', 'available_time']
        return [tuple(row[key] for key in keys) for row in results]

    finally:
        cursor.close()
        conn.close()
