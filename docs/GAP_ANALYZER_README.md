# 📊 Competitor Gap Analyzer Agent

## Overview

The Competitor Gap Analyzer identifies competitors, analyzes their content strategy, and uncovers content gaps and opportunities. It uses AI and web scraping to provide actionable competitive intelligence.

**Port:** 8002  
**File:** `CompetitorGapAnalyzerAgent.py`  
**Framework:** FastAPI  
**Dependencies:** Groq LLM, SerpAPI, WebCrawler

---

## Features

- ✅ Automatic competitor discovery
- ✅ Keyword gap analysis
- ✅ Content opportunity identification
- ✅ Multi-competitor comparison
- ✅ Actionable recommendations
- ✅ Detailed JSON reports

---

## API Endpoints

### 1. Health Check
```http
GET /
```

**Response:**
```json
{
  "message": "CompetitorGapAnalyzer Agent is running",
  "version": "1.0",
  "port": 8002
}
```

---

### 2. Analyze Keyword Gap
```http
POST /analyze-keyword-gap
Content-Type: application/json

{
  "company_name": "Cloud24",
  "product_description": "Cloud kitchen in Chennai specializing in healthy meal prep",
  "company_url": "https://cloud24.com",
  "max_competitors": 3,
  "max_pages_per_site": 2
}
```

**Response:**
```json
{
  "job_id": "4af48706-...",
  "status": "started",
  "message": "Analysis started"
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
  "job_id": "4af48706-...",
  "end_time": "2024-10-26T12:10:00Z"
}
```

---

### 4. Download Analysis (JSON)
```http
GET /download/json/{job_id}
```

**Response:**
```json
{
  "company_name": "Cloud24",
  "product_description": "Cloud kitchen...",
  "identified_domain": "cloud kitchen food delivery",
  
  "competitors": [
    {
      "name": "FreshMenu",
      "url": "https://freshmenu.com",
      "description": "Cloud kitchen platform..."
    },
    {
      "name": "Box8",
      "url": "https://box8.in",
      "description": "Indian cuisine cloud kitchen..."
    }
  ],
  
  "keyword_comparison": {
    "your_keywords": [
      "healthy meal prep",
      "chennai cloud kitchen",
      "fitness meals"
    ],
    "competitor_keywords": [
      "quick delivery",
      "pan-india service",
      "bulk orders",
      "corporate catering"
    ],
    "common_keywords": [
      "cloud kitchen",
      "home delivery",
      "fresh ingredients"
    ]
  },
  
  "content_gaps": [
    {
      "keyword": "bulk meal orders",
      "opportunity": "high",
      "why": "3 competitors mention it, you don't",
      "suggestion": "Create content about corporate catering packages"
    },
    {
      "keyword": "subscription plans",
      "opportunity": "medium",
      "why": "Popular in competitor content",
      "suggestion": "Add blog about weekly meal subscriptions"
    }
  ],
  
  "content_opportunities": [
    "Blog: '5 Benefits of Meal Prep Subscriptions'",
    "Landing Page: 'Corporate Catering Services'",
    "Social Post: 'Weekly Meal Plans for Busy Professionals'"
  ],
  
  "content_gaps_summary": "Focus on bulk orders, subscriptions, and corporate catering to compete effectively.",
  
  "analysis_timestamp": "2024-10-26T12:10:00Z"
}
```

---

## Usage Examples

### Python

```python
import requests
import time

BASE_URL = "http://127.0.0.1:8002"

# 1. Start analysis
response = requests.post(f"{BASE_URL}/analyze-keyword-gap", json={
    "company_name": "Cloud24",
    "product_description": "Cloud kitchen in Chennai",
    "company_url": "https://cloud24.com",
    "max_competitors": 3,
    "max_pages_per_site": 2
})

job_id = response.json()["job_id"]
print(f"Analysis started: {job_id}")

# 2. Wait for completion
while True:
    status = requests.get(f"{BASE_URL}/status/{job_id}").json()
    if status["status"] == "completed":
        break
    print(f"Status: {status['status']}")
    time.sleep(5)  # Gap analysis takes longer

# 3. Get results
result = requests.get(f"{BASE_URL}/download/json/{job_id}").json()

print(f"\\nCompetitors Found: {len(result['competitors'])}")
for comp in result['competitors']:
    print(f"  - {comp['name']}: {comp['url']}")

print(f"\\nContent Gaps: {len(result['content_gaps'])}")
for gap in result['content_gaps'][:3]:
    print(f"  - {gap['keyword']}: {gap['suggestion']}")
```

