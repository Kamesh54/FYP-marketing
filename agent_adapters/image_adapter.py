"""
Image Agent Adapter — calls Runway generation directly (no HTTP).
"""
import os
import logging
import asyncio
import httpx
import uuid
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger("adapter.image")


async def _generate_image_async(prompt: str,
                                brand_name: str = "",
                                style: str = "photorealistic",
                                aspect_ratio: str = "1280:768",
                                duration: Optional[int] = None,
                                negative_prompt: str = "") -> Dict[str, Any]:
    """Async image generation via Runway ML using HTTP API."""
    try:
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
        if negative_prompt:
            enriched += f" Avoid: {negative_prompt}"

        headers = {
            "Authorization": f"Bearer {RUNWAY_API_KEY}",
            "Content-Type": "application/json",
            "X-Runway-Version": "2024-11-06"
        }
        # Use Runway gen4_image model
        payload = {
            "model": "gen4_image",
            "promptText": enriched,
            "ratio": "1280:720",
        }

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post("https://api.dev.runwayml.com/v1/text_to_image", json=payload, headers=headers)
            resp.raise_for_status()
            task_data = resp.json()
            task_id = task_data.get("id")

            # Poll for completion
            for _ in range(60):
                await asyncio.sleep(5)
                status_resp = await client.get(f"https://api.dev.runwayml.com/v1/tasks/{task_id}", headers=headers)
                if status_resp.status_code != 200:
                    continue
                
                data = status_resp.json()
                if data.get('status') == 'SUCCEEDED':
                    output_url = data.get('output', [None])[0] if data.get('output') else None
                    
                    # Download local path
                    local_path = None
                    if output_url and output_url.startswith("http"):
                        job_id = f"img_{uuid.uuid4().hex[:10]}"
                        try:
                            IMAGES_DIR = "generated_images"
                            os.makedirs(IMAGES_DIR, exist_ok=True)
                            dl_resp = await client.get(output_url)
                            if dl_resp.status_code == 200:
                                path = os.path.join(IMAGES_DIR, f"{job_id}.jpg")
                                with open(path, "wb") as f:
                                    f.write(dl_resp.content)
                                local_path = path
                        except Exception as dl_e:
                            logger.warning(f"Asset download failed: {dl_e}")

                    return {
                        "url": output_url,
                        "local_path": local_path,
                        "runway_id": task_id,
                    }
                elif data.get('status') in ['FAILED', 'CANCELLED']:
                    return {"url": None, "error": f"Runway status: {data.get('status')}"}

            return {"url": None, "error": "Runway generation timed out"}

    except Exception as e:
        logger.error(f"Image generation failed: {e}")
        keywords = "+".join(prompt.split()[:4])
        return {
            "url": f"https://source.unsplash.com/1280x768/?{keywords}",
            "local_path": None,
            "runway_id": "demo",
            "error": str(e)
        }


def generate_image(prompt: str,
                   brand_name: str = "",
                   style: str = "photorealistic",
                   aspect_ratio: str = "1280:768",
                   duration: Optional[int] = None,
                   negative_prompt: str = "") -> Dict[str, Any]:
    """
    Generate an image from a text prompt using Runway ML.
    Returns dict with 'url', 'local_path', 'runway_id'.
    """
    try:
        loop = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            pass
            
        if loop and loop.is_running():
            # We're inside an async context, create a task
            import concurrent.futures
            
            # Create coroutine in the new thread to avoid tying to current loop
            def run_in_thread():
                return asyncio.run(_generate_image_async(prompt, brand_name, style, aspect_ratio, duration, negative_prompt))
                
            with concurrent.futures.ThreadPoolExecutor() as pool:
                result = pool.submit(run_in_thread).result()
            return result
        else:
            return asyncio.run(
                _generate_image_async(prompt, brand_name, style, aspect_ratio, duration, negative_prompt)
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
