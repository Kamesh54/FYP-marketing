"""
Agent Adapters — Direct Python calls to agent logic (no HTTP).
Wraps agent modules for use in LangGraph nodes.

Each adapter calls the agent's core logic directly, avoiding network overhead.
These functions replace HTTP calls to separate services (ports 8000-8010).

Functions called by langgraph_nodes.py:
  - extract_brand_from_url, extract_brand_signals
  - run_webcrawler, run_keyword_extraction, run_gap_analysis
  - run_reddit_research, generate_blog, generate_social, generate_image
  - run_critique, run_seo_analysis, run_deep_research
"""
import logging
import json
from typing import Dict, Any, Optional, List
from datetime import datetime
import uuid

logger = logging.getLogger("agent_adapters")

# ══════════════════════════════════════════════════════════════════════════════
# BRAND EXTRACTION ADAPTERS
# ══════════════════════════════════════════════════════════════════════════════

def extract_brand_from_url(brand_name: str, url: str) -> Dict[str, Any]:
    """
    Extract brand information from a website URL.
    Returns brand profile with industry, tone, audience, etc.
    """
    try:
        from brand_agent import extract_brand_info
        
        result = extract_brand_info(url, brand_name)
        return {
            "brand_name": result.get("brand_name", brand_name),
            "extracted_data": {
                "industry": result.get("industry", ""),
                "tone": result.get("tone", "professional"),
                "target_audience": result.get("target_audience", ""),
                "description": result.get("description", ""),
                "logo_url": result.get("logo_url", ""),
            },
            "colors": result.get("colors", []),
            "logo_url": result.get("logo_url", ""),
            "url": url,
        }
    except Exception as e:
        logger.error(f"Brand extraction from URL failed for {url}: {e}")
        return {
            "brand_name": brand_name,
            "error": str(e),
            "extracted_data": {
                "industry": "",
                "tone": "professional",
                "target_audience": "",
                "description": "",
            }
        }


def extract_brand_signals(brand_name: str, url: str, user_message: str) -> Dict[str, Any]:
    """
    Extract brand signals from user input (no URL required).
    Uses LLM to infer brand characteristics from text.
    """
    try:
        from intelligent_router import extract_brand_from_text
        
        result = extract_brand_from_text(brand_name, user_message) if extract_brand_from_text else {}
        return {
            "brand_name": result.get("brand_name", brand_name),
            "industry": result.get("industry", ""),
            "tone": result.get("tone", "professional"),
            "target_audience": result.get("target_audience", ""),
            "description": result.get("description", ""),
            "colors": result.get("colors", []),
            "unique_selling_points": result.get("unique_selling_points", []),
        }
    except Exception as e:
        logger.error(f"Brand signal extraction failed: {e}")
        return {
            "brand_name": brand_name,
            "error": str(e),
            "industry": "",
            "tone": "professional",
            "target_audience": "",
            "description": "",
        }


# ══════════════════════════════════════════════════════════════════════════════
# WEBCRAWLER ADAPTER
# ══════════════════════════════════════════════════════════════════════════════

