"""
Quick test script to verify Instagram credentials and login.
Run this before using the metrics collector to ensure Instagram auth works.
"""

import os
from dotenv import load_dotenv
from instagrapi import Client
import sys

def test_instagram_login():
    """Test Instagram login with current credentials."""
    
    print("=" * 60)
    print("🔍 Instagram Login Test")
    print("=" * 60)
    
    # Load environment variables
    load_dotenv()
    
    username = os.getenv("INSTAGRAM_USERNAME")
    password = os.getenv("INSTAGRAM_PASSWORD")
    
    # Check if credentials are set
    if not username or not password:
        print("\n❌ FAILED: Instagram credentials not found in .env file")
        print("\nPlease add to your .env file:")
        print("  INSTAGRAM_USERNAME=your_username")
        print("  INSTAGRAM_PASSWORD=your_password")
        return False
    
    print(f"\n📋 Username: {username}")
    print(f"📋 Password: {'*' * len(password)}")
    
    # Try to login
    print("\n🔐 Attempting to login...")
    
    try:
        client = Client()
        
        # Try to load existing session
        if os.path.exists("instagram.json"):
            print("📂 Found existing session file, loading...")
            client.load_settings("instagram.json")
        
        # Login
        client.login(username, password)
        
        # Save session
        client.dump_settings("instagram.json")
        
        print("✅ LOGIN SUCCESSFUL!")
        
        # Get user info to verify
        user_id = client.user_id
        user_info = client.user_info(user_id)
        
        print(f"\n👤 Account Info:")
        print(f"   User ID: {user_id}")
        print(f"   Username: {user_info.username}")
        print(f"   Full Name: {user_info.full_name}")
        print(f"   Followers: {user_info.follower_count}")
        print(f"   Following: {user_info.following_count}")
        print(f"   Posts: {user_info.media_count}")
        
        # Test fetching recent post
        print(f"\n📸 Testing media access...")
        try:
            medias = client.user_medias(user_id, amount=1)
            if medias:
                media = medias[0]
                print(f"   ✅ Successfully accessed recent post")
                print(f"   Post ID: {media.pk}")
                print(f"   Shortcode: {media.code}")
                print(f"   Likes: {media.like_count}")
                print(f"   Comments: {media.comment_count}")
            else:
                print(f"   ⚠️  No posts found on this account")
        except Exception as e:
            print(f"   ⚠️  Could not fetch media: {e}")
        
        print("\n" + "=" * 60)
        print("✅ Instagram authentication is working properly!")
        print("   You can now use the metrics collector.")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print(f"\n❌ LOGIN FAILED: {e}")
        
        # Provide helpful troubleshooting tips
        print("\n🔧 Troubleshooting:")
        
        if "challenge_required" in str(e).lower():
            print("  ⚠️  Instagram is asking for a challenge (security check)")
            print("     1. Login to Instagram on your browser/app")
            print("     2. Complete any verification steps")
            print("     3. Wait 30 minutes and try again")
        
        elif "two_factor" in str(e).lower():
            print("  ⚠️  Two-factor authentication is enabled")
            print("     1. Disable 2FA temporarily, OR")
            print("     2. Use an app-specific password")
        
        elif "checkpoint" in str(e).lower():
            print("  ⚠️  Instagram detected suspicious activity")
            print("     1. Login on Instagram app/website")
            print("     2. Complete any security checks")
            print("     3. Try again after 24 hours")
        
        elif "login" in str(e).lower() or "password" in str(e).lower():
            print("  ⚠️  Invalid username or password")
            print("     1. Check your credentials in .env")
            print("     2. Make sure there are no extra spaces")
            print("     3. Try logging in on Instagram app first")
        
        else:
            print("  ⚠️  Unexpected error")
            print(f"     Error details: {e}")
        
        print("\n💡 Common solutions:")
        print("  - Use the same device/IP you normally access Instagram from")
        print("  - Wait 24 hours between login attempts")
        print("  - Complete any challenges on Instagram app/website first")
        
        return False

if __name__ == "__main__":
    success = test_instagram_login()
    sys.exit(0 if success else 1)

