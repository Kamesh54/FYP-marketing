"""
Brand Agent — port 8006
Manages brand profiles:
  - CRUD via database.py
  - Auto-extract brand signals from a website URL using webcrawler + Groq
  - Merge learned performance signals back into the brand profile
  - Sync new/updated brand data to Neo4j knowledge graph

LangSmith traces every LLM extraction call.
"""

import os
import uuid
import json
import asyncio
import logging
import httpx
import re as _re
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from groq import Groq

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("brand_agent")

from langsmith_tracer import trace_llm, get_current_run_id
from database import (
    save_brand_profile, get_brand_profile, update_brand_profile,
    delete_brand_profile, merge_learned_signals,
    list_brand_profiles,
)
from graph.dual_write_helper import sync_new_brand

GROQ_API_KEY  = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL    = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
WEBCRAWLER_URL = os.getenv("WEBCRAWLER_URL", "http://localhost:8000")
groq_client   = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

app = FastAPI(title="Brand Agent", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
    expose_headers=["*"]
)

from fastapi import Request
from fastapi.responses import JSONResponse

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error on {request.url}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
        headers={"Access-Control-Allow-Origin": "*"},
    )


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/")
def health():
    return {"service": "brand_agent", "port": 8006, "version": "1.0.0", "status": "ok"}


# ── Pydantic models ───────────────────────────────────────────────────────────

class BrandCreateRequest(BaseModel):
    user_id: int
    brand_name: str
    description: Optional[str] = ""
    target_audience: Optional[str] = ""
    tone: Optional[str] = "professional"
    colors: Optional[List[str]] = []
    fonts: Optional[List[str]] = []
    tone_preference: Optional[str] = ""
    industry: Optional[str] = ""
    tagline: Optional[str] = ""
    website_url: Optional[str] = ""


class BrandUpdateRequest(BaseModel):
    description: Optional[str] = None
    target_audience: Optional[str] = None
    tone: Optional[str] = None
    colors: Optional[List[str]] = None
    fonts: Optional[List[str]] = None
    tone_preference: Optional[str] = None
    industry: Optional[str] = None
    tagline: Optional[str] = None
    website_url: Optional[str] = None


class BrandExtractRequest(BaseModel):
    user_id: int
    brand_name: str
    website_url: str


class LearnedSignalsRequest(BaseModel):
    signals: Dict[str, Any]


# ── CRUD endpoints ─────────────────────────────────────────────────────────────

@app.get("/brands/{user_id}")
def list_brands(user_id: int):
    """Return all brand profiles owned by user_id."""
    brands = list_brand_profiles(user_id)
    return {"brands": brands, "count": len(brands)}


@app.get("/brand/{user_id}/{brand_name}")
def get_brand(user_id: int, brand_name: str):
    profile = get_brand_profile(user_id, brand_name)
    if not profile:
        raise HTTPException(404, f"Brand '{brand_name}' not found for user {user_id}")
    return profile


@app.post("/brand", status_code=201)
def create_brand(req: BrandCreateRequest):
    save_brand_profile(
        user_id=req.user_id,
        brand_name=req.brand_name,
        description=req.description,
        target_audience=req.target_audience,
        tone=req.tone,
        colors=req.colors,
        fonts=req.fonts,
        tone_preference=req.tone_preference,
        industry=req.industry,
        tagline=req.tagline,
        website_url=req.website_url,
    )
    # NOTE: sync_new_brand is called internally by save_brand_profile — no duplicate call needed
    return {"status": "created", "brand_name": req.brand_name}


@app.put("/brand/{user_id}/{brand_name}")
def update_brand(user_id: int, brand_name: str, req: BrandUpdateRequest):
    profile = get_brand_profile(user_id, brand_name)
    if not profile:
        raise HTTPException(404, f"Brand '{brand_name}' not found")
    update_data = {k: v for k, v in req.dict().items() if v is not None}
    update_brand_profile(user_id, brand_name, **update_data)
    return {"status": "updated", "brand_name": brand_name, "updated_fields": list(update_data.keys())}


@app.delete("/brand/{user_id}/{brand_name}")
def remove_brand(user_id: int, brand_name: str):
    profile = get_brand_profile(user_id, brand_name)
    if not profile:
        raise HTTPException(404, f"Brand '{brand_name}' not found")
    delete_brand_profile(user_id, brand_name)
    return {"status": "deleted", "brand_name": brand_name}


