# 🏗️ Multi-Agent Architecture

## Overview

This document explains how the multi-agent system works, how agents communicate, and the orchestration patterns used throughout the platform.

---

## Table of Contents

- [System Architecture](#system-architecture)
- [Agent Roles](#agent-roles)
- [Communication Protocols](#communication-protocols)
- [Data Flow](#data-flow)
- [Orchestration Patterns](#orchestration-patterns)
- [Error Handling](#error-handling)
- [Performance Optimization](#performance-optimization)

---

## System Architecture

### Layered Architecture

```
┌───────────────────────────────────────────────────────────────────┐
│                      PRESENTATION LAYER                            │
│  • agent.html (ChatGPT UI)  • metrics.html (Dashboard)           │
│  • login.html (Auth)         • Markdown Rendering                 │
└────────────────────────┬──────────────────────────────────────────┘
                         │
┌────────────────────────▼──────────────────────────────────────────┐
│                    ORCHESTRATION LAYER                             │
│  ┌────────────────────────────────────────────────────────┐       │
│  │              Orchestrator (FastAPI)                     │       │
│  │  • JWT Authentication  • Session Management             │       │
│  │  • Intent Recognition  • Brand Memory                   │       │
│  │  • RL Agent Selection  • Content Approval               │       │
│  └───────┬──────────┬──────────┬──────────┬──────────────┘       │
└──────────┼──────────┼──────────┼──────────┼────────────────────────┘
           │          │          │          │
┌──────────▼──────────▼──────────▼──────────▼────────────────────────┐
│                      AGENT LAYER                                    │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐          │
│  │   Web    │  │ Keyword  │  │Competitor│  │ Content  │          │
│  │ Crawler  │  │Extractor │  │   Gap    │  │  Agent   │          │
│  │          │  │          │  │ Analyzer │  │          │          │
│  │  :8000   │  │  :8001   │  │  :8002   │  │  :8003   │          │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐          │
│  │   SEO    │  │ Metrics  │  │    RL    │  │ Router   │          │
│  │  Agent   │  │Collector │  │  Agent   │  │          │          │
│  │  :5000   │  │(Internal)│  │(Internal)│  │(Internal)│          │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘          │
└─────────────────────────┬───────────────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────────────┐
│                      DATA LAYER                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │
│  │   SQLite DB  │  │  Cache Layer │  │  File System │             │
│  │  • Users     │  │  • API Cache │  │  • Images    │             │
│  │  • Sessions  │  │  • Responses │  │  • Previews  │             │
│  │  • Content   │  │              │  │  • Reports   │             │
│  │  • Metrics   │  │              │  │              │             │
│  └──────────────┘  └──────────────┘  └──────────────┘             │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Agent Roles

### 1. Orchestrator Agent 🎯
**Port:** 8004  
**File:** `orchestrator.py`

**Primary Responsibilities:**
- User authentication and session management
- Intent classification and routing
- Agent coordination and workflow execution
- Content approval and publishing
- Brand profile management
- Background job scheduling

**Key Components:**
- **IntelligentRouter**: LLM-based intent classification
- **RLAgent**: Reinforcement learning for workflow optimization
- **Database Manager**: Data persistence
- **Auth Manager**: JWT token handling
- **Scheduler**: Cron jobs for metrics collection

**APIs Exposed:**
```python
POST   /signup                    # User registration
POST   /login                     # Authentication
POST   /chat                      # Main chat interface
GET    /sessions                  # List user sessions
POST   /content/{id}/approve      # Content approval
GET    /metrics/dashboard         # Analytics data
POST   /metrics/collect           # Trigger metrics collection
```

---

### 2. WebCrawler Agent 🕷️
**Port:** 8000  
**File:** `webcrawler.py`

**Primary Responsibilities:**
- Extract text content from websites
- Clean and structure HTML content
- Generate downloadable reports (DOCX, JSON)
- Cache crawled data

**Communication Pattern:**
```python
# 1. Initiate crawl
Request:  POST /crawl
Body:     {"url": "https://example.com"}
Response: {"job_id": "uuid-1234", "status": "started"}

# 2. Check status
Request:  GET /status/uuid-1234
Response: {"status": "completed", "url": "..."}

# 3. Download result
Request:  GET /download/uuid-1234
Response: {"url": "...", "extracted_text": "...", "metadata": {...}}
```

**Data Format:**
```json
{
  "url": "https://example.com",
  "title": "Page Title",
  "extracted_text": "Clean text content...",
  "metadata": {
    "word_count": 1500,
    "crawl_timestamp": "2024-10-26T10:00:00Z"
  }
}
```

---

### 3. Keyword Extractor Agent 🔑
**Port:** 8001  
**File:** `keywordExtraction.py`

**Primary Responsibilities:**
- Extract relevant keywords from business context
- Identify target domains/industries
- Provide SEO-focused keyword analysis
- Rank keywords by relevance

**Communication Pattern:**
```python
# Extract keywords
Request:  POST /extract-keywords
Body:     {
  "customer_statement": "Cloud kitchen in Chennai...",
  "max_results": 10
}
Response: {
  "job_id": "uuid",
  "status": "started"
}

# Get results
Request:  GET /download/uuid
Response: {
  "keywords": ["cloud kitchen", "meal prep", "chennai food"],
  "domains": ["restaurant", "food delivery"],
  "confidence_scores": {...}
}
```

**Integration with Other Agents:**
- **Input From:** Orchestrator (business context)
- **Output To:** Gap Analyzer, Content Agent
- **Uses:** Groq LLM for NLP processing

---

### 4. Competitor Gap Analyzer Agent 📊
**Port:** 8002  
**File:** `CompetitorGapAnalyzerAgent.py`

**Primary Responsibilities:**
- Identify competitors using SerpAPI
- Crawl competitor websites
- Analyze content gaps and opportunities
- Provide keyword comparison

**Communication Pattern:**
```python
# Analyze keyword gaps
Request:  POST /analyze-keyword-gap
Body:     {
  "company_name": "Cloud24",
  "product_description": "Cloud kitchen in Chennai",
  "company_url": "https://cloud24.com",
  "max_competitors": 3,
  "max_pages_per_site": 2
}
Response: {"job_id": "uuid", "status": "started"}

# Get analysis
Request:  GET /download/json/uuid
Response: {
  "competitors": [...],
  "content_gaps": [...],
  "keyword_comparison": {...},
  "opportunities": [...]
}
```

**Workflow:**
1. Use Groq to extract domain from product description
2. Query SerpAPI for top competitors
3. Crawl competitor websites (via WebCrawler)
4. Compare keywords and identify gaps
5. Generate actionable insights

---

### 5. Content Agent ✍️
**Port:** 8003  
**File:** `content_agent.py`

**Primary Responsibilities:**
- Generate SEO-optimized blog posts
- Create platform-specific social media content
- Generate image prompts for AI art
- Format content with metadata

**Communication Patterns:**

**Blog Generation:**
```python
Request:  POST /generate-blog
Body:     {
  "keywords": {...},
  "business_details": {
    "brand_name": "Cloud24",
    "industry": "Cloud Kitchen",
    "location": "Chennai"
  },
  "topic": "Healthy meal prep tips",
  "gap_analysis": {...}
}
Response: {
  "job_id": "uuid",
  "status": "started"
}

# Download HTML blog
Request:  GET /download/html/uuid
Response: "<!DOCTYPE html>...<h1>Blog Title</h1>..."
```

**Social Post Generation:**
```python
Request:  POST /generate-social
Body:     {
  "keywords": {...},
  "brand_name": "Cloud24",
  "industry": "Cloud Kitchen",
  "location": "Chennai",
  "platforms": ["twitter", "instagram"],
  "tone": "professional"
}
Response: {
  "posts": {
    "twitter": {
      "copy": "Tweet text...",
      "hashtags": ["#CloudKitchen", "#Chennai"]
    },
    "instagram": {
      "copy": "Instagram caption...",
      "hashtags": [...]
    }
  },
  "image_prompts": ["Photorealistic image..."],
  "meta": {...}
}
```

**Key Features:**
- Context-aware content generation
- Location-specific customization
- SEO keyword integration
- Multiple tone options

---

### 6. SEO Agent 🔍
**Port:** 5000  
**File:** `seo_agent.py`

**Primary Responsibilities:**
- Comprehensive SEO audits
- Technical SEO analysis
- On-page optimization recommendations
- Generate detailed HTML reports

**Communication Pattern:**
```python
Request:  POST /analyze
Body:     {"url": "https://example.com"}
Response: {
  "job_id": "uuid",
  "status": "started"
}

# Download report
Request:  GET /download/report/uuid
Response: "<!DOCTYPE html>...<div class='seo-score'>85/100</div>..."
```

**Analysis Coverage:**
- Meta tags and titles
- Header structure (H1-H6)
- Image optimization
- Mobile responsiveness
- Page speed insights
- Internal/external links

---

### 7. Metrics Collector 📈
**Component:** Internal module  
**File:** `metrics_collector.py`

**Primary Responsibilities:**
- Fetch Instagram engagement metrics
- Fetch Twitter engagement metrics
- Calculate engagement rates
- Store historical data
- Aggregate analytics

**Key Functions:**
```python
# Collect metrics for a specific post
collector = MetricsCollector()
collector.collect_and_save_metrics(
    content_id="uuid",
    platform="instagram",
    post_id="ABC123xyz"
)

# Get aggregated dashboard metrics
metrics = get_aggregated_metrics(
    user_id=1,
    days=30
)
# Returns: {total_posts, total_engagement, avg_rate, ...}
```

**Scheduled Jobs:**
- Runs every 4 hours (APScheduler)
- On-demand via `/metrics/collect` endpoint
- Automatic on dashboard page load

**Metrics Tracked:**
- Likes, comments, shares
- Impressions (when available)
- Reach estimates
- Engagement rate (%)
- Platform-specific analytics

---

### 8. RL Agent (Reinforcement Learning) 🎓
**Component:** Internal module  
**File:** `rl_agent.py`

**Primary Responsibilities:**
- Learn optimal agent workflows
- Select best workflow based on intent and context
- Update Q-values based on performance
- Optimize resource allocation

**Q-Learning Algorithm:**
```python
# State: (intent, has_url, has_keywords)
# Action: workflow_name
# Reward: content_approval + engagement_score

Q(state, action) = Q(state, action) + 
    α * [reward + γ * max(Q(next_state, a')) - Q(state, action)]
```

**Available Workflows:**
- `quick_blog`: Fast blog generation
- `comprehensive_blog`: Full analysis pipeline
- `quick_social`: Fast social post
- `comprehensive_social`: Full social pipeline
- `seo_focused`: SEO-optimized content

**Decision Process:**
1. Observe state (intent, user context)
2. Check Q-values for all workflows
3. Use ε-greedy strategy (explore vs exploit)
4. Execute chosen workflow
5. Receive reward based on user approval and metrics
6. Update Q-values

---

### 9. Intelligent Router 🧠
**Component:** Internal module  
**File:** `intelligent_router.py`

**Primary Responsibilities:**
- Classify user intent using LLM
- Extract parameters from natural language
- Route to appropriate agent workflow
- Handle general conversations

**Intent Classification:**
```python
router = IntelligentRouter()
result = router.classify_intent_with_groq(
    user_message="Create a blog about healthy eating",
    conversation_history=[...]
)
# Returns:
{
    "intent": "blog_generation",
    "confidence": 0.95,
    "parameters": {
        "topic": "healthy eating",
        "content_type": "blog"
    }
}
```

**Supported Intents:**
- `blog_generation`
- `social_post`
- `seo_analysis`
- `metrics_report`
- `brand_setup`
- `general_conversation`

**LLM Prompt Engineering:**
```python
system_prompt = """You are an AI assistant that classifies user intent.
Based on the conversation, determine if the user wants to:
- Generate a blog post
- Create social media content
- Analyze SEO
- View metrics
- Set up business profile
- Have a general conversation

Return JSON with intent, confidence (0-1), and extracted parameters."""
```

---

## Communication Protocols

### 1. Job-Based Pattern (Async)

All long-running agent operations use this pattern:

```
┌─────────────┐
│ Orchestrator│
└──────┬──────┘
       │ 1. POST /endpoint {"data": "..."}
       ▼
┌──────────────┐
│    Agent     │
└──────┬───────┘
       │ 2. Response: {"job_id": "uuid", "status": "started"}
       ▼
┌─────────────┐
│ Orchestrator│ ─┐
└─────────────┘  │ 3. Polling loop
       ▲         │    GET /status/uuid
       │         │
       └─────────┘
       │ 4. {"status": "completed"}
       ▼
┌─────────────┐
│ Orchestrator│
└──────┬──────┘
       │ 5. GET /download/uuid
       ▼
┌──────────────┐
│    Agent     │
└──────┬───────┘
       │ 6. Response: {result_data}
       ▼
┌─────────────┐
│ Orchestrator│
└─────────────┘
```

**Advantages:**
- ✅ Non-blocking
- ✅ Handles long operations
- ✅ Supports retries
- ✅ Clear status tracking

---

### 2. Direct Call Pattern (Sync)

For fast operations:

```
┌─────────────┐
│ Orchestrator│
└──────┬──────┘
       │ POST /endpoint {"data": "..."}
       ▼
┌──────────────┐
│    Agent     │
└──────┬───────┘
       │ Response: {result}
       ▼
┌─────────────┐
│ Orchestrator│
└─────────────┘
```

**Used For:**
- Authentication
- Simple queries
- Cache hits
- Status checks

---

### 3. Retry Logic

All agent calls use `tenacity` for robust error handling:

```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10)
)
def call_agent_job(agent_name, url, payload, ...):
    # Attempt call up to 3 times
    # Wait 2s, 4s, 8s between retries
    pass
```

---

## Data Flow

### Complete Blog Generation Flow

```
USER: "Write a blog about meal prep"
  │
  ▼
┌─────────────────────────────────────────────────────────────┐
│ 1. ORCHESTRATOR - Receive Message                           │
│    • Authenticate user (JWT)                                 │
│    • Load session history                                    │
│    • Store message in database                               │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. INTELLIGENT ROUTER - Classify Intent                     │
│    • Build context from conversation history                 │
│    • Call Groq LLM with classification prompt                │
│    • Parse JSON response                                     │
│    Result: intent="blog_generation", confidence=0.95         │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. BRAND CONTEXT - Retrieve/Extract                         │
│    • Check database for existing brand profile               │
│    • If not exists: Extract from conversation history        │
│    • Call Groq to extract brand details                      │
│    • Save to database                                        │
│    Result: {brand_name, industry, location, ...}             │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. RL AGENT - Select Workflow                               │
│    • Observe state: (intent, has_url, context)               │
│    • Query Q-table for best workflow                         │
│    • Apply ε-greedy exploration                              │
│    • Select: "comprehensive_blog"                            │
│    Result: [webcrawler, keyword, gap, content]               │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. WEBCRAWLER - Extract Website Content (if URL provided)   │
│    • POST /crawl {url}                                       │
│    • Poll /status/job_id until complete                      │
│    • GET /download/job_id                                    │
│    Result: {"extracted_text": "...", "metadata": {...}}      │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. KEYWORD EXTRACTOR - Analyze Keywords                     │
│    • Build context: brand + user query + crawled data        │
│    • POST /extract-keywords {customer_statement, max: 10}    │
│    • Poll /status/job_id                                     │
│    • GET /download/job_id                                    │
│    Result: {keywords: ["meal prep", ...], domains: [...]}    │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 7. GAP ANALYZER - Competitor Analysis                       │
│    • POST /analyze-keyword-gap                               │
│      {company_name, product_desc, url, max_competitors: 3}   │
│    • Agent uses SerpAPI to find competitors                  │
│    • Crawls competitor sites                                 │
│    • Compares keywords                                       │
│    • Poll status and download results                        │
│    Result: {content_gaps, opportunities, keyword_comparison} │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 8. CONTENT AGENT - Generate Blog                            │
│    • POST /generate-blog                                     │
│      {keywords, business_details, topic, gap_analysis}       │
│    • Agent uses Groq to write SEO-optimized blog             │
│    • Formats as HTML with proper structure                   │
│    • Poll status and download HTML                           │
│    Result: Full HTML blog post                               │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 9. ORCHESTRATOR - Save & Preview                            │
│    • Save HTML to previews/blog_{content_id}.html            │
│    • Store in database:                                      │
│      - content_id, type="blog", status="pending"             │
│      - preview_url, metadata                                 │
│    • Send response to frontend with preview buttons          │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 10. FRONTEND - Display Preview                              │
│     • Render chat message with:                              │
│       "📝 Blog post ready! [Preview] [Approve] [Reject]"     │
│     • User clicks [Preview] → Open in new tab                │
│     • User clicks [Approve] → Trigger approval endpoint      │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼ (User approves)
┌─────────────────────────────────────────────────────────────┐
│ 11. ORCHESTRATOR - Publish                                  │
│     • POST /content/{content_id}/approve {approved: true}    │
│     • Upload HTML to AWS S3                                  │
│     • Update database: status="approved", url=s3_url         │
│     • RL Agent records positive reward                       │
│     • Send public URL to user                                │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 12. RL AGENT - Update Q-Values                              │
│     • Calculate reward: approval + future engagement         │
│     • Update Q(state, "comprehensive_blog") += learning      │
│     • Save updated Q-table to database                       │
└─────────────────────────────────────────────────────────────┘
```

---

## Orchestration Patterns

### 1. Sequential Workflow

Agents execute in order, each using previous results:

```python
# Example: Blog generation
results = {}
results['crawl'] = await call_webcrawler(url)
results['keywords'] = await call_keyword_extractor(results['crawl'])
results['gaps'] = await call_gap_analyzer(results['keywords'])
results['blog'] = await call_content_agent(results)
```

### 2. Parallel Execution

Independent operations run concurrently:

```python
# Example: Multiple SEO analyses
import asyncio

tasks = [
    analyze_seo(url1),
    analyze_seo(url2),
    analyze_seo(url3)
]
results = await asyncio.gather(*tasks)
```

### 3. Conditional Branching

Workflow changes based on context:

```python
if url_provided:
    crawl_result = await call_webcrawler(url)
    context = extract_context(crawl_result)
else:
    context = user_input

# Continue with context
keywords = await call_keyword_extractor(context)
```

### 4. Retry with Fallback

Graceful degradation on failure:

```python
try:
    gap_analysis = await call_gap_analyzer(params)
except Exception as e:
    logger.warning(f"Gap analysis failed: {e}")
    gap_analysis = None  # Continue without it

# Generate content with or without gap analysis
content = await call_content_agent(
    keywords=keywords,
    gap_analysis=gap_analysis  # May be None
)
```

---

## Error Handling

### Agent-Level Error Handling

Each agent implements:

```python
@app.post("/endpoint")
async def process(req: Request):
    try:
        # Validate input
        if not req.data:
            raise HTTPException(400, "Missing data")
        
        # Process
        result = await heavy_operation(req.data)
        
        # Return success
        return {"status": "success", "result": result}
        
    except ValidationError as e:
        logger.error(f"Validation error: {e}")
        raise HTTPException(422, str(e))
        
    except ExternalAPIError as e:
        logger.error(f"External API failed: {e}")
        raise HTTPException(502, "External service unavailable")
        
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise HTTPException(500, "Internal server error")
```

### Orchestrator-Level Error Handling

```python
def call_agent_with_fallback(agent_name, *args, **kwargs):
    """Call agent with retry and fallback."""
    try:
        return call_agent_job(agent_name, *args, **kwargs)
    except RetryError:
        logger.warning(f"{agent_name} failed after retries, using fallback")
        return None  # or default value
    except Exception as e:
        logger.error(f"{agent_name} unexpected error: {e}")
        return None
```

### User-Facing Error Messages

```python
# Generic error
"⚠️ Something went wrong. Please try again."

# Specific error
"⚠️ Blog generation failed: Unable to analyze competitors. " 
"Continuing with keyword analysis only."

# Actionable error
"⚠️ Instagram login failed. Please check your credentials in .env "
"and run: python test_instagram_login.py"
```

---

## Performance Optimization

### 1. Caching Strategy

```python
# Agent response caching
cache_key = f"{agent_name}:{hash(payload)}"
if cache_key in cache:
    return cache[cache_key]

result = await call_agent(payload)
cache[cache_key] = result
return result
```

### 2. Connection Pooling

```python
# Reuse HTTP sessions
session = aiohttp.ClientSession()
response = await session.post(url, json=payload)
```

### 3. Background Tasks

```python
# Non-blocking operations
background_tasks.add_task(
    collect_metrics_for_post,
    content_id
)
return {"message": "Processing in background"}
```

### 4. Database Indexing

```sql
CREATE INDEX idx_sessions_user_id ON sessions(user_id);
CREATE INDEX idx_messages_session_id ON messages(session_id);
CREATE INDEX idx_content_status ON generated_content(status);
CREATE INDEX idx_metrics_content_id ON social_metrics(content_id);
```

---

## Summary

This multi-agent architecture provides:

✅ **Modularity** - Each agent is independent and replaceable  
✅ **Scalability** - Agents can run on different servers  
✅ **Reliability** - Retry logic and fallback mechanisms  
✅ **Intelligence** - RL-based optimization and LLM routing  
✅ **Observability** - Comprehensive logging and tracing  
✅ **Flexibility** - Easy to add new agents or workflows  

For detailed agent-specific documentation, see individual agent README files in the `docs/` directory.

---

**Last Updated:** October 2024 | Version 5.0.0

