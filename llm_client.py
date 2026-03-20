"""
llm_client.py — Shared Groq LLM client with 3-model fallback chain.

Usage:
    from llm_client import llm_chat, llm_chat_json

    # Plain text response
    text, model_used = llm_chat(messages, temperature=0.7)

    # JSON-forced response (returns parsed dict)
    data, model_used = llm_chat_json(messages, temperature=0.3)

Model priority (configurable via env vars):
    GROQ_MODEL_1  →  primary   (default: llama-3.3-70b-versatile)
    GROQ_MODEL_2  →  fallback  (default: llama-3.1-8b-instant)
    GROQ_MODEL_3  →  last resort (default: gemma2-9b-it)

If a model fails for any reason (rate-limit, overload, timeout, bad response),
the next model in the chain is tried automatically.  Only raises if ALL three fail.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from groq import Groq

load_dotenv()
logger = logging.getLogger(__name__)

# ── Groq client (single shared instance for the whole process) ───────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
if not GROQ_API_KEY:
    logger.warning("GROQ_API_KEY is not set — LLM calls will fail at runtime.")

groq_client = Groq(api_key=GROQ_API_KEY)

# ── Model priority chain (override via env vars) ──────────────────────────────
LLM_MODELS: List[str] = [
    os.getenv("GROQ_MODEL_1", "llama-3.3-70b-versatile"),   # primary
    os.getenv("GROQ_MODEL_2", "llama-3.1-8b-instant"),      # fast fallback
    os.getenv("GROQ_MODEL_3", "gemma2-9b-it"),              # last resort
]


# ── Core fallback caller ──────────────────────────────────────────────────────

def llm_chat(
    messages: List[Dict[str, str]],
    *,
    temperature: float = 0.7,
    max_tokens: Optional[int] = None,
    response_format: Optional[Dict[str, str]] = None,
    stop: Optional[List[str]] = None,
    retry_delay: float = 1.0,
) -> Tuple[str, str]:
    """
    Call Groq with automatic 3-model fallback.

    Returns:
        (content: str, model_used: str)

    Raises:
        RuntimeError if all three models fail.
    """
    kwargs: Dict[str, Any] = {
        "messages":    messages,
        "temperature": temperature,
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if response_format is not None:
        kwargs["response_format"] = response_format
    if stop is not None:
        kwargs["stop"] = stop

    last_exc: Optional[Exception] = None

    for model in LLM_MODELS:
        try:
            logger.debug("LLM call → model=%s", model)
            resp = groq_client.chat.completions.create(model=model, **kwargs)
            content = resp.choices[0].message.content or ""
            logger.debug("LLM success ← model=%s  tokens=%s",
                         model, getattr(resp.usage, "total_tokens", "?"))
            return content, model

        except Exception as exc:
            logger.warning("LLM model '%s' failed: %s — trying next model.", model, exc)
            last_exc = exc
            time.sleep(retry_delay)

    raise RuntimeError(
        f"All LLM models failed. Last error: {last_exc}\n"
        f"Models tried: {LLM_MODELS}"
    )


def llm_chat_json(
    messages: List[Dict[str, str]],
    *,
    temperature: float = 0.3,
    max_tokens: Optional[int] = None,
    stop: Optional[List[str]] = None,
    retry_delay: float = 1.0,
) -> Tuple[Dict[str, Any], str]:
    """
    Call Groq with JSON mode + automatic 3-model fallback.

    First attempt uses response_format=json_object.  If the model rejects strict
    JSON mode, the fallback calls use plain text and extract the JSON substring.

    Returns:
        (parsed_dict: dict, model_used: str)

    Raises:
        RuntimeError if all three models fail.
    """
    last_exc: Optional[Exception] = None

    for model in LLM_MODELS:
        # ── Pass 1: strict JSON mode ─────────────────────────────────────────
        try:
            logger.debug("LLM JSON call (strict) → model=%s", model)
            resp = groq_client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                response_format={"type": "json_object"},
                **({"max_tokens": max_tokens} if max_tokens else {}),
                **({"stop": stop} if stop else {}),
            )
            content = resp.choices[0].message.content or "{}"
            try:
                data = json.loads(content)
                logger.debug("LLM JSON success (strict) ← model=%s", model)
                return data, model
            except json.JSONDecodeError:
                data = _extract_json(content)
                if data is not None:
                    return data, model
                # fall through to pass 2 with same model
        except Exception as exc:
            logger.warning("LLM JSON strict mode failed for '%s': %s — trying relaxed.", model, exc)
            last_exc = exc
            time.sleep(retry_delay)
            # skip pass 2 for this model and try next
            continue

        # ── Pass 2: relaxed (no response_format) ────────────────────────────
        relaxed_msgs = list(messages)
        relaxed_msgs[-1] = {
            "role": relaxed_msgs[-1]["role"],
            "content": relaxed_msgs[-1]["content"] + "\n\nReturn ONLY valid JSON. No prose, no code fences.",
        }
        try:
            logger.debug("LLM JSON call (relaxed) → model=%s", model)
            resp2 = groq_client.chat.completions.create(
                model=model,
                messages=relaxed_msgs,
                temperature=temperature,
                **({"max_tokens": max_tokens} if max_tokens else {}),
            )
            content2 = resp2.choices[0].message.content or "{}"
            data = _extract_json(content2)
            if data is not None:
                logger.debug("LLM JSON success (relaxed) ← model=%s", model)
                return data, model
            # store raw text and try next model
            last_exc = ValueError(f"Could not extract JSON from model {model} response.")
            logger.warning("Could not extract JSON from '%s' relaxed response.", model)
        except Exception as exc2:
            logger.warning("LLM JSON relaxed mode also failed for '%s': %s", model, exc2)
            last_exc = exc2
            time.sleep(retry_delay)

    raise RuntimeError(
        f"All LLM models failed to return valid JSON. Last error: {last_exc}\n"
        f"Models tried: {LLM_MODELS}"
    )


# ── Simple text completion (no chat history) ─────────────────────────────────

def llm_complete(
    prompt: str,
    *,
    system: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: Optional[int] = None,
    json_mode: bool = False,
) -> Tuple[str | Dict[str, Any], str]:
    """
    Convenience wrapper for a single-turn prompt → response.

    Returns:
        (str, model_used) when json_mode=False
        (dict, model_used) when json_mode=True
    """
    messages: List[Dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    if json_mode:
        return llm_chat_json(messages, temperature=temperature, max_tokens=max_tokens)
    return llm_chat(messages, temperature=temperature, max_tokens=max_tokens)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Extract the first valid JSON object from a string (handles markdown fences)."""
    # Strip code fences if present
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.split("\n")
        stripped = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    # Try full string first
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    # Scan for first { ... } pair
    start = text.find("{")
    end   = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    return None
