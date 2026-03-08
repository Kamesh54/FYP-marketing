import sqlite3
import json
import os
from datetime import datetime

DB_PATH = "database/app.db"

def inspect_memory():
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # Get the 5 most recent memories
        cursor.execute("""
            SELECT id, campaign_id, alignment_score, created_at, tags, context_metadata
            FROM campaign_memory 
            ORDER BY created_at DESC 
            LIMIT 5
        """)
        rows = cursor.fetchall()
        
        print(f"\nFound {len(rows)} memory entities:\n")
        
        for row in rows:
            print(f"--- Memory ID: {row['id']} ---")
            print(f"Time: {row['created_at']}")
            print(f"Alignment Score: {row['alignment_score']}")
            print(f"Tags: {row['tags']}")
            
            # Parse Metadata to show what's actually stored
            try:
                metadata = json.loads(row['context_metadata'])
                print("Content Preview:")
                
                # Check for social or blog content
                if 'platform' in metadata:
                    print(f"  Type: Social Post ({metadata.get('platform')})")
                    print(f"  Tone: {metadata.get('variant_tone')}")
                    if 'post_copy' in metadata:
                        copy = metadata['post_copy']
                        print(f"  Twitter: {copy.get('twitter', '')[:100]}...")
                        print(f"  Instagram: {copy.get('instagram', '')[:100]}...")
                elif 'topic' in metadata:
                    print(f"  Type: Blog/Content")
                    print(f"  Topic: {metadata.get('topic')}")
                else:
                    print(f"  Metadata Keys: {list(metadata.keys())}")
                    
            except Exception as e:
                print(f"  Raw Metadata: {row['context_metadata'][:100]}...")
            
            print("-" * 50)

    except Exception as e:
        print(f"Error reading memory: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    inspect_memory()
