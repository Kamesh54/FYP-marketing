# Implementation Assessment & Plan
## Advanced Features: NLI, D-UCB, & SEO Content Compliance

**Assessment Date:** April 17, 2026  
**Status:** ❌❌❌ None of the three features are implemented

---

## 1. Zero-Shot Classifier & Slot Filling for Intent Finding ❌

### Current State
- **File:** `intelligent_router.py`
- **Method:** Sentence Transformers with embedding-based cosine similarity
- **Limitation:** Rigid intent matching against 13 predefined intents

```python
# Current approach (line 133 in intelligent_router.py):
INTENT_EXAMPLES = {
    "general_chat": "hello what can you do help me understand this",
    "seo_analysis": "analyse my website SEO audit check page optimisation",
    "blog_generation": "write a blog post create an article generate content",
    # ... 10 more hardcoded intents
}
```

**Issues:**
- ❌ Not a zero-shot classifier (only works with predefined intents)
- ❌ No slot filling (cannot extract parameters from user intent)
- ❌ Fails gracefully at runtime if unknown intent is encountered
- ❌ Requires manual enum updates for new intents

### Proposed Solution
Implement **zero-shot text classification** using the `transformers` library:

```python
# Pseudocode - what we'll implement
from transformers import pipeline

classifier = pipeline(
    "zero-shot-classification",
    model="facebook/bart-large-mnli"  # Pre-trained on NLI task
)

# Can classify ANY intent without predefined enum
result = classifier(
    "I need to optimize my website for Google",
    candidate_labels=[
        "SEO optimization",
        "Content creation", 
        "Social media",
        "Competitor analysis"
    ],
    multi_class=True
)
# Returns top-k scores dynamically
```

**Benefits:**
- ✅ Works with unlimited intent types
- ✅ Confidence scores guide routing
- ✅ Can handle multi-intent queries
- ✅ No enum maintenance needed

---

## 2. Entailment (Natural Language Inference) for Critic Agent ❌

### Current State
- **File:** `critic_agent.py` (lines 300-400)
- **Method:** Cosine similarity on sentence embeddings
- **Threshold:** Static 0.85 similarity score

```python
# Current approach:
intent_emb = _critic_model.encode(req.original_intent, normalize_embeddings=True)
intent_score = min(1.0, max(0.0, cosine(intent_emb, content_emb) * 1.5))
# Purely syntactic/semantic similarity - NOT logical entailment
```

**Issues:**
- ❌ No **logical entailment** check (Statement A ⊨ Statement B)
- ❌ Cannot detect **contradictions** in generated content
- ❌ Treats "opposite" statements as high similarity if embeddings are close
- ❌ Example failure:
  - Intent: "Create an eco-friendly product guide"
  - Generated: "Why plastic pollution is acceptable"
  - Current: ~0.7 similarity (PASS ❌)
  - With NLI: "Contradiction" (FAIL ✅)

### Proposed Solution
Integrate **Natural Language Inference (NLI) model**:

```python
# Pseudocode - what we'll implement
from transformers import pipeline

# Pre-trained on MNLI (Multi-Genre Natural Language Inference)
nli_classifier = pipeline(
    "zero-shot-classification",
    model="microsoft/deberta-v3-large"  # Modern high-accuracy NLI
)

def check_entailment(intent: str, generated_content: str) -> dict:
    """
    Check if generated content logically follows from intent.
    Returns: {"label": "entailment" | "neutral" | "contradiction", "score": 0.0-1.0}
    """
    # Premise: Original intent
    # Hypothesis: Generated content
    result = nli_classifier(
        f"Intent: {intent}",
        [f"Content: {generated_content}"],
        hypothesis_template="{}",
        multi_class=False
    )
    return result

# Example usage in critic_agent.py:
entailment_result = check_entailment(
    req.original_intent,
    req.content_text[:2000]  # First 2K chars for efficiency
)

# New scoring:
if entailment_result["label"] == "entailment":
    intent_score = 0.95 * entailment_result["score"]  # High confidence
elif entailment_result["label"] == "neutral":
    intent_score = 0.50 * entailment_result["score"]  # Medium
else:  # contradiction
    intent_score = 0.0  # Auto-fail if contradicts intent
```

**Benefits:**
- ✅ Detects logical contradictions (prevents bad content)
- ✅ More robust than similarity (handles paraphrasing)
- ✅ Returns 3 labels: Entailment (Good), Neutral (Mediocre), Contradiction (Bad)
- ✅ Better explains why content failed to user

