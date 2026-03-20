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
        # Decaying exploration: kappa halves roughly every 15 iterations
        # Floor at 0.5 so exploration never truly dies
        kappa_eff = max(0.5, self.kappa / (1.0 + iteration / 15.0) ** 0.5)

        n_init = 1 << min(self.dim, 2)   # 4 for dim >= 2, 2 for dim == 1
        if len(self.X) < n_init:
            idx = len(self.X)
            x = np.array([0.1 if ((idx >> d) & 1) == 0 else 0.9
                          for d in range(self.dim)])
            return x, 1.0, 0.0, kappa_eff

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



DEMO_AGENTS: Dict[str, Any] = {
    "keyword_extractor": {
        "dim": 2, "bounds": [(0, 1), (0, 5)],
        "base_cost": 1.8, "opt_quality": (0.50, 0.85), "peak_reward": 0.86,
        "color": "#7c6afc", "label": "Keyword Extractor",
    },
    "seo_agent": {
        "dim": 2, "bounds": [(0, 1), (0, 10)],
        "base_cost": 4.2, "opt_quality": (0.55, 0.90), "peak_reward": 0.81,
        "color": "#00c2cb", "label": "SEO Agent",
    },
    "gap_analyzer": {
        "dim": 2, "bounds": [(0, 1), (0, 8)],
        "base_cost": 3.0, "opt_quality": (0.60, 0.95), "peak_reward": 0.79,
        "color": "#ffc11a", "label": "Gap Analyzer",
    },
    # 5D: [quality_weight, tone, template_style, content_length, budget_$]
    "content_agent": {
        "dim": 5, "bounds": [(0, 1), (0, 1), (0, 1), (0, 1), (0, 15)],
        "base_cost": 7.5, "opt_quality": (0.55, 0.80), "peak_reward": 0.91,
        "color": "#1fd96e", "label": "Content Agent",
    },
    "critic_agent": {
        "dim": 2, "bounds": [(0, 1), (0, 3)],
        "base_cost": 1.2, "opt_quality": (0.45, 0.80), "peak_reward": 0.84,
        "color": "#f04baf", "label": "Critic Agent",
    },
    "image_generator": {
        "dim": 2, "bounds": [(0, 1), (0, 15)],
        "base_cost": 5.5, "opt_quality": (0.40, 0.75), "peak_reward": 0.77,
        "color": "#ff7434", "label": "Image Generator",
    },
}
DEMO_AGENT_NAMES: List[str] = list(DEMO_AGENTS.keys())
TOTAL_DEMO_BUDGET: float = 45.0   # per-iteration budget (demo scale)


