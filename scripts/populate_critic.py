"""Push all content pieces through the critic agent to populate the dashboard."""
import sqlite3, json, urllib.request, os, sys

DB = os.path.join(os.path.dirname(os.path.dirname(__file__)), "database", "app.db")
CTYPE_MAP = {"post": "social_post", "blog": "blog", "email": "email", "ad": "ad_copy"}

conn = sqlite3.connect(DB)
rows = conn.execute(
    "SELECT id, type, content, metadata FROM generated_content ORDER BY created_at DESC LIMIT 20"
).fetchall()
conn.close()

print(f"Critiquing {len(rows)} content pieces...")

for content_id, ctype, content_raw, meta_raw in rows:
    meta = json.loads(meta_raw) if meta_raw else {}
    try:
        content_obj = json.loads(content_raw) if content_raw and content_raw.strip() else {}
    except Exception:
        content_obj = {}
    text = list(content_obj.values())[0][:500] if content_obj else "Sample content"
    payload = json.dumps({
        "content_id": content_id,
        "content_text": text,
        "content_type": CTYPE_MAP.get(ctype, ctype),
        "brand_name": meta.get("brand_name", ""),
        "original_intent": "promote the brand and drive engagement on social media",
        "session_id": "dashboard-populate",
    }).encode()
    req = urllib.request.Request(
        "http://localhost:8007/critique",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        r = urllib.request.urlopen(req, timeout=45)
        res = json.loads(r.read())
        status = "PASS" if res["passed"] else "FAIL"
        print(f"  {meta.get('brand_name','?'):<22s}  overall={res['overall_score']}  {status}")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"  SKIP {content_id[:8]}: HTTP {e.code} {body[:80]}")
    except Exception as e:
        print(f"  SKIP {content_id[:8]}: {e}")

print("\nDone — refresh http://localhost:8080/critic_dashboard.html")
