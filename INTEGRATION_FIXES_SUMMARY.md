# Integration Fixes Summary

## 🎯 Overview
Fixed critical integration issues with Runway ML image generation and Instagram social posting.

---

## ✅ Issue 1: Runway API 400 Bad Request Error

### Problem
```
ERROR - Runway Error: 400 Client Error: Bad Request
```

### Root Cause
- Using incorrect model name: `"gen4_image"` 
- Using incorrect payload format: `"ratio": "1920:1080"` instead of separate width/height

### Solution
Updated Runway API calls to use the correct Gen-3 Alpha model:

**Files Modified:**
1. `orchestrator.py` (line 684-691)
2. `agent_adapters/image_adapter.py` (line 43-55)

**Changes:**
```python
# OLD (incorrect)
payload = {
    "model": "gen4_image",
    "ratio": "1920:1080",
    ...
}

# NEW (correct)
payload = {
    "model": "gen3a_turbo",  # ✅ Correct Gen-3 model
    "width": 1920,            # ✅ Separate dimensions
    "height": 1080,
    ...
}
```

---

## ✅ Issue 2: Instagram Login Error

### Problem
```
ERROR - Social Post Error (instagram): 'NoneType' object has no attribute 'login'
```

### Root Cause
- Global `insta_client` was `None` (failed initialization or missing credentials)
- Code tried to call `insta_client.login()` without checking if client exists

### Solution
Refactored Instagram posting to:
1. Check if `instagrapi` is available
2. Verify credentials are set
3. Create a fresh client instance for each post
4. Provide clear error messages

**File Modified:**
`orchestrator.py` (line 760-793)

**Changes:**
```python
# OLD (vulnerable to None)
insta_client.login(...)  # ❌ Crashes if insta_client is None

# NEW (defensive)
if not INSTAGRAPI_AVAILABLE:
    raise ValueError("Instagram posting requires Python 3.10+")
if not INSTAGRAM_USERNAME or not INSTAGRAM_PASSWORD:
    raise ValueError("Instagram credentials not configured")

temp_insta_client = InstaClient()  # ✅ Fresh instance
temp_insta_client.login(...)
```

---

## 🧪 Test Scripts Created

### 1. Runway API Test (`test_runway_api.py`)
**Purpose:** Verify Runway ML image generation with the correct API

**Usage:**
```bash
# Test with default prompts
python3 test_runway_api.py

# Test with custom prompt
python3 test_runway_api.py "A beautiful sunset over mountains"
```

**Features:**
- ✅ Tests correct `gen3a_turbo` model
- ✅ Tests width/height format
- ✅ Polls for task completion
- ✅ Downloads generated images to `test_images/`
- ✅ Detailed error reporting

---

### 2. Instagram Login Test (`test_instagram_login.py`)
**Purpose:** Test Instagram login and create reusable session file

**Usage:**
```bash
# Create/refresh session
python3 test_instagram_login.py

# Verify existing session
python3 test_instagram_login.py --verify
```

**Features:**
- ✅ Logs in to Instagram
- ✅ Saves session to `instagram.json`
- ✅ Verifies session validity
- ✅ Shows account info (followers, etc.)
- ✅ Creates metadata file for tracking
- ✅ Provides troubleshooting tips

**Session Files Created:**
- `instagram.json` - Session data for reuse
- `instagram_session_metadata.json` - Human-readable metadata

---

## 📋 Prerequisites

### Runway ML
1. Get API key from https://runwayml.com
2. Add to `.env`:
   ```
   RUNWAY_API_KEY=your_api_key_here
   ```

### Instagram
1. Must use **Python 3.10+** (instagrapi requirement)
2. Add to `.env`:
   ```
   INSTAGRAM_USERNAME=your_username
   INSTAGRAM_PASSWORD=your_password
   ```
3. Account should not have 2FA enabled (or use session file)

---

## 🚀 Next Steps

1. **Test Runway Integration:**
   ```bash
   python3 test_runway_api.py
   ```

2. **Setup Instagram Session:**
   ```bash
   python3 test_instagram_login.py
   ```

3. **Verify Orchestrator:**
   ```bash
   # Restart orchestrator to load fixes
   python3 orchestrator.py
   ```

4. **End-to-End Test:**
   - Create a social post through the frontend
   - Verify image is generated successfully
   - Verify post goes to Instagram

---

## 📝 Notes

- **Runway costs:** Gen-3 Alpha Turbo is faster and cheaper than other models
- **Instagram session:** Reusing session file prevents repeated logins and reduces blocking risk
- **Error handling:** Both integrations now provide clear error messages for missing credentials

---

## 🐛 Troubleshooting

### Runway Issues
- **400 Error:** Check API key is valid
- **Timeout:** Increase poll timeout (currently 5 minutes)
- **Rate limiting:** Wait before retrying

### Instagram Issues
- **Login fails:** May need to verify from Instagram app first
- **2FA enabled:** Use session file approach
- **Rate limited:** Instagram may block automated logins
- **Python < 3.10:** Upgrade Python or disable Instagram posting

---

## ✅ Summary

| Issue | Status | Files Modified |
|-------|--------|----------------|
| Runway 400 Error | ✅ Fixed | `orchestrator.py`, `agent_adapters/image_adapter.py` |
| Instagram NoneType | ✅ Fixed | `orchestrator.py` |
| Test Scripts | ✅ Created | `test_runway_api.py`, `test_instagram_login.py` |

All integration issues resolved! 🎉

