import sqlite3
import os

DB_PATH = "database/app.db"

if not os.path.exists(DB_PATH):
    print(f"Database not found at {DB_PATH}")
else:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM agent_costs")
        rows = cursor.fetchall()
        if not rows:
            print("No rows in agent_costs table.")
        else:
            print("agent_costs table content:")
            for row in rows:
                print(row)
    except sqlite3.OperationalError as e:
        print(f"Error querying agent_costs: {e}")
    finally:
        conn.close()
