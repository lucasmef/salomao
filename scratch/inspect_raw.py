import psycopg2

try:
    conn = psycopg2.connect("postgresql://postgres:postgres@localhost:5432/salomao_dev")
    cur = conn.cursor()
    cur.execute("SELECT id, name, is_active, exclude_from_balance, account_type FROM accounts")
    rows = cur.fetchall()
    print(f"Found {len(rows)} accounts")
    for row in rows:
        print(row)
    cur.close()
    conn.close()
except Exception as e:
    print(e)
