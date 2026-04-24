# Step-by-Step Implementation Guide

## Feature 1: Zero-Shot Classifier & Slot Filling

### Step 1: Setup & Dependencies
**Location:** `requirements.txt`
```
Add:
transformers>=4.35.0
torch>=2.0.0
accelerate>=0.24.0  # For faster inference
```

**Action:**
```bash
pip install transformers torch accelerate
```

**Verification:**
- Test import in Python: `from transformers import pipeline`

---

### Step 2: Create Zero-Shot Classifier Module
**New File:** `zero_shot_classifier.py`

**Implementation:**
```python
"""
Zero-Shot Classifier Module
- Replaces hardcoded intent enum
- Works with dynamic intent lists
- No API calls needed
"""

from typing import Dict, List, Optional, Tuple
import logging
from transformers import pipeline

logger = logging.getLogger(__name__)

class DynamicIntentClassifier:
    def __init__(self, model_name: str = "facebook/bart-large-mnli"):
        """Load model once at startup."""
        self.model_name = model_name
        self.classifier = None
        self._load_model()
    
    def _load_model(self):
        """Lazy load with error handling."""
        try:
            self.classifier = pipeline(
                "zero-shot-classification",
                model=self.model_name,
                device=-1  # CPU (use 0 for GPU)
            )
            logger.info(f"Loaded {self.model_name}")
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise
    
    def classify(
        self,
        text: str,
        candidate_labels: List[str],
        multi_class: bool = False,
        threshold: float = 0.5
    ) -> Dict:
        """
        Classify text against any list of candidate labels.
        
        Returns:
            {
                "top_intent": "blog_generation",
                "confidence": 0.92,
                "all_scores": {...},
                "multi_intent": ["blog_generation", "seo_optimization"],
                "multi_intent_scores": [0.92, 0.65]
            }
        """
        result = self.classifier(text, candidate_labels, multi_class=multi_class)
        
        top_intent = result["labels"][0]
        top_score = result["scores"][0]
        
        # Extract multi-intent if above threshold
        multi_intent = []
        for label, score in zip(result["labels"], result["scores"]):
            if score >= threshold:
                multi_intent.append(label)
        
        return {
            "top_intent": top_intent,
            "confidence": round(top_score, 3),
            "all_scores": dict(zip(result["labels"], result["scores"])),
            "multi_intent": multi_intent,
            "multi_intent_scores": [s for s in result["scores"] if s >= threshold]
        }

# Singleton instance
_classifier = None

def get_classifier():
    global _classifier
    if _classifier is None:
        _classifier = DynamicIntentClassifier()
    return _classifier
```

---

### Step 3: Update Intelligent Router
**File:** `intelligent_router.py` (lines 1-150)

**Current Code (to replace):**
```python
INTENT_EXAMPLES: Dict[str, str] = {
    "general_chat": "hello what can you do help me understand this",
    "seo_analysis": "analyse my website SEO audit check page optimisation",
    # ... hardcoded 13 intents
}

def route_user_query(message, history):
    """Uses cosine similarity against hardcoded intents."""
    embeddings = _get_intent_embeddings(message)
    # Rigid matching...
```

**New Code:**
```python
from zero_shot_classifier import get_classifier

# Intent labels (now updatable, no code changes needed)
DEFAULT_INTENTS = [
    "general_chat",
    "seo_analysis",
    "blog_generation",
    "social_post",
    "competitor_research",
    "metrics_report",
    "brand_setup",
    "daily_schedule",
    "campaign_planning",
    "image_generation",
    "deep_research",
    "critic_review",
    "campaign_post",
]

async def route_user_query(message: str, history: List = None) -> Dict:
    """
    Route using zero-shot classification (dynamic).
    
    Returns:
        {
            "intent": "blog_generation",
            "confidence": 0.89,
            "is_multi_intent": False,
            "secondary_intents": []
        }
    """
    classifier = get_classifier()
    
    result = classifier.classify(
        text=message,
        candidate_labels=DEFAULT_INTENTS,
        multi_class=True,
        threshold=0.4  # Include secondary intents >= 0.4
    )
    
    return {
        "intent": result["top_intent"],
        "confidence": result["confidence"],
        "is_multi_intent": len(result["multi_intent"]) > 1,
        "secondary_intents": result["multi_intent"][1:] if len(result["multi_intent"]) > 1 else [],
        "all_scores": result["all_scores"]
    }
```

