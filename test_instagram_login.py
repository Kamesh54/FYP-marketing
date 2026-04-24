#!/usr/bin/env python3
"""
Instagram login and session persistence test.
Creates instagram.json session file for reuse.
"""

import os
import sys
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Check Python version
if sys.version_info < (3, 10):
    print("❌ Instagram posting requires Python 3.10+")
    print(f"   Current version: {sys.version_info.major}.{sys.version_info.minor}")
    sys.exit(1)

try:
    from instagrapi import Client
    from instagrapi.exceptions import ChallengeRequired, TwoFactorRequired
except ImportError:
    print("❌ instagrapi not installed")
    print("   Install with:")
    print("   python3 -m pip install instagrapi python-dotenv")
    sys.exit(1)

INSTAGRAM_USERNAME = os.getenv("INSTAGRAM_USERNAME")
INSTAGRAM_PASSWORD = os.getenv("INSTAGRAM_PASSWORD")

SESSION_FILE = "instagram.json"
METADATA_FILE = "instagram_session_metadata.json"


def save_metadata(user_id: str):
    metadata = {
        "created_at": datetime.now().isoformat(),
        "username": INSTAGRAM_USERNAME,
        "user_id": str(user_id),
        "python_version": sys.version,
    }
    with open(METADATA_FILE, "w") as f:
        json.dump(metadata, f, indent=2)


def create_client():
    cl = Client()

    # Load existing session if available
    if os.path.exists(SESSION_FILE):
        print(f"📁 Found existing session file: {SESSION_FILE}")
        try:
            cl.load_settings(SESSION_FILE)
            print("✅ Session settings loaded")
        except Exception as e:
            print(f"⚠️ Failed to load session settings: {e}")

    return cl


def print_account_info(cl):
    try:
        account_info = cl.account_info()
        print("\n👤 Account Info:")
        print(f"   Username: {account_info.username}")
        print(f"   Full Name: {account_info.full_name}")
        print(f"   Followers: {account_info.follower_count}")
        print(f"   Following: {account_info.following_count}")
    except Exception as e:
        print(f"⚠️ Could not fetch account info: {e}")


def login_and_save_session():
    print("\n" + "=" * 60)
    print("📸 Instagram Login & Session Test")
    print("=" * 60 + "\n")

    if not INSTAGRAM_USERNAME or not INSTAGRAM_PASSWORD:
        print("❌ Instagram credentials not found in environment variables")
        print("   Please add them to your .env file:")
        print("   INSTAGRAM_USERNAME=your_username")
        print("   INSTAGRAM_PASSWORD=your_password")
        return False

    print(f"Username: {INSTAGRAM_USERNAME}")
    print(f"Password: {'*' * len(INSTAGRAM_PASSWORD)}")

    cl = create_client()

    try:
        print("\n🔐 Attempting login...")
        cl.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)

        print("✅ Login successful!")

        user_id = cl.user_id
        print(f"   User ID: {user_id}")

        print(f"\n💾 Saving session to {SESSION_FILE}...")
        cl.dump_settings(SESSION_FILE)

        if os.path.exists(SESSION_FILE):
            file_size = os.path.getsize(SESSION_FILE)
            print("✅ Session saved successfully!")
            print(f"   File: {SESSION_FILE}")
            print(f"   Size: {file_size} bytes")
        else:
            print("❌ Failed to save session file")
            return False

        save_metadata(user_id)
        print(f"✅ Metadata saved to {METADATA_FILE}")

        print("\n🧪 Testing API access...")
        print_account_info(cl)

        print("\n" + "=" * 60)
        print("✅ Instagram login and session storage complete!")
        print("=" * 60)

        print("\n💡 Usage in your code:")
        print("   from instagrapi import Client")
        print("   cl = Client()")
        print("   cl.load_settings('instagram.json')")
        print("   cl.login('your_username', 'your_password')")

        return True

    except ChallengeRequired:
        print("\n❌ Login failed: challenge_required")
        print("   Instagram wants you to verify this login attempt.")
        print("\n✅ What to do next:")
        print("   1. Open Instagram mobile app or website")
        print("   2. Complete any security challenge/checkpoint")
        print("   3. Approve the login if Instagram asks")
        print("   4. Then rerun this script")
        return False

    except TwoFactorRequired:
        print("\n❌ Login failed: two_factor_required")
        print("   Your account has 2FA enabled.")
        print("   You need to extend the script to submit the 2FA code.")
        return False

    except Exception as e:
        print(f"\n❌ Login failed: {e}")
        import traceback
        traceback.print_exc()

        print("\n💡 Common Issues:")
        print("   1. Wrong username/password")
        print("   2. Account requires 2FA")
        print("   3. Instagram rate limiting/blocking")
        print("   4. Need to verify login from Instagram app first")
        print("   5. Session file is stale/corrupted")

        return False


def verify_session():
    if not os.path.exists(SESSION_FILE):
        print(f"❌ No session file found: {SESSION_FILE}")
        return False

    print(f"\n🔍 Verifying session file: {SESSION_FILE}")

    try:
        cl = Client()
        cl.load_settings(SESSION_FILE)

        if not INSTAGRAM_USERNAME or not INSTAGRAM_PASSWORD:
            print("⚠️ Credentials not set in .env")
            return False

        cl.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
        print("✅ Session is valid!")
        print(f"   User ID: {cl.user_id}")
        print_account_info(cl)
        return True

    except ChallengeRequired:
        print("❌ Session verification failed: challenge_required")
        print("   Instagram is asking for a checkpoint verification.")
        return False

    except TwoFactorRequired:
        print("❌ Session verification failed: two_factor_required")
        return False

    except Exception as e:
        print(f"❌ Session verification failed: {e}")
        return False


if __name__ == "__main__":
    print("🚀 Instagram Login Test Suite")
    print("=" * 60)

    if len(sys.argv) > 1 and sys.argv[1] == "--verify":
        success = verify_session()
    else:
        success = login_and_save_session()

    sys.exit(0 if success else 1)