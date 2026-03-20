import os
import uuid
import asyncio
import logging
import httpx
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("campaign_agent")

from langsmith_tracer import trace_agent, get_current_run_id
from database import (
    create_campaign_schedule, get_campaign_schedules, get_all_active_schedules,
    update_schedule_after_run, cancel_campaign_schedule, save_social_post,
    get_social_posts, list_brand_profiles,
)

# ── Platform credentials ──────────────────────────────────────────────────────
TWITTER_API_KEY            = os.getenv("TWITTER_API_KEY", "")
TWITTER_API_SECRET         = os.getenv("TWITTER_API_SECRET", "")
TWITTER_ACCESS_TOKEN       = os.getenv("TWITTER_ACCESS_TOKEN", "")
TWITTER_ACCESS_TOKEN_SECRET = os.getenv("TWITTER_ACCESS_TOKEN_SECRET", "")
INSTAGRAM_ACCESS_TOKEN     = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
INSTAGRAM_ACCOUNT_ID       = os.getenv("INSTAGRAM_ACCOUNT_ID", "")
INSTAGRAM_USERNAME         = os.getenv("INSTAGRAM_USERNAME", "")
INSTAGRAM_PASSWORD         = os.getenv("INSTAGRAM_PASSWORD", "")
LINKEDIN_ACCESS_TOKEN      = os.getenv("LINKEDIN_ACCESS_TOKEN", "")
LINKEDIN_PERSON_URN        = os.getenv("LINKEDIN_PERSON_URN", "")
REDDIT_CLIENT_ID           = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET       = os.getenv("REDDIT_CLIENT_SECRET", "")
REDDIT_USERNAME            = os.getenv("REDDIT_USERNAME", "")
REDDIT_PASSWORD            = os.getenv("REDDIT_PASSWORD", "")
REDDIT_DEFAULT_SUBREDDIT   = os.getenv("REDDIT_DEFAULT_SUBREDDIT", "test")
GROQ_API_KEY               = os.getenv("GROQ_API_KEY", "")
_ORCHESTRATOR_URL          = "http://127.0.0.1:8004"
_CONTENT_AGENT_URL         = "http://127.0.0.1:8003"

