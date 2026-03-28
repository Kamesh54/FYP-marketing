"""
Critic Agent Adapter — calls evaluation logic directly (no HTTP).
Uses the embedding-based evaluation from critic_agent.py.
"""
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger("adapter.critic")


def run_critique(content_text: str,
                 original_intent: str,
                 content_type: str = "blog",
                 brand_name: Optional[str] = None,
                 user_id: Optional[int] = None,
                 session_id: Optional[str] = None,
                 content_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Evaluate content against intent alignment, brand alignment, and quality.
    Returns dict with scores, critique text, and suggestions.
    """
    import asyncio
    from critic_agent import _evaluate, CriticRequest
    from database import get_brand_profile

    try:
        # Build brand context
        brand_context = ""
        if user_id and brand_name:
            profile = get_brand_profile(user_id, brand_name)
            if profile:
                brand_context = (
                    f"Brand: {profile.get('brand_name', brand_name)}\n"
                    f"Tone: {profile.get('tone', 'professional')}\n"
                    f"Industry: {profile.get('industry', '')}\n"
                    f"Target audience: {profile.get('target_audience', '')}\n"
                    f"Tagline: {profile.get('tagline', '')}"
                )

        # Build request
        cid = content_id or f"lg_{id(content_text)}"
        req = CriticRequest(
            content_id=cid,
            session_id=session_id,
            user_id=user_id,
            content_text=content_text,
            original_intent=original_intent,
            content_type=content_type,
            brand_name=brand_name,
        )

        # Run evaluation (async function)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    scores, critique_text, suggestions = pool.submit(
                        asyncio.run, _evaluate(req, brand_context)
                    ).result()
            else:
                scores, critique_text, suggestions = asyncio.run(
                    _evaluate(req, brand_context)
                )
        except RuntimeError:
            scores, critique_text, suggestions = asyncio.run(
                _evaluate(req, brand_context)
            )

        intent_s = scores["intent"]
        brand_s = scores["brand"]
        quality_s = scores["quality"]
        overall_s = round((intent_s * 0.4 + brand_s * 0.35 + quality_s * 0.25), 3)

        PASS_THRESHOLD = 0.70
        passed = overall_s >= PASS_THRESHOLD

        return {
            "content_id": cid,
            "intent_score": intent_s,
            "brand_score": brand_s,
            "quality_score": quality_s,
            "overall_score": overall_s,
            "passed": passed,
            "critique_text": critique_text,
            "improvement_suggestions": suggestions,
        }

    except Exception as e:
        logger.error(f"Critic adapter failed: {e}")
        return {
            "content_id": content_id or "",
            "intent_score": 0.0,
            "brand_score": 0.0,
            "quality_score": 0.0,
            "overall_score": 0.0,
            "passed": False,
            "critique_text": f"Evaluation failed: {e}",
            "improvement_suggestions": [],
            "error": str(e),
        }
