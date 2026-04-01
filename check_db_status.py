import sqlite3
import json

conn = sqlite3.connect('database/app.db')
cursor = conn.cursor()

print('=== AGENT COSTS ===')
cursor.execute('SELECT agent_name, token_cost, time_cost, api_cost_per_call FROM agent_costs')
for row in cursor.fetchall():
    print(f'{row[0]:25} token:{row[1]:.6f}  time:{row[2]:.6f}  api:{row[3]:.6f}')

print('\n=== MABO LOCAL BO STATE ===')
cursor.execute('SELECT agent_name, iteration, best_value FROM mabo_local_bo_state LIMIT 5')
rows = cursor.fetchall()
if rows:
    for row in rows:
        bv = 'inf' if row[2] == float('inf') else f'{row[2]:.4f}'
        print(f'{row[0]:25} iter:{row[1]:3} best:{bv}')
else:
    print('No MABO local BO data')

print('\n=== GENERATED CONTENT (last 5) ===')
cursor.execute('SELECT id, type, metadata, created_at FROM generated_content ORDER BY created_at DESC LIMIT 5')
rows = cursor.fetchall()
if rows:
    for row in rows:
        import json
        meta = json.loads(row[2]) if row[2] else {}
        workflow = meta.get('workflow_name', 'N/A')
        print(f'{row[0][:36]:38} type:{row[1]:10} workflow:{workflow:20} at:{row[3]}')
else:
    print('No generated content')

print('\n=== MABO REWARD QUEUE ===')
cursor.execute('SELECT content_id, action, reward, engagement_rate, content_approved, created_at FROM mabo_reward_queue ORDER BY created_at DESC LIMIT 5')
rows = cursor.fetchall()
if rows:
    print(f'Found {len(rows)} rewards in queue:')
    for row in rows:
        reward = row[2] if row[2] is not None else 'NULL'
        engagement = row[3] if row[3] is not None else 'NULL'
        approved = row[4] if row[4] is not None else 'NULL'
        print(f'  {row[0][:36]:38} action:{row[1]:15} reward:{reward} engagement:{engagement} approved:{approved}')
else:
    print('❌ NO MABO rewards in queue! Workflows are not being registered.')

print('\n=== CRITIC LOGS (check if NEW ones are being created) ===')
cursor.execute('SELECT content_id, overall_score, passed, created_at FROM critic_logs ORDER BY created_at DESC LIMIT 10')
rows = cursor.fetchall()
if rows:
    print(f'Found {len(rows)} total critic evaluations (showing latest 10):')
    for i, row in enumerate(rows):
        marker = '🆕' if i < 3 else '  '
        print(f'{marker} {row[0][:36]:38} score:{row[1]:.2f} passed:{row[2]} at:{row[3]}')

    # Check if critic ran in last 10 minutes
    from datetime import datetime, timedelta
    latest = datetime.fromisoformat(rows[0][3])
    now = datetime.now()
    age_minutes = (now - latest).total_seconds() / 60
    print(f'\n  Latest critic log is {age_minutes:.1f} minutes old')
    if age_minutes > 10:
        print('  ⚠️  No recent critic activity! Critic may not be running.')
else:
    print('❌ NO CRITIC LOGS FOUND! This means critic is not saving results.')

print('\n=== GAP ANALYSIS CHECK ===')
cursor.execute('''
    SELECT id, metadata FROM generated_content
    WHERE metadata LIKE '%gap%'
    ORDER BY created_at DESC LIMIT 3
''')
rows = cursor.fetchall()
if rows:
    for row in rows:
        meta = json.loads(row[1]) if row[1] else {}
        print(f'  {row[0][:36]:38} gaps: {meta.get("gaps_found", "N/A")}')
else:
    print('No gap analysis results found in content metadata')

conn.close()
print('\n✅ Database check complete')

