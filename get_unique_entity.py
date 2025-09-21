from db_config import db_conn

def get_unique_entity():
    # Establish connection
    conn = db_conn()
    cursor = conn.cursor()

    # Execute query to get unique restaurant names
    query = "SELECT DISTINCT name FROM Restaurants;"
    cursor.execute(query)
    unique_restaurant_names = [row[0] for row in cursor.fetchall()]

    # Execute query to get unique dish names
    query = "SELECT DISTINCT name FROM menu;" # Assuming 'name' is the dish name column in 'menu'
    cursor.execute(query)
    unique_dish_names = [row[0] for row in cursor.fetchall()]

    # Close cursor and connection properly
    cursor.close()
    conn.close() # Closing here ensures resource release even if an error occurs later
    return unique_restaurant_names, unique_dish_names


def db_menu_request(restaurant_name):
    # Establish connection
    conn = db_conn()
    cursor = conn.cursor()
    # No f-string for para1, as it's a tuple for parameterized query
    para1 = (f"{restaurant_name}",)
    # Execute query to get menu items for the specified restaurant
    query = """SELECT
    r.name,
    CONCAT(TIME_FORMAT(r.opening_time, '%h:%i'), '-', TIME_FORMAT(r.closing_time, '%h:%i')) AS timings,
    CASE
        WHEN CURRENT_TIME BETWEEN r.opening_time AND r.closing_time THEN 'Open'
        ELSE 'Closed'
    END AS status,
    r.menu_link AS menuLink,
    m.category
    FROM restaurants r
    JOIN menu m ON r.restaurant_id = m.restaurant_id
    WHERE r.name LIKE %s
    AND m.category IS NOT NULL AND m.category <> '';
"""
    cursor.execute(query, para1)
    menu_items = cursor.fetchall()

    # Close cursor and connection properly
    cursor.close()
    conn.close()
    return menu_items

def db_price_inquiry(restaurant_name, dish_name, variant=None, size=None):
    # Establish connection
    conn = db_conn()
    cursor = conn.cursor()

    # Prepare parameters with wildcards for LIKE clauses
    # The '%' wildcard needs to be part of the string that is passed as a parameter.
    # The database driver will then correctly quote the entire string including the wildcards.
    search_dish_name = f"%{dish_name}%"
    search_restaurant_name = f"{restaurant_name}" # If you want exact match, no '%' here.
                                                # If partial match, add '%' like f"%{restaurant_name}%"

    para1 = (search_dish_name,)
    para2 = (search_dish_name, search_restaurant_name)

    # Execute query to get menu items for the specified restaurant
    query1 = """SELECT
    m.`food_name` AS food_name,
    m.variant AS variant,
    m.`size` AS size,
    m.`price`,
    r.`name` AS restaurant_name,
    CASE
        WHEN m.`available_from` <= CURTIME() AND m.`available_until` >= CURTIME()
        THEN 'Available Now'
        ELSE 'Not Available Now'
    END AS food_availability,
    CASE
        WHEN r.`opening_time` <= CURTIME() AND r.`closing_time` >= CURTIME()
        THEN 'Open Now'
        ELSE 'Closed Now'
    END AS restaurant_status,
    CONCAT(TIME_FORMAT(m.`available_from`, '%H:%i'), ' - ', TIME_FORMAT(m.`available_until`, '%H:%i')) AS available_time
    FROM `food_items` m
    JOIN `restaurants` r ON m.`restaurant_id` = r.`restaurant_id`
    WHERE m.`food_name` LIKE %s
    ORDER BY
        r.`name` ASC,
        m.`price` ASC;
    """
    query2 = """SELECT
    m.`food_name` AS food_name,
    m.variant AS variant,
    m.`size` AS size,
    m.`price`,
    r.`name` AS restaurant_name,
    CASE
        WHEN m.`available_from` <= CURTIME() AND m.`available_until` >= CURTIME()
        THEN 'Available Now'
        ELSE 'Not Available Now'
    END AS food_availability,
    CASE
        WHEN r.`opening_time` <= CURTIME() AND r.`closing_time` >= CURTIME()
        THEN 'Open Now'
        ELSE 'Closed Now'
    END AS restaurant_status,
    CONCAT(TIME_FORMAT(m.`available_from`, '%H:%i'), ' - ', TIME_FORMAT(m.`available_until`, '%H:%i')) AS available_time
    FROM `food_items` m
    JOIN `restaurants` r ON m.`restaurant_id` = r.`restaurant_id`
    WHERE m.`food_name` LIKE %s
        AND r.`name` LIKE %s
    ORDER BY
        r.`name` ASC,
        m.`price` ASC;
    """

    try:
        if not restaurant_name:
            cursor.execute(query1, para1)
        else:
            # Here, the driver will correctly quote 'Mum's Food' or 'Kotthu Rotti'
            # including any internal apostrophes, as long as they are part of the
            # string passed in the tuple.
            cursor.execute(query2, para2)

        variants = set()
        sizes = set()
        price_list = cursor.fetchall()
        keys = ['dish', 'variant', 'size', 'price', 'restaurant', 'availability', 'restaurant_status', 'available_time']
        formatted_data = [dict(zip(keys, item)) for item in price_list]
        for item in formatted_data:
            variant_val = item.get('variant')
            size_val = item.get('size')
            if variant_val:
                variants.add(variant_val.lower().strip())
            # if size_val:
            #     sizes.add(size_val.lower().strip())

        # Filter by variant and size if they exist
        if variant and variant.lower().strip() in variants:
            formatted_data = [item for item in formatted_data
                            if item['variant'].lower().strip() == variant.lower().strip()]

        # if size and size.lower().strip() in sizes:
        #     formatted_data = [item for item in formatted_data
        #                     if item['size'].lower().strip() == size.lower().strip()]
        
        price_list = [tuple(item[key] for key in keys) for item in formatted_data]
        return price_list
    finally:
        # Ensure resources are always closed
        cursor.close()
        conn.close()