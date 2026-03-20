"""
Critic Agent — port 8007
Evaluates generated content against three axes:
  - Intent alignment  (0-1): does it fulfil the user's stated goal?
  - Brand alignment   (0-1): voice, tone, values match the brand profile?
  - Quality score     (0-1): grammar, coherence, engagement, SEO basics

If overall_score >= threshold, mark as "passed".
Otherwise emit a HITL event so the user can approve / reject / edit.

Scores are saved to critic_logs table and fed back to LangSmith for MABO.
"""

import os
import json
import uuid
import logging
import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from groq import Groq
import numpy as np
from sentence_transformers import SentenceTransformer
import textstat

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("critic_agent")

from langsmith_tracer import trace_llm, get_current_run_id, record_critic_feedback
from database import (
    save_critic_log, update_critic_decision, get_critic_log,
    get_recent_critic_logs,
    create_hitl_event, get_brand_profile,
)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL   = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
groq_client  = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

PASS_THRESHOLD = float(os.getenv("CRITIC_PASS_THRESHOLD", "0.70"))

# ── Embedding model for critic evaluation (loaded once, zero API tokens) ────────────────────
os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
import contextlib, io as _io
logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)


class _HashingSentenceEncoder:
    """Lightweight local fallback when the transformer model is unavailable."""

    def __init__(self, dim: int = 384):
        self.dim = dim

    def encode(self, text: str, normalize_embeddings: bool = True):
        vec = np.zeros(self.dim, dtype=np.float32)
        tokens = re.findall(r"\w+", (text or "").lower())
        if not tokens:
            return vec

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "big") % self.dim
            sign = 1.0 if (digest[4] % 2 == 0) else -1.0
            vec[idx] += sign

        if normalize_embeddings:
            norm = np.linalg.norm(vec)
            if norm > 1e-8:
                vec = vec / norm
        return vec


def _load_critic_model():
    """Load a cached transformer if available; otherwise degrade gracefully."""
    try:
        with contextlib.redirect_stderr(_io.StringIO()):
            model = SentenceTransformer("all-MiniLM-L6-v2", local_files_only=True)
        logger.info("Critic embedding model loaded from local cache")
        return model
    except Exception as cached_exc:
        logger.warning("Cached critic embedding model unavailable: %s", cached_exc)

    try:
        with contextlib.redirect_stderr(_io.StringIO()):
            model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("Critic embedding model downloaded successfully")
        return model
    except Exception as download_exc:
        logger.warning(
            "Falling back to local hashing encoder because SentenceTransformer could not be loaded: %s",
            download_exc,
        )
        return _HashingSentenceEncoder()


_critic_model = _load_critic_model()

def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors."""
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.dot(a, b) / denom) if denom > 1e-8 else 0.0

app = FastAPI(title="Critic Agent", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


# ── Models ────────────────────────────────────────────────────────────────────

class CriticRequest(BaseModel):
    content_id: str
    session_id: Optional[str] = None
    user_id: Optional[int] = None
    content_text: str
    original_intent: str           # what the user asked for, e.g. "blog post about vegan skincare"
    content_type: str = "blog"     # blog | social_post | email | ad_copy
    brand_name: Optional[str] = None
    target_platform: Optional[str] = None


class CriticResponse(BaseModel):
    content_id: str
    critic_log_id: Optional[int] = None
    intent_score: float
    brand_score: float
    quality_score: float
    overall_score: float
    passed: bool
    critique_text: str
    improvement_suggestions: list
    hitl_event_id: Optional[str] = None
    langsmith_run_id: Optional[str] = None


class HitlDecisionRequest(BaseModel):
    decision: str                  # approved | rejected | edited
    edited_content: Optional[str] = None


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/")
def health():
    return {"service": "critic_agent", "port": 8007, "version": "1.0.0",
            "pass_threshold": PASS_THRESHOLD, "status": "ok"}


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    """Serve the critic results dashboard."""
    html_path = Path(__file__).parent / "critic_dashboard.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


# ── Critique endpoint ─────────────────────────────────────────────────────────

@app.post("/critique", response_model=CriticResponse)
async def critique(req: CriticRequest):
    # Load brand profile for context
    brand_context = ""
    if req.user_id and req.brand_name:
        profile = get_brand_profile(req.user_id, req.brand_name)
        if profile:
            brand_context = (
                f"Brand: {profile.get('brand_name', req.brand_name)}\n"
                f"Tone: {profile.get('tone', 'professional')}\n"
                f"Industry: {profile.get('industry', '')}\n"
                f"Target audience: {profile.get('target_audience', '')}\n"
                f"Tagline: {profile.get('tagline', '')}"
            )

    scores, critique_text, suggestions = await _evaluate(req, brand_context)

    intent_s = scores["intent"]
    brand_s  = scores["brand"]
    quality_s = scores["quality"]
    overall_s = round((intent_s * 0.4 + brand_s * 0.35 + quality_s * 0.25), 3)
    passed    = overall_s >= PASS_THRESHOLD

    run_id = get_current_run_id()

    # Persist
    log_id = save_critic_log(
        content_id=req.content_id,
        session_id=req.session_id,
        intent_score=intent_s,
        brand_score=brand_s,
        quality_score=quality_s,
        overall_score=overall_s,
        critique_text=critique_text,
        passed=passed,
        langsmith_run_id=run_id,
    )

    # Feed back to LangSmith
    if run_id:
        record_critic_feedback(run_id, intent_s, brand_s, quality_s)

    # Emit HITL event if not passed
    hitl_event_id = None
    if not passed and req.session_id and req.user_id:
        hitl_event_id = str(uuid.uuid4())
        create_hitl_event(
            event_id=hitl_event_id,
            session_id=req.session_id,
            user_id=req.user_id,
            event_type="content_review",
            payload={
                "content_id": req.content_id,
                "content_type": req.content_type,
                "overall_score": overall_s,
                "critique_text": critique_text,
                "suggestions": suggestions,
                "original_intent": req.original_intent,
                "content_preview": req.content_text[:500],
            },
        )

    return CriticResponse(
        content_id=req.content_id,
        critic_log_id=log_id,
        intent_score=intent_s,
        brand_score=brand_s,
        quality_score=quality_s,
        overall_score=overall_s,
        passed=passed,
        critique_text=critique_text,
        improvement_suggestions=suggestions,
        hitl_event_id=hitl_event_id,
        langsmith_run_id=run_id,
    )


@app.post("/decision/{content_id}")
def record_decision(content_id: str, req: HitlDecisionRequest):
    """Record the user's HITL decision for a content piece."""
    if req.decision not in ("approved", "rejected", "edited"):
        raise HTTPException(400, "decision must be 'approved', 'rejected', or 'edited'")
    update_critic_decision(content_id, req.decision)
    return {"status": "recorded", "content_id": content_id, "decision": req.decision}


