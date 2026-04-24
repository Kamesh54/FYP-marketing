#!/usr/bin/env python3
import requests
import time

print("Testing fast SEO endpoint...")
print("=" * 60)

start = time.time()

try:
    resp = requests.post(
        'http://localhost:8004/seo/analyze',
        json={'url': 'https://www.herocycles.com/'},
        timeout=60
    )
    
    elapsed = time.time() - start
    
    print(f"✅ Status: {resp.status_code}")
    print(f"⏱️  Time: {elapsed:.1f} seconds")
    
    data = resp.json()
    print(f"✅ SEO Score: {data.get('seo_score'):.2f}/1.0 ({int(data.get('seo_score', 0) * 100)}/100)")
    print(f"✅ Recommendations: {len(data.get('recommendations', []))}")
    print(f"✅ Status: {data.get('status')}")
    
    if elapsed < 60:
        print(f"\n🎉 FAST! Completed in {elapsed:.1f} seconds (very quick for chat)")
    else:
        print(f"\n⚠️  Took {elapsed:.1f} seconds (increased timeout helps)")
        
except Exception as e:
    elapsed = time.time() - start
    print(f"❌ Error after {elapsed:.1f}s: {e}")