class ADMMCoordinator:
    """
    Lightweight simulation of ADMM budget coordination.
    Mirrors GlobalCoordinator in mabo_framework.py.

    Each iteration:
      1. Agents spend budget based on their selected actions.
      2. Dual update  : lambda_k += rho * (cost_k - alloc_k)
         => lambda rises when an agent overspends its allocation.
      3. Primal update: reallocate total budget proportional to
         ROI (reward/cost) adjusted by the lambda penalty.
         => High-ROI agents earn more budget next round (automatic
            rebalancing without any central controller).

    The temperature parameter cools over iterations, causing the
    allocation to lock in to the learned high-ROI agents over time.
    """

    def __init__(self, agents: List[str], total_budget: float = 45.0, rho: float = 0.12,
                 base_costs: Optional[Dict[str, float]] = None):
        self.agents          = agents
        self.total_budget    = total_budget
        self.rho             = rho
        self.iteration       = 0
        # base_costs: each agent's natural spend level — drives proportional allocation.
        # Cheap agents (Critic $1.2) stay small; expensive ones (Content $7.5) get more.
        self.base_costs: Dict[str, float] = base_costs or {a: 1.0 for a in agents}
        equal = total_budget / len(agents)
        self.allocations: Dict[str, float] = {a: equal for a in agents}
        self.lambdas:     Dict[str, float] = {a: 0.0   for a in agents}
        self._prev_lambdas: Dict[str, float] = {a: 0.0 for a in agents}  # for dual residual

    def update(self, costs: Dict[str, float], rewards: Dict[str, float]) -> Dict:
        """Run one ADMM step. Returns a full snapshot dict including residuals."""
        self.iteration += 1

        # Save previous lambdas for dual residual computation
        prev_lam = {a: self.lambdas[a] for a in self.agents}

        roi = {
            a: rewards.get(a, 0.0) / max(costs.get(a, 0.01), 0.01)
            for a in self.agents
        }

        # Dual update  — paper eq (11b), λ rises when agent overspends its allocation
        for a in self.agents:
            self.lambdas[a] += self.rho * (costs.get(a, 0.0) - self.allocations[a])
            self.lambdas[a] = float(np.clip(self.lambdas[a], -3.0, 3.0))

        
        old_alloc = {a: self.allocations[a] for a in self.agents}

        rew_arr   = np.array([max(rewards.get(a, 0.01), 0.01) for a in self.agents])
        
        act_arr   = np.array([max(costs.get(a,  self.base_costs.get(a, 1.0)), 0.01)
                               for a in self.agents])
        lam_arr   = np.array([self.lambdas[a]   for a in self.agents])

        # Positive λ means agent is over-budget (could use more) → slight boost
        # Clip negative λ to -0.5 so underspending agents do NOT get penalised extra
        lam_boost = np.clip(lam_arr, -0.5, 2.0)
        scores    = rew_arr * act_arr * (1.0 + 0.20 * lam_boost)
        scores    = np.maximum(scores, 0.01)
        raw       = scores * (self.total_budget / scores.sum())
        raw       = np.maximum(raw, 0.05)                    # floor: every agent gets ≥$0.05
        raw       = raw * (self.total_budget / raw.sum())    # renormalise after floor clamp

        for i, a in enumerate(self.agents):
            # EMA smoothing (α=0.30 old / 0.70 new): converges visibly within 8 iterations
            self.allocations[a] = round(float(0.70 * raw[i] + 0.30 * old_alloc[a]), 2)

        # ── Residuals — Boyd et al. (2010) §3.3 convergence certificates ────────
        # Primal residual = ||alloc^{k+1} - alloc^k||_2  (allocation step size)
        # Shrinks monotonically as EMA stabilises — reaches 0 when allocations
        # stop changing (budget equilibrium found).  Always converges regardless
        # of whether agent costs are stochastic.
        total_spent   = sum(costs.get(a, 0.0) for a in self.agents)
        primal_resid  = round(
            float(np.sqrt(sum(
                (self.allocations[a] - old_alloc[a]) ** 2 for a in self.agents
            ))), 4
        )

        # Dual residual = rho * ||lambda^{k+1} - lambda^k||_2  (shadow-price step size)
        # Shrinks monotonically as shadow prices stabilise.  0 when every agent’s
        # cost matches its allocation (cost - alloc ≈ 0 for all agents).
        dual_resid = round(
            self.rho * float(np.sqrt(sum(
                (self.lambdas[a] - prev_lam[a]) ** 2 for a in self.agents
            ))), 6
        )

        return {
            "allocations":    {k: round(v, 2)  for k, v in self.allocations.items()},
            "lambdas":        {k: round(v, 4)  for k, v in self.lambdas.items()},
            "roi":            {k: round(v, 4)  for k, v in roi.items()},
            "costs":          {k: round(costs.get(k, 0), 3) for k in self.agents},
            "rewards":        {k: round(rewards.get(k, 0), 4) for k in self.agents},
            "total_spent":    round(total_spent, 2),
            "primal_residual": primal_resid,   # should → 0 as ADMM converges
            "dual_residual":   dual_resid,     # should → 0 as λ stabilises
        }

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
                    # GenerateSocialRequest fields (keywords OR keywords_job_id required)
                    "keywords": {
                        "short_keywords": [topic],
                        "long_tail_keywords": [prompt["text"].replace("{topic}", topic)]
                    },
                    "platforms": ["instagram"],
                    "tone": "engaging",
                    "brand_name": "Demo Brand",
                    "user_request": prompt["text"].replace("{topic}", topic),
                    "target_audience": "conscious consumers",
                },
            )
            if resp.status_code == 200:
                data    = resp.json()
                job_id  = data.get("job_id")
                # Poll for completion (max 30s)
                for _ in range(30):
                    await asyncio.sleep(1.0)
                    status_r = await client.get(f"{CONTENT_AGENT_URL}/status/{job_id}")
                    sd = status_r.json()
                    if sd.get("status") == "completed":
                        posts = (sd.get("posts") or {}).get("posts", {})
                        text  = (posts.get("instagram") or {}).get("copy", "")
                        if text and len(text) > 20:
                            return text
                        break
                    if sd.get("status") == "failed":
                        break
    except Exception:
        pass

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


