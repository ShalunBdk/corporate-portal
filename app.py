from flask import Flask, jsonify, send_from_directory
import psycopg2
from db_cred import *
import os
from dotenv import load_dotenv

load_dotenv()
dbname = os.getenv('dbname')
user = os.getenv('user')
password = os.getenv('password')
host = os.getenv('host')
app = Flask(__name__)

def get_employee_hierarchy():
    try:
        conn = psycopg2.connect(
            f"dbname= {dbname} user={user} password={password} host={host} port=5432"
        )
        cur = conn.cursor()
        cur.execute("""
        WITH RECURSIVE employee_hierarchy AS (
            SELECT
                id,
                firstname,
                lastname,
                email,
                manager,
                title,
                CONCAT(firstname, ' ', lastname) AS fullname,
                1 AS level
            FROM employees
            WHERE manager IS NULL OR manager = 'None'

            UNION ALL

            SELECT
                e.id,
                e.firstname,
                e.lastname,
                e.email,
                e.manager,
                e.title,
                CONCAT(e.firstname, ' ', e.lastname) AS fullname,
                eh.level + 1
            FROM employees e
            INNER JOIN employee_hierarchy eh ON e.manager = eh.fullname
        )
        SELECT * FROM employee_hierarchy;
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()

        def build_tree(data, manager='None'):
            tree = {"name": manager, "relationship": "Работает", "email": "", "title": "", "children": []}
            for row in data:
                if row[4] == manager:
                    child = {
                        "name": f"{row[2]}\n{row[1]}",  # Фамилия\nИмя
                        "relationship": "Работает",
                        "children": build_tree(data, row[6]),
                        "class": "TION",
                        "textClass": "emphasis",
                        "extra":
                        {
                            "email": row[3],
                            "title": row[5],
                        }
                    }
                    tree["children"].append(child)
            return tree["children"] if tree["children"] else []

        hierarchy = build_tree(rows)
        return hierarchy
    except Exception as e:
        print("Failed to execute query:", e)
        return []

@app.route('/api/employees_hierarchy')
def employees_hierarchy():
    hierarchy = get_employee_hierarchy()
    return jsonify(hierarchy)

@app.route('/')
def home():
    return send_from_directory('', 'home.html')

@app.route('/index.html')
def index():
    return send_from_directory('', 'index.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
