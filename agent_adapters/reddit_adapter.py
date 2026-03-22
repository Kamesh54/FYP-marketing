"""
Reddit Agent Adapter — calls Reddit research pipeline directly (no HTTP).
"""
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger("adapter.reddit")


def run_reddit_research(keywords: List[str],
                        brand_name: str = "",
                        max_subreddits: int = 3,
                        posts_per_sub: int = 8) -> Dict[str, Any]:
    """
    Full Reddit research pipeline:
    1. Find top subreddits for given keywords
    2. Fetch hot/trending posts from each
    3. Synthesise insights via Groq LLM
    Returns structured research context for content generation.
    """
    from reddit_agent import (
        find_top_subreddits,
        fetch_trending_posts,
        synthesize_reddit_research,
    )

    try:
        logger.info(f"Reddit research for keywords={keywords[:4]}, brand={brand_name}")

        # Step 1: find relevant subreddits
        try:
            subreddits = find_top_subreddits(keywords, max_results=max_subreddits)
        except Exception as e:
            logger.warning(f"Subreddit discovery failed: {e}")
            subreddits = []

        if not subreddits:
            return {"available": False, "subreddits": [], "insights": {}}

        # Step 2: fetch trending posts
        subreddits_with_posts: List[Dict[str, Any]] = []
        for sub in subreddits:
            name = sub.get("name")
            if not name:
                continue
            posts = fetch_trending_posts(name, sort="hot", limit=posts_per_sub)
            if posts:
                subreddits_with_posts.append({
                    "subreddit": name,
                    "subscribers": sub.get("subscribers", 0),
                    "posts": posts,
                })

        if not subreddits_with_posts:
            return {"available": False, "subreddits": [], "insights": {}}

        # Step 3: synthesise with Groq
        insights = synthesize_reddit_research(
            subreddits_with_posts, brand_name, keywords
        )

        return {
            "available": insights.get("available", False),
            "subreddits": [s["subreddit"] for s in subreddits_with_posts],
            "post_count": sum(len(s["posts"]) for s in subreddits_with_posts),
            "insights": insights,
            # Flatten key insights for easy access
            "trending_topics": insights.get("trending_topics", []),
            "community_language": insights.get("community_language", []),
            "content_angles": insights.get("content_angles", []),
            "community_pain_points": insights.get("community_pain_points", []),
        }

    except Exception as e:
        logger.error(f"Reddit research adapter failed: {e}")
        return {"available": False, "error": str(e)}