**Integration Points:**
1. `critic_agent.py` → Replace cosine similarity scoring with NLI check
2. `database.py` → Add `entailment_label` and `entailment_score` columns
3. API response → Include entailment reasoning in critique_text

---

## 3. Discounted UCB (D-UCB) for Budget Allocation ❌

### Current State
- **File:** `budget_allocator.py`
- **Method:** Parametric Multi-Armed Bandit (standard UCB)
- **Issue:** No discount factor for recent results

```python
# Current approach (line 50 in budget_allocator.py):
class ParametricBandit:
    def __init__(self, campaigns, max_budget=1000.0, ...):
        self.campaign_states = {
            cid: CampaignState(campaign_id=cid)
            for cid in campaigns
        }
        # observations = [(budget, clicks, impressions), ...]
        # ALL historical observations weighted equally - NO decay
```

**Problem Scenario:**
- Week 1-3: "Red Shirt" campaign performs excellently (500 clicks/week)
- Week 4: Trend dies out (only 10 clicks/week)
- Current system: Keeps allocating high budget based on old average
- Result: Wasted budget on dead trend

### Proposed Solution
Implement **Discounted UCB (D-UCB)** with exponential decay:

```python
# Pseudocode - what we'll implement
import numpy as np
from datetime import datetime, timedelta

class DiscountedUCB:
    def __init__(self, campaigns: List[str], gamma: float = 0.95):
        """
        Args:
            gamma: discount factor (0.9-0.99)
                   - 0.95 = observations lose 5% weight per time period
                   - 0.90 = observations lose 10% weight per time period
        """
        self.gamma = gamma
        self.campaign_states = {
            cid: {
                "observations": [],  # List of (timestamp, budget, clicks)
                "discounted_mean": 0.0,
                "discounted_variance": 0.0
            }
            for cid in campaigns
        }
    
    def compute_discounted_mean(self, campaign_id: str, current_time: datetime) -> float:
        """
        Compute weighed average that gives exponentially less weight to old observations.
        
        Math: mean = Σ(obs_i * γ^(t_now - t_i)) / Σ(γ^(t_now - t_i))
        """
        obs_list = self.campaign_states[campaign_id]["observations"]
        if not obs_list:
            return 0.0
        
        weighted_sum = 0.0
        weight_sum = 0.0
        
        for obs_timestamp, budget_spent, clicks in obs_list:
            # Days elapsed since observation
            days_ago = (current_time - obs_timestamp).days
            
            # Exponential decay: γ^days_ago
            weight = self.gamma ** days_ago
            
            # Click efficiency: clicks per dollar
            efficiency = clicks / budget_spent if budget_spent > 0 else 0
            
            weighted_sum += efficiency * weight
            weight_sum += weight
        
        return weighted_sum / weight_sum if weight_sum > 0 else 0.0
    
    def select_campaign_by_dcb_index(self, campaigns: List[str], c: float = 1.5) -> str:
        """
        Select campaign with highest Discounted Confidence Bound (D-CB) index.
        
        D-CB = discounted_mean + c * sqrt(ln(t) / N_discounted)
        
        Args:
            c: exploration constant (higher = more exploration)
        """
        indices = {}
        t = sum(len(s["observations"]) for s in self.campaign_states.values())
        
        for campaign_id in campaigns:
            mean = self.compute_discounted_mean(campaign_id, datetime.now())
            
            # Effective sample size (discounted)
            obs_list = self.campaign_states[campaign_id]["observations"]
            n_eff = sum(
                self.gamma ** (datetime.now() - obs_ts).days
                for obs_ts, _, _ in obs_list
            )
            
            # UCB = mean + exploration bonus
            exploration_bonus = c * np.sqrt(np.log(t) / max(n_eff, 1))
            indices[campaign_id] = mean + exploration_bonus
        
        return max(indices, key=indices.get)
    
    def add_observation(self, campaign_id: str, budget_spent: float, clicks: int):
        """Record new result with current timestamp for decay calculation."""
        self.campaign_states[campaign_id]["observations"].append(
            (datetime.now(), budget_spent, clicks)
        )
```

**Integration in budget allocator:**

