# 📚 Documentation Index

Welcome to the Multi-Agent Content Marketing Platform documentation!

---

## 📖 Main Documentation

### [Main README](../README.md)
Complete project overview, installation guide, configuration, and usage instructions.

**Contents:**
- System overview and features
- Installation and setup
- Configuration (API keys, environment)
- Quick start guide
- Troubleshooting
- Project structure
- Contributing guidelines

---

## 🏗️ Architecture Documentation

### [Agent Architecture](./AGENT_ARCHITECTURE.md)
Comprehensive guide to the multi-agent system architecture, communication protocols, and orchestration patterns.

**Contents:**
- System architecture overview
- Agent roles and responsibilities
- Communication protocols (Job-based, Direct call)
- Complete data flow examples
- Orchestration patterns (Sequential, Parallel, Conditional)
- Error handling strategies
- Performance optimization techniques
- Integration examples

---

## 🤖 Individual Agent Documentation

### [WebCrawler Agent](./WEBCRAWLER_README.md)
**Port:** 8000 | **File:** `webcrawler.py`

Website content extraction and processing agent.

**Key Features:**
- HTML content extraction
- Text cleaning and structuring
- Multiple output formats (JSON, DOCX)
- Metadata extraction

**API Endpoints:**
- `POST /crawl` - Start crawl job
- `GET /status/{job_id}` - Check status
- `GET /download/{job_id}` - Download JSON
- `GET /download/docx/{job_id}` - Download DOCX

---

### [Keyword Extractor Agent](./KEYWORD_EXTRACTOR_README.md)
**Port:** 8001 | **File:** `keywordExtraction.py`

AI-powered SEO keyword extraction and analysis.

**Key Features:**
- LLM-based keyword extraction
- Domain/industry identification
- Confidence scoring
- Context-aware analysis

**API Endpoints:**
- `POST /extract-keywords` - Extract keywords
- `GET /status/{job_id}` - Check status
- `GET /download/{job_id}` - Download results

---

### [Competitor Gap Analyzer Agent](./GAP_ANALYZER_README.md)
**Port:** 8002 | **File:** `CompetitorGapAnalyzerAgent.py`

Competitive intelligence and content gap analysis.

**Key Features:**
- Automatic competitor discovery
- Keyword gap analysis
- Content opportunity identification
- Multi-competitor comparison

**API Endpoints:**
- `POST /analyze-keyword-gap` - Start analysis
- `GET /status/{job_id}` - Check status
- `GET /download/json/{job_id}` - Download analysis

---

### [Content Agent](./CONTENT_AGENT_README.md)
**Port:** 8003 | **File:** `content_agent.py`

AI-powered content generation for blogs and social media.

**Key Features:**
- SEO-optimized blog generation
- Multi-platform social posts
- AI image prompt generation
- Context-aware content creation

**API Endpoints:**
- `POST /generate-blog` - Generate blog post
- `POST /generate-social` - Generate social posts
- `GET /status/{job_id}` - Check status
- `GET /download/html/{job_id}` - Download blog HTML
- `GET /download/json/{job_id}` - Download social JSON

---

### [SEO Agent](./SEO_AGENT_README.md)
**Port:** 5000 | **File:** `seo_agent.py`

Comprehensive SEO auditing and reporting.

**Key Features:**
- Technical SEO analysis
- On-page optimization checks
- Content quality assessment
- Image optimization review
- Beautiful HTML reports

**API Endpoints:**
- `POST /analyze` - Start SEO audit
- `GET /status/{job_id}` - Check status
- `GET /download/report/{job_id}` - Download report

---

## 📊 Quick Reference Tables

### Agent Communication Matrix

| Agent | Calls → | Called By ← | Primary Function |
|-------|---------|-------------|------------------|
| **Orchestrator** | All agents | Frontend | Coordination, routing |
| **WebCrawler** | - | Orchestrator, Gap Analyzer | Content extraction |
| **Keyword Extractor** | Groq API | Orchestrator | Keyword analysis |
| **Gap Analyzer** | Groq, SerpAPI, WebCrawler | Orchestrator | Competitive analysis |
| **Content Agent** | Groq API | Orchestrator | Content generation |
| **SEO Agent** | - | Orchestrator | SEO auditing |
| **Metrics Collector** | Twitter, Instagram APIs | Orchestrator (scheduled) | Analytics |
| **RL Agent** | - | Orchestrator | Workflow optimization |
| **Router** | Groq API | Orchestrator | Intent classification |

---

### Agent Ports Reference

| Agent | Port | URL |
|-------|------|-----|
| Orchestrator | 8004 | http://127.0.0.1:8004 |
| WebCrawler | 8000 | http://127.0.0.1:8000 |
| Keyword Extractor | 8001 | http://127.0.0.1:8001 |
| Gap Analyzer | 8002 | http://127.0.0.1:8002 |
| Content Agent | 8003 | http://127.0.0.1:8003 |
| SEO Agent | 5000 | http://127.0.0.1:5000 |

---

### Communication Protocol Summary

All agents follow a standardized **job-based async pattern**:

```
1. POST /endpoint {payload} → {job_id, status: "started"}
2. GET /status/{job_id} → {status: "running|completed|failed"}
3. GET /download/{job_id} → {result_data}
```

