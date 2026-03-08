"""
Neo4j Repair + Backfill Script  (v3)
--------------------------------------
1. Deletes junk TestNode nodes
2. Deletes nodes with None/null IDs
3. Re-syncs all SQLite brands, users, content to Neo4j with correct props
4. Creates all missing edges:
   - User -[OWNS]-> Brand
   - User -[OWNS]-> Content        (via session to user join)
   - Brand -[HAS_CONTENT]-> Content (via metadata.brand_name -> brand lookup)
   - User -[HAS_SESSION]-> Session
   - Session -[PRODUCED]-> Content
   - Content -[PUBLISHED_ON]-> Platform  (via social_posts)
   - Content -[PERFORMED_ON {likes,shares,engagement_rate}]-> Platform  (via social_metrics)
"""
from dotenv import load_dotenv
load_dotenv()

import sys, os, json, sqlite3
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from neo4j import GraphDatabase
from datetime import datetime

URI  = os.getenv("NEO4J_URI")
USER = os.getenv("NEO4J_USER")
PW   = os.getenv("NEO4J_PASSWORD")
DB   = os.getenv("NEO4J_DATABASE", "neo4j")

driver = GraphDatabase.driver(URI, auth=(USER, PW))

def run(cypher, params=None):
    with driver.session(database=DB) as s:
        result = s.run(cypher, params or {})
        records = list(result)
        result.consume()
        return records

print("=== Neo4j Repair + Backfill v2 ===")
print()

# Step 1: Clean up
print("Step 1: Cleaning up invalid nodes...")
run("MATCH (n:TestNode) DETACH DELETE n")
for label, key in [("Brand", "brand_id"), ("Competitor", "competitor_id"), ("Content", "content_id")]:
    run(f"MATCH (n:{label}) WHERE n.{key} IS NULL OR n.{key} = 'None' DETACH DELETE n")
print("  Done.")

# SQLite connection
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "database", "app.db")
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

def q(sql, params=()):
    return [dict(r) for r in conn.execute(sql, params).fetchall()]

tables = [r["name"] for r in q("SELECT name FROM sqlite_master WHERE type='table'")]

# Step 2: Sync Users
print("\nStep 2: Syncing users...")
for u in q("SELECT * FROM users"):
    run(
        "MERGE (n:User {user_id: $uid}) ON CREATE SET n = $props ON MATCH SET n += $props",
        {
            "uid": str(u["id"]),
            "props": {
                "user_id": str(u["id"]),
                "email": u.get("email", ""),
                "tier": "free",
                "is_active": True,
                "created_at": str(u.get("created_at", "")),
                "updated_at": datetime.now().isoformat(),
            }
        }
    )
    print(f"  User {u['id']} ({u['email']})")

# Step 3: Sync Brands + User-OWNS-Brand
print("\nStep 3: Syncing brands + OWNS edges...")
for b in q("SELECT * FROM brand_profiles"):
    bid = str(b["id"])
    uid = str(b["user_id"])
    colors = []
    try:
        raw = b.get("colors", "[]")
        colors = json.loads(raw) if isinstance(raw, str) else (raw or [])
    except Exception:
        pass

    run(
        "MERGE (n:Brand {brand_id: $bid}) ON CREATE SET n = $props ON MATCH SET n += $props",
        {
            "bid": bid,
            "props": {
                "brand_id": bid,
                "brand_name": b.get("brand_name", ""),
                "industry": b.get("industry", ""),
                "website": b.get("website_url") or b.get("website") or "",
                "description": b.get("description", ""),
                "tagline": b.get("tagline", ""),
                "tone": b.get("tone", ""),
                "colors": colors,
                "auto_extracted": bool(b.get("auto_extracted", 0)),
                "created_at": str(b.get("created_at", "")),
                "updated_at": datetime.now().isoformat(),
            }
        }
    )

    r = run(
        "MATCH (u:User {user_id: $uid}) MATCH (b:Brand {brand_id: $bid}) "
        "MERGE (u)-[r:OWNS]->(b) SET r.role = 'owner', r.since = $since RETURN r",
        {"uid": uid, "bid": bid, "since": datetime.now().isoformat()}
    )
    print(f"  Brand {bid} ({b.get('brand_name')}) owned by User {uid}: {'OK' if r else 'MISS (user not in Neo4j?)'}")

