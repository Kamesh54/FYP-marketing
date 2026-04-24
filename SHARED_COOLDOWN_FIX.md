# Global Shared Cooldown Fix (April 6, 2026)

## Problem Diagnosed
Your logs showed **repeated 429 errors** even when cooldown was supposedly active:
```
2026-04-06 15:33:35,048 - INFO - Skipping model llama-3.3-70b-versatile due to active cooldown (845.0s left)
2026-04-06 15:33:39,107 - INFO - HTTP Request: POST https://api.groq.com/openai/v1/chat/completions "HTTP/1.1 429"  ← STILL HAMMERING!
```

**Root Cause:** Three independent LLM call paths existed, each with their own cooldown tracking:
1. `safe_groq_chat()` in content_agent.py ✅ (had cooldown)
2. `groq_chat_with_failover()` in llm_failover.py ❌ (no cooldown)
3. `_groq_chat_with_fallback()` in intelligent_router.py ❌ (no cooldown)

When agent A set cooldown in one location, agents B & C didn't know about it → repeated 429s.

---

## Solution Implemented

### 1. Created Shared Cooldown Module
**File:** `shared_cooldown.py` (NEW)
- Global `_MODEL_COOLDOWN_UNTIL` dict (thread-safe with lock)
- Functions all agents import:
  - `is_model_on_cooldown(model_name)` — check if model is blocked
  - `get_cooldown_remaining(model_name)` — remaining seconds
  - `set_cooldown(model_name, retry_after_seconds)` — block model
  - `handle_groq_429(model_name, error_dict)` — automatic parsing and blocking
  - `parse_retry_after_seconds(error_message)` — extract retry window from Groq error

### 2. Updated All Groq Call Sites
Integrated shared cooldown into:

#### `content_agent.py` — `safe_groq_chat()`
- **Before:** Local `_MODEL_COOLDOWN_UNTIL` dict per function
- **After:** 
  - Imports `is_model_on_cooldown()`, `handle_groq_429()`
  - Checks global cooldown BEFORE attempting any Groq call
  - Registers 429s to global cooldown
  - Syntax: ✅ VALID

#### `llm_failover.py` — `groq_chat_with_failover()`
- **Before:** No cooldown checking at all
- **After:**
  - Imports shared cooldown functions
  - Hard-blocks models on global cooldown
  - Registers 429s to global cooldown on caught exceptions
  - Syntax: ✅ VALID

#### `intelligent_router.py` — `_groq_chat_with_fallback()`
- **Before:** No cooldown checking at all
- **After:**
  - Imports shared cooldown functions
  - Hard-blocks models on global cooldown
  - Registers 429s to global cooldown on caught exceptions
  - Syntax: ✅ VALID

---

## How It Works Now

### Scenario: llama-3.3-70b-versatile hits 429

1. **Agent A** (e.g., content_agent) calls Groq with llama-3.3
2. Groq returns 429: "Please try again in 3m37.728s"
3. **Agent A's safe_groq_chat()** calls `handle_groq_429()` → sets global cooldown ✅
4. **Agent B** (e.g., intelligent_router) tries to use llama-3.3
5. **Before:** Would retry immediately → 429 again
6. **After:** Calls `is_model_on_cooldown()` → **SKIPS** to next fallback model
7. **Agent C** (campaign_agent using llm_failover) also skips
8. Result: **No repeated 429s** across any agent

---

## Data Structures

### Global Cooldown Dict
```python
_MODEL_COOLDOWN_UNTIL: Dict[str, datetime] = {
    "llama-3.3-70b-versatile": datetime(2026, 4, 6, 15, 37, 35),  # UTC
    "qwen/qwen3-32b": datetime(2026, 4, 6, 15, 38, 10),  # If also hit
}
```
- Keys: Model name
- Values: datetime when model becomes available again (UTC)
- Thread-safe: Access via `threading.Lock`

### Fallback Model Stack (Order of Attempts)
```
1. llama-3.3-70b-versatile (primary)
2. meta-llama/llama-4-scout-17b-16e-instruct (NEW - #1 fallback)
3. qwen/qwen3-32b
4. openai/gpt-oss-120b
5. openai/gpt-oss-20b
6. llama-3.1-8b-instant
7. llama3-8b-8192
```

---

## Files Modified

| File | Change | Status |
|------|--------|--------|
| `shared_cooldown.py` | NEW file (global cooldown module) | ✅ Created |
| `content_agent.py` | Import + integrate shared cooldown in `safe_groq_chat()` | ✅ Updated |
| `llm_failover.py` | Import + integrate shared cooldown in `groq_chat_with_failover()` | ✅ Updated |
| `intelligent_router.py` | Import + integrate shared cooldown in `_groq_chat_with_fallback()` | ✅ Updated |

---

## Testing the Fix

After restarting services, the logs should show:

```
2026-04-06 15:35:00 - Groq call failed: Error code 429 (retry in 3m37s)
2026-04-06 15:35:01 - Skipping model llama-3.3-70b-versatile due to active global cooldown (216.0s left)
2026-04-06 15:35:02 - HTTP Request: meta-llama/llama-4-scout-17b-16e-instruct "200 OK"  ← FALLBACK WORKING!
```

**Key indicator:** Model is skipped (not retried) across ALL agents until cooldown expires.

---

## Backward Compatibility
- If `shared_cooldown.py` can't import → agents log warning but continue with NO cooldown
- Existing fallback models remain in GROQ_FALLBACK_MODELS env var
- Syntax fully compatible with Python 3.8+

---

## Restart Instructions
```bash
# Kill all agent processes
pkill -f "python.*\.py"

# Or use start.bat (Windows):
.\start.bat

# Verify orchestrator logs show:
# "shared_cooldown not found" → PROBLEM
# (no warning) → ✅ GOOD
```

---

## Summary
- ✅ Created shared global cooldown tracker
- ✅ Integrated into all 3 Groq call paths (content_agent, llm_failover, intelligent_router)
- ✅ Thread-safe with automatic retry window parsing
- ✅ All syntax validated
- ✅ Backward compatible
- **Expected improvement:** No more repeated 429s; fallback models attempted immediately
