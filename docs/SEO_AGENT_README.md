# 🔍 SEO Agent

## Overview

The SEO Agent performs comprehensive website audits, analyzing technical SEO, on-page optimization, content quality, and provides actionable recommendations. It generates detailed HTML reports with scores and prioritized fixes.

**Port:** 5000  
**File:** `seo_agent.py`  
**Framework:** FastAPI

---

## Features

- ✅ Comprehensive SEO audits
- ✅ Technical SEO analysis
- ✅ On-page optimization checks
- ✅ Meta tag validation
- ✅ Header structure analysis
- ✅ Image optimization review
- ✅ Internal/external link analysis
- ✅ Mobile responsiveness check
- ✅ Page speed insights
- ✅ Beautiful HTML reports
- ✅ Prioritized recommendations

---

## API Endpoints

### 1. Health Check
```http
GET /
```

**Response:**
```json
{
  "message": "SEO Agent is running",
  "version": "1.0",
  "port": 5000
}
```

---

### 2. Analyze Website
```http
POST /analyze
Content-Type: application/json

{
  "url": "https://example.com"
}
```

**Response:**
```json
{
  "job_id": "seo_example.com_20241026_120000_abc123",
  "status": "started",
  "message": "SEO analysis started"
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
  "job_id": "seo_example.com_20241026_120000_abc123",
  "end_time": "2024-10-26T12:20:00Z"
}
```

---

### 4. Download Report (HTML)
```http
GET /download/report/{job_id}
```

**Response:** Full HTML SEO audit report

```html
<!DOCTYPE html>
<html>
<head>
    <title>SEO Audit Report - example.com</title>
    <style>/* Beautiful CSS */</style>
</head>
<body>
    <div class="report-header">
        <h1>SEO Audit Report</h1>
        <div class="score-card">
            <div class="score">85/100</div>
            <div class="grade">Good</div>
        </div>
    </div>
    
    <section class="summary">
        <h2>Executive Summary</h2>
        <div class="stats">
            <div class="stat">
                <span class="label">Total Issues:</span>
                <span class="value">12</span>
            </div>
            ...
        </div>
    </section>
    
    <section class="issues">
        <h2>Critical Issues (3)</h2>
        <div class="issue critical">
            <h3>Missing Meta Description</h3>
            <p>Impact: High | Effort: Low</p>
            <p>Fix: Add unique meta description...</p>
        </div>
        ...
    </section>
    ...
</body>
</html>
```

---

## Usage Examples

### Python

```python
import requests
import time

BASE_URL = "http://127.0.0.1:5000"

# 1. Start analysis
response = requests.post(f"{BASE_URL}/analyze", json={
    "url": "https://example.com"
})

job_id = response.json()["job_id"]
print(f"Analysis started: {job_id}")

# 2. Wait for completion
while True:
    status = requests.get(f"{BASE_URL}/status/{job_id}").json()
    if status["status"] == "completed":
        break
    print(f"Status: {status['status']}")
    time.sleep(3)

# 3. Download report
report_html = requests.get(f"{BASE_URL}/download/report/{job_id}").text

# Save report
with open("seo_report.html", "w", encoding="utf-8") as f:
    f.write(report_html)

print("Report saved to seo_report.html")
```

### cURL

```bash
# Start analysis
curl -X POST http://127.0.0.1:5000/analyze \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'

# Check status
curl http://127.0.0.1:5000/status/seo_example.com_20241026_120000_abc123

# Download report
curl http://127.0.0.1:5000/download/report/seo_example.com_20241026_120000_abc123 \
  -o seo_report.html
```

---

## Communication with Other Agents

### Called By:
- **Orchestrator** - When user requests SEO analysis

### Calls:
- **WebCrawler** (indirectly) - Fetches website HTML

### Typical Flow:

```
┌──────────────┐
│ Orchestrator │ User: "Analyze my website's SEO"
└──────┬───────┘
       │
       ▼
┌────────────────┐
│   SEO Agent    │ Fetch HTML + Parse + Analyze
└──────┬─────────┘
       │
       ▼
┌────────────────┐
│  Generate      │ Create HTML report with scores
│  Report        │
└──────┬─────────┘
       │
       ▼
┌──────────────┐
│ Orchestrator │ Display report link
└──────────────┘
```

---

## SEO Analysis Components

### 1. Technical SEO

