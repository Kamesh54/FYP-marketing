# Implementation Quick Reference

## High-Level Overview

```
FEATURE 1: Zero-Shot Classifier
└─ Module: zero_shot_classifier.py
   └─ Class: DynamicIntentClassifier
      └─ Method: classify(text, candidate_labels) → top_intent, confidence, multi_intent
   └─ Integration: intelligent_router.py
      └─ Replace: INTENT_EXAMPLES (hardcoded) → dynamic list from .env
   └─ Time: 6-8 hours
   └─ Cost: Free (local transformers)

FEATURE 2: Entailment (NLI)
└─ Module: nli_evaluator.py
   └─ Class: NLIEvaluator
      └─ Method: check_entailment(premise, hypothesis) → entailment/neutral/contradiction
   └─ Integration: critic_agent.py
      └─ Replace: Cosine similarity scoring → NLI-based scoring
      └─ Add DB columns: entailment_label, entailment_score
   └─ Time: 8-10 hours
   └─ Cost: Free (local transformers)

FEATURE 3: Discounted UCB (D-UCB)
└─ Module: discounted_bandit.py
   └─ Class: DiscountedUCB
      └─ Method: select_campaign() → best campaign based on D-UCB index
      └─ Method: allocate_budget() → {campaign: budget} mapping
   └─ Integration: budget_allocator.py + orchestrator.py
      └─ Replace: Standard Bandit → DiscountedUCB with gamma factor
      └─ Add endpoint: /allocate-budget, /update-campaign-performance
   └─ Time: 10-12 hours
   └─ Cost: Free (local NumPy)

FEATURE 4: SEO Compliance
└─ Module: seo_content_compliance.py
   └─ Class: ContentSEOCompliance
      └─ Method: audit(content, title, url) → SEOComplianceReport (score 0-100)
      └─ Checks: Keyword (25%), Readability (20%), Structure (25%), Markup (15%), Linking (15%)
   └─ Integration: content_agent.py + critic_agent.py
      └─ Add endpoint: /generate-blog-with-seo
      └─ Add DB table: seo_audits
   └─ Time: 12-15 hours
   └─ Cost: Free (Python rules)

TOTAL TIME: 60-75 hours (~3 weeks)
TOTAL COST: $0 (all local inference)
```

---

## Implementation Dependency Graph

```
FOUNDATION PHASE (Days 1-5)
├─ Create zero_shot_classifier.py ──────┐
├─ Create nli_evaluator.py ─────────────├─→ All ready by Day 5
├─ Create discounted_bandit.py ─────────┤
└─ Create seo_content_compliance.py ────┘

INTEGRATION PHASE (Days 6-10)
├─ Feature 1 → intelligent_router.py ──┐
├─ Feature 2 → critic_agent.py ────────├─→ All integrated by Day 10
│            + database.py (migrate)   │
├─ Feature 3 → budget_allocator.py ────┤
│            + orchestrator.py         │
└─ Feature 4 → content_agent.py ───────┘
              + critic_agent.py

TESTING PHASE (Days 10-12)
├─ Unit tests (all modules) ───────────┐
├─ Integration tests ────────────────────├─→ All verified by Day 12
└─ End-to-end workflow tests ──────────┘

DEPLOYMENT PHASE (Days 13-15)
├─ Performance optimization ──────────┐
├─ Documentation ───────────────────────├─→ Ready for production
└─ Deployment ──────────────────────────┘
```

---

## Code Changes Summary

### New Files (4)
```
zero_shot_classifier.py        (150 lines)
nli_evaluator.py               (180 lines)
discounted_bandit.py           (250 lines)
seo_content_compliance.py       (400 lines)
────────────────────────────────────────
Total new code: ~980 lines
```

### Modified Files (5)
```
intelligent_router.py          (+50 lines)
critic_agent.py                (+80 lines)
budget_allocator.py            (+50 lines)
content_agent.py               (+60 lines)
orchestrator.py                (+100 lines)
.env                           (+5 lines)
────────────────────────────────────────
Total modifications: ~345 lines
```

