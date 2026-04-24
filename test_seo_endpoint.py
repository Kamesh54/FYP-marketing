import requests
import json
import time

time.sleep(2)
print("Testing SEO endpoint...")
try:
    resp = requests.post('http://localhost:8004/seo/analyze', 
        json={"url": "https://www.herocycles.com/"}
    )
    print(f"Status: {resp.status_code}")
    data = resp.json()
    print(f"Response keys: {list(data.keys())}")
    print(f"Status: {data.get('status')}")
    print(f"URL: {data.get('url')}")
    print(f"SEO Score: {data.get('seo_score')}")
    if data.get('error'):
        print(f"Error: {data.get('error')}")
    else:
        print("✓ SEO analyze endpoint working!")
except Exception as e:
    print(f"Error: {e}")
