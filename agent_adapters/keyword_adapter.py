"""
Keyword Extraction Adapter — calls core functions directly (no HTTP).
Re-uses logic from keywordExtraction.py:
  - extract_domains_with_groq()
  - get_serpapi_results()
  - extract_keywords_from_text()
  - crawl logic is replaced by webcrawler_adapter
"""
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("adapter.keyword")


def run_keyword_extraction(customer_statement: str,
                           max_results: int = 5,
                           max_pages: int = 1) -> Dict[str, Any]:
    """
    Full keyword extraction pipeline:
    1. Extract domains from statement via Groq
    2. Search competitors via SerpAPI
    3. Crawl competitor sites (via webcrawler adapter)
    4. Extract keywords from crawled content
    Returns dict with competitor keyword data.
    """
    from keywordExtraction import (
        extract_domains_with_groq,
        get_serpapi_results,
        extract_keywords_from_text,
    )
    from .webcrawler_adapter import run_webcrawler

    try:
        # Step 1: Normalize to domains
        domains = extract_domains_with_groq(customer_statement)
        if not domains:
            return {"competitors": [], "error": "No domains extracted"}

        all_competitor_data: List[Dict[str, Any]] = []

        # Step 2: For each domain, search and crawl
        for d in domains:
            logger.info(f"Searching for competitors in domain: {d}")
            query = f"{d} software site"
            serp_results = get_serpapi_results(query, max_results=max_results)

            if serp_results:
                comp = serp_results[0]  # Take first result
                # Use webcrawler adapter instead of HTTP call
                crawl_result = run_webcrawler(comp["url"], max_pages=max_pages)
                content = crawl_result.get("content", "")

                if content:
                    kws = extract_keywords_from_text(content, max_keywords=50)
                    all_competitor_data.append({
                        "domain": d,
                        "competitor_name": comp["name"],
                        "url": comp["url"],
                        "short_keywords": kws.get("short_keywords", []),
                        "long_tail_keywords": kws.get("long_tail_keywords", []),
                        "content_length": len(content),
                    })

        logger.info(f"Extracted keywords for {len(all_competitor_data)} competitors")
        return {
            "competitors": all_competitor_data,
            "competitors_processed": len(all_competitor_data),
            "total_keywords": sum(
                len(c.get("short_keywords", [])) + len(c.get("long_tail_keywords", []))
                for c in all_competitor_data
            ),
        }
    except Exception as e:
        logger.error(f"Keyword extraction adapter failed: {e}")
        return {"competitors": [], "error": str(e)}
