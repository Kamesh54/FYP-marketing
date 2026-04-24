#!/usr/bin/env python3
"""Test Instagram posting with dummy content"""
import os
import sys
from dotenv import load_dotenv
from instagrapi import Client
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime

load_dotenv()

INSTAGRAM_USERNAME = os.getenv("INSTAGRAM_USERNAME")
INSTAGRAM_PASSWORD = os.getenv("INSTAGRAM_PASSWORD")

print("🚀 Instagram Dummy Content Posting Test")
print("=" * 60)

if not INSTAGRAM_USERNAME or not INSTAGRAM_PASSWORD:
    print("ERROR: Instagram credentials not found in .env file")
    sys.exit(1)

# Step 1: Create a dummy image
print("\n📸 Step 1: Creating dummy image...")
try:
    img = Image.new('RGB', (1080, 1080), color='#4A90E2')
    draw = ImageDraw.Draw(img)
    
    # Add text
    text = f"Test Post from Markx Pro\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    
    # Use default font
    draw.text((100, 500), text, fill="white")
    
    # Save image
    image_path = "dummy_instagram_post.jpg"
    img.save(image_path)
    print(f"✅ Dummy image created: {image_path}")
except Exception as e:
    print(f"❌ Failed to create image: {e}")
    sys.exit(1)

# Step 2: Load Instagram session and post
print("\n📤 Step 2: Posting to Instagram...")
try:
    client = Client()
    
    # Load existing session or login
    if os.path.exists("instagram.json"):
        print("   Loading existing session...")
        client.load_settings("instagram.json")
    
    print(f"   Re-authenticating with {INSTAGRAM_USERNAME}...")
    client.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
    
    # Create caption
    caption = """🎉 Test Post - Markx Pro Content Marketing Platform
    
✨ This is a dummy post to test Instagram integration
📅 Posted via automated system
🤖 Powered by LangGraph + Multi-Agent Architecture

#MarketingAutomation #ContentMarketing #TestPost #AI"""
    
    print(f"   Uploading image with caption...")
    media = client.photo_upload(path=image_path, caption=caption)
    
    post_url = f"https://www.instagram.com/p/{media.code}/"
    
    print(f"\n✅✅✅ SUCCESS! Post published! ✅✅✅")
    print(f"Post URL: {post_url}")
    print(f"Media ID: {media.pk}")
    print(f"Caption length: {len(caption)} characters")
    
    # Save session for future use
    print(f"\n   Saving session...")
    client.dump_settings("instagram.json")
    print(f"   Session saved!")
    
except Exception as e:
    print(f"\n❌ Failed to post: {type(e).__name__}")
    print(f"Error: {str(e)}")
    
    # Clean up dummy image
    if os.path.exists(image_path):
        os.remove(image_path)
    sys.exit(1)

# Clean up
print(f"\n🧹 Cleaning up dummy image...")
if os.path.exists(image_path):
    os.remove(image_path)
    print(f"✅ Dummy image removed")

print("\n" + "=" * 60)
print("✅ Instagram posting test complete!")
