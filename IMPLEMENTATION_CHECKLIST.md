# Implementation Checklist & Timeline

## Feature 1: Zero-Shot Classifier & Slot Filling

### Tasks
- [ ] **Step 1:** Add to requirements.txt: `transformers>=4.35.0`, `torch>=2.0.0`, `accelerate>=0.24.0`
- [ ] **Step 2:** Create `zero_shot_classifier.py` with `DynamicIntentClassifier` class
- [ ] **Step 3:** Update `intelligent_router.py` - replace hardcoded INTENT_EXAMPLES with dynamic list
- [ ] **Step 4:** Add `extract_slots()` function in zero_shot_classifier.py
- [ ] **Step 5:** Update `orchestrator.py` - handle multi-intent routing
- [ ] **Step 6:** Create `tests/test_zero_shot.py` - 3 test cases
- [ ] **Testing:** Verify: basic classification, unknown intents, multi-intent

**Files to Create:** `zero_shot_classifier.py`  
**Files to Modify:** `intelligent_router.py`, `orchestrator.py`, `requirements.txt`  
**Estimated Time:** 6-8 hours

---

## Feature 2: Entailment (NLI) for Critic Agent

### Tasks
- [ ] **Step 1:** Create `nli_evaluator.py` with `NLIEvaluator` class using microsoft/deberta-v3-large
- [ ] **Step 2:** Create DB migration: add `entailment_label`, `entailment_score` columns to critic_logs
- [ ] **Step 3:** Update `critic_agent.py` - replace cosine similarity with NLI check in `_evaluate()`
- [ ] **Step 4:** Update `CriticResponse` model - add `entailment_label`, `entailment_reasoning`, `entailment_score`
- [ ] **Step 5:** Modify scoring logic:
  - Entailment: score = 0.90 + (0.10 * entailment_score)
  - Contradiction: score = 0.0 (auto-fail)
  - Neutral: score = 0.5 * embedding_similarity
- [ ] **Step 6:** Create `tests/test_nli_evaluator.py` - 3 test cases
- [ ] **Testing:** Verify: entailment, contradiction, neutral detection

**Files to Create:** `nli_evaluator.py`, database migration script  
**Files to Modify:** `critic_agent.py`, `database.py`  
**DB Changes:** 2 new columns in critic_logs table  
**Estimated Time:** 8-10 hours

---

## Feature 3: Discounted UCB (D-UCB) for Budget Allocation

### Tasks
- [ ] **Step 1:** Create `discounted_bandit.py` with `DiscountedUCB` class
- [ ] **Step 2:** Implement decay math: weight = γ^(days_old)
- [ ] **Step 3:** Update `budget_allocator.py` - replace ParametricBandit with DiscountedUCB
- [ ] **Step 4:** Update `orchestrator.py` - add `/allocate-budget` endpoint with gamma parameter
- [ ] **Step 5:** Add `/update-campaign-performance` endpoint for recording observations
- [ ] **Step 6:** Add `.env` config: `BANDIT_GAMMA=0.95`, `ALLOCATION_STRATEGY=proportional`
- [ ] **Step 7:** Create `tests/test_discounted_bandit.py` - 2 test cases
- [ ] **Testing:** Verify: decay adaptation, strategy selection differs from standard bandit

**Files to Create:** `discounted_bandit.py`  
**Files to Modify:** `budget_allocator.py`, `orchestrator.py`, `.env`  
**Estimated Time:** 10-12 hours

---

## Feature 4: SEO Compliance in Critic Agent

### Tasks
- [ ] **Step 1:** Create `seo_content_compliance.py` with `ContentSEOCompliance` class
- [ ] **Step 2:** Implement 5 audit methods:
  - [ ] `_check_keywords()` - density (1-3%), presence
  - [ ] `_check_readability()` - Flesch-Kincaid, TTR (lexical diversity)
  - [ ] `_check_structure()` - word count (300+), intro/body/conclusion
  - [ ] `_check_markup()` - meta title (50-60 chars), description (120-160)
  - [ ] `_check_linking()` - CTA presence, engagement hook
- [ ] **Step 3:** Create `SEOComplianceReport` and `SEOComplianceIssue` dataclasses
- [ ] **Step 4:** Update `critic_agent.py` request/response models:
  - [ ] Add `check_seo_compliance: bool = False` in `CriticRequest`
  - [ ] Add `seo_score`, `seo_passed`, `seo_issues` in `CriticResponse`
- [ ] **Step 5:** Update `critic_agent.py` `_evaluate()` flow:
  - [ ] Run SEO audit when `check_seo_compliance=True`
  - [ ] Merge SEO into overall score (e.g., 15% weight)
  - [ ] Include SEO findings in critique text
