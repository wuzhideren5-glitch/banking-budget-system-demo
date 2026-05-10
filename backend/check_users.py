import sqlite3, os
path = os.path.join(os.path.dirname(__file__), "data", "common.db")
conn = sqlite3.connect(path)
rows = conn.execute("SELECT id, user_name, first_login_flag, permission_type FROM users").fetchall()
print("Users:")
for r in rows:
    print(f"  id={r[0]} name={r[1]} first_login={r[2]} perm={r[3]}")
conn.close()
