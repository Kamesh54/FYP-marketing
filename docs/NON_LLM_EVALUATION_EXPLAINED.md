# How the Non-LLM Evaluation Pipeline Works

## Overview

Two components were replaced so that **no API token is spent on evaluation**:

| Component | Before | After |
|---|---|---|
| Intent Router (`intelligent_router.py`) | Groq LLM call (~1 s, costs tokens) | Sentence-transformer cosine similarity (~5 ms, free) |
| Content Critic (`critic_agent.py`) | Groq LLM call (~1 s, costs tokens) | Embedding similarity + readability math (~5 ms, free) |

The Groq LLM is still used for **generative tasks only** (writing blog posts, social captions, chat replies).
Evaluation — deciding *how good* something is — is now done with mathematics.

---

## Part 1 — Embedding-Based Intent Router

### What is a sentence embedding?

A sentence embedding is a list of 384 numbers (a vector) that captures the *meaning* of a sentence.
Sentences with similar meanings produce vectors that point in the same direction in that 384-dimensional space.

Example:
- "Write a blog post about coffee" → vector A
- "Create an article about trends"  → vector B
- "Check my website SEO"            → vector C

Vectors A and B will be close together (same direction).
Vector C will point in a completely different direction.

### How similarity is measured — Cosine Similarity

Cosine similarity measures the angle between two vectors:

```
similarity = (A · B) / (|A| × |B|)
```

- Result = 1.0 → identical meaning
- Result = 0.0 → completely unrelated
- Result between 0.4 and 0.8 → semantically related

When vectors are already L2-normalised (length = 1), this formula simplifies to just a dot product:

```
similarity = A · B   (dot product only, since |A| = |B| = 1)
```

That is the single line that replaces the entire LLM call.

### What happens at startup

```python
_st_model = SentenceTransformer("all-MiniLM-L6-v2")

INTENT_EXAMPLES = {
    "blog_generation":   "write a blog post create an article",
    "seo_analysis":      "analyse my website SEO audit",
    "social_post":       "create an instagram caption",
    "campaign_planning": "plan a multi-day marketing campaign",
    # ... 13 intents total
}

_intent_embeddings = {
    intent: _st_model.encode(example, normalize_embeddings=True)
    for intent, example in INTENT_EXAMPLES.items()
}
```

This runs **once when the server starts**. After that, the 13 intent vectors sit in memory.
No network call is ever made again for routing.

### What happens per request

```
User types: "Write a blog post about coffee trends"

Step 1 — Encode the user message into a vector (384 numbers)
          user_emb = model.encode("Write a blog post about coffee trends")

Step 2 — Dot-product with every intent vector
          blog_generation  score = 0.487  ← highest
          seo_analysis     score = 0.201
          social_post      score = 0.312
          campaign_planning score = 0.298
          ...

Step 3 — Pick the highest score
          intent = "blog_generation",  confidence = 0.487

Step 4 — Apply hard rule (optional override)
          If message contains question words ("what", "tell me", etc.)
          AND intent was brand_setup → override to general_chat
          (prevents "What is my brand name?" being treated as a brand setup request)

Step 5 — Return routing result (no token spent)
```

### The model used — all-MiniLM-L6-v2

- Size: ~22 MB
- Runs on CPU (no GPU needed)
- Produces 384-dimensional vectors
- Trained on 1 billion sentence pairs — it understands paraphrases, synonyms, intent
- Free, no API key, no rate limits

---

## Part 2 — Embedding + Readability Content Critic

The critic evaluates generated content on three axes and returns scores between 0.0 and 1.0.
**Zero LLM calls are made.** All three scores are computed mathematically.

---

### Axis 1 — Intent Score (Does the content fulfil what the user asked for?)

```
intent_score = cosine(encode(original_intent), encode(content)) × 1.5
```

**Why × 1.5?**
Raw cosine similarity between semantically related (but not identical) texts typically
falls between 0.4 and 0.7. Multiplying by 1.5 maps that range to 0.6–1.0, which is
more useful as a quality score. The result is then clipped to [0, 1].

**Example:**
- User intent: "write a blog post about vegan skincare"
- Generated content: 800-word article about vegan skincare routines
- encode("vegan skincare blog") · encode(article text) ≈ 0.55
- intent_score = min(1.0, 0.55 × 1.5) = 0.83  ← good alignment

If the content drifted off-topic (e.g. accidentally became a recipe article),
the cosine would drop to ~0.2 → intent_score = 0.30 → triggers suggestion.

---

### Axis 2 — Brand Score (Does the content match the brand voice?)

```
brand_score = cosine(encode(brand_profile_text), encode(content)) × 1.5
```