- [ ] **Step 6:** Create DB table: `seo_audits` (`critic_log_id`, `seo_score`, `seo_passed`, `issues_json`, `meta_tags_json`)
- [ ] **Step 7:** Persist SEO audit result from critic evaluation
- [ ] **Step 8:** Create `tests/test_seo_compliance.py` and critic integration tests
- [ ] **Testing:** Verify: keyword detection, readability issues, structure validation, critic response fields, DB persistence

**Files to Create:** `seo_content_compliance.py`, database migration  
**Files to Modify:** `critic_agent.py`, `database.py`  
**DB Changes:** New seo_audits table  
**Estimated Time:** 8-10 hours

---

## Implementation Timeline

### Week 1: Foundation (Days 1-5)
```
Day 1-2: Zero-Shot Classifier
├─ Create zero_shot_classifier.py
├─ Add dependencies to requirements.txt
└─ Write unit tests

Day 2-3: NLI Evaluator
├─ Create nli_evaluator.py
├─ Design DB migration
└─ Write unit tests

Day 3-4: Discounted Bandit
├─ Create discounted_bandit.py
├─ Add .env config
└─ Write unit tests

Day 4-5: SEO Compliance
├─ Create seo_content_compliance.py
├─ Design SEO audit logic
└─ Write unit tests
```

### Week 2: Integration (Days 6-10)
```
Day 6: Zero-Shot Integration
├─ Update intelligent_router.py
├─ Update orchestrator.py
└─ Integration tests

Day 7: NLI Integration
├─ Execute DB migration
├─ Update critic_agent.py
└─ Integration tests

Day 8: D-UCB Integration
├─ Update budget_allocator.py
├─ Update orchestrator.py endpoints
└─ Integration tests

Day 9: SEO Compliance Integration
├─ Update critic_agent.py
├─ Persist SEO results in database.py
└─ Integration tests

Day 10: End-to-End Testing
├─ Test full workflows
├─ Bug fixes
└─ Performance verification
```

### Week 3: Optimization & Deployment (Days 11-15)
```
Day 11: Performance Tuning
├─ Benchmark latency
├─ Optimize model loading
└─ Profile memory

Day 12-13: Documentation
├─ Update README
├─ Add API docs
├─ Create examples
└─ Add troubleshooting guide

Day 14: Deployment Prep
├─ Code review
├─ Security audit
└─ Final testing

Day 15: Go-Live
├─ Deploy to production
├─ Monitor performance
└─ Document changes
```

---

## Dependency Installation Order

```bash
# 1. Install Python packages
pip install transformers==4.35.0
pip install torch==2.0.0
pip install accelerate==0.24.0
pip install scipy>=1.9.0  # For optimization in bandit

# 2. Verify installations
python -c "from transformers import pipeline; print('✓ Transformers loaded')"
python -c "import torch; print('✓ PyTorch loaded')"
python -c "from scipy.optimize import minimize; print('✓ SciPy loaded')"

# 3. Test model downloads (will cache locally)
python -c "from transformers import pipeline; p = pipeline('zero-shot-classification', model='facebook/bart-large-mnli')"
python -c "from transformers import pipeline; p = pipeline('zero-shot-classification', model='microsoft/deberta-v3-large')"
```

---

## Database Migrations

### Migration 1: Add NLI Columns (for critic_agent)
```sql
-- File: migrations/001_add_entailment_columns.sql
ALTER TABLE critic_logs ADD COLUMN entailment_label TEXT DEFAULT 'neutral';
ALTER TABLE critic_logs ADD COLUMN entailment_score REAL DEFAULT 0.5;
CREATE INDEX idx_entailment_label ON critic_logs(entailment_label);
```

### Migration 2: Create SEO Audits Table
```sql
-- File: migrations/002_create_seo_audits_table.sql
CREATE TABLE seo_audits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_id TEXT NOT NULL UNIQUE,
    seo_score REAL,
    seo_passed BOOLEAN,
    issues_json TEXT,
    meta_tags_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_seo_content ON seo_audits(content_id);
CREATE INDEX idx_seo_score ON seo_audits(seo_score);
```

---

## Model Download Sizes

| Model | Size | Load Time | Speed |
|-------|------|-----------|-------|
| facebook/bart-large-mnli | ~406MB | ~3-5s | Fast (CPU) |
| microsoft/deberta-v3-large | ~435MB | ~5-8s | Faster (GPU) |
| all-MiniLM-L6-v2 | ~80MB | <1s | Very fast |
| **Total** | **~920MB** | **~8-13s** | OK for CPU |

**Optimization:** Models cached locally after first load, so subsequent requests are instant.

---

## Environment Variables (.env)