```python
# In orchestrator.py or campaign_planner.py:

from datetime import datetime

def allocate_budget_for_next_week(campaigns, total_budget, gamma=0.95):
    """
    Use D-UCB to allocate budget, giving recent results more weight.
    """
    # Example: if campaign A had 100 clicks last week, 10 this week
    # With gamma=0.95:
    # - Last week's weight: 0.95^7 ≈ 0.70
    # - This week's weight: 0.95^0 = 1.0
    # System NOW prefers the trend, not the historical high
    
    allocator = DiscountedUCB(campaigns, gamma=0.95)
    
    # Load historical data
    for campaign in campaigns:
        history = db.get_campaign_history(campaign)
        for record in history:  # (timestamp, budget, clicks)
            allocator.add_observation(
                campaign,
                record["budget_spent"],
                record["clicks"]
            )
    
    # Select which campaign to fund
    selected = allocator.select_campaign_by_dcb_index(campaigns, c=1.5)
    
    # Allocate proportionally
    allocation = {cmp: 0.0 for cmp in campaigns}
    allocation[selected] = total_budget * 0.6  # 60% to best performer
    
    # Remaining distributed by D-UCB ranking
    remaining_budget = total_budget * 0.4
    remaining_campaigns = [c for c in campaigns if c != selected]
    for idx, cmp in enumerate(sorted(
        remaining_campaigns,
        key=lambda c: allocator.compute_discounted_mean(c, datetime.now()),
        reverse=True
    )):
        allocation[cmp] = remaining_budget / len(remaining_campaigns)
    
    return allocation
```

**Benefits:**
- ✅ Quickly adapts to trend changes (week-level decay)
- ✅ Avoids wasting budget on dead campaigns
- ✅ Mathematically principled (UCB guarantees)
- ✅ Configurable patience (gamma parameter)

---

## 4. SEO Audit for Content Compliance ❌

### Current State
- **File:** `seo_agent.py` (lines 1-200+)
- **Scope:** Website audit (crawls page, checks on-page elements)
- **Missing:** Generated content compliance checking

```python
# Current: Website audit only
def analyze_onpage(soup):
    """Checks live website elements: title, meta description, headings, etc."""
    issues = []
    # - Title tag length
    # - Meta description length
    # - H1/H2 hierarchy
    # Returns: numeric score ~0-100
    
# NOT present: Generated content compliance
```

**Gaps:**
- ❌ No "content compliance" checker for generated blog posts
- ❌ No keyword density analysis
- ❌ No schema.org markup validation for SEO
- ❌ No readability→SEO mapping
- ❌ No internal linking suggestions
- ❌ No featured snippet optimization

### Proposed Solution
Create **`seo_content_compliance.py`** module:

```python
"""
SEO Content Compliance Checker
Validates generated content against SEO best practices.
Not a crawler - evaluates text-only content for publishability.
"""

import re
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from collections import Counter

logger = logging.getLogger(__name__)

@dataclass
class SEOComplianceIssue:
    category: str  # "keyword", "readability", "structure", "markup", "linking"
    severity: str  # "error", "warning", "info"
    message: str
    suggestion: str

@dataclass
class SEOComplianceReport:
    score: float  # 0-100
    passed: bool  # score >= 70
    issues: List[SEOComplianceIssue]
    details: Dict  # breakdown by category
    meta_tags: Dict  # generated meta title, description

class ContentSEOCompliance:
    
    def __init__(self, target_keywords: List[str], content_type: str = "blog"):
        """
        Args:
            target_keywords: Intent keywords, e.g., ["vegan skincare", "natural makeup"]
            content_type: "blog" | "social" | "product" (affects thresholds)
        """
        self.target_keywords = [kw.lower() for kw in target_keywords]
        self.content_type = content_type
        
        # Category weights (sum to 1.0)
        self.weights = {
            "keyword": 0.25,
            "readability": 0.20,
            "structure": 0.25,
            "markup": 0.15,
            "linking": 0.15,
        } if content_type == "blog" else {
            "keyword": 0.15,
            "readability": 0.30,
            "structure": 0.10,
            "markup": 0.10,
            "linking": 0.35,  # Social + linking emphasis
        }
    
    def audit(self, content: str, title: str = "", url: str = "") -> SEOComplianceReport:
        """
        Comprehensive audit of content against SEO compliance.
        
        Returns:
            SEOComplianceReport with score, issues, and generated meta tags
        """
        issues = []
        details = {}
        
        # 1. KEYWORD COMPLIANCE (25%)
        keyword_score, keyword_issues, keyword_details = self._check_keywords(content, title)
        issues.extend(keyword_issues)
        details["keyword"] = keyword_details
        
        # 2. READABILITY & ENGAGEMENT (20%)
        readability_score, readability_issues, readability_details = self._check_readability(content)
        issues.extend(readability_issues)
        details["readability"] = readability_details
        
        # 3. CONTENT STRUCTURE (25%)
        structure_score, structure_issues, structure_details = self._check_structure(content)
        issues.extend(structure_issues)
        details["structure"] = structure_details
        
        # 4. SCHEMA MARKUP & META (15%)
        markup_score, markup_issues, meta_tags = self._check_markup(content, title, url)
        issues.extend(markup_issues)
        details["markup"] = {"score": markup_score, "meta": meta_tags}
        
        # 5. INTERNAL LINKING POTENTIAL (15%)
        linking_score, linking_issues, linking_details = self._check_linking(content, title)
        issues.extend(linking_issues)
        details["linking"] = linking_details
        
        # Calculate weighted score
        overall_score = (
            keyword_score * self.weights["keyword"] +
            readability_score * self.weights["readability"] +
            structure_score * self.weights["structure"] +
            markup_score * self.weights["markup"] +
            linking_score * self.weights["linking"]
        )
        
        passed = overall_score >= 70.0
        
        return SEOComplianceReport(
            score=round(overall_score, 2),
            passed=passed,
            issues=issues,
            details=details,
            meta_tags=meta_tags
        )
    
    def _check_keywords(self, content: str, title: str) -> Tuple[float, List[SEOComplianceIssue], Dict]:
        """
        Validate keyword presence, density (1-3%), and distribution.
        """
        issues = []
        words = content.lower().split()
        word_count = len(words)
        
        # Check primary keyword presence
        primary_kw = self.target_keywords[0] if self.target_keywords else ""
        if primary_kw and primary_kw not in content.lower():
            issues.append(SEOComplianceIssue(
                category="keyword",
                severity="error",
                message=f"Primary keyword '{primary_kw}' not found in content",
                suggestion=f"Naturally incorporate '{primary_kw}' in title, intro, and body"
            ))
            return 30.0, issues, {"primary_keyword": False}
        
        # Keyword density analysis
        keyword_density_score = 100.0
        keyword_presence = {}
        
        for kw in self.target_keywords:
            kw_words = kw.lower().split()
            kw_count = len(re.findall(r'\b' + r'\s+'.join(kw_words) + r'\b', content.lower()))
            density = (kw_count / max(word_count, 1)) * 100 if word_count > 0 else 0
            keyword_presence[kw] = kw_count
            
            if density < 0.5:
                issues.append(SEOComplianceIssue(
                    category="keyword",
                    severity="warning",
                    message=f"Keyword '{kw}' density is too low ({density:.1f}%)",
                    suggestion=f"Add 2-3 more mentions of '{kw}' naturally throughout"
                ))
                keyword_density_score -= 15
            elif density > 4.0:
                issues.append(SEOComplianceIssue(
                    category="keyword",
                    severity="warning",
                    message=f"Keyword '{kw}' density is too high ({density:.1f}%) - risk of overstuffing",
                    suggestion=f"Reduce mentions of '{kw}'; use synonyms instead"
                ))
                keyword_density_score -= 20
        
        # Title inclusion bonus
        title_lower = title.lower()
        if self.target_keywords and any(kw in title_lower for kw in self.target_keywords):
            keyword_density_score = min(100.0, keyword_density_score + 10)
        
        return keyword_density_score, issues, keyword_presence
    
    def _check_readability(self, content: str) -> Tuple[float, List[SEOComplianceIssue], Dict]:
        """
        Flesch-Kincaid grade, TTR, sentence variety, paragraph length.
        """
        issues = []
        
        try:
            import textstat
        except ImportError:
            textstat = None
        
        if textstat:
            fk_grade = textstat.flesch_kincaid_grade(content)
            flesch_score = textstat.flesch_reading_ease(content)  # 0-100
        else:
            # Fallback approximation
            words = content.split()
            sentences = max(1, content.count(".") + content.count("!") + content.count("?"))
            fk_grade = 0.39 * (len(words) / max(sentences, 1)) + 5.0
            flesch_score = 206.835 - 1.015 * (len(words) / max(sentences, 1)) - 84.6 * 1
        
        readability_score = 100.0
        
        # Grade 8-9 ideal for web content
        if fk_grade > 12:
            issues.append(SEOComplianceIssue(
                category="readability",
                severity="warning",
                message=f"Reading grade level too high ({fk_grade:.1f})",
                suggestion="Simplify sentences; use shorter words; break into shorter paragraphs"
            ))
            readability_score = max(50.0, 100.0 - (fk_grade - 9) * 5)
        
        # Lexical density
        unique_words = len(set(w.lower() for w in content.split() if w.isalpha()))
        total_words = len([w for w in content.split() if w.isalpha()])
        ttr = unique_words / max(total_words, 1) if total_words > 0 else 0
        
        if ttr < 0.5:
            issues.append(SEOComplianceIssue(
                category="readability",
                severity="warning",
                message="Low word variety - content may feel repetitive",
                suggestion="Use synonyms and vary vocabulary"
            ))
            readability_score -= 10
        
        # Paragraph length check
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        long_para = [p for p in paragraphs if len(p.split()) > 150]
        if long_para:
            issues.append(SEOComplianceIssue(
                category="readability",
                severity="info",
                message=f"{len(long_para)} paragraphs exceed 150 words",
                suggestion="Break long paragraphs into 2-3 shorter ones for readability"
            ))
            readability_score -= 5
        
        return min(100.0, readability_score), issues, {
            "flesch_kincaid_grade": round(fk_grade, 1),
            "flesch_reading_ease": round(flesch_score, 1),
            "ttr": round(ttr, 2),
            "avg_paragraph_length": round(sum(len(p.split()) for p in paragraphs) / max(len(paragraphs), 1), 0)
        }
    
    def _check_structure(self, content: str) -> Tuple[float, List[SEOComplianceIssue], Dict]:
        """
        H1/H2 hierarchy, intro/body/conclusion, word count.
        """
        issues = []
        structure_score = 100.0
        
        # Minimal structure check (no HTML parsing assumed for text content)
        paragraphs = [p.strip() for p in content.split("\n") if p.strip()]
        word_count = len(content.split())
        
        # Word count thresholds
        if word_count < 300:
            issues.append(SEOComplianceIssue(
                category="structure",
                severity="warning",
                message=f"Content too short ({word_count} words) - minimum 300 recommended",
                suggestion="Expand with detailed information, examples, or subheadings"
            ))
            structure_score -= 25
        elif word_count > 5000:
            issues.append(SEOComplianceIssue(
                category="structure",
                severity="warning",
                message=f"Content very long ({word_count} words) - consider breaking into multiple posts",
                suggestion="Split into series or create summary with links"
            ))
            structure_score -= 10
        
        # Intro/body/conclusion heuristic
        has_intro = len(paragraphs) > 0 and len(paragraphs[0].split()) >= 8
        has_body = len(paragraphs) >= 3
        has_conclusion = any(term in content.lower() for term in [
            "in conclusion", "to summarize", "ultimately", "in summary", "key takeaways"
        ])
        
        if not has_intro:
            structure_score -= 10
        if not has_body:
            structure_score -= 10
        if not has_conclusion:
            structure_score -= 10
        
        return max(50.0, structure_score), issues, {
            "word_count": word_count,
            "paragraph_count": len(paragraphs),
            "has_intro": has_intro,
            "has_body": has_body,
            "has_conclusion": has_conclusion
        }
    
    def _check_markup(self, content: str, title: str = "", url: str = "") -> Tuple[float, List[SEOComplianceIssue], Dict]:
        """
        Generate recommended meta tags and check for schema.org opportunity.
        """
        issues = []
        
        # Generate meta title (50-60 chars)
        primary_kw = self.target_keywords[0] if self.target_keywords else ""
        if not title:
            title = f"{primary_kw} - Guide"[:60]
        meta_title = title[:60]
        
        # Generate meta description (120-160 chars) from first text
        meta_desc = (content[:150] + "...").replace("\n", " ")
        meta_desc = meta_desc[:160]
        
        if len(meta_title) < 50:
            issues.append(SEOComplianceIssue(
                category="markup",
                severity="warning",
                message=f"Meta title too short ({len(meta_title)} chars) - target 50-60",
                suggestion=f"Expand title to include target keyword"
            ))
        
        markup_score = 70.0 if meta_title and meta_desc else 50.0
        
        return markup_score, issues, {
            "meta_title": meta_title,
            "meta_description": meta_desc,
            "suggested_schema": "Article"  # TBD: detect type
        }
    
    def _check_linking(self, content: str, title: str = "") -> Tuple[float, List[SEOComplianceIssue], Dict]:
        """
        Check for internal linking opportunities and CTA potential.
        """
        issues = []
        linking_score = 80.0
        
        # CTA presence
        cta_keywords = [
            "click here", "learn more", "sign up", "get started", "try now",
            "contact us", "schedule", "book", "shop", "discover", "read more"
        ]
        has_cta = any(cta in content.lower() for cta in cta_keywords)
        
        # Hook/engagement
        hook_keywords = ["did you know", "imagine", "what if", "struggling", "ready to"]
        has_hook = any(hook in content.lower() for hook in hook_keywords)
        
        if not has_cta:
            issues.append(SEOComplianceIssue(
                category="linking",
                severity="info",
                message="No clear call-to-action (CTA) detected",
                suggestion="Add CTA: 'Learn more', 'Sign up', 'Contact us', etc."
            ))
            linking_score -= 15
        
        if not has_hook:
            issues.append(SEOComplianceIssue(
                category="linking",
                severity="info",
                message="No engagement hook in intro",
                suggestion="Open with 'Did you know...', 'What if...', or a question"
            ))
            linking_score -= 10
        
        suggestion_count = len(self.target_keywords)  # Placeholder
        
        return linking_score, issues, {
            "has_cta": has_cta,
            "has_hook": has_hook,
            "internal_link_suggestions": suggestion_count
        }
```

