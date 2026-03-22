"""
LangGraph Configuration — LangSmith tracing, checkpointer, and graph settings.

LangSmith auto-tracing is activated by these environment variables (already in .env):
  LANGCHAIN_TRACING_V2=true
  LANGCHAIN_API_KEY=<your key>
  LANGCHAIN_PROJECT=<your project>  (defaults to "default")

This module exposes helpers for additional runtime configuration.
"""
import os
import logging

logger = logging.getLogger("langgraph.config")


def ensure_langsmith_env():
    """
    Verify LangSmith environment variables are set.
    Called once at startup to log tracing status.
    """
    tracing = os.getenv("LANGCHAIN_TRACING_V2", "").lower() in ("true", "1", "yes")
    api_key = os.getenv("LANGCHAIN_API_KEY") or os.getenv("LANGSMITH_API_KEY")
    project = os.getenv("LANGCHAIN_PROJECT") or os.getenv("LANGSMITH_PROJECT", "default")

    if tracing and api_key:
        logger.info(f"LangSmith tracing ENABLED — project: {project}")
        return True
    elif tracing and not api_key:
        logger.warning("LANGCHAIN_TRACING_V2=true but LANGCHAIN_API_KEY is missing — tracing disabled")
        return False
    else:
        logger.info("LangSmith tracing DISABLED (set LANGCHAIN_TRACING_V2=true to enable)")
        return False


def get_graph_run_config(session_id: str, user_id: int,
                         brand: str = "", extra_tags: list = None):
    """
    Build a LangGraph run config dict with LangSmith metadata.
    Pass this as `config=` to graph.ainvoke().
    """
    config = {
        "metadata": {
            "session_id": session_id,
            "user_id": user_id,
            "brand": brand or "none",
        },
        "tags": ["marketing_graph", f"user_{user_id}"] + (extra_tags or []),
    }

    project = os.getenv("LANGCHAIN_PROJECT") or os.getenv("LANGSMITH_PROJECT")
    if project:
        config["run_name"] = f"chat_{session_id[:8]}"

    return config


# Auto-check on import
_tracing_active = ensure_langsmith_env()
