"""
Quick migration script to add social_posts table to existing database
Run this once to fix the "no such table: social_posts" error
"""
import sqlite3
import os

DB_PATH = "orchestrator_memory.sqlite"

def add_social_posts_table():
    """Add social_posts table to database if it doesn't exist."""
    
    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found: {DB_PATH}")
        print("The database will be created automatically when you run orchestrator.py")
        return
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Check if table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='social_posts'")
        exists = cursor.fetchone()
        
        if exists:
            print("✅ Table 'social_posts' already exists!")
            return
        
        # Create table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS social_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_id TEXT NOT NULL,
            platform TEXT NOT NULL CHECK(platform IN ('twitter', 'instagram', 'facebook', 'linkedin')),
            post_id TEXT,
            post_url TEXT,
            posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (content_id) REFERENCES generated_content(id) ON DELETE CASCADE
        )
        """)
        
        conn.commit()
        conn.close()
        
        print("✅ Successfully created 'social_posts' table!")
        print("You can now approve posts and they will be saved to the database.")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    print("Adding social_posts table to database...")
    add_social_posts_table()

