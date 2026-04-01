"""
LangGraph Graph — builds the StateGraph with routing and conditional edges.
This is the central orchestration engine replacing HTTP microservice calls.

Graph structure:
  START → router → (conditional routing by intent) → ... → response_builder → END

LangSmith auto-traces every node when LANGCHAIN_TRACING_V2=true.
"""
import os
import logging
from typing import Dict, Any, Optional

from langgraph.graph import StateGraph, START, END
from langgraph_state import MarketingState
from langgraph_nodes import (
    router_node,
    chat_node,
    brand_setup_node,
    crawl_node,
    keyword_node,
    gap_analysis_node,
    reddit_node,
    blog_content_node,
    social_content_node,
    image_node,
    critic_node,
    seo_node,
    campaign_node,
    research_node,
    response_builder_node,
)

logger = logging.getLogger("langgraph.graph")

# ── Singleton graph instance ──────────────────────────────────────────────────
_compiled_graph = None


def route_by_intent(state: MarketingState) -> str:
    """
    Conditional edge function: routes to the appropriate starting node
    based on the classified intent from the router node.

    This mapping mirrors every intent defined in intelligent_router.INTENTS
    so that no classified intent silently falls through to general_chat.
    """
    intent = state.get("intent", "general_chat")

    intent_to_node = {
        # ── Core intents from intelligent_router.INTENTS ──────────────
        "general_chat": "chat",
        "greeting": "chat",
        "brand_setup": "brand_setup",
        "seo_analysis": "seo_crawl",
        "blog_generation": "blog_keywords",
        "social_post": "social_keywords",
        "social_media_post": "social_keywords",
        "competitor_research": "research",
        "deep_research": "research",
        "campaign_planning": "campaign",
        "campaign_post": "campaign",
        "image_generation": "image_gen",
        "content_generation": "blog_keywords",
        "critic_review": "chat",           # critique requests handled conversationally
        "daily_schedule": "campaign",       # scheduling routed to campaign planner
        "metrics_report": "chat",           # metrics answered conversationally
    }

    target = intent_to_node.get(intent, "chat")
    logger.info(f"Routing intent '{intent}' → node '{target}'")
    return target


def build_marketing_graph() -> StateGraph:
    """
    Build and return the compiled LangGraph StateGraph for the
    marketing platform orchestration.
    """
    builder = StateGraph(MarketingState)

    # ── Add all nodes ─────────────────────────────────────────────────────────
    builder.add_node("router", router_node)
    builder.add_node("chat", chat_node)
    builder.add_node("brand_setup", brand_setup_node)

    # SEO workflow nodes
    builder.add_node("seo_crawl", crawl_node)
    builder.add_node("seo_analyze", seo_node)

    # Blog workflow nodes
    builder.add_node("blog_keywords", keyword_node)
    builder.add_node("blog_gap", gap_analysis_node)
    builder.add_node("blog_reddit", reddit_node)
    builder.add_node("blog_generate", blog_content_node)
    builder.add_node("blog_critic", critic_node)

    # Social workflow nodes
    builder.add_node("social_keywords", keyword_node)
    builder.add_node("social_gap", gap_analysis_node)
    builder.add_node("social_generate", social_content_node)
    builder.add_node("social_image", image_node)
    builder.add_node("social_critic", critic_node)

    # Standalone nodes
    builder.add_node("campaign", campaign_node)
    builder.add_node("research", research_node)
    builder.add_node("image_gen", image_node)
    builder.add_node("response_builder", response_builder_node)

    # ── Entry edge ────────────────────────────────────────────────────────────
    builder.add_edge(START, "router")

    # ── Conditional routing from router ───────────────────────────────────────
    builder.add_conditional_edges(
        "router",
        route_by_intent,
        {
            "chat": "chat",
            "brand_setup": "brand_setup",
            "seo_crawl": "seo_crawl",
            "blog_keywords": "blog_keywords",
            "social_keywords": "social_keywords",
            "campaign": "campaign",
            "research": "research",
            "image_gen": "image_gen",
        },
    )

    # ── SEO workflow: crawl → analyze → done ──────────────────────────────────
    builder.add_edge("seo_crawl", "seo_analyze")
    builder.add_edge("seo_analyze", "response_builder")

    # ── Blog workflow: keywords → gap → reddit → generate → critic → done ─────
    builder.add_edge("blog_keywords", "blog_gap")
    builder.add_edge("blog_gap", "blog_reddit")
    builder.add_edge("blog_reddit", "blog_generate")
    builder.add_edge("blog_generate", "blog_critic")
    builder.add_edge("blog_critic", "response_builder")

    # ── Social workflow: keywords → gap → generate → image → critic → done ────
    builder.add_edge("social_keywords", "social_gap")
    builder.add_edge("social_gap", "social_generate")
    builder.add_edge("social_generate", "social_image")
    builder.add_edge("social_image", "social_critic")
    builder.add_edge("social_critic", "response_builder")

    # ── Terminal edges for simple workflows ────────────────────────────────────
    builder.add_edge("chat", "response_builder")
    builder.add_edge("brand_setup", "response_builder")
    builder.add_edge("campaign", "response_builder")
    builder.add_edge("research", "response_builder")
    builder.add_edge("image_gen", "response_builder")

    # ── Final edge ────────────────────────────────────────────────────────────
    builder.add_edge("response_builder", END)

    # ── Compile the graph ─────────────────────────────────────────────────────
    graph = builder.compile()

    logger.info("Marketing LangGraph compiled successfully")
    return graph


def get_marketing_graph():
    """
    Return the singleton compiled graph instance.
    Thread-safe: LangGraph compiled graphs are immutable and shareable.
    """
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_marketing_graph()
    return _compiled_graph


async def run_marketing_graph(
    user_message: str,
    session_id: str,
    user_id: int,
    active_brand: Optional[str] = None,
    conversation_history: Optional[list] = None,
    brand_info: Optional[Dict[str, Any]] = None,
    brand_context_summary: str = "",
    trace_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Convenience function to invoke the marketing graph with a user message.
    Called from orchestrator.py chat_endpoint.

    Returns the final state dict containing response_text and all intermediate results.
    """
    graph = get_marketing_graph()

    initial_state: MarketingState = {
        "user_message": user_message,
        "session_id": session_id,
        "user_id": user_id,
        "active_brand": active_brand or "",
        "conversation_history": conversation_history or [],
        "brand_info": brand_info,
        "brand_context_summary": brand_context_summary,
        "trace_id": trace_id,  # For live execution visualization
        "steps_completed": [],
        "errors": [],
        "clarification_needed": False,
    }

    # Configure LangSmith metadata for this invocation
    config = {
        "metadata": {
            "session_id": session_id,
            "user_id": user_id,
            "brand": active_brand or "none",
        },
        "tags": ["marketing_graph", f"user_{user_id}"],
    }

    # If LANGSMITH_PROJECT is set, include run_name for better dashboard UX
    project = os.getenv("LANGSMITH_PROJECT")
    if project:
        config["run_name"] = f"chat_{session_id[:8]}"

    result = await graph.ainvoke(initial_state, config=config)

    logger.info(
        f"Graph completed: intent={result.get('intent', '?')}, "
        f"steps={result.get('steps_completed', [])}"
    )

    return result
