"""
Prompt Optimizer — importable module (no HTTP server)
Integrates with the MABO framework to select, version, and evolve prompts.

Key responsibilities:
  1. get_best_prompt_for_agent(agent, context)  → best performing prompt text  
  2. register_prompt(agent, context, text)       → save new version, return version_id
  3. score_prompt(version_id, score)             → update performance_score in DB
  4. evolve_prompt(agent, context, feedback)     → use LLM to mutate best prompt with
                                                    feedback signal (MABO step)

All DB interactions go through database.py helpers.
All LLM calls are traced via LangSmith.
"""

import os
import logging
from typing import Optional

from dotenv import load_dotenv
from groq import Groq

load_dotenv()
logger = logging.getLogger("prompt_optimizer")

from langsmith_tracer import trace_llm, get_current_run_id
from database import (
    save_prompt_version,
    get_best_prompt,
    update_prompt_score,
)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL   = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
groq_client  = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None


# ── Default seed prompts per agent ────────────────────────────────────────────
#   These are used the first time an agent has no scored versions yet.

_SEED_PROMPTS: dict = {
    "content_agent": {
        "blog": (
            "You are an expert content writer. Write a comprehensive, engaging blog post "
            "for the following topic. Include a hook, 3-5 main sections with H2 headings, "
            "practical examples, and a strong CTA. Aim for 800-1200 words. "
            "Tone: {tone}. Brand: {brand}.\n\nTopic: {topic}"
        ),
        "social_post": (
            "You are a social media expert. Write a compelling {platform} post about: {topic}. "
            "Brand voice: {tone}. Include relevant hashtags. Keep under 280 chars for X, "
            "2200 for Instagram, 700 for LinkedIn."
        ),
    },
    "seo_agent": {
        "meta_description": (
            "Write an SEO-optimised meta description (150-160 chars) for a page about: {topic}. "
            "Include the primary keyword naturally. Make it compelling and clickable."
        ),
    },
    "research_agent": {
        "synthesis": (
            "You are a senior content strategist. Synthesise the following research data "
            "into a concise brief with: brand positioning, audience signals, top 3 content "
            "opportunities, recommended tone, and 5 content ideas.\n\nData: {data}"
        ),
    },
}


# ── Public API ────────────────────────────────────────────────────────────────

def get_best_prompt_for_agent(agent_name: str, context_type: str,
                               fallback_template: Optional[str] = None) -> str:
    """
    Return the best-performing prompt text for an agent/context pair.
    Falls back to seed prompts, then the supplied fallback_template.
    """
    best = get_best_prompt(agent_name, context_type)
    if best:
        logger.debug(f"[PromptOptimizer] Using scored prompt v{best['id']} "
                     f"(score={best['performance_score']}) for {agent_name}/{context_type}")
        return best["prompt_text"]

    # Try seed
    seed = _SEED_PROMPTS.get(agent_name, {}).get(context_type)
    if seed:
        logger.debug(f"[PromptOptimizer] Using seed prompt for {agent_name}/{context_type}")
        return seed

    # Use supplied fallback
    if fallback_template:
        return fallback_template

    raise ValueError(f"No prompt found for {agent_name}/{context_type} and no fallback provided")


def register_prompt(agent_name: str, context_type: str, prompt_text: str,
                    langsmith_run_id: Optional[str] = None) -> str:
    """Save a new prompt version and return its version_id."""
    vid = save_prompt_version(agent_name, context_type, prompt_text, langsmith_run_id)
    logger.info(f"[PromptOptimizer] Registered prompt version {vid} for {agent_name}/{context_type}")
    return vid


def score_prompt(version_id: str, score: float):
    """Update a prompt version's performance score (0.0–1.0)."""
    update_prompt_score(version_id, max(0.0, min(1.0, score)))
    logger.info(f"[PromptOptimizer] Scored prompt {version_id}: {score:.3f}")


@trace_llm(name="prompt_evolution", tags=["prompt_optimizer", "llm"])
def evolve_prompt(agent_name: str, context_type: str,
                  feedback: str, current_score: float) -> str:
    """
    Use the LLM to mutate the best prompt based on feedback.
    Registers the evolved version in the DB and returns its version_id.

    Args:
        feedback: Free-text description of what went wrong / could improve.
        current_score: Score of the current best prompt (0-1).

    Returns:
        version_id of the new evolved prompt.
    """
    if not groq_client:
        raise RuntimeError("GROQ_API_KEY not set — cannot evolve prompts")

    # Get current best to mutate
    best = get_best_prompt(agent_name, context_type)
    base_prompt = best["prompt_text"] if best else (
        _SEED_PROMPTS.get(agent_name, {}).get(context_type, "")
    )
    if not base_prompt:
        raise ValueError(f"No base prompt to evolve for {agent_name}/{context_type}")

    meta_prompt = f"""You are a prompt engineer specialising in AI content generation.

CURRENT PROMPT (score: {current_score:.2f}/1.0):
---
{base_prompt[:2000]}
---

USER FEEDBACK ON CONTENT PRODUCED BY THIS PROMPT:
{feedback}

Rewrite the prompt to address the feedback while preserving what works.
Rules:
1. Keep all placeholder variables ({{topic}}, {{tone}}, {{brand}}, etc.)
2. Make incremental improvements — don't completely rewrite
3. Return ONLY the improved prompt text, no explanation

IMPROVED PROMPT:"""

    try:
        resp = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": meta_prompt}],
            temperature=0.4,
            max_tokens=1000,
        )
        evolved_text = resp.choices[0].message.content.strip()
        run_id = get_current_run_id()
        vid = register_prompt(agent_name, context_type, evolved_text, run_id)
        logger.info(f"[PromptOptimizer] Evolved prompt → {vid}")
        return vid
    except Exception as e:
        logger.error(f"Prompt evolution failed: {e}")
        raise


def suggest_next_prompt(agent_name: str, context_type: str) -> dict:
    """
    Return metadata about what the optimizer recommends next:
    whether to exploit (use best), explore (try a variant), or evolve.
    Used by MABO agent to decide its next action.
    """
    best = get_best_prompt(agent_name, context_type)
    if not best:
        return {"action": "seed", "reason": "No scored versions yet"}
    score = best.get("performance_score", 0)
    use_count = best.get("use_count", 0)

    if score >= 0.85 and use_count < 20:
        return {"action": "exploit", "version_id": best["id"], "score": score,
                "reason": "High score, low use — exploit"}
    elif score >= 0.70:
        return {"action": "explore", "version_id": best["id"], "score": score,
                "reason": "Good score — try minor variation"}
    else:
        return {"action": "evolve", "version_id": best["id"], "score": score,
                "reason": "Below threshold — needs evolution"}


def score_latest_for_agent(agent_name: str, context_type: str, score: float) -> None:
    """
    Score the most recently registered (unscored) prompt version for this
    agent / context.  Called by the orchestrator after critic evaluation so
    that every generation round produces a training signal for the optimizer.
    """
    try:
        from database import get_db_connection
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id FROM prompt_versions
                WHERE agent_name = ? AND context_type = ? AND performance_score IS NULL
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (agent_name, context_type),
            )
            row = cursor.fetchone()
            if row:
                score_prompt(row["id"], score)
                logger.info(
                    f"[PromptOptimizer] Scored latest {agent_name}/{context_type} "
                    f"version={row['id']} → {score:.3f}"
                )
            else:
                logger.debug(
                    f"[PromptOptimizer] No unscored prompt found for {agent_name}/{context_type}"
                )
    except Exception as exc:
        logger.warning(f"[PromptOptimizer] score_latest_for_agent failed: {exc}")
