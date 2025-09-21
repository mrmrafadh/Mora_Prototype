import mysql.connector

# Function to establish MySQL connection
def db_conn():
    conn = mysql.connector.connect(
        host="localhost",
        user="root",
        password="root",
        database="foodstation"
    )
    return conn