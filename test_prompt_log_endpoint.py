import requests
import time

time.sleep(2)
resp = requests.get('http://localhost:8004/prompt-log')
data = resp.json()
print(f'Templates: {data.get("total_templates")}')
print(f'Executions: {data.get("total_executions")}')
print(f'Agents: {len(data.get("agents", []))}')
