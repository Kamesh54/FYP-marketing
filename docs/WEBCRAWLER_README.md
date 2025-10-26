# 🕷️ WebCrawler Agent

## Overview

The WebCrawler Agent is responsible for extracting and processing content from websites. It handles HTML parsing, content cleaning, and generates structured output in multiple formats.

**Port:** 8000  
**File:** `webcrawler.py`  
**Framework:** FastAPI

---

## Features

- ✅ HTML content extraction
- ✅ Text cleaning and structuring
- ✅ Multiple output formats (JSON, DOCX)
- ✅ Metadata extraction (title, word count, etc.)
- ✅ Async job processing
- ✅ Result caching
- ✅ Error handling with retries

---

## API Endpoints

### 1. Health Check
```http
GET /
```

**Response:**
```json
{
  "message": "WebCrawler Agent is running",
  "version": "1.0",
  "port": 8000
}
```

---

### 2. Crawl Website
```http
POST /crawl
Content-Type: application/json

{
  "url": "https://example.com"
}
```

**Response:**
```json
{
  "job_id": "crawl_example.com_20241026_120000_abc123",
  "status": "started",
  "message": "Crawling started"
}
```

---

### 3. Check Job Status
```http
GET /status/{job_id}
```

**Response (Running):**
```json
{
  "status": "running",
  "job_id": "crawl_example.com_20241026_120000_abc123"
}
```

**Response (Completed):**
```json
{
  "status": "completed",
  "job_id": "crawl_example.com_20241026_120000_abc123",
  "url": "https://example.com"
}
```

**Response (Failed):**
```json
{
  "status": "failed",
  "job_id": "crawl_example.com_20241026_120000_abc123",
  "message": "Error: Connection timeout"
}
```

---

### 4. Download Crawl Result (JSON)
```http
GET /download/{job_id}
```

**Response:**
```json
{
  "url": "https://example.com",
  "title": "Example Domain",
  "extracted_text": "This domain is for use in illustrative examples...",
  "metadata": {
    "crawl_timestamp": "2024-10-26T12:00:00Z",
    "word_count": 150,
    "character_count": 850
  }
}
```

---

### 5. Download Crawl Result (DOCX)
```http
GET /download/docx/{job_id}
```

**Response:** Binary DOCX file

---

## Usage Examples

### Python (using requests)

```python
import requests
import time

BASE_URL = "http://127.0.0.1:8000"

# 1. Start crawl
response = requests.post(f"{BASE_URL}/crawl", json={
    "url": "https://example.com"
})
job_id = response.json()["job_id"]
print(f"Job started: {job_id}")

# 2. Poll status
while True:
    status_resp = requests.get(f"{BASE_URL}/status/{job_id}")
    status = status_resp.json()["status"]
    
    if status == "completed":
        break
    elif status == "failed":
        print("Crawl failed!")
        exit(1)
    
    print(f"Status: {status}")
    time.sleep(2)

# 3. Download result
result = requests.get(f"{BASE_URL}/download/{job_id}").json()
print(f"Title: {result['title']}")
print(f"Text: {result['extracted_text'][:200]}...")
```

### cURL

```bash
# 1. Start crawl
curl -X POST http://127.0.0.1:8000/crawl \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'

# 2. Check status
curl http://127.0.0.1:8000/status/crawl_example.com_20241026_120000_abc123

# 3. Download JSON
curl http://127.0.0.1:8000/download/crawl_example.com_20241026_120000_abc123

# 4. Download DOCX
curl http://127.0.0.1:8000/download/docx/crawl_example.com_20241026_120000_abc123 \
  -o result.docx
```

---

## Communication with Other Agents

### Called By:
- **Orchestrator** - When URL is provided for blog/social post generation
- **Gap Analyzer** - To crawl competitor websites

### Typical Flow:

```
┌──────────────┐
│ Orchestrator │
└──────┬───────┘
       │ User: "Analyze https://example.com"
       ▼
┌──────────────┐
│  WebCrawler  │
└──────┬───────┘
       │ Extract content
       ▼
┌──────────────┐
│    Return    │
│ {text, meta} │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Orchestrator │
└──────┬───────┘
       │ Pass to Keyword Extractor
       ▼
```

---

## Technical Details

### Content Extraction

**Libraries Used:**
- `requests` - HTTP requests
- `BeautifulSoup4` - HTML parsing
- `html2text` - HTML to plain text conversion
- `python-docx` - DOCX generation

**Extraction Process:**
1. Fetch HTML using requests
2. Parse with BeautifulSoup
3. Remove script, style, and navigation elements
4. Convert to clean text
5. Extract metadata (title, word count)
6. Store in memory

