"""
Shared Groq LLM failover utilities with GLOBAL SHARED COOLDOWN.

Usage:
    response, model_used = groq_chat_with_failover(
        client,
        messages=[{"role": "user", "content": "..."}],
        primary_model="llama-3.3-70b-versatile",
        temperature=0.3,
    )
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

# Import shared cooldown (acts as global rate-limit gate)
try:
    from shared_cooldown import is_model_on_cooldown, get_cooldown_remaining, handle_groq_429
    SHARED_COOLDOWN_AVAILABLE = True
except ImportError:
    SHARED_COOLDOWN_AVAILABLE = False


def get_model_candidates(primary_model: str) -> List[str]:
    """Return ordered model candidates, primary first then configured fallbacks."""
    fallback_raw = os.getenv(
        "GROQ_FALLBACK_MODELS",
        "meta-llama/llama-4-scout-17b-16e-instruct,qwen/qwen3-32b,openai/gpt-oss-120b,openai/gpt-oss-20b,llama-3.1-8b-instant,llama3-8b-8192",
    )

    models = [primary_model]
    models.extend([m.strip() for m in fallback_raw.split(",") if m.strip()])

    deduped: List[str] = []
    for model_name in models:
        if model_name not in deduped:
            deduped.append(model_name)
    return deduped


def groq_chat_with_failover(
    client: Any,
    messages: List[Dict[str, str]],
    primary_model: str,
    logger: Optional[Any] = None,
    **kwargs: Any,
) -> Tuple[Any, str]:
    """Try Groq chat completion across candidate models until one succeeds.
    
    Respects GLOBAL SHARED COOLDOWN: if a model is on cooldown globally (set by ANY agent),
    it will be skipped here too.
    """
    if client is None:
        raise RuntimeError("Groq client is not configured")

    last_error: Optional[Exception] = None
    models = get_model_candidates(primary_model)

    for model_name in models:
        # === HARD CHECK: Is this model on global cooldown? ===
        if SHARED_COOLDOWN_AVAILABLE and is_model_on_cooldown(model_name):
            remaining = get_cooldown_remaining(model_name)
            if logger and remaining is not None:
                logger.info(f"Skipping model {model_name} due to active global cooldown ({remaining:.1f}s left)")
            continue

        try:
            call_kwargs = {"model": model_name, "messages": messages, **kwargs}
            response = client.chat.completions.create(**call_kwargs)
            return response, model_name
        except Exception as e:  # pragma: no cover - depends on external API behavior
            last_error = e
            
            # === SHARED COOLDOWN: On 429, register with global cooldown ===
            error_str = str(e).lower()
            if "429" in error_str or "rate_limit" in error_str or "too many requests" in error_str:
                if SHARED_COOLDOWN_AVAILABLE:
                    try:
                        error_dict = {}
                        if hasattr(e, 'response'):
                            try:
                                error_dict = e.response.json()
                            except:
                                error_dict = {"error": {"message": str(e)}}
                        else:
                            error_dict = {"error": {"message": str(e)}}
                        handle_groq_429(model_name, error_dict)
                    except Exception as cooldown_err:
                        if logger:
                            logger.warning(f"Failed to set shared cooldown: {cooldown_err}")
            
            if logger:
                logger.warning(f"Groq call failed on model {model_name}: {e}")
            continue

    if last_error:
        raise last_error
    raise RuntimeError("Groq call failed with no model candidates")
