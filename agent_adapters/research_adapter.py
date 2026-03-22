"""
Research Agent Adapter — calls research pipeline directly (no HTTP).
"""
import logging
import asyncio
from typing import Dict, Any, Optional, List

logger = logging.getLogger("adapter.research")


def run_deep_research(domain: str,
                      depth_level: str = "standard",
                      competitors: Optional[List[str]] = None,
                      use_cache: bool = True) -> Dict[str, Any]:
    """
    Run deep competitor/topic research pipeline:
    1. Check cache
    2. Crawl domain
    3. Extract keywords
    4. Gap analysis (if competitors)
    5. LLM synthesis
    Returns structured research brief.
    """
    import os
    from datetime import datetime
    from groq import Groq
    from database import get_research_cache, save_research_cache
    from .webcrawler_adapter import run_webcrawler
    from .keyword_adapter import run_keyword_extraction

    try:
        # Check cache
        if use_cache:
            cached = get_research_cache(domain, depth_level)
            if cached:
                logger.info(f"Research cache hit for {domain}/{depth_level}")
                return cached.get("result_json", cached)

        # Step 1: Crawl
        max_pages = {"quick": 2, "standard": 5, "deep": 10}.get(depth_level, 5)
        url = f"https://{domain}" if not domain.startswith("http") else domain
        crawl_data = run_webcrawler(url, max_pages=max_pages)

        # Step 2: Extract keywords
        raw_text = crawl_data.get("content", "")[:8000]
        kw_result = run_keyword_extraction(raw_text, max_results=5, max_pages=1)
        keywords = []
        for comp in kw_result.get("competitors", []):
            keywords.extend(comp.get("short_keywords", []))
            keywords.extend(comp.get("long_tail_keywords", []))
        keywords = list(set(keywords))[:20]

        # Step 3: Gap analysis (if competitors provided)
        gaps: List[str] = []
        if competitors:
            from .gap_analyzer_adapter import run_gap_analysis
            for comp_domain in competitors[:3]:
                try:
                    gap_result = run_gap_analysis(
                        company_name=domain,
                        product_description=raw_text[:2000],
                        company_url=url,
                        max_competitors=1,
                    )
                    missing = gap_result.get("gap_analysis", {}).get("missing_keywords", {})
                    if missing:
                        gaps.extend(missing.get("short", []))
                        gaps.extend(missing.get("long_tail", []))
                except Exception as ge:
                    logger.warning(f"Gap analysis failed for {comp_domain}: {ge}")

        # Step 4: Synthesize with LLM
        GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
        brief = "LLM not configured"
        if GROQ_API_KEY:
            client = Groq(api_key=GROQ_API_KEY)
            kw_str = ", ".join(keywords[:15]) or "none found"
            gap_str = "\n".join(f"- {g}" for g in gaps[:8]) or "- none analyzed"

            prompt = f"""You are a senior content strategist. Produce a concise research brief for {domain}.

Top keywords found: {kw_str}

Competitor content gaps:
{gap_str}

Write a structured brief covering:
1. Brand positioning / market niche (2-3 sentences)
2. Audience signals inferred from keywords
3. Top 3 content opportunities based on gaps
4. Recommended content tone and format
5. 5 specific blog / social post ideas with suggested titles

Keep it concise and actionable."""

            try:
                resp = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.5,
                    max_tokens=1200,
                )
                brief = resp.choices[0].message.content.strip()
            except Exception as llm_err:
                brief = f"Synthesis failed: {llm_err}"

        result = {
            "domain": domain,
            "depth_level": depth_level,
            "crawl_summary": {
                "pages_crawled": crawl_data.get("pages_count", 0),
            },
            "top_keywords": keywords[:20],
            "competitor_gaps": gaps[:10],
            "research_brief": brief,
            "generated_at": datetime.now().isoformat(),
        }

        # Cache result
        ttl = {"quick": 24, "standard": 72, "deep": 168}.get(depth_level, 72)
        save_research_cache(domain, depth_level, result, ttl_hours=ttl)

        logger.info(f"Research completed for {domain}")
        return result

    except Exception as e:
        logger.error(f"Research adapter failed for {domain}: {e}")
        return {"domain": domain, "error": str(e)}
