"""
Campaign Agent Adapter — calls campaign logic directly (no HTTP).
"""
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger("adapter.campaign")


def generate_campaign_post(topic: str,
                           platform: str,
                           brand_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Generate AI-powered social media post content for a campaign.
    Returns dict with 'post_text' and 'image_prompt'.
    """
    import os
    import json
    from groq import Groq

    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    if not GROQ_API_KEY:
        return {"post_text": topic, "image_prompt": "", "error": "GROQ_API_KEY not set"}

    try:
        client = Groq(api_key=GROQ_API_KEY)

        platform_hints = {
            "linkedin": "professional tone, 150-300 words, include relevant hashtags",
            "x": "punchy, max 270 characters, 1-3 hashtags",
            "instagram": "engaging, 100-200 words, emoji-friendly, 5-10 hashtags",
            "reddit": "conversational, no hashtags, add a question to spark discussion",
        }
        hint = platform_hints.get(platform.lower(), "engaging social media post")
        brand_ctx = f" The brand is: {brand_name}." if brand_name else ""

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are an expert social media copywriter. Reply with valid JSON only."},
                {"role": "user", "content": (
                    f"Campaign topic: {topic}.{brand_ctx}\n"
                    f"Platform: {platform} ({hint}).\n"
                    'Return JSON: {"post_text": "...", "image_prompt": "..."}\n'
                    "image_prompt: vivid Stable Diffusion / RunwayML prompt for complementary visual."
                )},
            ],
            temperature=0.7,
            max_tokens=512,
        )
        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        data = json.loads(raw)
        return {
            "post_text": data.get("post_text", topic),
            "image_prompt": data.get("image_prompt", ""),
        }
    except Exception as e:
        logger.error(f"Campaign post generation failed: {e}")
        return {"post_text": topic, "image_prompt": "", "error": str(e)}


def schedule_campaign(user_id: int,
                      name: str,
                      platform: str,
                      content_template: str,
                      trigger_type: str = "once",
                      run_at: Optional[str] = None,
                      cron_expr: Optional[str] = None,
                      ai_generate: bool = False,
                      brand_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Create a campaign schedule directly via database functions.
    """
    import uuid
    from database import create_campaign_schedule

    try:
        schedule_id = str(uuid.uuid4())
        db_platform = "twitter" if platform.lower() == "x" else platform.lower()
        metadata = {
            "ai_generate": ai_generate,
            "display_platform": platform,
        }
        if brand_name:
            metadata["brand_name"] = brand_name

        create_campaign_schedule(
            schedule_id=schedule_id,
            user_id=user_id,
            name=name,
            platform=db_platform,
            content_template=content_template,
            trigger_type=trigger_type,
            run_at=run_at,
            cron_expr=cron_expr,
            next_run=run_at if trigger_type == "once" else None,
            metadata=metadata,
        )

        return {
            "status": "created",
            "schedule_id": schedule_id,
            "ai_generate": ai_generate,
        }
    except Exception as e:
        logger.error(f"Campaign scheduling failed: {e}")
        return {"status": "failed", "error": str(e)}
