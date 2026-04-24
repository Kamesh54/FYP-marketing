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
try:
    import textstat
except Exception:
    textstat = None

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("critic_agent")

from langsmith_tracer import trace_llm, get_current_run_id, record_critic_feedback
from database import (
    save_critic_log, update_critic_decision, get_critic_log,
    get_recent_critic_logs,
    create_hitl_event, get_brand_profile, get_critic_attempt_count,
)
from llm_failover import groq_chat_with_failover

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL   = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
groq_client  = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

PASS_THRESHOLD = float(os.getenv("CRITIC_PASS_THRESHOLD", "0.70"))

# ── Embedding model for critic evaluation (loaded once, zero API tokens) ────────────────────
os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("HF_HUB_LOCAL_DIR_USE_SYMLINKS", "False")
import contextlib, io as _io
import time

_critic_model = None

def _ensure_critic_model():
    global _critic_model
    if _critic_model is not None:
        return
    logger.info("Loading sentence transformer model for critic (lazy init)...")
    try:
        from sentence_transformers import SentenceTransformer
    except Exception as e:
        logger.warning(f"sentence_transformers unavailable, using fallback critic embeddings: {e}")
        class FallbackEmbedder:
            def encode(self, texts, normalize_embeddings=False):
                single_input = isinstance(texts, str)
                if isinstance(texts, str):
                    texts = [texts]
                import hashlib
                embeddings = []
                for text in texts:
                    hash_val = hashlib.md5(text.encode()).digest()
                    embedding = np.frombuffer(hash_val, dtype=np.float32)[:384]
                    if normalize_embeddings:
                        norm = np.linalg.norm(embedding)
                        if norm > 0:
                            embedding = embedding / norm
                    embeddings.append(embedding)
                return embeddings[0] if single_input else np.array(embeddings)

        _critic_model = FallbackEmbedder()
        return
    logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
    logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
    
    # Retry logic for model download with exponential backoff
    model_names = ["all-MiniLM-L6-v2", "all-MiniLM-L12-v2"]
    last_error = None
    
    for model_name in model_names:
        for attempt in range(3):
            try:
                with contextlib.redirect_stderr(_io.StringIO()):
                    _critic_model = SentenceTransformer(
                        model_name,
                        cache_folder=os.path.join(os.path.expanduser("~"), ".sentence-transformers-cache"),
                        trust_remote_code=True
                    )
                logger.info(f"Successfully loaded model: {model_name}")
                return
            except Exception as e:
                last_error = e
                if attempt < 2:
                    wait_time = 2 ** attempt  # exponential backoff: 1s, 2s, 4s
                    logger.warning(f"Attempt {attempt + 1}/3 failed for {model_name}, retrying in {wait_time}s: {e}")
                    time.sleep(wait_time)
                else:
                    logger.warning(f"Failed to load {model_name}: {e}")
    
    # Fallback: use a simple embedding function if all models fail
    logger.warning(f"Could not load sentence transformer models, using fallback embeddings: {last_error}")
    class FallbackEmbedder:
        def encode(self, texts, normalize_embeddings=False):
            # Simple hash-based embedding as fallback
            single_input = isinstance(texts, str)
            if isinstance(texts, str):
                texts = [texts]
            import hashlib
            embeddings = []
            for text in texts:
                hash_val = hashlib.md5(text.encode()).digest()
                embedding = np.frombuffer(hash_val, dtype=np.float32)[:384]
                if normalize_embeddings:
                    norm = np.linalg.norm(embedding)
                    if norm > 0:
                        embedding = embedding / norm
                embeddings.append(embedding)
            return embeddings[0] if single_input else np.array(embeddings)
    
    _critic_model = FallbackEmbedder()

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
    attempt_number: int
    threshold: float
    decision: str
    intent_score: float
    brand_score: float
    quality_score: float
    overall_score: float
    passed: bool
    critique_text: str
    improvement_suggestions: list
    content_agent_instructions: list
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

    attempt_number = get_critic_attempt_count(req.content_id) + 1

    intent_s = scores["intent"]
    brand_s  = scores["brand"]
    quality_s = scores["quality"]
    overall_s = round((intent_s * 0.4 + brand_s * 0.35 + quality_s * 0.25), 3)
    decision = "approved" if overall_s >= PASS_THRESHOLD else ("rejected" if attempt_number < 3 else "escalate")
    passed = decision == "approved"

    content_agent_instructions = []
    if decision != "approved":
        if intent_s < 0.70:
            content_agent_instructions.append("Rewrite the content to directly satisfy the user's original request and expected output format.")
        if brand_s < 0.70:
            content_agent_instructions.append("Match the stored brand profile: tone, industry language, and unique selling points.")
        if quality_s < 0.70:
            content_agent_instructions.append("Improve readability and structure: clear opening hook, coherent body, and a strong CTA in the conclusion.")
        if req.content_type == "blog":
            content_agent_instructions.append("For blog content, keep target keyword density around 1-3% and maintain natural wording.")

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
        attempt_number=attempt_number,
    )

    # Feed back to LangSmith
    if run_id:
        record_critic_feedback(run_id, intent_s, brand_s, quality_s)

    # Emit HITL event only after max automatic retries have been exhausted.
    hitl_event_id = None
    if decision == "escalate" and req.session_id and req.user_id:
        hitl_event_id = str(uuid.uuid4())
        create_hitl_event(
            event_id=hitl_event_id,
            session_id=req.session_id,
            user_id=req.user_id,
            event_type="critic_review",
            payload={
                "content_id": req.content_id,
                "content_type": req.content_type,
                "overall_score": overall_s,
                "intent_score": intent_s,
                "brand_score": brand_s,
                "quality_score": quality_s,
                "attempt_number": attempt_number,
                "decision": decision,
                "critique_text": critique_text,
                "suggestions": suggestions,
                "content_agent_instructions": content_agent_instructions,
                "original_intent": req.original_intent,
                "content_preview": req.content_text[:500],
            },
        )

    return CriticResponse(
        content_id=req.content_id,
        critic_log_id=log_id,
        attempt_number=attempt_number,
        threshold=PASS_THRESHOLD,
        decision=decision,
        intent_score=intent_s,
        brand_score=brand_s,
        quality_score=quality_s,
        overall_score=overall_s,
        passed=passed,
        critique_text=critique_text,
        improvement_suggestions=suggestions,
        content_agent_instructions=content_agent_instructions,
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
    """
    Evaluates content using sentence-transformer cosine similarity + textstat readability.
    No API tokens consumed.  Runs on CPU in ~5 ms.

    Axes
    ----
    intent_score  — cosine(encode(original_intent), encode(content))  × scale
    brand_score   — cosine(encode(brand_profile),   encode(content))  × scale
    quality_score — Flesch-Kincaid grade + Type–Token Ratio + length bonus
    """
    _ensure_critic_model()
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
    if textstat is not None:
        fk_grade = textstat.flesch_kincaid_grade(content)   # reading-grade level
    else:
        # Fallback approximation when textstat is unavailable.
        approx_words = len([w for w in content.split() if w.strip()])
        sentences = max(1, content.count(".") + content.count("!") + content.count("?"))
        avg_sentence_len = approx_words / sentences if approx_words else 0
        fk_grade = max(1.0, min(16.0, 0.39 * avg_sentence_len + 5.0))
    # Grade 9 is ideal for marketing copy; penalise proportionally for deviation
    readability = max(0.0, 1.0 - abs(fk_grade - 9.0) / 14.0)

    words      = [w.lower() for w in content.split() if w.isalpha()]
    word_count = len(words)
    ttr        = (len(set(words)) / word_count) if word_count > 0 else 0.5  # lexical diversity
    length_ok  = 1.0 if word_count >= 300 else (word_count / 300)

    # Structural coherence: basic intro/body/conclusion heuristic
    paragraphs = [p.strip() for p in content.split("\n") if p.strip()]
    has_intro = len(paragraphs) >= 1 and len(paragraphs[0].split()) >= 8
    has_body = len(paragraphs) >= 2
    has_conclusion = any(k in content.lower() for k in ["in conclusion", "to summarize", "overall", "finally"])
    structure_score = (0.35 if has_intro else 0.0) + (0.35 if has_body else 0.0) + (0.30 if has_conclusion else 0.0)

    # Engagement potential: hook + CTA
    cta_terms = ["learn more", "sign up", "get started", "contact us", "try now", "book", "shop now", "discover"]
    has_cta = any(t in content.lower() for t in cta_terms)
    hook_terms = ["did you know", "imagine", "what if", "struggling", "ready to", "introducing"]
    has_hook = any(t in content.lower() for t in hook_terms) or (len(paragraphs) > 0 and paragraphs[0].endswith("?"))
    engagement_score = (0.5 if has_hook else 0.0) + (0.5 if has_cta else 0.0)

    # Keyword density for blogs: target around 1-3%
    keyword_density_score = 0.7
    if req.content_type == "blog":
        intent_terms = [w.lower() for w in req.original_intent.split() if w.isalpha() and len(w) > 3]
        intent_terms = list(dict.fromkeys(intent_terms))[:6]
        if intent_terms and word_count > 0:
            hit_count = sum(1 for w in words if w in intent_terms)
            density = (hit_count / max(word_count, 1)) * 100
            if 1.0 <= density <= 3.0:
                keyword_density_score = 1.0
            elif 0.6 <= density < 1.0 or 3.0 < density <= 4.0:
                keyword_density_score = 0.75
            else:
                keyword_density_score = 0.45

    quality_score = round(
        min(
            1.0,
            readability * 0.26
            + ttr * 0.20
            + length_ok * 0.14
            + structure_score * 0.20
            + engagement_score * 0.12
            + keyword_density_score * 0.08,
        ),
        3,
    )

    # Banned words / off-brand language penalty
    banned_words = [w.strip().lower() for w in os.getenv("CRITIC_BANNED_WORDS", "").split(",") if w.strip()]
    if banned_words:
        low = content.lower()
        banned_hits = [w for w in banned_words if w in low]
        if banned_hits:
            brand_score = max(0.0, round(brand_score - min(0.25, 0.05 * len(banned_hits)), 3))

    # Optional LLM review to strengthen semantic assessment and actionable feedback.
    if groq_client:
        try:
            llm_prompt = f"""Evaluate the content with this rubric and return JSON only.

User intent: {req.original_intent}
Brand context:\n{brand_context or 'N/A'}
Content type: {req.content_type}
Content:\n{content[:3000]}

Return JSON with keys:
intent_score (0..1), brand_score (0..1), quality_score (0..1), critique_text, suggestions (array of strings).
Focus checks:
- Intent fulfillment.
- Brand tone, language, USP consistency.
- Grammar/readability, structure, keyword density (1-3% for blog), engagement hook+CTA.
"""
            llm_resp, _used_model = groq_chat_with_failover(
                groq_client,
                messages=[{"role": "user", "content": llm_prompt}],
                primary_model=GROQ_MODEL,
                logger=logger,
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=700,
            )
            llm_data = json.loads(llm_resp.choices[0].message.content)
            li = float(llm_data.get("intent_score", intent_score))
            lb = float(llm_data.get("brand_score", brand_score))
            lq = float(llm_data.get("quality_score", quality_score))

            # Blend deterministic and LLM signals for robustness.
            intent_score = round(min(1.0, max(0.0, intent_score * 0.6 + li * 0.4)), 3)
            brand_score = round(min(1.0, max(0.0, brand_score * 0.6 + lb * 0.4)), 3)
            quality_score = round(min(1.0, max(0.0, quality_score * 0.6 + lq * 0.4)), 3)
        except Exception as llm_err:
            logger.warning(f"LLM critic augmentation skipped: {llm_err}")

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
    if structure_score < 0.7:
        suggestions.append("Improve structure with clear intro, body, and conclusion sections.")
    if engagement_score < 0.5:
        suggestions.append("Add a stronger opening hook and explicit call-to-action (CTA).")
    if req.content_type == "blog" and keyword_density_score < 0.7:
        suggestions.append("Adjust target keyword density closer to 1-3% for blog content.")

    scores = {"intent": intent_score, "brand": brand_score, "quality": quality_score}
    return scores, critique_text, suggestions


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("critic_agent:app", host="0.0.0.0", port=8007, reload=True)
