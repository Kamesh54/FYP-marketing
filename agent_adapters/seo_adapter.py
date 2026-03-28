"""
SEO Agent Adapter — calls SEO analysis functions directly (no HTTP).
"""
import logging
from typing import Dict, Any

logger = logging.getLogger("adapter.seo")


def run_seo_analysis(url: str) -> Dict[str, Any]:
    """
    Perform comprehensive SEO analysis on a URL.
    Returns dict with scores by category, recommendations, and overall score.
    """
    from seo_agent import (
        crawl_page,
        analyze_onpage,
        analyze_links,
        analyze_performance,
        analyze_usability,
        analyze_social,
        analyze_local,
        analyze_technical,
        generate_recommendations,
        WEIGHTS,
    )

    try:
        # Crawl the page
        data = crawl_page(url)
        soup = data["soup"]

        # Run all analyses
        onpage = analyze_onpage(soup)
        links = analyze_links(soup, data["final_url"])
        performance = analyze_performance(data, soup)
        usability = analyze_usability(soup, data["final_url"])
        social = analyze_social(soup)
        local_seo = analyze_local(soup)
        technical = analyze_technical(data["final_url"])

        # Calculate overall score
        overall_score = round(
            onpage["score"] * WEIGHTS["onpage"]
            + links["score"] * WEIGHTS["links"]
            + performance["score"] * WEIGHTS["performance"]
            + usability["score"] * WEIGHTS["usability"]
            + social["score"] * WEIGHTS["social"]
            + local_seo["score"] * WEIGHTS["local"]
            + technical["score"] * WEIGHTS["technical"],
            2,
        )

        analyses = {
            "onpage": onpage,
            "links": links,
            "performance": performance,
            "usability": usability,
            "social": social,
            "local": local_seo,
            "technical": technical,
            "raw_soup": soup,
        }

        recommendations = generate_recommendations(analyses)

        # Remove non-serializable soup from result
        result = {
            "url": url,
            "final_url": data["final_url"],
            "overall_score": overall_score,
            "category_scores": {
                "content_keywords": onpage["score"],
                "links_structure": links["score"],
                "speed_performance": performance["score"],
                "user_experience": usability["score"],
                "social_media": social["score"],
                "local_business": local_seo["score"],
                "technical_setup": technical["score"],
            },
            "details": {
                "onpage": {k: v for k, v in onpage.items() if k != "components"},
                "links": {k: v for k, v in links.items() if k != "components"},
                "performance": {k: v for k, v in performance.items() if k != "components"},
                "usability": {k: v for k, v in usability.items() if k != "components"},
                "social": {k: v for k, v in social.items() if k != "components"},
                "local": {k: v for k, v in local_seo.items() if k != "components"},
                "technical": {k: v for k, v in technical.items() if k != "components"},
            },
            "recommendations": recommendations,
            "word_count": onpage.get("word_count", 0),
            "page_title": onpage.get("title", ""),
        }

        logger.info(f"SEO analysis completed for {url}: score={overall_score}")
        return result

    except Exception as e:
        logger.error(f"SEO analysis adapter failed for {url}: {e}")
        return {
            "url": url,
            "overall_score": 0,
            "error": str(e),
            "category_scores": {},
            "recommendations": [],
        }
