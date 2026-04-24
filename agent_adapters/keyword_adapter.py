"""
Keyword Extraction Adapter — calls core functions directly (no HTTP).
Re-uses logic from keywordExtraction.py:
  - extract_domains_with_groq()
  - get_serpapi_results()
  - extract_keywords_from_text()
  - crawl logic is replaced by webcrawler_adapter

Key improvement: Groq-powered filtering step removes non-brand results
(review sites, software tools, health blogs, etc.) from SerpAPI output
before crawling.
"""
import os
import json
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("adapter.keyword")

# Known non-competitor domain patterns to skip fast (saves Groq calls)
_BLACKLIST_PATTERNS = [
    "wikipedia.org", "reddit.com", "quora.com",
    "amazon.com", "flipkart.com", "indiamart.com",
    "healthline.com", "webmd.com", "mayoclinic.org",
    "emailvendorselection.com", "g2.com", "capterra.com",
    "gartner.com", "trustradius.com", "softwareadvice.com",
    "techradar.com", "pcmag.com", "techcrunch.com",
    "youtube.com", "linkedin.com", "twitter.com", "facebook.com",
    "instagram.com", "medium.com", "wordpress.com",
    "shopify.com", "woocommerce.com", "stripe.com",
    "onfleet.com", "mycloudgrocer.com",
    "infor.com", "sap.com", "oracle.com",
]


def _is_likely_non_competitor(url: str) -> bool:
    """Quick check — skip obvious non-brand URLs without using Groq."""
    url_lower = url.lower()
    for pattern in _BLACKLIST_PATTERNS:
        if pattern in url_lower:
            return True
    # Skip listicle / blog paths
    for kw in ["/blog/", "/news/", "/article/", "/review/", "/best-", "/top-", "/how-to"]:
        if kw in url_lower:
            return True
    return False


def _filter_competitors_with_groq(candidates: List[Dict], industry_context: str) -> List[Dict]:
    """
    Send SerpAPI candidate results to Groq and ask it to keep only
    real competitor brand/company websites. Returns filtered list.
    """
    if not candidates:
        return []

    groq_api_key = os.getenv("GROQ_API_KEY", "")
    if not groq_api_key:
        return candidates  # No Groq → pass through (avoid breaking pipeline)

    try:
        from groq import Groq
        from llm_failover import groq_chat_with_failover
        client = Groq(api_key=groq_api_key)

        items_text = "\n".join(
            f"{i+1}. Title: {c['name']} | URL: {c['url']}"
            for i, c in enumerate(candidates)
        )

        prompt = f"""You are a market research expert. The company we are researching is in the following industry:
"{industry_context}"

Below are search result titles and URLs. Your task is to identify ONLY the ones that are real COMPETITOR BRANDS or COMPANIES selling similar products/services in the same industry.

EXCLUDE:
- Software tools, SaaS platforms, ERPs
- Review/comparison/listicle sites (e.g. g2.com, capterra, emailvendorselection)
- News, blogs, Wikipedia, social media, health info sites
- Retailers/marketplaces (Amazon, Flipkart, IndiaMart)
- Industry associations or government pages

INCLUDE ONLY:
- Brand websites of companies that sell similar products
- Direct competitors operating in the same market

Search results:
{items_text}

Return ONLY a JSON object with key "keep" containing a list of the numbers (1-based) of results to keep.
Example: {{"keep": [1, 3, 5]}}
If none are valid competitors, return {{"keep": []}}"""

        resp, _used_model = groq_chat_with_failover(
            client,
            messages=[{"role": "user", "content": prompt}],
            primary_model="llama-3.3-70b-versatile",
            logger=logger,
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        parsed = json.loads(resp.choices[0].message.content)
        keep_indices = parsed.get("keep", [])
        filtered = [candidates[i - 1] for i in keep_indices if 1 <= i <= len(candidates)]
        logger.info(f"Groq competitor filter: {len(candidates)} → {len(filtered)} kept")
        return filtered
    except Exception as e:
        logger.warning(f"Groq competitor filter failed ({e}), using unfiltered results")
        return candidates


def run_keyword_extraction(customer_statement: str,
                           max_results: int = 10,
                           max_pages: int = 1,
                           max_competitors: int = 8) -> Dict[str, Any]:
    """
    Full keyword extraction pipeline:
    1. Extract industry + competitor search queries via Groq
    2. Search competitors via SerpAPI
    3. Fast-filter obvious non-brand URLs
    4. Groq-filter remaining results to keep only real competitors
    5. Crawl validated competitor sites
    6. Extract keywords from crawled content
    Returns dict with competitor keyword data.
    """
    from keywordExtraction import (
        extract_domains_with_groq,
        get_serpapi_results,
        extract_keywords_from_text,
    )
    from .webcrawler_adapter import run_webcrawler

    try:
        # Step 1: Generate industry-aware competitor search queries
        domains = extract_domains_with_groq(customer_statement)
        if not domains:
            return {"competitors": [], "error": "No domains extracted"}

        # Use the first query as industry context for filtering
        industry_context = domains[0] if domains else "unknown industry"

        all_competitor_data: List[Dict[str, Any]] = []
        seen_urls: set = set()

        # Step 2: Collect SerpAPI results across all queries
        raw_candidates: List[Dict] = []
        for d in domains:
            logger.info(f"Searching for competitors: {d}")
            serp_results = get_serpapi_results(d, max_results=max_results)

            for comp in serp_results:
                url = comp.get("url", "")
                if not url or url in seen_urls:
                    continue
                # Fast pre-filter: skip obvious non-brand URLs
                if _is_likely_non_competitor(url):
                    logger.debug(f"Pre-filter skipped: {url}")
                    continue
                seen_urls.add(url)
                raw_candidates.append(comp)

        logger.info(f"Candidates after fast-filter: {len(raw_candidates)}")

        # Step 3: Groq-powered validation — keep only real competitor brands
        validated = _filter_competitors_with_groq(raw_candidates, industry_context)

        # Step 4: Crawl validated competitors and extract keywords
        for comp in validated:
            url = comp.get("url", "")
            crawl_result = run_webcrawler(url, max_pages=max_pages)
            content = crawl_result.get("content", "")

            if content:
                kws = extract_keywords_from_text(content, max_keywords=50)
                all_competitor_data.append({
                    "domain": industry_context,
                    "competitor_name": comp["name"],
                    "url": url,
                    "short_keywords": kws.get("short_keywords", []),
                    "long_tail_keywords": kws.get("long_tail_keywords", []),
                    "content_length": len(content),
                })

            if len(all_competitor_data) >= max(1, max_competitors):
                break

        logger.info(f"Final competitors extracted: {len(all_competitor_data)}")
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
