import sqlite3
import json
import os
import sys

def get_db_connection():
    return sqlite3.connect("database/app.db")

def check_mabo_status():
    print("\n=== 🧠 MABO (Multi-Agent Brain) Status ===")
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 1. Check Global Coordination State
        print("\n[Global Coordination State]")
        try:
            cursor.execute("SELECT iteration, budget_allocations, total_budget, last_update FROM mabo_coordination_state ORDER BY iteration DESC LIMIT 1")
            row = cursor.fetchone()
            if row:
                print(f"Current Iteration: {row[0]}")
                print(f"Total Budget: ${row[2]}")
                print(f"Last Update: {row[3]}")
                allocations = json.loads(row[1])
                print("Budget Allocations (How much $ each agent gets):")
                for agent, budget in allocations.items():
                    print(f"  - {agent}: ${budget:.2f}")
            else:
                print("No coordination state found (System might be new).")
        except sqlite3.OperationalError:
            print("Table 'mabo_coordination_state' not found.")

        # 2. Check Agent Performance (Bandit/Metrics)
        print("\n[Agent Performance Metrics]")
        cursor.execute("""
            SELECT agent_name, AVG(execution_time) as avg_time, AVG(cost) as avg_cost, COUNT(*) as runs 
            FROM execution_metrics 
            GROUP BY agent_name
        """)
        rows = cursor.fetchall()
        if rows:
            print(f"{'Agent':<25} | {'Runs':<5} | {'Avg Time (s)':<12} | {'Avg Cost ($)':<12}")
            print("-" * 65)
            for r in rows:
                print(f"{r[0]:<25} | {r[3]:<5} | {r[1]:.4f}       | {r[2]:.4f}")
        else:
            print("No execution metrics recorded yet.")

        conn.close()
    except Exception as e:
        print(f"Error reading MABO status: {e}")

def check_vector_memory():
    print("\n=== 🧬 Vector Memory (Chroma/SQL) ===")
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check campaign_memory table
        try:
            cursor.execute("SELECT COUNT(*) FROM campaign_memory")
            count = cursor.fetchone()[0]
            print(f"Total Memories Stored: {count}")
            
            if count > 0:
                print("\nMost Recent Memories:")
                cursor.execute("SELECT id, source, created_at, alignment_score FROM campaign_memory ORDER BY created_at DESC LIMIT 3")
                for row in cursor.fetchall():
                    score = row[3] if row[3] is not None else "N/A"
                    print(f"  - [{row[2]}] Source: {row[1]}, Alignment Score: {score}")
        except sqlite3.OperationalError:
             print("Table 'campaign_memory' not found.")
            
        conn.close()
        
        # Check ChromaDB files
        if os.path.exists("./chroma_db"):
            print("\n[ChromaDB] Local vector store folder exists.")
        else:
             print("\n[ChromaDB] No local vector store folder found (might be getting created on fly).")

    except Exception as e:
        print(f"Error reading Vector Memory: {e}")

if __name__ == "__main__":
    if not os.path.exists("database/app.db"):
        print("❌ Database file 'database/app.db' not found. Run the orchestrator first!")
    else:
        check_mabo_status()
        check_vector_memory()