**Integration with content_agent.py:**

```python
# In content_agent.py, after content generation:

from seo_content_compliance import ContentSEOCompliance

@app.post("/generate-blog-with-seo-check")
async def generate_blog_with_seo_check(req: BlogGenerationRequest):
    # Step 1: Generate content (existing)
    content = await generate_blog_content(req)
    
    # Step 2: NEW - SEO Compliance check
    target_keywords = extract_keywords(req.intent)  # From intent
    seo_checker = ContentSEOCompliance(
        target_keywords=target_keywords,
        content_type="blog"
    )
    
    seo_report = seo_checker.audit(
        content=content,
        title=req.title,
        url=req.url
    )
    
    # Step 3: Return with SEO score
    return {
        "content": content,
        "seo_score": seo_report.score,
        "seo_passed": seo_report.passed,
        "seo_issues": [
            {
                "category": issue.category,
                "severity": issue.severity,
                "message": issue.message,
                "suggestion": issue.suggestion
            }
            for issue in seo_report.issues
        ],
        "meta_tags": seo_report.meta_tags
    }
```

**Integration with critic_agent.py:**

```python
# In critic_agent.py:
from seo_content_compliance import ContentSEOCompliance

class CriticRequest(BaseModel):
    # ... existing fields ...
    check_seo_compliance: bool = False  # New optional field

@app.post("/evaluate")
async def evaluate_content(req: CriticRequest):
    # ... existing critic evaluation ...
    
    if req.check_seo_compliance:
        seo_checker = ContentSEOCompliance(
            target_keywords=[req.original_intent],
            content_type=req.content_type
        )
        seo_report = seo_checker.audit(req.content_text)
        
        # Add SEO score to overall evaluation
        seo_weight = 0.15  # 15% of final score
        overall_score = (
            0.35 * intent_score +
            0.25 * brand_score +
            0.25 * quality_score +
            seo_weight * (seo_report.score / 100.0)
        )
    
    # ... return with seo_report included ...
```

