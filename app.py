from flask import Flask, request, jsonify, send_from_directory, redirect, make_response
from flask_caching import Cache
from requests import post
import psycopg2
from db_cred import *
import os
from dotenv import load_dotenv
from urllib.parse import urlencode
import requests

load_dotenv()

dbname = os.getenv('dbname')
user = os.getenv('user')
password = os.getenv('password')
host = os.getenv('host')

client_id = 'b18e232b89424dd7ae7b4d65cab1e070'
client_secret = '24959c0211e84122b941dbd55ae40eb6'
baseurl = 'https://oauth.yandex.ru/'

app = Flask(__name__, static_url_path='/static')
cache = Cache(app, config={'CACHE_TYPE': 'simple'})  # Используем простой кэш

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
    access_token = request.cookies.get('access_token')
    return send_from_directory('', 'home.html')
    

@app.route('/index.html')
def index():
    return send_from_directory('', 'index.html')

@app.route('/auth')
def auth():
    return send_from_directory('', 'auth.html')

@app.route('/auth_token')
def auth_token():
    if request.args.get('code', False):
        print(request.args)
        print(request.data)
        data = {
            'grant_type': 'authorization_code',
            'code': request.args.get('code'),
            'client_id': client_id,
            'client_secret': client_secret
        }
        data = urlencode(data)
        response = post(baseurl + "token", data=data)
        response_data = response.json()
        access_token = response_data.get('access_token')
        if access_token:
            # Создаем ответ с куки и перенаправляем на главную страницу
            resp = make_response(redirect('/'))
            resp.set_cookie('access_token', access_token)
            return resp
        else:
            return jsonify(response_data)
    else:
        return redirect(baseurl + "authorize?response_type=code&client_id={}".format(client_id))

@cache.cached(timeout=300, key_prefix='user_info')  # Кэшируем запрос на 5 минут
@app.route('/user_info')
def user_info():
    access_token = request.cookies.get('access_token')
    if access_token:
        response = requests.get('https://login.yandex.ru/info?format=json', headers={
            'Authorization': 'OAuth ' + access_token
        })
        return jsonify(response.json())
    return jsonify({'error': 'No access token'}), 401

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