@app.get("/log/{content_id}")
def get_log(content_id: str):
    log = get_critic_log(content_id)
    if not log:
        raise HTTPException(404, f"No critic log for content {content_id}")
    return log


@app.get("/logs")
def list_logs(limit: int = 100):
    """Return recent critic evaluations (newest first), joined with content metadata."""
    return get_recent_critic_logs(limit=limit)


# ── Non-LLM evaluation (embeddings + readability math) ───────────────────────

@trace_llm(name="critic_evaluation", tags=["critic_agent", "embedding"])
async def _evaluate(req: CriticRequest, brand_context: str):
   
    content = req.content_text[:4000]
    content_emb = _critic_model.encode(content, normalize_embeddings=True)

    # — Intent alignment ———————————————————————————————————————————————————————
    intent_emb  = _critic_model.encode(req.original_intent, normalize_embeddings=True)
    # Raw cosine between semantically related texts is typically 0.4–0.8;
    # multiply by 1.5 then clip to [0, 1] to spread the useful range.
    intent_score = round(min(1.0, max(0.0, _cosine(intent_emb, content_emb) * 1.5)), 3)

    # — Brand alignment ————————————————————————————————————————————————————————
    if brand_context and brand_context.strip():
        brand_emb   = _critic_model.encode(brand_context, normalize_embeddings=True)
        brand_score = round(min(1.0, max(0.0, _cosine(brand_emb, content_emb) * 1.5)), 3)
    else:
        brand_score = 0.70   # neutral default — no brand profile to compare against

    # — Quality score (computational linguistics) ——————————————————————————————
    fk_grade    = textstat.flesch_kincaid_grade(content)   # reading-grade level
    # Grade 9 is ideal for marketing copy; penalise proportionally for deviation
    readability = max(0.0, 1.0 - abs(fk_grade - 9.0) / 14.0)

    words      = [w.lower() for w in content.split() if w.isalpha()]
    word_count = len(words)
    ttr        = (len(set(words)) / word_count) if word_count > 0 else 0.5  # lexical diversity
    length_ok  = 1.0 if word_count >= 300 else (word_count / 300)

    quality_score = round(
        min(1.0, readability * 0.45 + ttr * 0.35 + length_ok * 0.20), 3
    )

    # — Human-readable critique ————————————————————————————————————————————————
    def _band(s: float) -> str:
        if s >= 0.85: return "excellent"
        if s >= 0.70: return "good"
        if s >= 0.55: return "needs improvement"
        return "poor"

    critique_text = (
        f"Intent alignment is {_band(intent_score)} ({intent_score:.2f}). "
        f"Brand alignment is {_band(brand_score)} ({brand_score:.2f}). "
        f"Content quality is {_band(quality_score)} — "
        f"readability grade {fk_grade:.1f}, lexical diversity {ttr:.2f}, "
        f"{word_count} words."
    )

    suggestions = []
    if intent_score < 0.70:
        suggestions.append("Revise the content to more directly address the original goal.")
    if brand_score < 0.70:
        suggestions.append("Align tone and vocabulary more closely with the brand profile.")
    if readability < 0.50:
        complexity = "too complex" if fk_grade > 12 else "too simple"
        suggestions.append(
            f"Adjust sentence structure — Flesch-Kincaid grade {fk_grade:.1f} is {complexity} for marketing copy."
        )
    if ttr < 0.40:
        suggestions.append("Increase vocabulary variety to improve engagement (low type-token ratio).")
    if word_count < 300:
        suggestions.append(f"Content is short ({word_count} words) — consider expanding to at least 300 words.")

    scores = {"intent": intent_score, "brand": brand_score, "quality": quality_score}
    return scores, critique_text, suggestions


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("critic_agent:app", host="0.0.0.0", port=8007, reload=True)
