"""
MABO Demo Runner — port 8020
============================
Simulates N iterations of the full content pipeline and streams live
results to demo_dashboard.html via Server-Sent Events.

Each iteration:
  1. MABO LightweightBO suggests next prompt variant (Gaussian Process UCB)
  2. Content is generated (real call to content_agent:8003, or sample fallback)
  3. Critic evaluates content (sentence-transformer + textstat — no LLM)
  4. Simulated Instagram metrics are computed (deterministic noise model)
  5. Composite reward is computed and fed back to the BO
  6. All data is streamed live to the dashboard

Run:  python demo_runner.py
Open: http://localhost:8020
"""

import os
import json
import uuid
import asyncio
import random
import time
from datetime import datetime
from typing import Dict, Any, List, Optional

import numpy as np
import httpx
import textstat
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

load_dotenv()

CONTENT_AGENT_URL = "http://localhost:8003"
DASHBOARD_FILE    = os.path.join(os.path.dirname(__file__), "demo_dashboard.html")

app = FastAPI(title="MABO Demo Runner", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

# ─── In-memory store ──────────────────────────────────────────────────────────
_runs: Dict[str, Dict] = {}

# ─── Sentence-transformer (shared, loaded once) ───────────────────────────────
import logging as _logging, contextlib as _ctx, io as _io
os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
_logging.getLogger("sentence_transformers").setLevel(_logging.ERROR)
_logging.getLogger("huggingface_hub").setLevel(_logging.ERROR)
with _ctx.redirect_stderr(_io.StringIO()):
    _st = SentenceTransformer("all-MiniLM-L6-v2")


# ═══════════════════════════════════════════════════════════════════════════════
#  LIGHTWEIGHT BAYESIAN OPTIMISER (GP + UCB)
# ═══════════════════════════════════════════════════════════════════════════════

class LightweightBO:
    """
    Minimal Gaussian Process with UCB acquisition function.
    Tracks a 3-dimensional action space:
      dim 0 — prompt style index (0-1)
      dim 1 — tone aggressiveness (0-1)
      dim 2 — content length preference (0-1)
    """

    def __init__(self, dim: int = 3, kappa: float = 1.2, length_scale: float = 0.5):
        self.dim   = dim
        self.kappa = kappa
        self.ls    = length_scale
        self.X: List[np.ndarray] = []
        self.y: List[float]      = []
        self.best_y: float       = -np.inf
        self.best_x: Optional[np.ndarray] = None

    def _rbf(self, X1: np.ndarray, X2: np.ndarray) -> np.ndarray:
        sq = np.sum((X1[:, None] - X2[None, :]) ** 2, axis=2)
        return np.exp(-sq / (2 * self.ls ** 2))

    def observe(self, x: np.ndarray, reward: float):
        self.X.append(x.copy())
        self.y.append(reward)
        if reward > self.best_y:
            self.best_y = reward
            self.best_x = x.copy()

    def suggest_next(self, iteration: int = 0, n_candidates: int = 500):
        """Returns (next_x, mean_space_variance, mu_at_x, effective_kappa).

        Uses a DECAYING kappa schedule: kappa(t) = kappa_max / sqrt(1 + t/tau)
        - Early iterations: high kappa  → broad exploration across the 3D space
        - Later iterations: lower kappa → exploitation of the best discovered region
        - Never reaches 0  → GP retains a small exploration bonus forever,
          preventing permanent lock-in at a local optimum

        mean_space_variance: average posterior variance over a fixed grid —
        measures remaining global uncertainty (decreases as space is covered).
        """
        # Decaying exploration: kappa halves roughly every 15 iterations
        # Floor at 0.5 so exploration never truly dies
        kappa_eff = max(0.5, self.kappa / (1.0 + iteration / 15.0) ** 0.5)

        if len(self.X) < 2:
            x = np.random.uniform(0, 1, self.dim)
            return x, 1.0, 0.0, kappa_eff  # max uncertainty before any observations

        X = np.array(self.X)
        y = np.array(self.y)

        K     = self._rbf(X, X) + 1e-6 * np.eye(len(X))
        K_inv = np.linalg.inv(K)

        # UCB candidates — large set for good coverage
        cands  = np.random.uniform(0, 1, (n_candidates, self.dim))
        k_star = self._rbf(cands, X)

        mu     = k_star @ K_inv @ y
        var    = np.maximum(1.0 - np.sum(k_star @ K_inv * k_star, axis=1), 0.0)
        ucb    = mu + kappa_eff * np.sqrt(var)

        best_idx = int(np.argmax(ucb))
        best_x   = cands[best_idx]
        best_mu  = float(mu[best_idx])

        # Mean variance over a stable fixed grid (same seed every call)
        # This is the correct convergence metric — decreases as space is covered
        grid = np.random.RandomState(0).uniform(0, 1, (150, self.dim))
        k_g  = self._rbf(grid, X)
        var_g = np.maximum(1.0 - np.sum(k_g @ K_inv * k_g, axis=1), 0.0)
        mean_space_var = float(np.mean(var_g))

        return best_x, mean_space_var, best_mu, kappa_eff

    def acquisition_snapshot(self) -> Dict[str, Any]:
        """Return a JSON-serialisable snapshot of the GP state."""
        rewards = self.y
        best_so_far = []
        running_best = -np.inf
        for r in rewards:
            running_best = max(running_best, r)
            best_so_far.append(round(running_best, 4))
        regrets = [round(max(rewards) - r, 4) for r in rewards] if rewards else []
        return {
            "n_observations":  len(rewards),
            "best_reward":     round(self.best_y, 4) if rewards else 0.0,
            "best_x":          self.best_x.tolist() if self.best_x is not None else [],
            "reward_history":  [round(v, 4) for v in rewards],
            "best_so_far":     best_so_far,
            "regret_history":  regrets,
            "mu_at_best":      round(float(np.max(rewards)), 4) if rewards else 0.0,
        }


# ═══════════════════════════════════════════════════════════════════════════════
#  PROMPT TEMPLATES  (5 variants — MABO selects among them)
# ═══════════════════════════════════════════════════════════════════════════════

PROMPT_TEMPLATES = [
    {
        "name": "Benefit-focused CTA",
        "text": "Write a compelling Instagram caption about {topic} that highlights key benefits and ends with a strong call-to-action.",
    },
    {
        "name": "Storytelling + Emojis",
        "text": "Create an engaging Instagram post about {topic} using storytelling, relevant emojis, and popular hashtags.",
    },
    {
        "name": "Emotional Connection",
        "text": "Write a persuasive Instagram caption for {topic}. Focus on emotional connection and authentic brand voice.",
    },
    {
        "name": "Social Proof + Urgency",
        "text": "Generate an Instagram post about {topic} with strong social proof, urgency signals, and a clear CTA.",
    },
    {
        "name": "Question Hook",
        "text": "Craft an Instagram caption about {topic} that opens with a question, lists key benefits, and closes with a CTA.",
    },
]

# ═══════════════════════════════════════════════════════════════════════════════
#  CONTENT BANK — varied quality so MABO can actually optimise
#  Key: (template_idx, quality_tier)  where tier 0=poor, 1=medium, 2=excellent
#
#  Brand context: Sustainable wellness brand — warm, empowering, conscious
#  Intent context: Instagram post for product awareness and sales
#
#  Optimal MABO configuration (hidden ground-truth the GP must discover):
#    Template 2 (Emotional Connection) or 3 (Social Proof)
#    Tone  0.35 – 0.65   (balanced-assertive; wellness brands hate aggression)
#    Length 0.45 – 0.75   (50-70 words is Instagram sweet-spot)
# ═══════════════════════════════════════════════════════════════════════════════

CONTENT_BANK: Dict[tuple, str] = {
    # ── Benefit-focused CTA ────────────────────────────────────────────────────
    (0, 2): (
        "Your skin deserves better. Our new skincare line is formulated with sustainably sourced botanicals "
        "to nourish, protect, and visibly transform your complexion. Lightweight, deeply effective, and "
        "cruelty-free — because conscious beauty should never compromise on results. "
        "Join thousands of empowered consumers who've already made the switch. "
        "Shop the launch now — link in bio. 🌿 #SustainableBeauty #CleanSkincare #WellnessFirst"
    ),
    (0, 1): (
        "Discover our new skincare collection — crafted with natural ingredients and designed for real results. "
        "Gentle on your skin, tough on dullness. Ready to glow sustainably? "
        "Tap the link in bio and shop today! 🌸 #NaturalBeauty #GlowUp #ConsciousSkincare"
    ),
    (0, 0): (
        "New skincare! Buy now. Great results. Shop today. link in bio. #Beauty"
    ),

    # ── Storytelling + Emojis ──────────────────────────────────────────────────
    (1, 2): (
        "✨ Three months ago, Emma had given up finding skincare that aligned with her values. She wanted real results — "
        "without harming the planet. 🌍 Then she discovered our sustainable skincare line and everything changed. "
        "Clinically tested, ethically sourced, genuinely effective — her skin transformed and so did her morning ritual. "
        "Ready to write your own story? 💚 Tap the link in bio to start your conscious skincare journey. "
        "#SustainableBeauty #CleanBeauty #ConsciousConsumer #SkincareJourney"
    ),
    (1, 1): (
        "🌿 We believe beauty and sustainability go hand in hand. "
        "Our new skincare product is packed with natural goodness to give your skin everything it needs. "
        "Try it today — your skin and the planet will thank you! 💚 Link in bio. "
        "#EcoBeauty #NaturalSkincare #GreenBeauty"
    ),
    (1, 0): (
        "✨ New product!! Amazing skincare 🌟 Buy buy buy! Great deal today! Now! #Beauty #Sale #New"
    ),

    # ── Emotional Connection ───────────────────────────────────────────────────
    (2, 2): (
        "Taking care of your skin is an act of self-love. 💛 "
        "At our core, we believe wellness isn't a luxury — it's something every conscious consumer deserves every single day. "
        "Our sustainably crafted skincare collection is designed to empower your daily ritual, "
        "honouring both your body and the world around you. "
        "Every ingredient ethically sourced. Every formula made with genuine intention. "
        "Because you are worth it, and so is the planet. 🌱 "
        "Begin your journey today — link in bio. #ConsciousSkincare #EmpoweredBeauty #SustainableWellness"
    ),
    (2, 1): (
        "Your wellness journey starts with how you treat your skin. 💚 "
        "Our skincare line is gentle, effective, and rooted in sustainable values. "
        "Because feeling good and doing good should never be separate. "
        "Discover the collection — link in bio. #WellnessJourney #CleanBeauty #ConsciousLiving"
    ),
    (2, 0): (
        "Feel good. Look good. Buy skincare. Products. Skin. Wellness. Shop today. Link bio."
    ),

    # ── Social Proof + Urgency ─────────────────────────────────────────────────
    (3, 2): (
        "⭐⭐⭐⭐⭐ Over 12,000 conscious consumers have already transformed their skincare routine with us — "
        "and we are just getting started. "
        "Our sustainably formulated products are flying off the shelves, and for good reason: "
        "real results, ethical sourcing, and an unwavering commitment to your wellness. "
        "Stock is limited at launch — don't miss it. "
        "Shop now via the link in bio and join a community that truly cares. 💚 "
        "#SustainableBeauty #ProvenResults #ConsciousBeauty #LimitedLaunch"
    ),
    (3, 1): (
        "🌟 Trusted by thousands of wellness-conscious shoppers! "
        "Our new skincare launch is already getting incredible reviews and selling fast. "
        "Don't miss out — grab yours via the link in bio before stock runs out! "
        "#SkincareResults #NaturalBeauty #ConsciousSkincare"
    ),
    (3, 0): (
        "Buy now!! Limited stock. Everyone loves it! SALE! Discount skincare! Great product. Buy today. Link."
    ),

    # ── Question Hook ─────────────────────────────────────────────────────────
    (4, 2): (
        "What if your skincare routine could empower you — and make a difference in the world? ✨ "
        "Our sustainably crafted collection is designed for the conscious consumer who refuses to compromise on results or values. "
        "Clinically effective ingredients. Zero harmful chemicals. Packaging that respects the planet. 🌱 "
        "Thousands of inspired customers have already made the switch — their glowing skin speaks for itself. "
        "Ready to feel the difference? Tap the link in bio to begin. "
        "#EmpoweredSkincare #SustainableBeauty #ConsciousWellness"
    ),
    (4, 1): (
        "Is your skincare really working for you — and for the planet? 🌿 "
        "Our new launch combines proven ingredients with sustainable values for a routine you can truly feel good about. "
        "Check it out via the link in bio! #CleanBeauty #ConsciousLiving #NaturalSkincare"
    ),
    (4, 0): (
        "Want better skin? Buy our product. Great skincare? Yes! What are you waiting for? Link in bio. #Skincare"
    ),
}

_TEMPLATE_NAMES = [
    "Benefit-focused CTA",
    "Storytelling + Emojis",
    "Emotional Connection",
    "Social Proof + Urgency",
    "Question Hook",
]


def _quality_tier(template_idx: int, tone: float, length_pref: float) -> int:
    """
    Compute content quality tier (0=poor, 1=medium, 2=excellent) based on
    how well (template, tone, length) matches the brand + intent configuration.

    Ground-truth landscape (encoded here, hidden from the GP):
      • Template 2 (Emotional Connection) and 3 (Social Proof) suit this brand best
      • Tone 0.35–0.65 is ideal (wellness brands penalise aggressive hard-sell)
      • Length 0.45–0.75 produces Instagram-optimal copy (~50-70 words)
    The GP must explore the space and discover these ranges by itself.
    """
    # How well each template naturally fits this sustainable wellness brand
    template_fit = [0.65, 0.60, 1.00, 0.88, 0.75]
    t_fit = template_fit[min(template_idx, 4)]

    # Tone compatibility
    if 0.35 <= tone <= 0.65:
        tone_fit = 1.0
    elif tone < 0.35:
        tone_fit = 0.45 + tone * 1.5          # too soft → moderate penalty
    else:
        tone_fit = max(0.20, 1.0 - (tone - 0.65) * 3.0)  # too aggressive → big penalty for wellness

    # Length compatibility
    if 0.45 <= length_pref <= 0.75:
        len_fit = 1.0
    elif length_pref < 0.45:
        len_fit = max(0.15, length_pref * 2.2)  # too short
    else:
        len_fit = max(0.25, 1.0 - (length_pref - 0.75) * 2.5)  # too long

    score = t_fit * 0.40 + tone_fit * 0.35 + len_fit * 0.25

    if score >= 0.78:
        return 2
    if score >= 0.52:
        return 1
    return 0


# ═══════════════════════════════════════════════════════════════════════════════
#  CONTENT GENERATION
# ═══════════════════════════════════════════════════════════════════════════════

async def generate_content(
    topic: str, prompt: Dict, mabo_point: np.ndarray, iteration: int
) -> str:
    """Generate content via content_agent if available, otherwise use the MABO-aware fallback."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{CONTENT_AGENT_URL}/generate-social",
                json={
                    "topic": topic,
                    "platform": "instagram",
                    "tone": "engaging",
                    "brand_name": "Demo Brand",
                    "custom_instructions": prompt["text"].replace("{topic}", topic),
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                text = data.get("content_text") or data.get("content") or data.get("instagram_copy", "")
                if text and len(text) > 20:
                    return text
    except Exception:
        pass

    # ── MABO-aware fallback ──────────────────────────────────────────────────
    # Content quality depends on the action point chosen by the GP:
    #   mabo_point[0] → prompt template (already resolved to prompt[name])
    #   mabo_point[1] → tone aggressiveness (0=soft, 1=bold)
    #   mabo_point[2] → content length preference (0=short, 1=long)
    # The _quality_tier function encodes the hidden optimum the GP must discover.
    template_idx = _TEMPLATE_NAMES.index(prompt["name"]) if prompt["name"] in _TEMPLATE_NAMES else 0
    tone         = float(mabo_point[1])
    length_pref  = float(mabo_point[2])
    tier         = _quality_tier(template_idx, tone, length_pref)
    return CONTENT_BANK[(template_idx, tier)]


# ═══════════════════════════════════════════════════════════════════════════════
#  CRITIC  (non-LLM — embedding cosine + textstat, same as critic_agent.py)
# ═══════════════════════════════════════════════════════════════════════════════

def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    d = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / d) if d > 1e-8 else 0.0


def evaluate_content(content: str, intent: str, brand: str) -> Dict[str, float]:
    c_emb = _st.encode(content, normalize_embeddings=True)
    i_emb = _st.encode(intent,  normalize_embeddings=True)
    b_emb = _st.encode(brand,   normalize_embeddings=True)

    intent_score = round(min(1.0, max(0.0, _cosine(i_emb, c_emb) * 1.5)), 3)
    brand_score  = round(min(1.0, max(0.0, _cosine(b_emb, c_emb) * 1.5)), 3)

    fk          = textstat.flesch_kincaid_grade(content)
    readability = max(0.0, 1.0 - abs(fk - 9.0) / 14.0)
    words       = [w.lower() for w in content.split() if w.isalpha()]
    wc          = len(words)
    ttr         = len(set(words)) / wc if wc > 0 else 0.5
    length_ok   = 1.0 if wc >= 50 else wc / 50  # Instagram: 50 words is fine
    quality     = round(min(1.0, readability * 0.45 + ttr * 0.35 + length_ok * 0.20), 3)

    overall = round(intent_score * 0.40 + brand_score * 0.35 + quality * 0.25, 3)

    def _band(s: float) -> str:
        if s >= 0.85: return "Excellent"
        if s >= 0.70: return "Good"
        if s >= 0.55: return "Needs improvement"
        return "Poor"

    critique_text = (
        f"Intent alignment is {_band(intent_score)} ({intent_score:.0%}) — "
        f"the content {'closely addresses' if intent_score >= 0.70 else 'loosely addresses'} the campaign goal. "
        f"Brand alignment is {_band(brand_score)} ({brand_score:.0%}) — "
        f"tone {'matches' if brand_score >= 0.70 else 'does not fully match'} the brand profile. "
        f"Quality is {_band(quality)} — readability grade {fk:.1f} "
        f"({'ideal' if 6 <= fk <= 12 else 'too complex' if fk > 12 else 'very simple'} for marketing), "
        f"{wc} words, lexical diversity {ttr:.2f}."
    )

    suggestions = []
    if intent_score < 0.70:
        suggestions.append("Revise content to more directly address the campaign goal.")
    if brand_score < 0.70:
        suggestions.append("Align tone and vocabulary more closely with the brand profile.")
    if fk > 12:
        suggestions.append(f"Simplify sentences — FK grade {fk:.1f} is too complex for Instagram copy.")
    elif fk < 5:
        suggestions.append(f"Add more substance — FK grade {fk:.1f} reads too simply.")
    if ttr < 0.40:
        suggestions.append("Increase vocabulary variety — too many repeated words (low TTR).")
    if wc < 30:
        suggestions.append(f"Content is very short ({wc} words) — Instagram captions perform better with 30–80 words.")
    if not suggestions:
        suggestions.append("No major issues — content meets all quality thresholds.")

    return {
        "intent_score":   intent_score,
        "brand_score":    brand_score,
        "quality_score":  quality,
        "overall_score":  overall,
        "fk_grade":       round(fk, 1),
        "word_count":     wc,
        "ttr":            round(ttr, 3),
        "critique_text":  critique_text,
        "suggestions":    suggestions,
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  SIMULATED INSTAGRAM METRICS
# ═══════════════════════════════════════════════════════════════════════════════

def simulate_ig_metrics(critic_score: float, iteration: int) -> Dict[str, Any]:
    """
    Deterministic per-iteration simulation of Instagram engagement.
    Better critic score → higher base engagement.
    Progressive improvement trend: +5% compound per iteration.
    """
    rng        = random.Random(iteration * 137 + 42)
    trend      = 1.0 + 0.03 * min(iteration, 50)   # cap extended so >10 iterations still improve
    noise      = lambda v: max(1, int(v * (1 + rng.uniform(-0.12, 0.18))))

    base_likes  = 35 + int(critic_score * 130)
    base_reach  = 380 + int(critic_score * 1400)
    base_saves  = 4  + int(critic_score * 38)
    base_shares = 2  + int(critic_score * 20)
    base_comments = 1 + int(critic_score * 12)

    likes    = noise(int(base_likes    * trend))
    reach    = noise(int(base_reach    * trend))
    saves    = noise(int(base_saves    * trend))
    shares   = noise(int(base_shares   * trend))
    comments = noise(int(base_comments * trend))
    eng_rate = round((likes + saves * 3 + shares * 2 + comments) / max(reach, 1) * 100, 2)

    return {
        "likes":           likes,
        "reach":           reach,
        "saves":           saves,
        "shares":          shares,
        "comments":        comments,
        "engagement_rate": eng_rate,
    }


def compute_reward(critic: Dict, ig: Dict) -> float:
    """
    Composite reward fed back to MABO:
      50% — critic overall quality
      30% — normalised engagement rate (cap at 10%)
      20% — saves signal (high-intent indicator)
    """
    return round(
        critic["overall_score"]          * 0.50 +
        min(1.0, ig["engagement_rate"] / 10.0) * 0.30 +
        min(1.0, ig["saves"] / 30.0)           * 0.20,
        4,
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  PIPELINE STAGES  (for trace panel)
# ═══════════════════════════════════════════════════════════════════════════════

PIPELINE_STAGES = [
    "Intent Classification",
    "MABO Prompt Selection",
    "Content Generation",
    "Critic Evaluation",
    "Simulated IG Metrics",
    "Reward Computation",
    "BO Observation Update",
]


# ═══════════════════════════════════════════════════════════════════════════════
#  DEMO LOOP
# ═══════════════════════════════════════════════════════════════════════════════

class DemoConfig(BaseModel):
    topic:      str = "our new skincare product launch"
    brand:      str = "A sustainable wellness brand with a warm, empowering tone for conscious consumers"
    intent:     str = "Create an engaging Instagram post to drive product awareness and sales"
    iterations: int = 8


@app.post("/run")
async def start_run(config: DemoConfig):
    run_id = str(uuid.uuid4())[:8]
    _runs[run_id] = {
        "status":     "queued",
        "config":     config.dict(),
        "iterations": [],
    }
    asyncio.create_task(_execute_run(run_id, config))
    return {"run_id": run_id, "status": "started"}


async def _execute_run(run_id: str, config: DemoConfig):
    run = _runs[run_id]
    run["status"]     = "running"
    run["started_at"] = datetime.now().isoformat()

    bo = LightweightBO(dim=3)

    for i in range(config.iterations):
        t0 = time.time()

        # Stage 1 – MABO suggests action
        if i > 0:
            mabo_point, gp_variance, gp_mu, kappa_eff = bo.suggest_next(iteration=i)
        else:
            mabo_point = np.array([0.5, 0.5, 0.5])
            gp_variance = 1.0  # prior max uncertainty
            gp_mu = 0.0
            kappa_eff = bo.kappa

        # Map dim-0 to prompt template index
        pt_idx  = int(mabo_point[0] * len(PROMPT_TEMPLATES)) % len(PROMPT_TEMPLATES)
        prompt  = PROMPT_TEMPLATES[pt_idx]

        # Stage 2 – Generate content (pass mabo_point so fallback varies with GP choices)
        content = await generate_content(config.topic, prompt, mabo_point, i)

        # Stage 3 – Critic
        critic  = evaluate_content(content, config.intent, config.brand)

        # Stage 4 – Simulated IG metrics
        ig      = simulate_ig_metrics(critic["overall_score"], i)

        # Stage 5 – Reward + BO update
        reward  = compute_reward(critic, ig)
        bo.observe(mabo_point, reward)

        snap = bo.acquisition_snapshot()
        regret = round(snap["best_reward"] - reward, 4) if snap["best_reward"] > -np.inf else 0.0

        iteration_data = {
            "iteration":          i + 1,
            "prompt":             prompt,
            "content":            content,
            "critic":             critic,
            "ig_metrics":         ig,
            "reward":             reward,
            "mabo_point":         mabo_point.tolist(),
            "gp_variance":        round(gp_variance, 4),
            "gp_mu":              round(gp_mu, 4),
            "kappa":              round(kappa_eff, 3),
            "regret":             regret,
            "bo_snapshot":        snap,
            "pipeline_stages":    PIPELINE_STAGES,
            "elapsed_s":          round(time.time() - t0, 2),
            "timestamp":          datetime.now().isoformat(),
        }
        run["iterations"].append(iteration_data)
        await asyncio.sleep(0.6)   # pacing so dashboard updates are visible

    run["status"]        = "completed"
    run["completed_at"]  = datetime.now().isoformat()
    run["best_reward"]   = round(bo.best_y, 4)
    run["best_iteration"] = int(np.argmax(bo.y)) + 1


# ═══════════════════════════════════════════════════════════════════════════════
#  SERVER-SENT EVENTS STREAM
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/stream/{run_id}")
async def stream_run(run_id: str):
    async def generator():
        sent = 0
        while True:
            if run_id not in _runs:
                yield f"data: {json.dumps({'error': 'run not found'})}\n\n"
                break

            run        = _runs[run_id]
            iterations = run["iterations"]

            while sent < len(iterations):
                payload = json.dumps({"type": "iteration", "data": iterations[sent]})
                yield f"data: {payload}\n\n"
                sent += 1

            if run["status"] == "completed":
                final = {
                    "type":           "completed",
                    "best_reward":    run.get("best_reward"),
                    "best_iteration": run.get("best_iteration"),
                    "total":          sent,
                }
                yield f"data: {json.dumps(final)}\n\n"
                break

            await asyncio.sleep(0.2)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/status/{run_id}")
async def get_status(run_id: str):
    if run_id not in _runs:
        return {"error": "not found"}
    r = _runs[run_id]
    return {"status": r["status"], "done": len(r["iterations"]), "config": r["config"]}


# ═══════════════════════════════════════════════════════════════════════════════
#  SERVE DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    with open(DASHBOARD_FILE, encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/health")
def health():
    return {"service": "demo_runner", "port": 8020, "status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("demo_runner:app", host="0.0.0.0", port=8020, reload=False)