**Benefits:**
- ✅ Non-blocking operations
- ✅ Long-running task support
- ✅ Retry-friendly
- ✅ Status tracking
- ✅ Scalable

---

## 🔗 Integration Examples

### Example 1: Complete Blog Generation Flow

```python
# 1. Extract keywords
keywords = keyword_extractor.extract(business_context)

# 2. Analyze competitors
gaps = gap_analyzer.analyze(company_name, description)

# 3. Generate blog
blog = content_agent.generate_blog(
    keywords=keywords,
    gaps=gaps,
    topic="User's topic"
)

# 4. Display preview
show_preview(blog_html)
```

### Example 2: SEO-Optimized Social Post

```python
# 1. Crawl website (if URL provided)
if url:
    content = webcrawler.crawl(url)
    brand_info = extract_brand(content)

# 2. Extract keywords
keywords = keyword_extractor.extract(brand_info)

# 3. Analyze gaps
gaps = gap_analyzer.analyze(brand_info)

# 4. Generate social post
post = content_agent.generate_social(
    keywords=keywords,
    gaps=gaps,
    platforms=["twitter", "instagram"]
)

# 5. Generate image (RunwayML)
image = generate_image(post["image_prompts"][0])

# 6. Post to social media
post_to_social(platform, text, image)
```

---

## 🛠️ Development Guide

### Adding a New Agent

1. **Create agent file** (e.g., `new_agent.py`)
2. **Implement FastAPI endpoints** (health, job, status, download)
3. **Add to orchestrator** communication
4. **Update documentation** (create README in `docs/`)
5. **Add to `start.bat`** (Windows) or start script
6. **Add to architecture diagram**
7. **Write tests**

**Template:**
```python
from fastapi import FastAPI, BackgroundTasks
import uuid

app = FastAPI(title="NewAgent")

jobs = {}

@app.get("/")
def health():
    return {"message": "NewAgent is running", "version": "1.0"}

@app.post("/process")
async def process(data: dict, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "started"}
    
    background_tasks.add_task(process_job, job_id, data)
    
    return {"job_id": job_id, "status": "started"}

def process_job(job_id: str, data: dict):
    # Do work
    result = do_something(data)
    jobs[job_id] = {"status": "completed", "result": result}

@app.get("/status/{job_id}")
def status(job_id: str):
    return jobs.get(job_id, {"status": "not_found"})

@app.get("/download/{job_id}")
def download(job_id: str):
    return jobs[job_id].get("result", {})
```

---

## 📝 API Testing

### Using cURL

```bash
# Test WebCrawler
curl -X POST http://127.0.0.1:8000/crawl \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'

# Test Keyword Extractor
curl -X POST http://127.0.0.1:8001/extract-keywords \
  -H "Content-Type: application/json" \
  -d '{"customer_statement": "Cloud kitchen in Chennai", "max_results": 10}'

# Test Content Agent
curl -X POST http://127.0.0.1:8003/generate-social \
  -H "Content-Type: application/json" \
  -d '{"brand_name": "Test", "platforms": ["twitter"]}'
```

### Using Python

```python
import requests

# Generic agent caller
def call_agent(base_url, endpoint, payload):
    # Start job
    resp = requests.post(f"{base_url}/{endpoint}", json=payload)
    job_id = resp.json()["job_id"]
    
    # Poll status
    while True:
        status = requests.get(f"{base_url}/status/{job_id}").json()
        if status["status"] == "completed":
            break
        time.sleep(2)
    
    # Download result
    result = requests.get(f"{base_url}/download/{job_id}").json()
    return result
```

---

## 🐛 Common Issues & Solutions

### Issue: Agent Not Starting

**Check:**
1. Port already in use? `netstat -ano | findstr :PORT`
2. Missing dependencies? `pip install -r requirements.txt`
3. Missing API keys? Check `.env` file

### Issue: Job Stuck in "Running"

**Solution:**
- Check agent logs for errors
- Increase timeout settings
- Restart agent
- Clear job status manually

### Issue: Communication Timeout

**Solution:**
- Check network connectivity
- Increase timeout in orchestrator
- Check agent health endpoint
- Review firewall settings

---

## 📞 Support

- **Issues:** Check individual agent README for troubleshooting
- **Architecture Questions:** See [AGENT_ARCHITECTURE.md](./AGENT_ARCHITECTURE.md)
- **API Reference:** Each agent README has complete API docs
- **Integration Help:** See code examples in each README

---

## 🗺️ Documentation Roadmap

### Completed ✅
- [x] Main README
- [x] Agent Architecture
- [x] WebCrawler Agent
- [x] Keyword Extractor Agent
- [x] Gap Analyzer Agent
- [x] Content Agent
- [x] SEO Agent

### In Progress 🚧
- [ ] Metrics Collector detailed guide
- [ ] RL Agent detailed guide
- [ ] Frontend (agent.html) documentation
- [ ] Database schema documentation

### Planned 📋
- [ ] Deployment guide (Docker, cloud)
- [ ] Performance tuning guide
- [ ] Security best practices
- [ ] Testing guide
- [ ] CI/CD setup
- [ ] API versioning strategy

---

**Last Updated:** October 2024 | Version 5.0.0  
**Maintained By:** Development Team

