# 🚀 AI-Powered Multi-Agent Content Marketing Platform

A sophisticated multi-agent system that leverages AI to automate content marketing workflows, from SEO analysis to social media posting with intelligent decision-making and metrics tracking.

![Version](https://img.shields.io/badge/version-5.0.0-blue)
![Python](https://img.shields.io/badge/python-3.12-green)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115.0-teal)
![License](https://img.shields.io/badge/license-MIT-orange)

---

## 📋 Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Agent Communication](#agent-communication)
- [API Documentation](#api-documentation)
- [Project Structure](#project-structure)
- [Contributing](#contributing)
- [Troubleshooting](#troubleshooting)

---

## 🎯 Overview

This platform uses a **multi-agent architecture** powered by **Groq LLM** to automate end-to-end content marketing:

1. **Extract business information** from user input or websites
2. **Analyze competitors** and identify content gaps
3. **Generate SEO-optimized blogs** and social media posts
4. **Post to Instagram & Twitter** with AI-generated images
5. **Track engagement metrics** and optimize using reinforcement learning
6. **Provide ChatGPT-like conversational interface** for natural interaction

### What Makes It Unique?

- 🤖 **Intelligent Agent Orchestration** - Autonomous agents communicate and coordinate
- 🧠 **Context-Aware Brand Memory** - Remembers your business details across sessions
- 📊 **Reinforcement Learning** - Optimizes agent selection based on performance
- 🎨 **AI Image Generation** - Creates visual content with RunwayML
- 📈 **Real-Time Metrics** - Tracks social media engagement automatically
- 💬 **Natural Conversations** - ChatGPT-like interface with intent recognition

---

## ✨ Key Features

### Content Generation
- ✅ **Blog Post Generation** - SEO-optimized, keyword-rich articles
- ✅ **Social Media Posts** - Platform-specific content (Twitter, Instagram)
- ✅ **AI Image Generation** - Professional visuals for posts
- ✅ **Multi-Platform Publishing** - Direct posting to social media

### Intelligence Layer
- 🧠 **Brand Profile Extraction** - Automatically captures business details
- 🔍 **Competitor Analysis** - Identifies content gaps and opportunities
- 🎯 **Keyword Research** - Extracts relevant SEO keywords
- 🤖 **Intent Recognition** - Routes queries to appropriate agents
- 📚 **Conversation Memory** - Maintains context across sessions

### Analytics & Optimization
- 📊 **Engagement Tracking** - Instagram & Twitter metrics
- 🔄 **Auto-Refresh Metrics** - Updates on page load
- 📈 **Performance Dashboard** - Visual analytics
- 🎓 **Reinforcement Learning** - Improves agent selection over time

### User Experience
- 💬 **ChatGPT-Like Interface** - Natural conversation flow
- 🖼️ **Content Preview** - Approve before publishing
- 📱 **Session Management** - Resume conversations anytime
- 🔐 **JWT Authentication** - Secure user accounts

---

## 🏗️ Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER INTERFACE                           │
│  (agent.html - ChatGPT-like, metrics.html - Dashboard)          │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR (FastAPI)                        │
│  • JWT Authentication      • Session Management                  │
│  • Intent Routing          • Brand Memory                        │
│  • Content Approval Flow   • RL Agent Selection                  │
└─────┬──────┬──────┬──────┬──────┬──────┬──────┬────────────────┘
      │      │      │      │      │      │      │
      ▼      ▼      ▼      ▼      ▼      ▼      ▼
┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
│  Web    │ │ Keyword │ │Competitor│ │ Content │ │  SEO    │
│ Crawler │ │Extractor│ │   Gap   │ │  Agent  │ │ Agent   │
│         │ │         │ │ Analyzer │ │         │ │         │
│ :8000   │ │ :8001   │ │  :8002  │ │  :8003  │ │  :5000  │
└─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘
      │          │            │            │           │
      └──────────┴────────────┴────────────┴───────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │  EXTERNAL APIS   │
                    │  • Groq LLM      │
                    │  • RunwayML      │
                    │  • Twitter API   │
                    │  • Instagram API │
                    │  • SerpAPI       │
                    └──────────────────┘
```

### Agent Communication Flow

```
USER → Orchestrator → IntelligentRouter (LLM) → Intent Classification
                              │
                              ▼
                    ┌─────────────────┐
                    │  Intent Router  │
                    │  Confidence: 95%│
                    └────────┬────────┘
                             │
        ┌────────────────────┼────────────────────┐
        ▼                    ▼                    ▼
   blog_generation      social_post         seo_analysis
        │                    │                    │
        ▼                    ▼                    ▼
    RL Agent Selects     RL Agent Selects    RL Agent Selects
    Best Workflow        Best Workflow       Best Workflow
        │                    │                    │
        ▼                    ▼                    ▼
   [WebCrawler] ──┐    [WebCrawler] ──┐     [WebCrawler]
   [Keyword]   ──┤    [Keyword]   ──┤          │
   [Gap]       ──┤    [Gap]       ──┤          ▼
   [Content]   ──┘    [Content]   ──┘     [SEOAgent]
        │                    │                    │
        ▼                    ▼                    ▼
   Blog Preview       Social Preview        SEO Report
        │                    │                    │
        ▼                    ▼                    ▼
   User Approval      User Approval         Display
        │                    │
        ▼                    ▼
   AWS S3 Hosting     Instagram + Twitter
        │                    │
        ▼                    ▼
   Public URL         Metrics Collection
```

---

## 🛠️ Tech Stack

### Backend
- **FastAPI** - High-performance async web framework
- **Python 3.12** - Modern Python with type hints
- **SQLite** - Embedded database for data persistence
- **Groq API** - Fast LLM inference (Llama 3.3 70B)
- **Tweepy** - Twitter API integration
- **Instagrapi** - Instagram API integration

### Frontend
- **Vanilla JavaScript** - Fast, no-framework approach
- **HTML5/CSS3** - Modern responsive design
- **Markdown Rendering** - Real-time message formatting

### AI & ML
- **LangSmith** - LLM observability and tracing
- **Reinforcement Learning** - Q-learning for agent optimization
- **RunwayML** - AI image generation

### DevOps & Monitoring
- **APScheduler** - Background job scheduling
- **Python Logging** - Comprehensive logging
- **Tenacity** - Retry logic for API calls

---

## 📦 Installation

### Prerequisites

- Python 3.12+
- Windows/Linux/MacOS
- API Keys (see Configuration)

### Step 1: Clone Repository

```bash
git clone <your-repo-url>
cd "multi agent"
```

### Step 2: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 3: Configure Environment

Create a `.env` file in the project root:

```bash
# Copy example
cp .env.example .env

# Edit with your API keys
notepad .env  # Windows
nano .env     # Linux/Mac
```

### Step 4: Initialize Database

```bash
python -c "import database; database.create_tables()"
```

### Step 5: Test Instagram Login (Optional)

```bash
python test_instagram_login.py
```

---

## ⚙️ Configuration

### Required API Keys

Add these to your `.env` file:

```bash
# AI/LLM
GROQ_API_KEY=gsk_xxxxx                    # Required - Get from console.groq.com
LANGSMITH_API_KEY=ls_xxxxx                # Optional - LangSmith tracing

# Social Media
TWITTER_API_KEY=xxxxx                      # Required for Twitter posting
TWITTER_API_SECRET=xxxxx
TWITTER_ACCESS_TOKEN=xxxxx
TWITTER_ACCESS_TOKEN_SECRET=xxxxx
TWITTER_BEARER_TOKEN=xxxxx

INSTAGRAM_USERNAME=your_username           # Required for Instagram
INSTAGRAM_PASSWORD=your_password

# Image Generation
RUNWAYML_API_KEY=xxxxx                     # Required for AI images

# Search & SEO
SERPAPI_KEY=xxxxx                          # Required for competitor analysis

# AWS (Optional - for blog hosting)
AWS_ACCESS_KEY_ID=xxxxx                    # Optional
AWS_SECRET_ACCESS_KEY=xxxxx
AWS_S3_BUCKET=your-bucket-name
AWS_REGION=us-east-1

# App Configuration
JWT_SECRET=your-random-secret-key-here     # Change this!
DATABASE_PATH=orchestrator_memory.sqlite
```

### API Key Sources

| Service | Get Keys From | Free Tier? |
|---------|---------------|------------|
| Groq | https://console.groq.com | ✅ Yes |
| Twitter | https://developer.twitter.com | ✅ Limited |
| Instagram | Your Instagram account | ✅ Yes |
| RunwayML | https://runwayml.com | ⚠️ Credits |
| SerpAPI | https://serpapi.com | ✅ Limited |
| AWS S3 | https://aws.amazon.com | ✅ Free tier |

---

## 🚀 Usage

### Starting the Platform

#### Option 1: Start All Services (Windows)
```bash
start.bat
```

#### Option 2: Start Manually

**Terminal 1 - Orchestrator:**
```bash
python orchestrator.py
# Runs on http://127.0.0.1:8004
```

**Terminal 2 - WebCrawler:**
```bash
python webcrawler.py
# Runs on http://127.0.0.1:8000
```

**Terminal 3 - Keyword Extractor:**
```bash
python keywordExtraction.py
# Runs on http://127.0.0.1:8001
```

**Terminal 4 - Gap Analyzer:**
```bash
python CompetitorGapAnalyzerAgent.py
# Runs on http://127.0.0.1:8002
```

**Terminal 5 - Content Agent:**
```bash
python content_agent.py
# Runs on http://127.0.0.1:8003
```

**Terminal 6 - SEO Agent:**
```bash
python seo_agent.py
# Runs on http://127.0.0.1:5000
```

### Accessing the Platform

1. **Main Interface:** http://127.0.0.1:8004/agent.html
2. **Metrics Dashboard:** http://127.0.0.1:8004/metrics.html
3. **Login Page:** http://127.0.0.1:8004/login.html

### Quick Start Guide

#### 1. Create Account
- Open http://127.0.0.1:8004/login.html
- Click "Sign Up"
- Enter email and password

#### 2. Set Up Business Profile
```
You: Hi, I want to set up my business
AI: Let me save your business information...

You: I run a cloud kitchen called Cloud24 in Chennai. 
     My email is cloud24@gmail.com, phone: 7305900924

AI: ✅ Brand Profile Saved!
    Business Name: Cloud24
    Industry: Cloud Kitchen
    Location: Chennai
```

#### 3. Generate Content
```
You: Create a blog post about healthy meal prep

AI: I'll create a blog post for you. Analyzing your business 
    and competitors...
    [Shows preview with approval buttons]
```

#### 4. Post to Social Media
```
You: Create a social media post for Instagram

AI: Creating social media content for you...
    [Shows image + text preview]
    [Approve to post]
```

#### 5. View Metrics
```
Open: http://127.0.0.1:8004/metrics.html
- See engagement rates
- Track post performance
- Compare platforms
```

---

## 🔄 Agent Communication

### Communication Protocol

All agents communicate via **HTTP REST APIs** with a standardized job-based pattern:

```python
# 1. Initiate Job
POST /endpoint
Response: {"job_id": "uuid", "status": "started"}

# 2. Check Status
GET /status/{job_id}
Response: {"status": "running|completed|failed"}

# 3. Download Result
GET /download/{job_id}
Response: {result data}
```

### Message Flow Example

**Blog Generation Workflow:**

```
1. User Input
   └─> Orchestrator receives: "Write a blog about SEO"

2. Intent Classification
   └─> IntelligentRouter (Groq) → Intent: "blog_generation"

3. Brand Context Retrieval
   └─> Database → Brand Profile: {name, industry, location}

4. RL Agent Selection
   └─> RLAgent → Workflow: "comprehensive_blog"
       [webcrawler → keyword → gap → content]

5. Agent Execution Chain:
   
   A. WebCrawler (if URL provided)
      POST /crawl {"url": "..."}
      └─> Returns: {"extracted_text": "..."}
   
   B. KeywordExtractor
      POST /extract-keywords {
        "customer_statement": "Business context + user query"
      }
      └─> Returns: {"keywords": [...], "domains": [...]}
   
   C. CompetitorGapAnalyzer
      POST /analyze-keyword-gap {
        "company_name": "Cloud24",
        "product_description": "...",
        "company_url": "..."
      }
      └─> Returns: {"content_gaps": [...], "opportunities": [...]}
   
   D. ContentAgent
      POST /generate-blog {
        "keywords": {...},
        "business_details": {...},
        "gap_analysis": {...}
      }
      └─> Returns: {"html": "...", "metadata": {...}}

6. Content Storage
   └─> Database → Save as "pending" status

7. User Preview
   └─> Frontend shows content with [Approve] [Reject]

8. Post-Approval
   └─> Upload to AWS S3 → Public URL
   └─> Update status: "approved"
   └─> RL Agent records reward

9. Metrics Collection (Background)
   └─> APScheduler → Every 4 hours
   └─> MetricsCollector → Updates engagement data
```

See [AGENT_ARCHITECTURE.md](./docs/AGENT_ARCHITECTURE.md) for detailed communication patterns.

---

## 📚 API Documentation

### Orchestrator API (Port 8004)

#### Authentication
```bash
# Signup
POST /signup
Body: {"email": "user@example.com", "password": "pass123"}

# Login
POST /login
Body: {"email": "user@example.com", "password": "pass123"}
Response: {"token": "jwt-token", "user_id": 1}
```

#### Chat
```bash
# Send message
POST /chat
Headers: {"Authorization": "Bearer {token}"}
Body: {
  "message": "Create a blog post",
  "session_id": "uuid"
}
```

#### Content Management
```bash
# Approve content
POST /content/{content_id}/approve
Body: {"approved": true}

# Get preview
GET /preview/blog/{content_id}
GET /preview/image/{image_path}
```

#### Metrics
```bash
# Trigger collection
POST /metrics/collect?days=7

# Get dashboard
GET /metrics/dashboard?days=30
```

### Agent APIs

See individual agent README files:
- [WebCrawler API](./docs/WEBCRAWLER_README.md)
- [Keyword Extractor API](./docs/KEYWORD_EXTRACTOR_README.md)
- [Gap Analyzer API](./docs/GAP_ANALYZER_README.md)
- [Content Agent API](./docs/CONTENT_AGENT_README.md)
- [SEO Agent API](./docs/SEO_AGENT_README.md)

---

## 📁 Project Structure

```
multi agent/
├── orchestrator.py              # Main coordinator (FastAPI)
├── webcrawler.py                # Website content extraction
├── keywordExtraction.py         # SEO keyword analysis
├── CompetitorGapAnalyzerAgent.py # Competitive analysis
├── content_agent.py             # Blog/social content generation
├── seo_agent.py                 # SEO auditing
├── metrics_collector.py         # Social media metrics
├── rl_agent.py                  # Reinforcement learning
├── intelligent_router.py        # Intent classification
├── database.py                  # SQLite operations
├── auth.py                      # JWT authentication
├── scheduler.py                 # Background jobs
├── cost_model.py                # Cost tracking
│
├── agent.html                   # ChatGPT-like UI
├── metrics.html                 # Analytics dashboard
├── login.html                   # Authentication UI
├── style.css                    # Global styles
├── script.js                    # Shared JS utilities
│
├── requirements.txt             # Python dependencies
├── .env                         # Configuration (create this)
├── start.bat                    # Launch script (Windows)
│
├── docs/                        # Detailed documentation
│   ├── AGENT_ARCHITECTURE.md
│   ├── WEBCRAWLER_README.md
│   ├── KEYWORD_EXTRACTOR_README.md
│   ├── GAP_ANALYZER_README.md
│   ├── CONTENT_AGENT_README.md
│   └── SEO_AGENT_README.md
│
├── generated_images/            # AI-generated visuals
├── previews/                    # Content previews
├── reports/                     # SEO reports
├── uploads/                     # User uploads
├── cache/                       # Agent response cache
└── orchestrator_memory.sqlite   # Main database
```

---

## 🐛 Troubleshooting

### Common Issues

#### 1. Instagram "Challenge Required" Error
```bash
# Solution: Login on Instagram app first
python test_instagram_login.py
# Complete any security checks, wait 24 hours
```

#### 2. Twitter 401 Unauthorized
```
# This is normal with free tier
# Metrics work with estimated impressions
# For real data: Apply for Elevated access
https://developer.twitter.com/en/portal/products/elevated
```

#### 3. Groq JSON Validation Error
```
# Usually self-correcting
# Check prompts don't have special characters
# Retry the operation
```

#### 4. "MetricsCollector not defined"
```bash
# Fixed in latest version
# Ensure you have latest orchestrator.py
```

#### 5. Database Locked Error
```bash
# Close all connections
# Restart orchestrator.py
```

### Debug Mode

Enable detailed logging:

```python
# In orchestrator.py
logging.basicConfig(level=logging.DEBUG)
```

---

## 📊 Performance & Scalability

### Current Capabilities
- ✅ **Concurrent Users:** 10-50 (SQLite limit)
- ✅ **Requests/sec:** ~100 (FastAPI async)
- ✅ **Agent Response Time:** 2-10 seconds
- ✅ **Storage:** Unlimited (SQLite 140TB limit)

### Scaling Considerations

For production deployment:

1. **Database:** Migrate to PostgreSQL
2. **Caching:** Add Redis for agent responses
3. **Queue:** Use Celery for background jobs
4. **Load Balancer:** Nginx for multiple orchestrator instances
5. **Monitoring:** Prometheus + Grafana

---

## 🔐 Security

- ✅ JWT-based authentication
- ✅ Password hashing (bcrypt)
- ✅ API key protection (.env)
- ✅ SQL injection prevention (parameterized queries)
- ⚠️ HTTPS recommended for production
- ⚠️ Rate limiting recommended for production

---

## 🤝 Contributing

We welcome contributions! Please see:

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

---

## 📝 License

This project is licensed under the MIT License - see [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- **Groq** - Lightning-fast LLM inference
- **FastAPI** - Modern Python web framework
- **RunwayML** - AI image generation
- **LangSmith** - LLM observability

---

## 📞 Support

- 📧 Email: support@example.com
- 📖 Docs: [Full Documentation](./docs/)
- 🐛 Issues: [GitHub Issues](https://github.com/your-repo/issues)
- 💬 Discord: [Community Server](https://discord.gg/your-server)

---

## 🗺️ Roadmap

### Version 5.1 (Q1 2025)
- [ ] Facebook & LinkedIn integration
- [ ] Voice input support
- [ ] Multi-language content generation
- [ ] Video content generation

### Version 6.0 (Q2 2025)
- [ ] PostgreSQL migration
- [ ] GraphQL API
- [ ] Mobile app (React Native)
- [ ] Team collaboration features

---

**Built with ❤️ using AI and Multi-Agent Systems**

*Last Updated: October 2024 | Version 5.0.0*
