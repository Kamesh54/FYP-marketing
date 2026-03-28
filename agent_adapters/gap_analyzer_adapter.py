"""
Gap Analyzer Adapter — calls GapAnalyzer class directly (no HTTP).
Replaces internal HTTP webcrawler/keyword calls with adapter equivalents.
"""
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("adapter.gap_analyzer")


def run_gap_analysis(company_name: str,
                     product_description: str,
                     company_url: Optional[str] = None,
                     max_competitors: int = 3,
                     max_pages: int = 1) -> Dict[str, Any]:
    """
    Perform full keyword gap analysis:
    1. Crawl company site (or use product_description)
    2. Extract company keywords
    3. Extract competitor keywords
    4. Perform Groq-powered gap analysis
    Returns structured gap analysis result.
    """
    from CompetitorGapAnalyzerAgent import GapAnalyzer
    from .webcrawler_adapter import run_webcrawler
    from .keyword_adapter import run_keyword_extraction

    analyzer = GapAnalyzer()

    try:
        # Step 1: Get company content
        if company_url:
            crawl_result = run_webcrawler(company_url, max_pages=max_pages)
            company_content = crawl_result.get("content", "")
        else:
            company_content = product_description

        # Step 2: Extract company keywords (local processing)
        company_keywords = analyzer.extract_company_keywords(company_content)

        # Step 3: Extract competitor keywords
        competitor_result = run_keyword_extraction(
            f"{company_name} competitors and alternatives in the same market.",
            max_results=max_competitors,
            max_pages=1,
        )
        competitor_data = competitor_result.get("competitors", [])

        # Step 4: Perform gap analysis via Groq
        gap_analysis = analyzer.perform_gap_analysis(
            company_keywords, competitor_data, product_description
        )

        results = {
            "company_info": {
                "name": company_name,
                "url": company_url,
                "product_description": product_description,
            },
            "company_keywords": {
                "short_keywords": company_keywords.get("short_keywords", []),
                "long_tail_keywords": company_keywords.get("long_tail_keywords", []),
            },
            "competitor_analysis": {
                "competitors_analyzed": len(competitor_data),
                "competitor_details": [
                    {
                        "name": comp.get("competitor_name", ""),
                        "url": comp.get("url", ""),
                        "short_keywords_count": len(comp.get("short_keywords", [])),
                        "long_tail_keywords_count": len(comp.get("long_tail_keywords", [])),
                    }
                    for comp in competitor_data
                ],
            },
            "gap_analysis": gap_analysis,
        }

        logger.info(f"Gap analysis completed for {company_name}")
        return results

    except Exception as e:
        logger.error(f"Gap analyzer adapter failed: {e}")
        return {"error": str(e), "company_info": {"name": company_name}}