---

### Step 4: Add Slot Filling
**Location:** `zero_shot_classifier.py` (add new function)

**Implementation:**
```python
def extract_slots(
    text: str,
    intent: str,
    slot_definitions: Dict[str, List[str]]
) -> Dict[str, Optional[str]]:
    """
    Extract parameters/slots from user message.
    
    Args:
        text: User message
        intent: Detected intent
        slot_definitions: {"keyword": ["topic", "subject", "keyword"],
                          "platform": ["instagram", "facebook", "twitter"],
                          "count": ["number", "how many", "total"]}
    
    Returns: {"keyword": "vegan skincare", "platform": "instagram", ...}
    """
    slots = {}
    
    for slot_name, slot_keywords in slot_definitions.items():
        # Use zero-shot classifier to find slot values
        slot_result = classifier.classify(
            text,
            slot_keywords,
            multi_class=False
        )
        
        # Extract named entities as slot values
        # (Simplified - use NER for production)
        if slot_result["confidence"] > 0.6:
            # Extract entities from text matching the slot intent
            # Example: if slot is "keyword", extract nouns from text
            slots[slot_name] = extract_entity(text, slot_name)
    
    return slots
```

---

### Step 5: Update Orchestrator Routes
**File:** `orchestrator.py` (lines 200-250)

**Current:**
```python
router_result = await router.route_user_query(message, history)
intent = router_result.get("intent")
```

**New:**
```python
router_result = await router.route_user_query(message, history)
intent = router_result.get("intent")
confidence = router_result.get("confidence")

# Log confidence for monitoring
if confidence < 0.5:
    logger.warning(f"Low confidence routing: {intent} ({confidence})")
    # Could trigger escalation to human

# Handle multi-intent
if router_result.get("is_multi_intent"):
    logger.info(f"Multi-intent detected: {router_result['secondary_intents']}")
    # Route to multi-intent handler
```

---

### Step 6: Testing
**File:** `tests/test_zero_shot.py` (new)

```python
import pytest
from zero_shot_classifier import DynamicIntentClassifier

def test_basic_classification():
    classifier = DynamicIntentClassifier()
    result = classifier.classify(
        "I need to write a blog post about vegan skincare",
        ["blog_generation", "seo_analysis", "social_post"]
    )
    assert result["top_intent"] == "blog_generation"
    assert result["confidence"] > 0.7

def test_unknown_intent():
    """Should still classify to most similar intent."""
    classifier = DynamicIntentClassifier()
    result = classifier.classify(
        "Schedule a marketing event next Tuesday",
        ["blog_generation", "seo_analysis", "campaign_planning"]
    )
    # Should pick campaign_planning as closest match
    assert "campaign_planning" in result["top_intent"] or result["confidence"] > 0.5

def test_multi_intent():
    classifier = DynamicIntentClassifier()
    result = classifier.classify(
        "Create a blog post optimized for SEO",
        ["blog_generation", "seo_analysis"],
        multi_class=True
    )
    assert len(result["multi_intent"]) == 2
```

---

## Feature 2: Entailment (NLI) for Critic Agent

### Step 1: Create NLI Evaluator Module
**New File:** `nli_evaluator.py`

