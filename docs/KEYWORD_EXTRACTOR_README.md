# 🔑 Keyword Extractor Agent

## Overview

The Keyword Extractor Agent uses AI (Groq LLM) to analyze business context and extract relevant SEO keywords, target domains, and industry insights. It's a critical component in the content generation pipeline.

**Port:** 8001  
**File:** `keywordExtraction.py`  
**Framework:** FastAPI  
**AI Model:** Llama 3.3 70B (via Groq)

---

## Features

- ✅ AI-powered keyword extraction
- ✅ Domain/industry identification
- ✅ Confidence scoring
- ✅ Context-aware analysis
- ✅ Handles multiple languages
- ✅ Async job processing
- ✅ Result caching

---

## API Endpoints

### 1. Health Check
```http
GET /
```

**Response:**
```json
{
  "message": "Keyword Extraction Agent is running",
  "version": "1.0",
  "port": 8001
}
```

---

### 2. Extract Keywords
```http
POST /extract-keywords
Content-Type: application/json

{
  "customer_statement": "I run a cloud kitchen called Cloud24 in Chennai. We specialize in healthy meal prep and delivery.",
  "max_results": 10
}
```

**Response:**
```json
{
  "job_id": "21f2931d-609b-4fe9-9676-8179f4659d22",
  "status": "started",
  "message": "Keyword extraction started"
}
```

---

### 3. Check Job Status
```http
GET /status/{job_id}
```

**Response:**
```json
{
  "status": "completed",
  "job_id": "21f2931d-609b-4fe9-9676-8179f4659d22",
  "end_time": "2024-10-26T12:05:30Z"
}
```

---

### 4. Download Results
```http
GET /download/{job_id}
```

**Response:**
```json
{
  "keywords": [
    "cloud kitchen",
    "healthy meal prep",
    "food delivery chennai",
    "meal planning",
    "nutritious meals",
    "chef-prepared meals",
    "diet food",
    "fitness meals",
    "home delivery",
    "fresh ingredients"
  ],
  "domains": [
    "food service",
    "health and wellness",
    "restaurant technology",
    "meal delivery"
  ],
  "confidence_scores": {
    "cloud kitchen": 0.95,
    "healthy meal prep": 0.92,
    "food delivery chennai": 0.88,
    ...
  },
  "extracted_at": "2024-10-26T12:05:30Z"
}
```

---

## Usage Examples

### Python

```python
import requests
import time

BASE_URL = "http://127.0.0.1:8001"

# Business context
context = """
I run a cloud kitchen called Cloud24 in Chennai.
We specialize in healthy meal prep and delivery.
Our target customers are fitness enthusiasts and busy professionals.
"""

# 1. Start extraction
response = requests.post(f"{BASE_URL}/extract-keywords", json={
    "customer_statement": context,
    "max_results": 10
})
job_id = response.json()["job_id"]

# 2. Wait for completion
while True:
    status = requests.get(f"{BASE_URL}/status/{job_id}").json()
    if status["status"] == "completed":
        break
    time.sleep(2)

# 3. Get results
result = requests.get(f"{BASE_URL}/download/{job_id}").json()
print("Keywords:", result["keywords"])
print("Domains:", result["domains"])
```

### cURL

```bash
# Extract keywords
curl -X POST http://127.0.0.1:8001/extract-keywords \
  -H "Content-Type: application/json" \
  -d '{
    "customer_statement": "Cloud kitchen in Chennai",
    "max_results": 10
  }'

# Check status
curl http://127.0.0.1:8001/status/21f2931d-609b-4fe9-9676-8179f4659d22

# Get results
curl http://127.0.0.1:8001/download/21f2931d-609b-4fe9-9676-8179f4659d22
```

---

## Communication with Other Agents

### Called By:
- **Orchestrator** - For blog and social post generation
- **Gap Analyzer** - To understand business domain

### Calls:
- **Groq API** - LLM for keyword extraction

### Typical Flow:

