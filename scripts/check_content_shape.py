import sqlite3, json, os
conn = sqlite3.connect(os.path.join(os.path.dirname(os.path.dirname(__file__)), "database", "app.db"))
rows = conn.execute("SELECT id, type, content, metadata FROM generated_content WHERE type != 'post' LIMIT 6").fetchall()
for r in rows:
    raw = r[2]
    meta = json.loads(r[3]) if r[3] else {}
    if raw and raw.strip().startswith("{"):
        parsed = json.loads(raw)
        print(f"ID: {r[0]} | type: {r[1]} | brand: {meta.get('brand_name')}")
        print(f"  Keys: {list(parsed.keys())[:8]}")
        for k, v in list(parsed.items())[:3]:
            print(f"  {k}: {str(v)[:120]}")
        print()
conn.close()