**Implementation:**
```python
"""
Natural Language Inference (NLI) Evaluator
- Checks if generated content logically follows from intent
- Returns: entailment, neutral, contradiction
"""

from typing import Dict, Literal
import logging
from transformers import pipeline

logger = logging.getLogger(__name__)

class NLIEvaluator:
    def __init__(self, model_name: str = "microsoft/deberta-v3-large"):
        """Load NLI model optimized for entailment."""
        self.model_name = model_name
        self.nli = None
        self._load_model()
    
    def _load_model(self):
        """Load with device selection and error handling."""
        try:
            self.nli = pipeline(
                "zero-shot-classification",
                model=self.model_name,
                device=-1  # CPU
            )
            logger.info(f"Loaded NLI model: {self.model_name}")
        except Exception as e:
            logger.error(f"Failed to load NLI model: {e}")
            raise
    
    def check_entailment(
        self,
        premise: str,  # Intent (e.g., "Create eco-friendly product guide")
        hypothesis: str,  # Generated content (first 2K chars)
        return_scores: bool = True
    ) -> Dict:
        """
        Check if hypothesis (content) logically follows from premise (intent).
        
        Returns:
            {
                "label": "entailment" | "neutral" | "contradiction",
                "entailment_score": 0.92,
                "neutral_score": 0.05,
                "contradiction_score": 0.03,
                "reasoning": "Content strongly supports the stated intent"
            }
        """
        # Create NLI task prompt
        prompt = f"Premise: {premise}\nHypothesis: {hypothesis}"
        
        # Classify with 3 NLI labels
        result = self.nli(
            prompt,
            ["entailment", "neutral", "contradiction"],
            hypothesis_template="The hypothesis {} the premise."
        )
        
        # Map to scores
        label_scores = dict(zip(result["labels"], result["scores"]))
        
        return {
            "label": result["labels"][0],  # Top label
            "entailment_score": round(label_scores.get("entailment", 0), 3),
            "neutral_score": round(label_scores.get("neutral", 0), 3),
            "contradiction_score": round(label_scores.get("contradiction", 0), 3),
            "all_scores": label_scores,
            "reasoning": self._generate_reasoning(result["labels"][0], label_scores)
        }
    
    def _generate_reasoning(self, label: str, scores: Dict) -> str:
        """Generate human-readable explanation."""
        if label == "entailment":
            return f"Content strongly supports the stated intent (confidence: {scores['entailment']:.1%})"
        elif label == "contradiction":
            return f"Content contradicts the stated intent (conflict score: {scores['contradiction']:.1%})"
        else:
            return f"Content is only loosely related to intent (similarity: {scores['neutral']:.1%})"

# Singleton
_nli_evaluator = None

def get_nli_evaluator():
    global _nli_evaluator
    if _nli_evaluator is None:
        _nli_evaluator = NLIEvaluator()
    return _nli_evaluator
```

---

### Step 2: Update Database Schema
**File:** `database.py` (find the `save_critic_log` function)

**Current:**
```python
def save_critic_log(content_id, intent_score, brand_score, quality_score, ...):
    """Save critic evaluation."""
    # Columns: content_id, intent_score, brand_score, quality_score, overall_score
```

**New:**
```python
def save_critic_log(
    content_id,
    intent_score,
    brand_score,
    quality_score,
    entailment_label: str,  # NEW: "entailment", "neutral", "contradiction"
    entailment_score: float,  # NEW: 0.0-1.0
    ...
):
    """Save critic evaluation WITH NLI scores."""
    query = """
    INSERT INTO critic_logs (
        content_id, intent_score, brand_score, quality_score,
        entailment_label, entailment_score,  -- NEW COLUMNS
        overall_score, decision, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    # Add migration script to create columns
```

**Migration Script:**
```sql
-- File: migrations/add_entailment_columns.sql
ALTER TABLE critic_logs ADD COLUMN entailment_label TEXT DEFAULT 'neutral';
ALTER TABLE critic_logs ADD COLUMN entailment_score REAL DEFAULT 0.5;
CREATE INDEX idx_entailment ON critic_logs(entailment_label);
```

---

### Step 3: Update Critic Agent Evaluation
**File:** `critic_agent.py` (lines 300-350, replace `_evaluate` function)

**Current:**
```python
@trace_llm(name="critic_evaluation")
async def _evaluate(req: CriticRequest, brand_context: str):
    """
    Evaluates: intent_score, brand_score, quality_score
    No entailment check.
    """
    _ensure_critic_model()
    
    # Intent alignment (cosine similarity only)
    intent_emb = _critic_model.encode(req.original_intent, normalize_embeddings=True)
    intent_score = round(min(1.0, max(0.0, _cosine(intent_emb, content_emb) * 1.5)), 3)
```

