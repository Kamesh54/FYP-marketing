#!/usr/bin/env python3
import requests
import time

print("Testing detailed SEO endpoint...")
print("=" * 70)

start = time.time()

try:
    # Test bisleri.com with detailed endpoint
    resp = requests.post(
        'http://localhost:8004/seo/analyze/detailed',
        json={'url': 'https://www.bisleri.com/'},
        timeout=60
    )
    
    elapsed = time.time() - start
    
    print(f"✅ Status: {resp.status_code}")
    print(f"⏱️ Time: {elapsed:.1f} seconds")
    
    data = resp.json()
    print(f"✅ SEO Score: {round(data.get('seo_score', 0) * 100)}/100")
    print(f"✅ Total Issues: {len(data.get('recommendations', []))}")
    print(f"✅ High Priority: {data.get('scores', {}).get('high_priority', 0)}")
    print(f"✅ Medium Priority: {data.get('scores', {}).get('medium_priority', 0)}")
    print(f"✅ Low Priority: {data.get('scores', {}).get('low_priority', 0)}")
    
    print("\nTop Issues:")
    for i, rec in enumerate(data.get('recommendations', [])[:5], 1):
        print(f"  {i}. [{rec.get('priority')}] {rec.get('issue')}")
    
    print(f"\n📊 Details included:")
    details = data.get('details', {})
    if details:
        print(f"  - Title: {details.get('title', {}).get('length', 0)} chars")
        print(f"  - Meta Description: {details.get('meta_description', {}).get('length', 0)} chars")
        print(f"  - H1 Tags: {details.get('headings', {}).get('h1_count', 0)}")
        print(f"  - Total Images: {details.get('images', {}).get('total', 0)}")
        print(f"  - Alt Text Coverage: {details.get('images', {}).get('alt_coverage', 'N/A')}")
        print(f"  - Internal Links: {details.get('links', {}).get('internal', 0)}")
        print(f"  - Word Count: {details.get('content', {}).get('word_count', 0)}")
    
    print(f"\n✅ Analysis Time: {data.get('analysis_time', 'unknown')}")
    print(f"\n🎉 Comprehensive endpoint working!")
    
except Exception as e:
    elapsed = time.time() - start
    print(f"❌ Error after {elapsed:.1f}s: {e}")