### Database Changes (2)
```
1. Add 2 columns to critic_logs
2. Create new seo_audits table
```

---

## Step 1-by-1 Breakdown

### FEATURE 1: Zero-Shot Classifier

#### STEP 1.1: Create Module (2 hours)
```python
# File: zero_shot_classifier.py
class DynamicIntentClassifier:
    def __init__(self, model_name="facebook/bart-large-mnli"):
        self.classifier = pipeline("zero-shot-classification", model=model_name)
    
    def classify(self, text, candidate_labels, multi_class=False, threshold=0.5):
        result = self.classifier(text, candidate_labels, multi_class=multi_class)
        return {
            "top_intent": result["labels"][0],
            "confidence": result["scores"][0],
            "multi_intent": [label for label, score in zip(result["labels"], result["scores"]) if score >= threshold]
        }
```

#### STEP 1.2: Update Router (1 hour)
```python
# File: intelligent_router.py
from zero_shot_classifier import get_classifier

DEFAULT_INTENTS = ["general_chat", "seo_analysis", "blog_generation", ...]

async def route_user_query(message, history):
    classifier = get_classifier()
    result = classifier.classify(message, DEFAULT_INTENTS, multi_class=True)
    return {
        "intent": result["top_intent"],
        "confidence": result["confidence"],
        "multi_intent": result["multi_intent"]
    }
```

#### STEP 1.3: Update Orchestrator (1 hour)
```python
# File: orchestrator.py
router_result = await router.route_user_query(message)
if router_result["confidence"] < 0.5:
    logger.warning(f"Low confidence: {router_result}")
if router_result.get("multi_intent"):
    # Handle multi-intent routing
```

#### STEP 1.4: Add Tests (1 hour)
```python
# File: tests/test_zero_shot.py
def test_basic_classification():
    result = classifier.classify("write a blog about vegan skincare", ["blog_generation", "seo_analysis"])
    assert result["top_intent"] == "blog_generation"
    assert result["confidence"] > 0.7
```

**Subtotal: 5 hours**

---

### FEATURE 2: Entailment (NLI)

#### STEP 2.1: Create NLI Module (2 hours)
```python
# File: nli_evaluator.py
class NLIEvaluator:
    def __init__(self, model_name="microsoft/deberta-v3-large"):
        self.nli = pipeline("zero-shot-classification", model=model_name)
    
    def check_entailment(self, premise, hypothesis):
        result = self.nli(
            f"Premise: {premise}\nHypothesis: {hypothesis}",
            ["entailment", "neutral", "contradiction"]
        )
        return {
            "label": result["labels"][0],
            "entailment_score": result["scores"][result["labels"].index("entailment")],
            "reasoning": f"Content {result['labels'][0]} intent"
        }
```

#### STEP 2.2: Database Migration (1 hour)
```sql
ALTER TABLE critic_logs ADD COLUMN entailment_label TEXT DEFAULT 'neutral';
ALTER TABLE critic_logs ADD COLUMN entailment_score REAL DEFAULT 0.5;
```

#### STEP 2.3: Update Critic Agent (2 hours)
```python
# File: critic_agent.py
nli = get_nli_evaluator()
nli_result = nli.check_entailment(req.original_intent, content[:2000])

if nli_result["label"] == "entailment":
    intent_score = 0.90 + (0.10 * nli_result["entailment_score"])
elif nli_result["label"] == "contradiction":
    intent_score = 0.0  # Auto-fail
else:  # neutral
    intent_score = 0.5 * embedding_similarity
```

#### STEP 2.4: Update Response Model (0.5 hours)
```python
class CriticResponse(BaseModel):
    entailment_label: Optional[str] = None
    entailment_reasoning: Optional[str] = None
    entailment_score: Optional[float] = None
```

#### STEP 2.5: Add Tests (1.5 hours)
```python
# tests/test_nli_evaluator.py
def test_entailment(): assert nli.check_entailment(...) == "entailment"
def test_contradiction(): assert nli.check_entailment(...) == "contradiction"
```

