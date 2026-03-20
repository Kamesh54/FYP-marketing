"""
Image Agent — port 8005
Generates marketing images and videos via Runway ML Gen-3 API.

Endpoints:
  POST /generate          — submit a generation job
  GET  /status/{job_id}   — poll job status
  GET  /download/{job_id} — retrieve final asset URL / local path

Requires RUNWAY_API_KEY in environment.
Images are saved to generated_images/ directory.
"""

import os
import uuid
import asyncio
import logging
import httpx
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("image_agent")

from langsmith_tracer import trace_agent, get_current_run_id

# ── Runway SDK (optional import) ──────────────────────────────────────────────
try:
    import runwayml
    _RUNWAY_AVAILABLE = True
except ImportError:
    _RUNWAY_AVAILABLE = False
    logger.debug("runwayml package not installed — will use HuggingFace or demo placeholder")

RUNWAY_API_KEY = os.getenv("RUNWAY_API_KEY", "")
HF_TOKEN       = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_API_KEY", "")
# Model to use for HuggingFace text-to-image (change via HF_IMAGE_MODEL env var)
HF_IMAGE_MODEL = os.getenv("HF_IMAGE_MODEL", "stabilityai/stable-diffusion-xl-base-1.0")
IMAGES_DIR     = "generated_images"
os.makedirs(IMAGES_DIR, exist_ok=True)

app = FastAPI(title="Image Agent", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)
app.mount("/images", StaticFiles(directory=IMAGES_DIR), name="images")

_jobs: Dict[str, Dict[str, Any]] = {}


# ── Models ────────────────────────────────────────────────────────────────────

class ImageRequest(BaseModel):
    prompt: str
    brand_name: Optional[str] = ""
    style: Optional[str] = "photorealistic"       # photorealistic | illustration | minimal | cinematic
    aspect_ratio: Optional[str] = "1280:768"       # Runway Gen-3 ratios
    duration: Optional[int] = None                 # seconds; None = still image
    negative_prompt: Optional[str] = ""
    content_id: Optional[str] = None               # link output to a content piece


class ImageStatusResponse(BaseModel):
    job_id: str
    status: str
    prompt: str
    url: Optional[str] = None
    local_path: Optional[str] = None
    runway_id: Optional[str] = None
    error: Optional[str] = None
    created_at: str
    completed_at: Optional[str] = None


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/")
def health():
    return {
        "service": "image_agent", "port": 8005, "version": "1.0.0",
        "runway_available": _RUNWAY_AVAILABLE and bool(RUNWAY_API_KEY),
        "huggingface_available": bool(HF_TOKEN),
        "hf_model": HF_IMAGE_MODEL if HF_TOKEN else None,
        "active_backend": (
            "runway" if (_RUNWAY_AVAILABLE and RUNWAY_API_KEY)
            else "huggingface" if HF_TOKEN
            else "demo_placeholder"
        ),
        "status": "ok"
    }


# ── Generate endpoint ─────────────────────────────────────────────────────────

@app.post("/generate", response_model=ImageStatusResponse)
async def generate_image(req: ImageRequest):
    job_id = f"img_{uuid.uuid4().hex[:10]}"
    _jobs[job_id] = {
        "status": "queued",
        "prompt": req.prompt,
        "created_at": datetime.now().isoformat(),
        "request": req.dict(),
    }
    asyncio.create_task(_run_generation(job_id, req))
    return ImageStatusResponse(
        job_id=job_id,
        status="queued",
        prompt=req.prompt,
        created_at=_jobs[job_id]["created_at"],
    )


@app.get("/status/{job_id}", response_model=ImageStatusResponse)
def get_status(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id} not found")
    return ImageStatusResponse(
        job_id=job_id,
        status=job["status"],
        prompt=job["prompt"],
        url=job.get("url"),
        local_path=job.get("local_path"),
        runway_id=job.get("runway_id"),
        error=job.get("error"),
        created_at=job["created_at"],
        completed_at=job.get("completed_at"),
    )


@app.get("/download/{job_id}")
def download(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] != "completed":
        raise HTTPException(409, f"Job status is '{job['status']}', not completed")
    return {
        "job_id": job_id,
        "url": job.get("url"),
        "local_path": job.get("local_path"),
        "runway_id": job.get("runway_id"),
    }


# ── Background generation ─────────────────────────────────────────────────────

