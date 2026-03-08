import sqlite3, json, os
conn = sqlite3.connect(os.path.join(os.path.dirname(os.path.dirname(__file__)), "database", "app.db"))
tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print("Tables:", tables)
for t in tables:
    cols = [c[1] for c in conn.execute(f"PRAGMA table_info({t})").fetchall()]
    count = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"\n  {t} ({count} rows):")
    print(f"    cols: {cols}")
    if count > 0:
        row = dict(zip(cols, conn.execute(f"SELECT * FROM {t} LIMIT 1").fetchone()))
        # Show sample (truncate long values)
        sample = {k: (str(v)[:80] if v else v) for k, v in row.items()}
        print(f"    sample: {sample}")
conn.close()
