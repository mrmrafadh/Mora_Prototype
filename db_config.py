import mysql.connector
import psycopg2

# Function to establish MySQL connection
# def db_conn():
#     conn = mysql.connector.connect(
#         host="localhost",
#         user="root",
#         password="root",
#         database="foodstation"
#     )
#     return conn



def db_conn():
    conn = psycopg2.connect(
        host="moradb.c38maw0agkjw.ap-south-1.rds.amazonaws.com",
        port=5432,          # PostgreSQL default port
        user="postgres",
        password="rootroot",
        dbname="foodstation"
    )
    return conn