**New:**
```python
from nli_evaluator import get_nli_evaluator

@trace_llm(name="critic_evaluation")
async def _evaluate(req: CriticRequest, brand_context: str):
    """
    Evaluates: intent_score (with NLI), brand_score, quality_score.
    NEW: Entailment check prevents contradictory content.
    """
    _ensure_critic_model()
    nli = get_nli_evaluator()
    
    content = req.content_text[:4000]
    content_emb = _critic_model.encode(content, normalize_embeddings=True)
    
    # ===== NEW: Entailment Check =====
    nli_result = nli.check_entailment(
        premise=req.original_intent,
        hypothesis=content[:2000]  # First 2K for efficiency
    )
    
    entailment_label = nli_result["label"]
    entailment_score = nli_result["entailment_score"]
    
    # NEW: Scoring logic based on entailment
    if entailment_label == "entailment":
        # Content logically supports intent - boost score
        intent_score = 0.90 + (0.10 * entailment_score)
    elif entailment_label == "contradiction":
        # Content contradicts intent - fail immediately
        intent_score = 0.0
        logger.warning(f"Content contradicts intent: {req.original_intent}")
    else:  # neutral
        # Content only loosely related - reduce confidence
        intent_score_emb = min(1.0, max(0.0, _cosine(intent_emb, content_emb) * 1.5))
        intent_score = 0.5 * intent_score_emb
    
    intent_score = round(intent_score, 3)
    
    # ===== Rest of evaluation (brand, quality) unchanged =====
    # ... (existing code for brand_score, quality_score) ...
    
    # ===== NEW: Save entailment data =====
    save_critic_log(
        content_id=req.content_id,
        intent_score=intent_score,
        brand_score=brand_score,
        quality_score=quality_score,
        entailment_label=entailment_label,  # NEW
        entailment_score=entailment_score,  # NEW
        overall_score=overall_score,
        decision="pending"
    )
    
    return CriticResponse(
        ...,
        intent_score=intent_score,
        entailment_label=entailment_label,  # NEW in response
        entailment_reasoning=nli_result["reasoning"],  # NEW
        critique_text=f"{critique_text}\n\n**Entailment: {nli_result['reasoning']}**"
    )
```

---

### Step 4: Update API Response Model
**File:** `critic_agent.py` (CriticResponse class)

**Current:**
```python
class CriticResponse(BaseModel):
    content_id: str
    intent_score: float
    brand_score: float
    quality_score: float
    overall_score: float
    passed: bool
    critique_text: str
```

**New:**
```python
class CriticResponse(BaseModel):
    content_id: str
    intent_score: float
    brand_score: float
    quality_score: float
    overall_score: float
    passed: bool
    critique_text: str
    # NEW FIELDS:
    entailment_label: Optional[str] = None  # "entailment", "neutral", "contradiction"
    entailment_reasoning: Optional[str] = None
    entailment_score: Optional[float] = None
```

---

### Step 5: Testing
**File:** `tests/test_nli_evaluator.py` (new)

```python
import pytest
from nli_evaluator import NLIEvaluator

def test_entailment_detected():
    """Content that supports intent."""
    nli = NLIEvaluator()
    result = nli.check_entailment(
        premise="Create an eco-friendly product guide",
        hypothesis="This guide explains sustainable materials and reduces environmental impact..."
    )
    assert result["label"] == "entailment"
    assert result["entailment_score"] > 0.7

def test_contradiction_detected():
    """Content that opposes intent."""
    nli = NLIEvaluator()
    result = nli.check_entailment(
        premise="Create an eco-friendly product guide",
        hypothesis="Plastic is superior to eco-friendly alternatives..."
    )
    assert result["label"] == "contradiction"
    assert result["contradiction_score"] > 0.7

def test_neutral_detected():
    """Content loosely related to intent."""
    nli = NLIEvaluator()
    result = nli.check_entailment(
        premise="Write about marketing strategies",
        hypothesis="The weather today is sunny and warm..."
    )
    assert result["label"] == "neutral"
```

---

## Feature 3: Discounted UCB (D-UCB) for Budget Allocation

### Step 1: Create Discounted Bandit Module
**New File:** `discounted_bandit.py`