```
┌──────────────┐
│ Orchestrator │
└──────┬───────┘
       │ Extract keywords from: "Cloud kitchen in Chennai..."
       ▼
┌────────────────┐
│ Keyword Extractor│
└──────┬─────────┘
       │ Call Groq LLM
       ▼
┌──────────────┐
│   Groq API   │
└──────┬───────┘
       │ Return: keywords + domains
       ▼
┌────────────────┐
│ Keyword Extractor│
└──────┬─────────┘
       │ Parse & structure
       ▼
┌──────────────┐
│ Orchestrator │
└──────┬───────┘
       │ Pass to Content Agent
       ▼
```

---

## Technical Details

### AI Prompt Engineering

**System Prompt:**
```python
system_prompt = """You are an expert SEO and keyword research specialist.
Given a business description, extract:
1. Primary keywords (high search intent)
2. Long-tail keywords (specific phrases)
3. Industry domains
4. Target audience keywords

Return JSON with:
{
  "keywords": ["keyword1", "keyword2", ...],
  "domains": ["domain1", "domain2", ...],
  "confidence_scores": {"keyword1": 0.95, ...}
}
"""
```

**User Prompt Template:**
```python
user_prompt = f"""
Business Context:
{customer_statement}

Extract up to {max_results} most relevant SEO keywords.
Focus on:
- Business type and industry
- Location (if mentioned)
- Products/services
- Target audience
- Unique value proposition

Return ONLY valid JSON.
"""
```

### Keyword Selection Algorithm

1. **Extract entities** using LLM
2. **Rank by relevance** (0-1 score)
3. **Filter duplicates** (case-insensitive)
4. **Sort by confidence** (highest first)
5. **Return top N** keywords

---

## Input Guidelines

### Effective Customer Statements

**Good Examples:**
```
✅ "Cloud kitchen in Chennai specializing in healthy meal prep 
    for fitness enthusiasts. We deliver fresh, chef-prepared 
    meals with macro tracking."

✅ "E-commerce platform for sustainable fashion. We sell 
    eco-friendly clothing made from recycled materials. 
    Target audience: environmentally conscious millennials."

✅ "Digital marketing agency focused on small businesses. 
    Services: SEO, content marketing, social media management. 
    Located in Bangalore."
```

**Poor Examples:**
```
❌ "Business" (too vague)
❌ "Website" (no context)
❌ "Help" (not descriptive)
```

### Required Information

For best results, include:
- **Business type** (restaurant, agency, shop, etc.)
- **Location** (city, region, or "online")
- **Products/Services** (what you sell/offer)
- **Target audience** (who are your customers)
- **Unique features** (what makes you different)

---

## Output Format

### Keywords Object

```json
{
  "keywords": [
    "primary keyword",      // Most relevant
    "secondary keyword",    // Supporting
    "long-tail keyword",    // Specific phrases
    ...
  ],
  "domains": [
    "industry1",            // Primary industry
    "industry2"             // Related industries
  ],
  "confidence_scores": {
    "primary keyword": 0.95, // Very confident
    "secondary keyword": 0.82, // Confident
    "long-tail keyword": 0.68 // Moderate confidence
  }
}
```

### Confidence Score Interpretation

| Score | Meaning | Use Case |
|-------|---------|----------|
| 0.9-1.0 | Very High | Core business keywords |
| 0.7-0.9 | High | Primary marketing keywords |
| 0.5-0.7 | Medium | Supporting keywords |
| < 0.5 | Low | Consider excluding |

---

## Performance

### Benchmarks

| Metric | Value |
|--------|-------|
| Average extraction time | 3-5 seconds |
| Groq API latency | 1-2 seconds |
| Max concurrent jobs | 20 |
| Tokens per request | ~500 input, ~300 output |
| Cost per request | ~$0.0001 (Groq) |

### Rate Limits

- **Groq Free Tier:** 30 requests/minute
- **Recommended:** Add rate limiting
- **Fallback:** Queue system for high load

---

## Configuration

### Environment Variables

```bash
# Required
GROQ_API_KEY=gsk_xxxxx

# Optional
KEYWORD_EXTRACTOR_MAX_RESULTS=15
KEYWORD_EXTRACTOR_TEMPERATURE=0.3  # Lower = more consistent
KEYWORD_EXTRACTOR_TIMEOUT=30       # Seconds
```

### Groq Model Settings

