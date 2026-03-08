"""
Knowledge Graph Context Builder
---------------------------------
Called before content generation to pull brand-specific memory from Neo4j:
  - What topics/titles have already been generated (avoid repetition)
  - Which content types have been used (blog, post, etc.)
  - Best performing content per platform (what worked)
  - Platforms the brand has published on
  - Competitor landscape (if any COMPETES_WITH edges exist)

Returns a plain dict that prompt builders inject into the LLM prompt.
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def get_brand_knowledge_context(brand_name: str) -> Dict[str, Any]:
    """
    Query Neo4j for everything known about a brand and its content history.
    Returns a structured dict ready to be formatted into a generation prompt.
    Falls back to empty context if graph is unavailable — generation continues normally.
    """
    empty = {
        "past_titles": [],
        "content_type_counts": {},
        "best_performing": [],
        "platforms_used": [],
        "competitor_names": [],
        "total_content_count": 0,
        "available": False,
    }

    try:
        from .graph_database import get_graph_client
        client = get_graph_client()
        if not client.connected:
            return empty
    except Exception as e:
        logger.warning(f"KG context: graph not available — {e}")
        return empty

    ctx: Dict[str, Any] = {"available": True}

    # 1. Titles of recently generated content (last 20) — avoid repeating topics
    try:
        rows = client.query(
            """
            MATCH (b:Brand)-[:HAS_CONTENT]->(c:Content)
            WHERE toLower(b.brand_name) = toLower($brand_name)
            RETURN c.title AS title, c.content_type AS ctype, c.status AS status,
                   c.created_at AS created_at
            ORDER BY c.created_at DESC
            LIMIT 20
            """,
            {"brand_name": brand_name},
        )
        ctx["past_titles"] = [
            {"title": r.get("title", ""), "type": r.get("ctype", ""), "status": r.get("status", "")}
            for r in rows if r.get("title")
        ]
        ctx["total_content_count"] = len(rows)
    except Exception as e:
        logger.warning(f"KG context: past_titles query failed — {e}")
        ctx["past_titles"] = []
        ctx["total_content_count"] = 0

    # 2. Content type breakdown — know what's been over/under-used
    try:
        rows = client.query(
            """
            MATCH (b:Brand)-[:HAS_CONTENT]->(c:Content)
            WHERE toLower(b.brand_name) = toLower($brand_name)
            RETURN c.content_type AS ctype, count(*) AS cnt
            ORDER BY cnt DESC
            """,
            {"brand_name": brand_name},
        )
        ctx["content_type_counts"] = {r.get("ctype", "unknown"): r.get("cnt", 0) for r in rows}
    except Exception as e:
        logger.warning(f"KG context: content_type_counts query failed — {e}")
        ctx["content_type_counts"] = {}

    # 3. Best performing content (by engagement_rate on PERFORMED_ON edges)
    try:
        rows = client.query(
            """
            MATCH (b:Brand)-[:HAS_CONTENT]->(c:Content)-[p:PERFORMED_ON]->(pl:Platform)
            WHERE toLower(b.brand_name) = toLower($brand_name)
              AND p.engagement_rate > 0
            RETURN c.title AS title, pl.name AS platform,
                   p.engagement_rate AS engagement_rate, p.likes AS likes,
                   p.impressions AS impressions
            ORDER BY p.engagement_rate DESC
            LIMIT 5
            """,
            {"brand_name": brand_name},
        )
        ctx["best_performing"] = [
            {
                "title": r.get("title", ""),
                "platform": r.get("platform", ""),
                "engagement_rate": r.get("engagement_rate", 0),
                "likes": r.get("likes", 0),
            }
            for r in rows
        ]
    except Exception as e:
        logger.warning(f"KG context: best_performing query failed — {e}")
        ctx["best_performing"] = []

    # 4. Platforms the brand has published on
    try:
        rows = client.query(
            """
            MATCH (b:Brand)-[:HAS_CONTENT]->(c:Content)-[:PUBLISHED_ON]->(pl:Platform)
            WHERE toLower(b.brand_name) = toLower($brand_name)
            RETURN DISTINCT pl.name AS platform
            """,
            {"brand_name": brand_name},
        )
        ctx["platforms_used"] = [r.get("platform", "") for r in rows if r.get("platform")]
    except Exception as e:
        logger.warning(f"KG context: platforms_used query failed — {e}")
        ctx["platforms_used"] = []

    # 5. Competitors (if CompetitorGapAnalyzer has created COMPETES_WITH edges)
    try:
        rows = client.query(
            """
            MATCH (b:Brand)-[:COMPETES_WITH]->(comp:Competitor)
            WHERE toLower(b.brand_name) = toLower($brand_name)
            RETURN comp.competitor_name AS name, comp.domain AS domain,
                   comp.threat_level AS threat_level
            LIMIT 10
            """,
            {"brand_name": brand_name},
        )
        ctx["competitor_names"] = [
            r.get("name") or r.get("domain", "") for r in rows if (r.get("name") or r.get("domain"))
        ]
    except Exception as e:
        logger.warning(f"KG context: competitor query failed — {e}")
        ctx["competitor_names"] = []

    return ctx


def format_kg_context_for_prompt(ctx: Dict[str, Any]) -> str:
    """
    Convert the raw KG context dict into a concise, LLM-readable section
    to be injected into content generation prompts.
    """
    if not ctx.get("available"):
        return ""

    lines = ["=== KNOWLEDGE GRAPH MEMORY (from previous content history) ==="]

    total = ctx.get("total_content_count", 0)
    lines.append(f"Total content generated for this brand so far: {total}")

    # Past topics — avoid repetition
    past = ctx.get("past_titles", [])
    if past:
        lines.append("\nRecently generated content (DO NOT repeat these topics/angles):")
        for item in past[:10]:
            t = item.get("title", "").strip()
            if t:
                lines.append(f"  - [{item.get('type', 'content')}] {t}")

    # Type breakdown — suggest under-used types
    type_counts = ctx.get("content_type_counts", {})
    if type_counts:
        lines.append("\nContent type history:")
        for ctype, cnt in type_counts.items():
            lines.append(f"  - {ctype}: {cnt} pieces")

    # Best performing — replicate what worked
    best = ctx.get("best_performing", [])
    if best:
        lines.append("\nBest performing content (replicate these angles/styles):")
        for item in best:
            lines.append(
                f"  - \"{item.get('title', '')}\" on {item.get('platform', '')} "
                f"(engagement: {item.get('engagement_rate', 0):.2f}, likes: {item.get('likes', 0)})"
            )

    # Platforms used
    platforms = ctx.get("platforms_used", [])
    if platforms:
        lines.append(f"\nPlatforms brand has published on: {', '.join(platforms)}")

    # Competitors
    competitors = ctx.get("competitor_names", [])
    if competitors:
        lines.append(f"\nKnown competitors: {', '.join(competitors)}")
        lines.append("  → Differentiate from these competitors in tone, angle, and value proposition.")

    lines.append(
        "\nINSTRUCTION: Use this history to generate content that is FRESH — "
        "new angles, topics not yet covered, and build on what performed well."
    )

    return "\n".join(lines)