**Implementation:**
```python
"""
Discounted Multi-Armed Bandit (D-UCB)
- Exponential decay for time-sensitive rewards
- Adapts to trend changes faster than standard UCB
"""

import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

@dataclass
class CampaignObservation:
    timestamp: datetime
    budget_spent: float
    clicks: int
    conversions: int = 0
    revenue: float = 0.0

@dataclass
class CampaignStats:
    campaign_id: str
    observations: List[CampaignObservation] = field(default_factory=list)
    discounted_mean_efficiency: float = 0.0
    discounted_mean_clicks: float = 0.0

class DiscountedUCB:
    def __init__(
        self,
        campaigns: List[str],
        gamma: float = 0.95,
        exploration_constant: float = 1.5
    ):
        """
        Initialize D-UCB bandit.
        
        Args:
            campaigns: List of campaign IDs
            gamma: Discount factor (0.90 = 10% decay per period, 0.95 = 5% decay)
            exploration_constant: Higher = more exploration (c in UCB formula)
        """
        self.gamma = gamma
        self.exploration_constant = exploration_constant
        self.campaign_stats: Dict[str, CampaignStats] = {
            cid: CampaignStats(campaign_id=cid)
            for cid in campaigns
        }
        self.last_update = datetime.now()
    
    def add_observation(
        self,
        campaign_id: str,
        budget_spent: float,
        clicks: int,
        conversions: int = 0,
        revenue: float = 0.0,
        timestamp: Optional[datetime] = None
    ):
        """Record a new campaign performance observation."""
        if campaign_id not in self.campaign_stats:
            logger.warning(f"Unknown campaign: {campaign_id}")
            return
        
        if timestamp is None:
            timestamp = datetime.now()
        
        obs = CampaignObservation(
            timestamp=timestamp,
            budget_spent=budget_spent,
            clicks=clicks,
            conversions=conversions,
            revenue=revenue
        )
        
        self.campaign_stats[campaign_id].observations.append(obs)
        self._update_discounted_stats(campaign_id)
    
    def _update_discounted_stats(self, campaign_id: str):
        """Recompute discounted mean for campaign."""
        stats = self.campaign_stats[campaign_id]
        
        if not stats.observations:
            return
        
        current_time = datetime.now()
        weighted_sum_efficiency = 0.0
        weighted_sum_clicks = 0.0
        weight_sum = 0.0
        
        for obs in stats.observations:
            # Days since observation
            days_old = (current_time - obs.timestamp).days
            
            # Exponential decay: γ^days_old
            decay_weight = self.gamma ** days_old
            weight_sum += decay_weight
            
            # Efficiency: clicks per dollar
            efficiency = obs.clicks / obs.budget_spent if obs.budget_spent > 0 else 0
            weighted_sum_efficiency += efficiency * decay_weight
            weighted_sum_clicks += obs.clicks * decay_weight
        
        # Compute discounted means
        stats.discounted_mean_efficiency = (
            weighted_sum_efficiency / weight_sum if weight_sum > 0 else 0
        )
        stats.discounted_mean_clicks = (
            weighted_sum_clicks / weight_sum if weight_sum > 0 else 0
        )
    
    def select_campaign(self, campaigns: Optional[List[str]] = None) -> str:
        """
        Select best campaign using Discounted Confidence Bound.
        
        D-UCB = discounted_mean + c * sqrt(ln(t) / N_eff)
        
        Returns: campaign_id with highest D-UCB index
        """
        if campaigns is None:
            campaigns = list(self.campaign_stats.keys())
        
        # Total discounted observations
        t = sum(
            len(s.observations)
            for s in self.campaign_stats.values()
        )
        t = max(t, 1)  # Avoid log(0)
        
        indices = {}
        current_time = datetime.now()
        
        for cid in campaigns:
            stats = self.campaign_stats[cid]
            
            # Discounted mean performance
            mean = stats.discounted_mean_efficiency
            
            # Effective sample size (discounted)
            n_eff = 0
            for obs in stats.observations:
                days_old = (current_time - obs.timestamp).days
                n_eff += self.gamma ** days_old
            
            n_eff = max(n_eff, 0.1)  # Avoid division by zero
            
            # UCB index: mean + exploration bonus
            exploration_bonus = self.exploration_constant * np.sqrt(np.log(t) / n_eff)
            indices[cid] = mean + exploration_bonus
            
            logger.info(
                f"Campaign {cid}: mean={mean:.3f}, n_eff={n_eff:.1f}, "
                f"bonus={exploration_bonus:.3f}, ucb_index={indices[cid]:.3f}"
            )
        
        selected = max(indices, key=indices.get)
        return selected
    
    def allocate_budget(
        self,
        total_budget: float,
        allocation_strategy: str = "proportional"
    ) -> Dict[str, float]:
        """
        Allocate budget across campaigns using D-UCB ranking.
        
        Strategies:
            "proportional": Allocate proportionally to D-UCB scores
            "epsilon_greedy": 80% to best, 20% spread across others
            "top_two": 60% to best, 30% to second, 10% to rest
        """
        campaigns = list(self.campaign_stats.keys())
        
        # Rank campaigns by D-UCB
        ranked = sorted(
            campaigns,
            key=lambda c: self._compute_dcb_index(c),
            reverse=True
        )
        
        allocation = {}
        
        if allocation_strategy == "proportional":
            # Allocate proportional to D-UCB scores
            dcb_scores = {
                c: self._compute_dcb_index(c)
                for c in campaigns
            }
            total_score = sum(dcb_scores.values())
            
            for cid in campaigns:
                share = dcb_scores[cid] / total_score if total_score > 0 else 1.0 / len(campaigns)
                allocation[cid] = total_budget * share
        
        elif allocation_strategy == "epsilon_greedy":
            # 80% to best, 20% to rest
            best = ranked[0]
            others = ranked[1:]
            allocation[best] = total_budget * 0.80
            for cid in others:
                allocation[cid] = total_budget * 0.20 / len(others)
        
        elif allocation_strategy == "top_two":
            # 60% to best, 30% to second, 10% to rest
            allocation[ranked[0]] = total_budget * 0.60
            allocation[ranked[1]] = total_budget * 0.30
            for cid in ranked[2:]:
                allocation[cid] = total_budget * 0.10 / len(ranked[2:])
        
        return allocation
    
    def _compute_dcb_index(self, campaign_id: str) -> float:
        """Helper to compute D-UCB index for a campaign."""
        stats = self.campaign_stats[campaign_id]
        t = sum(len(s.observations) for s in self.campaign_stats.values())
        t = max(t, 1)
        
        n_eff = sum(
            self.gamma ** (datetime.now() - obs.timestamp).days
            for obs in stats.observations
        )
        n_eff = max(n_eff, 0.1)
        
        exploration_bonus = self.exploration_constant * np.sqrt(np.log(t) / n_eff)
        return stats.discounted_mean_efficiency + exploration_bonus
```

