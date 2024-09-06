import psycopg2

try:
    conn = psycopg2.connect(
        "dbname=Users user=shalin-ar password=123QshI098 host=localhost port=5432"
    )
    cur = conn.cursor()
    cur.execute("SELECT 1;")
    result = cur.fetchone()
    print("Connection successful. Test query result:", result)
    cur.close()
    conn.close()
except Exception as e:
    print("Failed to connect to the database:", e) 