The brand profile is pulled from the database and contains:
- Brand name
- Tone (e.g. "playful and bold")
- Industry (e.g. "sustainable fashion")
- Target audience (e.g. "women aged 25–40")
- Tagline

All of this is encoded into a single vector. Content that uses similar language,
describes the same domain, and matches the described tone will produce a high cosine.

If no brand profile exists, the score defaults to 0.70 (neutral — cannot penalise
content when there is nothing to compare against).

---

### Axis 3 — Quality Score (Is the writing itself good?)

This axis uses two independent text-analysis techniques, weighted together:

#### a) Flesch-Kincaid Grade Level (45% weight)

```python
fk_grade = textstat.flesch_kincaid_grade(content)
```

The Flesch-Kincaid grade formula:

```
FK = 0.39 × (words/sentences) + 11.8 × (syllables/words) − 15.59
```

It returns a US school grade level. Grade 7 = easy reading, Grade 12 = complex.

For marketing copy, **grade 9 is considered optimal** (readable but not childish).
The readability component penalises content that is too complex (academic) or too simple:

```python
readability = max(0.0, 1.0 - abs(fk_grade - 9.0) / 14.0)
```

Examples:
- Grade 9  → readability = 1.00 (perfect)
- Grade 12 → readability = 0.79
- Grade 14 → readability = 0.64
- Grade 4  → readability = 0.64
- Grade 20 → readability = 0.21

#### b) Type-Token Ratio — TTR (35% weight)

```python
words = [w.lower() for w in content.split() if w.isalpha()]
ttr   = len(set(words)) / len(words)
```

TTR measures **vocabulary diversity**:
- A TTR of 0.60 means 60% of all words are unique
- Low TTR (< 0.40) indicates repetitive, boring writing ("great great great product is great")
- High TTR (> 0.60) indicates rich, varied vocabulary

#### c) Length Bonus (20% weight)

```python
length_ok = 1.0 if word_count >= 300 else (word_count / 300)
```

Content under 300 words is penalised proportionally. A 150-word piece scores 0.50 on this axis.

#### Combined quality formula

```python
quality_score = readability × 0.45 + ttr × 0.35 + length_ok × 0.20
```

---

### Final Overall Score

```python
overall_score = intent_score × 0.40 + brand_score × 0.35 + quality_score × 0.25
```

Weights rationale:
- Intent (40%) — most important: content must do what was asked
- Brand (35%) — second: must sound like the brand
- Quality (25%) — third: well-written but less important than purpose and brand fit

If overall_score >= 0.70 → **passed** (no human review needed)
If overall_score < 0.70  → **HITL event** created (human reviews before publishing)

---

### Automatic Suggestions

The critic also generates plain-English improvement suggestions based on which axis failed:

```
intent_score < 0.70 → "Revise the content to more directly address the original goal."
brand_score  < 0.70 → "Align tone and vocabulary more closely with the brand profile."
fk_grade     > 12   → "Flesch-Kincaid grade 13.2 is too complex for marketing copy."
ttr          < 0.40 → "Increase vocabulary variety (low type-token ratio)."
word_count   < 300  → "Content is short (187 words) — consider expanding to 300 words."
```

These suggestions are deterministic — the same content always produces the same suggestions.

---

## Why This is the Innovation

| Property | LLM Critic (old) | Embedding + Math Critic (new) |
|---|---|---|
| Cost | ~$0.002 per evaluation | $0.00 |
| Speed | ~1,000 ms | ~5 ms |
| Determinism | Non-deterministic (changes each call) | Fully deterministic |
| Explainability | "I think the quality is 0.7" — no reason | FK grade = 10.3, TTR = 0.45 — measurable |
| Dependency | Requires internet + API key | Runs offline on CPU |
| Bias | LLM may favour its own writing style | Pure mathematics — no bias |

The academic answer to the professor's question:

> "The innovation is that the evaluation pipeline is **decoupled from the generation pipeline**.
> LLMs are used only where they add value (creative generation). Evaluation uses the
> geometry of embedding space (cosine similarity measures semantic alignment) combined
> with computational linguistics (Flesch-Kincaid, TTR) — giving deterministic, explainable,
> zero-cost scoring. This is the same principle behind BERTScore, used in NLP research
> to evaluate text without a judge model."

---

## File Reference

| File | What changed |
|---|---|
| `intelligent_router.py` | `route_user_query()` replaced with embedding cosine classifier |
| `critic_agent.py` | `_evaluate()` replaced with cosine similarity + textstat math |
| Both files | `sentence-transformers`, `textstat`, `numpy` imports added |