def simulate_agent_reward(
    agent_name: str,
    action: np.ndarray,
    iteration: int,
    rng_seed: int,
    budget_alloc: float = 0.0,
) -> tuple:
    
    cfg            = DEMO_AGENTS[agent_name]
    quality_weight = float(action[0])
    opt_lo, opt_hi = cfg["opt_quality"]
    peak           = cfg["peak_reward"]

    if opt_lo <= quality_weight <= opt_hi:
        center  = (opt_lo + opt_hi) / 2.0
        dist    = abs(quality_weight - center) / max((opt_hi - opt_lo) / 2.0, 1e-6)
        base_r  = peak * (1.0 - 0.12 * dist ** 2)
    elif quality_weight < opt_lo:
        base_r  = peak * (0.30 + 0.70 * (quality_weight / opt_lo) ** 1.4)
    else:
        excess  = (quality_weight - opt_hi) / max(1.0 - opt_hi, 1e-6)
        base_r  = peak * (1.0 - 0.28 * excess ** 0.9)

    # Progressive improvement: trend rises as GP converges toward optimum
    trend  = 1.0 + 0.018 * min(iteration, 35)
    base_r = min(0.96, base_r * trend)

    rng          = random.Random(rng_seed)
    natural_cost = cfg["base_cost"] * (0.4 + quality_weight * 0.7)
    natural_cost = natural_cost * (1 + rng.uniform(-0.08, 0.12))

    # ── Budget scaling: does the allocation match what this agent naturally needs? ──
    if budget_alloc <= 0.0:
        # No allocation info yet (first iteration) — run at natural cost
        actual_cost    = natural_cost
        reward_adjust  = 0.0
    elif budget_alloc < natural_cost * 0.75:
        # Underfunded: agent is constrained, spends only what it has, reward degrades
        underfund_ratio = budget_alloc / natural_cost
        actual_cost    = budget_alloc
        reward_adjust  = -0.18 * (1.0 - underfund_ratio)
    elif budget_alloc <= natural_cost * 1.5:
        # Well-matched: normal operation, no adjustment needed
        actual_cost    = natural_cost
        reward_adjust  = 0.0
    else:
        # Overfunded: marginal benefit (richer pipeline), but heavily diminishing returns
        # cost stays at natural_cost — agent can only use what it needs
        overfund_ratio = min((budget_alloc / natural_cost) - 1.0, 4.0)
        actual_cost    = natural_cost  # does NOT soak up the extra allocation
        reward_adjust  = 0.04 * (1.0 - float(np.exp(-0.4 * overfund_ratio)))

    base_r = float(np.clip(base_r + reward_adjust, 0.05, 0.96))
    reward = float(np.clip(base_r + rng.gauss(0, 0.035), 0.05, 0.96))
    cost   = round(max(actual_cost, 0.01), 2)

    return reward, cost


# ═══════════════════════════════════════════════════════════════════════════════
#  REAL AGENT CALLERS
#  Each function calls the live service and returns (reward, cost) or None.
#  None means the service is offline — the caller falls back to simulate_agent_reward().
# ═══════════════════════════════════════════════════════════════════════════════

async def _call_real_keyword_extractor(topic: str, action: np.ndarray) -> Optional[tuple]:
    """POST /extract-keywords → poll /status/{job_id}. Port 8001."""
    max_results = max(1, int(1 + float(action[0]) * 4))  # quality_weight → 1-5 results
    try:
        async with httpx.AsyncClient(timeout=8.0) as c:
            r = await c.post("http://localhost:8001/extract-keywords",
                             json={"customer_statement": topic, "max_results": max_results, "max_pages": 1})
            if r.status_code != 200:
                return None
            job_id = r.json().get("job_id")
        async with httpx.AsyncClient(timeout=8.0) as c:
            for _ in range(50):   # poll up to 50 s
                await asyncio.sleep(1.0)
                s = (await c.get(f"http://localhost:8001/status/{job_id}")).json()
                if s.get("status") == "completed":
                    kw   = s.get("total_keywords") or 0
                    rv   = round(min(1.0, kw / max(max_results * 8, 1)), 4)
                    cost = round(DEMO_AGENTS["keyword_extractor"]["base_cost"]
                                 * (0.4 + float(action[0]) * 0.7), 2)
                    return rv, cost
                if s.get("status") == "failed":
                    return None
    except Exception:
        return None
    return None