---

### Step 2: Update Budget Allocator Integration
**File:** `budget_allocator.py` (replace entire class)

**Current:**
```python
class ParametricBandit:
    """Standard bandit - no decay."""
    def __init__(self, campaigns, ...):
        self.campaign_states = {...}
        # No gamma factor
```

**New:**
```python
from discounted_bandit import DiscountedUCB

class ParametricBandit:
    """
    NOW uses Discounted UCB for faster adaptation.
    Can switch between strategies via config.
    """
    def __init__(
        self,
        campaigns: List[str],
        gamma: float = 0.95,
        allocation_strategy: str = "proportional"
    ):
        self.gamma = gamma
        self.allocation_strategy = allocation_strategy
        self.bandit = DiscountedUCB(
            campaigns=campaigns,
            gamma=gamma,
            exploration_constant=1.5
        )
    
    def update_campaign_performance(
        self,
        campaign_id: str,
        budget_spent: float,
        clicks: int,
        conversions: int = 0
    ):
        """Record new performance data."""
        self.bandit.add_observation(
            campaign_id=campaign_id,
            budget_spent=budget_spent,
            clicks=clicks,
            conversions=conversions
        )
    
    def allocate(self, total_budget: float) -> Dict[str, float]:
        """Get next week's budget allocation."""
        return self.bandit.allocate_budget(
            total_budget=total_budget,
            allocation_strategy=self.allocation_strategy
        )
```

---

### Step 3: Update Orchestrator/Campaign Planner
**File:** `orchestrator.py` (find budget allocation endpoint, ~line 800)

**Current:**
```python
@app.post("/allocate-budget")
def allocate_budget(campaigns: List[str], total_budget: float):
    """Allocate budget using standard bandit."""
    allocator = ParametricBandit(campaigns)
    return allocator.allocate()
```