---

## Communication with Other Agents

### Called By:
- **Orchestrator** - During blog/social post generation

### Calls:
- **Groq API** - Domain extraction
- **SerpAPI** - Competitor discovery
- **WebCrawler** - Scrape competitor content

### Complete Flow:

```
┌──────────────┐
│ Orchestrator │
└──────┬───────┘
       │ Analyze gaps for "Cloud24"
       ▼
┌────────────────┐
│ Gap Analyzer   │
└──────┬─────────┘
       │ 1. Extract domain using Groq
       ▼
┌──────────────┐
│   Groq API   │ "cloud kitchen" → domain
└──────┬───────┘
       │
       ▼
┌────────────────┐
│ Gap Analyzer   │
└──────┬─────────┘
       │ 2. Search competitors
       ▼
┌──────────────┐
│   SerpAPI    │ Returns top 5 sites
└──────┬───────┘
       │
       ▼
┌────────────────┐
│ Gap Analyzer   │
└──────┬─────────┘
       │ 3. Crawl each competitor
       ▼
┌──────────────┐
│ WebCrawler   │ Extract content
└──────┬───────┘
       │
       ▼
┌────────────────┐
│ Gap Analyzer   │
└──────┬─────────┘
       │ 4. Compare keywords & identify gaps
       ▼
┌──────────────┐
│ Orchestrator │
└──────────────┘
```

---

## Analysis Algorithm

### Step 1: Domain Extraction

```python
# Use Groq to identify business domain
prompt = f"""
Extract the primary business domain from:
"{product_description}"

Return a single domain keyword suitable for Google search.
Example: "cloud kitchen" or "e-commerce fashion"
"""

domain = groq_client.extract(prompt)
```

### Step 2: Competitor Discovery

```python
# Search Google via SerpAPI
search_query = f"{domain} software site"
results = serpapi.search(search_query, num=10)

# Filter and rank competitors
competitors = []
for result in results:
    if is_valid_competitor(result):
        competitors.append({
            "name": extract_name(result),
            "url": result["link"],
            "description": result["snippet"]
        })

# Return top N
return competitors[:max_competitors]
```

### Step 3: Content Crawling

```python
# Crawl each competitor
for competitor in competitors:
    try:
        # Call WebCrawler agent
        content = webcrawler.crawl(competitor["url"])
        competitor["content"] = content
    except Exception:
        # Continue with other competitors
        pass
```

### Step 4: Keyword Extraction

```python
# Extract keywords from each competitor
all_competitor_keywords = []
for competitor in competitors:
    keywords = extract_keywords_from_text(competitor["content"])
    competitor["keywords"] = keywords
    all_competitor_keywords.extend(keywords)

# Get your keywords (from input or website)
your_keywords = extract_keywords_from_text(company_content)
```

### Step 5: Gap Analysis

```python
# Find gaps
competitor_only = set(all_competitor_keywords) - set(your_keywords)
your_only = set(your_keywords) - set(competitor_keywords)
common = set(your_keywords) & set(competitor_keywords)

# Rank gaps by opportunity
content_gaps = []
for keyword in competitor_only:
    frequency = count_mentions(keyword, competitors)
    if frequency >= 2:  # Mentioned by 2+ competitors
        content_gaps.append({
            "keyword": keyword,
            "opportunity": calculate_opportunity(frequency),
            "suggestion": generate_suggestion(keyword)
        })

return sorted(content_gaps, key=lambda x: x["opportunity"], reverse=True)
```

---

## Configuration

### Environment Variables

```bash
# Required
GROQ_API_KEY=gsk_xxxxx
SERPAPI_KEY=xxxxx

# Optional
GAP_ANALYZER_MAX_COMPETITORS=5
GAP_ANALYZER_MAX_PAGES=3
GAP_ANALYZER_TIMEOUT=120
```

### Timeouts

- **Total analysis:** 60-120 seconds
- **Groq call:** 10 seconds
- **SerpAPI call:** 5 seconds
- **Per-site crawl:** 30 seconds

---

## Performance

### Benchmarks

| Metric | Value |
|--------|-------|
| Average analysis time | 30-60 seconds |
| Max competitors analyzed | 5 |
| Pages per competitor | 1-3 |
| Accuracy rate | ~85% |
| Memory usage | ~200 MB |