@app.post("/brand/{user_id}/{brand_name}/signals")
def add_signals(user_id: int, brand_name: str, req: LearnedSignalsRequest):
    """Merge new learned performance signals (from MABO/social) into the brand profile."""
    profile = get_brand_profile(user_id, brand_name)
    if not profile:
        raise HTTPException(404, f"Brand '{brand_name}' not found")
    merge_learned_signals(user_id, req.signals)
    return {"status": "merged", "signals_count": len(req.signals)}


# ── Auto-extract endpoint ──────────────────────────────────────────────────────

@app.post("/brand/extract", status_code=201)
async def extract_and_create(req: BrandExtractRequest):
    """
    Crawl req.website_url, then use LLM to auto-populate brand fields.
    Creates the brand profile and returns it.
    """
    raw_content, visual = await asyncio.gather(
        _crawl_site(req.website_url),
        _extract_visual_assets(req.website_url),
    )
    brand_data  = await _extract_brand_signals(req.brand_name, req.website_url, raw_content)

    # Use LLM-extracted brand_name if it's better than what was passed in
    _PLACEHOLDERS = {"not specified", "not provided", "unknown", "n/a", "", "none"}
    extracted_name = brand_data.pop("brand_name", "").strip()
    final_brand_name = extracted_name if extracted_name and extracted_name.lower() not in _PLACEHOLDERS else req.brand_name

    # Prefer directly-scraped logo/colors over LLM guesses
    final_logo    = visual.get("logo_url") or ""
    final_colors  = visual.get("colors") or brand_data.get("colors", [])

    save_brand_profile(
        user_id=req.user_id,
        brand_name=final_brand_name,
        description=brand_data.get("description", ""),
        target_audience=brand_data.get("target_audience", ""),
        tone=brand_data.get("tone", "professional"),
        colors=final_colors,
        fonts=brand_data.get("fonts", []),
        tone_preference=brand_data.get("tone_preference", ""),
        industry=brand_data.get("industry", ""),
        tagline=brand_data.get("tagline", ""),
        website_url=req.website_url,
        logo_url=final_logo,
        auto_extracted=True,
    )
    # NOTE: sync_new_brand is called internally by save_brand_profile — no duplicate call needed
    return {
        "status": "created",
        "brand_name": final_brand_name,
        "logo_url": final_logo,
        "colors": final_colors,
        "auto_extracted": True,
        "extracted_data": brand_data,
        "langsmith_run_id": get_current_run_id(),
    }


# ── Internal helpers ──────────────────────────────────────────────────────────

import re as _re
from bs4 import BeautifulSoup as _BS

async def _extract_visual_assets(url: str) -> dict:
    """
    Directly fetch the homepage HTML and extract:
    - logo_url: best candidate logo image
    - colors: brand colors from meta theme-color + CSS variables + og:image bg hints
    """
    logo_url = ""
    colors: list = []
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return {"logo_url": "", "colors": []}
            soup = _BS(resp.text, "html.parser")

            # ── Logo detection (priority order) ───────────────────────────
            base = f"{resp.url.scheme}://{resp.url.host}"

            def abs_url(src: str) -> str:
                if not src:
                    return ""
                if src.startswith("http"):
                    return src
                if src.startswith("//"):
                    return "https:" + src
                return base.rstrip("/") + "/" + src.lstrip("/")

            # 1. og:image
            og = soup.find("meta", property="og:image") or soup.find("meta", attrs={"name": "og:image"})
            if og and og.get("content"):
                logo_url = abs_url(og["content"])

            # 2. apple-touch-icon (high-res)
            if not logo_url:
                for rel in ["apple-touch-icon", "apple-touch-icon-precomposed"]:
                    tag = soup.find("link", rel=rel)
                    if tag and tag.get("href"):
                        logo_url = abs_url(tag["href"])
                        break

            # 3. <img> with logo/brand in class, id, alt, or src
            if not logo_url:
                for img in soup.find_all("img"):
                    attrs_str = " ".join([
                        img.get("class", [""])[0] if img.get("class") else "",
                        img.get("id", ""),
                        img.get("alt", ""),
                        img.get("src", ""),
                    ]).lower()
                    if any(k in attrs_str for k in ["logo", "brand", "header-img", "site-logo"]):
                        logo_url = abs_url(img.get("src", ""))
                        break

            # 4. First image inside <header> or <nav>
            if not logo_url:
                for container in soup.find_all(["header", "nav"]):
                    img = container.find("img")
                    if img and img.get("src"):
                        logo_url = abs_url(img["src"])
                        break

            # 5. favicon as last resort
            if not logo_url:
                fav = soup.find("link", rel=lambda r: r and "icon" in " ".join(r).lower())
                if fav and fav.get("href"):
                    logo_url = abs_url(fav["href"])

            # ── Color detection ────────────────────────────────────────────
            # 1. meta theme-color
            tc = soup.find("meta", attrs={"name": "theme-color"})
            if tc and tc.get("content"):
                colors.append(tc["content"].strip())

            # 2. CSS custom properties (--color-*, --brand-*, --primary, etc.) in <style> tags
            hex_pattern = _re.compile(r'(--(?:color|brand|primary|secondary|accent|bg|background)[^:]*)\s*:\s*(#[0-9A-Fa-f]{3,8}|rgba?\([^)]+\))')
            for style_tag in soup.find_all("style"):
                for match in hex_pattern.finditer(style_tag.get_text()):
                    val = match.group(2).strip()
                    if val not in colors:
                        colors.append(val)
                    if len(colors) >= 6:
                        break

            # 3. Standalone hex values in <style> blocks (background-color, color)
            if len(colors) < 3:
                simple_hex = _re.compile(r'(?:background-color|background|color)\s*:\s*(#[0-9A-Fa-f]{6})')
                for style_tag in soup.find_all("style"):
                    for m in simple_hex.finditer(style_tag.get_text()):
                        val = m.group(1)
                        if val.upper() not in [c.upper() for c in colors]:
                            colors.append(val)
                        if len(colors) >= 5:
                            break

    except Exception as e:
        logger.warning(f"Visual asset extraction failed for {url}: {e}")

    return {"logo_url": logo_url, "colors": colors[:6]}