# Lookup tables
brand_lookup = {b["brand_name"].lower(): str(b["id"]) for b in q("SELECT id, brand_name FROM brand_profiles")}
session_to_user = {}
if "sessions" in tables:
    for row in q("SELECT id, user_id FROM sessions"):
        if row.get("user_id"):
            session_to_user[row["id"]] = str(row["user_id"])

# Step 4: Sync Content + edges
print("\nStep 4: Syncing content + edges...")
contents = q("SELECT * FROM generated_content")
synced = owns_ok = brand_ok = 0

for c in contents:
    cid = c.get("id")
    if not cid:
        continue

    meta = {}
    raw_meta = c.get("metadata", "")
    if isinstance(raw_meta, str) and raw_meta:
        try:
            meta = json.loads(raw_meta)
        except Exception:
            pass
    elif isinstance(raw_meta, dict):
        meta = raw_meta

    # Extract title from content JSON
    # Blog types: look for title/headline keys
    # Social post types (twitter/instagram keys): use brand + first line of text
    title = ""
    raw_c = c.get("content", "")
    if isinstance(raw_c, str) and raw_c.strip().startswith("{"):
        try:
            parsed = json.loads(raw_c)
            title = (parsed.get("title") or parsed.get("blog_title") or
                     parsed.get("subject") or parsed.get("headline") or "")
            if not title:
                # Social post — use first platform's text truncated
                for key in ("twitter", "instagram", "linkedin", "facebook"):
                    val = parsed.get(key, "")
                    if val:
                        title = str(val)[:80].split("\n")[0].strip()
                        break
        except Exception:
            pass
    # Final fallback: brand_name + content type
    if not title:
        title = f"{meta.get('brand_name', '')} {c.get('type', '')}".strip()

    run(
        "MERGE (n:Content {content_id: $cid}) ON CREATE SET n = $props ON MATCH SET n += $props",
        {
            "cid": str(cid),
            "props": {
                "content_id": str(cid),
                "content_type": c.get("type", "blog_post"),
                "title": title,
                "brand_name": meta.get("brand_name", ""),
                "industry": meta.get("industry", ""),
                "status": c.get("status", "draft"),
                "seo_score": 0.0,
                "preview_url": c.get("preview_url", "") or "",
                "final_url": c.get("final_url", "") or "",
                "session_id": c.get("session_id", "") or "",
                "created_at": str(c.get("created_at", "")),
                "updated_at": datetime.now().isoformat(),
            }
        }
    )
    synced += 1

    # User OWNS Content
    uid = session_to_user.get(c.get("session_id", ""))
    if uid:
        r = run(
            "MATCH (u:User {user_id: $uid}) MATCH (cn:Content {content_id: $cid}) "
            "MERGE (u)-[rel:OWNS]->(cn) SET rel.since = $since RETURN rel",
            {"uid": uid, "cid": str(cid), "since": datetime.now().isoformat()}
        )
        if r:
            owns_ok += 1

    # Brand HAS_CONTENT Content
    brand_name_key = (meta.get("brand_name") or "").lower().strip()
    brand_id = brand_lookup.get(brand_name_key)
    if brand_id:
        r = run(
            "MATCH (b:Brand {brand_id: $bid}) MATCH (cn:Content {content_id: $cid}) "
            "MERGE (b)-[rel:HAS_CONTENT]->(cn) SET rel.since = $since RETURN rel",
            {"bid": brand_id, "cid": str(cid), "since": datetime.now().isoformat()}
        )
        if r:
            brand_ok += 1

print(f"  Content synced: {synced}")
print(f"  User OWNS Content edges: {owns_ok}")
print(f"  Brand HAS_CONTENT edges: {brand_ok}")