```python
groq_client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=[...],
    response_format={"type": "json_object"},
    temperature=0.3,  # Consistency over creativity
    max_tokens=1000
)
```

---

## Error Handling

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `Groq API timeout` | Slow response | Increase timeout |
| `JSON parse error` | Invalid LLM output | Retry with stricter prompt |
| `Empty keywords` | Vague input | Request more context |
| `Rate limit` | Too many requests | Implement queue |

### Retry Strategy

```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(min=2, max=10),
    retry=retry_if_exception_type(GroqAPIError)
)
def call_groq_with_retry(prompt):
    return groq_client.chat.completions.create(...)
```

---

## Caching Strategy

### Cache Key Format

```python
cache_key = f"keywords:{hash(customer_statement)}:{max_results}"
```

### Cache Behavior

- **TTL:** 24 hours
- **Storage:** In-memory (dict)
- **Invalidation:** Manual or TTL expiry
- **Size limit:** 1000 entries

### Implementation

```python
cache = {}

def get_keywords(statement, max_results):
    key = generate_cache_key(statement, max_results)
    
    if key in cache:
        logger.info("Cache hit!")
        return cache[key]
    
    # Call Groq
    result = extract_with_groq(statement, max_results)
    
    # Store in cache
    cache[key] = result
    return result
```

---

## Monitoring & Logs

### Log Examples

```
INFO - Starting keyword extraction for job: 21f2931d-...
INFO - Calling Groq API...
INFO - Groq response received: 15 keywords extracted
INFO - Job completed: 21f2931d-...
ERROR - Groq API error: Rate limit exceeded
```

### Metrics to Track

- Total extractions per day
- Average extraction time
- Groq API success rate
- Cache hit rate (%)
- Token usage

---

## Integration Examples

### With Content Agent

```python
# 1. Extract keywords
keywords_data = call_keyword_extractor(business_context)

# 2. Pass to Content Agent
blog = call_content_agent(
    keywords=keywords_data["keywords"],
    domains=keywords_data["domains"],
    topic="healthy eating"
)
```

### With Gap Analyzer

```python
# 1. Extract domain
keywords_data = call_keyword_extractor(business_context)
primary_domain = keywords_data["domains"][0]

# 2. Find competitors in that domain
competitors = call_gap_analyzer(
    company_name="Cloud24",
    domain=primary_domain
)
```

---

## Testing

### Unit Tests

```python
def test_keyword_extraction():
    response = client.post("/extract-keywords", json={
        "customer_statement": "Cloud kitchen in Chennai",
        "max_results": 5
    })
    assert response.status_code == 200
    job_id = response.json()["job_id"]
    assert job_id is not None
```

### Integration Tests

```python
def test_full_workflow():
    # Start job
    response = client.post("/extract-keywords", json={
        "customer_statement": "E-commerce fashion store",
        "max_results": 10
    })
    job_id = response.json()["job_id"]
    
    # Wait and download
    time.sleep(5)
    result = client.get(f"/download/{job_id}").json()
    
    # Validate
    assert "keywords" in result
    assert len(result["keywords"]) > 0
    assert "domains" in result
```

---

## Troubleshooting

### No Keywords Extracted

**Check:**
1. Input too vague? Add more context
2. Groq API key valid?
3. Check logs for errors

### Low-Quality Keywords

**Solutions:**
1. Lower temperature (more conservative)
2. Add industry hints to prompt
3. Increase max_results for more options

### Slow Response

**Solutions:**
1. Implement caching
2. Use faster Groq model
3. Reduce max_results

---

## Future Enhancements

- [ ] Multi-language support (currently English-focused)
- [ ] Keyword difficulty scoring
- [ ] Search volume estimates (integrate Google Keyword Planner)
- [ ] Related keywords suggestions
- [ ] Negative keyword identification
- [ ] Seasonal keyword trends
- [ ] Competitor keyword analysis

---

## Dependencies

```txt
fastapi==0.115.0
uvicorn==0.24.0
groq==0.9.0
tenacity==8.2.3
python-dotenv==1.0.0
```

---

**Agent Status:** ✅ Production Ready  
**Maintainer:** AI Team  
**Last Updated:** October 2024

