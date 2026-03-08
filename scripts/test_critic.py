"""Quick test: hit the critic agent with a real content piece from SQLite."""
import sqlite3, json, urllib.request, os, sys

DB = os.path.join(os.path.dirname(os.path.dirname(__file__)), "database", "app.db")
conn = sqlite3.connect(DB)
row = conn.execute(
    "SELECT id, type, content, metadata FROM generated_content LIMIT 1"
).fetchone()
conn.close()

content_id, ctype, content_raw, meta_raw = row
meta = json.loads(meta_raw) if meta_raw else {}
content_obj = json.loads(content_raw) if content_raw else {}

# Take first platform text as the content to critique
content_text = list(content_obj.values())[0] if content_obj else "Sample content"

print(f"Testing critic with content_id: {content_id}")
print(f"Type: {ctype} | Brand: {meta.get('brand_name','?')}")
print()

# Map stored type names to what CriticRequest expects
CTYPE_MAP = {"post": "social_post", "blog": "blog", "email": "email", "ad": "ad_copy"}
critic_ctype = CTYPE_MAP.get(ctype, ctype)

payload = json.dumps({
    "content_id": content_id,
    "content_text": content_text[:500],
    "content_type": critic_ctype,
    "brand_name": meta.get("brand_name", ""),
    "original_intent": "promote the brand on social media",
    "session_id": "test-session"
}).encode()

req = urllib.request.Request(
    "http://localhost:8007/critique",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST"
)
try:
    r = urllib.request.urlopen(req, timeout=30)
    result = json.loads(r.read())
    print("=== CRITIC RESPONSE ===")
    print(f"  Passed:          {result.get('passed')}")
    print(f"  Intent score:    {result.get('intent_score')}")
    print(f"  Brand score:     {result.get('brand_score')}")
    print(f"  Quality score:   {result.get('quality_score')}")
    print(f"  Overall score:   {result.get('overall_score')}")
    print(f"  Critique:        {result.get('critique_text', '')[:200]}")
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)
