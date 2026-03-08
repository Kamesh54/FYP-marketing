"""
LangSmith tracing utilities for the multi-agent content marketing platform.

Usage:
    from langsmith_tracer import trace_llm, trace_workflow, trace_agent, record_feedback

Requires LANGSMITH_API_KEY and LANGCHAIN_PROJECT in .env (or environment).
If keys are absent, all decorators are no-ops and feedback calls are silent.
"""

import os
import logging
import functools
import time
from typing import Any, Callable, Dict, List, Optional, TypeVar

logger = logging.getLogger(__name__)

# ── Availability check ────────────────────────────────────────────────────────
try:
    from langsmith import Client as _LSClient, traceable as _traceable, RunTree
    from langsmith.run_helpers import get_current_run_tree
    _LANGSMITH_AVAILABLE = True
except ImportError:
    _LANGSMITH_AVAILABLE = False
    _traceable = None

_ENABLED = (
    _LANGSMITH_AVAILABLE
    and bool(os.getenv("LANGSMITH_API_KEY"))
)

# ── Lazy client ───────────────────────────────────────────────────────────────
_client: Optional[Any] = None

def get_client() -> Optional[Any]:
    global _client
    if not _ENABLED:
        return None
    if _client is None:
        try:
            _client = _LSClient()
        except Exception as e:
            logger.warning(f"LangSmith client init failed: {e}")
    return _client


# ── Decorator factories ───────────────────────────────────────────────────────

F = TypeVar("F", bound=Callable)


def _noop(fn: F) -> F:
    """Return the function unchanged (no-op wrapper)."""
    return fn


def trace_llm(name: Optional[str] = None, tags: Optional[List[str]] = None) -> Callable[[F], F]:
    """
    Decorator that traces a function as an LLM call in LangSmith.

    @trace_llm(name="generate_blog", tags=["content_agent"])
    def my_llm_call(prompt, model):
        ...
    """
    if not _ENABLED:
        return _noop  # type: ignore

    def decorator(fn: F) -> F:
        run_name = name or fn.__name__
        traced = _traceable(run_type="llm", name=run_name, tags=tags or [])(fn)

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            return traced(*args, **kwargs)
        return wrapper  # type: ignore

    return decorator


def trace_workflow(name: Optional[str] = None, tags: Optional[List[str]] = None) -> Callable[[F], F]:
    """
    Decorator that traces an entire agent workflow / chain.

    @trace_workflow(name="full_content_pipeline", tags=["orchestrator"])
    async def run_pipeline(...):
        ...
    """
    if not _ENABLED:
        return _noop  # type: ignore

    def decorator(fn: F) -> F:
        run_name = name or fn.__name__
        traced = _traceable(run_type="chain", name=run_name, tags=tags or [])(fn)

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            return traced(*args, **kwargs)
        return wrapper  # type: ignore

    return decorator


def trace_agent(name: Optional[str] = None, tags: Optional[List[str]] = None) -> Callable[[F], F]:
    """
    Decorator that traces a single agent invocation.
    """
    if not _ENABLED:
        return _noop  # type: ignore

    def decorator(fn: F) -> F:
        run_name = name or fn.__name__
        traced = _traceable(run_type="tool", name=run_name, tags=tags or [])(fn)

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            return traced(*args, **kwargs)
        return wrapper  # type: ignore

    return decorator


# ── Feedback helpers ──────────────────────────────────────────────────────────

def record_feedback(run_id: str, key: str, score: float, comment: Optional[str] = None):
    """
    Attach a numeric feedback score to a LangSmith run.

    Args:
        run_id: UUID of the LangSmith run (returned in run metadata or from get_current_run_id).
        key: feedback dimension, e.g. "quality", "brand_alignment", "intent_match"
        score: 0.0–1.0 float
        comment: optional human-readable note
    """
    client = get_client()
    if not client:
        return
    try:
        client.create_feedback(
            run_id=run_id,
            key=key,
            score=score,
            comment=comment,
        )
    except Exception as e:
        logger.warning(f"LangSmith feedback failed for run {run_id}: {e}")


def record_critic_feedback(run_id: str, intent_score: float, brand_score: float,
                           quality_score: float, user_decision: Optional[str] = None):
    """
    Convenience wrapper that records all three critic dimension scores and an
    optional user decision ('approved'/'rejected'/'edited') as a string value.
    """
    record_feedback(run_id, "intent_match", intent_score)
    record_feedback(run_id, "brand_alignment", brand_score)
    record_feedback(run_id, "quality", quality_score)
    if user_decision:
        try:
            client = get_client()
            if client:
                client.create_feedback(
                    run_id=run_id,
                    key="user_decision",
                    value=user_decision,
                )
        except Exception as e:
            logger.warning(f"LangSmith decision feedback failed: {e}")


def record_prompt_version_feedback(run_id: str, prompt_version_id: str, score: float):
    """Record which prompt version was used and how it performed."""
    record_feedback(run_id, "prompt_version_performance", score,
                    comment=f"prompt_version_id={prompt_version_id}")


def record_mabo_reward(run_id: str, reward: float, platform: str):
    """Record delayed social-media reward back to the MABO trace run."""
    record_feedback(run_id, "social_reward", reward, comment=f"platform={platform}")


# ── Current run ID helper ─────────────────────────────────────────────────────

def get_current_run_id() -> Optional[str]:
    """
    Return the LangSmith run_id of the innermost active trace, or None if
    tracing is disabled or we're outside a traced context.
    """
    if not _ENABLED:
        return None
    try:
        run = get_current_run_tree()
        return str(run.id) if run else None
    except Exception:
        return None


# ── Context-manager style tracing (for manual spans) ─────────────────────────

class LangSmithSpan:
    """
    Lightweight context manager for creating manual spans inside a traced function.

    with LangSmithSpan("embedding_lookup", run_type="tool") as span:
        results = embed(query)
        span.set_output({"count": len(results)})
    """

    def __init__(self, name: str, run_type: str = "tool",
                 inputs: Optional[Dict] = None, tags: Optional[List[str]] = None):
        self.name = name
        self.run_type = run_type
        self.inputs = inputs or {}
        self.tags = tags or []
        self._run = None

    def __enter__(self):
        if _ENABLED:
            try:
                self._run = RunTree(
                    name=self.name,
                    run_type=self.run_type,
                    inputs=self.inputs,
                    tags=self.tags,
                )
                self._run.post()
            except Exception as e:
                logger.debug(f"LangSmithSpan enter failed: {e}")
        return self

    def set_output(self, outputs: Dict):
        if self._run:
            try:
                self._run.end(outputs=outputs)
                self._run.patch()
            except Exception as e:
                logger.debug(f"LangSmithSpan set_output failed: {e}")

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._run:
            try:
                if exc_type:
                    self._run.end(error=str(exc_val))
                else:
                    if not hasattr(self._run, '_ended'):
                        self._run.end(outputs={})
                self._run.patch()
            except Exception:
                pass
        return False  # don't suppress exceptions


# ── Status ────────────────────────────────────────────────────────────────────

def tracer_status() -> Dict[str, Any]:
    return {
        "available": _LANGSMITH_AVAILABLE,
        "enabled": _ENABLED,
        "project": os.getenv("LANGCHAIN_PROJECT", "default"),
        "api_key_set": bool(os.getenv("LANGSMITH_API_KEY")),
    }
