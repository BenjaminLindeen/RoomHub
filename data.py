""" database access
docs:
* http://initd.org/psycopg/docs/
* http://initd.org/psycopg/docs/pool.html
* http://initd.org/psycopg/docs/extras.html#dictionary-like-cursor
"""
# Source: Daniel Kluver

from contextlib import contextmanager
from dotenv import find_dotenv, load_dotenv
from flask import current_app
import logging
import os
import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from psycopg2.extras import DictCursor
from datetime import datetime
import logging

logging.basicConfig(level=logging.DEBUG)

ENV_FILE = find_dotenv()
if ENV_FILE:
    load_dotenv(ENV_FILE)

pool = None

DAY_NAMES = {
    0: "Monday",
    1: "Tuesday",
    2: "Wednesday",
    3: "Thursday",
    4: "Friday",
    5: "Saturday",
    6: "Sunday"
}

def setup():
    global pool
    DATABASE_URL = os.environ['DATABASE_URL']
    current_app.logger.info(f"creating db connection pool")
    pool = ThreadedConnectionPool(1, 100, dsn=DATABASE_URL, sslmode='require')


@contextmanager
def get_db_connection():
    try:
        connection = pool.getconn()
        yield connection
    finally:
        pool.putconn(connection)


@contextmanager
def get_db_cursor(commit=False):
    with get_db_connection() as connection:
        cursor = connection.cursor(cursor_factory=DictCursor)
        # cursor = connection.cursor()
        try:
            yield cursor
            if commit:
                connection.commit()
        finally:
            cursor.close()


def create_user_account(username, email):
    with get_db_cursor(True) as cur:
        current_app.logger.info("Adding user account %s", username)
        cur.execute("INSERT INTO users (username, email) values (%s, %s)",
                    (username, email))


def check_user_exists(email):
    with get_db_cursor() as cur:
        cur.execute("SELECT username FROM users WHERE email = %s", (email,))
        return cur.fetchone()


def create_house(house_name, creator_id):
    stripped_name = house_name.strip()
    formatted_name = ""
    i = 0
    while i < len(stripped_name):
        if stripped_name[i] == " ":
            formatted_name += " "
            while i+1 < len(stripped_name) and stripped_name[i+1] == " ":
                i += 1
        else:
            formatted_name += stripped_name[i]
        i += 1
        
    with get_db_cursor(True) as cur:
        cur.execute("INSERT INTO houses (house_name) VALUES (%s) RETURNING house_id", (formatted_name,))
        house_id = cur.fetchone()[0]
        cur.execute("INSERT INTO user_houses (user_id, house_id) VALUES (%s, %s)", (creator_id, house_id))



def check_house_exists(house_name):
    with get_db_cursor() as cur:
        cur.execute("SELECT * FROM houses WHERE house_name = %s", (house_name,))
        return cur.fetchone()


def get_houses():
    with get_db_cursor() as cur:
        cur.execute("SELECT house_name, house_id FROM houses")
        return cur.fetchall()

def get_houses_to_join(user_id):
    with get_db_cursor() as cur:
        cur.execute("SELECT DISTINCT house_name, house_id FROM houses LEFT JOIN user_houses USING (house_id) WHERE house_id NOT IN (SELECT house_id FROM user_houses WHERE user_id = %s)", (user_id, ))
        return cur.fetchall()
    
def get_user_id(user_email):
    with get_db_cursor() as cur:
        cur.execute("SELECT id FROM users WHERE email = %s", (user_email,))
        return cur.fetchone()

def get_user_houses(user_id):
    with get_db_cursor() as cur:
        cur.execute("SELECT house_name, house_id FROM user_houses LEFT JOIN houses USING (house_id) WHERE user_id = %s", (user_id,))
        return cur.fetchall()
    
def add_user_house(user_id, house_id):
    with get_db_cursor(True) as cur:
        cur.execute("INSERT INTO user_houses (user_id, house_id) VALUES (%s, %s)", (user_id, house_id))

def remove_user_house(user_id, house_id):
    with get_db_cursor(True) as cur:
        cur.execute("DELETE FROM user_houses WHERE user_id = %s AND house_id = %s", (user_id, house_id))

# get users' names given a house id
def get_house_members(house_id):
    with get_db_cursor() as cur:
        cur.execute(
            "SELECT u.username FROM users u JOIN user_houses uh ON u.id = uh.user_id WHERE uh.house_id = %s",
            (house_id,))
        members = cur.fetchall()
        return [member[0] for member in members] if members else ["No members"]

