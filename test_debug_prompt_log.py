import json
from database import get_db_connection, get_prompt_executions

limit = 100
agent_name = None
context_type = None

try:
    with get_db_connection() as conn:
        conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
        cursor = conn.cursor()
        
        where_clauses, params = [], []
        where_sql = ""
        
        cursor.execute(
            f"""
            SELECT id, agent_name, context_type, prompt_text,
                   performance_score, use_count, created_at, updated_at
            FROM prompt_versions
            {where_sql}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            params + [limit],
        )
        templates = [dict(r) for r in cursor.fetchall()]
        print(f"Templates found: {len(templates)}")
        
        cursor.execute(
            "SELECT DISTINCT agent_name, context_type FROM prompt_versions ORDER BY agent_name, context_type"
        )
        agents = [{"agent_name": row["agent_name"], "context_type": row["context_type"]} for row in cursor.fetchall()]
        print(f"Agents found: {len(agents)}")
    
    executions = get_prompt_executions(
        agent_name=agent_name,
        context_type=context_type,
        limit=limit
    )
    print(f"Executions found: {len(executions)}")
    
    result = {
        "templates": templates,
        "total_templates": len(templates),
        "executions": executions,
        "total_executions": len(executions),
        "agents": agents
    }
    json.dumps(result, default=str)
    print("Success!")
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