**Checks:**
- ✅ Page title presence and length (50-60 chars)
- ✅ Meta description presence and length (150-160 chars)
- ✅ Canonical URL
- ✅ Robots meta tag
- ✅ XML sitemap reference
- ✅ Favicon presence
- ✅ HTTPS protocol
- ✅ Page load speed
- ✅ Mobile responsiveness
- ✅ Structured data (Schema.org)

**Scoring:**
```python
score = 0
if has_title and 50 <= len(title) <= 60:
    score += 10
if has_meta_description and 150 <= len(description) <= 160:
    score += 10
if is_https:
    score += 10
...
total_score = (score / max_score) * 100
```

---

### 2. On-Page SEO

**Checks:**
- ✅ H1 tag presence (only one)
- ✅ Heading hierarchy (H1 → H2 → H3)
- ✅ Keyword density
- ✅ Content length (>300 words)
- ✅ Internal links (5-10 recommended)
- ✅ External links (authority sites)
- ✅ Image alt tags
- ✅ URL structure
- ✅ Breadcrumbs

---

### 3. Content Quality

**Checks:**
- ✅ Word count (minimum 300)
- ✅ Readability score (Flesch-Kincaid)
- ✅ Duplicate content detection
- ✅ Content freshness
- ✅ Multimedia presence (images, videos)
- ✅ Call-to-action presence

---

### 4. Image Optimization

**Checks:**
- ✅ Alt text presence (all images)
- ✅ File size (<200 KB recommended)
- ✅ Dimensions appropriate
- ✅ Format (WebP, JPEG, PNG)
- ✅ Lazy loading
- ✅ Responsive images

---

### 5. Link Analysis

**Internal Links:**
- Count and quality
- Anchor text variation
- Deep linking
- Broken links

**External Links:**
- Authority (DA/PA)
- Relevance
- Nofollow vs dofollow
- Broken links

---

## Scoring System

### Overall Score Calculation

```python
weights = {
    "technical": 0.30,    # 30%
    "on_page": 0.25,      # 25%
    "content": 0.20,      # 20%
    "images": 0.15,       # 15%
    "links": 0.10         # 10%
}

overall_score = (
    technical_score * 0.30 +
    on_page_score * 0.25 +
    content_score * 0.20 +
    image_score * 0.15 +
    link_score * 0.10
)
```

### Score Grades

| Score | Grade | Status |
|-------|-------|--------|
| 90-100 | Excellent | ✅ Outstanding |
| 80-89 | Good | ✅ Well optimized |
| 70-79 | Fair | ⚠️ Needs improvement |
| 60-69 | Poor | ⚠️ Major issues |
| < 60 | Critical | ❌ Urgent fixes needed |

---

## Issue Prioritization

### Priority Levels

**Critical (Fix Immediately):**
- Missing page title
- Missing meta description
- No H1 tag
- Non-HTTPS
- Broken links

**High (Fix Soon):**
- Duplicate H1 tags
- Poor heading hierarchy
- Missing alt tags
- Slow page speed
- No mobile optimization

**Medium (Fix When Possible):**
- Long meta description
- Low keyword density
- Insufficient internal links
- Large image sizes

**Low (Nice to Have):**
- Missing favicon
- No structured data
- No breadcrumbs
- No canonical URL

---

## Report Format

### HTML Report Structure

