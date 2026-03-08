"""Inspect all Neo4j nodes and relationships."""
from dotenv import load_dotenv; load_dotenv()
from neo4j import GraphDatabase
import os, json

uri  = os.getenv("NEO4J_URI")
user = os.getenv("NEO4J_USER")
pw   = os.getenv("NEO4J_PASSWORD")
db   = os.getenv("NEO4J_DATABASE", "neo4j")

driver = GraphDatabase.driver(uri, auth=(user, pw))
with driver.session(database=db) as s:
    print("=== NODES ===")
    for r in s.run("MATCH (n) RETURN labels(n) as labels, properties(n) as props"):
        label = r["labels"]
        props = dict(r["props"])
        print(f"  {label}")
        for k, v in props.items():
            print(f"    {k}: {v}")
        print()

    print("=== RELATIONSHIPS ===")
    rels = list(s.run(
        "MATCH (a)-[r]->(b) RETURN labels(a) as la, properties(a) as pa, type(r) as rel, labels(b) as lb, properties(b) as pb, properties(r) as rp"
    ))
    if not rels:
        print("  NONE — no edges exist!")
    for r in rels:
        a_id = dict(r["pa"]).get("brand_id") or dict(r["pa"]).get("user_id") or dict(r["pa"]).get("campaign_id") or "?"
        b_id = dict(r["pb"]).get("brand_id") or dict(r["pb"]).get("user_id") or dict(r["pb"]).get("campaign_id") or "?"
        print(f"  ({r['la']} id={a_id})-[{r['rel']}]->({r['lb']} id={b_id})  props={dict(r['rp'])}")

driver.close()
print("\nDone.")