**Subtotal: 7 hours**

---

### FEATURE 3: Discounted UCB

#### STEP 3.1: Create Bandit Module (3 hours)
```python
# File: discounted_bandit.py
class DiscountedUCB:
    def __init__(self, campaigns, gamma=0.95):
        self.gamma = gamma
        self.campaign_stats = {cid: CampaignStats(cid) for cid in campaigns}
    
    def add_observation(self, campaign_id, budget_spent, clicks):
        obs = CampaignObservation(datetime.now(), budget_spent, clicks)
        self.campaign_stats[campaign_id].observations.append(obs)
        self._update_discounted_stats(campaign_id)
    
    def select_campaign(self):
        # Compute D-UCB index for each campaign
        # Return highest
        return max_campaign_by_dcb_index()
```

#### STEP 3.2: Update Budget Allocator (1.5 hours)
```python
# File: budget_allocator.py
from discounted_bandit import DiscountedUCB

class ParametricBandit:
    def __init__(self, campaigns, gamma=0.95):
        self.bandit = DiscountedUCB(campaigns, gamma)
    
    def allocate(self, total_budget):
        return self.bandit.allocate_budget(total_budget, strategy="proportional")
```

#### STEP 3.3: Update Orchestrator Endpoints (1.5 hours)
```python
# File: orchestrator.py
@app.post("/allocate-budget")
def allocate_budget(campaigns, total_budget, gamma=0.95):
    allocator = ParametricBandit(campaigns, gamma)
    # Load history, allocate
    return {"allocation": {...}}

@app.post("/update-campaign-performance")
def update_performance(campaign_id, budget_spent, clicks):
    db.save_campaign_performance(...)
```

#### STEP 3.4: Configuration (.env) (0.5 hours)
```
BANDIT_GAMMA=0.95
ALLOCATION_STRATEGY=proportional
```

#### STEP 3.5: Add Tests (2 hours)
```python
# tests/test_discounted_bandit.py
def test_decay_adaptation(): # Old data < recent data
def test_strategy_selection(): # D-UCB differs from standard
```

**Subtotal: 8.5 hours**

---

### FEATURE 4: SEO Compliance

#### STEP 4.1: Create SEO Module (3 hours)
```python
# File: seo_content_compliance.py
class ContentSEOCompliance:
    def __init__(self, target_keywords, content_type="blog"):
        self.target_keywords = target_keywords
    
    def audit(self, content, title="", url=""):
        keyword_score = self._check_keywords(content, title)
        readability_score = self._check_readability(content)
        structure_score = self._check_structure(content)
        markup_score = self._check_markup(content, title)
        linking_score = self._check_linking(content)
        
        overall = weighted_average(...)
        return SEOComplianceReport(score=overall, issues=issues, ...)
```

#### STEP 4.2: Create DB Table (1 hour)
```sql
CREATE TABLE seo_audits (
    id INTEGER PRIMARY KEY,
    content_id TEXT UNIQUE,
    seo_score REAL,
    seo_passed BOOLEAN,
    issues_json TEXT,
    meta_tags_json TEXT,
    created_at TIMESTAMP
);
```

#### STEP 4.3: Integrate with Content Agent (1.5 hours)
```python
# File: content_agent.py
@app.post("/generate-blog-with-seo")
async def generate_blog_with_seo(req):
    content = await generate_blog(req)
    keywords = extract_keywords(req.intent)
    seo_report = ContentSEOCompliance(keywords).audit(content)
    return {"content": content, "seo_score": seo_report.score, ...}
```

#### STEP 4.4: Integrate with Critic (1 hour)
```python
# File: critic_agent.py
if req.check_seo_compliance:
    seo_report = ContentSEOCompliance(keywords).audit(req.content_text)
    overall_score = 0.35*intent + 0.25*brand + 0.25*quality + 0.15*(seo/100)
```