---

## Implementation Roadmap

### Phase 1: Foundation (Week 1-2)
- [ ] Install required packages: `transformers>=4.35`, `torch>=2.0`, `sentence-transformers>=2.2`
- [ ] Create `nli_evaluator.py` module (NLI integration)
- [ ] Update `requirements.txt`
- [ ] Unit tests for NLI label mapping

**Acceptance Criteria:**
- NLI model loads without errors
- Returns consistent labels (entailment/neutral/contradiction)
- Latency < 500ms per inference

### Phase 2: Integration (Week 2-3)
- [ ] Integrate NLI into `critic_agent.py` (lines 300-400)
- [ ] Update database schema: add `entailment_label`, `entailment_score` columns
- [ ] Create `seo_content_compliance.py` module
- [ ] Add zero-shot classifier to `intelligent_router.py`
- [ ] Migration script for database updates

**Acceptance Criteria:**
- Critic agent returns entailment label + score
- SEO compliance checker returns numeric score (0-100)
- Intent routing handles unknown intents gracefully
- All endpoints respond with new fields

### Phase 3: Optimization (Week 3-4)
- [ ] Integrate D-UCB into `budget_allocator.py`
- [ ] Add gamma parameter to `.env` configuration
- [ ] Create `discounted_bandit.py` module
- [ ] Performance benchmarks (latency, memory)
- [ ] Documentation + examples