### Cost Per Analysis

- Groq API: ~$0.0002
- SerpAPI: ~$0.005
- WebCrawler: Free (internal)
- **Total:** ~$0.0052 per analysis

---

## Error Handling

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `No competitors found` | Niche domain | Broaden search query |
| `SerpAPI quota exceeded` | Rate limit | Upgrade plan |
| `Crawl failed` | Blocked by site | Add delays, rotate IPs |
| `Invalid domain` | Vague description | Request clearer input |

### Retry Strategy

```python
# Competitor crawling with fallback
for competitor in competitors:
    try:
        content = crawl_with_retry(competitor["url"])
    except CrawlError:
        logger.warning(f"Skipping {competitor['name']}")
        continue  # Analyze others
```

---

## Output Interpretation

### Opportunity Levels

| Level | Frequency | Action |
|-------|-----------|--------|
| **High** | 3+ competitors | **Create content ASAP** |
| **Medium** | 2 competitors | Consider for next quarter |
| **Low** | 1 competitor | Monitor for trends |

### Content Gap Types

1. **Keyword Gaps** - Topics competitors cover, you don't
2. **Feature Gaps** - Services/products they highlight
3. **Audience Gaps** - Customer segments they target
4. **Content Format Gaps** - Blogs, videos, guides they have

---

## Integration Examples

### With Orchestrator (Blog Generation)

```python
# 1. Get keywords
keywords = keyword_extractor.extract(business_context)

# 2. Analyze gaps
gap_analysis = gap_analyzer.analyze(
    company_name="Cloud24",
    description=business_context,
    url=company_url
)

# 3. Generate blog with gaps in mind
blog = content_agent.generate_blog(
    keywords=keywords,
    gap_insights=gap_analysis["content_gaps"],
    opportunities=gap_analysis["content_opportunities"]
)
```

---

## Testing

### Unit Tests

```python
def test_domain_extraction():
    domain = extract_domain_with_groq("Cloud kitchen in Chennai")
    assert "cloud kitchen" in domain.lower()

def test_competitor_search():
    competitors = search_competitors("cloud kitchen", max_results=3)
    assert len(competitors) <= 3
    assert all("url" in c for c in competitors)
```

### Integration Tests

```python
def test_full_analysis():
    response = client.post("/analyze-keyword-gap", json={
        "company_name": "TestCo",
        "product_description": "Cloud kitchen",
        "max_competitors": 2
    })
    
    job_id = response.json()["job_id"]
    time.sleep(60)  # Wait for completion
    
    result = client.get(f"/download/json/{job_id}").json()
    
    assert "competitors" in result
    assert "content_gaps" in result
    assert len(result["competitors"]) <= 2
```

---

## Monitoring & Logs

### Log Examples

```
INFO - Starting gap analysis: TestCo
INFO - Extracted domain: cloud kitchen
INFO - Found 5 competitors via SerpAPI
INFO - Crawling competitor 1/5: FreshMenu
INFO - Crawling competitor 2/5: Box8
INFO - Keyword comparison complete: 15 gaps found
INFO - Analysis complete: 4af48706-...
```

### Metrics to Track

- Analyses per day
- Average analysis time
- Competitor discovery rate
- Crawl success rate
- Gap identification accuracy

---

## Troubleshooting

### No Competitors Found

**Solutions:**
1. Check SerpAPI key validity
2. Broaden search terms
3. Remove filters
4. Check SerpAPI logs

### Analysis Too Slow

**Solutions:**
1. Reduce `max_competitors`
2. Reduce `max_pages_per_site`
3. Parallelize crawling
4. Use caching

### Low-Quality Gaps

**Solutions:**
1. Improve domain extraction prompt
2. Increase competitor count
3. Add manual competitor URLs
4. Filter out generic keywords

---

## Future Enhancements

- [ ] Social media competitor analysis
- [ ] Backlink gap analysis
- [ ] Content freshness comparison
- [ ] SERP feature analysis
- [ ] Automated competitive monitoring
- [ ] Historical gap tracking
- [ ] Visual gap reports (charts)

---

## Dependencies

```txt
fastapi==0.115.0
uvicorn==0.24.0
groq==0.9.0
requests==2.31.0
google-search-results==2.4.2  # SerpAPI
tenacity==8.2.3
```

---

**Agent Status:** ✅ Production Ready  
**Maintainer:** SEO Team  
**Last Updated:** October 2024