# Step 5: Sessions — User -[HAS_SESSION]-> Session -[PRODUCED]-> Content
print("\nStep 5: Syncing sessions + HAS_SESSION / PRODUCED edges...")
has_session_ok = produced_ok = 0
for s in q("SELECT * FROM sessions"):
    sid = s.get("id")
    uid = str(s.get("user_id", ""))
    if not sid or not uid:
        continue

    run(
        "MERGE (n:Session {session_id: $sid}) ON CREATE SET n = $props ON MATCH SET n += $props",
        {
            "sid": str(sid),
            "props": {
                "session_id": str(sid),
                "title": s.get("title", ""),
                "is_active": bool(s.get("is_active", 0)),
                "created_at": str(s.get("created_at", "")),
                "last_active": str(s.get("last_active", "")),
            }
        }
    )

    r = run(
        "MATCH (u:User {user_id: $uid}) MATCH (se:Session {session_id: $sid}) "
        "MERGE (u)-[rel:HAS_SESSION]->(se) SET rel.since = $since RETURN rel",
        {"uid": uid, "sid": str(sid), "since": datetime.now().isoformat()}
    )
    if r:
        has_session_ok += 1

    # Session -[PRODUCED]-> Content
    for c in q("SELECT id FROM generated_content WHERE session_id = ?", (sid,)):
        cid = c.get("id")
        if not cid:
            continue
        r = run(
            "MATCH (se:Session {session_id: $sid}) MATCH (cn:Content {content_id: $cid}) "
            "MERGE (se)-[rel:PRODUCED]->(cn) SET rel.since = $since RETURN rel",
            {"sid": str(sid), "cid": str(cid), "since": datetime.now().isoformat()}
        )
        if r:
            produced_ok += 1

print(f"  Session nodes synced: {len(q('SELECT id FROM sessions'))}")
print(f"  User HAS_SESSION edges: {has_session_ok}")
print(f"  Session PRODUCED edges: {produced_ok}")

# Step 6: Platforms — Content -[PUBLISHED_ON]-> Platform
print("\nStep 6: Syncing platforms + PUBLISHED_ON edges...")
published_ok = 0
for sp in q("SELECT * FROM social_posts"):
    cid = sp.get("content_id")
    platform = (sp.get("platform") or "").lower().strip()
    if not cid or not platform:
        continue

    run(
        "MERGE (p:Platform {name: $name}) ON CREATE SET p.name = $name ON MATCH SET p.name = $name",
        {"name": platform}
    )
    r = run(
        "MATCH (cn:Content {content_id: $cid}) MATCH (p:Platform {name: $pname}) "
        "MERGE (cn)-[rel:PUBLISHED_ON]->(p) "
        "SET rel.post_id = $post_id, rel.post_url = $post_url, rel.posted_at = $posted_at "
        "RETURN rel",
        {
            "cid": str(cid),
            "pname": platform,
            "post_id": sp.get("post_id", ""),
            "post_url": sp.get("post_url", ""),
            "posted_at": str(sp.get("posted_at", "")),
        }
    )
    if r:
        published_ok += 1

print(f"  Content PUBLISHED_ON edges: {published_ok}")

# Step 7: Performance — Content -[PERFORMED_ON {metrics}]-> Platform
print("\nStep 7: Syncing performance metrics + PERFORMED_ON edges...")
performed_ok = 0
for sm in q("SELECT * FROM social_metrics"):
    cid = sm.get("content_id")
    platform = (sm.get("platform") or "").lower().strip()
    if not cid or not platform:
        continue

    # Ensure Platform node exists
    run(
        "MERGE (p:Platform {name: $name}) ON CREATE SET p.name = $name ON MATCH SET p.name = $name",
        {"name": platform}
    )
    r = run(
        "MATCH (cn:Content {content_id: $cid}) MATCH (p:Platform {name: $pname}) "
        "MERGE (cn)-[rel:PERFORMED_ON]->(p) "
        "SET rel.likes = $likes, rel.comments = $comments, rel.shares = $shares, "
        "rel.impressions = $impressions, rel.reach = $reach, "
        "rel.engagement_rate = $engagement_rate, rel.recorded_at = $recorded_at "
        "RETURN rel",
        {
            "cid": str(cid),
            "pname": platform,
            "likes": sm.get("likes", 0),
            "comments": sm.get("comments", 0),
            "shares": sm.get("shares", 0),
            "impressions": sm.get("impressions", 0),
            "reach": sm.get("reach", 0),
            "engagement_rate": float(sm.get("engagement_rate", 0.0)),
            "recorded_at": str(sm.get("timestamp", "")),
        }
    )
    if r:
        performed_ok += 1

print(f"  Content PERFORMED_ON edges: {performed_ok}")

# Summary
print("\n=== Final Summary ===")
for r in run("MATCH (n) RETURN labels(n)[0] as lbl, count(*) as cnt ORDER BY cnt DESC"):
    print(f"  Node  {r['lbl']}: {r['cnt']}")
print()
for r in run("MATCH ()-[r]->() RETURN type(r) as rel, count(*) as cnt ORDER BY cnt DESC"):
    print(f"  Edge -{r['rel']}->: {r['cnt']}")

conn.close()
driver.close()
print("\nDone.")
