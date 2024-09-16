import psycopg2
from ldap3 import Server, Connection, ALL
from dotenv import load_dotenv
from pathlib import Path
import datetime
import os
import sys
import re

project_root = Path(__file__).resolve().parent.parent

# Загрузка переменных окружения из файла .env
load_dotenv(dotenv_path=project_root / '.env')

# Данные для подключения к Active Directory из .env файла
ad_server = os.getenv('AD_SERVER')
print(ad_server)
ad_user = os.getenv('AD_USER')
print(ad_user)
ad_password = os.getenv('AD_PASSWORD')
print(ad_password)
ad_base_dn = os.getenv('AD_BASE_DN')
print(ad_base_dn)

if ad_server is None:
    raise ValueError("AD_SERVER is not set.")

# Данные для подключения к PostgreSQL из .env файла
db_host = os.getenv('DB_HOST')
db_port = os.getenv('DB_PORT')
db_user = os.getenv('DB_USER')
db_password = os.getenv('DB_PASSWORD')
db_name = os.getenv('DB_NAME')

# Функция для безопасного получения строковых значений
def safe_str(value):
    return str(value) if value else None

def extract_manager_name(manager_value):
    if manager_value:
        match = re.search(r'CN=([^,]+)', manager_value)
        if match:
            return match.group(1)  # Вернуть часть строки после "CN="
    return None

# Подключение к AD
server = Server(ad_server, get_info=ALL)
try:
    conn = Connection(server, user=ad_user, password=ad_password, auto_bind=True)
    conn.search(ad_base_dn, '(objectClass=person)', attributes=['givenName', 'sn', 'extensionAttribute1', 'manager', 'mail', 'title', 'company', 'department'])
    ad_users = conn.entries
except Exception as e:
    print(f"Ошибка подключения к AD: {e}")
    sys.exit(1)

# Создание хэш-сета пользователей AD
ad_users_set = {f"{user.givenName} {user.sn}".lower() for user in ad_users}

try:
    conn = psycopg2.connect(
        host=db_host,
        port=db_port,
        user=db_user,
        password=db_password,
        dbname=db_name
    )

    cur = conn.cursor()

    # SQL-запросы для создания таблиц
    create_tables = """
    CREATE TABLE IF NOT EXISTS employees (
        id SERIAL PRIMARY KEY,
        firstname VARCHAR(255) NOT NULL,
        lastname VARCHAR(255) NOT NULL,
        email VARCHAR(255) UNIQUE NOT NULL,
        manager VARCHAR(255),
        b_day DATE,
        title VARCHAR(255),
        company VARCHAR(255),
        department VARCHAR(255),
        role VARCHAR(50) DEFAULT 'user',
        yaid VARCHAR(50)
    );

    CREATE TABLE IF NOT EXISTS managers (
        id SERIAL PRIMARY KEY,
        department VARCHAR(255) NOT NULL,
        manager VARCHAR(255) NOT NULL,
        name VARCHAR(255) NOT NULL,
        orgname VARCHAR(255)
    );

    CREATE TABLE IF NOT EXISTS news (
        id SERIAL PRIMARY KEY,
        image_url TEXT,
        title VARCHAR(255) NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        likes INT DEFAULT 0
    );
    """

    # Выполнение SQL-запросов
    cur.execute(create_tables)
    conn.commit()

    # Закрытие соединения
    cur.close()
    conn.close()
except Exception as e:
    print(f"Ошибка при работе с БД: {e}")
    sys.exit(1)


