#!/usr/bin/env python3
"""
Fix agent costs in the database.
The old values had time_cost as total cost instead of per-second cost.
This script updates them to per-second rates.
"""
import sqlite3
import os

DB_PATH = "marketing_agents.db"

def fix_costs():
    if not os.path.exists(DB_PATH):
        print(f"Database {DB_PATH} not found - will be created with correct values on first run")
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check if agent_costs table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='agent_costs'")
    if not cursor.fetchone():
        print("agent_costs table does not exist - will be created on first run")
        conn.close()
        return
    
    print("Fixing agent costs...")
    
    # Update all agent costs to use per-second rates
    # Format: (agent_name, token_cost_per_1k, time_cost_per_second, api_cost_per_call)
    correct_costs = [
        ('webcrawler', 0.0001, 0.0001, 0),
        ('seo_agent', 0.0001, 0.0001, 0),
        ('keyword_extractor', 0.0005, 0.0001, 0),
        ('gap_analyzer', 0.001, 0.0001, 0.005),
        ('content_agent_blog', 0.002, 0.0001, 0),
        ('content_agent_social', 0.0005, 0.0001, 0),
        ('image_generator', 0, 0.0001, 0.05),
        ('social_poster', 0, 0.0001, 0),
        ('critic_agent', 0.0005, 0.0001, 0),
        ('research_agent', 0.0008, 0.0001, 0.01)
    ]
    
    for agent_name, token_cost, time_cost, api_cost in correct_costs:
        cursor.execute("""
        INSERT OR REPLACE INTO agent_costs (agent_name, token_cost, time_cost, api_cost_per_call)
        VALUES (?, ?, ?, ?)
        """, (agent_name, token_cost, time_cost, api_cost))
        print(f"  Updated {agent_name}: token_cost={token_cost}, time_cost_per_sec={time_cost}, api_cost={api_cost}")
    
    conn.commit()
    conn.close()
    print("\n✅ Agent costs fixed successfully!")
    print("Costs are now properly set as per-second rates.")

if __name__ == "__main__":
    fix_costs()

