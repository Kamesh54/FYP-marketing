"""
Research Agent — port 8009
Orchestrates deep competitor and topic research by coordinating:
  - webcrawler (8000)  → raw page content
  - keywordExtraction (8001)  → keyword cluster
  - CompetitorGapAnalyzerAgent (8002)  → gaps
  - Groq LLM  → synthesise into research brief

Results are cached in SQLite (research_cache table) with 72-hour TTL.
LangSmith traces every LLM synthesis call.
"""

import os
import uuid
import asyncio
import logging
import httpx
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from groq import Groq

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("research_agent")

# ── LangSmith tracer (no-op if keys absent) ───────────────────────────────────
from langsmith_tracer import trace_llm, trace_workflow, get_current_run_id

# ── DB helpers ────────────────────────────────────────────────────────────────
from database import get_research_cache, save_research_cache

# ── Groq client ───────────────────────────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# ── Service ports ─────────────────────────────────────────────────────────────
WEBCRAWLER_URL  = os.getenv("WEBCRAWLER_URL",  "http://localhost:8000")
KEYWORD_URL     = os.getenv("KEYWORD_URL",     "http://localhost:8001")
GAP_URL         = os.getenv("GAP_URL",         "http://localhost:8002")
HTTP_TIMEOUT    = 120  # seconds