**New:**
```python
from dotenv import load_dotenv
load_dotenv()

BANDIT_GAMMA = float(os.getenv("BANDIT_GAMMA", "0.95"))
ALLOCATION_STRATEGY = os.getenv("ALLOCATION_STRATEGY", "proportional")

@app.post("/allocate-budget")
def allocate_budget(
    campaigns: List[str],
    total_budget: float,
    gamma: Optional[float] = None,
    strategy: Optional[str] = None
):
    """
    Allocate budget using Discounted UCB.
    
    Query params:
        gamma: Discount factor (0.90-0.99)
        strategy: "proportional" | "epsilon_greedy" | "top_two"
    """
    gamma = gamma or BANDIT_GAMMA
    strategy = strategy or ALLOCATION_STRATEGY
    
    # Load historical data
    allocator = ParametricBandit(
        campaigns=campaigns,
        gamma=gamma,
        allocation_strategy=strategy
    )
    
    # Populate with past performance
    for campaign in campaigns:
        history = db.get_campaign_history(campaign, days=90)
        for record in history:
            allocator.update_campaign_performance(
                campaign_id=campaign,
                budget_spent=record["budget_spent"],
                clicks=record["clicks"],
                conversions=record.get("conversions", 0)
            )
    
    # Allocate
    allocation = allocator.allocate(total_budget)
    
    return {
        "allocation": allocation,
        "gamma": gamma,
        "strategy": strategy,
        "timestamp": datetime.now().isoformat()
    }

@app.post("/update-campaign-performance")
def update_performance(
    campaign_id: str,
    budget_spent: float,
    clicks: int,
    conversions: int = 0
):
    """Record campaign performance (called daily/weekly)."""
    db.save_campaign_performance(
        campaign_id=campaign_id,
        budget_spent=budget_spent,
        clicks=clicks,
        conversions=conversions,
        timestamp=datetime.now()
    )
    return {"status": "recorded"}
```

---

### Step 4: Add Configuration
**File:** `.env`

```
# Discounted UCB Configuration
BANDIT_GAMMA=0.95
ALLOCATION_STRATEGY=proportional
EXPLORATION_CONSTANT=1.5
```

---

### Step 5: Testing
**File:** `tests/test_discounted_bandit.py` (new)

```python
import pytest
from datetime import datetime, timedelta
from discounted_bandit import DiscountedUCB

def test_decay_adaptation():
    """Recent data weighted more than old data."""
    bandit = DiscountedUCB(["campaign_a"], gamma=0.95)
    
    # Old data (2 weeks ago): high performance
    bandit.add_observation(
        campaign_id="campaign_a",
        budget_spent=100,
        clicks=100,
        timestamp=datetime.now() - timedelta(days=14)
    )
    
    # Recent data (1 day ago): low performance
    bandit.add_observation(
        campaign_id="campaign_a",
        budget_spent=100,
        clicks=5,
        timestamp=datetime.now() - timedelta(days=1)
    )
    
    stats = bandit.campaign_stats["campaign_a"]
    # Discounted mean should be closer to recent 5 clicks, not average of 100+5
    assert stats.discounted_mean_clicks < 30  # Closer to recent 5

def test_standard_bandit_comparison():
    """D-UCB should weight recent differently than standard."""
    # Create two bandits: with gamma and without
    d_ucb = DiscountedUCB(["a", "b"], gamma=0.95)
    
    # Add same observations to both campaigns
    # Campaign A: historically good, recently bad
    d_ucb.add_observation("a", 100, 50, timestamp=datetime.now() - timedelta(days=7))
    d_ucb.add_observation("a", 100, 5, timestamp=datetime.now())
    
    # Campaign B: always mediocre
    d_ucb.add_observation("b", 100, 20, timestamp=datetime.now() - timedelta(days=7))
    d_ucb.add_observation("b", 100, 15, timestamp=datetime.now())
    
    selected = d_ucb.select_campaign(["a", "b"])
    # Should pick B because A's recent performance is bad
    assert selected == "b"
```

---

## Feature 4: SEO Compliance in Critic Agent

### Step 1: Create SEO Compliance Module
**New File:** `seo_content_compliance.py`

*(Already shown in IMPLEMENTATION_ASSESSMENT.md - see sections starting at "The "Discounted" UCB (D-UCB)")*

**Key components:**
- `ContentSEOCompliance` class with 5 audit categories
- `SEOComplianceReport` dataclass
- Methods: `_check_keywords()`, `_check_readability()`, `_check_structure()`, `_check_markup()`, `_check_linking()`

---

### Step 2: Integrate with Critic Agent
**File:** `critic_agent.py` (add optional SEO check in evaluate flow)

