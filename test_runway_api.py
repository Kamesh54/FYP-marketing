#!/usr/bin/env python3
"""
Test script for Runway ML API
Tests image generation with different prompts and configurations
"""
import os
import sys
import time
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

RUNWAY_API_KEY = os.getenv("RUNWAY_API_KEY")

def test_runway_image_generation(prompt: str, output_filename: str = None):
    """Test Runway ML text-to-image generation."""
    
    if not RUNWAY_API_KEY:
        print("❌ RUNWAY_API_KEY not found in environment variables")
        print("   Please add it to your .env file:")
        print("   RUNWAY_API_KEY=your_api_key_here")
        return False
    
    print(f"\n{'='*60}")
    print(f"🎨 Testing Runway ML Image Generation")
    print(f"{'='*60}\n")
    print(f"Prompt: {prompt}")
    print(f"API Key: {RUNWAY_API_KEY[:10]}...{RUNWAY_API_KEY[-4:]}")
    
    headers = {
        "Authorization": f"Bearer {RUNWAY_API_KEY}",
        "Content-Type": "application/json",
        "X-Runway-Version": "2024-11-06"
    }
    
    # Runway ML API format
    payload = {
        "model": "gen4_image",
        "promptText": prompt,
        "ratio": "1280:720",
    }
    
    print(f"\n📤 Sending request to Runway API...")
    print(f"   Model: {payload['model']}")
    print(f"   Prompt: {prompt[:50]}...")
    print(f"   Ratio: {payload['ratio']}")
    
    try:
        # Create task
        response = requests.post(
            "https://api.dev.runwayml.com/v1/text_to_image",
            json=payload,
            headers=headers,
            timeout=30
        )
        
        print(f"\n📥 Response Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ Error Response:")
            print(f"   Status: {response.status_code}")
            print(f"   Body: {response.text}")
            
            # Try to parse error details
            try:
                error_data = response.json()
                if 'error' in error_data:
                    print(f"\n💡 Error Details:")
                    print(f"   {error_data['error']}")
            except:
                pass
            
            return False
        
        task_data = response.json()
        task_id = task_data.get("id")
        
        print(f"✅ Task Created!")
        print(f"   Task ID: {task_id}")
        print(f"   Status: {task_data.get('status', 'unknown')}")
        
        # Poll for completion
        print(f"\n⏳ Polling for completion (max 5 minutes)...")
        
        for attempt in range(60):  # 60 attempts * 5 seconds = 5 minutes max
            time.sleep(5)
            
            status_response = requests.get(
                f"https://api.dev.runwayml.com/v1/tasks/{task_id}",
                headers=headers,
                timeout=30
            )
            
            if status_response.status_code != 200:
                print(f"   ⚠️  Poll attempt {attempt + 1}: HTTP {status_response.status_code}")
                continue
            
            status_data = status_response.json()
            status = status_data.get('status', 'UNKNOWN')
            
            print(f"   📊 Attempt {attempt + 1}/60: Status = {status}")
            
            if status == 'SUCCEEDED':
                output = status_data.get('output', [])
                if output and len(output) > 0:
                    image_url = output[0]
                    print(f"\n🎉 Success!")
                    print(f"   Image URL: {image_url}")
                    
                    # Download the image
                    if output_filename:
                        print(f"\n💾 Downloading image...")
                        img_response = requests.get(image_url, timeout=60)
                        if img_response.status_code == 200:
                            os.makedirs("test_images", exist_ok=True)
                            filepath = f"test_images/{output_filename}"
                            with open(filepath, "wb") as f:
                                f.write(img_response.content)
                            print(f"   ✅ Saved to: {filepath}")
                            print(f"   Size: {len(img_response.content) / 1024:.2f} KB")
                        else:
                            print(f"   ❌ Download failed: HTTP {img_response.status_code}")
                    
                    return True
                else:
                    print(f"❌ No output in response")
                    return False
            
            elif status in ['FAILED', 'CANCELLED']:
                print(f"\n❌ Task {status}")
                print(f"   Full response: {status_data}")
                return False
        
        print(f"\n⏰ Timeout: Task did not complete in 5 minutes")
        return False
    
    except requests.exceptions.RequestException as e:
        print(f"\n❌ Request Error: {e}")
        return False
    except Exception as e:
        print(f"\n❌ Unexpected Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    # Test prompts
    test_cases = [
        ("A modern minimalist logo for a tech startup, clean design, blue and white colors", "test_logo.jpg"),
        ("Professional product photography of a motorcycle, studio lighting, 8K resolution", "test_motorcycle.jpg"),
    ]
    
    print("🚀 Runway ML API Test Suite")
    print("="*60)
    
    if len(sys.argv) > 1:
        # Custom prompt from command line
        custom_prompt = " ".join(sys.argv[1:])
        test_cases = [(custom_prompt, f"custom_{int(time.time())}.jpg")]
    
    results = []
    for i, (prompt, filename) in enumerate(test_cases, 1):
        print(f"\n\n{'#'*60}")
        print(f"# Test Case {i}/{len(test_cases)}")
        print(f"{'#'*60}")
        
        success = test_runway_image_generation(prompt, filename)
        results.append((prompt[:50], success))
        
        if i < len(test_cases):
            print(f"\n⏸️  Waiting 10 seconds before next test...")
            time.sleep(10)
    
    # Summary
    print(f"\n\n{'='*60}")
    print(f"📊 TEST SUMMARY")
    print(f"{'='*60}")
    for i, (prompt, success) in enumerate(results, 1):
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{i}. {status} - {prompt}...")
    
    passed = sum(1 for _, s in results if s)
    print(f"\n🏁 Results: {passed}/{len(results)} tests passed")
    
    sys.exit(0 if passed == len(results) else 1)