# Подключение к базе данных PostgreSQL
try:
    conn_db = psycopg2.connect(
        host=db_host,
        port=db_port,
        user=db_user,
        password=db_password,
        dbname=db_name
    )
    cur = conn_db.cursor()

    # Получение списка пользователей из БД
    cur.execute("SELECT firstname, lastname FROM employees")
    db_users = cur.fetchall()

    # Поиск пользователей для удаления
    users_to_delete = [user for user in db_users if f"{user[0]} {user[1]}".lower() not in ad_users_set]

    # Вывод и удаление пользователей
    if users_to_delete:
        print("Пользователи для удаления:")
        for user in users_to_delete:
            print(f"{user[0]} {user[1]}")
            try:
                cur.execute("DELETE FROM employees WHERE firstname = %s AND lastname = %s", (user[0], user[1]))
            except psycopg2.Error as e:
                print(f"Ошибка при удалении пользователя {user[0]} {user[1]}: {e}")
                conn_db.rollback()  # Откат транзакции в случае ошибки
    else:
        print("Нет пользователей для удаления.")

    # Добавление/обновление пользователей
    users_with_errors = []
    for user in ad_users:
        first_name = safe_str(user.givenName)
        last_name = safe_str(user.sn)
        extension_attr = safe_str(user.extensionAttribute1)
        if not extension_attr:
            print(f"Пропускаем запись для пользователя {first_name} {last_name}: поле b_day пустое.")
            continue # Пропускаем запись, если день рождения отсутствует
        manager = extract_manager_name(safe_str(user.manager)) if 'manager' in user else "None"
        email = safe_str(user.mail)
        title = safe_str(user.title)
        company = safe_str(user.company)
        department = safe_str(user.department)

        if not last_name:
            print(f"Ошибка при вставке пользователя {first_name} {last_name}: фамилия отсутствует, запись пропущена.")
            continue  # Пропускаем запись, если фамилия отсутствует
        if not email:
            print(f"Ошибка при вставке пользователя {first_name} {last_name}: отсутствует email, запись пропущена.")
            continue  # Пропускаем запись, если email отсутствует
        # Далее вставка или обновление в базу данных
        try:
            # Проверка существования записи в базе данных по email
            cur.execute("SELECT COUNT(*) FROM employees WHERE email = %s", (email,))
            exists = cur.fetchone()[0]

            if exists > 0:
                # Запись уже существует, выполняем UPDATE
                update_query = """
                    UPDATE employees 
                    SET firstname = %s, lastname = %s, b_day = TO_DATE(%s, 'DD.MM.YYYY'), manager = %s, 
                        email = %s, title = %s, company = %s, department = %s
                    WHERE email = %s
                """
                cur.execute(update_query, (first_name, last_name, extension_attr, manager, email, title, company, department, email))
            else:
                # Запись не существует, выполняем INSERT
                insert_query = """
                    INSERT INTO employees (firstname, lastname, b_day, manager, email, title, company, department)
                    VALUES (%s, %s, TO_DATE(%s, 'DD.MM.YYYY'), %s, %s, %s, %s, %s)
                """
                cur.execute(insert_query, (first_name, last_name, extension_attr, manager, email, title, company, department))

            conn_db.commit()

        except Exception as e:
            print(f"Ошибка при вставке или обновлении пользователя {first_name} {last_name}: {e}")
            conn_db.rollback()  # Откат транзакции в случае ошибки

        # Проверка на наличие записи по email
        cur.execute("SELECT COUNT(*) FROM employees WHERE email = %s", (email,))
        exists = cur.fetchone()[0]

        if exists > 0:
            # Обновление
            try:
                cur.execute("""
                    UPDATE employees SET firstname = %s, lastname = %s, b_day = TO_DATE(%s, 'DD.MM.YYYY'), manager = %s, title = %s, company = %s, department = %s
                    WHERE email = %s
                """, (first_name, last_name, extension_attr, manager, title, company, department, email))
            except psycopg2.Error as e:
                print(f"Ошибка при обновлении пользователя {first_name} {last_name}: {e}")
                # Логирование подробностей для определения проблемного поля
                print(f"Данные пользователя: firstname='{first_name}' (len={len(first_name)}), lastname='{last_name}' (len={len(last_name)}), b_day='{extension_attr}' (len={len(extension_attr) if extension_attr else 0}), manager='{manager}' (len={len(manager)}), title='{title}' (len={len(title) if title else 0}), company='{company}' (len={len(company) if company else 0}), department='{department}' (len={len(department) if department else 0}), email='{email}' (len={len(email) if email else 0})")
                conn_db.rollback()  # Откат транзакции в случае ошибки
                if e.pgcode == '22007':
                    users_with_errors.append((first_name, last_name, "Некорректная дата рождения"))
                else:
                    users_with_errors.append((first_name, last_name, str(e)))
        else:
            # Вставка
            try:
                cur.execute("""
                    INSERT INTO employees (firstname, lastname, b_day, manager, email, title, company, department)
                    VALUES (%s, %s, TO_DATE(%s, 'DD.MM.YYYY'), %s, %s, %s, %s, %s)
                """, (first_name, last_name, extension_attr, manager, email, title, company, department))
            except psycopg2.Error as e:
                print(f"Ошибка при вставке пользователя {first_name} {last_name}: {e}")
                # Логирование подробностей для определения проблемного поля
                print(f"Данные пользователя: firstname='{first_name}' (len={len(first_name)}), lastname='{last_name}' (len={len(last_name)}), b_day='{extension_attr}' (len={len(extension_attr) if extension_attr else 0}), manager='{manager}' (len={len(manager)}), title='{title}' (len={len(title) if title else 0}), company='{company}' (len={len(company) if company else 0}), department='{department}' (len={len(department) if department else 0}), email='{email}' (len={len(email) if email else 0})")
                conn_db.rollback()  # Откат транзакции в случае ошибки
                if e.pgcode == '22007':
                    users_with_errors.append((first_name, last_name, "Некорректная дата рождения"))
                else:
                    users_with_errors.append((first_name, last_name, str(e)))

    # Закрытие соединений
    conn_db.commit()  # Фиксация транзакций после успешного выполнения
    cur.close()
    conn_db.close()

    if users_with_errors:
        print("Пользователи с ошибками:")
        for user in users_with_errors:
            print(f"{user[0]} {user[1]}: {user[2]}")
    else:
        print("Все пользователи успешно обработаны.")
except Exception as e:
    print(f"Ошибка при работе с БД: {e}")
    sys.exit(1)
