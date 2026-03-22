"""
LangGraph State Definition
Shared TypedDict state that flows through all graph nodes.
"""
from typing import TypedDict, Optional, List, Dict, Any, Annotated
from operator import add


def _merge_dict(left: Optional[Dict], right: Optional[Dict]) -> Optional[Dict]:
    """Reducer: merge two dicts, right overrides left."""
    if left is None:
        return right
    if right is None:
        return left
    return {**left, **right}


class MarketingState(TypedDict, total=False):
    """
    Central state shared across all LangGraph nodes.
    Fields are grouped by purpose.
    """
    # ── User Input ────────────────────────────────────────────────────────────
    user_message: str
    session_id: str
    user_id: int
    active_brand: Optional[str]
    conversation_history: List[Dict[str, Any]]

    # ── Router Output ─────────────────────────────────────────────────────────
    intent: str
    confidence: float
    extracted_params: Dict[str, Any]
    workflow_plan: Optional[Dict[str, Any]]

    # ── Brand Context ─────────────────────────────────────────────────────────
    brand_info: Optional[Dict[str, Any]]
    brand_context_summary: str

    # ── Agent Outputs (populated by individual nodes) ─────────────────────────
    crawled_data: Optional[Dict[str, Any]]
    keywords_data: Optional[Dict[str, Any]]
    gap_analysis: Optional[Dict[str, Any]]
    reddit_insights: Optional[Dict[str, Any]]
    blog_result: Optional[Dict[str, Any]]
    social_data: Optional[Dict[str, Any]]
    image_result: Optional[Dict[str, Any]]
    seo_result: Optional[Dict[str, Any]]
    critic_result: Optional[Dict[str, Any]]
    research_result: Optional[Dict[str, Any]]
    campaign_result: Optional[Dict[str, Any]]
    brand_extraction_result: Optional[Dict[str, Any]]

    # ── Workflow Metadata ─────────────────────────────────────────────────────
    mabo_state: Optional[Dict[str, Any]]
    current_step: str
    steps_completed: List[str]
    errors: List[str]

    # ── Final Output ──────────────────────────────────────────────────────────
    response_text: str
    response_options: Optional[List[Dict[str, Any]]]
    response_data: Optional[Dict[str, Any]]
    content_preview_id: Optional[str]
    clarification_needed: bool
    clarification_request: Optional[Dict[str, Any]]
