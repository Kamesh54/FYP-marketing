"""
Content Agent Adapter — calls content generation directly (no HTTP).
Wraps blog and social post generation from content_agent.py.
"""
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import logging
import json
from typing import Dict, Any, Optional, List
from content_agent import safe_groq_chat, build_blog_prompt, format_kg_context_for_prompt, get_brand_knowledge_context, _clean_markdown_wrapped_html  # type: ignore


logger = logging.getLogger("adapter.content")


def generate_blog(business_details: str,
                  keywords: Optional[Dict] = None,
                  gap_analysis: Optional[Dict] = None,
                  reddit_insights: Optional[Dict] = None,
                  brand_context: str = "",
                  tone: str = "professional",
                  word_count: int = 1500,
                  blog_style: str = "informational") -> Dict[str, Any]:
    """
    Generate an HTML blog article using the content agent's Groq-based generation.
    Returns dict with 'html' (str), 'title' (str), 'meta_description' (str).
    """
   
    try:
        # Pull brand memory from knowledge graph
        kg_context = ""
        if brand_context:
            try:
                # Find brand name from context or business details
                import re
                brand_match = re.search(r'(?:brand[_\s]*name|business[_\s]*name|company)[:\s]+([\w\s&\'\-\.]+)', business_details, re.IGNORECASE)
                brand_name_hint = brand_match.group(1).strip()[:60] if brand_match else brand_context[:50]
                
                raw_ctx = get_brand_knowledge_context(brand_name_hint)
                kg_context = format_kg_context_for_prompt(raw_ctx)
            except Exception as kg_err:
                logger.warning(f"KG context fetch failed for blog: {kg_err}")

        # Re-use the high-quality, fully-featured prompt from the original agent
        prompt = build_blog_prompt(
            business_details=business_details + (f"\nBrand context: {brand_context}" if brand_context else ""),
            keywords_obj=keywords or {},
            crawled_content=None, # LangGraph handles crawling earlier, but blog prompt accepts it
            gap_analysis=gap_analysis,
            target_tone=tone,
            blog_length=str(word_count),
            variant_label=blog_style, # 'blog_style' is repurposed to pass variant info (e.g. Option A/B)
            kg_context=kg_context
        )

        result = safe_groq_chat(prompt, strict_json=False)

        if isinstance(result, dict):
            # The original content_agent.py prompt returns {"html_content": "<html...>"}
            # We need to map this to "html" for compatibility with LangGraph and the UI.
            raw_html = result.get("html_content", "") or result.get("html", "") or result.get("raw_text", "")
            
            # Clean markdown-wrapped responses
            raw_html = _clean_markdown_wrapped_html(raw_html)
            
            return {
                "html": raw_html,
                "title": result.get("title", "Generated Blog"),
                "meta_description": result.get("meta_description", "")
            }
        return {"html": str(result), "title": "", "meta_description": ""}

    except Exception as e:
        logger.error(f"Blog generation adapter failed: {e}")
        return {"html": "", "title": "", "meta_description": "", "error": str(e)}


def generate_social(keywords: Optional[Dict] = None,
                    gap_analysis: Optional[Dict] = None,
                    platforms: Optional[List[str]] = None,
                    brand_name: str = "",
                    brand_context: str = "",
                    tone: str = "professional",
                    topic: str = "") -> Dict[str, Any]:
    """
    Generate social media posts for specified platforms.
    Returns dict with platform-specific post content.
    """
    from content_agent import safe_groq_chat, build_social_prompt, format_kg_context_for_prompt, get_brand_knowledge_context

    if platforms is None:
        platforms = ["linkedin", "x", "instagram"]

    def _build_fallback_posts() -> Dict[str, Any]:
        brand = brand_name or (brand_context[:40].strip() if brand_context else "Our brand")
        subject = topic.strip() or "our latest update"
        posts: Dict[str, Any] = {}
        for platform in platforms:
            p = (platform or "social").lower()
            copy = f"{brand}: {subject}. Discover how we can help you improve results today."
            hashtags = ["#marketing", "#growth"]
            if p in ("twitter", "x"):
                copy = f"{brand}: {subject}. Improve results today."
                hashtags = ["#growth", "#marketing"]
            elif p == "instagram":
                copy = f"{brand} - {subject}\n\nBuilt for better outcomes."
                hashtags = ["#instagram", "#business", "#marketing"]
            elif p == "linkedin":
                copy = f"{brand}: {subject}. We help teams improve marketing performance with practical execution."
                hashtags = ["#linkedin", "#marketing", "#business"]

            posts[p] = {
                "copy": copy,
                "hashtags": hashtags,
            }

        return {
            "posts": posts,
            "image_prompts": [f"Brand marketing visual for {brand_name or 'business'}"],
            "fallback": True,
            "fallback_reason": "groq_unavailable_or_rate_limited",
        }

    try:
        # Pull brand memory from knowledge graph
        kg_context = ""
        brand_name_hint = brand_context[:50] if brand_context else ""
        if brand_name_hint:
            try:
                raw_ctx = get_brand_knowledge_context(brand_name_hint)
                kg_context = format_kg_context_for_prompt(raw_ctx)
            except Exception as kg_err:
                logger.warning(f"KG context fetch failed for social: {kg_err}")

        # Use the fully-featured social prompt from the original agent
        prompt = build_social_prompt(
            keywords_obj=keywords or {},
            platforms=platforms,
            tone=tone,
            hashtags=[],
            brand_name=brand_name if brand_name else (brand_name_hint if brand_name_hint else None),
            image_style="Photorealistic, high quality",
            user_request=topic,
            kg_context=kg_context
        )

        result = safe_groq_chat(prompt)

        if isinstance(result, dict):
            if result.get("error") or not result.get("posts"):
                logger.warning("Using fallback social post generation due to Groq error or missing posts")
                return _build_fallback_posts()
            return result
        return {"error": "Unexpected response format", "raw": str(result)}

    except Exception as e:
        logger.error(f"Social content generation adapter failed: {e}")
        return _build_fallback_posts()
