#!/usr/bin/env python3
"""Test detailed vs quick SEO analysis detection in chat"""

import requests
import json
import time
import jwt
import os
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

def test_quick_seo_request():
    """Test regular SEO request (should use fast endpoint)"""
    print("\n=== TEST 1: Quick SEO Analysis ===")
    payload = {
        "user_id": "test_user",
        "message": "Analyze https://www.bisleri.com/ for SEO",
        "active_brand": "default"
    }
    
    headers = {"Authorization": f"Bearer {get_auth_token()}"}
    response = requests.post(f"{BASE_URL}/chat", json=payload, headers=headers, timeout=60)
    print(f"Status: {response.status_code}")
    if response.ok:
        data = response.json()
        text = data.get("response", "")
        print(f"Response preview: {text[:200]}...")
        if "Quick" in text or "quick" in text or "metrics" in text:
            print("✅ Response suggests QUICK analysis (good - no detailed keywords)")
        return True
    print(f"❌ Error: {response.text}")
    return False

def test_detailed_seo_request():
    """Test detailed SEO request (should use comprehensive endpoint)"""
    print("\n=== TEST 2: Detailed SEO Analysis ===")
    payload = {
        "user_id": "test_user",
        "message": "Give me a detailed SEO report for https://www.bisleri.com/",
        "active_brand": "default"
    }
    
    headers = {"Authorization": f"Bearer {get_auth_token()}"}
    response = requests.post(f"{BASE_URL}/chat", json=payload, headers=headers, timeout=60)
    print(f"Status: {response.status_code}")
    if response.ok:
        data = response.json()
        text = data.get("response", "")
        print(f"Response preview: {text[:200]}...")
        if "Detailed" in text or "comprehensive" in text:
            print("✅ Response indicates DETAILED analysis (correct - detected keyword)")
        return True
    print(f"❌ Error: {response.text}")
    return False

def test_comprehensive_keyword_variants():
    """Test different keyword variations"""
    print("\n=== TEST 3: Keyword Variants ===")
    keywords = ["comprehensive", "full", "in-depth", "complete", "thorough"]
    
    for keyword in keywords:
        payload = {
            "user_id": "test_user",
            "message": f"Provide a {keyword} SEO audit for https://www.zapier.com/",
            "active_brand": "default"
        }
        
        headers = {"Authorization": f"Bearer {get_auth_token()}"}
        response = requests.post(f"{BASE_URL}/chat", json=payload, headers=headers, timeout=60)
        if response.ok:
            print(f"✅ '{keyword}' - Status {response.status_code}")
        else:
            print(f"❌ '{keyword}' - Status {response.status_code}")

if __name__ == "__main__":
    print("Testing Detailed SEO Detection in Chat")
    print("=" * 50)
    
    # Check if orchestrator is running
    try:
        requests.get(f"{BASE_URL}/", timeout=5)
    except:
        print("❌ Orchestrator not running on port 8004")
        exit(1)
    
    print("✅ Orchestrator is running\n")
    
    test_quick_seo_request()
    time.sleep(2)
    test_detailed_seo_request()
    time.sleep(2)
    test_comprehensive_keyword_variants()
    
    print("\n" + "=" * 50)
    print("Testing Complete!")