```html
<!DOCTYPE html>
<html>
<head>
    <title>SEO Audit - {domain}</title>
    <style>
        /* Modern, professional CSS */
        .report-header { ... }
        .score-card { ... }
        .issue.critical { background: #fee; }
        .issue.high { background: #ffc; }
        ...
    </style>
</head>
<body>
    <!-- Header with score -->
    <div class="report-header">
        <h1>SEO Audit Report</h1>
        <div class="score-card">
            <div class="score">85/100</div>
            <div class="grade">Good</div>
        </div>
        <div class="meta">
            <span>URL: example.com</span>
            <span>Date: 2024-10-26</span>
        </div>
    </div>
    
    <!-- Summary statistics -->
    <section class="summary">
        <h2>Executive Summary</h2>
        <div class="stats-grid">
            <div class="stat">
                <div class="value">85</div>
                <div class="label">Overall Score</div>
            </div>
            <div class="stat">
                <div class="value">12</div>
                <div class="label">Total Issues</div>
            </div>
            <div class="stat critical">
                <div class="value">3</div>
                <div class="label">Critical</div>
            </div>
            <div class="stat high">
                <div class="value">5</div>
                <div class="label">High Priority</div>
            </div>
        </div>
    </section>
    
    <!-- Detailed issues by priority -->
    <section class="issues">
        <h2>Critical Issues (3)</h2>
        
        <div class="issue critical">
            <div class="issue-header">
                <h3>Missing Meta Description</h3>
                <span class="badge">Critical</span>
            </div>
            <div class="issue-body">
                <p><strong>Impact:</strong> High - Affects search result click-through rate</p>
                <p><strong>Effort:</strong> Low - 5 minutes to fix</p>
                <p><strong>How to Fix:</strong></p>
                <pre>Add this in your <head> tag:
&lt;meta name="description" content="Your unique 150-160 char description"&gt;</pre>
            </div>
        </div>
        
        <div class="issue critical">
            <div class="issue-header">
                <h3>Multiple H1 Tags Found</h3>
                <span class="badge">Critical</span>
            </div>
            <div class="issue-body">
                <p><strong>Found:</strong> 3 H1 tags</p>
                <p><strong>Recommendation:</strong> Use only ONE H1 per page</p>
                <p><strong>How to Fix:</strong> Convert additional H1 tags to H2 or H3</p>
            </div>
        </div>
        ...
    </section>
    
    <!-- Category breakdowns -->
    <section class="breakdown">
        <h2>Technical SEO (Score: 80/100)</h2>
        <ul class="checklist">
            <li class="pass">✅ Page title present (58 characters)</li>
            <li class="fail">❌ Meta description missing</li>
            <li class="pass">✅ HTTPS enabled</li>
            <li class="warn">⚠️  Page load time: 3.2s (should be < 2s)</li>
            ...
        </ul>
    </section>
    
    ...
    
    <!-- Action plan -->
    <section class="action-plan">
        <h2>30-Day Action Plan</h2>
        <div class="timeline">
            <div class="phase">
                <h3>Week 1: Critical Fixes</h3>
                <ul>
                    <li>Add meta description</li>
                    <li>Fix multiple H1 tags</li>
                    <li>Add missing alt tags</li>
                </ul>
            </div>
            <div class="phase">
                <h3>Week 2-3: High Priority</h3>
                <ul>
                    <li>Optimize images</li>
                    <li>Improve page speed</li>
                    <li>Fix broken links</li>
                </ul>
            </div>
            <div class="phase">
                <h3>Week 4: Medium Priority</h3>
                <ul>
                    <li>Add structured data</li>
                    <li>Improve internal linking</li>
                    <li>Add breadcrumbs</li>
                </ul>
            </div>
        </div>
    </section>
</body>
</html>
```

---

## Configuration

### Environment Variables

```bash
# Optional
SEO_AGENT_TIMEOUT=60           # Analysis timeout
SEO_AGENT_MAX_IMAGES=50        # Max images to analyze
SEO_AGENT_MAX_LINKS=100        # Max links to check
```

---

## Performance

### Benchmarks

| Metric | Value |
|--------|-------|
| Average analysis time | 15-30 seconds |
| Memory usage | ~100 MB |
| Max page size analyzed | 5 MB |
| Report generation time | 2-3 seconds |

---

## Error Handling

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `Cannot fetch URL` | Invalid/unreachable URL | Check URL validity |
| `Timeout` | Slow website | Increase timeout |
| `Parse error` | Malformed HTML | Check website HTML |
| `Too large` | Page > 5MB | Skip large files |

---

## Testing

```python
def test_seo_analysis():
    response = client.post("/analyze", json={
        "url": "https://example.com"
    })
    assert response.status_code == 200
    job_id = response.json()["job_id"]
    
    # Wait and download
    time.sleep(30)
    report = client.get(f"/download/report/{job_id}").text
    assert "SEO Audit Report" in report
```

---

## Future Enhancements

- [ ] Competitive analysis (compare with competitors)
- [ ] Historical tracking (monitor changes over time)
- [ ] Automated alerts (when score drops)
- [ ] PDF report export
- [ ] Email report delivery
- [ ] Batch analysis (multiple URLs)
- [ ] API for programmatic access
- [ ] Integration with Google Search Console

---

## Dependencies

```txt
fastapi==0.115.0
uvicorn==0.24.0
requests==2.31.0
beautifulsoup4==4.12.2
tenacity==8.2.3
```

---

**Agent Status:** ✅ Production Ready  
**Maintainer:** SEO Team  
**Last Updated:** October 2024

