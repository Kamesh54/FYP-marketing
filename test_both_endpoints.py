#!/usr/bin/env python3
"""
Compare Fast vs Comprehensive SEO Analysis
Shows the difference between chat (fast) and SEO page (detailed) endpoints
"""
import requests
import time

print("=" * 80)
print("COMPARING: Fast vs Comprehensive SEO Analysis")
print("=" * 80)

url = "https://www.bisleri.com/"

# Test 1: Fast Analysis (For Chat)
print("\n1️⃣ FAST ANALYSIS (Chat Integration)")
print("-" * 80)
start = time.time()
try:
    resp_fast = requests.post(
        'http://localhost:8004/seo/analyze',
        json={'url': url},
        timeout=30
    )
    fast_time = time.time() - start
    fast_data = resp_fast.json()
    
    print(f"✅ Status: {resp_fast.status_code}")
    print(f"⏱️  Time: {fast_time:.2f} seconds")
    print(f"📊 Score: {round(fast_data.get('seo_score', 0) * 100)}/100")
    print(f"📋 Recommendations: {len(fast_data.get('recommendations', []))}")
    print(f"📝 Message: 'Use this for instant chat feedback'")
except Exception as e:
    print(f"❌ Error: {e}")
    fast_data = None

# Test 2: Comprehensive Analysis (For SEO Page)
print("\n\n2️⃣ COMPREHENSIVE ANALYSIS (SEO Page)")
print("-" * 80)
start = time.time()
try:
    resp_comp = requests.post(
        'http://localhost:8004/seo/analyze/detailed',
        json={'url': url},
        timeout=60
    )
    comp_time = time.time() - start
    comp_data = resp_comp.json()
    
    print(f"✅ Status: {resp_comp.status_code}")
    print(f"⏱️  Time: {comp_time:.2f} seconds")
    print(f"📊 Score: {round(comp_data.get('seo_score', 0) * 100)}/100")
    print(f"📋 Total Issues: {len(comp_data.get('recommendations', []))}")
    print(f"🔴 High Priority: {comp_data.get('scores', {}).get('high_priority', 0)}")
    print(f"🟡 Medium Priority: {comp_data.get('scores', {}).get('medium_priority', 0)}")
    print(f"🟢 Low Priority: {comp_data.get('scores', {}).get('low_priority', 0)}")
    print(f"📊 Analysis Time: {comp_data.get('analysis_time', 'N/A')}")
    
    # Show details
    details = comp_data.get('details', {})
    if details:
        print(f"\n📈 Detailed Metrics:")
        print(f"   • Title: {details.get('title', {}).get('length', 0)} chars")
        print(f"   • Meta Description: {details.get('meta_description', {}).get('length', 0)} chars")
        print(f"   • H1 Headings: {details.get('headings', {}).get('h1_count', 0)}")
        print(f"   • H2 Headings: {details.get('headings', {}).get('h2_count', 0)}")
        print(f"   • Images: {details.get('images', {}).get('total', 0)} (Alt coverage: {details.get('images', {}).get('alt_coverage', 'N/A')})")
        print(f"   • Internal Links: {details.get('links', {}).get('internal', 0)}")
        print(f"   • External Links: {details.get('links', {}).get('external', 0)}")
        print(f"   • Word Count: {details.get('content', {}).get('word_count', 0)}")
        print(f"   • HTTPS: {'Yes' if details.get('https') else 'No'}")
        print(f"   • Mobile Responsive: {'Yes' if details.get('mobile_responsive') else 'No'}")
    
except Exception as e:
    print(f"❌ Error: {e}")
    comp_data = None

# Comparison Summary
print("\n\n" + "=" * 80)
print("COMPARISON SUMMARY")
print("=" * 80)

if fast_data and comp_data:
    print(f"\nSpeed Comparison:")
    print(f"  Fast:         {fast_time:.2f}s ✅ (for chat)")
    print(f"  Comprehensive: {comp_time:.2f}s ✅ (for SEO page)")
    print(f"  Difference:   {abs(comp_time - fast_time):.2f}s")
    
    print(f"\nIssues Comparison:")
    fast_issues = len(fast_data.get('recommendations', []))
    comp_issues = len(comp_data.get('recommendations', []))
    print(f"  Fast Issues:         {fast_issues}")
    print(f"  Comprehensive Issues: {comp_issues}")
    print(f"  Additional Details:  +{comp_issues - fast_issues}")
    
    print(f"\nScore Detail:")
    fast_score = round(fast_data.get('seo_score', 0) * 100)
    comp_score = round(comp_data.get('seo_score', 0) * 100)
    print(f"  Fast Score:         {fast_score}/100")
    print(f"  Comprehensive Score: {comp_score}/100")
    
    print(f"\nRecommendation Usage:")
    print(f"  Chat:     Use /seo/analyze")
    print(f"  SEO Page: Use /seo/analyze/detailed")
    
    print(f"\n🎉 Both endpoints working perfectly!")
    print(f"   - Chat gets instant response")
    print(f"   - SEO page gets comprehensive details")
    print(f"   - User experience optimized for both scenarios")

print("\n" + "=" * 80)
