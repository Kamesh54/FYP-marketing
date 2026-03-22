"""
Agent Adapters Package
Converts HTTP-based microservice agents into directly-callable Python functions
for use as LangGraph nodes. Each adapter imports the core logic from the
original agent file (bypassing FastAPI endpoint/job-polling boilerplate).
"""

from .webcrawler_adapter import run_webcrawler
from .keyword_adapter import run_keyword_extraction
from .gap_analyzer_adapter import run_gap_analysis
from .content_adapter import generate_blog, generate_social
from .image_adapter import generate_image
from .brand_adapter import extract_brand_from_url, extract_brand_signals
from .critic_adapter import run_critique
from .campaign_adapter import generate_campaign_post, schedule_campaign
from .research_adapter import run_deep_research
from .seo_adapter import run_seo_analysis
from .reddit_adapter import run_reddit_research

__all__ = [
    "run_webcrawler",
    "run_keyword_extraction",
    "run_gap_analysis",
    "generate_blog",
    "generate_social",
    "generate_image",
    "extract_brand_from_url",
    "extract_brand_signals",
    "run_critique",
    "generate_campaign_post",
    "schedule_campaign",
    "run_deep_research",
    "run_seo_analysis",
    "run_reddit_research",
]