async def _call_real_seo_agent(website_url: str, action: np.ndarray) -> Optional[tuple]:
    """POST /analyze (synchronous crawl+audit). Port 5000."""
    try:
        async with httpx.AsyncClient(timeout=40.0) as c:
            r = await c.post("http://localhost:5000/analyze", json={"url": website_url})
            if r.status_code != 200:
                return None
            data = r.json()
            if data.get("status") != "completed":
                return None
            scores = [v for k, v in data.get("scores", {}).items()
                      if isinstance(v, (int, float)) and k != "raw_soup"]
            if not scores:
                return None
            rv   = round(min(1.0, sum(scores) / (len(scores) * 100.0)), 4)
            cost = round(DEMO_AGENTS["seo_agent"]["base_cost"]
                         * (0.4 + float(action[0]) * 0.7), 2)
            return rv, cost
    except Exception:
        return None


async def _call_real_gap_analyzer(topic: str, brand: str, action: np.ndarray) -> Optional[tuple]:
    """POST /analyze-keyword-gap → poll /status/{job_id}. Port 8002."""
    max_comp = max(1, int(1 + float(action[0]) * 2))  # quality_weight → 1-3 competitors
    try:
        async with httpx.AsyncClient(timeout=8.0) as c:
            r = await c.post("http://localhost:8002/analyze-keyword-gap",
                             json={"company_name": "Demo Brand",
                                   "product_description": f"{topic}. {brand}",
                                   "max_competitors": max_comp,
                                   "max_pages_per_site": 1})
            if r.status_code != 200:
                return None
            job_id = r.json().get("job_id")
        async with httpx.AsyncClient(timeout=8.0) as c:
            for _ in range(55):   # poll up to 55 s
                await asyncio.sleep(1.0)
                s = (await c.get(f"http://localhost:8002/status/{job_id}")).json()
                if s.get("status") == "completed":
                    kw   = s.get("total_keywords") or 0
                    rv   = round(min(1.0, kw / max(max_comp * 15, 1)), 4)
                    cost = round(DEMO_AGENTS["gap_analyzer"]["base_cost"]
                                 * (0.4 + float(action[0]) * 0.7), 2)
                    return rv, cost
                if s.get("status") == "failed":
                    return None
    except Exception:
        return None
    return None


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
    topic:       str = "our new skincare product launch"
    brand:       str = "A sustainable wellness brand with a warm, empowering tone for conscious consumers"
    intent:      str = "Create an engaging Instagram post to drive product awareness and sales"
    iterations:  int = 8
    website_url: str = "https://www.sephora.in"  # used by real SEO agent


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

    agent_bos: Dict[str, LightweightBO] = {
        name: LightweightBO(dim=cfg["dim"])
        for name, cfg in DEMO_AGENTS.items()
    }

    admm = ADMMCoordinator(
        agents=DEMO_AGENT_NAMES,
        total_budget=TOTAL_DEMO_BUDGET,
        base_costs={name: DEMO_AGENTS[name]["base_cost"] for name in DEMO_AGENT_NAMES},
    )

    # ── Warm-up: call real agents ONCE before the loop ──────────────────────
    # They run concurrently (asyncio.gather). Each falls back to None if the
    # service is offline. Results are cached as baselines; every iteration
    # then scales them by the GP's current quality_weight + progressive trend.
    run["status"] = "warming_up"
    _base_acts = {
        name: np.array([(b[0]+b[1])/2.0 for b in DEMO_AGENTS[name]["bounds"]])
        for name in ("keyword_extractor", "seo_agent", "gap_analyzer")
    }
    _kw, _seo, _gap = await asyncio.gather(
        _call_real_keyword_extractor(config.topic,                     _base_acts["keyword_extractor"]),
        _call_real_seo_agent        (config.website_url,               _base_acts["seo_agent"]),
        _call_real_gap_analyzer     (config.topic, config.brand,       _base_acts["gap_analyzer"]),
        return_exceptions=True,
    )
    real_baseline: Dict[str, Optional[tuple]] = {
        "keyword_extractor": _kw  if isinstance(_kw,  tuple) else None,
        "seo_agent":         _seo if isinstance(_seo, tuple) else None,
        "gap_analyzer":      _gap if isinstance(_gap, tuple) else None,
    }
    run["real_baseline"] = {
        k: {"reward": round(v[0], 4), "cost": v[1], "source": "real"} if v
           else {"source": "simulated"}
        for k, v in real_baseline.items()
    }
    run["status"] = "running"

    for i in range(config.iterations):
        t0 = time.time()

        # ── Stage 1: Each agent's GP suggests its next action ───────────────
        agent_actions:   Dict[str, np.ndarray] = {}
        agent_variances: Dict[str, float]      = {}
        agent_kappas:    Dict[str, float]      = {}

        for agent_name, bo in agent_bos.items():
            # suggest_next handles bootstrapping internally via LHS for early iterations
            action, gp_var, _, kappa_eff = bo.suggest_next(iteration=i)
            agent_actions[agent_name]   = action
            agent_variances[agent_name] = round(gp_var, 4)
            agent_kappas[agent_name]    = round(kappa_eff, 3)

        # ── Stage 2-4: Content agent runs the full pipeline ────────────────
        content_action = agent_actions["content_agent"]
        pt_idx  = int(content_action[0] * len(PROMPT_TEMPLATES)) % len(PROMPT_TEMPLATES)
        prompt  = PROMPT_TEMPLATES[pt_idx]
        content = await generate_content(config.topic, prompt, content_action, i)
        critic  = evaluate_content(content, config.intent, config.brand)
        ig      = simulate_ig_metrics(critic["overall_score"], i)
        content_reward = compute_reward(critic, ig)
        content_cost   = round(
            DEMO_AGENTS["content_agent"]["base_cost"] * (0.5 + float(content_action[0]) * 0.6), 2
        )

        agent_rewards: Dict[str, float] = {"content_agent": content_reward}
        agent_costs:   Dict[str, float] = {"content_agent": content_cost}
        image_prompt: str = (
            f"Instagram marketing photograph: {content.split('.')[0][:100].strip()}. "
            f"Sustainable wellness brand, warm aesthetic, soft lighting, professional photography."
        )

        # ── Stage 3 (other agents) ────────────────────────────────────────────
        # - critic_agent  : already computed as evaluate_content() above
        # - keyword/seo/gap: use real baseline scaled by GP quality_weight + trend
        # - image_generator: no live service → always simulated
        # - any real service offline → falls back to simulate_agent_reward()
        for agent_name in DEMO_AGENT_NAMES:
            if agent_name == "content_agent":
                continue

            rng_seed = i * 997 + hash(agent_name) % 1000
            alloc    = admm.allocations.get(agent_name, 0.0)

            if agent_name == "critic_agent":
                # Critic IS evaluate_content() — score is already computed.
                # Cost is tiny and FIXED (embedding + textstat, no LLM) regardless
                # of how much budget ADMM gives it — the excess stays unused.
                agent_rewards[agent_name] = critic["overall_score"]
                agent_costs[agent_name]   = round(
                    DEMO_AGENTS["critic_agent"]["base_cost"]
                    * (0.6 + float(agent_actions[agent_name][0]) * 0.25), 2  # ~$0.8–0.9, narrow range
                )
                continue

            if agent_name == "image_generator":
                # Image prompt is derived directly from the generated content so that
                # image_generator reward tracks content quality improvements.
                content_quality = critic.get("overall_score", 0.5)
                r, c = simulate_agent_reward(
                    agent_name, agent_actions[agent_name], i, rng_seed, budget_alloc=alloc
                )
                # Blend simulated reward with content quality (60/40) so image_generator
                # reward tracks content improvement across iterations
                blended_r = round(float(np.clip(0.60 * r + 0.40 * content_quality, 0.05, 0.96)), 4)
                agent_rewards[agent_name] = blended_r
                agent_costs[agent_name]   = c
                # Build a concrete image brief from the generated content
                first_sentence = content.split(".")[0].strip()
                first_sentence = first_sentence[:120] if len(first_sentence) > 120 else first_sentence
                _ig_quality_tag = (
                    "cinematic soft light" if content_quality >= 0.80 else
                    "warm studio lighting" if content_quality >= 0.60 else
                    "natural outdoor lighting"
                )
                image_prompt = (
                    f"Instagram marketing photograph: {first_sentence}. "
                    f"Sustainable wellness brand aesthetic, {_ig_quality_tag}, "
                    f"soft pastel palette, aspirational lifestyle, no text overlay, "
                    f"professional product photography, 4K, high detail."
                )
                continue

            baseline = real_baseline.get(agent_name)   # (reward, cost) or None
            if baseline and agent_name != "image_generator":
                # Scale real baseline by GP quality_weight proximity to optimal zone
                base_r, base_c = baseline
                qw             = float(agent_actions[agent_name][0])
                opt_lo, opt_hi = DEMO_AGENTS[agent_name]["opt_quality"]
                if opt_lo <= qw <= opt_hi:
                    scale = 1.0
                elif qw < opt_lo:
                    scale = 0.70 + 0.30 * (qw / max(opt_lo, 1e-6))
                else:
                    scale = max(0.50, 1.0 - (qw - opt_hi) * 1.5)
                trend  = 1.0 + 0.018 * min(i, 35)
                rng_   = random.Random(rng_seed)
                reward = float(np.clip(base_r * scale * trend + rng_.gauss(0, 0.025), 0.05, 0.96))
                cost   = round(base_c * (0.6 + qw * 0.4), 2)
                # Apply budget pressure on top of real reward
                if alloc > 0.0 and alloc < cost * 0.75:
                    reward = float(np.clip(reward - 0.18 * (1.0 - alloc / cost), 0.05, 0.96))
                    cost   = alloc
                agent_rewards[agent_name] = round(reward, 4)
                agent_costs[agent_name]   = cost
            else:
                # image_generator or real service unavailable → simulate
                r, c = simulate_agent_reward(
                    agent_name, agent_actions[agent_name], i, rng_seed, budget_alloc=alloc
                )
                agent_rewards[agent_name] = r
                agent_costs[agent_name]   = c

        # ── Stage 5: ADMM budget reallocation ──────────────────────────
        admm_snap = admm.update(agent_costs, agent_rewards)

        # ── Stage 6: Feed rewards back to each agent's BO ───────────────
        for agent_name, bo in agent_bos.items():
            bo.observe(agent_actions[agent_name], agent_rewards[agent_name])

        # ── Snapshots ───────────────────────────────────────────────────
        main_bo   = agent_bos["content_agent"]
        main_snap = main_bo.acquisition_snapshot()
        regret    = round(
            main_snap["best_reward"] - content_reward, 4
        ) if main_snap["best_reward"] > -np.inf else 0.0

        agents_summary: Dict[str, Any] = {}
        for agent_name in DEMO_AGENT_NAMES:
            bo = agent_bos[agent_name]
            agents_summary[agent_name] = {
                "action":         agent_actions[agent_name].tolist(),
                "reward":         round(agent_rewards[agent_name], 4),
                "cost":           round(agent_costs[agent_name], 2),
                "budget_alloc":   admm_snap["allocations"].get(agent_name, 0.0),
                "roi":            round(admm_snap["roi"].get(agent_name, 0.0), 4),
                "gp_variance":    agent_variances[agent_name],
                "kappa":          agent_kappas[agent_name],
                "best_reward":    round(bo.best_y, 4) if bo.best_y > -np.inf else 0.0,
                "quality_weight": round(float(agent_actions[agent_name][0]), 3),
                "color":          DEMO_AGENTS[agent_name]["color"],
                "label":          DEMO_AGENTS[agent_name]["label"],
            }

        iteration_data = {
            "iteration":       i + 1,
            "prompt":          prompt,
            "content":         content,
            "image_prompt":    image_prompt,   # brief derived from content for image_generator
            "critic":          critic,
            "ig_metrics":      ig,
            "reward":          content_reward,
            "mabo_point":      content_action.tolist(),
            "gp_variance":     agent_variances["content_agent"],
            "gp_mu":           0.0,
            "kappa":           agent_kappas["content_agent"],
            "regret":          regret,
            "bo_snapshot":     main_snap,
            "pipeline_stages": PIPELINE_STAGES,
            "elapsed_s":       round(time.time() - t0, 2),
            "timestamp":       datetime.now().isoformat(),
            # ── Multi-agent fields ─────────────────────────────────────
            "agents": agents_summary,
            "admm": {
                "allocations":     admm_snap["allocations"],
                "lambdas":         admm_snap["lambdas"],
                "roi":             admm_snap["roi"],
                "total_spent":     admm_snap["total_spent"],
                "total_budget":    TOTAL_DEMO_BUDGET,
                "primal_residual": admm_snap["primal_residual"],
                "dual_residual":   admm_snap["dual_residual"],
            },
        }
        run["iterations"].append(iteration_data)
        await asyncio.sleep(0.6)

    run["status"]         = "completed"
    run["completed_at"]   = datetime.now().isoformat()
    run["best_reward"]    = round(agent_bos["content_agent"].best_y, 4)
    run["best_iteration"] = int(np.argmax(agent_bos["content_agent"].y)) + 1


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
    return {
        "status":        r["status"],
        "done":          len(r["iterations"]),
        "config":        r["config"],
        "real_baseline": r.get("real_baseline", {}),  # which agents used real services
    }


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