app = FastAPI(title="Research Agent", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

# ── In-progress job store ─────────────────────────────────────────────────────
_jobs: Dict[str, Dict[str, Any]] = {}


# ── Request / Response models ─────────────────────────────────────────────────

class ResearchRequest(BaseModel):
    domain: str                         # e.g. "sephora.com"
    depth_level: str = "standard"       # quick | standard | deep
    competitors: Optional[List[str]] = []
    use_cache: bool = True


class ResearchStatusResponse(BaseModel):
    job_id: str
    status: str
    domain: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: str
    completed_at: Optional[str] = None


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/")
def health():
    return {"service": "research_agent", "port": 8009, "version": "1.0.0", "status": "ok"}


# ── Research endpoint ─────────────────────────────────────────────────────────

@app.post("/research", response_model=ResearchStatusResponse)
async def start_research(req: ResearchRequest):
    """Kick off a research job and return a job_id immediately."""
    # Check cache first
    if req.use_cache:
        cached = get_research_cache(req.domain, req.depth_level)
        if cached:
            job_id = f"research_cached_{req.domain}_{uuid.uuid4().hex[:6]}"
            logger.info(f"Cache hit for {req.domain}/{req.depth_level}")
            return ResearchStatusResponse(
                job_id=job_id,
                status="completed",
                domain=req.domain,
                result=cached["result_json"],
                created_at=datetime.now().isoformat(),
                completed_at=datetime.now().isoformat(),
            )

    job_id = f"research_{req.domain.replace('.', '_')}_{uuid.uuid4().hex[:8]}"
    _jobs[job_id] = {
        "status": "queued",
        "domain": req.domain,
        "depth_level": req.depth_level,
        "created_at": datetime.now().isoformat(),
    }
    asyncio.create_task(_run_research(job_id, req))
    return ResearchStatusResponse(
        job_id=job_id,
        status="queued",
        domain=req.domain,
        created_at=_jobs[job_id]["created_at"],
    )


@app.get("/status/{job_id}", response_model=ResearchStatusResponse)
def get_status(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id} not found")
    return ResearchStatusResponse(
        job_id=job_id,
        status=job["status"],
        domain=job["domain"],
        result=job.get("result"),
        error=job.get("error"),
        created_at=job["created_at"],
        completed_at=job.get("completed_at"),
    )


# ── Background research pipeline ──────────────────────────────────────────────

@trace_workflow(name="research_pipeline", tags=["research_agent"])
async def _run_research(job_id: str, req: ResearchRequest):
    job = _jobs[job_id]
    job["status"] = "running"
    logger.info(f"[{job_id}] Starting research for {req.domain}")

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            # ── 1. Crawl domain ───────────────────────────────────────────────
            crawl_data = await _crawl(client, req.domain, req.depth_level)

            # ── 2. Extract keywords ───────────────────────────────────────────
            raw_text = crawl_data.get("content", "")[:8000]
            keywords = await _extract_keywords(client, raw_text, req.domain)

            # ── 3. Gap analysis (if competitors provided) ─────────────────────
            gaps: List[str] = []
            if req.competitors:
                gaps = await _gap_analysis(client, req.domain, req.competitors)

            # ── 4. Synthesise with LLM ────────────────────────────────────────
            brief = await _synthesise(req.domain, crawl_data, keywords, gaps, req.depth_level)

        result = {
            "domain": req.domain,
            "depth_level": req.depth_level,
            "crawl_summary": {
                "pages_crawled": crawl_data.get("pages_count", 1),
                "title": crawl_data.get("title", ""),
                "description": crawl_data.get("description", ""),
            },
            "top_keywords": keywords[:20],
            "competitor_gaps": gaps[:10],
            "research_brief": brief,
            "langsmith_run_id": get_current_run_id(),
            "generated_at": datetime.now().isoformat(),
        }

        # ── 5. Cache result ───────────────────────────────────────────────────
        ttl = {"quick": 24, "standard": 72, "deep": 168}.get(req.depth_level, 72)
        save_research_cache(req.domain, req.depth_level, result, ttl_hours=ttl)

        job["result"] = result
        job["status"] = "completed"
        job["completed_at"] = datetime.now().isoformat()
        logger.info(f"[{job_id}] Research completed")

    except Exception as e:
        logger.error(f"[{job_id}] Research failed: {e}", exc_info=True)
        job["status"] = "failed"
        job["error"] = str(e)
        job["completed_at"] = datetime.now().isoformat()


# ── Helper: crawl ─────────────────────────────────────────────────────────────

async def _crawl(client: httpx.AsyncClient, domain: str, depth: str) -> Dict[str, Any]:
    try:
        resp = await client.post(f"{WEBCRAWLER_URL}/crawl", json={"url": f"https://{domain}", "depth": 1})
        if resp.status_code != 200:
            return {"content": "", "pages_count": 0}
        job = resp.json()
        job_id = job.get("job_id")
        if not job_id:
            return {"content": "", "pages_count": 0}

        # Poll for completion
        for _ in range(30):
            await asyncio.sleep(3)
            status_resp = await client.get(f"{WEBCRAWLER_URL}/status/{job_id}")
            s = status_resp.json().get("status", "running")
            if s == "completed":
                dl = await client.get(f"{WEBCRAWLER_URL}/download/{job_id}")
                return dl.json() if dl.status_code == 200 else {}
            if s == "failed":
                return {}
        return {}
    except Exception as e:
        logger.warning(f"Crawl failed for {domain}: {e}")
        return {}


# ── Helper: keywords ──────────────────────────────────────────────────────────

async def _extract_keywords(client: httpx.AsyncClient, text: str, domain: str) -> List[str]:
    try:
        resp = await client.post(f"{KEYWORD_URL}/extract", json={"text": text, "domain": domain})
        if resp.status_code == 200:
            data = resp.json()
            kws = data.get("keywords", [])
            return [k if isinstance(k, str) else k.get("keyword", "") for k in kws]
        return []
    except Exception as e:
        logger.warning(f"Keyword extraction failed: {e}")
        return []


# ── Helper: gap analysis ──────────────────────────────────────────────────────

async def _gap_analysis(client: httpx.AsyncClient, domain: str,
                        competitors: List[str]) -> List[str]:
    try:
        resp = await client.post(f"{GAP_URL}/analyze", json={
            "brand_domain": domain, "competitor_domains": competitors
        }, timeout=120)
        if resp.status_code == 200:
            data = resp.json()
            job_id = data.get("job_id")
            if job_id:
                for _ in range(20):
                    await asyncio.sleep(4)
                    st = await client.get(f"{GAP_URL}/status/{job_id}")
                    if st.json().get("status") == "completed":
                        dl = await client.get(f"{GAP_URL}/result/{job_id}")
                        gaps_raw = dl.json().get("gaps", [])
                        return [g.get("opportunity", str(g)) for g in gaps_raw]
            return data.get("gaps", [])
        return []
    except Exception as e:
        logger.warning(f"Gap analysis failed: {e}")
        return []


# ── Helper: LLM synthesis ─────────────────────────────────────────────────────

@trace_llm(name="research_synthesis", tags=["research_agent", "llm"])
async def _synthesise(domain: str, crawl: Dict, keywords: List[str],
                      gaps: List[str], depth: str) -> str:
    if not groq_client:
        return "LLM not configured — set GROQ_API_KEY."

    kw_str   = ", ".join(keywords[:15]) or "none found"
    gap_str  = "\n".join(f"- {g}" for g in gaps[:8]) or "- none analyzed"
    title    = crawl.get("title", domain)
    desc     = crawl.get("description", "")

    prompt = f"""You are a senior content strategist. Produce a concise research brief for {domain}.

Website title: {title}
Description: {desc}

Top keywords found: {kw_str}

Competitor content gaps:
{gap_str}

Research depth requested: {depth}

Write a structured brief covering:
1. Brand positioning / market niche (2-3 sentences)
2. Audience signals inferred from keywords
3. Top 3 content opportunities based on gaps
4. Recommended content tone and format
5. 5 specific blog / social post ideas with suggested titles

Keep it concise and actionable."""

    try:
        resp = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=1200,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"LLM synthesis error: {e}")
        return f"Synthesis failed: {e}"


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("research_agent:app", host="0.0.0.0", port=8009, reload=True)