def run_webcrawler(url: str, max_pages: int = 10, delay: float = 1.0) -> Dict[str, Any]:
    """
    Directly calls WebCrawler logic without HTTP.
    Returns extracted content and metadata.
    Replaces: requests.post(CRAWLER_BASE + "/crawl")
    """
    try:
        from webcrawler import WebCrawler
        
        crawler = WebCrawler(delay=delay, timeout=10, max_pages=max_pages)
        extracted_content = crawler.crawl(url) if hasattr(crawler, 'crawl') else ""
        
        return {
            "status": "completed",
            "url": url,
            "pages_count": len(crawler.visited_urls) if hasattr(crawler, 'visited_urls') else 0,
            "extracted_text": extracted_content,
            "content": extracted_content,
            "visited_urls": list(crawler.visited_urls) if hasattr(crawler, 'visited_urls') else [url],
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Crawl failed for {url}: {e}")
        return {
            "status": "failed",
            "error": str(e),
            "url": url,
            "pages_count": 0,
            "extracted_text": "",
            "content": "",
        }


# ══════════════════════════════════════════════════════════════════════════════
# KEYWORD EXTRACTION ADAPTER
# ══════════════════════════════════════════════════════════════════════════════

def run_keyword_extraction(
    query: str,
    max_results: int = 5,
    max_pages: int = 1
) -> Dict[str, Any]:
    """
    Directly calls keyword extraction logic.
    Returns SEO keywords with competitor data.
    Replaces: requests.post(KEYWORD_EXTRACTOR_BASE + "/extract-keywords")
    """
    try:
        from keywordExtraction import KeywordExtractor
        
        extractor = KeywordExtractor()
        keywords = extractor.extract_keywords(query, max_pages=max_pages) if hasattr(extractor, 'extract_keywords') else {}
        
        return {
            "status": "completed",
            "query": query,
            "competitors": keywords.get("competitors", []),
            "competitors_processed": len(keywords.get("competitors", [])),
            "keywords": keywords.get("keywords", []),
            "long_tail": keywords.get("long_tail", []),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Keyword extraction failed: {e}")
        return {
            "status": "failed",
            "error": str(e),
            "competitors": [],
            "competitors_processed": 0,
            "keywords": [],
        }


# ══════════════════════════════════════════════════════════════════════════════
# COMPETITOR GAP ANALYZER ADAPTER
# ══════════════════════════════════════════════════════════════════════════════

def run_gap_analysis(
    company_name: str,
    product_description: str,
    company_url: Optional[str] = None,
    max_competitors: int = 3
) -> Dict[str, Any]:
    """
    Directly calls competitor gap analysis.
    Returns gap analysis results with missing keywords.
    Replaces: requests.post(GAP_ANALYZER_BASE + "/analyze-keyword-gap")
    """
    try:
        from CompetitorGapAnalyzerAgent import CompetitorGapAnalyzer
        
        analyzer = CompetitorGapAnalyzer()
        gap_results = analyzer.analyze(
            company_name=company_name,
            product_description=product_description,
            company_url=company_url,
            max_competitors=max_competitors
        ) if hasattr(analyzer, 'analyze') else {}
        
        return {
            "status": "completed",
            "company_name": company_name,
            "gap_analysis": gap_results.get("gap_analysis", {}),
            "gaps": gap_results.get("gaps", []),
            "opportunities": gap_results.get("opportunities", []),
            "recommendations": gap_results.get("recommendations", []),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Gap analysis failed: {e}")
        return {
            "status": "failed",
            "error": str(e),
            "gap_analysis": {},
            "gaps": [],
        }


# ══════════════════════════════════════════════════════════════════════════════
# REDDIT RESEARCH ADAPTER
# ══════════════════════════════════════════════════════════════════════════════

def run_reddit_research(
    keywords: List[str],
    brand_name: str = "",
    max_subreddits: int = 3
) -> Dict[str, Any]:
    """
    Directly calls Reddit research.
    Returns community insights and sentiment data.
    """
    try:
        from reddit_agent import RedditAgent
        
        agent = RedditAgent()
        research = agent.research(
            keywords=keywords,
            brand_name=brand_name,
            max_subreddits=max_subreddits
        ) if hasattr(agent, 'research') else {}
        
        return {
            "status": "completed",
            "available": True,
            "keywords": keywords,
            "insights": research.get("insights", []),
            "sentiment": research.get("sentiment", []),
            "subreddits": research.get("subreddits", []),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.warning(f"Reddit research not available: {e}")
        return {
            "status": "unavailable",
            "available": False,
            "error": str(e),
            "insights": [],
            "timestamp": datetime.now().isoformat()
        }


# ══════════════════════════════════════════════════════════════════════════════
# BLOG CONTENT GENERATION ADAPTER
# ══════════════════════════════════════════════════════════════════════════════

def generate_blog(
    business_details: str,
    keywords: Optional[Dict[str, List[str]]] = None,
    gap_analysis: Optional[Dict[str, Any]] = None,
    reddit_insights: Optional[Dict[str, Any]] = None,
    brand_context: str = "",
    brand_info: Optional[Dict[str, Any]] = None,
    tone: str = "professional",
    word_count: int = 1500
) -> Dict[str, Any]:
    """
    Directly calls content generation for blog posts.
    Returns HTML blog post.
    Logs execution with brand context for prompt-log.
    Replaces: requests.post(CONTENT_AGENT_BASE + "/generate-blog")
    """
    try:
        from content_agent import ContentAgent
        
        agent = ContentAgent()
        content = agent.generate_blog(
            business_details=business_details,
            keywords=keywords,
            gap_analysis=gap_analysis,
            reddit_insights=reddit_insights,
            brand_context=brand_context,
            tone=tone,
            word_count=word_count
        ) if hasattr(agent, 'generate_blog') else {}
        
        # Log execution with brand context
        try:
            from database import log_prompt_execution
            log_prompt_execution(
                execution_id=f"exec_{uuid.uuid4().hex[:12]}",
                prompt_id=None,
                agent_name="content_agent",
                context_type="blog",
                brand_info=brand_info or {},
                performance_score=content.get('quality_score', 0.8),
                feedback=f"Generated blog post: {content.get('title', 'Untitled')}"
            )
        except Exception as e:
            logger.warning(f"Failed to log prompt execution: {e}")
        
        return {
            "status": "completed",
            "content": content.get("content", ""),
            "html": content.get("html", ""),
            "title": content.get("title", ""),
            "meta_description": content.get("meta_description", ""),
            "content_type": "blog",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Blog generation failed: {e}")
        return {
            "status": "failed",
            "error": str(e),
            "html": "<p>Blog generation failed. Please try again.</p>",
        }


# ══════════════════════════════════════════════════════════════════════════════
# SOCIAL CONTENT GENERATION ADAPTER
# ══════════════════════════════════════════════════════════════════════════════

def generate_social(
    keywords: Optional[Dict[str, List[str]]] = None,
    gap_analysis: Optional[Dict[str, Any]] = None,
    platforms: Optional[List[str]] = None,
    brand_name: str = "",
    brand_info: Optional[Dict[str, Any]] = None,
    brand_context: str = "",
    tone: str = "professional",
    topic: str = ""
) -> Dict[str, Any]:
    """
    Directly calls content generation for social posts.
    Returns multi-platform posts with hashtags and imagery suggestions.
    Logs execution with brand context for prompt-log.
    """
    try:
        from content_agent import ContentAgent
        
        agent = ContentAgent()
        content = agent.generate_social(
            keywords=keywords,
            gap_analysis=gap_analysis,
            platforms=platforms or ["twitter", "instagram"],
            brand_name=brand_name,
            brand_context=brand_context,
            tone=tone,
            topic=topic
        ) if hasattr(agent, 'generate_social') else {}
        
        # Log execution with brand context
        try:
            from database import log_prompt_execution
            log_prompt_execution(
                execution_id=f"exec_{uuid.uuid4().hex[:12]}",
                prompt_id=None,
                agent_name="content_agent",
                context_type="social_post",
                brand_info=brand_info or {},
                performance_score=content.get('quality_score', 0.8),
                feedback=f"Generated social posts for {len(content.get('posts', {}))} platforms"
            )
        except Exception as e:
            logger.warning(f"Failed to log prompt execution: {e}")
        
        return {
            "status": "completed",
            "posts": content.get("posts", {}),
            "image_prompts": content.get("image_prompts", []),
            "hashtags": content.get("hashtags", []),
            "content_type": "social",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Social generation failed: {e}")
        return {
            "status": "failed",
            "error": str(e),
            "posts": {},
            "image_prompts": [],
        }


# ══════════════════════════════════════════════════════════════════════════════
# IMAGE GENERATION ADAPTER
# ══════════════════════════════════════════════════════════════════════════════

def generate_image(
    prompt: str,
    brand_name: str = "",
    style: str = "photorealistic",
    negative_prompt: str = "",
    duration: Optional[int] = None
) -> Dict[str, Any]:
    """
    Directly calls image generation via Runway ML.
    Returns image URL or local path.
    """
    try:
        from image_agent import ImageGenerator
        
        generator = ImageGenerator()
        result = generator.generate(
            prompt=prompt,
            brand_name=brand_name,
            style=style,
            negative_prompt=negative_prompt,
            duration=duration
        ) if hasattr(generator, 'generate') else {}
        
        return {
            "status": "completed",
            "url": result.get("url", ""),
            "local_path": result.get("local_path", ""),
            "runway_id": result.get("runway_id", ""),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Image generation failed: {e}")
        return {
            "status": "failed",
            "error": str(e),
            "url": "",
            "local_path": "",
        }


# ══════════════════════════════════════════════════════════════════════════════
# CONTENT CRITIC / REVIEW ADAPTER
# ══════════════════════════════════════════════════════════════════════════════

def run_critique(
    content: str,
    content_type: str = "blog",
    brand_context: str = ""
) -> Dict[str, Any]:
    """
    Directly calls content critic agent.
    Returns critique scores and quality feedback.
    """
    try:
        from critic_agent import CriticAgent
        
        agent = CriticAgent()
        critique = agent.critique(
            content=content,
            content_type=content_type,
            brand_context=brand_context
        ) if hasattr(agent, 'critique') else {}
        
        return {
            "status": "completed",
            "quality_score": critique.get("quality_score", 0.7),
            "brand_alignment_score": critique.get("brand_alignment_score", 0.7),
            "intent_score": critique.get("intent_score", 0.7),
            "overall_score": critique.get("overall_score", 0.7),
            "feedback": critique.get("feedback", "Good content"),
            "passed": critique.get("passed", True),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Content review failed: {e}")
        return {
            "status": "failed",
            "error": str(e),
            "quality_score": 0.5,
            "passed": False,
        }


# ══════════════════════════════════════════════════════════════════════════════
# SEO ANALYSIS ADAPTER
# ══════════════════════════════════════════════════════════════════════════════

def run_seo_analysis(
    url: str,
    crawled_content: str = "",
    keywords: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Fast SEO analysis for chat integration.
    Returns quick results in 20-30 seconds instead of full 90+ second analysis.
    Uses optimized lightweight version for better chat experience.
    """
    try:
        from fast_seo_analysis import run_fast_seo_analysis
        
        # Use the fast version for immediate results in chat
        result = run_fast_seo_analysis(url)
        
        return {
            "status": result.get("status", "completed"),
            "url": url,
            "seo_score": result.get("seo_score", 0.0),
            "recommendations": result.get("recommendations", []),
            "issues": result.get("issues", []),
            "opportunities": result.get("opportunities", []),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"SEO analysis failed: {e}")
        return {
            "status": "failed",
            "error": str(e),
            "seo_score": 0.0,
            "recommendations": [],
        }


# ══════════════════════════════════════════════════════════════════════════════
# DEEP RESEARCH ADAPTER
# ══════════════════════════════════════════════════════════════════════════════

def run_deep_research(
    topic: str,
    depth: str = "standard"
) -> Dict[str, Any]:
    """
    Directly calls deep research agent.
    Returns detailed research findings and sources.
    """
    try:
        from research_agent import ResearchAgent
        
        agent = ResearchAgent()
        research = agent.research(
            topic=topic,
            depth=depth
        ) if hasattr(agent, 'research') else {}
        
        return {
            "status": "completed",
            "topic": topic,
            "depth": depth,
            "findings": research.get("findings", []),
            "summary": research.get("summary", ""),
            "sources": research.get("sources", []),
            "key_insights": research.get("key_insights", []),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Deep research failed: {e}")
        return {
            "status": "failed",
            "error": str(e),
            "findings": [],
            "sources": [],
        }