```env
# Zero-Shot Classifier (intelligent_router.py)
ZERO_SHOT_MODEL=facebook/bart-large-mnli
ZERO_SHOT_THRESHOLD=0.5

# NLI Evaluator (critic_agent.py)
NLI_MODEL=microsoft/deberta-v3-large
NLI_ENTAILMENT_WEIGHT=0.90  # If entailment, score = 0.90 + bonus

# Discounted UCB (budget_allocator.py)
BANDIT_GAMMA=0.95
ALLOCATION_STRATEGY=proportional
EXPLORATION_CONSTANT=1.5

# SEO Compliance (critic_agent.py)
SEO_MIN_WORD_COUNT=300
SEO_TARGET_GRADE_LEVEL=9
SEO_KEYWORD_DENSITY_MIN=0.5
SEO_KEYWORD_DENSITY_MAX=4.0

# Model caching
HF_HUB_LOCAL_DIR_USE_SYMLINKS=False
```

---

## Testing Checklist

### Zero-Shot Classifier Tests
```python
✓ test_basic_classification() - Known intent
✓ test_unknown_intent() - Falls back to closest match
✓ test_multi_intent() - Multiple intents detected
✓ test_confidence_score() - Confidence 0.0-1.0
✓ test_slot_extraction() - Extracts entities
```

### NLI Evaluator Tests
```python
✓ test_entailment_detected() - Content supports intent
✓ test_contradiction_detected() - Content opposes intent
✓ test_neutral_detected() - Content loosely related
✓ test_confidence_scores() - Scores sum to 1.0
✓ test_reasoning_text() - Human-readable explanation
```

### Discounted Bandit Tests
```python
✓ test_decay_adaptation() - Recent > old data
✓ test_gamma_factor() - γ^days_old applied
✓ test_allocation_strategies() - Proportional, epsilon-greedy, top-two
✓ test_trend_changes() - Adapts within 5-7 days
✓ test_comparison_with_standard_ucb() - Different behavior
```

### SEO Compliance Tests
```python
✓ test_keyword_presence() - Detects keywords
✓ test_keyword_density() - Flags over/under-stuffing
✓ test_readability() - Detects high grade level
✓ test_structure() - Checks intro/body/conclusion
✓ test_meta_generation() - Creates correct length titles/descriptions
✓ test_linking() - Detects CTA, engagement hooks
✓ test_combined_score() - Weighted average calculation
```

---

## Acceptance Criteria

### Feature 1 Acceptance ✓
- [ ] Zero-shot classifier loads in <10s
- [ ] Classifies known intents with >90% accuracy
- [ ] Handles unknown intents gracefully
- [ ] Detects multi-intent cases (2+ labels)
- [ ] Extracts 3+ slots from sample queries
- [ ] All unit tests pass
- [ ] Latency <500ms per classification

### Feature 2 Acceptance ✓
- [ ] NLI model loads in <15s
- [ ] Detects entailment with >85% accuracy on MNLI validation set
- [ ] Detects contradiction with >85% accuracy
- [ ] Database migrations execute without error
- [ ] Critic scores change based on entailment label
- [ ] API returns entailment info in response
- [ ] Latency <500ms per evaluation

### Feature 3 Acceptance ✓
- [ ] Bandit loads and initializes in <1s
- [ ] D-UCB selects differently from standard UCB within 7 days
- [ ] Allocation respects gamma decay factor
- [ ] Supports 3 strategies (proportional, epsilon-greedy, top-two)
- [ ] Budget allocation endpoint responds in <100ms
- [ ] Performance data persists in DB
- [ ] Latency <100ms per allocation decision

### Feature 4 Acceptance ✓
- [ ] SEO checker loads in <1s
- [ ] Calculates score 0-100 correctly
- [ ] Detects keyword density issues
- [ ] Flags readability problems (grade > 12)
- [ ] Checks structure (word count, intro/body/conclusion)
- [ ] Generates valid meta tags
- [ ] Detects CTA and hooks
- [ ] Critic API returns seo_score, seo_passed, and seo_issues when enabled
- [ ] SEO audit rows are persisted and linked to critic logs
- [ ] All unit tests pass
- [ ] Latency <200ms per audit

---

## Rollback Plan

If any feature fails integration:

1. **Zero-Shot:** Revert to embedding-based router (old code in git)
2. **NLI:** Disable entailment check in critic, keep cosine similarity
3. **D-UCB:** Switch ALLOCATION_STRATEGY env var to "standard"
4. **SEO:** Make check_seo_compliance optional, default False

---

## Success Metrics

### Performance
- [ ] All inference requests <1s (99th percentile)
- [ ] No memory leaks over 24-hour run
- [ ] Model caching working (2nd+ requests <100ms)

### Accuracy
- [ ] Intent classification accuracy >85%
- [ ] Entailment detection >80% on test set
- [ ] SEO compliance score correlated with manual QA

### Adoption
- [ ] 100% of critic evaluations with `check_seo_compliance=true` return SEO results
- [ ] 100% of critic evaluations include entailment
- [ ] Budget allocation uses D-UCB by default

---

