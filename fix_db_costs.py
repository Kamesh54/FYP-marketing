import sqlite3
import os

DB_PATH = "database/app.db"

def fix_agent_costs():
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Correct values based on DEFAULT_AGENT_COSTS in cost_model.py
    # We want time_cost to be time_cost_per_second (e.g. 0.0001)
    # Currently it seems to hold execution time (e.g. 25.0)
    
    updates = [
        ("webcrawler", 0.0001),
        ("seo_agent", 0.0001),
        ("keyword_extractor", 0.0001),
        ("gap_analyzer", 0.0001),
        ("content_agent_blog", 0.0001),
        ("content_agent_social", 0.0001),
        ("image_generator", 0.0001),
        ("social_poster", 0.0001)
    ]
    
    try:
        for agent, cost in updates:
            print(f"Updating {agent} time_cost to {cost}")
            cursor.execute("UPDATE agent_costs SET time_cost = ? WHERE agent_name = ?", (cost, agent))
        
        conn.commit()
        print("Database updated successfully.")
        
        # Verify
        cursor.execute("SELECT agent_name, time_cost FROM agent_costs")
        rows = cursor.fetchall()
        print("New values:")
        for row in rows:
            print(row)
            
    except Exception as e:
        print(f"Error updating database: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    fix_agent_costs()
