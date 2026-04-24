#!/usr/bin/env python3
"""Test SEO HTML report generation in orchestrator"""

import requests
import json
import os
import jwt
from datetime import datetime, timedelta

BASE_URL = "http://localhost:8004"
JWT_SECRET = os.getenv("JWT_SECRET", "your-secret-key-change-this-in-production")

def get_auth_token():
    """Generate a valid JWT token"""
    payload = {
        "user_id": "test_user",
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=1)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

def test_html_report_generation():
    """Test that HTML reports are generated"""
    print("\n=== Test: SEO Analysis with HTML Report Generation ===\n")
    
    payload = {
        "user_id": "test_user",
        "message": "Give me a detailed SEO report for https://www.google.com/",
        "active_brand": "default"
    }
    
    headers = {"Authorization": f"Bearer {get_auth_token()}"}
    
    try:
        response = requests.post(f"{BASE_URL}/chat", json=payload, headers=headers, timeout=120)
        print(f"Status: {response.status_code}")
        
        if response.ok:
            data = response.json()
            print(f"✅ Chat endpoint responded successfully")
            print(f"\nResponse:\n{data.get('response', '')[:300]}...")
            return True
        else:
            print(f"❌ Error: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Exception: {e}")
        return False

def test_direct_seo_endpoint():
    """Test direct SEO endpoint with report generation"""
    print("\n=== Test: Direct /seo/analyze/detailed Endpoint ===\n")
    
    try:
        response = requests.post(
            f"{BASE_URL}/seo/analyze/detailed",
            json={"url": "https://www.example.com/"},
            timeout=120
        )
        print(f"Status: {response.status_code}")
        
        if response.ok:
            data = response.json()
            
            print(f"✅ Analysis completed")
            print(f"  • URL: {data.get('final_url')}")
            print(f"  • Score: {int(data.get('seo_score', 0) * 100)}/100")
            print(f"  • Issues: {len(data.get('recommendations', []))}")
            
            report_path = data.get('report_path')
            if report_path:
                print(f"  • Report path: {report_path}")
                
                # Check if file exists
                if os.path.exists(report_path):
                    size = os.path.getsize(report_path)
                    print(f"  • Report file size: {size:,} bytes ✅")
                else:
                    print(f"  • Report file NOT found ❌")
            else:
                print(f"  • No report_path in response ❌")
            
            return True
        else:
            print(f"❌ Error: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Exception: {e}")
        return False

def list_generated_reports():
    """List all generated reports"""
    print("\n=== Generated SEO Reports ===\n")
    
    reports = [f for f in os.listdir('.') if f.startswith('seo_report_') and f.endswith('.html')]
    
    if reports:
        for report in sorted(reports)[-5:]:  # Show last 5
            size = os.path.getsize(report)
            print(f"  📄 {report} ({size:,} bytes)")
        print(f"\n✅ Total reports found: {len(reports)}")
    else:
        print("  No reports found")

if __name__ == "__main__":
    print("Testing SEO HTML Report Generation")
    print("=" * 60)
    
    # Check if orchestrator is running
    try:
        requests.get(f"{BASE_URL}/", timeout=5)
    except:
        print("❌ Orchestrator not running on port 8004")
        exit(1)
    
    print("✅ Orchestrator is running\n")
    
    # Test direct endpoint
    test_direct_seo_endpoint()
    
    # List reports
    list_generated_reports()
    
    print("\n" + "=" * 60)
    print("Testing Complete!")