**Cleaning Rules:**
- Remove JavaScript and CSS
- Remove navigation and footer elements
- Remove excessive whitespace
- Normalize line breaks
- Remove special characters

---

### Job Management

**Job ID Format:**
```
crawl_{domain}_{timestamp}_{random_uuid}
Example: crawl_example.com_20241026_120000_abc123
```

**Job States:**
- `queued` - Job accepted, waiting to start
- `running` - Currently crawling
- `completed` - Successfully finished
- `failed` - Error occurred

**Storage:**
- Results stored in `tmp1/` directory
- JSON format for quick retrieval
- DOCX format for download
- Automatic cleanup after 24 hours

---

## Configuration

### Environment Variables

```bash
# WebCrawler settings
CRAWLER_TIMEOUT=30              # Request timeout in seconds
CRAWLER_MAX_RETRIES=3           # Max retry attempts
CRAWLER_USER_AGENT="..."        # Custom user agent
CRAWLER_MAX_PAGE_SIZE=5MB       # Max page size to crawl
```

### Timeouts

- **Request Timeout:** 30 seconds
- **Connection Timeout:** 10 seconds
- **Read Timeout:** 20 seconds

---

## Error Handling

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `Connection timeout` | Website too slow | Increase timeout |
| `Invalid URL` | Malformed URL | Validate URL format |
| `403 Forbidden` | Website blocks bots | Add user agent |
| `404 Not Found` | Page doesn't exist | Check URL |
| `SSL Error` | Certificate issue | Disable SSL verify |

### Retry Logic

```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(min=2, max=10)
)
def fetch_with_retry(url):
    return requests.get(url, timeout=30)
```

---

## Performance

### Benchmarks

| Metric | Value |
|--------|-------|
| Average crawl time | 2-5 seconds |
| Max concurrent jobs | 10 |
| Memory per job | ~50 MB |
| Disk per result | ~100 KB (JSON), ~50 KB (DOCX) |

### Optimization Tips

1. **Enable caching** for repeated URLs
2. **Use connection pooling** for multiple requests
3. **Limit page size** to avoid memory issues
4. **Clean up old jobs** regularly

---

## Monitoring & Logs

### Log Levels

```python
INFO  - Job started: crawl_example.com_...
INFO  - Fetching URL: https://example.com
INFO  - Content extracted: 1500 words
INFO  - Job completed: crawl_example.com_...
ERROR - Failed to crawl: Connection timeout
```

### Metrics to Monitor

- Total crawls per hour
- Success rate (%)
- Average response time
- Failed requests
- Queue length

---

## Testing

### Unit Tests

```python
# Test successful crawl
def test_successful_crawl():
    response = client.post("/crawl", json={"url": "https://example.com"})
    assert response.status_code == 200
    assert "job_id" in response.json()

# Test invalid URL
def test_invalid_url():
    response = client.post("/crawl", json={"url": "not-a-url"})
    assert response.status_code == 422
```

### Integration Tests

```python
# Test full workflow
def test_full_workflow():
    # Start crawl
    crawl_resp = client.post("/crawl", json={"url": "https://example.com"})
    job_id = crawl_resp.json()["job_id"]
    
    # Wait for completion
    time.sleep(5)
    
    # Check status
    status_resp = client.get(f"/status/{job_id}")
    assert status_resp.json()["status"] == "completed"
    
    # Download result
    result_resp = client.get(f"/download/{job_id}")
    assert "extracted_text" in result_resp.json()
```

---

## Troubleshooting

### WebCrawler Not Starting

**Check:**
```bash
# Port already in use?
netstat -ano | findstr :8000

# Kill process
taskkill /PID <pid> /F

# Restart
python webcrawler.py
```

### Jobs Stuck in "Running"

**Solution:**
```python
# Clear job status
jobs[job_id] = {"status": "failed", "message": "Timeout"}
```

### Out of Memory

**Solution:**
- Limit max page size
- Clean up old results
- Increase system memory

---

## Future Enhancements

- [ ] JavaScript rendering (Selenium/Playwright)
- [ ] PDF extraction support
- [ ] Image download and analysis
- [ ] Rate limiting per domain
- [ ] Distributed crawling
- [ ] Webhook notifications
- [ ] GraphQL API support

---

## Dependencies

```txt
fastapi==0.115.0
uvicorn==0.24.0
requests==2.31.0
beautifulsoup4==4.12.2
html2text==2020.1.16
python-docx==1.1.0
tenacity==8.2.3
```

---

**Agent Status:** ✅ Production Ready  
**Maintainer:** DevOps Team  
**Last Updated:** October 2024