**New Code:**
```python
from seo_content_compliance import ContentSEOCompliance

class CriticRequest(BaseModel):
    # ... existing fields ...
    check_seo_compliance: bool = False

class CriticResponse(BaseModel):
    # ... existing fields ...
    seo_score: float = 0.0
    seo_passed: bool = True
    seo_issues: list = []

@app.post("/evaluate")
async def evaluate_content(req: CriticRequest):
    """Critic evaluation with optional SEO compliance check."""

    # Existing critic evaluation
    intent_score, brand_score, quality_score = await _evaluate(req, brand_context)

    seo_score_norm = 1.0
    seo_passed = True
    seo_issues = []

    if req.check_seo_compliance:
        keywords = [req.original_intent]
        seo_checker = ContentSEOCompliance(keywords, req.content_type)
        seo_report = seo_checker.audit(req.content_text)
        seo_score_norm = seo_report.score / 100.0
        seo_passed = seo_report.passed
        seo_issues = seo_report.issues

    overall_score = (
        0.35 * intent_score +
        0.25 * brand_score +
        0.25 * quality_score +
        0.15 * seo_score_norm
    )

    return CriticResponse(
        ...,
        overall_score=overall_score,
        seo_score=round(seo_score_norm * 100.0, 2),
        seo_passed=seo_passed,
        seo_issues=seo_issues,
    )
```

---

### Step 3: Persist SEO Results from Critic Evaluation
**File:** `database.py` + `critic_agent.py`

**New Code:**
```python
def save_seo_audit(
    critic_log_id: int,
    seo_score: float,
    seo_passed: bool,
    issues_json: str,
    meta_tags_json: str,
):
    """Persist SEO audit tied to critic evaluation."""
    query = """
    INSERT INTO seo_audits (
        critic_log_id, seo_score, seo_passed, issues_json, meta_tags_json, created_at
    ) VALUES (?, ?, ?, ?, ?, ?)
    """

# In critic_agent.py after save_critic_log(...)
if req.check_seo_compliance:
    save_seo_audit(
        critic_log_id=critic_log_id,
        seo_score=seo_report.score,
        seo_passed=seo_report.passed,
        issues_json=json.dumps([i.__dict__ for i in seo_report.issues]),
        meta_tags_json=json.dumps(seo_report.meta_tags),
    )
```

---

### Step 4: Database Updates
**File:** `database.py`

```python
def save_seo_audit(
    critic_log_id: int,
    seo_score: float,
    seo_passed: bool,
    issues_json: str,
    meta_tags_json: str,
):
    """Save SEO compliance results."""
    query = """
    INSERT INTO seo_audits (
        critic_log_id, seo_score, seo_passed, issues_json, meta_tags_json, created_at
    ) VALUES (?, ?, ?, ?, ?, ?)
    """
    # Execute...
```

---

### Step 5: Testing
**File:** `tests/test_seo_compliance.py` (new)

```python
import pytest
from seo_content_compliance import ContentSEOCompliance

def test_keyword_presence():
    checker = ContentSEOCompliance(["vegan skincare"], "blog")
    report = checker.audit(
        content="This guide covers vegan skincare products and organic alternatives...",
        title="Ultimate Guide to Vegan Skincare"
    )
    assert report.score >= 70
    assert report.passed

def test_low_readability():
    checker = ContentSEOCompliance(["test"], "blog")
    report = checker.audit(
        content="Antidisestablishmentarianism represents multifaceted epistemological quandaries..."
    )
    assert any(issue.category == "readability" for issue in report.issues)

def test_short_content():
    checker = ContentSEOCompliance(["test"], "blog")
    report = checker.audit(content="Too short.")
    assert not report.passed
    assert any(issue.category == "structure" for issue in report.issues)
```

---

## Summary: Implementation Sequence

### Week 1: Foundation
1. **Day 1-2:** Setup dependencies, create 3 modules (zero_shot_classifier.py, nli_evaluator.py, discounted_bandit.py)
2. **Day 3:** Create seo_content_compliance.py
3. **Day 4:** Database migrations (add NLI columns, create seo_audits table)
4. **Day 5:** Unit tests for all modules

### Week 2: Integration
1. **Day 1:** Update intelligent_router.py (zero-shot integration)
2. **Day 2:** Update critic_agent.py (NLI integration)
3. **Day 3:** Update budget_allocator.py (D-UCB integration)
4. **Day 4:** Update critic_agent.py + database.py (SEO compliance integration)
5. **Day 5:** Integration tests, fix issues

### Week 3: Optimization & Docs
1. **Day 1-2:** Performance benchmarking, optimization
2. **Day 3-4:** Documentation, examples
3. **Day 5:** End-to-end testing, deployment prep

---