app = FastAPI(title="Campaign Agent", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

# ── APScheduler ───────────────────────────────────────────────────────────────
scheduler = AsyncIOScheduler()
_post_jobs: Dict[str, Dict[str, Any]] = {}
_post_history: List[Dict[str, Any]] = []   # in-memory post log

# Map frontend platform names → DB CHECK constraint values
_PLATFORM_DB_MAP: Dict[str, Optional[str]] = {
    "x": "twitter", "twitter": "twitter",
    "instagram": "instagram", "linkedin": "linkedin",
    "facebook": "facebook", "reddit": None,  # not in DB constraint
}

class ScheduleRequest(BaseModel):
    user_id: int
    name: str
    platform: str                           
    content_template: Optional[str] = None  
    content_text: Optional[str] = None      
    trigger_type: str                       
    run_at: Optional[str] = None            
    cron_expr: Optional[str] = None         
    ai_generate: bool = False               
    brand_name: Optional[str] = None        
    metadata: Optional[Dict[str, Any]] = {}

    @property
    def resolved_content(self) -> str:
        """Return whichever content field was provided."""
        return (self.content_template or self.content_text or "").strip()

    def model_post_init(self, __context: Any) -> None:
        # Normalise: always populate content_template from either field
        if not self.content_template and self.content_text:
            self.content_template = self.content_text


class PostRequest(BaseModel):
    user_id: int
    platform: str
    content: Optional[str] = None
    content_text: Optional[str] = None      # alias sent by frontend
    title: Optional[str] = None            # for Reddit posts
    subreddit: Optional[str] = None        # for Reddit posts
    image_url: Optional[str] = None        # optional image attachment
    content_id: Optional[str] = None       # link post to a content piece
    ai_generate: bool = False               # generate fresh content+image
    brand_name: Optional[str] = None        # brand context for generation

    @property
    def resolved_content(self) -> str:
        return (self.content or self.content_text or "").strip()


class PostStatusResponse(BaseModel):
    job_id: str
    status: str
    platform: str
    post_url: Optional[str] = None
    error: Optional[str] = None
    created_at: str
    completed_at: Optional[str] = None
    generated_content: Optional[str] = None   # AI-written post text
    generated_image_url: Optional[str] = None  # AI-generated image preview URL


# ── Lifecycle ─────────────────────────────────────────────────────────────────

def _reload_post_history_from_db():
    """Seed _post_history from the social_posts DB table on startup."""
    global _post_history
    try:
        rows = get_social_posts()  # returns all rows newest-first
        existing_ids = {p["job_id"] for p in _post_history}
        added = 0
        for r in reversed(rows):  # oldest-first so history order is preserved
            jid = r.get("post_id") or str(r.get("id", ""))
            if jid in existing_ids:
                continue
            existing_ids.add(jid)
            _post_history.append({
                "job_id":          jid,
                "user_id":         0,
                "platform":        r.get("platform", ""),
                "topic":           "",
                "content_snippet": "",
                "image_url":       "",
                "post_url":        r.get("post_url", ""),
                "status":          "completed",
                "posted_at":       str(r.get("posted_at", "")),
                "ai_generated":    False,
                "from_db":         True,
            })
            added += 1
        logger.info(f"Loaded {added} posts from DB into history (skipped duplicates)")
    except Exception as e:
        logger.warning(f"Could not load post history from DB: {e}")


@app.on_event("startup")
async def startup():
    scheduler.start()
    await _reload_schedules_from_db()
    _reload_post_history_from_db()
    logger.info("Campaign agent started, scheduler running")


@app.on_event("shutdown")
async def shutdown():
    scheduler.shutdown(wait=False)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/")
def health():
    return {
        "service": "campaign_agent", "port": 8008, "version": "1.0.0",
        "scheduler_running": scheduler.running,
        "status": "ok"
    }


# ── Brand listing ─────────────────────────────────────────────────────

@app.get("/brands/{user_id}")
def get_brands(user_id: int):
    """List all brand profiles (own brands first)."""
  
    profiles = list_brand_profiles(user_id)
    # Deduplicate by brand_name (keep first occurrence = user's own)
    seen: set = set()
    unique = []
    for p in profiles:
        name = (p.get("brand_name") or "").strip()
        if name and name not in seen:
            seen.add(name)
            unique.append(p)
    return {
        "brands": [{"brand_name": p["brand_name"], "logo_url": p.get("logo_url", ""),
                    "industry": p.get("industry", "")} for p in unique],
        "count": len(unique),
    }


@app.post("/schedule", status_code=201)
def create_schedule(req: ScheduleRequest):
    _validate_platform(req.platform)

    next_run = None
    normalised_run_at = req.run_at
    if req.trigger_type == "once" and req.run_at:
        # Validate and normalise to ISO string right here — fail fast with 400
        try:
            normalised_run_at = _parse_run_at(req.run_at).isoformat()
            next_run = normalised_run_at
        except Exception as e:
            raise HTTPException(400, f"Invalid run_at date: {e}")
    elif req.trigger_type == "recurring" and req.cron_expr:
        from apscheduler.triggers.cron import CronTrigger as _CT
        try:
            _CT.from_crontab(req.cron_expr)
        except Exception as e:
            raise HTTPException(400, f"Invalid cron expression: {e}")

    schedule_id = str(uuid.uuid4())
    db_platform = "twitter" if req.platform.lower() == "x" else req.platform.lower()
    metadata = dict(req.metadata or {})
    metadata["ai_generate"] = req.ai_generate
    if req.brand_name:
        metadata["brand_name"] = req.brand_name
    metadata["display_platform"] = req.platform

    # resolved_content is the actual text to post; fall back to name
    effective_content = req.resolved_content or req.content_template or req.name

    create_campaign_schedule(
        schedule_id=schedule_id,
        user_id=req.user_id,
        name=req.name,
        platform=db_platform,
        content_template=effective_content,
        trigger_type=req.trigger_type,
        run_at=normalised_run_at,
        cron_expr=req.cron_expr,
        next_run=next_run,
        metadata=metadata,
    )
    _add_to_scheduler(schedule_id, req.platform, effective_content,
                      req.trigger_type, normalised_run_at, req.cron_expr, req.user_id,
                      ai_generate=req.ai_generate, brand_name=req.brand_name)

    return {"status": "created", "schedule_id": schedule_id, "next_run": next_run,
            "ai_generate": req.ai_generate}


@app.get("/schedules/{user_id}")
def list_schedules(user_id: int, status: Optional[str] = None):
    schedules = get_campaign_schedules(user_id, status)
    # Surface brand_name and ai_generate from metadata for the frontend
    for s in schedules:
        meta = s.get("metadata") or {}
        s["brand_name"]       = meta.get("brand_name", "")
        s["ai_generate"]      = meta.get("ai_generate", False)
        s["display_platform"] = meta.get("display_platform") or s.get("platform", "")
        s["run_history"]      = meta.get("run_history", [])
    return {"schedules": schedules, "count": len(schedules)}


@app.get("/schedule/{schedule_id}/runs")
def schedule_runs(schedule_id: str):
    """Return the run history log for a specific schedule."""
    import sqlite3, json as _json
    from database import get_db_connection
    with get_db_connection() as conn:
        row = conn.execute("SELECT metadata FROM campaign_schedules WHERE id=?",
                           (schedule_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Schedule not found")
    meta = _json.loads(row[0] or "{}")
    return {"schedule_id": schedule_id, "runs": meta.get("run_history", [])}


@app.delete("/schedule/{schedule_id}")
def delete_schedule(schedule_id: str, user_id: int):
    cancel_campaign_schedule(schedule_id, user_id)
    try:
        scheduler.remove_job(schedule_id)
    except Exception:
        pass
    return {"status": "cancelled", "schedule_id": schedule_id}


# ── Immediate post endpoint ───────────────────────────────────────────────────

@app.post("/post")
async def post_now(req: PostRequest):
    _validate_platform(req.platform)
    job_id = f"post_{req.platform}_{uuid.uuid4().hex[:8]}"
    _post_jobs[job_id] = {
        "status": "queued",
        "platform": req.platform,
        "created_at": datetime.now().isoformat(),
    }
    asyncio.create_task(_post_content(job_id, req))
    return {"job_id": job_id, "status": "queued"}


@app.get("/post/status/{job_id}", response_model=PostStatusResponse)
def post_status(job_id: str):
    job = _post_jobs.get(job_id)
    if not job:
        raise HTTPException(404, f"Post job {job_id} not found")
    return PostStatusResponse(
        job_id=job_id,
        status=job["status"],
        platform=job["platform"],
        post_url=job.get("post_url"),
        error=job.get("error"),
        created_at=job["created_at"],
        completed_at=job.get("completed_at"),
        generated_content=job.get("generated_content"),
        generated_image_url=job.get("generated_image_url"),
    )


@app.get("/posts")
def list_posts(user_id: Optional[int] = None, platform: Optional[str] = None):
    """Return post history. user_id filter is intentionally ignored so all posts
    are visible regardless of which user_id was active when they were created."""
    filtered = list(_post_history)
    if platform:
        filtered = [p for p in filtered if p.get("platform") == platform.lower()]
    # Deduplicate by job_id (keep last occurrence = most up-to-date entry)
    seen: dict = {}
    for p in filtered:
        seen[p["job_id"]] = p
    deduped = list(reversed(list(seen.values())))
    return {"posts": deduped, "count": len(deduped)}


def _validate_platform(platform: str):
    allowed = {"linkedin", "x", "instagram", "reddit"}
    if platform.lower() not in allowed:
        raise HTTPException(400, f"Unsupported platform '{platform}'. Allowed: {allowed}")


async def _ai_generate_content_and_image(
    topic: str, platform: str, brand_name: Optional[str] = None
) -> tuple:
    
    if not GROQ_API_KEY:
        logger.warning("GROQ_API_KEY not set — skipping AI generation")
        return topic, None

    from llm_client import llm_chat_json as _llm_json

    platform_hints = {
        "linkedin": "professional tone, 150-300 words, include relevant hashtags",
        "x":        "punchy, max 270 characters, 1-3 hashtags",
        "instagram": "engaging, 100-200 words, emoji-friendly, 5-10 hashtags",
        "reddit":   "conversational, no hashtags, add a question to spark discussion",
    }
    hint = platform_hints.get(platform, "engaging social media post")
    brand_ctx = f" The brand is: {brand_name}." if brand_name else ""

    prompt_sys = (
        "You are an expert social media copywriter. "
        "Reply with valid JSON only, no markdown, no extra text."
    )
    prompt_user = (
        f"Campaign topic: {topic}.{brand_ctx}\n"
        f"Platform: {platform} ({hint}).\n"
        "Return JSON: {\"post_text\": \"...\", \"image_prompt\": \"...\"}\n"
        "image_prompt: a vivid, detailed Stable Diffusion / RunwayML prompt for a complementary visual."
    )

    import json as _json
    try:
        data, _model = _llm_json(
            [{"role": "system", "content": prompt_sys},
             {"role": "user",   "content": prompt_user}],
            temperature=0.7,
            max_tokens=512,
        )
    except Exception as _e:
        logger.warning("LLM post generation failed: %s", _e)
        return topic, None
    post_text    = data.get("post_text", topic)
    image_prompt = data.get("image_prompt", "")

    # Try to generate image (non-blocking — failures are silenced)
    image_url: Optional[str] = None
    if image_prompt:
        try:
            async with httpx.AsyncClient(timeout=180) as cli:
                r = await cli.post(
                    f"{_ORCHESTRATOR_URL}/generate-image",
                    json={"prompt": image_prompt},
                )
                if r.status_code == 200:
                    image_url = r.json().get("preview_url")
        except Exception as img_err:
            logger.warning(f"Image generation failed (non-fatal): {img_err}")

    return post_text, image_url




def _parse_run_at(run_at: str) -> datetime:
    """Parse a run_at string to a datetime object, accepting common ISO formats."""
    if not run_at:
        raise ValueError("run_at is empty")
    # Strip trailing 'Z' timezone suffix (treat as local time)
    s = run_at.strip().rstrip("Z")
    # Try common formats in order
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    # Last resort: fromisoformat (Python 3.7+)
    return datetime.fromisoformat(s)


def _add_to_scheduler(schedule_id: str, platform: str, content: str,
                      trigger_type: str, run_at: Optional[str],
                      cron_expr: Optional[str], user_id: int,
                      ai_generate: bool = False, brand_name: Optional[str] = None):
    try:
        if trigger_type == "once" and run_at:
            run_at_dt = _parse_run_at(run_at)
            trigger = DateTrigger(run_date=run_at_dt)
        elif trigger_type == "recurring" and cron_expr:
            trigger = CronTrigger.from_crontab(cron_expr)
        else:
            return
        scheduler.add_job(
            _scheduled_post_callback,
            trigger=trigger,
            id=schedule_id,
            replace_existing=True,
            args=[schedule_id, platform, content, user_id, ai_generate, brand_name],
        )
        logger.info(f"Scheduler job registered: {schedule_id} | trigger={trigger} | platform={platform}")
    except Exception as e:
        logger.warning(f"Scheduler add_job failed for {schedule_id}: {e}")


async def _reload_schedules_from_db():
    """On startup, reload active recurring schedules from DB."""
    try:
        active = get_all_active_schedules()
        for s in active:
            if s.get("trigger_type") == "recurring" and s.get("cron_expr"):
                meta = s.get("metadata") or {}
                _add_to_scheduler(
                    s["id"], s["platform"], s["content_template"],
                    "recurring", None, s["cron_expr"], s["user_id"],
                    ai_generate=meta.get("ai_generate", False),
                    brand_name=meta.get("brand_name"),
                )
        logger.info(f"Reloaded {len(active)} active schedules from DB")
    except Exception as e:
        logger.error(f"Failed to reload schedules: {e}")


async def _scheduled_post_callback(schedule_id: str, platform: str,
                                    content: str, user_id: int,
                                    ai_generate: bool = False,
                                    brand_name: Optional[str] = None):
    """Called by APScheduler for scheduled posts."""
    req = PostRequest(
        user_id=user_id, platform=platform, content=content,
        ai_generate=ai_generate, brand_name=brand_name,
    )
    job_id = f"sched_{schedule_id}_{uuid.uuid4().hex[:6]}"
    _post_jobs[job_id] = {
        "status": "queued", "platform": platform,
        "created_at": datetime.now().isoformat(),
    }
    await _post_content(job_id, req)
    update_schedule_after_run(schedule_id)
    # Persist run result to schedule metadata for history
    try:
        import json as _j
        from database import get_db_connection
        with get_db_connection() as _conn:
            row = _conn.execute("SELECT metadata FROM campaign_schedules WHERE id=?",
                                (schedule_id,)).fetchone()
            if row:
                meta = _j.loads(row[0] or "{}")
                runs = meta.get("run_history", [])
                job_data = _post_jobs.get(job_id, {})
                runs.insert(0, {
                    "job_id":    job_id,
                    "status":    job_data.get("status", "unknown"),
                    "post_url":  job_data.get("post_url", ""),
                    "ran_at":    datetime.now().isoformat(),
                })
                meta["run_history"] = runs[:50]  # keep last 50
                _conn.execute("UPDATE campaign_schedules SET metadata=? WHERE id=?",
                              (_j.dumps(meta), schedule_id))
    except Exception as _log_err:
        logger.warning(f"Failed to persist run log for {schedule_id}: {_log_err}")


@trace_agent(name="social_post", tags=["campaign_agent"])
async def _post_content(job_id: str, req: PostRequest):
    job = _post_jobs[job_id]
    job["status"] = "running"
    platform = req.platform.lower()

    try:
        resolved = req.resolved_content
        image_url: Optional[str] = req.image_url

        # ── AI content + image generation ────────────────────────────────────
        if req.ai_generate and resolved:
            try:
                resolved, image_url = await _ai_generate_content_and_image(
                    topic=resolved, platform=platform, brand_name=req.brand_name
                )
                logger.info(f"[{job_id}] AI generated content ({len(resolved)} chars), image: {image_url}")
                # Store back so status endpoint can return them
                job["generated_content"] = resolved
                job["generated_image_url"] = image_url or ""
            except Exception as gen_err:
                logger.warning(f"[{job_id}] AI generation failed, using raw topic: {gen_err}")

        if platform == "x":
            url = await _post_to_x(resolved, image_url)
        elif platform == "linkedin":
            url = await _post_to_linkedin(resolved, image_url)
        elif platform == "instagram":
            url = await _post_to_instagram(resolved, image_url)
        elif platform == "reddit":
            url = await _post_to_reddit(
                req.title or "Post", resolved,
                req.subreddit or REDDIT_DEFAULT_SUBREDDIT
            )
        else:
            raise ValueError(f"Unsupported platform: {platform}")

        completed_at = datetime.now().isoformat()
        _post_history.append({
            "job_id": job_id,
            "user_id": req.user_id,
            "platform": platform,
            "topic": req.resolved_content[:200],          # original brief
            "content_snippet": resolved[:200],            # actual posted text
            "image_url": image_url or "",
            "post_url": url or "",
            "status": "completed",
            "posted_at": completed_at,
            "ai_generated": req.ai_generate,
        })
        # Persist to DB when platform is DB-compatible
        db_platform = _PLATFORM_DB_MAP.get(platform)
        if db_platform:
            try:
                cid = req.content_id or job_id
                save_social_post(cid, db_platform, url or "")
            except Exception as db_err:
                logger.warning(f"[{job_id}] DB save skipped: {db_err}")

        job.update({
            "status": "completed",
            "post_url": url,
            "completed_at": completed_at,
        })
        logger.info(f"[{job_id}] Posted to {platform}: {url}")

    except Exception as e:
        logger.error(f"[{job_id}] Post to {platform} failed: {e}", exc_info=True)
        _post_history.append({
            "job_id": job_id,
            "user_id": req.user_id,
            "platform": platform,
            "topic": req.resolved_content[:200],
            "content_snippet": req.resolved_content[:200],
            "image_url": "",
            "post_url": "",
            "status": "failed",
            "posted_at": datetime.now().isoformat(),
            "ai_generated": req.ai_generate,
        })
        job.update({
            "status": "failed",
            "error": str(e),
            "completed_at": datetime.now().isoformat(),
        })


# ── Platform-specific posting ─────────────────────────────────────────────────

async def _post_to_x(content: str, image_url: Optional[str] = None) -> str:
    if not TWITTER_API_KEY:
        logger.warning("X/Twitter API keys not configured — simulating post")
        return "https://twitter.com/sim/status/000"
    try:
        import tweepy
        auth = tweepy.OAuth1UserHandler(
            TWITTER_API_KEY, TWITTER_API_SECRET,
            TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET
        )
        api = tweepy.API(auth)
        client = tweepy.Client(
            consumer_key=TWITTER_API_KEY, consumer_secret=TWITTER_API_SECRET,
            access_token=TWITTER_ACCESS_TOKEN, access_token_secret=TWITTER_ACCESS_TOKEN_SECRET
        )
        media_ids = []
        if image_url:
            import httpx, tempfile, os as _os
            async with httpx.AsyncClient(timeout=30) as c:
                r = await c.get(image_url)
                if r.status_code == 200:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
                        tmp.write(r.content)
                        tmp_path = tmp.name
                    m = api.media_upload(filename=tmp_path)
                    media_ids.append(m.media_id)
                    _os.unlink(tmp_path)
        tweet = client.create_tweet(text=content[:280], media_ids=media_ids or None)
        tweet_id = tweet.data["id"]
        return f"https://twitter.com/i/web/status/{tweet_id}"
    except ImportError:
        logger.warning("tweepy not installed; simulating X post")
        return "https://twitter.com/sim/status/000"


async def _post_to_linkedin(content: str, image_url: Optional[str] = None) -> str:
    if not LINKEDIN_ACCESS_TOKEN:
        logger.warning("LinkedIn token not configured — simulating post")
        return "https://linkedin.com/feed/update/sim"
    try:
        import httpx
        headers = {
            "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        }
        payload = {
            "author": f"urn:li:person:{LINKEDIN_PERSON_URN}",
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": content},
                    "shareMediaCategory": "NONE",
                }
            },
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        }
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post("https://api.linkedin.com/v2/ugcPosts",
                             headers=headers, json=payload)
            r.raise_for_status()
            post_id = r.json().get("id", "")
        return f"https://www.linkedin.com/feed/update/{post_id}"
    except Exception as e:
        logger.error(f"LinkedIn post failed: {e}")
        raise


async def _post_to_instagram(content: str, image_url: Optional[str] = None) -> str:
    """
    Post to Instagram using instagrapi (username + password).
    Falls back to a generated placeholder image when no image_url is provided.
    """
    if not INSTAGRAM_USERNAME or not INSTAGRAM_PASSWORD:
        logger.warning("Instagram credentials not configured — simulating")
        return "https://instagram.com/p/sim"

    import tempfile, pathlib, httpx as _httpx
    from instagrapi import Client as _IGClient

    tmp_path: Optional[str] = None
    try:
        # ── Resolve image to a local file ────────────────────────────────────
        if image_url:
            suffix = ".jpg"
            try:
                async with _httpx.AsyncClient(timeout=60) as hc:
                    resp = await hc.get(image_url)
                    resp.raise_for_status()
                ct = resp.headers.get("content-type", "")
                if "png" in ct:
                    suffix = ".png"
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tf:
                    tf.write(resp.content)
                    tmp_path = tf.name
            except Exception as dl_err:
                logger.warning(f"Could not download Instagram image ({dl_err}) — generating placeholder")
                image_url = None

        if not tmp_path:
            # Generate a simple solid-colour JPEG as placeholder
            try:
                from PIL import Image as _PILImage
                img = _PILImage.new("RGB", (1080, 1080), color=(30, 30, 60))
                with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tf:
                    img.save(tf, format="JPEG")
                    tmp_path = tf.name
            except ImportError:
                # Pillow not installed — write a minimal valid JPEG
                import base64
                _MIN_JPEG = base64.b64decode(
                    "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkS"
                    "Ew8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAAR"
                    "CAABAAEDASIAAhEBAxEB/8QAFAABAAAAAAAAAAAAAAAAAAAACf/EABQQAQAAAAAA"
                    "AAAAAAAAAAAAAP/EABQBAQAAAAAAAAAAAAAAAAAAAAD/xAAUEQEAAAAAAAAAAAAA"
                    "AAAAAAAA/9oADAMBAAIRAxEAPwCwABmX/9k="
                )
                with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tf:
                    tf.write(_MIN_JPEG)
                    tmp_path = tf.name

        # ── Login and post ────────────────────────────────────────────────────
        cl = _IGClient()
        cl.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
        media = cl.photo_upload(
            path=pathlib.Path(tmp_path),
            caption=content,
        )
        media_code = getattr(media, "code", None) or getattr(media, "pk", "")
        logger.info(f"Instagram posted: media_id={media.pk}")
        return f"https://www.instagram.com/p/{media_code}/"

    except Exception as e:
        logger.error(f"Instagram post failed: {e}")
        raise
    finally:
        if tmp_path:
            try:
                pathlib.Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass


async def _post_to_reddit(title: str, content: str, subreddit: str) -> str:
    if not REDDIT_CLIENT_ID:
        logger.warning("Reddit credentials not configured — simulating post")
        return f"https://reddit.com/r/{subreddit}/sim"
    try:
        import praw
        reddit = praw.Reddit(
            client_id=REDDIT_CLIENT_ID, client_secret=REDDIT_CLIENT_SECRET,
            username=REDDIT_USERNAME, password=REDDIT_PASSWORD,
            user_agent="ContentPlatformBot/1.0"
        )
        sub = reddit.subreddit(subreddit)
        submission = sub.submit(title=title, selftext=content)
        return f"https://reddit.com{submission.permalink}"
    except ImportError:
        logger.warning("praw not installed; simulating Reddit post")
        return f"https://reddit.com/r/{subreddit}/sim"


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("campaign_agent:app", host="0.0.0.0", port=8008, reload=True)
