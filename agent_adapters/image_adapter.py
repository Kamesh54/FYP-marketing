"""
Image Agent Adapter — calls Runway generation directly (no HTTP).
"""
import os
import logging
import asyncio
from typing import Dict, Any, Optional

logger = logging.getLogger("adapter.image")


async def _generate_image_async(prompt: str,
                                brand_name: str = "",
                                style: str = "photorealistic",
                                aspect_ratio: str = "1280:768") -> Dict[str, Any]:
    """Async image generation via Runway ML."""
    try:
        import runwayml
        RUNWAY_API_KEY = os.getenv("RUNWAY_API_KEY", "")
        if not RUNWAY_API_KEY:
            # Fallback: return placeholder
            keywords = "+".join(prompt.split()[:4])
            return {
                "url": f"https://source.unsplash.com/1280x768/?{keywords}",
                "local_path": None,
                "runway_id": "demo",
            }

        style_hints = {
            "photorealistic": "ultra-realistic photography, 8K, sharp focus, professional lighting",
            "illustration": "digital illustration, clean lines, vibrant colours, editorial style",
            "minimal": "minimalist, clean white background, simple shapes, professional",
            "cinematic": "cinematic wide shot, dramatic lighting, film grain, movie poster",
        }
        enriched = f"{prompt}. {style_hints.get(style, '')}. For brand: {brand_name}."

        client = runwayml.AsyncRunwayML(api_key=RUNWAY_API_KEY)
        task = await client.text_to_image.create(
            model="gen3a_turbo",
            prompt_text=enriched,
            ratio=aspect_ratio,
        )

        # Poll for completion
        for _ in range(60):
            await asyncio.sleep(5)
            task = await client.tasks.retrieve(task.id)
            if task.status == "SUCCEEDED":
                output = task.output[0] if task.output else None
                return {
                    "url": output,
                    "local_path": None,
                    "runway_id": task.id,
                }
            if task.status in ("FAILED", "CANCELLED"):
                return {"url": None, "error": f"Runway status: {task.status}"}

        return {"url": None, "error": "Runway generation timed out"}
    except ImportError:
        keywords = "+".join(prompt.split()[:4])
        return {
            "url": f"https://source.unsplash.com/1280x768/?{keywords}",
            "local_path": None,
            "runway_id": "demo",
        }
    except Exception as e:
        logger.error(f"Image generation failed: {e}")
        return {"url": None, "error": str(e)}


def generate_image(prompt: str,
                   brand_name: str = "",
                   style: str = "photorealistic",
                   aspect_ratio: str = "1280:768") -> Dict[str, Any]:
    """
    Generate an image from a text prompt using Runway ML.
    Returns dict with 'url', 'local_path', 'runway_id'.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # We're inside an async context, create a task
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                result = pool.submit(
                    asyncio.run,
                    _generate_image_async(prompt, brand_name, style, aspect_ratio)
                ).result()
            return result
        else:
            return asyncio.run(
                _generate_image_async(prompt, brand_name, style, aspect_ratio)
            )
    except Exception as e:
        logger.error(f"Image adapter failed: {e}")
        keywords = "+".join(prompt.split()[:4])
        return {
            "url": f"https://source.unsplash.com/1280x768/?{keywords}",
            "local_path": None,
            "runway_id": "demo",
            "error": str(e),
        }