#### STEP 4.5: Add Tests (1.5 hours)
```python
# tests/test_seo_compliance.py
def test_keyword_presence(): # Detects keywords
def test_readability(): # Flags high grade level
def test_scoring(): # 0-100 score computed
```

**Subtotal: 8.5 hours**

---

## Total Time by Phase

| Phase | Duration | Days |
|-------|----------|------|
| Setup & Dependencies | 1 hour | 0.125 |
| Feature 1 (Zero-Shot) | 5 hours | 0.625 |
| Feature 2 (NLI) | 7 hours | 0.875 |
| Feature 3 (D-UCB) | 8.5 hours | 1.0625 |
| Feature 4 (SEO) | 8.5 hours | 1.0625 |
| **Foundation Total** | **30 hours** | **3.75 days** |
| Integration Testing | 10 hours | 1.25 days |
| E2E Testing | 8 hours | 1 day |
| Documentation | 5 hours | 0.625 days |
| Optimization | 4 hours | 0.5 days |
| **Full Total** | **~60 hours** | **~3 weeks (with 1 dev)** |

---

## Critical Path for Implementation

```
Day 1 (8h):
  ✓ Dependencies installed
  ✓ zero_shot_classifier.py created + tested
  ✓ nli_evaluator.py created + tested

Day 2 (8h):
  ✓ discounted_bandit.py created + tested
  ✓ seo_content_compliance.py created + tested
  ✓ DB migrations prepared

Day 3 (8h):
  ✓ intelligent_router.py updated (Feature 1)
  ✓ critic_agent.py updated (Feature 2)
  ✓ DB migrations executed

Day 4 (8h):
  ✓ budget_allocator.py updated (Feature 3)
  ✓ content_agent.py updated (Feature 4)
  ✓ orchestrator.py updated (all features)

Day 5 (8h):
  ✓ Integration tests
  ✓ Bug fixes
  ✓ Performance verification

Days 6-7 (16h):
  ✓ E2E testing
  ✓ Documentation
  ✓ Optimization

Day 8+ (Deployment):
  ✓ Staging tests
  ✓ Production rollout
  ✓ Monitoring
```

---

## Command Sequence for Setup

```bash
# 1. Install Python dependencies
pip install -r requirements.txt  # Already includes most deps
pip install transformers==4.35.0
pip install torch==2.0.0
pip install accelerate==0.24.0

# 2. Verify installations
python -c "from transformers import pipeline; print('✓ OK')"
python -c "import torch; print('✓ OK')"

# 3. Create new modules (copy from IMPLEMENTATION_STEPS.md)
# - zero_shot_classifier.py
# - nli_evaluator.py
# - discounted_bandit.py
# - seo_content_compliance.py

# 4. Run tests
pytest tests/test_zero_shot.py -v
pytest tests/test_nli_evaluator.py -v
pytest tests/test_discounted_bandit.py -v
pytest tests/test_seo_compliance.py -v

# 5. Apply database migrations
# - migrations/001_add_entailment_columns.sql
# - migrations/002_create_seo_audits_table.sql

# 6. Update configuration
# - .env file with new variables

# 7. Integration testing
pytest tests/integration/test_features.py -v

# 8. Run full system
python orchestrator.py
python intelligent_router.py  # (separate service, if needed)
```

---

## Success Criteria Summary

### ✓ Zero-Shot Feature
- Classifies known intents with >90% accuracy
- Handles unknown intents gracefully (picks closest match)
- Detects multi-intent cases
- Latency <500ms

### ✓ NLI Feature
- Detects entailment with >85% accuracy
- Detects contradictions (prevents bad content)
- Integrates with critic scoring
- Latency <500ms

### ✓ D-UCB Feature
- Allocates budget based on recent trends
- Adapts faster than standard UCB
- Supports multiple strategies
- Latency <100ms

### ✓ SEO Feature
- Scores content 0-100
- Detects keyword issues
- Flags readability problems
- Generates valid meta tags
- Latency <200ms

---

