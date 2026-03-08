import sqlite3, json
conn = sqlite3.connect("database/app.db")
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
print("Tables:", [r[0] for r in cur.fetchall()])

for tbl in ["content", "generated_content"]:
    cur.execute(f"PRAGMA table_info({tbl})")
    cols = cur.fetchall()
    if cols:
        print(f"\n{tbl} columns:", [r[1] for r in cols])
        cur.execute(f"SELECT * FROM {tbl} LIMIT 2")
        rows = cur.fetchall()
        for row in rows:
            d = {cols[i][1]: row[i] for i in range(len(cols))}
            print("  ", {k: str(v)[:60] for k,v in d.items() if v is not None})
conn.close()