async def _crawl_site(url: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{WEBCRAWLER_URL}/crawl", json={"start_url": url, "max_pages": 5})
            if resp.status_code != 200:
                return ""
            data = resp.json()
            job_id = data.get("job_id")
            if not job_id:
                return ""
            for _ in range(20):
                await asyncio.sleep(3)
                st = await client.get(f"{WEBCRAWLER_URL}/status/{job_id}")
                if st.json().get("status") == "completed":
                    dl = await client.get(f"{WEBCRAWLER_URL}/download/json/{job_id}")
                    if dl.status_code != 200:
                        return ""
                    result = dl.json()
                    # Result is a list of page dicts with headers/paragraphs
                    if isinstance(result, list):
                        return " ".join(
                            [h.get('text', '') for doc in result for h in doc.get('headers', [])] +
                            [p for doc in result for p in doc.get('paragraphs', [])]
                        )
                    elif isinstance(result, dict):
                        return result.get("content", "") or result.get("extracted_text", "")
                    return ""
                if st.json().get("status") == "failed":
                    return ""
            return ""
    except Exception as e:
        logger.warning(f"Crawl failed for {url}: {e}")
        return ""


@trace_llm(name="brand_extraction", tags=["brand_agent", "llm"])
async def _extract_brand_signals(brand_name: str, url: str, content: str) -> Dict[str, Any]:
    """Use Groq to extract structured brand information from crawled content."""
    if not groq_client:
        return {}

    content_snippet = content[:6000]
    # Extract domain as brand name hint
    try:
        from urllib.parse import urlparse as _up
        _domain_hint = _up(url).netloc.replace('www.', '').split('.')[0].replace('-', ' ').replace('_', ' ').title()
    except Exception:
        _domain_hint = brand_name

    prompt = f"""You are a brand analyst. Analyse the following website content for the brand at {url}.

DOMAIN HINT: The website domain suggests the brand name is "{_domain_hint}" — use this if you cannot find the real name in the content.

CONTENT:
{content_snippet}

Return a JSON object with exactly these keys (no extras):
{{
  "brand_name": "The actual brand/company name found in the content, title, or headings. NEVER return 'Not specified' — use the DOMAIN HINT if needed",
  "description": "2-3 sentence brand description",
  "target_audience": "describe the target audience",
  "tone": "one of: professional, casual, playful, authoritative, inspirational",
  "tone_preference": "3-5 adjectives describing the writing style",
  "industry": "industry vertical e.g. 'beauty', 'fintech', 'saas'",
  "tagline": "brand tagline or value proposition if found",
  "colors": ["list of brand hex colors or color names if visible"],
  "fonts": ["list of font names if identifiable"],
  "content_themes": ["3-5 recurring content themes"],
  "unique_value_props": ["up to 3 key differentiators"]
}}

Respond ONLY with valid JSON. No markdown, no explanation."""

    try:
        resp = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=800,
        )
        raw = resp.choices[0].message.content.strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("LLM did not return valid JSON for brand extraction")
        return {}
    except Exception as e:
        logger.error(f"Brand extraction LLM error: {e}")
        return {}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("brand_agent:app", host="0.0.0.0", port=8006, reload=True)