@trace_agent(name="image_generation", tags=["image_agent"])
async def _run_generation(job_id: str, req: ImageRequest):
    job = _jobs[job_id]
    job["status"] = "running"
    job["langsmith_run_id"] = get_current_run_id()

    # Build enriched prompt
    style_hints = {
        "photorealistic": "ultra-realistic photography, 8K, sharp focus, professional lighting",
        "illustration":   "digital illustration, clean lines, vibrant colours, editorial style",
        "minimal":        "minimalist, clean white background, simple shapes, professional",
        "cinematic":      "cinematic wide shot, dramatic lighting, film grain, movie poster",
    }
    enriched = f"{req.prompt}. {style_hints.get(req.style, '')}. For brand: {req.brand_name}."
    if req.negative_prompt:
        enriched += f" Avoid: {req.negative_prompt}"

    try:
        local_path = None
        if _RUNWAY_AVAILABLE and RUNWAY_API_KEY:
            url, runway_id = await _runway_generate(enriched, req)
            if url and url.startswith("http"):
                local_path = await _download_asset(url, job_id)
        elif HF_TOKEN:
            logger.info(f"[{job_id}] Runway unavailable — using HuggingFace ({HF_IMAGE_MODEL})")
            local_path = await _huggingface_generate(enriched, req, job_id)
            url, runway_id = local_path, "huggingface"
        else:
            # Fallback: return a placeholder / unsplash search URL for demo
            url, runway_id = await _demo_placeholder(enriched, req), "demo"

        job.update({
            "status": "completed",
            "url": url,
            "local_path": local_path,
            "runway_id": runway_id,
            "completed_at": datetime.now().isoformat(),
        })
        logger.info(f"[{job_id}] Image generation completed: {url}")

    except Exception as e:
        logger.error(f"[{job_id}] Generation failed: {e}", exc_info=True)
        job.update({
            "status": "failed",
            "error": str(e),
            "completed_at": datetime.now().isoformat(),
        })


async def _runway_generate(prompt: str, req: ImageRequest):
    """Call Runway ML Gen-3 Alpha API."""
    client = runwayml.AsyncRunwayML(api_key=RUNWAY_API_KEY)

    if req.duration:
        # Text-to-video
        task = await client.image_to_video.create(
            model="gen3a_turbo",
            prompt_text=prompt,
            ratio=req.aspect_ratio,
            duration=req.duration,
        )
    else:
        # Text-to-image
        task = await client.text_to_image.create(
            model="gen3a_turbo",
            prompt_text=prompt,
            ratio=req.aspect_ratio,
        )

    task_id = task.id
    # Poll for completion
    for _ in range(60):
        await asyncio.sleep(5)
        task = await client.tasks.retrieve(task_id)
        if task.status == "SUCCEEDED":
            output = task.output[0] if task.output else None
            return output, task_id
        if task.status in ("FAILED", "CANCELLED"):
            raise RuntimeError(f"Runway task {task_id} status: {task.status}")

    raise TimeoutError(f"Runway task {task_id} timed out after 5 minutes")


async def _huggingface_generate(prompt: str, req: ImageRequest, job_id: str) -> str:
    """Call HuggingFace Inference API for text-to-image, save locally, return path."""
    api_url = f"https://api-inference.huggingface.co/models/{HF_IMAGE_MODEL}"
    headers = {
        "Authorization": f"Bearer {HF_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {"inputs": prompt}

    async with httpx.AsyncClient(timeout=120) as client:
        # HuggingFace may return 503 while the model is loading — retry up to 3x
        for attempt in range(3):
            resp = await client.post(api_url, headers=headers, json=payload)
            if resp.status_code == 503:
                wait = int(resp.headers.get("Retry-After", 20))
                logger.info(f"[{job_id}] HF model loading, retrying in {wait}s (attempt {attempt+1})")
                await asyncio.sleep(wait)
                continue
            if resp.status_code != 200:
                raise RuntimeError(f"HuggingFace API error {resp.status_code}: {resp.text[:200]}")
            # Response is raw image bytes
            path = os.path.join(IMAGES_DIR, f"{job_id}.png")
            with open(path, "wb") as f:
                f.write(resp.content)
            logger.info(f"[{job_id}] HuggingFace image saved: {path}")
            return path
        raise RuntimeError("HuggingFace model still loading after 3 retries")


async def _demo_placeholder(prompt: str, req: ImageRequest) -> str:
    """Return a keyword-based Unsplash URL as a demo placeholder."""
    keywords = "+".join(prompt.split()[:4])
    return f"https://source.unsplash.com/1280x768/?{keywords}"


async def _download_asset(url: str, job_id: str) -> Optional[str]:
    """Download remote asset and save to generated_images/."""
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                ext = "mp4" if "video" in resp.headers.get("content-type", "") else "png"
                path = os.path.join(IMAGES_DIR, f"{job_id}.{ext}")
                with open(path, "wb") as f:
                    f.write(resp.content)
                return path
    except Exception as e:
        logger.warning(f"Asset download failed for {job_id}: {e}")
    return None


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("image_agent:app", host="0.0.0.0", port=8005, reload=True)
