# 🚀 Multi-Agent Content Marketing Platform

**AI-Powered Content Generation, SEO Analysis & Marketing Automation**

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-18+-black.svg)](https://nextjs.org/)
[![License](https://img.shields.io/badge/License-FYP-yellow.svg)](LICENSE)

---

## 📋 Table of Contents

- [Overview](#-overview)
- [Features](#-features)
- [System Architecture](#️-system-architecture)
- [Installation](#️-installation)
- [Configuration](#-configuration)
- [Quick Start](#-quick-start)
- [Usage Guide](#-usage-guide)
- [API Reference](#-api-reference)
- [Agent Documentation](#-agent-documentation)
- [Project Structure](#-project-structure)
- [Technologies](#️-technologies)
- [Contributing](#-contributing)

---

## 📋 Overview

The **Multi-Agent Content Marketing Platform** is an advanced, AI-powered system that automates content creation, SEO analysis, competitor research, and social media marketing. Built with a microservices architecture, it uses multiple specialized agents working together to deliver comprehensive marketing solutions.

The platform leverages cutting-edge technologies including Large Language Models (LLMs), Multi-Agent Bayesian Optimization (MABO), reinforcement learning, and intelligent routing to optimize content generation workflows and maximize marketing ROI.

### Key Highlights

- 🤖 **Multi-Agent System:** Specialized agents for different marketing tasks
- 🧠 **AI-Powered:** Uses Groq LLM (Moonshot AI) for intelligent content generation
- 📊 **MABO Framework:** Multi-Agent Bayesian Optimization for workflow optimization
- 🔍 **SEO Analysis:** Comprehensive SEO auditing and keyword research
- 📱 **Social Media:** Automated content creation for multiple platforms
- 📈 **Analytics:** Real-time metrics collection and performance monitoring
- 🔐 **Secure:** JWT-based authentication and session management

---

## ✨ Features

### 📝 Blog Generation
Generate SEO-optimized blog posts with premium HTML design, including reading progress bars, table of contents, dark mode, and advanced animations.

### 🔍 SEO Analysis
Comprehensive SEO auditing with keyword analysis, competitor research, and actionable recommendations.

### 📱 Social Media
Create engaging social media content for Twitter, Instagram, Reddit, and more with platform-specific optimization.

### 🎯 Competitor Analysis
Identify content gaps, analyze competitor strategies, and discover new opportunities.

### 🧠 Intelligent Routing
AI-powered intent recognition routes user queries to the appropriate agents automatically.

### 📊 Performance Metrics
Track content performance, engagement rates, and ROI with comprehensive analytics.

### 💰 Budget Optimization
MABO framework optimizes budget allocation across campaigns using Bayesian optimization.

### 🔄 Workflow Automation
Automated workflows for content creation, approval, and publishing with background job processing.

---

## 🏗️ System Architecture

### Layered Architecture

```
┌─────────────────────────────────────────────────────────────┐
│              PRESENTATION LAYER                              │
│  • Frontend (Next.js)  • HTML Dashboards  • API Endpoints   │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│              ORCHESTRATION LAYER                             │
│  ┌────────────────────────────────────────────────────┐    │
│  │         Orchestrator (FastAPI :8004)                │    │
│  │  • JWT Auth  • Session Mgmt  • Intent Routing       │    │
│  │  • MABO Agent  • Workflow Orchestration            │    │
│  └──────┬──────────┬──────────┬──────────┬────────────┘    │
└─────────┼──────────┼──────────┼──────────┼─────────────────┘
          │          │          │          │
┌─────────▼──────────▼──────────▼──────────▼─────────────────┐
│                    AGENT LAYER                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │  Web     │  │ Keyword │  │Competitor│  │ Content  │   │
│  │ Crawler  │  │Extractor│  │   Gap    │  │  Agent   │   │
│  │  :8000   │  │  :8001  │  │  :8002  │  │  :8003  │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │   SEO    │  │  Reddit  │  │ Metrics  │  │  MABO    │   │
│  │  Agent   │  │  Agent   │  │Collector │  │ Framework│   │
│  │  :5000   │  │  :8010  │  │(Internal)│  │(Internal)│   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                    DATA LAYER                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   SQLite DB  │  │  Cache Layer │  │  File System │      │
│  │  • Users     │  │  • API Cache │  │  • Images    │      │
│  │  • Sessions  │  │  • Responses │  │  • Previews │      │
│  │  • Content   │  │              │  │  • Reports   │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

### Communication Patterns

- **Job-Based:** Agents communicate via job IDs for async operations
- **Direct API Calls:** Synchronous requests for immediate responses
- **Event-Driven:** Background tasks and scheduled jobs

---

## ⚙️ Installation

### Prerequisites

- Python 3.8+
- Node.js 18+ (for frontend)
- SQLite (included with Python)
- API Keys (see Configuration section)

### Step 1: Clone Repository

```bash
git clone <repository-url>
cd FYP
```

### Step 2: Install Python Dependencies

```bash
pip install -r requirements.txt
```

Or use the automated installer:

```bash
python install_dependencies.py
```

### Step 3: Install Frontend Dependencies

```bash
cd frontend
npm install
# or
pnpm install
```

### Step 4: Configure Environment

Create a `.env` file in the root directory (see Configuration section).

### Step 5: Initialize Database

```bash
python -c "import database; database.initialize_database()"
```

---

## 🔧 Configuration

### Environment Variables

Create a `.env` file with the following variables:

| Variable | Description | Required |
|----------|-------------|----------|
| `GROQ_API_KEY` | Groq API key for LLM (Moonshot AI) | ✅ Yes |
| `SERPAPI_API_KEY` | SerpAPI key for search results | ✅ Yes |
| `RUNWAY_API_KEY` | Runway API for image generation | ⚠️ Optional |
| `TWITTER_API_KEY` | Twitter API credentials | ⚠️ Optional |
| `TWITTER_API_SECRET` | Twitter API secret | ⚠️ Optional |
| `TWITTER_ACCESS_TOKEN` | Twitter access token | ⚠️ Optional |
| `TWITTER_ACCESS_TOKEN_SECRET` | Twitter access token secret | ⚠️ Optional |
| `INSTAGRAM_USERNAME` | Instagram account username | ⚠️ Optional |
| `INSTAGRAM_PASSWORD` | Instagram account password | ⚠️ Optional |
| `AWS_ACCESS_KEY_ID` | AWS S3 access key | ⚠️ Optional |
| `AWS_SECRET_ACCESS_KEY` | AWS S3 secret key | ⚠️ Optional |
| `AWS_S3_BUCKET_NAME` | S3 bucket name | ⚠️ Optional |
| `JWT_SECRET` | Secret key for JWT tokens | ✅ Yes |

### Example .env File

```env
# Required
GROQ_API_KEY=your_groq_api_key_here
SERPAPI_API_KEY=your_serpapi_key_here
JWT_SECRET=your_jwt_secret_here

# Optional
RUNWAY_API_KEY=your_runway_key_here
TWITTER_API_KEY=your_twitter_key_here
TWITTER_API_SECRET=your_twitter_secret_here
TWITTER_ACCESS_TOKEN=your_twitter_access_token
TWITTER_ACCESS_TOKEN_SECRET=your_twitter_access_token_secret
INSTAGRAM_USERNAME=your_instagram_username
INSTAGRAM_PASSWORD=your_instagram_password
AWS_ACCESS_KEY_ID=your_aws_key
AWS_SECRET_ACCESS_KEY=your_aws_secret
AWS_S3_BUCKET_NAME=your_bucket_name
```

---

## 🚀 Quick Start

### Starting All Services

Use the automated startup script:

**Windows:**
```bash
start_all_services.bat
```

**Linux/Mac:**
```bash
python start_all_services.py
```

### Starting Services Individually

```bash
# Terminal 1: Web Crawler
python webcrawler.py

# Terminal 2: Keyword Extractor
python keywordExtraction.py

# Terminal 3: Gap Analyzer
python CompetitorGapAnalyzerAgent.py

# Terminal 4: Content Agent
python content_agent.py

# Terminal 5: SEO Agent
python seo_agent.py

# Terminal 6: Reddit Agent
python reddit_agent.py

# Terminal 7: Orchestrator
python orchestrator.py
```

### Accessing the Platform

- **Orchestrator API:** http://localhost:8004
- **Frontend:** http://localhost:3000 (if running Next.js)
- **API Docs:** http://localhost:8004/docs (Swagger UI)

### First Steps

1. Sign up for an account via `POST /auth/signup`
2. Login to get JWT token via `POST /auth/login`
3. Start a chat session via `POST /chat`
4. Try: "Generate a blog post about AI trends"

---

## 📖 Usage Guide

### 1. Authentication

**Sign Up:**
```bash
curl -X POST http://localhost:8004/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "SecurePass123"}'
```

**Login:**
```bash
curl -X POST http://localhost:8004/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "SecurePass123"}'
```

**Response:**
```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "user_id": 1,
  "email": "user@example.com",
  "expires_at": "2024-12-20T12:00:00"
}
```

### 2. Chat Interface

**Start a conversation:**
```bash
curl -X POST http://localhost:8004/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{
    "message": "Generate a blog post about sustainable technology",
    "session_id": null
  }'
```

### 3. Content Approval

**Approve generated content:**
```bash
curl -X POST http://localhost:8004/content/{content_id}/approve \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"approved": true}'
```

---

## 📡 API Reference

### Authentication Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/auth/signup` | Register new user |
| `POST` | `/auth/login` | User login |
| `GET` | `/auth/me` | Get current user info |

### Chat & Content Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/chat` | Main chat interface |
| `GET` | `/sessions` | List user sessions |
| `POST` | `/content/{id}/approve` | Approve content |
| `GET` | `/content/{id}/preview` | Preview content |

### Metrics & Analytics

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/metrics/dashboard` | Get analytics dashboard |
| `GET` | `/mabo/stats` | Get MABO optimization stats |
| `POST` | `/mabo/batch-update` | Trigger MABO batch update |

**Full API Documentation:** Visit http://localhost:8004/docs for interactive Swagger UI.

---

## 🤖 Agent Documentation

### Agent Ports & Services

| Agent | Port | File | Purpose |
|-------|------|------|---------|
| **Web Crawler** | `8000` | `webcrawler.py` | Website content extraction |
| **Keyword Extractor** | `8001` | `keywordExtraction.py` | SEO keyword extraction |
| **Gap Analyzer** | `8002` | `CompetitorGapAnalyzerAgent.py` | Competitor analysis |
| **Content Agent** | `8003` | `content_agent.py` | Blog & social content generation |
| **SEO Agent** | `5000` | `seo_agent.py` | SEO analysis & reporting |
| **Reddit Agent** | `8010` | `reddit_agent.py` | Reddit content & engagement |
| **Orchestrator** | `8004` | `orchestrator.py` | Main coordination service |

### Key Components

- **MABO Framework:** Multi-Agent Bayesian Optimization for workflow optimization
- **Intelligent Router:** AI-powered intent recognition and routing
- **Performance Monitor:** Real-time metrics collection and analysis
- **Budget Allocator:** Optimized budget distribution across campaigns
- **Feedback Analyzer:** Learning from content performance

### Individual Agent Endpoints

#### Web Crawler (Port 8000)

- `POST /crawl` - Start crawl job
- `GET /status/{job_id}` - Check status
- `GET /download/{job_id}` - Download JSON
- `GET /download/docx/{job_id}` - Download DOCX

#### Keyword Extractor (Port 8001)

- `POST /extract-keywords` - Extract keywords
- `GET /status/{job_id}` - Check status
- `GET /download/{job_id}` - Download results

#### Gap Analyzer (Port 8002)

- `POST /analyze-keyword-gap` - Start analysis
- `GET /status/{job_id}` - Check status
- `GET /download/json/{job_id}` - Download analysis

#### Content Agent (Port 8003)

- `POST /generate-blog` - Generate blog post
- `POST /generate-social` - Generate social media content
- `POST /analyze-content` - Analyze existing content
- `GET /status/{job_id}` - Check job status
- `GET /download/html/{job_id}` - Download blog HTML

#### Reddit Agent (Port 8010)

- `POST /extract-keywords` - Extract Reddit keywords
- `POST /search-subreddits` - Search relevant subreddits
- `POST /generate-post` - Generate Reddit post
- `POST /post` - Post to Reddit (optional)

For detailed agent documentation, see the `docs/` directory.

---

## 📁 Project Structure

```
FYP/
├── agents/                    # Agent microservices
│   ├── webcrawler.py         # Web crawling service
│   ├── keywordExtraction.py  # Keyword extraction
│   ├── CompetitorGapAnalyzerAgent.py  # Competitor analysis
│   ├── content_agent.py      # Content generation
│   ├── seo_agent.py          # SEO analysis
│   └── reddit_agent.py       # Reddit integration
│
├── core/                      # Core framework
│   ├── orchestrator.py       # Main orchestrator
│   ├── mabo_framework.py     # MABO optimization
│   ├── mabo_agent.py         # MABO agent
│   ├── intelligent_router.py # Intent routing
│   ├── database.py           # Database layer
│   ├── auth.py               # Authentication
│   ├── cost_model.py         # Cost estimation
│   └── scheduler.py          # Job scheduling
│
├── frontend/                  # Next.js frontend
│   ├── app/                  # App router pages
│   ├── components/           # React components
│   └── lib/                  # Utilities
│
├── docs/                     # Documentation
│   ├── README.md            # Main docs index
│   ├── AGENT_ARCHITECTURE.md # Architecture guide
│   └── [agent]_README.md    # Individual agent docs
│
├── database/                 # SQLite database
├── cache/                    # API response cache
├── generated_images/         # Generated images
├── previews/                 # Content previews
├── reports/                  # SEO reports
│
├── requirements.txt          # Python dependencies
├── .env                      # Environment variables
├── README.md                 # This file
└── README.html              # HTML version (for local viewing)
```

---

## 🛠️ Technologies

### Backend

- **FastAPI:** Modern Python web framework
- **Groq:** LLM API (Moonshot AI - Kimi K2)
- **SQLite:** Lightweight database
- **JWT:** Authentication tokens
- **APScheduler:** Background job scheduling
- **Pydantic:** Data validation
- **Tenacity:** Retry logic

### AI & ML

- **MABO Framework:** Multi-Agent Bayesian Optimization
- **Reinforcement Learning:** Workflow optimization
- **LLM:** Moonshot AI (Kimi K2) for content generation
- **Scipy:** Scientific computing for optimization

### Frontend

- **Next.js:** React framework
- **TypeScript:** Type-safe JavaScript
- **Tailwind CSS:** Utility-first CSS

### External Services

- **SerpAPI:** Search engine results
- **Runway:** Image generation
- **AWS S3:** Cloud storage
- **Twitter API:** Social media posting
- **Instagram API:** Social media posting

---

## 🤝 Contributing

Contributions are welcome! Please follow these guidelines:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Code Style

- Follow PEP 8 for Python code
- Use type hints where possible
- Write docstrings for functions and classes
- Add comments for complex logic

---

## 📄 License

This project is part of a Final Year Project (FYP). Please refer to your institution's guidelines for usage and distribution.

---

## 💬 Support

For issues, questions, or contributions:

- Check the `docs/` directory for detailed documentation
- Review agent-specific README files
- Check API documentation at `/docs` endpoint

---

## 🎯 Roadmap

- [ ] Enhanced MABO optimization algorithms
- [ ] Additional social media platform support
- [ ] Real-time collaboration features
- [ ] Advanced analytics dashboard
- [ ] Multi-language content generation
- [ ] API rate limiting and caching improvements

---

**Built with ❤️ for FYP**

*Powered by FastAPI, Next.js, and AI*

---
**Embeddings & Memory — Execution & Output**

- **What was added:** a lightweight embedding helper and a CLI to populate the vector store from local artifacts:
  - Helper: `tools/embedding.py` — wrappers for `sentence-transformers` models (text + image).
  - CLI: `scripts/populate_chroma.py` — scans `previews/` (HTML) and `generated_images/` and writes embeddings to Chroma (if available) and a SQLite `campaign_memory` table.

- **Install prerequisites:**
  - Add to environment: `pip install -r requirements.txt` and `pip install chromadb sentence-transformers`.

- **Run (safe dry-run):**
  - `python scripts/populate_chroma.py --dry-run`
  - Output: lists found preview HTML files and images; does NOT download models or write to the vector store.

- **Run (populate):**
  - `python scripts/populate_chroma.py`
  - Behavior: loads `sentence-transformers` models, computes embeddings, writes vectors to Chroma collections `campaign_text` and `campaign_visual` (if Chroma available), and inserts/updates rows in the SQLite `campaign_memory` table.

- **SQLite storage (`campaign_memory` table):** each row contains: `campaign_id`, `visual_vector` (JSON array or `{"chroma_id":...}`), `text_vector` (JSON array or `{"chroma_id":...}`), `visual_model`, `text_model`, `context_metadata`, `performance_node`, `alignment_score`, `dedup_info`, `tags`, `source`, and `created_at`.

- **Vector store (Chroma):** when available, vectors are stored in collections named `campaign_text` and `campaign_visual`. Metadata contains `campaign_id` for easy lookup. The code gracefully falls back to storing vectors inline in SQLite when Chroma is not available.

- **TeleMem dedup output:** calling `telemem.deduplicate()` returns a summary JSON with keys: `clusters`, `merged_clusters`, and `merged_details` where each detail contains `telemem_id`, `representative_campaign_id`, `merged_campaigns`, and `merge_score`.

- **Planner output (`CampaignPlannerAgent.generate_proposals()`):** returns a 3-tier `proposals` list (budget, balanced, premium). Each proposal includes: `tier`, `budget`, `expected_cost`, `expected_reward`, `expected_ctr`, `creative` (text, `image_prompt`, `image_model`), `schedule` (start/end/recommended_windows), `low_noise_windows`, and `pivot_trigger` flag.

- **Where to look for artifacts after running:**
  - Vector store: local Chroma directory or Chroma server (depends on your config).
  - DB records: `database/app.db`, table `campaign_memory`.
  - Preview/generated files used as inputs: `previews/` and `generated_images/`.

If you'd like, I can add a short `README` for `scripts/` that includes sample runs, or implement a one-shot command to populate only new files since the last run. Tell me which you'd prefer.

