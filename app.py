from flask import Flask, request, jsonify, render_template,send_from_directory, redirect, make_response
from flask_caching import Cache
from requests import post
import psycopg2
from psycopg2.extras import RealDictCursor
from db_cred import *
import os
from dotenv import load_dotenv
from urllib.parse import urlencode
import requests
from werkzeug.utils import secure_filename

load_dotenv()

# Настройки для загрузки файлов
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

dbname = os.getenv('dbname')
user = os.getenv('user')
password = os.getenv('password')
host = os.getenv('host')

client_id = 'b18e232b89424dd7ae7b4d65cab1e070'
client_secret = '24959c0211e84122b941dbd55ae40eb6'
baseurl = 'https://oauth.yandex.ru/'

app = Flask(__name__, static_url_path='/static')
cache = Cache(app, config={'CACHE_TYPE': 'simple'})  # Используем простой кэш

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_db_connection():
    conn = psycopg2.connect(
        f"dbname= {dbname} user={user} password={password} host={host} port=5432"
    )
    return conn

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
                company,
                department,
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
                e.company,
                e.department,
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
                        "children": build_tree(data, row[8]),
                        "class": "TION",
                        "textClass": "emphasis",
                        "extra":
                        {
                            "email": row[3],
                            "title": row[5],
                            "company":row[6],
                            "department":row[7],
                        }
                    }
                    tree["children"].append(child)
            return tree["children"] if tree["children"] else []

        hierarchy = build_tree(rows)
        return hierarchy
    except Exception as e:
        print("Failed to execute query:", e)
        return []