# for leave button in user_home
def leave_house(user_id, house_id):
    with get_db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM user_houses WHERE user_id = %s AND house_id = %s", (user_id, house_id))
        # Check if the user leaving is the last member of the house
        cur.execute("SELECT COUNT(*) FROM user_houses WHERE house_id = %s", (house_id,))
        count = cur.fetchone()[0]
        if count == 0:
            cur.execute("DELETE FROM houses WHERE house_id = %s", (house_id,))

def delete_tasks_by_house(house_id):
    with get_db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM tasks WHERE house_id = %s", (house_id,))
        # print(f"All tasks associated with house {house_id} deleted successfully.")

def is_last_member(house_id):
    with get_db_cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM user_houses WHERE house_id = %s", (house_id,))
        num_members = cur.fetchone()[0]
        return num_members == 1

def delete_house(house_id):
    with get_db_cursor(True) as cur:
        cur.execute("DELETE FROM houses WHERE house_id = %s", (house_id,))


# for assign_task page
def get_member_id_dict(house_id):
    with get_db_cursor() as cur:
        cur.execute(
            "SELECT u.id, u.username FROM users u JOIN user_houses uh ON u.id = uh.user_id WHERE uh.house_id = %s",
            (house_id,))
        members = cur.fetchall()
        return {member[1]: member[0] for member in members}
    
def get_house_name_by_id(house_id):
    with get_db_cursor() as cur:
        cur.execute("SELECT house_name FROM houses WHERE house_id = %s", (house_id,))
        result = cur.fetchone()
        if result:
            return result[0]  
        else:
            return None  # id not found

def get_user_by_id(user_id):
    with get_db_cursor() as cur:
        cur.execute("SELECT username FROM users WHERE id = %s", (user_id, ))
        result = cur.fetchone()
        return result
    
# for join button in user_home
def join_house(user_id, house_id):
    with get_db_cursor(True) as cur:
        cur.execute("INSERT INTO user_houses (user_id, house_id) VALUES (%s, %s)", (user_id, house_id))

def delete_house(house_id):
    with get_db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM houses WHERE house_id = %s", (house_id,))

# for assign-task page
def insert_task(task_name, user_id, house_id, task_due_date):
    with get_db_cursor(True) as cur:
        query = "INSERT INTO tasks (task_name, user_id, house_id, added_timestamp, due_date) VALUES (%s, %s, %s, %s, %s)"
        cur.execute(query, (task_name, user_id, house_id, datetime.now(), task_due_date))

# for delete task page
def delete_task_by_id(task_id):
    with get_db_cursor(True) as cur:
        query = "DELETE FROM tasks WHERE task_id = %s"
        cur.execute(query, (task_id,))        

# for leave button in user_home: deletes user's tasks when they leave the house
def delete_tasks_by_user_and_house(user_id, house_id):
    with get_db_cursor(True) as cur:
        query = "DELETE FROM tasks WHERE user_id = %s AND house_id = %s"
        cur.execute(query, (user_id, house_id))

def delete_restrictions_by_house(house_id):
    with get_db_cursor(True) as cur:
        query = "DELETE FROM restrictions WHERE house_id = %s"
        cur.execute(query, (house_id,))

def get_tasks_by_house_id(house_id):
    with get_db_cursor() as cur:
        # print(house_id)
        cur.execute("SELECT * FROM tasks WHERE house_id = %s", (house_id,))
        tasks = cur.fetchall()
        return tasks

def get_tasks_with_due_dates(house_id):
    formatted_tasks = []
    
    tasks = get_tasks_by_house_id(house_id)  

    for task in tasks:
        task_id = task["task_id"]
        task_name = task["task_name"]
        task_due_date = task["due_date"]
        formatted_due_date = task_due_date.strftime("%m/%d, %I:%M%p").replace(" 0", " ")
        formatted_task = (task_id, f"{task_name} due {formatted_due_date}")
        formatted_tasks.append(formatted_task)

    return formatted_tasks

# for edit task page
def update_task(task_id, task_name, user_id, task_due_date):
    with get_db_cursor(True) as cur:
        query = """
            UPDATE tasks 
            SET task_name = %s, user_id = %s, due_date = %s
            WHERE task_id = %s
        """
        cur.execute(query, (task_name, user_id, task_due_date, task_id))

def insert_restrictions(house_id, user_id, dietary_restrictions, schedule_restrictions):
    with get_db_cursor(True) as cur:
        query = "INSERT INTO restrictions (house_id, user_id, diet_restrictions, schedule_restrictions) VALUES (%s, %s, %s, %s)"
        cur.execute(query, (house_id, user_id, dietary_restrictions, schedule_restrictions))

def get_restrictions(house_id):
    with get_db_cursor() as cur:
        cur.execute("SELECT * FROM restrictions WHERE house_id = %s", (house_id,))
        return cur.fetchall()