**Acceptance Criteria:**
- Budget allocation respects recent performance
- Gamma parameter configurable
- D-UCB selection differs from standard UCB within 5 days
- Performance: allocation decision < 100ms

### Phase 4: Testing & Refinement (Week 4-5)
- [ ] Integration tests (end-to-end workflows)
- [ ] Benchmark against baselines
- [ ] Documentation (README updates)
- [ ] Example workflows

---

## Cost Estimation

### Model Requirements
| Feature | Model | Type | Hosting | Cost |
|---------|-------|------|---------|------|
| NLI Entailment | microsoft/deberta-v3-large | 435MB | Local CPU (~5s load) | Free* |
| Zero-Shot Classifier | facebook/bart-large-mnli | 406MB | Local CPU | Free* |
| SEO Compliance | Custom (Python rules) | N/A | N/A | Free |
| D-UCB Bandit | Custom (NumPy) | N/A | N/A | Free |

*Local inference only - no API costs (unlike Groq's 10¢-1$/call)

### Development Effort
- **NLI Integration:** 8-10 hours
- **Zero-Shot Classifier:** 6-8 hours
- **SEO Content Compliance:** 12-15 hours
- **D-UCB Bandit:** 10-12 hours
- **Testing & Integration:** 15-20 hours
- **Documentation:** 5-8 hours

**Total:** ~60-75 hours (2-3 weeks, 1 developer)

---

## Alternative Architectures

### Option 1: API-Based (Higher latency, higher cost)
```
Use Groq API for all inference:
- NLI via text generation (custom prompting)
- Zero-shot classification via LLM parsing
Cost: ~$500-1000/month at current traffic
```

### Option 2: Hybrid (Our recommendation)
```
- NLI & Zero-shot: Local transformers (free, <1s)
- SEO compliance: Local Python rules (free, <100ms)
- D-UCB: Local NumPy (free, <10ms)
- LLM: Groq for generation only (current costs)
```

### Option 3: Edge Deployment
```
Deploy models to Edge runtime (AWS Lambda, Google Cloud Run)
Pro: No local GPU required, scalable
Con: Cold start latency 3-5s, cost ~$0.30/1M inferences
```

**Recommendation:** Option 2 (Hybrid) — best ROI, zero model cost, acceptable latency

---

## References

### Papers
1. **NLI:** Devlin et al., "BERT: Pre-training of Deep Bidirectional Transformers"
   - MNLI dataset: 393K sentence pairs
   - Entailment, Neutral, Contradiction labels

2. **Zero-Shot Classification:** Yin et al., "Few-shot Text Classification with Distributional Signatures"
   - BART-large-MNLI: Transfer learning for any classification task

3. **Discounted UCB:** "Discounted Regret Bounds for Contextual Bandits" (Abbasi-Yadkori et al.)
   - Exponential decay for non-stationary environments
   - Proven sublinear regret $O(\sqrt{T})$ under discount

### Hugging Face Models
- `microsoft/deberta-v3-large` — State-of-the-art NLI (91.3% MNLI accuracy)
- `facebook/bart-large-mnli` — Zero-shot classification (BART encoder-decoder)

---

## Questions & Decisions Needed

1. **NLI Sensitivity:** Should contradictions auto-fail (score=0) or reduce score?
   - Recommendation: Auto-fail + human review via HITL

2. **D-UCB Gamma:** What decay rate (0.90 vs 0.95 vs 0.99)?
   - 0.95: Default (5% weekly decay)
   - 0.90: Aggressive (10% weekly decay for fast-changing trends)
   - Recommendation: Configurable per client

3. **SEO Compliance:** Hard fail (<70) or soft warn (<80)?
   - Recommendation: Soft warn (<80), hard fail (<50)

4. **Model hosting:** Local or cloud GPU?
   - Recommendation: Local for MVP (~500MB RAM), scale to inferenceAPI if needed

---

**Next Steps:**
1. Review and approve architecture choices
2. Set up development branch: `feature/nli-d-ucb-seo`
3. Create tickets for Phase 1 tasks
4. Schedule kickoff meeting