def get_employee_hierarchy_by_manager(start_fullname, company=None, department=None):
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
                company,
                department,
                CONCAT(firstname, ' ', lastname) AS fullname,
                1 AS level
            FROM employees
            WHERE CONCAT(lastname, ' ', firstname) = %s

            UNION ALL

            SELECT
                e.id,
                e.firstname,
                e.lastname,
                e.email,
                e.manager,
                e.title,
                e.company,
                e.department,
                CONCAT(e.firstname, ' ', e.lastname) AS fullname,
                eh.level + 1
            FROM employees e
            INNER JOIN employee_hierarchy eh ON e.manager = eh.fullname
        )
        SELECT * FROM employee_hierarchy;
        """, (start_fullname,))
        rows = cur.fetchall()
        cur.close()
        conn.close()

        def build_tree(data, company_filter=None, department_filter=None):
            # Создаем список узлов, которые могут быть корнями
            roots = []
            nodes = {}

            # Сначала создаем все узлы
            for row in data:
                if (company_filter is None or company_filter.lower() in row[6].lower()) and \
                (department_filter is None or department_filter.lower() in row[7].lower()):
                    
                    nodes[row[8]] = {
                        "name": f"{row[2]}\n{row[1]}",  # Фамилия\nИмя
                        "relationship": "Работает",
                        "children": [],
                        "class": "TION",
                        "textClass": "emphasis",
                        "extra": {
                            "email": row[3],
                            "title": row[5],
                            "company": row[6],
                            "department": row[7],
                        }
                    }

            # Затем организуем их в дерево
            for row in data:
                if row[8] in nodes:
                    if row[4] in nodes:
                        # Если у узла есть менеджер, добавляем его как ребенка к менеджеру
                        nodes[row[4]]["children"].append(nodes[row[8]])
                    else:
                        # Если менеджера нет в списке (например, в другой организации), узел становится корнем
                        roots.append(nodes[row[8]])

            return roots

        hierarchy = build_tree(rows, company_filter=company, department_filter=department)
        return hierarchy
    except Exception as e:
        print("Failed to execute query:", e)
        return []

def get_user_by_email(email):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM employees WHERE email = %s", (email,))
    user = cursor.fetchone()
    conn.close()
    return user

def insert_or_update_user(user_data):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Проверьте, существует ли пользователь в базе данных
    user = get_user_by_email(user_data['default_email'])
    if user:
        # Обновление данных пользователя
        cursor.execute("""
            UPDATE employees
            SET yaid = %s
            WHERE email = %s
        """, (user_data['id'], user_data['default_email']))

    conn.commit()
    conn.close()

def get_user_role(yaid):
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT role FROM user_roles WHERE yaid = %s", (yaid,))
    role = cursor.fetchone()
    conn.close()
    return role[0] if role else None

@app.route('/api/employees_hierarchy', methods=['GET'])
def get_employee_hierarchy_for_department():
    department = request.args.get('department')
    if(department):
        # Найдём руководителя отдела
        try:
            conn = psycopg2.connect(
                f"dbname= {dbname} user={user} password={password} host={host} port=5432"
            )
            cur = conn.cursor()
            cur.execute("""
                SELECT manager
                FROM managers
                WHERE department = %s
                LIMIT 1
            """, (department,))
            manager = cur.fetchone()
            cur.close()
            conn.close()

            if manager:
                manager_fullname = manager[0]
                print(manager_fullname)
                hierarchy = get_employee_hierarchy_by_manager(manager_fullname)
                print(hierarchy)
                return jsonify(hierarchy)
            else:
                return jsonify({"error": "Manager not found for this department"}), 404
        except Exception as e:
            print("Failed to fetch manager:", e)
            return jsonify({"error": "Internal server error"}), 500
    else:
        conn = psycopg2.connect(
            f"dbname= {dbname} user={user} password={password} host={host} port=5432"
        )
        cur = conn.cursor()
        cur.execute('SELECT id, firstname, lastname, email, manager, title, company, department, b_day FROM employees;')
        employees = cur.fetchall()
        cur.close()
        conn.close()

        employee_hierarchy = get_employee_hierarchy()
        return jsonify(employee_hierarchy)

@app.route('/api/employees', methods=['GET'])
def get_employees():
    conn = psycopg2.connect(
        f"dbname= {dbname} user={user} password={password} host={host} port=5432"
    )
    cur = conn.cursor()
    cur.execute('SELECT id, firstname, lastname, email, manager, title, company, department, b_day FROM employees;')
    employees = cur.fetchall()
    cur.close()
    conn.close()
    
    employees_data = [
        {
            'id': emp[0],
            'firstname': emp[1],
            'lastname': emp[2],
            'email': emp[3],
            'manager': emp[4],
            'title': emp[5],
            'company': emp[6],
            'department': emp[7],
            'b_day': emp[8]
        }
        for emp in employees
    ]
    return jsonify(employees_data)

    employee_hierarchy = get_employee_hierarchy(employees)
    return jsonify(employee_hierarchy)

@app.route('/api/save_employee', methods=['POST'])
def save_employee():
    data = request.json
    department = data['department']
    manager = data['manager']

    conn = psycopg2.connect(
        f"dbname= {dbname} user={user} password={password} host={host} port=5432"
    )
    cur = conn.cursor()
    cur.execute("UPDATE managers SET manager = %s WHERE department = %s", (manager, department))
    conn.commit()
    cur.close()
    conn.close()
    
    return jsonify({'status': 'success'})

@app.route('/api/departments', methods=['GET'])
def get_departments():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT id, name, department, orgname FROM managers')
    departments = cur.fetchall()
    cur.close()
    conn.close()
    
    return jsonify([{'id': dept[0], 'name': dept[1], 'department': dept[2], 'orgname': dept[3]} for dept in departments])

@app.route('/api/departments', methods=['POST'])
def add_department():
    data = request.get_json()
    name = data['name']
    tag = data.get('tag', '')
    organization = data['organization']
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute('INSERT INTO managers (name, department, orgName) VALUES (%s, %s, %s)', (name, tag, organization))
        conn.commit()
        response = {'success': True}
    except Exception as e:
        conn.rollback()
        response = {'success': False, 'error': str(e)}
    
    cur.close()
    conn.close()
    return jsonify(response)

@app.route('/api/departments/<int:id>', methods=['DELETE'])
def delete_department(id):
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute('DELETE FROM managers WHERE id = %s', (id,))
        conn.commit()
        response = {'success': True}
    except Exception as e:
        conn.rollback()
        response = {'success': False, 'error': str(e)}
    
    cur.close()
    conn.close()
    return jsonify(response)


@app.route('/api/employees_hierarchy')
def employees_hierarchy():
    hierarchy = get_employee_hierarchy()
    return jsonify(hierarchy)

@app.route('/')
def home():
    access_token = request.cookies.get('access_token')
    return render_template('index.html', access_token = access_token)
    
@app.route('/api/news')
def get_news():
    conn = psycopg2.connect(
        f"dbname= {dbname} user={user} password={password} host={host} port=5432"
    )
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('SELECT * FROM news ORDER BY created_at DESC LIMIT 4;')
    news = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify({'news': news})

@app.route('/api/add_news', methods=['POST'])
def add_news():
    if 'image' not in request.files:
        return jsonify({'error': 'No image part'}), 400
    
    image = request.files['image']
    
    if image.filename == '':
        return jsonify({'error': 'No selected image'}), 400
    
    if image and allowed_file(image.filename):
        filename = secure_filename(image.filename)
        image.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        
        # Создаем URL для сохраненного изображения
        image_url = f'/uploads/{filename}'
        
        new_article_data = request.form
        new_article = (
            image_url,
            new_article_data['title'],
            new_article_data['content'] if 'content' in new_article_data else '',
            new_article_data['created_at']
        )
    
    conn = psycopg2.connect(
        f"dbname= {dbname} user={user} password={password} host={host} port=5432"
    )
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO news (image_url, title, content, created_at, likes)
        VALUES (%s, %s, %s, %s, 0)
    """, new_article)
    conn.commit()
    cur.close()
    conn.close()
    
    return jsonify({'success': 'News added'}), 201

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/test_visual')
def test_visual():
    return render_template('test_visual.html')

@app.route('/test_visual2')
def test_visual2():
    return render_template('test_visual2.html')

# Убедитесь, что путь к директории соответствует структуре вашего проекта
@app.route('/department')
def department():
    company = request.args.get('company')
    department = request.args.get('department')
    return render_template('department.html', company=company, department=department)

# @app.route('/auth')
# def auth():
#     return send_from_directory('', 'auth.html')

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
        insert_or_update_user(response.json())
        return jsonify(response.json())
    return jsonify({'error': 'No access token'}), 401


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
