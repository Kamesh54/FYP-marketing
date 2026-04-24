"""
Orchestrator Agent v5.0 - Multi-Agent ChatGPT-like Platform
Intelligent routing, authentication, session management, RL optimization
"""
import os
import uuid
import json
import time
import logging
import re
import subprocess
import math
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse

import requests
import boto3
from botocore.exceptions import NoCredentialsError, ClientError
from fastapi import FastAPI, HTTPException, UploadFile, File, Header, BackgroundTasks, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse, StreamingResponse as _SSEResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential
from groq import Groq
from contextlib import asynccontextmanager
import tweepy
try:
    from instagrapi import Client as InstaClient
    INSTAGRAPI_AVAILABLE = True
except (ImportError, TypeError) as e:
    # Python 3.9 compatibility - instagrapi requires 3.10+
    INSTAGRAPI_AVAILABLE = False
    InstaClient = None
from fastapi.middleware.cors import CORSMiddleware

# Optional: LangSmith tracing
try:
    from langsmith import traceable
except ImportError:
    # If langsmith not installed, create a no-op decorator
    def traceable(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

from langsmith_tracer import (
    trace_workflow, trace_llm, trace_agent,
    get_current_run_id, record_feedback, record_critic_feedback,
    tracer_status,
)
from trace_manager import get_trace_manager
from llm_failover import groq_chat_with_failover

# Import new modules
import auth
import database as db
try:
    import intelligent_router as router
    ROUTER_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Intelligent router not available: {e}")
    ROUTER_AVAILABLE = False
    # Create a mock router for basic functionality
    class MockRouter:
        async def route_user_query(self, message, history):
            return {"intent": "general_query", "confidence": 0.5}
        async def generate_conversational_response(self, message, history):
            return "I'm sorry, but the intelligent routing system is currently unavailable."
        async def extract_url_from_message(self, message):
            return None
    router = MockRouter()
import cost_model
import memory  # Added for memory persistence
# import rl_agent  # Deprecated - replaced with MABO
import mabo_agent
import mabo_agent
from scheduler import start_scheduler, get_scheduler_status

# Optional: Graph modules for knowledge graph integration (requires neo4j package)
# Commented out if neo4j is not installed
# try:
#     from graph import initialize_graph_db, close_graph_db, get_graph_queries, is_graph_db_available
#     from graph_routes import create_graph_routes
#     GRAPH_AVAILABLE = True
# except Exception as e:
#     GRAPH_AVAILABLE = False
#     create_graph_routes = None

# Setup logging FIRST before using logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

GRAPH_AVAILABLE = False
create_graph_routes = None

from metrics_collector import get_aggregated_metrics, collect_metrics_for_post, MetricsCollector
from campaign_planner import CampaignPlannerAgent
from campaign_agent import (
    ScheduleRequest as CampaignScheduleRequest,
    PostRequest as CampaignPostRequest,
    get_brands as campaign_get_brands,
    create_schedule as campaign_create_schedule,
    list_schedules as campaign_list_schedules,
    delete_schedule as campaign_delete_schedule,
    post_now as campaign_post_now,
    post_status as campaign_post_status,
    list_posts as campaign_list_posts,
    startup as campaign_runtime_startup,
    shutdown as campaign_runtime_shutdown,
)


# --- Configuration & Setup ---
load_dotenv()

# ── LangGraph Integration ────────────────────────────────────────────────────
USE_LANGGRAPH = True # Forced to True to bypass dotenv caching in long-running uvicorn
if USE_LANGGRAPH:
    try:
        from langgraph_graph import run_marketing_graph, get_marketing_graph
        # Pre-compile graph on import so first request is fast
        _lg = get_marketing_graph()
        logger.info("LangGraph mode ENABLED – graph compiled successfully")
        LANGGRAPH_AVAILABLE = True
    except Exception as _lg_err:
        logger.warning(f"LangGraph import failed, falling back to HTTP: {_lg_err}")
        LANGGRAPH_AVAILABLE = False
        USE_LANGGRAPH = False
else:
    LANGGRAPH_AVAILABLE = False
    logger.info("LangGraph mode DISABLED – using HTTP microservices")

# --- API Keys & Endpoints ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
RUNWAY_API_KEY = os.getenv("RUNWAY_API_KEY")
TWITTER_API_KEY = os.getenv("TWITTER_API_KEY")
TWITTER_API_SECRET = os.getenv("TWITTER_API_SECRET")
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_TOKEN_SECRET = os.getenv("TWITTER_ACCESS_TOKEN_SECRET")
INSTAGRAM_USERNAME = os.getenv("INSTAGRAM_USERNAME")
INSTAGRAM_PASSWORD = os.getenv("INSTAGRAM_PASSWORD")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_S3_BUCKET_NAME = os.getenv("AWS_S3_BUCKET_NAME")

# --- LANGGRAPH MIGRATION NOTICE ---
# All microservices have been consolidated into LangGraph orchestrator.
# HTTP calls to separate services are DEPRECATED.
# See agent_adapters.py for direct agent invocation (no HTTP).
# LangGraph handles all orchestration internally.

# --- Legacy Microservice Base URLs (DEPRECATED - DO NOT USE) ---
# CRAWLER_BASE           = "http://127.0.0.1:8000"
# KEYWORD_EXTRACTOR_BASE = "http://127.0.0.1:8001"
# GAP_ANALYZER_BASE      = "http://127.0.0.1:8002"
# CONTENT_AGENT_BASE     = "http://127.0.0.1:8003"
# IMAGE_AGENT_BASE       = "http://127.0.0.1:8005"
# BRAND_AGENT_BASE       = "http://127.0.0.1:8006"
# CRITIC_AGENT_BASE      = "http://127.0.0.1:8007"
# CAMPAIGN_AGENT_BASE    = "http://127.0.0.1:8008"
# REDDIT_AGENT_BASE      = "http://127.0.0.1:8010"


def _call_reddit_research(keywords: list, brand_name: str, max_subreddits: int = 3) -> dict:
    """Call Reddit research agent synchronously; returns insights dict or {} on failure."""
    try:
        r = requests.post(
            f"{REDDIT_AGENT_BASE}/research",
            json={
                "keywords": keywords[:8],
                "brand_name": brand_name,
                "max_subreddits": max_subreddits,
                "posts_per_sub": 6
            },
            timeout=45,
        )
        if r.status_code == 200:
            data = r.json()
            if data.get("available"):
                insights = data.get("insights", {})
                logger.info(
                    f"Reddit research: {len(insights.get('trending_topics', []))} trends, "
                    f"{len(insights.get('competitor_mentions', []))} competitors, "
                    f"{data.get('post_count', 0)} posts analysed"
                )
                return insights
    except Exception as e:
        logger.warning(f"Reddit research failed (non-fatal): {e}")
    return {}


def _call_critic_sync(content_id: str, content_text: str, content_type: str,
                     brand_name: str, original_intent: str) -> dict:
    """Call the critic agent and return a score dict; returns {} silently on failure."""
    import requests as _req
    try:
        resp = _req.post(
            f"{CRITIC_AGENT_BASE}/critique",
            json={
                "content_id": content_id,
                "content_text": content_text[:1000],
                "content_type": content_type,
                "brand_name": brand_name,
                "original_intent": original_intent,
                "session_id": "orchestrator-auto",
            },
            timeout=25,
        )
        if resp.status_code == 200:
            d = resp.json()
            return {
                "overall": round(d.get("overall_score", 0), 3),
                "intent": round(d.get("intent_score", 0), 2),
                "brand": round(d.get("brand_score", 0), 2),
                "quality": round(d.get("quality_score", 0), 2),
                "passed": bool(d.get("passed", False)),
                "text": d.get("critique_text", "")[:200],
            }
    except Exception as _critic_err:
        logger.warning(f"Critic auto-call failed for {content_id}: {_critic_err}")
    return {}
RESEARCH_AGENT_BASE    = "http://127.0.0.1:8009"

# --- Initialize Clients ---
groq_client = Groq(api_key=GROQ_API_KEY)
s3_client = boto3.client('s3', aws_access_key_id=AWS_ACCESS_KEY_ID, aws_secret_access_key=AWS_SECRET_ACCESS_KEY) if AWS_ACCESS_KEY_ID else None

# Initialize Instagram Client (requires Python 3.10+)
insta_client = None
if INSTAGRAPI_AVAILABLE and InstaClient:
    try:
        insta_client = InstaClient()
        if INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD:
            try:
                insta_client.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
                logger.info("Instagram client logged in successfully")
            except Exception as e:
                logger.warning(f"Instagram login failed: {e}")
                insta_client = None
    except Exception as e:
        logger.warning(f"Instagram client initialization failed: {e}")
        insta_client = None
else:
    logger.info("Instagram client not available (requires Python 3.10+)")

planner_agent = CampaignPlannerAgent()

# --- Lifespan Context Manager ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events."""
    # Startup
    logger.info("Starting Orchestrator v5.0...")
    try:
        db.initialize_database()
        start_scheduler()
        # Start embedded campaign runtime so /campaigns UI can use orchestrator only.
        await campaign_runtime_startup()
        
        # Initialize graph database
        if GRAPH_AVAILABLE:
            try:
                initialize_graph_db()
                logger.info("Graph database initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize graph database: {e}")
        
        logger.info("Orchestrator started successfully")
    except Exception as e:
        logger.error(f"Startup error: {e}")
    
    yield  # Application runs
    
    # Shutdown
    logger.info("Orchestrator shutting down...")
    try:
        await campaign_runtime_shutdown()
    except Exception as e:
        logger.warning(f"Campaign runtime shutdown warning: {e}")
    if GRAPH_AVAILABLE:
        try:
            close_graph_db()
            logger.info("Graph database closed")
        except Exception as e:
            logger.warning(f"Error closing graph database: {e}")

# --- App Setup ---
app = FastAPI(title="Orchestrator Agent", version="5.0.0", lifespan=lifespan)
origins = ["*"]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
os.makedirs("reports", exist_ok=True)
os.makedirs("uploads", exist_ok=True)
os.makedirs("generated_images", exist_ok=True)
os.makedirs("previews", exist_ok=True)

# In-memory store for sessions awaiting platform choice (social posts)
# Structure: {session_id: {"original_message": str, "timestamp": float}}
_pending_platform: dict = {}


def _detect_platform_from_text(text: str) -> Optional[str]:
    """Return 'twitter' or 'instagram' if the text mentions one, else None."""
    t = text.lower()
    if any(k in t for k in ["twitter", " x ", "tweet", "x post", "on x"]):
        return "twitter"
    if any(k in t for k in ["instagram", "insta", " ig ", "ig post", "on ig"]):
        return "instagram"
    return None


def _is_blog_instagram_combo_request(text: str) -> bool:
    """Detect requests that explicitly ask for both a blog and an Instagram post."""
    if not text:
        return False

    lower = text.lower()
    blog_markers = ["blog", "blog post", "article", "seo blog"]
    instagram_markers = ["instagram", "insta", "ig post", "instagram post"]
    combo_markers = ["both", "together", "along with", "and", "also"]

    has_blog = any(marker in lower for marker in blog_markers)
    has_instagram = any(marker in lower for marker in instagram_markers)
    has_combo = any(marker in lower for marker in combo_markers)

    return has_blog and has_instagram and has_combo


# Attach graph routes for knowledge graph insights
if GRAPH_AVAILABLE and create_graph_routes:
    try:
        create_graph_routes(app, auth, db)
        logger.info("Graph insight routes attached successfully")
    except Exception as e:
        logger.warning(f"Failed to attach graph routes: {e}")

# ==================== PYDANTIC MODELS ====================

class SignupRequest(BaseModel):
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class AuthResponse(BaseModel):
    token: str
    user_id: int
    email: str
    expires_at: str
    credits_balance: int

class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str
    active_brand: Optional[str] = None  # Brand name to use for this request
    platform: Optional[str] = None  # Platform for social posts
    intent: Optional[str] = None  # Optional intent override for trusted callers

class ChatResponse(BaseModel):
    session_id: str
    response: str
    formatted_response: Optional[str] = None
    intent: Optional[str] = None
    content_preview_id: Optional[str] = None
    workflow_cost: Optional[Dict] = None
    credits_charged: Optional[int] = None
    credits_balance: Optional[int] = None
    response_options: Optional[List[Dict[str, Any]]] = None
    clarification_request: Optional[Dict[str, Any]] = None
    seo_result: Optional[Dict[str, Any]] = None

class SessionResponse(BaseModel):
    id: str
    title: str
    created_at: str
    last_active: str

class ContentApprovalRequest(BaseModel):
    approved: bool
    platform: Optional[str] = None  # For social posts

class WorkflowSelectionRequest(BaseModel):
    session_id: str
    option_id: str

class CampaignSelectionRequest(BaseModel):
    session_id: str
    campaign_id: str
    tier: str
    theme: str
    duration_days: int

# â”€â”€ New models for HITL and workflow orchestration â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class HitlRespondRequest(BaseModel):
    decision: str               # approved | rejected | edited
    edited_content: Optional[str] = None

class WorkflowRunRequest(BaseModel):
    intent: str
    message: str
    session_id: Optional[str] = None
    brand_name: Optional[str] = None
    params: Optional[Dict[str, Any]] = {}

class SocialFeedbackRequest(BaseModel):
    content_id: str
    platform: str
    reward: float               # 0.0â€“1.0

class PromptEvolveRequest(BaseModel):
    agent_name: str
    context_type: str
    feedback: str
    current_score: float = 0.5


def _estimate_chat_credit_cost(intent: str, extracted_params: Optional[Dict[str, Any]] = None) -> int:
    """Estimate the credit cost for a chat request before execution."""
    extracted_params = extracted_params or {}

    if intent == "blog_instagram_combo":
        agents = [
            "keyword_extractor",
            "content_agent_blog",
            "content_agent_social",
            "image_generator",
            "critic_agent",
        ]
    elif intent == "general_chat":
        return 1
    else:
        workflow_plan = router.get_workflow_plan(intent, extracted_params) if hasattr(router, "get_workflow_plan") else None
        agents = workflow_plan.agents if workflow_plan else []

    if not agents:
        return 1

    estimate = cost_model.estimate_workflow_cost(agents)
    return int(estimate.get("credits_estimate") or cost_model.usd_cost_to_credits(estimate.get("total_cost", 0)))

@app.post("/auth/signup", response_model=AuthResponse)
async def signup(req: SignupRequest):
    """Create new user account."""
    try:
        # Validate email
        if not auth.validate_email(req.email):
            raise HTTPException(status_code=400, detail="Invalid email format")
        
        # Validate password strength
        is_valid, message = auth.validate_password_strength(req.password)
        if not is_valid:
            raise HTTPException(status_code=400, detail=message)
        
        # Check if user already exists
        existing_user = db.get_user_by_email(req.email)
        if existing_user:
            raise HTTPException(status_code=400, detail="Email already registered")
        
        # Create user
        password_hash = auth.hash_password(req.password)
        user_id = db.create_user(req.email, password_hash)
        
        # Generate JWT
        token_data = auth.generate_jwt(user_id, req.email)
        token_data["credits_balance"] = db.get_user_credit_balance(user_id)
        
        logger.info(f"New user created: {req.email} (ID: {user_id})")
        return AuthResponse(**token_data)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Signup error: {e}")
        raise HTTPException(status_code=500, detail="Signup failed")

@app.post("/auth/login", response_model=AuthResponse)
async def login(req: LoginRequest):
    """Login existing user."""
    try:
        # Get user by email
        user = db.get_user_by_email(req.email)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        # Verify password
        if not auth.verify_password(req.password, user['password_hash']):
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        # Update last login
        db.update_last_login(user['id'])
        
        # Generate JWT
        token_data = auth.generate_jwt(user['id'], user['email'])
        token_data["credits_balance"] = int(user.get("credits_balance", 0) or 0)
        
        logger.info(f"User logged in: {req.email}")
        return AuthResponse(**token_data)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=500, detail="Login failed")

@app.get("/auth/me")
async def get_current_user_info(authorization: str = Header(None)):
    """Get current user information from token."""
    try:
        payload = auth.get_current_user(authorization)
        user = db.get_user_by_id(payload['user_id'])
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        return {
            "user_id": user['id'],
            "email": user['email'],
            "created_at": user['created_at'],
            "last_login": user['last_login'],
            "credits_balance": int(user.get("credits_balance", 0) or 0),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get user info error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get user info")

# ==================== SESSION ENDPOINTS ====================

@app.get("/sessions")
async def get_sessions(authorization: str = Header(None), limit: int = 50, offset: int = 0):
    """Get all sessions for current user."""
    try:
        payload = auth.get_current_user(authorization)
        user_id = payload['user_id']
        
        sessions = db.get_user_sessions(user_id, limit, offset)
        
        return {
            "sessions": [
                {
                    "id": s['id'],
                    "title": s['title'],
                    "created_at": s['created_at'],
                    "last_active": s['last_active']
                }
                for s in sessions
            ]
        }
    except Exception as e:
        logger.error(f"Get sessions error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get sessions")

@app.post("/sessions/new")
async def create_new_session(authorization: str = Header(None)):
    """Create a new chat session."""
    try:
        payload = auth.get_current_user(authorization)
        user_id = payload['user_id']
        
        session_id = f"sess_{uuid.uuid4().hex[:12]}"
        db.create_session(session_id, user_id, "New Chat")
        
        return {"session_id": session_id, "title": "New Chat"}
    except Exception as e:
        logger.error(f"Create session error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create session")

@app.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str, authorization: str = Header(None)):
    """Get all messages for a session."""
    try:
        payload = auth.get_current_user(authorization)
        user_id = payload['user_id']
        
        # Verify session belongs to user
        session = db.get_session(session_id, user_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        messages = db.get_session_messages(session_id)
        
        return {
            "session_id": session_id,
            "messages": [
                {
                    "role": m['role'],
                    "content": m['content'],
                    "formatted_content": m['formatted_content'],
                    "timestamp": m['timestamp']
                }
                for m in messages
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get messages error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get messages")

@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str, authorization: str = Header(None)):
    """Delete a session."""
    try:
        payload = auth.get_current_user(authorization)
        user_id = payload['user_id']
        
        db.delete_session(session_id, user_id)
        return {"message": "Session deleted successfully"}
    except Exception as e:
        logger.error(f"Delete session error: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete session")

@app.patch("/sessions/{session_id}")
async def update_session(session_id: str, title: str, authorization: str = Header(None)):
    """Update session title."""
    try:
        payload = auth.get_current_user(authorization)
        user_id = payload['user_id']
        
        # Verify session belongs to user
        session = db.get_session(session_id, user_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        db.update_session_title(session_id, title)
        return {"message": "Session updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update session error: {e}")
        raise HTTPException(status_code=500, detail="Failed to update session")

@app.post("/campaigns/select")
async def select_campaign_tier(req: CampaignSelectionRequest, authorization: str = Header(None)):
    """Handle campaign tier selection."""
    try:
        payload = auth.get_current_user(authorization)
        user_id = payload['user_id']
        
        # Create campaign ID
        campaign_id = f"camp_{uuid.uuid4().hex[:8]}"
        
        # Create campaign in DB
        db.create_campaign(
            campaign_id=campaign_id,
            user_id=user_id,
            name=f"{req.theme} Campaign",
            start_date=(datetime.now() + timedelta(days=1)).isoformat(),
            end_date=(datetime.now() + timedelta(days=req.duration_days + 1)).isoformat(),
            budget_tier=req.tier,
            strategy=req.tier  # Using tier as strategy name for now
        )
        
        # Generate agenda
        agenda = planner_agent.generate_campaign_agenda(req.theme, req.duration_days, req.tier)
        
        # Save agenda to DB
        for item in agenda:
            db.add_campaign_agenda_item(
                campaign_id=campaign_id,
                scheduled_time=item["scheduled_time"],
                action=item["action"],
                metadata=item["metadata"]
            )
            
        return {
            "message": f"Campaign '{req.theme}' activated! First action scheduled for tomorrow.",
            "campaign_id": campaign_id,
            "agenda_count": len(agenda)
        }
        
    except Exception as e:
        logger.error(f"Campaign selection error: {e}")
        raise HTTPException(status_code=500, detail="Failed to activate campaign")

# ==================== HELPER FUNCTIONS ====================

def save_file_from_url(url: str, file_path: str) -> str:
    """Download file from URL."""
    try:
        r = requests.get(url, stream=True, timeout=120)
        r.raise_for_status()
        with open(file_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        logger.info(f"File saved to {file_path}")
        return file_path
    except requests.RequestException as e:
        logger.error(f"Failed to download file from {url}: {e}")
        raise

@retry(stop=stop_after_attempt(30), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
def poll_job_status(status_url: str) -> Dict[str, Any]:
    """Poll job status until completed."""
    r = requests.get(status_url, timeout=10)
    r.raise_for_status()
    data = r.json()
    status = data.get("status")
    if status == "completed":
        logger.info(f"Job completed at {status_url}")
        return data
    elif status == "failed":
        logger.error(f"Job failed at {status_url}: {data.get('message')}")
        raise HTTPException(status_code=500, detail=data.get("message"))
    raise Exception(f"Job is still running. Current status: {status}")

@traceable(run_type="chain", name="{name}")
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def call_agent_job(
    name: str,
    url: str,
    payload: Dict,
    download_path_template: str = "/download/json/{job_id}",
    result_format: str = "json",
    session_id: Optional[str] = None
) -> Any:
    """Call an agent microservice and wait for result."""
    start_time = time.time()
    try:
        # Start the job
        start_r = requests.post(url, json=payload, timeout=200)
        start_r.raise_for_status()
        job_id = start_r.json()["job_id"]
        base_url = url.rsplit('/', 1)[0]
        
        # Poll for status
        status_url = f"{base_url}/status/{job_id}"
        poll_job_status(status_url)
        
        # Download result
        download_url = f"{base_url}{download_path_template.format(job_id=job_id)}"
        logger.info(f"Downloading result for job {job_id} from {download_url}")
        download_r = requests.get(download_url, timeout=60)
        download_r.raise_for_status()

        result = download_r.json() if result_format == "json" else download_r.text
        return result
    except Exception as e:
        logger.error(f"Error in {name}: {e}")
        raise

@traceable(run_type="tool", name="ðŸ“Š SEO Agent")
def run_seo_agent(url: str) -> str:
    """Run SEO analysis agent."""
    try:
        result = subprocess.run(["python", "seo_agent.py", url], capture_output=True, text=True, check=True, timeout=120)
        match = re.search(r"(report_.*\.html)", result.stdout)
        if match:
            original_path = match.group(0)
            new_path = f"reports/{os.path.basename(original_path)}"
            if os.path.exists(original_path):
                if os.path.exists(new_path):
                    os.remove(new_path)  # Windows: remove first to allow rename
                os.rename(original_path, new_path)
                logger.info(f"SEO report saved to {new_path}")
            return new_path
        raise Exception("Could not find report filename in SEO agent output.")
    except subprocess.CalledProcessError as e:
        error_output = e.stderr or e.stdout
        logger.error(f"Failed to run SEO agent. Stderr: {e.stderr}\nStdout: {e.stdout}")
        raise Exception(f"SEO Agent failed: {error_output}")

@traceable(run_type="tool", name="ðŸŽ¨ RunwayML Image Gen")
def generate_image_with_runway(prompt: str, reference_images: Optional[List[str]] = None) -> str:
    """Generate image using Runway ML with gen3a_turbo model."""
    if not RUNWAY_API_KEY:
        raise ValueError("RUNWAY_API_KEY not set.")
    headers = {
        "Authorization": f"Bearer {RUNWAY_API_KEY}",
        "Content-Type": "application/json",
        "X-Runway-Version": "2024-11-06"
    }
    # Use gen4_image model
    payload = {
        "model": "gen4_image",
        "promptText": prompt,
        "ratio": "1280:720",
    }
    valid_reference_images = [
        ref for ref in (reference_images or [])
        if isinstance(ref, str) and ref.startswith(("http://", "https://"))
    ]
    if valid_reference_images:
        # Best effort: include uploaded logo/reference images when supported by the API.
        payload["referenceImages"] = [{"uri": ref} for ref in valid_reference_images[:3]]
    try:
        response = requests.post("https://api.dev.runwayml.com/v1/text_to_image", json=payload, headers=headers)
        if response.status_code >= 400 and payload.get("referenceImages"):
            logger.warning(
                f"Runway rejected referenceImages ({response.status_code}); retrying prompt-only generation"
            )
            fallback_payload = dict(payload)
            fallback_payload.pop("referenceImages", None)
            response = requests.post("https://api.dev.runwayml.com/v1/text_to_image", json=fallback_payload, headers=headers)
        response.raise_for_status()
        task_id = response.json().get("id")
        for _ in range(60):
            time.sleep(5)
            status_res = requests.get(f"https://api.dev.runwayml.com/v1/tasks/{task_id}", headers=headers)
            status_res.raise_for_status()
            data = status_res.json()
            if data['status'] == 'SUCCEEDED':
                image_url = data['output'][0]
                # Return Runway URL directly (it's already public with JWT auth, no need to download locally)
                logger.info(f"Image generated successfully: {image_url}")
                return image_url
            elif data['status'] in ['FAILED', 'CANCELLED']:
                raise Exception(f"Runway task failed with status: {data['status']}")
        raise TimeoutError("Runway image generation timed out.")
    except Exception as e:
        logger.error(f"Runway Error: {e}")
        raise

@traceable(run_type="tool", name="Social Poster ({platform})")
def post_to_social(platform: str, text: str, image_path: str) -> str:
    """Post to social media."""
    try:
        # If image_path is a URL, download it first
        local_image_path = image_path
        if image_path and (image_path.startswith('http://') or image_path.startswith('https://')):
            logger.info(f"Downloading image from URL: {image_path}")
            try:
                import uuid
                local_filename = f"generated_images/{uuid.uuid4().hex[:12]}.png"
                os.makedirs("generated_images", exist_ok=True)
                response = requests.get(image_path, timeout=120)
                response.raise_for_status()
                with open(local_filename, 'wb') as f:
                    f.write(response.content)
                local_image_path = local_filename
                logger.info(f"Image downloaded to: {local_image_path}")
            except Exception as e:
                logger.warning(f"Failed to download image from URL: {e}, attempting to post anyway")
                # Continue without image if download fails
                local_image_path = None
        
        if platform == "twitter":
            if not all([TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET]):
                raise ValueError("Twitter credentials not configured")
            auth = tweepy.OAuth1UserHandler(TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET)
            api_v1 = tweepy.API(auth)
            client = tweepy.Client(consumer_key=TWITTER_API_KEY, consumer_secret=TWITTER_API_SECRET, access_token=TWITTER_ACCESS_TOKEN, access_token_secret=TWITTER_ACCESS_TOKEN_SECRET)
            if local_image_path and os.path.exists(local_image_path):
                media = api_v1.media_upload(filename=local_image_path)
                post_result = client.create_tweet(text=text, media_ids=[media.media_id_string])
            else:
                # Post without image if not available
                post_result = client.create_tweet(text=text)
            post_url = f"https://twitter.com/user/status/{post_result.data['id']}"
        elif platform == "instagram":
            # Check if Instagram is available and credentials are set
            if not INSTAGRAPI_AVAILABLE:
                raise ValueError("Instagram posting requires Python 3.10+ and instagrapi package")
            if not INSTAGRAM_USERNAME or not INSTAGRAM_PASSWORD:
                raise ValueError("Instagram credentials not configured")

            # Create a fresh client instance for this post
            temp_insta_client = InstaClient()
            if not os.path.exists("instagram.json"):
                temp_insta_client.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
                temp_insta_client.dump_settings("instagram.json")
            else:
                temp_insta_client.load_settings("instagram.json")
                temp_insta_client.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
            if local_image_path and os.path.exists(local_image_path):
                media = temp_insta_client.photo_upload(path=local_image_path, caption=text)
                post_url = f"https://www.instagram.com/p/{media.code}/"
            else:
                raise ValueError("Image required for Instagram posting")
        return post_url
    except Exception as e:
        logger.error(f"Social Post Error ({platform}): {e}")
        raise

@traceable(run_type="tool", name="â˜ï¸ AWS S3 Hoster")
def host_on_s3(file_path: str, file_name: str, content_type: str = 'text/html') -> str:
    """Host file on AWS S3."""
    if not s3_client or not AWS_S3_BUCKET_NAME:
        raise ValueError("AWS credentials not configured.")
    try:
        s3_client.upload_file(file_path, AWS_S3_BUCKET_NAME, file_name, ExtraArgs={'ContentType': content_type})
        public_url = f"https://{AWS_S3_BUCKET_NAME}.s3.amazonaws.com/{file_name}"
        return public_url
    except (NoCredentialsError, ClientError) as e:
        logger.error(f"S3 Upload Error: {e}")
        raise

def normalize_brand_info(brand_info: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize brand info to have consistent structure whether from DB or fresh extraction."""
    if not brand_info:
        return {
            "brand_name": "My Business",
            "industry": "General",
            "location": None,
            "contacts": None,
            "description": "",
            "target_audience": "",
            "unique_selling_points": [],
            "website": ""
        }

    # Parse metadata JSON if it's a string
    meta = brand_info.get('metadata', {})
    if isinstance(meta, str):
        try:
            meta = json.loads(meta) if meta else {}
        except Exception:
            meta = {}

    _NORM_PLACEHOLDERS = {
        "", "not specified", "not provided", "unknown", "n/a", "na",
        "none", "null", "undefined", "your business", "my business",
        "not available", "no name", "company name", "business name"
    }

    def _clean(val, default=''):
        """Return val unless it's a placeholder, in which case return default."""
        if val and str(val).strip().lower() not in _NORM_PLACEHOLDERS:
            return str(val).strip()
        return default

    # Prefer direct DB columns; fall back to metadata JSON
    def _pick(direct_key, meta_key=None, default=''):
        v = brand_info.get(direct_key)
        cleaned = _clean(v)
        if cleaned:
            return cleaned
        return _clean(meta.get(meta_key or direct_key), default)

    raw_name = brand_info.get('brand_name') or meta.get('brand_name', '')
    brand_name_clean = _clean(raw_name, 'My Business')

    return {
        "brand_name":           brand_name_clean,
        "location":             _clean(brand_info.get('location')) or _clean(meta.get('location')) or None,
        "contacts":             _clean(brand_info.get('contacts')) or _clean(meta.get('contacts')) or None,
        "industry":             _pick('industry', default='General'),
        "description":          _pick('description'),
        "target_audience":      _pick('target_audience'),
        "tone":                 _pick('tone', default='professional'),
        "tone_preference":      _pick('tone_preference'),
        "tagline":              _pick('tagline'),
        "website":              brand_info.get('website_url') or meta.get('website', ''),
        "unique_selling_points": (
            brand_info.get('unique_selling_points')
            or meta.get('unique_selling_points', [])
        ),
        "colors":               brand_info.get('colors') or meta.get('colors', []),
        "products_services":    meta.get('products_services', []),
    }


def _build_user_context_summary(user_id: int, brand_name: Optional[str] = None) -> str:
    """
    Build a comprehensive plain-text summary of the user's stored brand profile.
    Used to inject business context into LLM calls so the model never
    needs to ask for details the user has already provided.

    Includes EVERYTHING: brand details, visual identity (colors, fonts, logo),
    tone, target audience, products/services, and website content.

    Returns an empty string when no profile is found.
    """
    try:
        profile = db.get_brand_profile(user_id, brand_name)
        if not profile:
            return ""
        b = normalize_brand_info(profile)
        meta = profile.get('metadata', {})
        if isinstance(meta, str):
            try:
                import json as _j; meta = _j.loads(meta) if meta else {}
            except Exception:
                meta = {}

        parts = []

        # ═══ BASIC BRAND INFORMATION ═══
        if b.get("brand_name") and b["brand_name"] != "My Business":
            parts.append(f"Business Name: {b['brand_name']}")

        if b.get("tagline"):
            parts.append(f"Tagline: {b['tagline']}")

        if b.get("industry") and b["industry"] != "General":
            parts.append(f"Industry: {b['industry']}")

        if b.get("location"):
            parts.append(f"Location: {b['location']}")

        if b.get("description"):
            parts.append(f"Description: {b['description']}")

        if b.get("target_audience"):
            parts.append(f"Target Audience: {b['target_audience']}")

        if b.get("unique_selling_points"):
            parts.append(f"Unique Selling Points: {', '.join(b['unique_selling_points'])}")

        if b.get("website"):
            parts.append(f"Website: {b['website']}")

        if b.get("contacts"):
            parts.append(f"Contact Info: {b['contacts']}")

        # ═══ VISUAL IDENTITY ═══
        colors = b.get("colors", [])
        if colors and len(colors) > 0:
            colors_str = ', '.join(colors) if isinstance(colors, list) else str(colors)
            parts.append(f"\n🎨 BRAND COLORS: {colors_str}")
            parts.append(f"   (Use these exact colors in all visual content and image generation)")

        fonts = b.get("fonts", [])
        if fonts and len(fonts) > 0:
            fonts_str = ', '.join(fonts) if isinstance(fonts, list) else str(fonts)
            parts.append(f"📝 BRAND FONTS: {fonts_str}")
            parts.append(f"   (Recommend these fonts in design descriptions)")

        if b.get("logo_url"):
            parts.append(f"🖼️  LOGO: {b['logo_url']}")
            parts.append(f"   (Reference the brand logo in image prompts)")

        # ═══ TONE & VOICE ═══
        tone = b.get("tone") or b.get("tone_preference") or "professional"
        parts.append(f"\n🗣️  BRAND TONE: {tone}")
        parts.append(f"   (Use this tone consistently in ALL content generation)")

        # ═══ PRODUCTS & SERVICES ═══
        products = meta.get("products_services", [])
        if products:
            parts.append(f"\n📦 PRODUCTS/SERVICES: {', '.join(products)}")

        # ═══ LEARNED SIGNALS (from past content) ═══
        learned = profile.get("learned_signals", {})
        if isinstance(learned, str):
            try:
                import json as _j; learned = _j.loads(learned) if learned else {}
            except:
                learned = {}

        if learned:
            parts.append(f"\n🧠 LEARNED PREFERENCES:")
            if learned.get("preferred_content_types"):
                parts.append(f"   - Preferred content types: {', '.join(learned['preferred_content_types'])}")
            if learned.get("avg_word_count"):
                parts.append(f"   - Typical content length: ~{learned['avg_word_count']} words")
            if learned.get("common_keywords"):
                parts.append(f"   - Common keywords: {', '.join(learned['common_keywords'][:5])}")

        # ═══ WEBSITE CONTENT (first 1500 chars) ═══
        website_content = meta.get("website_content", "")
        if website_content:
            parts.append(f"\n📄 CRAWLED WEBSITE CONTENT (first 1500 chars):")
            parts.append(f"{website_content[:1500]}")
            if len(website_content) > 1500:
                parts.append(f"... (truncated, total {len(website_content)} chars)")

        return "\n".join(parts) if parts else ""
    except Exception as e:
        logger.warning(f"Failed to build brand context summary: {e}")
        return ""


async def extract_brand_info(user_id: int, user_input: str, url: Optional[str] = None, crawled_data: Optional[str] = None, conversation_history: Optional[List[Dict]] = None, force_new: bool = False, active_brand: Optional[str] = None) -> Dict[str, Any]:
    """Extract and save brand information using LLM from user input, conversation history, and/or crawled website data."""
    try:
        # Check if brand profile already exists (skip if force_new=True)
        if not force_new:
            existing_profile = db.get_brand_profile(user_id, active_brand)
            if existing_profile:
                # If a URL was provided, check whether it belongs to a DIFFERENT brand
                if url:
                    try:
                        from urllib.parse import urlparse as _up
                        new_domain = _up(url).netloc.replace('www.', '').lower().split('.')[0]
                        # Check website_url column first, then metadata.website
                        stored_website = existing_profile.get('website_url') or ''
                        if not stored_website:
                            meta = existing_profile.get('metadata')
                            if isinstance(meta, str):
                                import json as _json
                                meta = _json.loads(meta) if meta else {}
                            if isinstance(meta, dict):
                                stored_website = meta.get('website', '')
                        if stored_website:
                            stored_domain = _up(stored_website).netloc.replace('www.', '').lower().split('.')[0]
                            if new_domain and stored_domain and new_domain != stored_domain:
                                logger.info(f"URL domain '{new_domain}' differs from stored '{stored_domain}' â€” re-extracting brand")
                                force_new = True
                        else:
                            # No stored website â€” always re-extract when a URL is given
                            logger.info(f"No stored website for user {user_id} â€” re-extracting from {url}")
                            force_new = True
                    except Exception:
                        pass

                if not force_new:
                    logger.info(f"Brand profile already exists for user {user_id}")
                    return normalize_brand_info(existing_profile)
        
        # Build comprehensive extraction prompt with all available context
        content_to_analyze = user_input
        
        # Include conversation history to capture business details from previous messages
        if conversation_history:
            history_text = "\n".join([
                f"{msg['role'].upper()}: {msg['content']}" 
                for msg in conversation_history[-10:]  # Last 10 messages
            ])
            content_to_analyze = f"""Conversation History:
{history_text}

Current Message: {user_input}"""
        
        # Add crawled website data if available
        if crawled_data:
            content_to_analyze += f"""

Website Content (crawled from {url}):
{crawled_data[:5000]}"""  # Limit to avoid token overflow
        
        # Pre-extract domain name as a strong brand_name hint
        _domain_hint = ""
        if url:
            try:
                from urllib.parse import urlparse as _urlp
                _raw_domain = _urlp(url).netloc.replace('www.', '').split('.')[0]
                _domain_hint = _raw_domain.replace('-', ' ').replace('_', ' ').title()
            except Exception:
                pass

        prompt = f"""Extract detailed business information from the following content (including conversation history):
        
IMPORTANT: Look through the ENTIRE conversation history to find business details that the user may have mentioned earlier.
{f'DOMAIN HINT: The website domain is "{_domain_hint}" â€” use this as the brand_name if the name cannot be found in the content.' if _domain_hint else ''}

{content_to_analyze}

Extract and return JSON with these fields:
- brand_name: The business/company name (REQUIRED - extract from page title, headings, logo text, or use the DOMAIN HINT above; NEVER return "Not specified", "Unknown", or any placeholder â€” always return a real name)
- contacts: Email, phone, or other contact info (extract if found)
- location: Business location, city, state, or address (extract if mentioned)
- industry: Type of business or industry (be specific: e.g., "Italian Restaurant", "E-commerce Fashion")
- description: Detailed description of what the business does (2-3 sentences)
- target_audience: Who are the target customers (if identifiable)
- unique_selling_points: Key differentiators or unique features (array of strings)
- products_services: List the specific products or services offered (array of strings, e.g. ["Vitamin C Serum", "Moisturiser", "Eye Cream"]). This is VERY IMPORTANT â€” extract every product or service name you can find.

If this is a website, extract the brand name from the domain, title, or content.
NEVER use placeholder text like "Not specified", "Unknown", "N/A" for any field â€” omit the field instead.
Return ONLY valid JSON. Be thorough and extract all available information."""

        response, _used_model = groq_chat_with_failover(
            groq_client,
            messages=[{"role": "user", "content": prompt}],
            primary_model="llama-3.3-70b-versatile",
            logger=logger,
            response_format={"type": "json_object"},
            temperature=0.3,
        )
        
        extracted = json.loads(response.choices[0].message.content)
        logger.info(f"Brand extraction result: {extracted}")
        
        # Ensure brand_name is not empty or a placeholder - use domain as fallback
        _PLACEHOLDER_VALUES = {
            "", "not specified", "not provided", "unknown", "n/a", "na",
            "none", "null", "undefined", "your business", "my business"
        }
        brand_name = extracted.get("brand_name", "").strip()
        if brand_name.lower() in _PLACEHOLDER_VALUES and url:
            # Extract domain name as fallback
            from urllib.parse import urlparse
            domain = urlparse(url).netloc.replace('www.', '')
            brand_name = domain.split('.')[0].title()
        if brand_name.lower() in _PLACEHOLDER_VALUES:
            brand_name = "My Business"

        # If an existing profile already has a real brand_name, never downgrade it
        _current = db.get_brand_profile(user_id, active_brand)
        if _current:
            _cur_norm = normalize_brand_info(_current)
            _cur_name = (_cur_norm.get("brand_name") or "").strip()
            if _cur_name and _cur_name.lower() not in _PLACEHOLDER_VALUES:
                # Keep existing name if the new extraction got a placeholder
                if brand_name.lower() in _PLACEHOLDER_VALUES or not brand_name:
                    brand_name = _cur_name
            # Merge: keep existing field if new extraction returned a placeholder
            def _keep(new_val, existing_val):
                if not new_val or str(new_val).strip().lower() in _PLACEHOLDER_VALUES:
                    return existing_val
                return new_val
            extracted["location"]         = _keep(extracted.get("location"), _cur_norm.get("location"))
            extracted["industry"]         = _keep(extracted.get("industry"), _cur_norm.get("industry"))
            extracted["description"]      = _keep(extracted.get("description"), _cur_norm.get("description"))
            extracted["target_audience"]  = _keep(extracted.get("target_audience"), _cur_norm.get("target_audience"))
            if not extracted.get("unique_selling_points"):
                extracted["unique_selling_points"] = _cur_norm.get("unique_selling_points", [])
        
        # Convert contacts to string if it's a dict
        contacts_data = extracted.get("contacts")
        if isinstance(contacts_data, dict):
            # Format contacts dict as string
            contacts_str = ", ".join([f"{k}: {v}" for k, v in contacts_data.items()])
        elif contacts_data:
            contacts_str = str(contacts_data)
        else:
            contacts_str = None
        
        # Save to database â€” write to both direct columns AND metadata for compatibility
        brand_id = db.save_brand_profile(
            user_id=user_id,
            brand_name=brand_name,
            contacts=contacts_str,
            location=extracted.get("location"),
            description=extracted.get("description", ""),
            target_audience=extracted.get("target_audience", ""),
            industry=extracted.get("industry", ""),
            website_url=url or "",
            metadata={
                "industry": extracted.get("industry", ""),
                "description": extracted.get("description", ""),
                "target_audience": extracted.get("target_audience", ""),
                "unique_selling_points": extracted.get("unique_selling_points", []),
                "products_services": extracted.get("products_services", []),
                "website": url if url else "",
                "website_content": crawled_data[:3000] if crawled_data else ""
            }
        )
        
        # Update extracted with normalized data for return
        extracted["brand_name"] = brand_name
        extracted["contacts"] = contacts_str  # Use string version for consistency
        
        logger.info(f"Brand profile created for user {user_id}: {brand_name} in {extracted.get('location', 'N/A')}")
        return extracted
        
    except Exception as e:
        logger.error(f"Brand extraction error: {e}")
        # Return default brand info with URL domain as brand name if available
        fallback_brand = "My Business"
        if url:
            try:
                from urllib.parse import urlparse
                domain = urlparse(url).netloc.replace('www.', '')
                fallback_brand = domain.split('.')[0].title()
            except:
                pass
        
        try:
            db.save_brand_profile(
                user_id=user_id,
                brand_name=fallback_brand,
                contacts=None,
                location=None,
                metadata={"industry": "", "description": "", "website": url if url else ""}
            )
        except:
            pass
        return {"brand_name": fallback_brand, "industry": "", "description": "", "location": ""}

async def generate_session_title(messages: List[Dict]) -> str:
    """
    Generate a short session title deterministically from the first user message.
    No LLM call — takes the first 6 meaningful words and title-cases them.
    """
    import re as _re

    # Filler words to skip when building the title
    _STOP = {
        "i", "me", "my", "a", "an", "the", "to", "for", "of", "in", "on",
        "at", "with", "and", "or", "is", "can", "you", "please", "hey",
        "hi", "hello", "what", "how", "would", "could", "should", "do",
        "just", "it", "this", "that", "be", "are", "was", "were"
    }

    # Find the first user message
    first_user = next(
        (m["content"] for m in messages if m.get("role") == "user"),
        None
    )
    if not first_user:
        return "New Chat"

    # Strip markdown / URLs / special chars, keep words
    clean = _re.sub(r"https?://\S+", "", first_user)
    clean = _re.sub(r"[^a-zA-Z0-9 ]", " ", clean)
    words = [w for w in clean.split() if w.lower() not in _STOP and len(w) > 1]

    if not words:
        return "New Chat"

    # Take up to 6 words, title-case, join
    title = " ".join(w.capitalize() for w in words[:6])
    return title[:50]

# ==================== MAIN CHAT ENDPOINT ====================

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest, authorization: str = Header(None)):
    """
    Main chat endpoint with intelligent routing.
    """
    user_id = None
    session_id = req.session_id
    credits_charged = 0
    credits_balance = None
    try:
        # Authenticate user
        payload = auth.get_current_user(authorization)
        user_id = payload['user_id']
        credits_balance = db.get_user_credit_balance(user_id)
        
        # Get or create session
        session_id = req.session_id
        if not session_id:
            session_id = f"sess_{uuid.uuid4().hex[:12]}"
            db.create_session(session_id, user_id, "New Chat")
        else:
            # Verify session belongs to user
            session = db.get_session(session_id, user_id)
            if not session:
                raise HTTPException(status_code=404, detail="Session not found")
        
        # Save user message
        db.save_message(session_id, "user", req.message)
        db.update_session_activity(session_id)
        
        # Get conversation history
        history = db.get_recent_messages(session_id, count=10)
        history_for_router = [{"role": h["role"], "content": h["content"]} for h in history]

        # --- Platform clarification intercept ---
        # If this session is waiting for a platform choice, try to resolve it now.
        _pending = _pending_platform.get(session_id)
        if _pending:
            _detected = _detect_platform_from_text(req.message)
            if _detected:
                # User answered â€” restore original message + inject platform, skip router
                logger.info(f"Platform resolved for session {session_id}: {_detected}")
                del _pending_platform[session_id]
                # Mutate the request so the social_post handler below uses original context
                req = ChatRequest(
                    message=_pending["original_message"],
                    session_id=req.session_id,
                    platform=_detected
                )
                routing_result = {
                    "intent": "social_post",
                    "confidence": 1.0,
                    "requires_url": False,
                    "requires_brand_info": False,
                    "extracted_params": {"platform": _detected},
                    "suggested_response": ""
                }
                intent = "social_post"
                confidence = 1.0
                extracted_params = {"platform": _detected}
            else:
                # Still no platform â€” ask again and bail
                response_text = "Please choose a platform: **Twitter/X** or **Instagram**?"
                db.save_message(session_id, "assistant", response_text, formatted_content=response_text)
                return {
                    "response": response_text,
                    "session_id": session_id,
                    "intent": "social_post",
                    "content_preview_id": None,
                    "workflow_cost": None,
                    "credits_charged": 0,
                    "credits_balance": credits_balance,
                    "seo_result": None,
                    "response_options": None
                }
        else:
            # Normal routing (or trusted intent override)
            forced_intent = (req.intent or "").strip().lower()
            allowed_forced_intents = {
                "general_chat",
                "brand_setup",
                "campaign_planning",
                "daily_schedule",
                "seo_analysis",
                "blog_generation",
                "blog_instagram_combo",
                "social_post",
                "metrics_report",
            }
            if forced_intent in allowed_forced_intents:
                intent = forced_intent
                confidence = 1.0
                extracted_params = {"platform": req.platform} if forced_intent == "social_post" and req.platform else {}
                routing_result = {
                    "intent": intent,
                    "confidence": confidence,
                    "requires_url": False,
                    "requires_brand_info": False,
                    "extracted_params": extracted_params,
                    "suggested_response": "",
                }
                logger.info(f"Using forced intent override: {intent}")
            elif _is_blog_instagram_combo_request(req.message):
                intent = "blog_instagram_combo"
                confidence = 1.0
                extracted_params = {"platform": "instagram"}
                routing_result = {
                    "intent": intent,
                    "confidence": confidence,
                    "requires_url": False,
                    "requires_brand_info": True,
                    "extracted_params": extracted_params,
                    "suggested_response": "Routing to combined blog + Instagram workflow.",
                }
                logger.info("Detected combined blog + Instagram request")
            else:
                routing_result = await router.route_user_query(req.message, history_for_router)
                intent = routing_result["intent"]
                confidence = routing_result["confidence"]
                extracted_params = routing_result["extracted_params"]
        
        logger.info(f"Routed to intent: {intent} (confidence: {confidence})")

        estimated_credits = _estimate_chat_credit_cost(intent, extracted_params)
        try:
            credits_balance = db.consume_user_credits(
                user_id,
                estimated_credits,
                reason=f"chat:{intent}",
                metadata={
                    "session_id": session_id,
                    "message": req.message[:200],
                    "intent": intent,
                },
            )
            credits_charged = estimated_credits
        except ValueError:
            response_text = (
                f"You need {estimated_credits} credits for this request, but only have {credits_balance} left. "
                f"Please top up or try a lighter request."
            )
            db.save_message(session_id, "assistant", response_text, formatted_content=response_text)
            return ChatResponse(
                session_id=session_id,
                response=response_text,
                formatted_response=response_text,
                intent=intent,
                content_preview_id=None,
                workflow_cost=None,
                credits_charged=0,
                credits_balance=credits_balance,
                response_options=None,
                clarification_request=None,
                seo_result=None,
            )
        
        response_text = ""
        content_preview_id = None
        workflow_cost = None
        seo_result: Optional[Dict[str, Any]] = None
        response_options: Optional[List[Dict[str, Any]]] = None
        clarification_request: Optional[Dict[str, Any]] = None

        # ══════════════ LangGraph path (feature-flagged) ══════════════
        if USE_LANGGRAPH and LANGGRAPH_AVAILABLE and intent != "blog_instagram_combo":
            try:
                # Build brand context
                brand_info_dict = None
                _brand_ctx = ""
                active_brand_name = req.active_brand

                # If no brand specified, try to get user's most recent brand from DB
                if not active_brand_name:
                    try:
                        first_brand_profile = db.get_brand_profile(user_id, None)
                        if first_brand_profile:
                            active_brand_name = first_brand_profile.get("brand_name", "")
                            logger.info(f"Chat: auto-selected brand '{active_brand_name}' for user {user_id}")
                    except Exception as e:
                        logger.warning(f"Could not fetch user brand for chat: {e}")

                if active_brand_name:
                    _profile = db.get_brand_profile(user_id, active_brand_name)
                    if _profile:
                        brand_info_dict = _profile
                        _brand_ctx = _build_user_context_summary(user_id, active_brand_name)

                # Invoke the compiled LangGraph
                import asyncio

                # Start trace for live visualization
                trace_id = f"chat_{session_id}_{int(time.time())}"
                trace_mgr = get_trace_manager()
                trace_mgr.start_trace(
                    trace_id=trace_id,
                    user_id=user_id,
                    session_id=session_id,
                    user_message=req.message,
                    intent="unknown",  # Will be determined by router node
                    workflow="langgraph"
                )

                try:
                    graph_result = await run_marketing_graph(
                        user_message=req.message,
                        session_id=session_id,
                        user_id=user_id,
                        active_brand=active_brand_name,
                        conversation_history=history_for_router,
                        brand_info=brand_info_dict,
                        brand_context_summary=_brand_ctx,
                        trace_id=trace_id,  # Pass trace_id to graph
                    )

                    # Update trace metadata with resolved intent/workflow for accurate visualization.
                    try:
                        resolved_intent = graph_result.get("intent") or intent
                        if trace_id in trace_mgr.trace_metadata:
                            trace_mgr.trace_metadata[trace_id]["intent"] = resolved_intent
                            trace_mgr.trace_metadata[trace_id]["workflow"] = "langgraph"
                    except Exception as trace_meta_err:
                        logger.warning(f"Failed to update trace metadata for {trace_id}: {trace_meta_err}")

                    trace_mgr.complete_trace(trace_id, success=True)
                except Exception as graph_err:
                    trace_mgr.complete_trace(trace_id, success=False, error=str(graph_err))
                    raise

                # Map graph result → ChatResponse fields
                response_text = graph_result.get("response_text", "")
                intent = graph_result.get("intent", intent)
                seo_result = graph_result.get("seo_result")
                content_preview_id = graph_result.get("content_preview_id")
                clarification_request = graph_result.get("clarification_request")
                response_options = graph_result.get("response_options", response_options)

                logger.info(
                    f"[LangGraph] intent={intent}, "
                    f"steps={graph_result.get('steps_completed', [])}, "
                    f"errors={graph_result.get('errors', [])}"
                )

                # Save assistant response + auto-generate title
                db.save_message(session_id, "assistant", response_text,
                                formatted_content=response_text)
                if len(history) <= 2:
                    messages_for_title = db.get_session_messages(session_id)
                    title = await generate_session_title(messages_for_title)
                    db.update_session_title(session_id, title)

                return ChatResponse(
                    session_id=session_id,
                    response=response_text,
                    formatted_response=response_text,
                    intent=intent,
                    content_preview_id=content_preview_id,
                    workflow_cost=workflow_cost,
                    credits_charged=credits_charged,
                    credits_balance=credits_balance,
                    response_options=response_options,
                    clarification_request=clarification_request,
                    seo_result=seo_result,
                )
            except Exception as lg_err:
                logger.error(f"LangGraph execution failed, falling back to HTTP path: {lg_err}",
                             exc_info=True)
                # Fall through to the original HTTP-based intent handling below
        # ══════════════ End LangGraph path ══════════════

        # Handle different intents
        if intent == "general_chat":
            # Generate conversational response with stored brand context
            _brand_ctx = _build_user_context_summary(user_id, req.active_brand)
            response_text = await router.generate_conversational_response(
                req.message, history_for_router, brand_context=_brand_ctx
            )
        
        elif intent == "brand_setup":
            # Guard: if user is asking a question ABOUT their existing profile,
            # treat it as general_chat and answer from stored context.
            _existing_profile = db.get_brand_profile(user_id, req.active_brand)
            _is_read_query = any(kw in req.message.lower() for kw in [
                "tell me", "what is my", "what's my", "show my", "my brand",
                "my product", "my business name", "my industry", "my profile",
                "my company", "my details", "can you tell", "what are my",
                "list my", "my service", "my website", "my location",
                "my description", "my audience", "my selling", "product name",
                "products", "services", "what do i sell", "what do i offer"
            ])
            if _is_read_query and _existing_profile:
                # If asking about products/services AND we have a website URL but no cached content,
                # do a live crawl to get the most accurate answer.
                _needs_live = any(kw in req.message.lower() for kw in [
                    "product", "service", "sell", "offer", "catalogue", "catalog"
                ])
                _meta = _existing_profile.get('metadata', {})
                if isinstance(_meta, str):
                    try:
                        import json as _jj; _meta = _jj.loads(_meta) if _meta else {}
                    except Exception:
                        _meta = {}
                _cached_content = _meta.get("website_content", "") if isinstance(_meta, dict) else ""
                _stored_url = (
                    _existing_profile.get('website_url')
                    or (_meta.get('website') if isinstance(_meta, dict) else '')
                )
                if _needs_live and _stored_url and not _cached_content:
                    try:
                        logger.info(f"Live crawl for product query: {_stored_url}")
                        _crawl = call_agent_job(
                            "WebCrawler", f"{CRAWLER_BASE}/crawl",
                            {"start_url": _stored_url, "max_pages": 3},
                            download_path_template="/download/{job_id}"
                        )
                        _cached_content = _crawl.get("extracted_text", "")[:3000]
                        # Persist so next query is instant
                        if isinstance(_meta, dict):
                            _meta["website_content"] = _cached_content
                            db.save_brand_profile(
                                user_id=user_id,
                                brand_name=_existing_profile.get('brand_name', 'My Business'),
                                contacts=_existing_profile.get('contacts'),
                                location=_existing_profile.get('location'),
                                description=_existing_profile.get('description', ''),
                                target_audience=_existing_profile.get('target_audience', ''),
                                industry=_existing_profile.get('industry', ''),
                                website_url=_stored_url,
                                metadata=_meta
                            )
                    except Exception as _lce:
                        logger.warning(f"Live crawl for product query failed: {_lce}")
                _brand_ctx = _build_user_context_summary(user_id, req.active_brand)
                # If we just fetched live content, append it directly
                if _needs_live and _cached_content and "Crawled Website Content" not in _brand_ctx:
                    _brand_ctx += f"\n\n--- Website Content ---\n{_cached_content[:1500]}"
                response_text = await router.generate_conversational_response(
                    req.message, history_for_router, brand_context=_brand_ctx
                )
            else:
                # Genuine setup / update request
                response_text = "Let me save your business information..."
                try:
                    # Extract URL if present
                    url = extracted_params.get("url") or await router.extract_url_from_message(req.message)
                    crawled_data = None
                    
                    # Crawl website if URL provided
                    if url:
                        try:
                            logger.info(f"Crawling website for brand setup: {url}")
                            crawl_result = call_agent_job(
                                "WebCrawler",
                                f"{CRAWLER_BASE}/crawl",
                                {"url": url, "max_pages": 5},
                                download_path_template="/download/json/{job_id}"
                            )
                            # crawl_result is a list of page dicts with headers/paragraphs
                            if isinstance(crawl_result, list):
                                crawled_data = " ".join(
                                    [h.get('text', '') for doc in crawl_result for h in doc.get('headers', [])] +
                                    [p for doc in crawl_result for p in doc.get('paragraphs', [])]
                                )
                            elif isinstance(crawl_result, dict):
                                crawled_data = crawl_result.get("extracted_text", "") or crawl_result.get("content", "")
                            else:
                                crawled_data = str(crawl_result)
                            logger.info(f"Website crawled successfully: {len(crawled_data)} characters")
                        except Exception as e:
                            logger.warning(f"Website crawl failed: {e}, continuing without crawled data")
                    
                    # Extract brand info
                    extracted = await extract_brand_info(
                        user_id,
                        req.message,
                        url=url,
                        crawled_data=crawled_data,
                        conversation_history=history,
                        force_new=True,
                        active_brand=req.active_brand
                    )
                    
                    response_text = f"I've set up your business profile for **{extracted.get('brand_name')}**.\n\n"
                    response_text += f"**Industry:** {extracted.get('industry')}\n"
                    response_text += f"**Description:** {extracted.get('description')}\n\n"
                    response_text += "You can now ask me to generate content, analyze SEO, or plan marketing campaigns!"

                except Exception as e:
                    logger.error(f"Error in brand setup: {e}")
                    response_text = f"I encountered an error setting up your brand profile: {str(e)}"
        
        elif intent == "campaign_planning":
            # Extract parameters
            theme = extracted_params.get("theme", "")
            duration_str = extracted_params.get("duration", "")
            domain = extracted_params.get("domain", "")

            # Fallback parse from natural language message when router params are sparse
            msg_lower = req.message.lower()
            if not theme:
                m_theme = re.search(r"theme\s+is\s+(.+)", req.message, re.IGNORECASE)
                if m_theme:
                    theme = m_theme.group(1).strip().rstrip(".")
            if not theme:
                # Strip leading instruction phrase and keep intent payload as theme
                theme = re.sub(r"^(build|create|plan|make)\s+(a\s+)?campaign\s+(for|about)?\s*", "", req.message, flags=re.IGNORECASE).strip()
            if not theme:
                theme = "General Promotion"

            if not duration_str:
                if "this week" in msg_lower or "week" in msg_lower:
                    duration_str = "7 days"
                else:
                    duration_str = "7 days"
            
            # Parse duration
            try:
                import re
                duration_days = int(re.search(r'\d+', duration_str).group())
            except:
                duration_days = 7
            
            # 1. Discover trends if domain provided
            trends = []
            if domain:
                trends = planner_agent.discover_trends(domain)
                theme = f"{theme} ({trends[0]})" if trends else theme
            
            # 2. Generate proposals
            proposals_data = planner_agent.generate_workflow_proposals(theme, duration_days)
            tiers = proposals_data["proposals"]
            
            response_text = f"I designed 3 campaign tiers for **{theme}** over **{duration_days} days**.\n\nSelect one card to activate the plan."
            
            # Format options for UI
            response_options = []
            for tier_name, details in tiers.items():
                response_options.append({
                    "option_id": f"campaign_{tier_name.lower()}",
                    "label": f"{tier_name} Tier",
                    "preview_text": details["description"],
                    "workflow_name": "campaign_plan",
                    "cost_display": (
                        f"{details['frequency']} | Est. "
                        f"{cost_model.format_credits_display(cost_model.usd_cost_to_credits(details['estimated_api_cost']))}"
                    ),
                    "campaign_data": {
                        "tier": tier_name.lower(),
                        "theme": theme,
                        "duration_days": duration_days
                    }
                })
        
        elif intent == "daily_schedule":
            response_text = "I can help you manage your daily schedule and tasks. What specifically would you like to schedule?"
        
        elif intent == "seo_analysis":
            # SEO Analysis workflow
            url = extracted_params.get("url") or await router.extract_url_from_message(req.message)
            if not url:
                response_text = "Please provide a URL to analyze. For example: 'Analyze https://example.com'"
            else:
                # Get optimized workflow from MABO agent
                mabo = mabo_agent.get_mabo_agent()
                state_context = mabo.create_state_from_context(
                    intent=intent,
                    user_id=user_id,
                    content_type="seo",
                    has_website=True
                )
                agents = mabo.get_optimized_workflow(state_context, use_mabo=True)
                cost_estimate = cost_model.estimate_workflow_cost(agents)
                workflow_cost = cost_estimate

                try:
                    # Normalize URL
                    if not url.startswith(("http://", "https://")):
                        url = f"https://{url}"
                    
                    # Detect if user is asking for detailed/comprehensive analysis
                    message_lower = req.message.lower()
                    detailed_keywords = ["detailed", "comprehensive", "full", "in-depth", "complete", "thorough", "deep", "all metrics", "full analysis", "full report"]
                    wants_detailed = any(keyword in message_lower for keyword in detailed_keywords)
                    
                    import requests as _sreq
                    # Route to detailed endpoint if keywords detected, otherwise use fast endpoint
                    endpoint = "/seo/analyze/detailed" if wants_detailed else "/seo/analyze"
                    _seo_resp = _sreq.post(
                        f"http://127.0.0.1:8004{endpoint}",
                        json={"url": url},
                        timeout=300  # Increased from 90 to 300 seconds (5 minutes) for comprehensive analysis
                    )
                    _seo_data = _seo_resp.json() if _seo_resp.ok else {}
                    if _seo_data.get("status") == "error":
                        raise Exception(_seo_data.get("error", "SEO audit failed"))

                    _report_base = os.path.basename(_seo_data.get("report_path", ""))
                    seo_result = {
                        "url": url,
                        "final_url": _seo_data.get("final_url", url),
                        "scores": _seo_data.get("scores", {}),
                        "recommendations": _seo_data.get("recommendations", []),
                        "report_path": _seo_data.get("report_path", ""),
                        "status": "completed",
                    }
                    _score_lines = " Â· ".join(
                        [f"{k.title()}: {round(v*100)}" for k, v in seo_result["scores"].items()]
                    )
                    _rec_lines = "\n".join([
                        f"- {r['issue'] if isinstance(r, dict) else r}"
                        for r in seo_result["recommendations"][:3]
                    ])
                    response_text = (
                        f"âœ… **SEO Audit Complete for {url}**\n\n"
                        f"ðŸ“Š **Scores:** {_score_lines}\n\n"
                        f"ðŸ” **Top Fixes:**\n{_rec_lines}"
                        + (f"\n\n[ðŸ“„ Open Full Report](http://localhost:8080/{_report_base})" if _report_base else "")
                        + "\n\n_Full scores and all recommendations are now shown in the **SEO Audit** page._"
                    )
                except Exception as e:
                    response_text = f"âš ï¸ Analysis encountered an error: {str(e)}\n\nPlease try again or provide a different URL."
        
        elif intent == "blog_instagram_combo":
            url = extracted_params.get("url") or await router.extract_url_from_message(req.message)
            crawled_data = None
            brand_profile = db.get_brand_profile(user_id, req.active_brand)
            brand_info = normalize_brand_info(brand_profile) if brand_profile else None

            if url:
                try:
                    logger.info(f"Crawling website for combo workflow: {url}")
                    crawl_result = call_agent_job(
                        "WebCrawler",
                        f"{CRAWLER_BASE}/crawl",
                        {"start_url": url, "max_pages": 3},
                        download_path_template="/download/{job_id}"
                    )
                    crawled_data = crawl_result.get("extracted_text", "")
                    logger.info(f"Combo workflow crawl completed: {len(crawled_data)} characters")
                except Exception as e:
                    logger.warning(f"Combo workflow crawl failed: {e}")

            try:
                extracted_brand = await extract_brand_info(
                    user_id,
                    req.message,
                    url=url,
                    crawled_data=crawled_data,
                    conversation_history=history_for_router,
                    force_new=bool(url),
                    active_brand=req.active_brand
                )
                if extracted_brand:
                    brand_info = extracted_brand
            except Exception as e:
                logger.warning(f"Combo brand extraction skipped: {e}")

            if not brand_info or not brand_info.get("brand_name") or brand_info.get("brand_name") == "My Business":
                response_text = "I need your business name to generate both the blog and Instagram post. What's your business or brand name?"
            elif not brand_info.get("industry") or brand_info.get("industry") in ["General", ""]:
                response_text = f"Thanks! I have your business name ({brand_info.get('brand_name')}). What industry is your business in?"
            else:
                try:
                    business_context_for_keywords = f"""
Business: {brand_info.get('brand_name', 'My Business')}
Industry: {brand_info.get('industry', 'General')}
Location: {brand_info.get('location', 'N/A')}
Description: {brand_info.get('description', '')}
Target Audience: {brand_info.get('target_audience', '')}
Unique Selling Points: {', '.join(brand_info.get('unique_selling_points', []))}

User Request: {req.message}

{"Website Content Summary: " + crawled_data[:2000] if crawled_data else ""}
"""
                    keywords_data = call_agent_job(
                        "KeywordExtractor",
                        f"{KEYWORD_EXTRACTOR_BASE}/extract-keywords",
                        {"customer_statement": business_context_for_keywords, "max_results": 10},
                        download_path_template="/download/{job_id}",
                        session_id=session_id
                    )

                    gap_analysis = None
                    try:
                        gap_analysis = call_agent_job(
                            "CompetitorGapAnalyzer",
                            f"{GAP_ANALYZER_BASE}/analyze-keyword-gap",
                            {
                                "company_name": brand_info.get("brand_name", "My Business"),
                                "product_description": f"{brand_info.get('industry', 'Business')} in {brand_info.get('location', 'N/A')}. {brand_info.get('description', '')}",
                                "company_url": brand_info.get("website", ""),
                                "max_competitors": 3,
                                "max_pages_per_site": 1,
                            },
                            download_path_template="/download/json/{job_id}",
                            session_id=session_id
                        )
                    except Exception as e:
                        logger.warning(f"Combo gap analysis failed: {e}")

                    reddit_insights = {}
                    try:
                        kw_list = keywords_data.get("keywords", [])[:8] if isinstance(keywords_data, dict) else []
                        if kw_list:
                            reddit_insights = _call_reddit_research(
                                kw_list, brand_info.get("brand_name", "")
                            )
                    except Exception as e:
                        logger.warning(f"Combo Reddit research skipped: {e}")

                    blog_business_context = f"""
=== BUSINESS PROFILE ===
Brand: {brand_info.get('brand_name', 'My Business')}
Industry: {brand_info.get('industry', 'General')}
Location: {brand_info.get('location', 'N/A')}
Description: {brand_info.get('description', req.message)}
Target Audience: {brand_info.get('target_audience', 'General audience')}
Unique Selling Points:
{chr(10).join(['- ' + usp for usp in brand_info.get('unique_selling_points', ['Quality products', 'Excellent service'])])}

=== USER REQUEST ===
{req.message}

=== COMPETITOR INSIGHTS ===
{gap_analysis.get('content_gaps_summary', 'Focus on unique value proposition') if gap_analysis else 'Emphasize unique strengths and local presence'}

=== REDDIT COMMUNITY INTELLIGENCE ===
{('Trending topics: ' + ', '.join(reddit_insights.get('trending_topics', []))) if reddit_insights.get('trending_topics') else 'No Reddit data available'}
{('Community language: ' + ', '.join(reddit_insights.get('community_language', []))) if reddit_insights.get('community_language') else ''}
{('Competitor mentions: ' + ', '.join(reddit_insights.get('competitor_mentions', []))) if reddit_insights.get('competitor_mentions') else ''}
"""

                    blog_html = call_agent_job(
                        "ContentAgent",
                        f"{CONTENT_AGENT_BASE}/generate-blog",
                        {
                            "business_details": blog_business_context,
                            "keywords": keywords_data,
                            "target_tone": "informative",
                            "blog_length": "medium",
                            "variant_label": "Blog + Instagram Combo",
                        },
                        download_path_template="/download/html/{job_id}",
                        result_format="html",
                        session_id=session_id
                    )

                    blog_content_id = str(uuid.uuid4())
                    blog_preview_path = f"previews/blog_{blog_content_id}.html"
                    with open(blog_preview_path, "w", encoding="utf-8") as f:
                        f.write(blog_html)

                    blog_metadata = {
                        "brand_name": brand_info.get("brand_name", "My Business"),
                        "industry": brand_info.get("industry"),
                        "location": brand_info.get("location"),
                        "topic": req.message,
                        "keywords_used": keywords_data.get("keywords", [])[:5] if isinstance(keywords_data, dict) else [],
                        "bundle_type": "blog_instagram_combo",
                        "bundle_role": "blog",
                    }
                    db.save_generated_content(
                        content_id=blog_content_id,
                        session_id=session_id,
                        content_type="blog",
                        content=blog_html,
                        preview_url=f"/preview/blog/{blog_content_id}",
                        metadata=blog_metadata
                    )

                    blog_critic = _call_critic_sync(
                        blog_content_id,
                        blog_html[:1000] if blog_html else "",
                        "blog",
                        brand_info.get("brand_name", ""),
                        req.message
                    )

                    social_data = call_agent_job(
                        "ContentAgent",
                        f"{CONTENT_AGENT_BASE}/generate-social",
                        {
                            "keywords": keywords_data,
                            "brand_name": brand_info.get("brand_name", "My Business"),
                            "industry": brand_info.get("industry", ""),
                            "location": brand_info.get("location", ""),
                            "target_audience": brand_info.get("target_audience", ""),
                            "unique_selling_points": brand_info.get("unique_selling_points", []),
                            "competitor_insights": gap_analysis.get("content_gaps_summary", "") if gap_analysis else "",
                            "user_request": req.message,
                            "platforms": ["instagram"],
                            "tone": "professional",
                        }
                    )

                    instagram_post = (social_data.get("posts") or {}).get("instagram", {})
                    instagram_copy = instagram_post.get("copy", "")
                    image_prompts = social_data.get("image_prompts", [])
                    image_prompt = image_prompts[0] if image_prompts else f"Professional Instagram post image for {brand_info.get('brand_name', 'brand')}"

                    reference_images = []
                    try:
                        latest_profile = db.get_brand_profile(user_id, req.active_brand)
                        if latest_profile:
                            logo_url = latest_profile.get("logo_url")
                            if logo_url:
                                reference_images.append(logo_url)
                            metadata = latest_profile.get("metadata", {})
                            if isinstance(metadata, dict):
                                assets = metadata.get("assets", {})
                                for asset_group in ("reference_image", "item"):
                                    for asset in assets.get(asset_group, []):
                                        if isinstance(asset, dict) and asset.get("url"):
                                            reference_images.append(asset["url"])
                    except Exception as e:
                        logger.debug(f"Combo reference image lookup skipped: {e}")

                    image_path = None
                    preview_url = None
                    try:
                        detailed_prompt = (
                            f"{image_prompt}. You MUST prominently include the text '{brand_info.get('brand_name', '')}' exactly as spelled. "
                            f"Brand: {brand_info.get('brand_name', '')}. Industry: {brand_info.get('industry', '')}. "
                            f"Target audience: {brand_info.get('target_audience', '')}."
                        )
                        image_path = generate_image_with_runway(
                            detailed_prompt,
                            reference_images if reference_images else None
                        )
                        if image_path:
                            preview_url = image_path if image_path.startswith(("http://", "https://")) else f"/preview/image/{image_path}"
                    except Exception as e:
                        logger.warning(f"Combo Instagram image generation failed: {e}")

                    social_content_id = str(uuid.uuid4())
                    social_metadata = {
                        "brand_name": brand_info.get("brand_name", "My Business"),
                        "industry": brand_info.get("industry"),
                        "location": brand_info.get("location"),
                        "target_audience": brand_info.get("target_audience"),
                        "unique_selling_points": brand_info.get("unique_selling_points", []),
                        "platforms": ["instagram"],
                        "hashtags": instagram_post.get("hashtags", []),
                        "image_prompt": image_prompt,
                        "image_path": image_path,
                        "reference_images": reference_images,
                        "post_copy": {"instagram": instagram_copy},
                        "bundle_type": "blog_instagram_combo",
                        "bundle_role": "instagram",
                    }
                    db.save_generated_content(
                        content_id=social_content_id,
                        session_id=session_id,
                        content_type="post",
                        content=json.dumps({"instagram": instagram_copy}),
                        preview_url=preview_url,
                        metadata=social_metadata
                    )

                    social_critic = _call_critic_sync(
                        social_content_id,
                        instagram_copy,
                        "social_post",
                        brand_info.get("brand_name", ""),
                        req.message
                    )

                    response_options = [
                        {
                            "option_id": f"combo_blog_{uuid.uuid4().hex[:8]}",
                            "label": "SEO Blog Draft",
                            "tone": "Informative",
                            "cost_display": "Long-form article",
                            "workflow_name": "blog_instagram_combo",
                            "preview_text": "SEO-focused blog draft ready for review.",
                            "preview_url": f"/preview/blog/{blog_content_id}",
                            "content_id": blog_content_id,
                            "content_type": "blog",
                            "html_code": blog_html,
                            "critic": blog_critic,
                            "bundle_type": "blog_instagram_combo",
                            "direct_action": True,
                        },
                        {
                            "option_id": f"combo_instagram_{uuid.uuid4().hex[:8]}",
                            "label": "Instagram Post",
                            "tone": "Professional",
                            "cost_display": "Caption + image",
                            "workflow_name": "blog_instagram_combo",
                            "preview_text": "Instagram copy and image ready to publish.",
                            "preview_url": preview_url,
                            "content_id": social_content_id,
                            "content_type": "post",
                            "instagram_copy": instagram_copy,
                            "hashtags": instagram_post.get("hashtags", []),
                            "critic": social_critic,
                            "bundle_type": "blog_instagram_combo",
                            "direct_action": True,
                            "platform": "instagram",
                        },
                    ]

                    response_text = (
                        f"Content kit ready for **{brand_info.get('brand_name', 'your brand')}**.\n\n"
                        "I've generated both pieces from the same brief:\n"
                        "1. An SEO-friendly blog draft\n"
                        "2. An Instagram post with image and caption\n\n"
                        "Review each card below and publish either one when you're ready."
                    )
                except Exception as e:
                    logger.error(f"Combined blog + Instagram generation failed: {e}", exc_info=True)
                    response_text = f"Blog + Instagram generation encountered an error: {str(e)}"

        elif intent == "blog_generation":
            # If a URL is present in this message, check whether it belongs to a different
            # brand than what's stored â€” if so, re-extract before generating.
            url = extracted_params.get("url") or await router.extract_url_from_message(req.message)
            if url:
                try:
                    from urllib.parse import urlparse as _up
                    new_domain = _up(url).netloc.replace('www.', '').lower().split('.')[0]
                    existing = db.get_brand_profile(user_id, req.active_brand)
                    needs_reextract = True
                    if existing:
                        # Check website_url column first, then metadata.website
                        stored_website = existing.get('website_url') or ''
                        if not stored_website:
                            meta = existing.get('metadata')
                            if isinstance(meta, str):
                                import json as _json
                                meta = _json.loads(meta) if meta else {}
                            stored_website = (meta or {}).get('website', '') if isinstance(meta, dict) else ''
                        if stored_website:
                            stored_domain = _up(stored_website).netloc.replace('www.', '').lower().split('.')[0]
                            needs_reextract = (new_domain != stored_domain)
                        # else: no stored website â€” always re-extract
                    if needs_reextract:
                        logger.info(f"New URL domain '{new_domain}' â€” crawling and extracting brand before blog generation")
                        try:
                            crawl_result = call_agent_job(
                                "WebCrawler", f"{CRAWLER_BASE}/crawl",
                                {"start_url": url, "max_pages": 3},
                                download_path_template="/download/{job_id}"
                            )
                            crawled_for_brand = crawl_result.get("extracted_text", "")
                        except Exception as _ce:
                            logger.warning(f"Crawl for brand extract failed: {_ce}")
                            crawled_for_brand = ""
                        await extract_brand_info(
                            user_id, req.message, url=url,
                            crawled_data=crawled_for_brand,
                            conversation_history=history_for_router,
                            force_new=True,
                            active_brand=req.active_brand
                        )
                except Exception as _ue:
                    logger.warning(f"URL brand-check failed: {_ue}")

            # Check if we have required business details BEFORE starting generation
            brand_profile = db.get_brand_profile(user_id, req.active_brand)
            brand_info = None
            
            if brand_profile:
                brand_info = normalize_brand_info(brand_profile)
                # Validate essential fields
                if not brand_info.get('brand_name') or brand_info.get('brand_name') == 'My Business':
                    response_text = "I need your business name to create personalized blog content. What's your business or brand name?"
                    # Don't proceed with generation
                elif not brand_info.get('industry') or brand_info.get('industry') in ['General', '']:
                    response_text = f"Thanks! I have your business name ({brand_info.get('brand_name')}). What industry is your business in? (e.g., Restaurant, E-commerce, Tech, Healthcare, etc.)"
                    # Don't proceed with generation
                else:
                    # All required fields present - proceed with generation
                    response_text = "I'll pull together two blog concepts for you..."
                    # url already extracted at the top of blog_generation block
                    crawled_data = None
                    
                    if url:
                        try:
                            logger.info(f"Crawling website: {url}")
                            crawl_result = call_agent_job(
                                "WebCrawler",
                                f"{CRAWLER_BASE}/crawl",
                                {"start_url": url, "max_pages": 3},
                                download_path_template="/download/{job_id}"
                            )
                            crawled_data = crawl_result.get("extracted_text", "")
                            logger.info(f"Website crawled successfully: {len(crawled_data)} characters")
                        except Exception as e:
                            logger.warning(f"Website crawl failed: {e}, continuing without crawled data")
                    
                    logger.info(f"âœ“ Using brand profile: {brand_info.get('brand_name')}")
            else:
                # No brand profile - url already extracted at top of blog_generation block
                crawled_data = None
                
                if url:
                    try:
                        logger.info(f"Crawling website: {url}")
                        crawl_result = call_agent_job(
                            "WebCrawler",
                            f"{CRAWLER_BASE}/crawl",
                            {"start_url": url, "max_pages": 3},
                            download_path_template="/download/{job_id}"
                        )
                        crawled_data = crawl_result.get("extracted_text", "")
                        logger.info(f"Website crawled successfully: {len(crawled_data)} characters")
                    except Exception as e:
                        logger.warning(f"Website crawl failed: {e}, continuing without crawled data")
                
                # Try to extract brand info from conversation
                brand_info = await extract_brand_info(
                    user_id,
                    req.message,
                    url=url,
                    crawled_data=crawled_data,
                    conversation_history=history_for_router,
                    active_brand=req.active_brand
                )
                
                # Check if essential fields are present
                if not brand_info.get('brand_name') or brand_info.get('brand_name') == 'My Business':
                    response_text = "I need your business name to create personalized blog content. What's your business or brand name?"
                    brand_info = None  # Don't proceed
                elif not brand_info.get('industry') or brand_info.get('industry') in ['General', '']:
                    response_text = f"Thanks! I have your business name ({brand_info.get('brand_name')}). What industry is your business in? (e.g., Restaurant, E-commerce, Tech, Healthcare, etc.)"
                    brand_info = None  # Don't proceed
                else:
                    logger.info(f"âœ“ Brand info extracted from conversation: {brand_info.get('brand_name')} in {brand_info.get('location', 'N/A')}")
                    response_text = "I'll pull together two blog concepts for you..."
            
            # Only proceed with generation if we have valid brand_info
            if brand_info and brand_info.get('brand_name') and brand_info.get('brand_name') != 'My Business' and brand_info.get('industry') and brand_info.get('industry') not in ['General', '']:
                try:
                    mabo = mabo_agent.get_mabo_agent()
                    state_context = mabo.create_state_from_context(
                        intent=intent,
                        user_id=user_id,
                        content_type="blog",
                        has_brand_profile=brand_profile is not None
                    )
                    state_hash = state_context["state_hash"]
                    primary_workflow = mabo.get_optimized_workflow_details(state_context, use_mabo=True)
                    workflow_cost = cost_model.estimate_workflow_cost(primary_workflow["agents"])
                    secondary_workflow = mabo.get_alternative_workflow_details(
                        intent,
                        state_context,
                        exclude_workflow=primary_workflow["workflow_name"]
                    )
                    
                    try:
                        business_context_for_keywords = f"""
Business: {brand_info.get('brand_name', 'My Business')}
Industry: {brand_info.get('industry', 'General')}
Location: {brand_info.get('location', 'N/A')}
Description: {brand_info.get('description', '')}
Target Audience: {brand_info.get('target_audience', '')}
Unique Selling Points: {', '.join(brand_info.get('unique_selling_points', []))}

User Request: {req.message}

{"Website Content Summary: " + crawled_data[:2000] if crawled_data else ""}
"""
                        logger.info("Extracting keywords from business context")
                        keywords_data = call_agent_job(
                            "KeywordExtractor",
                            f"{KEYWORD_EXTRACTOR_BASE}/extract-keywords",
                            {"customer_statement": business_context_for_keywords, "max_results": 10},
                            download_path_template="/download/{job_id}",
                            session_id=session_id
                        )
                        
                        gap_analysis = None
                        try:
                            logger.info("Running competitor gap analysis")
                            product_desc = f"{brand_info.get('industry', 'Business')} in {brand_info.get('location', 'N/A')}. {brand_info.get('description', '')}"
                            gap_analysis = call_agent_job(
                                "CompetitorGapAnalyzer",
                                f"{GAP_ANALYZER_BASE}/analyze-keyword-gap",
                                {
                                    "company_name": brand_info.get('brand_name', 'My Business'),
                                    "product_description": product_desc,
                                    "company_url": brand_info.get('website', ''),
                                    "max_competitors": 3,
                                    "max_pages_per_site": 1
                                },
                                download_path_template="/download/json/{job_id}",
                                session_id=session_id
                            )
                            logger.info("Gap analysis completed")
                        except Exception as e:
                            logger.warning(f"Gap analysis failed: {e}, continuing without it")

                        # Reddit community intelligence (non-blocking)
                        reddit_insights = {}
                        try:
                            _kw_list = keywords_data.get("keywords", [])[:8] if isinstance(keywords_data, dict) else []
                            if _kw_list:
                                reddit_insights = _call_reddit_research(
                                    _kw_list, brand_info.get("brand_name", "")
                                )
                        except Exception as _re:
                            logger.warning(f"Reddit research skipped: {_re}")

                        business_context = f"""
=== BUSINESS PROFILE ===
Brand: {brand_info.get('brand_name', 'My Business')}
Industry: {brand_info.get('industry', 'General')}
Location: {brand_info.get('location', 'N/A')}
Contact: {brand_info.get('contacts', 'N/A')}

Description: {brand_info.get('description', req.message)}
Target Audience: {brand_info.get('target_audience', 'General audience')}
Unique Selling Points:
{chr(10).join(['- ' + usp for usp in brand_info.get('unique_selling_points', ['Quality products', 'Excellent service'])])}

=== USER REQUEST ===
{req.message}

=== COMPETITOR INSIGHTS ===
{gap_analysis.get('content_gaps_summary', 'Focus on unique value proposition') if gap_analysis else 'Emphasize unique strengths and local presence'}

=== REDDIT COMMUNITY INTELLIGENCE ===
{('Trending topics: ' + ', '.join(reddit_insights.get('trending_topics', []))) if reddit_insights.get('trending_topics') else 'No Reddit data available'}
{('Community language: ' + ', '.join(reddit_insights.get('community_language', []))) if reddit_insights.get('community_language') else ''}
{('Competitor mentions: ' + ', '.join(reddit_insights.get('competitor_mentions', []))) if reddit_insights.get('competitor_mentions') else ''}
{chr(10).join(['- ' + a for a in reddit_insights.get('content_angles', [])]) if reddit_insights.get('content_angles') else ''}
{('Community pain points: ' + '; '.join(reddit_insights.get('community_pain_points', []))) if reddit_insights.get('community_pain_points') else ''}
{reddit_insights.get('summary', '')}

Please create a comprehensive, SEO-optimized blog post that:
1. Addresses the user's specific request: {req.message}
2. Highlights the business's unique strengths and location
3. Incorporates the extracted keywords naturally
4. Fills identified content gaps in the market
5. Appeals to the target audience
"""
                        
                        variant_configs = [
                            {
                                "label": "Option A Â· Research-Driven Depth",
                                "tone": "informative",
                                "length": "long",
                                "workflow": primary_workflow,
                                "source": "mabo"
                            },
                            {
                                "label": "Option B Â· Fast Conversion Story",
                                "tone": "persuasive",
                                "length": "medium",
                                "workflow": secondary_workflow,
                                "source": "baseline"
                            }
                        ]
                        
                        response_options = []
                        os.makedirs("previews", exist_ok=True)
                        
                        for variant in variant_configs:
                            try:
                                option_id = f"opt_{uuid.uuid4().hex[:8]}"
                                workflow_cost_estimate = cost_model.estimate_workflow_cost(variant["workflow"]["agents"])
                                blog_html = call_agent_job(
                                    "ContentAgent",
                                    f"{CONTENT_AGENT_BASE}/generate-blog",
                                    {
                                        "business_details": business_context,
                                        "keywords": keywords_data,
                                        "target_tone": variant["tone"],
                                        "blog_length": variant["length"],
                                        "variant_label": variant["label"]
                                    },
                                    download_path_template="/download/html/{job_id}",
                                    result_format="html",
                                    session_id=session_id  # Pass session_id for metrics
                                )
                                
                                content_id = str(uuid.uuid4())
                                preview_path = f"previews/blog_{content_id}.html"
                                with open(preview_path, "w", encoding="utf-8") as f:
                                    f.write(blog_html)
                                
                                keywords_used = keywords_data.get("keywords", [])[:5] if isinstance(keywords_data, dict) else []
                                metadata = {
                                    "brand_name": brand_info.get("brand_name", "My Business"),
                                    "location": brand_info.get("location"),
                                    "industry": brand_info.get("industry"),
                                    "topic": req.message,
                                    "keywords_used": keywords_used,
                                    "option_id": option_id,
                                    "selection_group": state_hash,
                                    "variant_label": variant["label"],
                                    "variant_tone": variant["tone"],
                                    "workflow_name": variant["workflow"]["workflow_name"],
                                    "workflow_agents": variant["workflow"]["agents"],
                                    "workflow_source": variant["source"]
                                }
                                
                                db.save_generated_content(
                                    content_id=content_id,
                                    session_id=session_id,
                                    content_type="blog",
                                    content=blog_html,
                                    preview_url=f"/preview/blog/{content_id}",
                                    metadata=metadata
                                )
                                
                                # --- ðŸ§  SAVE MEMORY (VECTOR DB) ---
                                try:
                                    logger.info(f"Saving vector memory for content {content_id}")
                                    # Create embedding for the text (using topic for now as proxy for full text to be fast)
                                    # Ideally we embed the whole blog, but for speed we embed the topic + description
                                    rich_text = f"{req.message}. {business_context}"
                                    text_embedding = memory.get_text_embedding(rich_text)
                                    
                                    memory_entity = {
                                        "campaign_id": content_id,
                                        "text_vector": text_embedding.tolist() if hasattr(text_embedding, 'tolist') else text_embedding,
                                        "text_model": "all-MiniLM-L6-v2",
                                        "context_metadata": metadata,
                                        "alignment_score": 1.0, # Initial assumption
                                        "source": "orchestrator",
                                        "tags": [brand_info.get("industry", "General")]
                                    }
                                    memory.write_campaign_entity(memory_entity)
                                    logger.info(f"Memory saved for {content_id}")
                                except Exception as mem_err:
                                    logger.warning(f"Failed to save vector memory: {mem_err}")
                                # ----------------------------------

                                db.save_workflow_variant(
                                    option_id=option_id,
                                    session_id=session_id,
                                    content_id=content_id,
                                    workflow_name=variant["workflow"]["workflow_name"],
                                    state_hash=state_hash,
                                    label=variant["label"],
                                    metadata={
                                        "tone": variant["tone"],
                                        "length": variant["length"],
                                        "cost_estimate": workflow_cost_estimate
                                    }
                                )
                                
                                mabo.register_workflow_execution(
                                    content_id=content_id,
                                    state_hash=state_hash,
                                    action=variant["workflow"]["workflow_name"],
                                    cost=workflow_cost_estimate["total_cost"],
                                    execution_time=workflow_cost_estimate["total_time"]
                                )
                                
                                _critic_text = blog_html[:1000] if blog_html else ""
                                _critic_brand = brand_info.get("brand_name", "")
                                _critic_data = _call_critic_sync(
                                    content_id, _critic_text, "blog", _critic_brand, req.message
                                )

                                # Feed critic score into MABO as an immediate quality reward
                                if _critic_data and _critic_data.get("overall") is not None:
                                    mabo.update_engagement_metrics(
                                        content_id, float(_critic_data["overall"])
                                    )
                                    if _critic_data.get("passed"):
                                        mabo.update_content_approval(content_id, approved=True)
                                    logger.info(
                                        f"[MABO] Blog critic reward fed: content={content_id} "
                                        f"overall={_critic_data['overall']:.2f} passed={_critic_data.get('passed')}"
                                    )
                                    # Score the prompt version that generated this content
                                    try:
                                        from prompt_optimizer import score_latest_for_agent
                                        score_latest_for_agent(
                                            "content_agent", "blog",
                                            float(_critic_data["overall"])
                                        )
                                    except Exception as _pe:
                                        logger.warning(f"[PromptOptimizer] Blog scoring skipped: {_pe}")

                                response_options.append({
                                    "option_id": option_id,
                                    "label": variant["label"],
                                    "tone": variant["tone"].title(),
                                    "workflow_name": variant["workflow"]["workflow_name"],
                                    "workflow_agents": variant["workflow"]["agents"],
                                    "cost": workflow_cost_estimate["total_cost"],
                                    "cost_display": cost_model.format_credits_display(
                                        workflow_cost_estimate.get("credits_estimate")
                                        or cost_model.usd_cost_to_credits(workflow_cost_estimate["total_cost"])
                                    ),
                                    "preview_url": f"/preview/blog/{content_id}",
                                    "content_id": content_id,
                                    "content_type": "blog",
                                    "state_hash": state_hash,
                                    "html_code": blog_html,  # ← Full HTML code included for programmatic use
                                    "critic": _critic_data,
                                })
                            except Exception as variant_error:
                                logger.error(f"Variant generation failed ({variant['label']}): {variant_error}", exc_info=True)
                                continue
                        
                        if response_options:
                            option_lines = "\n".join([
                                f"- {opt['label']}: {opt['tone']} tone Â· {opt['cost_display']} Â· workflow `{opt['workflow_name']}`"
                                for opt in response_options
                            ])
                            response_text = f"""ðŸ“ **Two Draft Blogs Ready**

I've produced two variations for *{brand_info.get('brand_name', 'your brand')}*. Review the cards below and pick the one that best fits your campaign.

{option_lines}

Tap a card to preview and lock in your preferred option. Once you choose, I'll tailor the workflow and budget around it."""
                        else:
                            response_text = "âš ï¸ I couldn't generate the blog variations right now. Please try again or adjust your prompt."
                    except Exception as e:
                        logger.error(f"Blog generation error: {e}", exc_info=True)
                        response_text = f"âš ï¸ Blog generation encountered an error: {str(e)}\n\nPlease try again with a different topic."
                except Exception as e:
                    logger.error(f"Blog generation setup error: {e}", exc_info=True)
                    response_text = f"âš ï¸ Blog generation encountered an error: {str(e)}\n\nPlease try again with a different topic."
            else:
                # Missing required fields - response_text already set above asking for info
                pass
        
        elif intent == "social_post":
            # --- Platform selection gate ---
            chosen_platform = (
                extracted_params.get("platform")
                or req.platform  # type: ignore[attr-defined]
                or _detect_platform_from_text(req.message)
            )
            if chosen_platform:
                chosen_platform = chosen_platform.lower().strip()
                # Normalise: "x" -> "twitter"
                if chosen_platform == "x":
                    chosen_platform = "twitter"
            else:
                # No platform specified â€” ask and park the request
                import time as _time
                _pending_platform[session_id] = {
                    "original_message": req.message,
                    "timestamp": _time.time()
                }
                _q = (
                    "Which platform would you like the post for?\n"
                    "**Twitter/X** or **Instagram**?"
                )
                db.save_message(session_id, "assistant", _q, formatted_content=_q)
                return {
                    "response": _q,
                    "session_id": session_id,
                    "intent": "social_post",
                    "content_preview_id": None,
                    "workflow_cost": None,
                    "seo_result": None,
                    "response_options": None
                }

            # If a URL is present, check if it's a different brand than stored â€” re-extract if so
            url = extracted_params.get("url") or await router.extract_url_from_message(req.message)
            if url:
                try:
                    from urllib.parse import urlparse as _up
                    new_domain = _up(url).netloc.replace('www.', '').lower().split('.')[0]
                    existing = db.get_brand_profile(user_id, req.active_brand)
                    needs_reextract = True
                    if existing:
                        # Check website_url column first, then metadata.website
                        stored_website = existing.get('website_url') or ''
                        if not stored_website:
                            meta = existing.get('metadata')
                            if isinstance(meta, str):
                                import json as _json
                                meta = _json.loads(meta) if meta else {}
                            stored_website = (meta or {}).get('website', '') if isinstance(meta, dict) else ''
                        if stored_website:
                            stored_domain = _up(stored_website).netloc.replace('www.', '').lower().split('.')[0]
                            needs_reextract = (new_domain != stored_domain)
                        # else: no stored website â€” always re-extract
                    if needs_reextract:
                        logger.info(f"New URL domain '{new_domain}' â€” re-extracting brand for social post")
                        try:
                            crawl_result = call_agent_job(
                                "WebCrawler", f"{CRAWLER_BASE}/crawl",
                                {"start_url": url, "max_pages": 3},
                                download_path_template="/download/{job_id}"
                            )
                            crawled_for_brand = crawl_result.get("extracted_text", "")
                        except Exception as _ce:
                            logger.warning(f"Crawl for brand extract failed: {_ce}")
                            crawled_for_brand = ""
                        await extract_brand_info(
                            user_id, req.message, url=url,
                            crawled_data=crawled_for_brand,
                            conversation_history=history_for_router,
                            force_new=True,
                            active_brand=req.active_brand
                        )
                except Exception as _ue:
                    logger.warning(f"URL brand-check failed (social): {_ue}")

            # Check if we have required business details BEFORE starting generation
            brand_profile = db.get_brand_profile(user_id, req.active_brand)
            brand_info = None
            
            if brand_profile:
                brand_info = normalize_brand_info(brand_profile)
                # Validate essential fields
                if not brand_info.get('brand_name') or brand_info.get('brand_name') == 'My Business':
                    response_text = "I need your business name to create personalized social media content. What's your business or brand name?"
                    # Don't proceed with generation
                elif not brand_info.get('industry') or brand_info.get('industry') in ['General', '']:
                    response_text = f"Thanks! I have your business name ({brand_info.get('brand_name')}). What industry is your business in? (e.g., Restaurant, E-commerce, Tech, Healthcare, etc.)"
                    # Don't proceed with generation
                else:
                    # All required fields present - proceed with generation
                    response_text = "Creating multiple social angles for you..."
                    # url already extracted at top of social_post block
                    crawled_data = None
                    
                    if url:
                        try:
                            logger.info(f"Crawling website: {url}")
                            crawl_result = call_agent_job(
                                "WebCrawler",
                                f"{CRAWLER_BASE}/crawl",
                                {"start_url": url, "max_pages": 3},
                                download_path_template="/download/{job_id}"
                            )
                            crawled_data = crawl_result.get("extracted_text", "")
                            logger.info(f"Website crawled successfully: {len(crawled_data)} characters")
                        except Exception as e:
                            logger.warning(f"Website crawl failed: {e}, continuing without crawled data")
                    
                    logger.info(f"âœ“ Using brand profile: {brand_info.get('brand_name')}")
            else:
                # No brand profile - url already extracted at top of social_post block
                crawled_data = None
                
                if url:
                    try:
                        logger.info(f"Crawling website: {url}")
                        crawl_result = call_agent_job(
                            "WebCrawler",
                            f"{CRAWLER_BASE}/crawl",
                            {"start_url": url, "max_pages": 3},
                            download_path_template="/download/{job_id}"
                        )
                        crawled_data = crawl_result.get("extracted_text", "")
                        logger.info(f"Website crawled successfully: {len(crawled_data)} characters")
                    except Exception as e:
                        logger.warning(f"Website crawl failed: {e}, continuing without crawled data")
                
                # Try to extract brand info from conversation
                brand_info = await extract_brand_info(
                    user_id,
                    req.message,
                    url=url,
                    crawled_data=crawled_data,
                    conversation_history=history_for_router,
                    active_brand=req.active_brand
                )
                
                # Check if essential fields are present
                if not brand_info.get('brand_name') or brand_info.get('brand_name') == 'My Business':
                    response_text = "I need your business name to create personalized social media content. What's your business or brand name?"
                    brand_info = None  # Don't proceed
                elif not brand_info.get('industry') or brand_info.get('industry') in ['General', '']:
                    response_text = f"Thanks! I have your business name ({brand_info.get('brand_name')}). What industry is your business in? (e.g., Restaurant, E-commerce, Tech, Healthcare, etc.)"
                    brand_info = None  # Don't proceed
                else:
                    logger.info(f"âœ“ Brand info extracted from conversation: {brand_info.get('brand_name')} in {brand_info.get('location', 'N/A')}")
                    response_text = "Creating multiple social angles for you..."
            
            # Only proceed with generation if we have valid brand_info
            if brand_info and brand_info.get('brand_name') and brand_info.get('brand_name') != 'My Business' and brand_info.get('industry') and brand_info.get('industry') not in ['General', '']:
                try:
                    business_context_for_keywords = f"""
Business: {brand_info.get('brand_name', 'My Business')}
Industry: {brand_info.get('industry', 'General')}
Location: {brand_info.get('location', 'N/A')}
Description: {brand_info.get('description', '')}
Target Audience: {brand_info.get('target_audience', '')}
Unique Selling Points: {', '.join(brand_info.get('unique_selling_points', []))}

User Request: {req.message}

{"Website Content Summary: " + crawled_data[:2000] if crawled_data else ""}
"""
                    logger.info("Extracting keywords from business context")
                    keywords_data = call_agent_job(
                        "KeywordExtractor",
                        f"{KEYWORD_EXTRACTOR_BASE}/extract-keywords",
                        {"customer_statement": business_context_for_keywords, "max_results": 8},
                        download_path_template="/download/{job_id}"
                    )
                    
                    gap_analysis = None
                    try:
                        logger.info("Running competitor gap analysis")
                        product_desc = f"{brand_info.get('industry', 'Business')} in {brand_info.get('location', 'N/A')}. {brand_info.get('description', '')}"
                        gap_analysis = call_agent_job(
                            "CompetitorGapAnalyzer",
                            f"{GAP_ANALYZER_BASE}/analyze-keyword-gap",
                            {
                                "company_name": brand_info.get('brand_name', 'My Business'),
                                "product_description": product_desc,
                                "company_url": brand_info.get('website', ''),
                                "max_competitors": 3,
                                "max_pages_per_site": 1
                            },
                            download_path_template="/download/json/{job_id}"
                        )
                        logger.info("Gap analysis completed")
                    except Exception as e:
                        logger.warning(f"Gap analysis failed: {e}, continuing without it")

                    # Reddit community intelligence (non-blocking)
                    reddit_insights_social = {}
                    try:
                        _kw_list_s = keywords_data.get("keywords", [])[:8] if isinstance(keywords_data, dict) else []
                        if _kw_list_s:
                            reddit_insights_social = _call_reddit_research(
                                _kw_list_s, brand_info.get("brand_name", "")
                            )
                    except Exception as _re:
                        logger.warning(f"Reddit research (social) skipped: {_re}")

                    mabo = mabo_agent.get_mabo_agent()
                    state_context = mabo.create_state_from_context(
                        intent=intent,
                        user_id=user_id,
                        content_type="social",
                        has_brand_profile=brand_profile is not None
                    )
                    state_hash = state_context["state_hash"]
                    primary_workflow = mabo.get_optimized_workflow_details(state_context, use_mabo=True)
                    workflow_cost = cost_model.estimate_workflow_cost(primary_workflow["agents"])
                    secondary_workflow = mabo.get_alternative_workflow_details(
                        intent,
                        state_context,
                        exclude_workflow=primary_workflow["workflow_name"]
                    )
                    
                    base_social_context = {
                        "keywords": keywords_data,
                        "brand_name": brand_info.get("brand_name", "My Business"),
                        "industry": brand_info.get("industry", ""),
                        "location": brand_info.get("location", ""),
                        "target_audience": brand_info.get("target_audience", ""),
                        "unique_selling_points": brand_info.get("unique_selling_points", []),
                        "competitor_insights": " | ".join(filter(None, [
                            gap_analysis.get("content_gaps_summary", "") if gap_analysis else "",
                            ("Reddit trends: " + ", ".join(reddit_insights_social.get("trending_topics", []))) if reddit_insights_social.get("trending_topics") else "",
                            ("Community language: " + ", ".join(reddit_insights_social.get("community_language", []))) if reddit_insights_social.get("community_language") else "",
                            ("Competitor mentions: " + ", ".join(reddit_insights_social.get("competitor_mentions", []))) if reddit_insights_social.get("competitor_mentions") else "",
                        ])),
                        "user_request": req.message,
                        "platforms": req.platforms if hasattr(req, 'platforms') and req.platforms else ["twitter", "instagram"],
                        "tone": "professional"
                    }
                    
                    variant_configs = [
                        {
                            "label": "Option A Â· Authority Launch",
                            "tone": "professional",
                            "workflow": primary_workflow,
                            "source": "mabo"
                        },
                        {
                            "label": "Option B Â· Conversational Buzz",
                            "tone": "playful",
                            "workflow": secondary_workflow,
                            "source": "baseline"
                        }
                ]
                    
                    response_options = []
                    
                    for variant in variant_configs:
                        try:
                            option_id = f"opt_{uuid.uuid4().hex[:8]}"
                            workflow_cost_estimate = cost_model.estimate_workflow_cost(variant["workflow"]["agents"])
                            variant_payload = dict(base_social_context)
                            variant_payload["tone"] = variant["tone"]
                            
                            social_data = call_agent_job(
                                "ContentAgent",
                                f"{CONTENT_AGENT_BASE}/generate-social",
                                variant_payload
                            )
                            
                            posts = social_data.get('posts', {})
                            twitter_post = posts.get('twitter', {})
                            instagram_post = posts.get('instagram', {})
                            # Use only the chosen platform's copy
                            if chosen_platform == "twitter":
                                primary_copy = twitter_post.get('copy', '')
                                secondary_copy = ''
                            else:
                                primary_copy = instagram_post.get('copy', '')
                                secondary_copy = ''
                            post_preview = json.dumps({chosen_platform: primary_copy})
                            image_prompts = social_data.get('image_prompts', [])
                            image_prompt = image_prompts[0] if image_prompts else f"Professional, high-quality social media image for {brand_info.get('brand_name', 'brand')} in {brand_info.get('industry', 'business')} industry, located in {brand_info.get('location', 'their area')}, showcasing {req.message[:50]}, {brand_info.get('unique_selling_points', ['quality service'])[0] if brand_info.get('unique_selling_points') else 'professional service'}, photorealistic style, modern design"
                            
                            # Get reference images from brand profile (S3 URLs)
                            reference_images = []
                            try:
                                brand_profile = db.get_brand_profile(user_id, req.active_brand)
                                if brand_profile:
                                    # Get logo URL if available
                                    logo_url = brand_profile.get('logo_url')
                                    if logo_url:
                                        reference_images.append(logo_url)
                                    
                                    # Get other reference images from metadata
                                    metadata = brand_profile.get('metadata', {})
                                    if isinstance(metadata, dict):
                                        assets = metadata.get('assets', {})
                                        # Get reference_image assets
                                        ref_images = assets.get('reference_image', [])
                                        for asset in ref_images:
                                            if isinstance(asset, dict) and asset.get('url'):
                                                reference_images.append(asset['url'])
                                        # Also include item images
                                        item_images = assets.get('item', [])
                                        for asset in item_images:
                                            if isinstance(asset, dict) and asset.get('url'):
                                                reference_images.append(asset['url'])
                            except Exception as e:
                                logger.debug(f"Error getting reference images from brand profile: {e}")
                            
                            # Generate image during preview (before approval) - SEQUENTIAL (1 per variant)
                            image_paths = []
                            image_path = None
                            try:
                                logger.info(f"Generating preview image for variant {variant['label']} [SEQUENTIAL]...")
                                # Build comprehensive image prompt with business context
                                # Generate only 1 image per variant sequentially
                                if image_prompts:
                                    single_image_prompt = image_prompts[0]  # Take first prompt only
                                    detailed_prompt = f"{single_image_prompt}. You MUST prominently include the text '{brand_info.get('brand_name', '')}' exactly as spelled. Brand: {brand_info.get('brand_name', '')}. Industry: {brand_info.get('industry', '')}. Location: {brand_info.get('location', '')}. Target audience: {brand_info.get('target_audience', '')}. Unique selling points: {', '.join(brand_info.get('unique_selling_points', []))}"
                                    logger.info(f"[SEQ] Generating image {len(response_options)+1}/{len(variant_configs)} (variant: {variant['label']})...")
                                    path = generate_image_with_runway(detailed_prompt, reference_images if reference_images else None)
                                    if path:
                                        image_paths.append(path)
                                        logger.info(f"[SEQ] ✓ Image generated: {path}")
                                    else:
                                        logger.warning(f"[SEQ] ✗ Image generation returned None")
                                else:
                                    # Fallback if no prompts provided
                                    detailed_prompt = f"{image_prompt}. You MUST prominently include the text '{brand_info.get('brand_name', '')}' exactly as spelled. Brand: {brand_info.get('brand_name', '')}. Industry: {brand_info.get('industry', '')}. Location: {brand_info.get('location', '')}. Target audience: {brand_info.get('target_audience', '')}. Unique selling points: {', '.join(brand_info.get('unique_selling_points', []))}"
                                    logger.info(f"[SEQ] Using fallback image prompt...")
                                    path = generate_image_with_runway(detailed_prompt, reference_images if reference_images else None)
                                    if path:
                                        image_paths.append(path)
                                        logger.info(f"[SEQ] ✓ Fallback image generated: {path}")
                                
                                image_path = image_paths[0] if image_paths else None
                                logger.info(f"[SEQ] Image generation complete for variant {variant['label']}")
                            except Exception as img_error:
                                logger.warning(f"Preview image generation failed (will generate on approval): {img_error}")
                                image_path = None
                            
                            content_id = str(uuid.uuid4())
                            metadata = {
                                "brand_name": brand_info.get("brand_name", "My Business"),
                                "location": brand_info.get("location"),
                                "industry": brand_info.get("industry"),
                                "target_audience": brand_info.get("target_audience"),
                                "unique_selling_points": brand_info.get("unique_selling_points", []),
                                "platforms": [chosen_platform],
                                "hashtags": twitter_post.get('hashtags', []),
                                "keywords_used": keywords_data.get("keywords", [])[:5] if isinstance(keywords_data, dict) else [],
                                "image_prompt": image_prompt,
                                "image_path": image_path,  # Store primary generated image path
                                "image_paths": image_paths if 'image_paths' in locals() and image_paths else ([image_path] if image_path else []), # All generated image paths
                                "reference_images": reference_images if reference_images else [],
                                "option_id": option_id,
                                "selection_group": state_hash,
                                "variant_label": variant["label"],
                                "variant_tone": variant["tone"],
                                "workflow_name": variant["workflow"]["workflow_name"],
                                "workflow_agents": variant["workflow"]["agents"],
                                "workflow_source": variant["source"],
                                "post_copy": {
                                    "twitter": twitter_post.get('copy', ''),
                                    "instagram": instagram_post.get('copy', '')
                                },
                                "full_post_data": social_data
                            }
                            
                            # Set preview_url to image if available
                            # If image_path is already a full URL (Runway CDN), use it directly; otherwise wrap it
                            if image_path:
                                if image_path.startswith('http://') or image_path.startswith('https://'):
                                    preview_url = image_path  # Use Runway URL directly
                                else:
                                    preview_url = f"/preview/image/{image_path}"  # Wrap local paths
                            else:
                                preview_url = None
                            
                            db.save_generated_content(
                                content_id=content_id,
                                session_id=session_id,
                                content_type="post",
                                content=post_preview,
                                preview_url=preview_url,
                                metadata=metadata
                            )

                            # --- ðŸ§  SAVE MEMORY (VECTOR DB) ---
                            try:
                                logger.info(f"Saving vector memory for social content {content_id}")
                                # Text Memory
                                rich_text = f"Social Post ({variant['tone']}): {req.message}. Twitter: {twitter_post.get('copy', '')}. Instagram: {instagram_post.get('copy', '')}"
                                text_embedding = memory.get_text_embedding(rich_text)
                                
                                # Visual Memory (if image exists)
                                visual_embedding = None
                                if image_path and os.path.exists(image_path):
                                    try:
                                        from tools import embedding
                                        # Load image model on demand
                                        img_model = embedding.load_image_model()
                                        visual_embedding = embedding.embed_image(img_model, image_path).tolist()
                                        logger.info("Generated visual embedding for social image")
                                    except Exception as ve:
                                        logger.warning(f"Visual embedding failed: {ve}")

                                memory_entity = {
                                    "campaign_id": content_id,
                                    "text_vector": text_embedding,
                                    "visual_vector": visual_embedding,
                                    "text_model": "all-MiniLM-L6-v2",
                                    "visual_model": "clip-ViT-B-32" if visual_embedding else None,
                                    "context_metadata": metadata,
                                    "alignment_score": 1.0,
                                    "source": "orchestrator",
                                    "tags": ["social", brand_info.get("industry", "General"), variant["tone"]]
                                }
                                memory.write_campaign_entity(memory_entity)
                                logger.info(f"Social memory saved for {content_id}")
                            except Exception as mem_err:
                                logger.warning(f"Failed to save social vector memory: {mem_err}")
                            # ----------------------------------
                            
                            db.save_workflow_variant(
                                option_id=option_id,
                                session_id=session_id,
                                content_id=content_id,
                                workflow_name=variant["workflow"]["workflow_name"],
                                state_hash=state_hash,
                                label=variant["label"],
                                metadata={
                                    "tone": variant["tone"],
                                    "cost_estimate": workflow_cost_estimate
                                }
                            )
                            
                            mabo.register_workflow_execution(
                                content_id=content_id,
                                state_hash=state_hash,
                                action=variant["workflow"]["workflow_name"],
                                cost=workflow_cost_estimate["total_cost"],
                                execution_time=workflow_cost_estimate["total_time"]
                            )
                            
                            _social_text = primary_copy
                            _critic_data_social = _call_critic_sync(
                                content_id, _social_text, "social_post",
                                brand_info.get("brand_name", ""), req.message
                            )

                            # Feed critic score into MABO as an immediate quality reward
                            if _critic_data_social and _critic_data_social.get("overall") is not None:
                                mabo.update_engagement_metrics(
                                    content_id, float(_critic_data_social["overall"])
                                )
                                if _critic_data_social.get("passed"):
                                    mabo.update_content_approval(content_id, approved=True)
                                logger.info(
                                    f"[MABO] Social critic reward fed: content={content_id} "
                                    f"overall={_critic_data_social['overall']:.2f} passed={_critic_data_social.get('passed')}"
                                )
                                # Score the prompt version that generated this content
                                try:
                                    from prompt_optimizer import score_latest_for_agent
                                    score_latest_for_agent(
                                        "content_agent", "social_post",
                                        float(_critic_data_social["overall"])
                                    )
                                except Exception as _pe:
                                    logger.warning(f"[PromptOptimizer] Social scoring skipped: {_pe}")

                            response_options.append({
                                "option_id": option_id,
                                "label": variant["label"],
                                "tone": variant["tone"].title(),
                                "workflow_name": variant["workflow"]["workflow_name"],
                                "workflow_agents": variant["workflow"]["agents"],
                                "cost": workflow_cost_estimate["total_cost"],
                                "cost_display": cost_model.format_credits_display(
                                    workflow_cost_estimate.get("credits_estimate")
                                    or cost_model.usd_cost_to_credits(workflow_cost_estimate["total_cost"])
                                ),
                                "content_id": content_id,
                                "content_type": "post",
                                "state_hash": state_hash,
                                "platform": chosen_platform,
                                "twitter_copy": primary_copy if chosen_platform == "twitter" else "",
                                "instagram_copy": primary_copy if chosen_platform == "instagram" else "",
                                "hashtags": (twitter_post if chosen_platform == "twitter" else instagram_post).get('hashtags', []),
                                "preview_url": preview_url,
                                "preview_text": f"{variant['label']} ready for {chosen_platform.title()}.",
                                "critic": _critic_data_social,
                            })
                        except Exception as variant_error:
                            logger.error(f"Social variant failed ({variant['label']}): {variant_error}", exc_info=True)
                            continue
                    
                    if response_options:
                        platform_label = chosen_platform.title().replace("Twitter", "Twitter/X")
                        response_text = f"ðŸ“£ **{len(response_options)} {platform_label} Post Concept{'s' if len(response_options) > 1 else ''} Ready**\n\nReview the cards below â€” each shows the generated image and {platform_label} copy. Hit **Approve & Post** on the one you like, or tap ðŸ”„ to regenerate the image."
                    else:
                        response_text = "âš ï¸ I couldn't generate social concepts right now. Please try again."
                except Exception as e:
                    logger.error(f"Social post error: {e}", exc_info=True)
                    response_text = f"âš ï¸ Post generation error: {str(e)}\n\nPlease try again with a different prompt."
            else:
                # Missing required fields - response_text already set above asking for info
                pass
        
        elif intent == "campaign_post":
            # Execute immediate campaign post from chat
            platform = (extracted_params.get("platform") or "instagram").lower()
            topic = (
                extracted_params.get("content_text")
                or extracted_params.get("topic")
                or extracted_params.get("theme")
                or req.message
            )

            # Basic normalization for common platform aliases
            if platform in {"twitter", "x", "tweet"}:
                platform = "x"
            elif platform in {"ig", "insta"}:
                platform = "instagram"

            if not topic or len(topic.strip()) < 5:
                response_text = "Please provide what you want to post. Example: Post campaign about eco-friendly water bottles on Instagram."
            else:
                try:
                    from agent_adapters.campaign_adapter import execute_campaign_post
                    post_result = await execute_campaign_post(
                        user_id=user_id,
                        platform=platform,
                        content=topic,
                        content_id=None,
                        ai_generate=True,
                        brand_name=req.active_brand or (brand_info.get("brand_name") if 'brand_info' in locals() else None),
                    )

                    status = post_result.get("status", "unknown")
                    response_text = f"Campaign post status: **{status}** on **{platform}**."
                    if post_result.get("post_url"):
                        response_text += f"\n\nPublished URL: {post_result.get('post_url')}"
                    if post_result.get("error"):
                        response_text += f"\n\nError: {post_result.get('error')}"
                except Exception as e:
                    logger.error(f"campaign_post execution failed: {e}", exc_info=True)
                    response_text = f"Couldn't post the campaign right now: {str(e)}"

        elif intent == "image_generation":
            _brand_ctx = _build_user_context_summary(user_id, req.active_brand)
            response_text = await router.generate_conversational_response(
                req.message, history_for_router, brand_context=_brand_ctx
            )

        elif intent == "competitor_research":
            brand_profile = db.get_brand_profile(user_id, req.active_brand)
            if not brand_profile:
                response_text = (
                    "I need your business details to find competitors. "
                    "Please share your **business name** and **industry** "
                    "(or say \"setup my business\" to configure your profile)."
                )
            else:
                brand_info = normalize_brand_info(brand_profile)
                try:
                    response_text = f"\U0001f50d Analysing competitors for **{brand_info.get('brand_name')}**..."
                    product_desc = (
                        f"{brand_info.get('industry', 'Business')} "
                        f"in {brand_info.get('location', 'N/A')}. "
                        f"{brand_info.get('description', '')}"
                    )
                    gap_result = call_agent_job(
                        "CompetitorGapAnalyzer",
                        f"{GAP_ANALYZER_BASE}/analyze-keyword-gap",
                        {
                            "company_name": brand_info.get("brand_name", "My Business"),
                            "product_description": product_desc,
                            "company_url": brand_info.get("website", ""),
                            "max_competitors": 5,
                            "max_pages_per_site": 2,
                        },
                        download_path_template="/download/json/{job_id}"
                    )
                    competitors = gap_result.get("competitors", [])
                    gaps_summary = gap_result.get("content_gaps_summary", "")
                    top_keywords = gap_result.get("top_competitor_keywords", [])

                    if competitors:
                        comp_lines = "\n".join([
                            f"- **{c.get('name', c)}**" +
                            (f" â€” {c.get('url', '')}" if isinstance(c, dict) and c.get('url') else "")
                            for c in competitors[:5]
                        ])
                        kw_lines = (
                            "\n\n\U0001f4cc **Keywords they rank for:** "
                            + ", ".join(top_keywords[:8])
                        ) if top_keywords else ""
                        response_text = (
                            f"\U0001f3c6 **Top Competitors for {brand_info.get('brand_name')}** "
                            f"({brand_info.get('industry', 'your industry')})"
                            f"\n\n{comp_lines}"
                            f"{kw_lines}"
                            f"\n\n\U0001f4ca **Market Gaps You Can Own:**\n{gaps_summary}"
                            f"\n\nWould you like me to **create content** targeting these gaps, or run a full **SEO audit**?"
                        )
                    else:
                        _brand_ctx = _build_user_context_summary(user_id, req.active_brand)
                        response_text = await router.generate_conversational_response(
                            req.message, history_for_router, brand_context=_brand_ctx
                        )
                except Exception as _ce:
                    logger.warning(f"Competitor analysis failed: {_ce}")
                    _brand_ctx = _build_user_context_summary(user_id, req.active_brand)
                    response_text = await router.generate_conversational_response(
                        req.message, history_for_router, brand_context=_brand_ctx
                    )

        elif intent == "deep_research":
            _brand_ctx = _build_user_context_summary(user_id, req.active_brand)
            response_text = await router.generate_conversational_response(
                req.message, history_for_router, brand_context=_brand_ctx
            )

        elif intent == "critic_review":
            _brand_ctx = _build_user_context_summary(user_id, req.active_brand)
            response_text = await router.generate_conversational_response(
                req.message, history_for_router, brand_context=_brand_ctx
            )

        elif intent == "metrics_report":
            # Show metrics dashboard link
            response_text = "ðŸ“Š **Social Media Metrics**\n\nView your performance metrics on the dashboard:\n\n[Open Metrics Dashboard](/metrics.html)\n\nI can also show specific metrics here. What would you like to see?"
        
        else:
            # Fallback â€” always provide brand context so generic answers are relevant
            _brand_ctx = _build_user_context_summary(user_id, req.active_brand)
            response_text = await router.generate_conversational_response(
                req.message, history_for_router, brand_context=_brand_ctx
            )
        
        # Check if clarification is needed for business details
        clarification_request = None
        
        # Check for required URL first
        if routing_result.get("requires_url") and not extracted_params.get("url"):
            clarification_request = {
                "type": "missing_url",
                "message": "I need a website URL to analyze. Please provide the URL of the website you'd like me to check.",
                "field": "url",
                "required": True
            }
        # Check for required business details for content generation
        elif intent in ["blog_generation", "social_post"]:
            brand_profile = db.get_brand_profile(user_id, req.active_brand)
            missing_fields = []
            
            if not brand_profile:
                # No brand profile at all - need all essential fields
                missing_fields = ["brand_name", "industry"]
                clarification_request = {
                    "type": "missing_brand_info",
                    "message": "I need some information about your business to create personalized content. Please provide:\n\n1. **Business Name** (required)\n2. **Industry** (required - e.g., 'Restaurant', 'E-commerce', 'Tech Startup')\n3. **Location** (optional but helpful - city/state)\n\nYou can provide this information in your message, or say 'setup business' to configure it step by step.",
                    "fields": missing_fields,
                    "required": True,
                    "intent": intent
                }
            else:
                # Brand profile exists - check if essential fields are present
                brand_info = normalize_brand_info(brand_profile)
                
                if not brand_info.get('brand_name') or brand_info.get('brand_name') == 'My Business':
                    missing_fields.append("brand_name")
                if not brand_info.get('industry') or brand_info.get('industry') in ['General', '']:
                    missing_fields.append("industry")
                
                if missing_fields:
                    field_names = {
                        "brand_name": "Business Name",
                        "industry": "Industry"
                    }
                    missing_list = [field_names.get(f, f) for f in missing_fields]
                    clarification_request = {
                        "type": "missing_brand_info",
                        "message": f"I need some additional information about your business to create personalized content. Please provide:\n\n" + "\n".join([f"- **{name}** (required)" for name in missing_list]) + "\n\nYou can provide this information in your message.",
                        "fields": missing_fields,
                        "required": True,
                        "intent": intent,
                        "existing_profile": True
                    }
        
        # Save assistant response
        db.save_message(session_id, "assistant", response_text, formatted_content=response_text)
        
        # Auto-generate session title if this is the first exchange
        if len(history) <= 2:
            messages_for_title = db.get_session_messages(session_id)
            title = await generate_session_title(messages_for_title)
            db.update_session_title(session_id, title)
        
        return ChatResponse(
            session_id=session_id,
            response=response_text,
            formatted_response=response_text,
            intent=intent,
            content_preview_id=content_preview_id,
            workflow_cost=workflow_cost,
            credits_charged=credits_charged,
            credits_balance=credits_balance,
            response_options=response_options,
            clarification_request=clarification_request,
            seo_result=seo_result
        )
    
    except HTTPException:
        if credits_charged > 0 and user_id is not None:
            try:
                credits_balance = db.change_user_credits(
                    user_id,
                    credits_charged,
                    reason="refund:chat_failure",
                    metadata={"session_id": session_id if 'session_id' in locals() else None},
                )
                credits_charged = 0
            except Exception:
                logger.exception("Failed to refund credits after HTTPException")
        raise
    except Exception as e:
        if credits_charged > 0 and user_id is not None:
            try:
                credits_balance = db.change_user_credits(
                    user_id,
                    credits_charged,
                    reason="refund:chat_failure",
                    metadata={"session_id": session_id if 'session_id' in locals() else None},
                )
                credits_charged = 0
            except Exception:
                logger.exception("Failed to refund credits after chat exception")
        logger.error(f"Chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# ==================== CONTENT PREVIEW & APPROVAL ====================

@app.get("/preview/blog/{content_id}")
async def preview_blog(content_id: str):
    """Serve blog preview."""
    try:
        preview_path = f"previews/blog_{content_id}.html"
        if not os.path.exists(preview_path):
            raise HTTPException(status_code=404, detail="Preview not found")
        return FileResponse(preview_path, media_type="text/html")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Preview error: {e}")
        raise HTTPException(status_code=500, detail="Failed to load preview")

@app.get("/preview/image/{image_path:path}")
async def preview_image(image_path: str):
    """Serve generated image preview."""
    try:
        # Security: only allow images from generated_images folder
        if not image_path.startswith("generated_images/"):
            image_path = f"generated_images/{os.path.basename(image_path)}"
        
        if not os.path.exists(image_path):
            raise HTTPException(status_code=404, detail="Image not found")
        
        return FileResponse(image_path, media_type="image/jpeg")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Image preview error: {e}")
        raise HTTPException(status_code=500, detail="Failed to load image")


@app.get("/images")
async def list_generated_images():
    """List all generated images with their preview URLs."""
    img_dir = "generated_images"
    os.makedirs(img_dir, exist_ok=True)
    images = []
    for fname in sorted(os.listdir(img_dir), reverse=True):
        if fname.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")):
            fpath = os.path.join(img_dir, fname)
            try:
                stat = os.stat(fpath)
                images.append({
                    "filename": fname,
                    "url": f"/preview/image/generated_images/{fname}",
                    "size_bytes": stat.st_size,
                    "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                })
            except OSError:
                continue
    return {"images": images, "count": len(images)}


@app.post("/generate-image")
async def generate_image_endpoint(request: Request):
    """Generate an image from a text prompt using RunwayML and return its preview URL."""
    try:
        body = await request.json()
        prompt = body.get("prompt", "").strip()
        if not prompt:
            raise HTTPException(status_code=400, detail="prompt is required")

        reference_images = body.get("reference_images") or []

        # Optional brand context for better image consistency.
        user_id_raw = body.get("user_id")
        brand_name = body.get("brand_name")
        try:
            user_id = int(user_id_raw) if user_id_raw is not None else None
        except (TypeError, ValueError):
            user_id = None

        if user_id:
            try:
                brand_profile = db.get_brand_profile(user_id, brand_name)
                if brand_profile:
                    brand_ctx = normalize_brand_info(brand_profile)

                    # If caller didn't pass references, auto-use uploaded logo/reference assets.
                    if not reference_images:
                        logo_url = brand_profile.get("logo_url")
                        if isinstance(logo_url, str) and logo_url.startswith(("http://", "https://")):
                            reference_images.append(logo_url)

                        metadata = brand_profile.get("metadata", {})
                        if isinstance(metadata, str):
                            try:
                                metadata = json.loads(metadata) if metadata else {}
                            except Exception:
                                metadata = {}

                        if isinstance(metadata, dict):
                            assets = metadata.get("assets", {})
                            for bucket in ("logo", "reference_image", "item"):
                                for asset in assets.get(bucket, [])[:3]:
                                    if isinstance(asset, dict) and isinstance(asset.get("url"), str):
                                        reference_images.append(asset["url"])

                    # Append brand details (including color palette) to prompt.
                    colors = brand_ctx.get("colors", [])
                    if not isinstance(colors, list):
                        colors = [str(colors)] if colors else []
                    colors_text = ", ".join([str(c) for c in colors if c])

                    usp = brand_ctx.get("unique_selling_points", [])
                    if not isinstance(usp, list):
                        usp = [str(usp)] if usp else []
                    usp_text = ", ".join([str(u) for u in usp[:3] if u])

                    brand_context_lines = []
                    if brand_ctx.get("brand_name"):
                        brand_context_lines.append(f"Brand name: {brand_ctx.get('brand_name')}")
                    if brand_ctx.get("industry"):
                        brand_context_lines.append(f"Industry: {brand_ctx.get('industry')}")
                    if brand_ctx.get("target_audience"):
                        brand_context_lines.append(f"Target audience: {brand_ctx.get('target_audience')}")
                    if colors_text:
                        brand_context_lines.append(f"Brand colors: {colors_text}")
                    if usp_text:
                        brand_context_lines.append(f"Brand strengths: {usp_text}")

                    if brand_context_lines:
                        prompt = (
                            f"{prompt}. Keep the visual identity consistent with this brand context: "
                            + " | ".join(brand_context_lines)
                        )
            except Exception as ctx_err:
                logger.warning(f"Could not enrich image prompt from brand profile: {ctx_err}")

        # De-duplicate references while preserving order.
        dedup_refs = []
        seen_refs = set()
        for ref in reference_images:
            if not isinstance(ref, str):
                continue
            ref = ref.strip()
            if not ref or ref in seen_refs:
                continue
            seen_refs.add(ref)
            dedup_refs.append(ref)
        reference_images = dedup_refs

        # generate_image_with_runway is blocking — run in thread pool
        import asyncio
        loop = asyncio.get_event_loop()
        image_path = await loop.run_in_executor(
            None, lambda: generate_image_with_runway(prompt, reference_images or None)
        )
        # Runway can return a direct https URL; keep it as-is.
        if isinstance(image_path, str) and image_path.startswith(("http://", "https://")):
            preview_url = image_path
        else:
            preview_url = f"http://127.0.0.1:8004/preview/image/{image_path}"
        return {"image_path": image_path, "preview_url": preview_url, "status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"/generate-image failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/content/{content_id}/details")
async def get_content_details(content_id: str, authorization: str = Header(None)):
    """Get content details including metadata."""
    try:
        payload = auth.get_current_user(authorization)
        content = db.get_generated_content(content_id)
        
        if not content:
            raise HTTPException(status_code=404, detail="Content not found")
        
        return {
            "id": content['id'],
            "type": content['type'],
            "content": content['content'],
            "status": content['status'],
            "preview_url": content['preview_url'],
            "final_url": content['final_url'],
            "metadata": content['metadata']
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get content details error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get content details")

@app.get("/brand-profile")
async def get_brand_profile_endpoint(authorization: str = Header(None)):
    """Get user's brand profile (latest or default)."""
    try:
        payload = auth.get_current_user(authorization)
        user_id = payload['user_id']

        # Get latest brand profile for user (brand_name is optional, gets most recent)
        brand_profile = db.get_brand_profile(user_id)
        if not brand_profile:
            return {"message": "No brand profile found", "profile": None}

        return {"profile": brand_profile}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get brand profile error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get brand profile")

@app.delete("/brand-profile")
async def delete_brand_profile(authorization: str = Header(None)):
    """Delete user's brand profile (allows re-extraction from new conversation)."""
    try:
        payload = auth.get_current_user(authorization)
        user_id = payload['user_id']
        
        # Delete brand profile to allow fresh extraction
        db.cursor.execute("DELETE FROM brand_profiles WHERE user_id = ?", (user_id,))
        db.connection.commit()
        
        return {"message": "Brand profile deleted. It will be re-extracted from your next conversation."}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete brand profile error: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete brand profile")

@app.post("/content/{content_id}/regenerate-image")
async def regenerate_image(content_id: str, authorization: str = Header(None)):
    """Regenerate the AI image for a social post card without changing the copy."""
    try:
        payload = auth.get_current_user(authorization)
        content = db.get_generated_content(content_id)
        if not content:
            raise HTTPException(status_code=404, detail="Content not found")

        metadata = content.get('metadata', {})
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except Exception:
                metadata = {}

        # Build image prompt from stored prompt or fall back to brand context
        image_prompt = metadata.get('image_prompt')
        if not image_prompt:
            brand_name = metadata.get('brand_name', 'business')
            industry = metadata.get('industry', '')
            location = metadata.get('location', '')
            usps = metadata.get('unique_selling_points', [])
            image_prompt = f"Professional social media image for {brand_name}"
            if industry:
                image_prompt += f" in the {industry} industry"
            if location:
                image_prompt += f" located in {location}"
            if usps:
                image_prompt += f", showcasing {usps[0]}"
            image_prompt += ", photorealistic style, modern design"

        reference_images = metadata.get('reference_images', [])

        try:
            new_image_path = generate_image_with_runway(
                image_prompt, reference_images if reference_images else None
            )
        except Exception as img_err:
            logger.error(f"Image regeneration failed: {img_err}")
            raise HTTPException(status_code=500, detail=f"Image generation failed: {str(img_err)}")

        # If image path is already a full URL (Runway CDN), use it directly; otherwise wrap it
        if new_image_path.startswith('http://') or new_image_path.startswith('https://'):
            new_preview_url = new_image_path  # Use Runway URL directly
        else:
            new_preview_url = f"/preview/image/{new_image_path}"  # Wrap local paths

        # Persist new image path to DB
        metadata['image_path'] = new_image_path
        metadata['image_prompt'] = image_prompt
        db.update_content_metadata(content_id, {"image_path": new_image_path, "image_prompt": image_prompt})

        # Update preview_url column
        with db.get_db_connection() as conn:
            conn.execute(
                "UPDATE generated_content SET preview_url = ? WHERE id = ?",
                (new_preview_url, content_id)
            )

        logger.info(f"Image regenerated for content {content_id}: {new_image_path}")
        return {"preview_url": new_preview_url, "image_path": new_image_path}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Regenerate image error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to regenerate image")


@app.post("/workflow/select")
async def select_workflow_option(req: WorkflowSelectionRequest, authorization: str = Header(None)):
    """Record client selection between workflow variants and update MABO feedback."""
    try:
        payload = auth.get_current_user(authorization)
        user_id = payload["user_id"]
        
        session = db.get_session(req.session_id, user_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        variant = db.get_workflow_variant(req.option_id)
        if not variant:
            raise HTTPException(status_code=404, detail="Option not found")
        
        if variant["session_id"] != req.session_id:
            raise HTTPException(status_code=400, detail="Option does not belong to this session")
        
        state_hash = variant["state_hash"]
        db.mark_variant_selection(req.option_id, True)
        db.clear_variant_selection(req.session_id, state_hash, exclude_option_id=req.option_id)
        
        variants = db.get_workflow_variants(req.session_id, state_hash)
        mabo = mabo_agent.get_mabo_agent()
        
        selected_content_id = variant["content_id"]
        selection_message = f"âœ… Locked in **{variant.get('label', 'your preferred option')}**. I'll continue with workflow `{variant['workflow_name']}`."
        
        for item in variants:
            is_selected = item["option_id"] == req.option_id
            db.update_content_metadata(
                item["content_id"],
                {
                    "selection_status": "selected" if is_selected else "dismissed",
                    "selection_recorded_at": datetime.now().isoformat()
                }
            )
            db.mark_variant_selection(item["option_id"], is_selected)
            mabo.update_content_approval(item["content_id"], approved=is_selected)
        
        db.save_message(req.session_id, "assistant", selection_message, formatted_content=selection_message)
        
        return {
            "message": selection_message,
            "content_id": selected_content_id,
            "state_hash": state_hash
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Workflow selection error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to record selection")

@app.post("/content/{content_id}/approve")
async def approve_content(content_id: str, req: ContentApprovalRequest, background_tasks: BackgroundTasks, authorization: str = Header(None)):
    """Approve and publish content."""
    try:
        payload = auth.get_current_user(authorization)
        
        content = db.get_generated_content(content_id)
        if not content:
            raise HTTPException(status_code=404, detail="Content not found")
        
        if req.approved:
            # Host on S3 or post to social
            if content['type'] == 'blog':
                preview_path = f"previews/blog_{content_id}.html"
                try:
                    s3_url = host_on_s3(preview_path, f"blogs/{content_id}.html")
                except Exception as _s3_err:
                    logger.warning(f"S3 upload skipped ({_s3_err}); using local preview URL")
                    s3_url = f"http://localhost:8080/{os.path.basename(preview_path)}"
                db.update_content_status(content_id, "approved", s3_url)
                return {"message": "Blog approved successfully", "url": s3_url}
            
            elif content['type'] == 'post':
                # Post to social media platforms
                try:
                    metadata = content.get('metadata', {})
                    image_path = metadata.get('image_path') or content.get('preview_url')
                    post_data = metadata.get('post_copy') or {}
                    hashtags = metadata.get('hashtags', [])
                    platforms = metadata.get('platforms', ['twitter', 'instagram'])
                    
                    # Generate image if not exists (skip generation if already have a valid URL)
                    is_valid_image = image_path and (image_path.startswith('http://') or image_path.startswith('https://') or os.path.exists(image_path))
                    if not is_valid_image:
                        logger.info("Image not found, generating new image...")
                        # Use the stored image_prompt from metadata, or build a comprehensive one
                        stored_prompt = metadata.get('image_prompt')
                        if stored_prompt:
                            image_prompt = stored_prompt
                        else:
                            # Build comprehensive prompt with business context
                            brand_name = metadata.get('brand_name', 'business')
                            industry = metadata.get('industry', '')
                            location = metadata.get('location', '')
                            usps = metadata.get('unique_selling_points', [])
                            image_prompt = f"Professional, high-quality social media image for {brand_name}"
                            if industry:
                                image_prompt += f" in the {industry} industry"
                            if location:
                                image_prompt += f" located in {location}"
                            if usps:
                                image_prompt += f", showcasing {usps[0]}"
                            image_prompt += ", photorealistic style, modern design"
                        
                        reference_images = metadata.get('reference_images', [])
                        try:
                            image_path = generate_image_with_runway(image_prompt, reference_images if reference_images else None)
                            logger.info(f"Image generated: {image_path}")
                            # Update metadata with new image path
                            metadata['image_path'] = image_path
                            db.update_content_metadata(content_id, {"image_path": image_path})
                        except Exception as img_error:
                            logger.warning(f"Image generation skipped (no key or failed): {img_error}")
                            image_path = None  # proceed without image
                    
                    # Post to social media platforms
                    post_urls = {}
                    errors = []
                    
                    for platform in platforms:
                        try:
                            logger.info(f"Posting to {platform}...")
                            copy = post_data.get(platform) if isinstance(post_data, dict) else None
                            if not copy:
                                copy = content['content']
                                if isinstance(copy, str):
                                    copy = copy.replace("Twitter:", "").replace("Instagram:", "").strip()
                            text_with_tags = f"{copy}\n\n{' '.join(hashtags)}" if hashtags else copy
                            post_url = post_to_social(platform, text_with_tags, image_path)
                            post_urls[platform] = post_url
                            logger.info(f"âœ“ Posted to {platform}: {post_url}")
                            
                            # Save to social_posts for metrics tracking
                            db.save_social_post(content_id, platform, post_url)
                            
                        except Exception as e:
                            error_msg = f"{platform}: {str(e)}"
                            errors.append(error_msg)
                            logger.error(f"Failed to post to {platform}: {e}")
                    
                    # Update content status with URLs
                    if post_urls:
                        final_url = ", ".join([f"{p}: {url}" for p, url in post_urls.items()])
                        db.update_content_status(content_id, "approved", final_url)
                        
                        response_msg = f"âœ… Post published successfully!\n\n"
                        for platform, url in post_urls.items():
                            response_msg += f"**{platform.title()}:** {url}\n"
                        
                        if errors:
                            response_msg += f"\nâš ï¸ Some platforms failed:\n" + "\n".join(errors)
                        
                        # Schedule background metrics collection (wait 30 seconds for APIs to update)
                        import time
                        def collect_metrics_delayed():
                            time.sleep(30)  # Give platforms time to update metrics
                            collect_metrics_for_post(content_id)
                        
                        background_tasks.add_task(collect_metrics_delayed)
                        logger.info(f"Scheduled metrics collection for content {content_id}")
                        
                        return {"message": response_msg, "urls": post_urls, "errors": errors if errors else None}
                    else:
                        logger.warning(f"All social platforms failed: {errors}")
                        db.update_content_status(content_id, "approved")
                        return {"message": f"Content approved. Social posting unavailable: {', '.join(errors)}", "urls": {}, "errors": errors}
                        
                except Exception as e:
                    logger.error(f"Social media posting error: {e}")
                    db.update_content_status(content_id, "failed")
                    raise HTTPException(status_code=500, detail=f"Failed to post to social media: {str(e)}")
        else:
            db.update_content_status(content_id, "rejected")
            return {"message": "Content rejected"}

    except Exception as e:
        logger.error(f"Approval error: {e}")
        raise HTTPException(status_code=500, detail="Failed to process approval")

# ==================== METRICS ENDPOINTS ====================

@app.post("/metrics/collect")
async def trigger_metrics_collection(background_tasks: BackgroundTasks, authorization: str = Header(None), days: int = 7):
    """Trigger immediate metrics collection for user's recent posts."""
    try:
        payload = auth.get_current_user(authorization)
        user_id = payload['user_id']
        
        # Run metrics collection in background
        def collect_user_metrics():
            try:
                collector = MetricsCollector()
                
                # Get user's recent posts
                with db.get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                    SELECT DISTINCT sp.content_id, sp.platform, sp.post_url
                    FROM social_posts sp
                    JOIN generated_content gc ON sp.content_id = gc.id
                    JOIN sessions s ON gc.session_id = s.id
                    WHERE s.user_id = ? AND sp.posted_at >= datetime('now', '-' || ? || ' days')
                    ORDER BY sp.posted_at DESC
                    """, (user_id, days))
                    
                    posts = cursor.fetchall()
                    logger.info(f"Collecting metrics for {len(posts)} posts for user {user_id}")
                    
                    for post in posts:
                        content_id, platform, post_url = post
                        try:
                            post_id = collector._extract_post_id_from_url(platform, post_url)
                            if post_id:
                                collector.collect_and_save_metrics(content_id, platform, post_id)
                        except Exception as e:
                            logger.error(f"Error collecting metrics for {content_id}: {e}")
                
                logger.info(f"Metrics collection complete for user {user_id}")
            except Exception as e:
                logger.error(f"Metrics collection job failed: {e}")
        
        background_tasks.add_task(collect_user_metrics)
        
        return {
            "message": "Metrics collection started",
            "status": "processing"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Trigger metrics error: {e}")
        raise HTTPException(status_code=500, detail="Failed to trigger metrics collection")

@app.get("/metrics/dashboard")
async def get_metrics_dashboard(authorization: str = Header(None), days: int = 30):
    """Get aggregated metrics for dashboard."""
    try:
        payload = auth.get_current_user(authorization)
        user_id = payload['user_id']
        
        metrics = get_aggregated_metrics(user_id, days)
        return metrics
    except Exception as e:
        logger.error(f"Metrics error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get metrics")

# ==================== UTILITY ENDPOINTS ====================

@app.get("/reports/{name}")
async def get_report(name: str):
    """Serve generated reports."""
    file_path = f"reports/{name}"
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Report not found")
    return FileResponse(file_path)

@app.post("/upload/{session_id}")
async def upload_file(session_id: str, file: UploadFile = File(...), authorization: str = Header(None), asset_type: str = Query("general", description="Type of asset: logo, item, reference_image, or general")):
    """
    Upload file (image/logo/etc) to S3 and store S3 URL in database.
    
    asset_type: "logo", "item", "reference_image", or "general"
    """
    try:
        payload = auth.get_current_user(authorization)
        user_id = payload['user_id']
        
        # Validate file type (only images for now)
        allowed_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg'}
        file_ext = os.path.splitext(file.filename)[1].lower()
        if file_ext not in allowed_extensions:
            raise HTTPException(status_code=400, detail=f"File type not allowed. Allowed: {', '.join(allowed_extensions)}")
        
        # Read file content
        file_content = await file.read()
        file_size = len(file_content)
        
        # Limit file size (10MB)
        max_size = 10 * 1024 * 1024
        if file_size > max_size:
            raise HTTPException(status_code=400, detail=f"File too large. Maximum size: 10MB")
        
        # Determine content type
        content_type_map = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
            '.svg': 'image/svg+xml'
        }
        content_type = content_type_map.get(file_ext, 'application/octet-stream')
        
        # Generate unique S3 key
        import uuid
        unique_id = uuid.uuid4().hex[:8]
        timestamp = datetime.now().strftime("%Y%m%d")
        s3_key = f"user-assets/{user_id}/{asset_type}/{timestamp}_{unique_id}{file_ext}"
        
        # Upload to S3
        if not s3_client or not AWS_S3_BUCKET_NAME:
            # Fallback: save locally if S3 not configured
            logger.warning("S3 not configured, saving file locally")
            local_path = f"uploads/{session_id}_{file.filename}"
            os.makedirs("uploads", exist_ok=True)
            with open(local_path, "wb") as buffer:
                buffer.write(file_content)
            return JSONResponse(content={
                "message": f"File '{file.filename}' uploaded (local storage)",
                "path": local_path,
                "s3_url": None,
                "asset_type": asset_type
            })
        
        # Upload to S3
        try:
            s3_client.put_object(
                Bucket=AWS_S3_BUCKET_NAME,
                Key=s3_key,
                Body=file_content,
                ContentType=content_type,
              # Make images publicly accessible
            )
            s3_url = f"https://{AWS_S3_BUCKET_NAME}.s3.amazonaws.com/{s3_key}"
            logger.info(f"File uploaded to S3: {s3_url}")
        except Exception as s3_error:
            logger.error(f"S3 upload failed: {s3_error}")
            # Fallback to local storage
            local_path = f"uploads/{session_id}_{file.filename}"
            os.makedirs("uploads", exist_ok=True)
            with open(local_path, "wb") as buffer:
                buffer.write(file_content)
            return JSONResponse(content={
                "message": f"File '{file.filename}' uploaded (local storage - S3 failed)",
                "path": local_path,
                "s3_url": None,
                "asset_type": asset_type
            })
        
        # Store S3 URL in database
        try:
            # Get or create brand profile
            brand_profile = db.get_brand_profile(user_id)
            if not brand_profile:
                # Create brand profile with logo if it's a logo, otherwise just create basic profile
                db.save_brand_profile(
                    user_id=user_id,
                    brand_name="My Business",
                    logo_url=s3_url if asset_type == "logo" else None
                )
                brand_profile = db.get_brand_profile(user_id)

            # Prepare metadata with assets
            metadata = brand_profile.get('metadata', {})
            if not isinstance(metadata, dict):
                metadata = json.loads(metadata) if metadata else {}

            # Store asset URLs in metadata
            if 'assets' not in metadata:
                metadata['assets'] = {}
            if asset_type not in metadata['assets']:
                metadata['assets'][asset_type] = []

            asset_info = {
                "url": s3_url,
                "filename": file.filename,
                "uploaded_at": datetime.now().isoformat(),
                "size": file_size,
                "content_type": content_type
            }
            metadata['assets'][asset_type].append(asset_info)

            # Keep only last 20 assets per type
            if len(metadata['assets'][asset_type]) > 20:
                metadata['assets'][asset_type] = metadata['assets'][asset_type][-20:]

            # Update brand profile with new metadata AND logo_url if it's a logo
            update_params = {
                'user_id': user_id,
                'brand_name': brand_profile.get('brand_name'),
                'metadata': metadata
            }
            if asset_type == "logo":
                update_params['logo_url'] = s3_url

            db.update_brand_profile(**update_params)
            logger.info(f"✅ Asset {asset_type} saved to brand profile for user {user_id}")
        except Exception as db_error:
            logger.warning(f"Failed to store asset URL in database: {db_error}")
            # Continue anyway, S3 upload succeeded
        
        return JSONResponse(content={
            "message": f"File '{file.filename}' uploaded successfully",
            "s3_url": s3_url,
            "asset_type": asset_type,
            "filename": file.filename,
            "size": file_size
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload error: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@app.get("/scheduler/status")
async def scheduler_status():
    """Get scheduler status."""
    return get_scheduler_status()


# ==================== CRITIC ROUTES (ORCHESTRATOR-HOSTED) ====================

@app.get("/critic/logs")
async def critic_logs(limit: int = 200):
    """Return recent critic logs for dashboard."""
    try:
        return db.get_recent_critic_logs(limit=limit)
    except Exception as e:
        logger.error(f"Failed to fetch critic logs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch critic logs")


@app.get("/critic/log/{content_id}")
async def critic_log(content_id: str):
    """Return latest critic log by content_id."""
    try:
        log = db.get_critic_log(content_id)
        if not log:
            raise HTTPException(status_code=404, detail=f"No critic log for content {content_id}")
        return log
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch critic log for {content_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch critic log")


class CriticDecisionRequest(BaseModel):
    decision: str  # approved | rejected | edited


@app.post("/critic/decision/{content_id}")
async def critic_decision(content_id: str, req: CriticDecisionRequest):
    """Record user decision for a critic log entry."""
    try:
        if req.decision not in ("approved", "rejected", "edited"):
            raise HTTPException(status_code=400, detail="decision must be approved, rejected, or edited")
        db.update_critic_decision(content_id, req.decision)
        return {"status": "recorded", "content_id": content_id, "decision": req.decision}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to record critic decision for {content_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to record decision")


# ==================== CAMPAIGN ROUTES (ORCHESTRATOR-HOSTED) ====================

@app.get("/brands/{user_id}")
async def campaign_brands(user_id: int):
    """List brand profiles for Campaigns UI via orchestrator."""
    return campaign_get_brands(user_id)


@app.post("/schedule", status_code=201)
async def campaign_schedule_create(req: CampaignScheduleRequest):
    """Create campaign schedule via orchestrator."""
    return campaign_create_schedule(req)


@app.get("/schedules/{user_id}")
async def campaign_schedules(user_id: int, status: Optional[str] = None):
    """List campaign schedules via orchestrator."""
    return campaign_list_schedules(user_id, status)


@app.delete("/schedule/{schedule_id}")
async def campaign_schedule_delete(schedule_id: str, user_id: int):
    """Cancel campaign schedule via orchestrator."""
    return campaign_delete_schedule(schedule_id, user_id)


@app.post("/post")
async def campaign_post_create(req: CampaignPostRequest):
    """Create immediate social post job via orchestrator."""
    return await campaign_post_now(req)


@app.get("/post/status/{job_id}")
async def campaign_post_job_status(job_id: str):
    """Get post job status via orchestrator."""
    return campaign_post_status(job_id)


@app.get("/posts")
async def campaign_posts(user_id: Optional[int] = None, platform: Optional[str] = None):
    """List social post history via orchestrator."""
    return campaign_list_posts(user_id=user_id, platform=platform)


@app.get("/campaigns/history/{user_id}")
async def campaigns_history(user_id: int, limit: int = 50):
    """List campaign history records for Campaigns UI."""
    try:
        campaigns = db.get_campaigns_for_user(user_id, limit=limit)
        return {
            "campaigns": campaigns,
            "count": len(campaigns),
        }
    except Exception as e:
        logger.error(f"Campaign history fetch failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to load campaign history")

@app.get("/user/assets")
async def get_user_assets(authorization: str = Header(None), asset_type: Optional[str] = Query(None, description="Filter by asset type: logo, item, reference_image, or general")):
    """Get user's uploaded assets (S3 URLs)."""
    try:
        payload = auth.get_current_user(authorization)
        user_id = payload['user_id']

        brand_profile = db.get_brand_profile(user_id)
        if not brand_profile:
            return {"assets": [], "logo_url": None}
        
        logo_url = brand_profile.get('logo_url')
        metadata = brand_profile.get('metadata', {})
        if not isinstance(metadata, dict):
            metadata = json.loads(metadata) if metadata else {}
        
        assets = metadata.get('assets', {})
        
        # Filter by asset_type if specified
        if asset_type:
            filtered_assets = assets.get(asset_type, [])
            return {
                "assets": filtered_assets,
                "logo_url": logo_url if asset_type == "logo" else None
            }
        
        # Return all assets
        all_assets = []
        for asset_type_key, asset_list in assets.items():
            for asset in asset_list:
                asset['asset_type'] = asset_type_key
                all_assets.append(asset)
        
        # Sort by uploaded_at (newest first)
        all_assets.sort(key=lambda x: x.get('uploaded_at', ''), reverse=True)
        
        return {
            "assets": all_assets,
            "logo_url": logo_url
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get user assets error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get user assets")

@app.get("/rl/stats")
async def rl_stats():
    """Get MABO agent statistics (legacy endpoint name)."""
    mabo = mabo_agent.get_mabo_agent()
    return mabo.get_mabo_stats()

def sanitize_json(obj: Any) -> Any:
    """Recursively sanitize object for JSON serialization (replace inf/nan)."""
    try:
        import numpy as np
        has_numpy = True
    except ImportError:
        has_numpy = False
    
    if isinstance(obj, dict):
        return {k: sanitize_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_json(item) for item in obj]
    elif isinstance(obj, float):
        if math.isinf(obj) or math.isnan(obj):
            return None
        return obj
    elif has_numpy:
        if isinstance(obj, np.floating):
            if math.isinf(obj) or math.isnan(obj):
                return None
            return float(obj)
        elif isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.ndarray):
            return sanitize_json(obj.tolist())
    return obj

@app.get("/mabo/stats")
async def mabo_stats():
    """Get MABO agent statistics."""
    try:
        mabo = mabo_agent.get_mabo_agent()
        stats = mabo.get_mabo_stats()
        
        # Add validation metrics
        try:
            from validation_metrics import get_validation_metrics
            validation = get_validation_metrics()
            stats["validation"] = validation.get_comprehensive_report()
        except Exception as e:
            logger.warning(f"Could not load validation metrics: {e}")
            stats["validation"] = {"error": "Validation metrics not available"}
        
        # Final sanitization pass to ensure JSON compliance
        stats = sanitize_json(stats)
        
        return stats
    except Exception as e:
        logger.error(f"Error getting MABO stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get MABO stats: {str(e)}")

@app.post("/mabo/batch-update")
async def trigger_mabo_update(authorization: str = Header(None)):
    """Trigger MABO batch update (for testing/scheduling)."""
    try:
        payload = auth.get_current_user(authorization)
        mabo = mabo_agent.get_mabo_agent()
        result = mabo.perform_batch_update()
        return result
    except Exception as e:
        logger.error(f"MABO update error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== HITL ENDPOINTS ====================

@app.get("/hitl/pending/{session_id}")
async def get_pending_hitl(session_id: str):
    """Return pending HITL events for a session (polled by frontend â€” no auth required)."""
    from database import get_pending_hitl_events
    events = get_pending_hitl_events(session_id)

    normalized = []
    for ev in events:
        payload = ev.get("payload") or {}
        normalized.append({
            "id": ev.get("id"),
            "event_type": ev.get("event_type"),
            "content_id": payload.get("content_id"),
            "content_text": payload.get("content_preview", ""),
            "content_type": payload.get("content_type", "content"),
            "platform": payload.get("platform"),
            "attempt_number": payload.get("attempt_number", 1),
            "decision": payload.get("decision", "escalate"),
            "critic_data": {
                "intent_score": payload.get("intent_score", 0),
                "brand_score": payload.get("brand_score", 0),
                "quality_score": payload.get("quality_score", 0),
                "critique": payload.get("critique_text", ""),
                "suggestions": payload.get("suggestions", []),
                "content_agent_instructions": payload.get("content_agent_instructions", []),
            },
            "composite_score": payload.get("overall_score"),
            "created_at": ev.get("created_at"),
        })

    return {"events": normalized, "count": len(normalized)}


@app.post("/hitl/respond/{event_id}")
async def respond_hitl(event_id: str, req: HitlRespondRequest,
                       authorization: str = Header(None)):
    """User responds to a HITL event (approve/reject/edit)."""
    payload = auth.get_current_user(authorization)
    from database import resolve_hitl_event, get_hitl_event
    event = get_hitl_event(event_id)
    if not event:
        raise HTTPException(404, f"HITL event {event_id} not found")
    resolve_hitl_event(event_id, {
        "decision": req.decision,
        "edited_content": req.edited_content,
        "user_id": payload["user_id"],
        "responded_at": datetime.now().isoformat(),
    })
    # If approved/edited/rejected on critic review, also record decision in critic_logs.
    if event.get("event_type") == "critic_review":
        content_id = event["payload"].get("content_id")
        if content_id:
            from database import update_critic_decision
            update_critic_decision(content_id, req.decision)
    return {"status": "recorded", "event_id": event_id, "decision": req.decision}


# ==================== WORKFLOW RUN ENDPOINT ====================

@app.post("/workflow/run")
@trace_workflow(name="orchestrator_workflow", tags=["orchestrator"])
async def run_workflow(req: WorkflowRunRequest, authorization: str = Header(None)):
    """
    Execute a named agent workflow, run critic, emit HITL event if needed.
    Returns workflow_run_id and intermediate results.
    """
    user_payload = auth.get_current_user(authorization)
    user_id = user_payload["user_id"]
    session_id = req.session_id or str(uuid.uuid4())

    from intelligent_router import get_workflow_plan
    from database import create_workflow_run, update_workflow_run, get_workflow_run

    plan = get_workflow_plan(req.intent, req.params or {})
    run_id = str(uuid.uuid4())
    langsmith_run_id = get_current_run_id()

    create_workflow_run(
        run_id=run_id,
        session_id=session_id,
        user_id=user_id,
        workflow_name=req.intent,
        agent_sequence=plan.agents,
        agent_settings=plan.params,
        langsmith_run_id=langsmith_run_id,
    )

    steps_output: Dict[str, Any] = {}

    try:
        for i, agent in enumerate(plan.agents):
            update_workflow_run(run_id, "running", current_step=i)
            logger.info(f"[{run_id}] Step {i}: {agent}")
            # Dispatch to agent microservice
            result = await _call_agent(agent, req.message, req.brand_name, plan.params, steps_output)
            steps_output[agent] = result

        update_workflow_run(run_id, "completed", steps_output=steps_output, completed=True)
        return {
            "workflow_run_id": run_id,
            "session_id": session_id,
            "status": "completed",
            "agents_run": plan.agents,
            "results": steps_output,
            "langsmith_run_id": langsmith_run_id,
        }

    except Exception as e:
        logger.error(f"Workflow {run_id} failed: {e}", exc_info=True)
        update_workflow_run(run_id, "failed", steps_output=steps_output, completed=True)
        raise HTTPException(500, f"Workflow failed: {e}")


async def _call_agent(agent_name: str, message: str, brand_name: Optional[str],
                      params: Dict, prior_outputs: Dict) -> Dict:
    """Dispatch a single agent step and return its result dict."""
    agent_url_map = {
        "webcrawler":           f"{CRAWLER_BASE}/crawl",
        "keyword_extractor":    f"{KEYWORD_EXTRACTOR_BASE}/extract",
        "gap_analyzer":         f"{GAP_ANALYZER_BASE}/analyze",
        "content_agent_blog":   f"{CONTENT_AGENT_BASE}/generate-blog",
        "content_agent_social": f"{CONTENT_AGENT_BASE}/generate-social",
        "seo_agent":            "http://127.0.0.1:5000/analyze",
        "research_agent":       f"{RESEARCH_AGENT_BASE}/research",
        "brand_agent":          f"{BRAND_AGENT_BASE}/brand",
        "image_agent":          f"{IMAGE_AGENT_BASE}/generate",
        "critic_agent":         f"{CRITIC_AGENT_BASE}/critique",
        "campaign_agent":       f"{CAMPAIGN_AGENT_BASE}/post",
    }
    url = agent_url_map.get(agent_name)
    if not url:
        return {"skipped": True, "reason": f"No URL mapping for agent {agent_name}"}

    # Build agent-specific payloads to match each service's schema
    target_url = params.get("url") or params.get("start_url") or message
    if agent_name == "webcrawler":
        payload = {"start_url": target_url, "max_pages": params.get("max_pages", 3)}
    elif agent_name == "keyword_extractor":
        crawled_text = prior_outputs.get("webcrawler", {}).get("extracted_text", message)
        payload = {"text": crawled_text, "num_keywords": params.get("num_keywords", 20)}
    elif agent_name == "gap_analyzer":
        payload = {"domain": target_url, "keywords": prior_outputs.get("keyword_extractor", {}).get("keywords", [])}
    elif agent_name == "seo_agent":
        payload = {"url": target_url}
    elif agent_name == "research_agent":
        payload = {"domain": target_url, "topic": message, "depth_level": params.get("depth_level", "standard")}
    elif agent_name in ("content_agent_blog", "content_agent_social"):
        payload = {
            "message": message,
            "brand_name": brand_name,
            **params,
            "prior_keywords": prior_outputs.get("keyword_extractor", {}).get("keywords", []),
            "prior_research": prior_outputs.get("research_agent", {}).get("research_brief", ""),
        }
    elif agent_name == "critic_agent":
        payload = {
            "content_text": prior_outputs.get("content_agent_blog", prior_outputs.get("content_agent_social", {})).get("content", message),
            "intent": params.get("intent", "blog"),
            "brand_name": brand_name,
        }
    elif agent_name == "image_agent":
        payload = {"prompt": message, "style": params.get("style", "photorealistic")}
    elif agent_name == "campaign_agent":
        payload = {"user_id": params.get("user_id", 1), "platform": params.get("platform", "linkedin"), "content_text": message}
    else:
        payload = {"message": message, "brand_name": brand_name, **params}

    try:
        resp = requests.post(url, json=payload, timeout=120)
        if resp.status_code in (200, 201, 202):
            return resp.json()
        return {"error": f"HTTP {resp.status_code}", "body": resp.text[:200]}
    except requests.exceptions.RequestException as e:
        return {"error": str(e)}


# ==================== SOCIAL FEEDBACK & PROMPT EVOLUTION ====================

@app.post("/feedback/social")
async def social_feedback(req: SocialFeedbackRequest, authorization: str = Header(None)):
    """Feed social media performance back into MABO and LangSmith."""
    auth.get_current_user(authorization)
    mabo = mabo_agent.get_mabo_agent()
    # Try to find the langsmith_run_id from the content record
    langsmith_id = None
    try:
        from database import get_content
        content = get_content(req.content_id)
        if content:
            langsmith_id = content.get("langsmith_run_id")
    except Exception:
        pass
    mabo.record_social_feedback(req.content_id, req.platform, req.reward, langsmith_id)
    return {"status": "recorded", "content_id": req.content_id, "reward": req.reward}


@app.post("/prompt/evolve")
async def prompt_evolve(req: PromptEvolveRequest, authorization: str = Header(None)):
    """Ask the prompt optimizer to evolve a prompt using LLM mutation."""
    auth.get_current_user(authorization)
    mabo = mabo_agent.get_mabo_agent()
    version_id = mabo.trigger_prompt_evolution(
        req.agent_name, req.context_type, req.feedback, req.current_score
    )
    return {"status": "evolved" if version_id else "failed", "version_id": version_id}


@app.get("/prompt-log")
async def get_prompt_log(limit: int = 100, agent_name: Optional[str] = None,
                         context_type: Optional[str] = None):
    """Return prompt version history for the UI log page (no auth â€” read-only telemetry)."""
    try:
        import json
        from database import get_db_connection, get_prompt_executions
        
        with get_db_connection() as conn:
            conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
            cursor = conn.cursor()
            
            # Get template prompts
            where_clauses, params = [], []
            if agent_name:
                where_clauses.append("agent_name = ?")
                params.append(agent_name)
            if context_type:
                where_clauses.append("context_type = ?")
                params.append(context_type)
            where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
            
            cursor.execute(
                f"""
                SELECT id, agent_name, context_type, prompt_text,
                       performance_score, use_count, created_at, updated_at
                FROM prompt_versions
                {where_sql}
                ORDER BY created_at DESC
                LIMIT ?
                """,
                params + [limit],
            )
            templates = [dict(r) for r in cursor.fetchall()]
            
            # Get distinct agents for filters
            cursor.execute(
                "SELECT DISTINCT agent_name, context_type FROM prompt_versions ORDER BY agent_name, context_type"
            )
            agents = [{"agent_name": row["agent_name"], "context_type": row["context_type"]} for row in cursor.fetchall()]
        
        # Get recent executions with brand context
        executions = get_prompt_executions(
            agent_name=agent_name,
            context_type=context_type,
            limit=limit
        )
        
        # Format executions for display
        formatted_executions = []
        for exec_row in executions:
            formatted_executions.append({
                "execution_id": exec_row.get("execution_id"),
                "agent_name": exec_row.get("agent_name"),
                "context_type": exec_row.get("context_type"),
                "brand_info": exec_row.get("brand_info", {}),
                "performance_score": exec_row.get("performance_score"),
                "quality_score": exec_row.get("quality_score"),
                "brand_alignment_score": exec_row.get("brand_alignment_score"),
                "overall_score": exec_row.get("overall_score"),
                "feedback": exec_row.get("feedback"),
                "execution_time": exec_row.get("execution_time"),
                "created_at": exec_row.get("created_at"),
            })
        
        return {
            "templates": templates,
            "total_templates": len(templates),
            "executions": formatted_executions,
            "total_executions": len(formatted_executions),
            "agents": agents
        }
    except Exception as e:
        logger.error(f"/prompt-log failed: {e}")
        return {
            "templates": [],
            "total_templates": 0,
            "executions": [],
            "total_executions": 0,
            "agents": [],
            "error": str(e)
        }


@app.post("/seo/analyze")
async def seo_analyze_endpoint(request: dict):
    """
    SEO analysis endpoint using LangGraph orchestrator.
    Accepts URL and returns SEO audit report.
    """
    try:
        url = request.get("url", "").strip()
        if not url:
            return {
                "status": "error",
                "error": "URL is required",
                "url": url
            }
        
        # Validate URL format
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        
        # Run SEO analysis via agent adapter
        from agent_adapters import run_seo_analysis
        
        result = run_seo_analysis(url=url)
        
        return {
            "status": result.get("status", "completed"),
            "url": url,
            "final_url": url,
            "seo_score": result.get("seo_score", 0.0),
            "scores": {
                "overall": result.get("seo_score", 0.0),
                "recommendations": len(result.get("recommendations", [])),
                "issues": len(result.get("issues", [])),
                "opportunities": len(result.get("opportunities", [])),
            },
            "recommendations": result.get("recommendations", []) or result.get("issues", []),
            "error": result.get("error"),
            "audited_at": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"/seo/analyze failed: {e}")
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "error": str(e),
            "url": request.get("url", ""),
            "seo_score": 0.0,
            "recommendations": []
        }


@app.post("/seo/analyze/detailed")
async def seo_analyze_detailed_endpoint(request: dict):
    """
    Comprehensive SEO analysis endpoint.
    More detailed than /seo/analyze, takes 20-30 seconds.
    Includes full technical, content, and accessibility analysis.
    Generates an HTML report and returns the path.
    """
    try:
        url = request.get("url", "").strip()
        if not url:
            return {
                "status": "error",
                "error": "URL is required",
                "url": url
            }
        
        # Validate URL format
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        
        # Run comprehensive SEO analysis
        from comprehensive_seo_analysis import run_comprehensive_seo_analysis
        
        result = run_comprehensive_seo_analysis(url=url)
        
        # Generate HTML report if analysis was successful
        report_path = None
        if result.get("status") == "completed":
            try:
                from seo_html_report_generator import generate_seo_html_report
                report_path = generate_seo_html_report(url, result)
                logger.info(f"HTML report generated: {report_path}")
            except Exception as e:
                logger.warning(f"Failed to generate HTML report: {e}")
        
        return {
            "status": result.get("status", "completed"),
            "url": url,
            "final_url": result.get("final_url", url),
            "seo_score": result.get("seo_score", 0.0),
            "scores": result.get("scores", {}),
            "recommendations": result.get("recommendations", []),
            "details": result.get("details", {}),
            "analysis_time": result.get("analysis_time", "unknown"),
            "report_path": report_path,
            "error": result.get("error"),
            "audited_at": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"/seo/analyze/detailed failed: {e}")
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "error": str(e),
            "url": request.get("url", ""),
            "seo_score": 0.0,
            "recommendations": []
        }


@app.get("/tracer/status")
async def get_tracer_status():
    """Return LangSmith tracer configuration status."""
    return tracer_status()


# ═══════════════════════════════════════════════════════════════════════════════
# MCP (MODEL CONTEXT PROTOCOL) LAYER
# Exposes agents as MCP tools, resources, and prompts for LLM integration
# ═══════════════════════════════════════════════════════════════════════════════

ENABLE_MCP = os.getenv("ENABLE_MCP", "true").lower() == "true"  # Enabled by default

if ENABLE_MCP:
    try:
        from mcp_server import mcp_server, MCP_TOOLS, MCP_RESOURCES, MCP_PROMPTS
        from mcp_models import MCPRequest, MCPResponse, MCPToolCallRequest
        logger.info("MCP protocol layer ENABLED")
    except ImportError as e:
        logger.error(f"MCP imports failed: {e}. Make sure mcp_server.py and mcp_models.py exist.")
        ENABLE_MCP = False

    # ══════════════════════════════════════════════════════════════════════════
    # MCP ENDPOINTS
    # ══════════════════════════════════════════════════════════════════════════

    @app.post("/mcp/initialize")
    async def mcp_initialize(request: MCPRequest):
        """MCP initialization endpoint"""
        result = mcp_server.handle_initialize(request.params or {})
        return MCPResponse(
            id=request.id,
            result=result.model_dump()
        )

    @app.post("/mcp/tools/list")
    async def mcp_list_tools(request: MCPRequest):
        """List all available MCP tools"""
        tools = mcp_server.list_tools()
        return MCPResponse(
            id=request.id,
            result={"tools": [t.model_dump() for t in tools]}
        )

    @app.post("/mcp/tools/call")
    async def mcp_call_tool(request: MCPRequest, authorization: str = Header(None)):
        """Execute an MCP tool call"""
        # Authentication optional but recommended
        user_id = None
        if authorization:
            try:
                user = auth.get_current_user(authorization)
                user_id = user["id"]
            except:
                pass  # Allow unauthenticated for testing

        params = request.params or {}
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        # Create agent caller that uses our existing infrastructure
        async def agent_caller(agent_name: str, agent_params: Dict) -> Dict:
            """Call agent using LangGraph or HTTP fallback"""
            try:
                if LANGGRAPH_AVAILABLE:
                    # Use LangGraph adapter if available
                    from agent_adapters import (
                        run_webcrawler, run_keyword_extraction, run_gap_analysis,
                        generate_blog, generate_social, generate_image,
                        extract_brand_from_url, run_deep_research, run_seo_analysis,
                        run_reddit_research
                    )

                    adapter_map = {
                        "webcrawler": run_webcrawler,
                        "keyword_extractor": run_keyword_extraction,
                        "gap_analyzer": run_gap_analysis,
                        "content_agent_blog": lambda p: generate_blog(**p),
                        "content_agent_social": lambda p: generate_social(**p),
                        "image_agent": generate_image,
                        "brand_agent": lambda p: extract_brand_from_url(p.get("url")),
                        "research_agent": lambda p: run_deep_research(p.get("topic"), p.get("depth")),
                        "seo_agent": lambda p: run_seo_analysis(p.get("url")),
                        "reddit_agent": lambda p: run_reddit_research(p.get("keywords"), p.get("subreddits")),
                    }

                    if agent_name in adapter_map:
                        return await adapter_map[agent_name](agent_params)

                # HTTP fallback
                return await _call_agent(agent_name, "", None, agent_params, {})

            except Exception as e:
                logger.error(f"MCP agent caller error ({agent_name}): {e}")
                return {"error": str(e)}

        # Execute the tool
        result = await mcp_server.call_tool(tool_name, arguments, agent_caller)

        return MCPResponse(
            id=request.id,
            result=result.model_dump()
        )

    @app.post("/mcp/resources/list")
    async def mcp_list_resources(request: MCPRequest):
        """List all available MCP resources"""
        resources = mcp_server.list_resources()
        return MCPResponse(
            id=request.id,
            result={"resources": [r.model_dump() for r in resources]}
        )

    @app.post("/mcp/resources/read")
    async def mcp_read_resource(request: MCPRequest, authorization: str = Header(None)):
        """Read a specific MCP resource"""
        auth.get_current_user(authorization)

        params = request.params or {}
        uri = params.get("uri", "")

        # Parse resource URI and fetch from database
        content = {}
        try:
            if uri.startswith("brand://"):
                brand_id = uri.replace("brand://", "")
                brand_data = db.get_brand_profile(brand_id)
                content = {"text": json.dumps(brand_data, indent=2)}

            elif uri.startswith("content://"):
                content_id = uri.replace("content://", "")
                content_data = db.get_content_by_id(int(content_id))
                content = {"text": json.dumps(content_data, indent=2)}

            elif uri.startswith("campaign://"):
                campaign_id = uri.replace("campaign://", "")
                campaign_data = db.get_campaign_by_id(int(campaign_id))
                content = {"text": json.dumps(campaign_data, indent=2)}

            elif uri == "metrics://overview":
                metrics = get_aggregated_metrics()
                content = {"text": json.dumps(metrics, indent=2)}

            elif uri == "knowledge://graph" and GRAPH_AVAILABLE:
                from graph import get_graph_queries
                graph_summary = {"status": "available", "queries": get_graph_queries()}
                content = {"text": json.dumps(graph_summary, indent=2)}

            else:
                content = {"text": json.dumps({"error": "Resource not found"}, indent=2)}

        except Exception as e:
            content = {"text": json.dumps({"error": str(e)}, indent=2)}

        return MCPResponse(
            id=request.id,
            result={
                "contents": [{
                    "uri": uri,
                    "mimeType": "application/json",
                    **content
                }]
            }
        )

    @app.post("/mcp/prompts/list")
    async def mcp_list_prompts(request: MCPRequest):
        """List all available MCP prompts"""
        prompts = mcp_server.list_prompts()
        return MCPResponse(
            id=request.id,
            result={"prompts": [p.model_dump() for p in prompts]}
        )

    @app.post("/mcp/prompts/get")
    async def mcp_get_prompt(request: MCPRequest):
        """Get a specific prompt template with arguments filled in"""
        params = request.params or {}
        prompt_name = params.get("name")
        arguments = params.get("arguments", {})

        # Generate prompt messages based on template
        messages = []

        if prompt_name == "blog_generation_workflow":
            topic = arguments.get("topic", "")
            messages = [
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": f"""Generate a complete SEO-optimized blog post on: {topic}

Steps:
1. Use webcrawler_extract if competitor URL provided
2. Use keywords_extract to find relevant keywords
3. Use content_generate_blog to create the post
4. Optionally use seo_analyze to verify optimization"""
                    }
                }
            ]

        elif prompt_name == "social_campaign_workflow":
            goal = arguments.get("campaign_goal", "")
            platforms = arguments.get("platforms", "")
            messages = [
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": f"""Create a social media campaign for: {goal}

Target platforms: {platforms}

Steps:
1. Use campaign_plan to create strategy
2. Use content_generate_social for each platform
3. Use image_generate for visual content
4. Review and schedule posts"""
                    }
                }
            ]

        elif prompt_name == "competitor_analysis_workflow":
            competitor_url = arguments.get("competitor_url", "")
            messages = [
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": f"""Analyze competitor: {competitor_url}

Steps:
1. Use webcrawler_extract to get content
2. Use seo_analyze for SEO insights
3. Use keywords_extract for keyword strategy
4. Use gap_analyzer_run to find opportunities"""
                    }
                }
            ]

        else:
            messages = [{"role": "user", "content": {"type": "text", "text": "Prompt template not found"}}]

        return MCPResponse(
            id=request.id,
            result={
                "description": f"Workflow template: {prompt_name}",
                "messages": messages
            }
        )

    logger.info("MCP routes registered: /mcp/initialize, /mcp/tools/*, /mcp/resources/*, /mcp/prompts/*")

else:
    logger.info("MCP protocol layer DISABLED (set ENABLE_MCP=true to enable)")


# ═══════════════════════════════════════════════════════════════════════════════
# A2A (AGENT-TO-AGENT) PROTOCOL LAYER
# Gated behind ENABLE_A2A env var.  All endpoints reuse existing auth/db/graph.
# ═══════════════════════════════════════════════════════════════════════════════

ENABLE_A2A = os.getenv("ENABLE_A2A", "true").lower() == "true"  # Enabled by default

if ENABLE_A2A:
    import asyncio as _a2a_asyncio
    import collections as _a2a_collections
    from fastapi.responses import StreamingResponse as _SSEResponse
    from a2a_models import (
        AgentCard, A2AJsonRpcRequest, A2AJsonRpcResponse, A2AJsonRpcError,
        A2ATask, A2ATaskStatus, A2AMessage, A2APart, A2AArtifact,
        TaskStatusEnum, TaskStatusUpdateEvent, TaskArtifactUpdateEvent,
    )

    logger.info("A2A protocol layer ENABLED")

    # ── In-memory SSE event queues keyed by task_id ──────────────────────────
    _a2a_event_queues: Dict[str, _a2a_asyncio.Queue] = {}

    # ── Simple in-memory rate limiter (100 req/min per IP) ───────────────────
    _a2a_rate_window: Dict[str, List[float]] = _a2a_collections.defaultdict(list)
    _A2A_RATE_LIMIT = 100
    _A2A_RATE_WINDOW_SECS = 60

    def _a2a_check_rate(client_ip: str):
        now = time.time()
        window = _a2a_rate_window[client_ip]
        # Prune old entries
        _a2a_rate_window[client_ip] = [t for t in window if now - t < _A2A_RATE_WINDOW_SECS]
        if len(_a2a_rate_window[client_ip]) >= _A2A_RATE_LIMIT:
            raise HTTPException(status_code=429, detail="A2A rate limit exceeded (100/min)")
        _a2a_rate_window[client_ip].append(now)

    # ── Helper: push event to SSE queue + optional webhook ───────────────────
    async def _a2a_emit_event(task_id: str, event_dict: dict):
        """Push an event to the SSE queue and optionally POST to the webhook."""
        q = _a2a_event_queues.get(task_id)
        if q:
            await q.put(event_dict)

        # Webhook push
        task_row = db.get_a2a_task(task_id)
        webhook = task_row.get("webhook_url") if task_row else None
        if webhook:
            try:
                import httpx
                async with httpx.AsyncClient(timeout=10) as client:
                    await client.post(webhook, json=event_dict)
            except Exception as wh_err:
                logger.warning(f"A2A webhook POST failed for {task_id}: {wh_err}")

    def _normalize_campaign_proposal(raw: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize external campaign proposal payload for deterministic execution."""
        if not isinstance(raw, dict):
            raw = {}
        theme = str(raw.get("theme") or raw.get("product_name") or "New Product Launch").strip()
        tier = str(raw.get("tier") or "balanced").strip().lower()
        duration_days = int(raw.get("duration_days") or 7)
        summary = str(raw.get("summary") or raw.get("description") or "").strip()
        budget_guardrail = raw.get("budget_guardrail")

        if tier not in {"budget", "balanced", "premium"}:
            tier = "balanced"

        return {
            "theme": theme,
            "tier": tier,
            "duration_days": max(1, duration_days),
            "summary": summary,
            "budget_guardrail": budget_guardrail,
        }

    # ── Background worker: runs graph and updates task rows ──────────────────
    async def _a2a_run_task(task_id: str, user_message: str, user_id: int,
                            session_id: str, active_brand: str = "",
                            proposal: Optional[Dict[str, Any]] = None):
        """Execute the marketing graph for an A2A task (background)."""
        try:
            db.update_a2a_task_status(task_id, "working")
            await _a2a_emit_event(task_id, {
                "type": "status",
                "taskId": task_id,
                "status": {"state": "working", "message": "Pipeline started"},
            })

            # Campaign proposal mode: skip intent routing and execute deterministic campaign activation.
            if proposal:
                # ── TRACING FOR CAMPAIGN EXECUTION ──
                trace_id = f"campaign_{task_id}"
                trace_mgr = get_trace_manager()
                trace_mgr.create_trace(
                    trace_id=trace_id,
                    user_id=user_id,
                    metadata={
                        "intent": "campaign_execution",
                        "workflow": "campaign_a2a",
                        "task_id": task_id,
                        "session_id": session_id,
                    }
                )
                
                try:
                    normalized = _normalize_campaign_proposal(proposal)
                    trace_agent_event = trace_workflow(
                        name="campaign_acceptance_flow",
                        tags=["campaign_agent", "a2a"],
                        metadata={"task_id": task_id, "theme": normalized.get("theme")}
                    )
                    trace_agent_event.__enter__()
                    
                    await _a2a_emit_event(task_id, {
                        "type": "lifecycle",
                        "taskId": task_id,
                        "stage": "proposal_accepted",
                        "proposal": normalized,
                    })

                    campaign_id = f"camp_{uuid.uuid4().hex[:8]}"
                    start_date = (datetime.now() + timedelta(days=1)).isoformat()
                    end_date = (datetime.now() + timedelta(days=normalized["duration_days"] + 1)).isoformat()

                    # Trace database creation
                    with trace_workflow(
                        name="campaign_database_creation",
                        tags=["database", "campaign"],
                        metadata={"campaign_id": campaign_id}
                    ):
                        db.create_campaign(
                            campaign_id=campaign_id,
                            user_id=user_id,
                            name=f"{normalized['theme']} Campaign",
                            start_date=start_date,
                            end_date=end_date,
                            budget_tier=normalized["tier"],
                            strategy=normalized["tier"],
                        )

                    # Trace agenda generation
                    with trace_workflow(
                        name="campaign_agenda_generation",
                        tags=["planner", "campaign"],
                        metadata={"theme": normalized["theme"], "duration_days": normalized["duration_days"]}
                    ):
                        agenda = planner_agent.generate_campaign_agenda(
                            normalized["theme"],
                            normalized["duration_days"],
                            normalized["tier"],
                        )
                    
                    # Trace agenda storage
                    with trace_workflow(
                        name="campaign_agenda_storage",
                        tags=["database", "agenda"],
                        metadata={"agenda_count": len(agenda), "campaign_id": campaign_id}
                    ):
                        for item in agenda:
                            db.add_campaign_agenda_item(
                                campaign_id=campaign_id,
                                scheduled_time=item["scheduled_time"],
                                action=item["action"],
                                metadata=item["metadata"],
                            )

                    completion_artifact = {
                        "name": "campaign_execution",
                        "parts": [{
                            "type": "text",
                            "text": json.dumps({
                                "campaign_id": campaign_id,
                                "theme": normalized["theme"],
                                "tier": normalized["tier"],
                                "duration_days": normalized["duration_days"],
                                "agenda_count": len(agenda),
                                "publish_status": "scheduled",
                                "metrics_hook": {
                                    "tracer_status": "/tracer/status",
                                    "mabo_stats": "/mabo/stats",
                                },
                            }),
                        }],
                    }
                    artifacts = [
                        {
                            "name": "response",
                            "parts": [{
                                "type": "text",
                                "text": (
                                    f"Campaign proposal accepted and activated. "
                                    f"Campaign {campaign_id} was created with {len(agenda)} agenda items."
                                ),
                            }],
                        },
                        completion_artifact,
                    ]

                    db.update_a2a_task_status(task_id, "completed", artifacts=artifacts)
                    await _a2a_emit_event(task_id, {
                        "type": "lifecycle",
                        "taskId": task_id,
                        "stage": "campaign_completed",
                        "campaign_id": campaign_id,
                        "agenda_count": len(agenda),
                    })
                    await _a2a_emit_event(task_id, {
                        "type": "status",
                        "taskId": task_id,
                        "status": {"state": "completed", "message": "Campaign executed"},
                    })
                    for art in artifacts:
                        await _a2a_emit_event(task_id, {
                            "type": "artifact",
                            "taskId": task_id,
                            "artifact": art,
                        })
                    q = _a2a_event_queues.get(task_id)
                    if q:
                        await q.put(None)
                    
                    # Close trace context
                    trace_agent_event.__exit__(None, None, None)
                    trace_mgr.complete_trace(trace_id, success=True)
                    logger.info(f"Campaign execution trace completed: {trace_id}")
                    return
                    
                except Exception as campaign_err:
                    logger.error(f"Campaign execution error: {campaign_err}", exc_info=True)
                    trace_agent_event.__exit__(campaign_err.__class__, campaign_err, campaign_err.__traceback__)
                    trace_mgr.complete_trace(trace_id, success=False, error=str(campaign_err))
                    raise

            # Build brand context (same logic as chat_endpoint)
            brand_info_dict = None
            brand_ctx = ""
            if active_brand:
                _profile = db.get_brand_profile(user_id, active_brand)
                if _profile:
                    brand_info_dict = _profile
                    brand_ctx = _build_user_context_summary(user_id, active_brand)

            # Check if LangGraph is available
            if not LANGGRAPH_AVAILABLE:
                error_msg = "LangGraph is not available. Please restart the orchestrator after installing langgraph."
                logger.error(error_msg)
                raise Exception(error_msg)

            # Use LangGraph
            graph_result = await run_marketing_graph(
                user_message=user_message,
                session_id=session_id,
                user_id=user_id,
                active_brand=active_brand,
                conversation_history=[],
                brand_info=brand_info_dict,
                brand_context_summary=brand_ctx,
            )

            # Build artifacts from graph result
            response_text = graph_result.get("ai_message", "") or graph_result.get("response_text", "")
            artifacts = []
            
            # 1. Main Text artifact (Conversational intro)
            if response_text:
                artifacts.append({
                    "name": "response",
                    "parts": [{"type": "text", "text": response_text}],
                })
                
            # 2. Extract specific generated content variants
            options = graph_result.get("response_options", [])
            for idx, opt in enumerate(options):
                # Try to pull the raw text copy securely
                content_text = ""
                # For Social Posts
                if opt.get("twitter_copy"):
                    content_text += f"[Twitter/X]\n{opt['twitter_copy']}\n"
                if opt.get("instagram_copy"):
                    content_text += f"[Instagram]\n{opt['instagram_copy']}\n"
                if opt.get("facebook_copy"):
                    content_text += f"[Facebook]\n{opt['facebook_copy']}\n"
                # For Blog Links
                if opt.get("preview_url"):
                    content_text += f"[Blog HTML Output]\n{opt['preview_url']}\n"
                
                # If parsed content is empty, just dump the raw dict for the robot to parse manually
                if not content_text.strip():
                    content_text = json.dumps(opt)
                    
                artifacts.append({
                    "name": f"generated_variant_{idx+1}",
                    "parts": [{"type": "text", "text": content_text.strip()}]
                })
                
            # 3. Image artifact (if the graph produced a single flat preview id)
            preview_id = graph_result.get("content_preview_id")
            if preview_id:
                content_row = db.get_generated_content(preview_id)
                if content_row and content_row.get("preview_url"):
                    artifacts.append({
                        "name": "preview",
                        "parts": [{"type": "text", "text": content_row["preview_url"]}],
                    })

            db.update_a2a_task_status(task_id, "completed", artifacts=artifacts)
            await _a2a_emit_event(task_id, {
                "type": "status",
                "taskId": task_id,
                "status": {"state": "completed", "message": "Done"},
            })
            for art in artifacts:
                await _a2a_emit_event(task_id, {
                    "type": "artifact",
                    "taskId": task_id,
                    "artifact": art,
                })
            # Send sentinel to close SSE
            q = _a2a_event_queues.get(task_id)
            if q:
                await q.put(None)

        except Exception as e:
            logger.error(f"A2A task {task_id} failed: {e}", exc_info=True)
            db.update_a2a_task_status(task_id, "failed", error=str(e))
            await _a2a_emit_event(task_id, {
                "type": "status",
                "taskId": task_id,
                "status": {"state": "failed", "message": str(e)},
            })
            q = _a2a_event_queues.get(task_id)
            if q:
                await q.put(None)

    # ── Helper: build A2ATask dict from DB row ───────────────────────────────
    def _a2a_task_from_row(row: dict) -> dict:
        return {
            "id": row["task_id"],
            "status": {
                "state": row["status"],
                "message": row.get("error") or "",
            },
            "messages": row.get("request_payload", {}).get("messages", []),
            "artifacts": row.get("result_artifacts", []),
            "metadata": {
                "method": row.get("method"),
                "created_at": row.get("created_at"),
                "updated_at": row.get("updated_at"),
            },
        }

    # ══════════════════════════════════════════════════════════════════════════
    # ROUTE: Discovery
    # ══════════════════════════════════════════════════════════════════════════

    @app.get("/.well-known/agent.json")
    async def a2a_agent_card(request: Request):
        """Return the A2A Agent Card for discovery."""
        host = os.getenv("A2A_HOST", "")
        if not host:
            host = str(request.base_url).rstrip("/")
        card = AgentCard.build(host)
        return card.model_dump()

    # ══════════════════════════════════════════════════════════════════════════
    # ROUTE: JSON-RPC Gateway
    # ══════════════════════════════════════════════════════════════════════════

    @app.post("/a2a")
    async def a2a_jsonrpc(request: Request, authorization: str = Header(None)):
        """
        Main A2A JSON-RPC endpoint.
        Supported methods: tasks.send, tasks.sendSubscribe, tasks.cancel,
                           tasks.pushNotification.set
        """
        payload = auth.get_current_user(authorization)
        user_id = payload["user_id"]
        _a2a_check_rate(request.client.host if request.client else "unknown")

        body = await request.json()
        rpc = A2AJsonRpcRequest(**body)

        # ---------- tasks.send ----------
        if rpc.method == "tasks.send":
            return await _a2a_handle_send(rpc, user_id, subscribe=False)

        # ---------- tasks.sendSubscribe ----------
        elif rpc.method == "tasks.sendSubscribe":
            return await _a2a_handle_send(rpc, user_id, subscribe=True)

        # ---------- campaigns.propose ----------
        elif rpc.method == "campaigns.propose":
            return await _a2a_handle_campaign_propose(rpc, user_id)

        # ---------- campaigns.accept ----------
        elif rpc.method == "campaigns.accept":
            return await _a2a_handle_campaign_accept(rpc, user_id)

        # ---------- tasks.cancel ----------
        elif rpc.method == "tasks.cancel":
            task_id = rpc.params.get("taskId", "")
            row = db.get_a2a_task(task_id)
            if not row:
                return A2AJsonRpcResponse(
                    id=rpc.id,
                    error=A2AJsonRpcError(code=-32001, message="Task not found"),
                ).model_dump()
            db.update_a2a_task_status(task_id, "canceled")
            return A2AJsonRpcResponse(
                id=rpc.id,
                result=_a2a_task_from_row(db.get_a2a_task(task_id)),
            ).model_dump()

        # ---------- tasks.pushNotification.set ----------
        elif rpc.method == "tasks.pushNotification.set":
            task_id = rpc.params.get("taskId", "")
            webhook_url = rpc.params.get("webhookUrl", "")
            row = db.get_a2a_task(task_id)
            if not row:
                return A2AJsonRpcResponse(
                    id=rpc.id,
                    error=A2AJsonRpcError(code=-32001, message="Task not found"),
                ).model_dump()
            if not webhook_url:
                return A2AJsonRpcResponse(
                    id=rpc.id,
                    error=A2AJsonRpcError(code=-32602, message="Missing webhookUrl"),
                ).model_dump()
            db.set_a2a_webhook(task_id, webhook_url)
            return A2AJsonRpcResponse(
                id=rpc.id,
                result={"taskId": task_id, "webhookUrl": webhook_url},
            ).model_dump()

        # ---------- Unknown method ----------
        else:
            return A2AJsonRpcResponse(
                id=rpc.id,
                error=A2AJsonRpcError(code=-32601, message=f"Method not found: {rpc.method}"),
            ).model_dump()

    async def _a2a_handle_send(rpc: A2AJsonRpcRequest, user_id: int, subscribe: bool):
        """Core handler for tasks.send and tasks.sendSubscribe."""
        params = rpc.params
        task_id = params.get("taskId", str(uuid.uuid4()))
        messages = params.get("messages", [])

        # Extract the first user message text
        user_text = ""
        for msg in messages:
            if msg.get("role", "user") == "user":
                for part in msg.get("parts", []):
                    if part.get("type") == "text" and part.get("text"):
                        user_text = part["text"]
                        break
                if user_text:
                    break

        if not user_text:
            return A2AJsonRpcResponse(
                id=rpc.id,
                error=A2AJsonRpcError(code=-32602, message="No text content in messages"),
            ).model_dump()

        # Create internal session (with unique ID to avoid conflicts)
        session_id = f"a2a_{task_id}"
        try:
            db.create_session(session_id, user_id, f"A2A Task {task_id[:8]}")
        except Exception as e:
            # Session may already exist on retry, that's okay
            logger.debug(f"Session {session_id} already exists: {e}")

        # Store task and determine active brand
        active_brand = params.get("metadata", {}).get("brand", "")

        # If no brand specified in metadata, try to get user's most recent brand from DB
        if not active_brand:
            try:
                first_brand_profile = db.get_brand_profile(user_id, None)
                if first_brand_profile:
                    active_brand = first_brand_profile.get("brand_name", "")
                    logger.info(f"A2A task: auto-selected brand '{active_brand}' for user {user_id}")
            except Exception as e:
                logger.warning(f"Could not fetch user brand for A2A task: {e}")

        db.create_a2a_task(task_id, rpc.method, params, user_id)

        if subscribe:
            # SSE mode: create queue and return streaming response
            q: _a2a_asyncio.Queue = _a2a_asyncio.Queue()
            _a2a_event_queues[task_id] = q

            # Launch background work
            _a2a_asyncio.create_task(
                _a2a_run_task(task_id, user_text, user_id, session_id, active_brand)
            )

            async def _sse_generator():
                try:
                    while True:
                        event = await q.get()
                        if event is None:
                            break
                        yield f"data: {json.dumps(event)}\n\n"
                finally:
                    _a2a_event_queues.pop(task_id, None)

            return _SSEResponse(_sse_generator(), media_type="text/event-stream")

        else:
            # Synchronous mode: run graph and return result
            _a2a_event_queues[task_id] = _a2a_asyncio.Queue()
            await _a2a_run_task(task_id, user_text, user_id, session_id, active_brand)
            _a2a_event_queues.pop(task_id, None)

            row = db.get_a2a_task(task_id)
            return A2AJsonRpcResponse(
                id=rpc.id,
                result=_a2a_task_from_row(row) if row else {},
            ).model_dump()

    async def _a2a_handle_campaign_propose(rpc: A2AJsonRpcRequest, user_id: int):
        """Create a campaign proposal task without executing until explicitly accepted."""
        params = rpc.params
        task_id = params.get("taskId", str(uuid.uuid4()))
        proposal = _normalize_campaign_proposal(params.get("proposal", {}))

        if not proposal.get("theme"):
            return A2AJsonRpcResponse(
                id=rpc.id,
                error=A2AJsonRpcError(code=-32602, message="proposal.theme is required"),
            ).model_dump()

        session_id = f"a2a_{task_id}"
        try:
            db.create_session(session_id, user_id, f"A2A Proposal {task_id[:8]}")
        except Exception as e:
            logger.debug(f"Session {session_id} already exists: {e}")

        payload = {
            "taskId": task_id,
            "proposal": proposal,
            "metadata": params.get("metadata", {}),
            "messages": [
                {
                    "role": "user",
                    "parts": [{"type": "text", "text": proposal.get("summary") or proposal["theme"]}],
                }
            ],
        }
        db.create_a2a_task(task_id, rpc.method, payload, user_id)
        db.update_a2a_task_status(task_id, "submitted", artifacts=[
            {
                "name": "proposal",
                "parts": [{"type": "text", "text": json.dumps(proposal)}],
            }
        ])

        await _a2a_emit_event(task_id, {
            "type": "lifecycle",
            "taskId": task_id,
            "stage": "proposal_received",
            "proposal": proposal,
        })

        row = db.get_a2a_task(task_id)
        return A2AJsonRpcResponse(
            id=rpc.id,
            result=_a2a_task_from_row(row) if row else {},
        ).model_dump()

    async def _a2a_handle_campaign_accept(rpc: A2AJsonRpcRequest, user_id: int):
        """Accept a previously proposed campaign task and execute it."""
        params = rpc.params
        task_id = params.get("taskId", "")
        row = db.get_a2a_task(task_id)
        if not row:
            return A2AJsonRpcResponse(
                id=rpc.id,
                error=A2AJsonRpcError(code=-32001, message="Task not found"),
            ).model_dump()

        request_payload = row.get("request_payload", {})
        proposal = request_payload.get("proposal")
        if not proposal:
            return A2AJsonRpcResponse(
                id=rpc.id,
                error=A2AJsonRpcError(code=-32602, message="Task has no proposal payload"),
            ).model_dump()

        await _a2a_emit_event(task_id, {
            "type": "lifecycle",
            "taskId": task_id,
            "stage": "campaign_executing",
        })

        active_brand = request_payload.get("metadata", {}).get("brand", "")
        session_id = f"a2a_{task_id}"
        run_async = bool(params.get("async", True))
        if run_async:
            _a2a_asyncio.create_task(
                _a2a_run_task(
                    task_id,
                    proposal.get("summary") or proposal.get("theme", "Campaign proposal"),
                    row.get("user_id") or user_id,
                    session_id,
                    active_brand,
                    proposal=proposal,
                )
            )
            latest = db.get_a2a_task(task_id)
            return A2AJsonRpcResponse(
                id=rpc.id,
                result=_a2a_task_from_row(latest) if latest else {},
            ).model_dump()

        await _a2a_run_task(
            task_id,
            proposal.get("summary") or proposal.get("theme", "Campaign proposal"),
            row.get("user_id") or user_id,
            session_id,
            active_brand,
            proposal=proposal,
        )
        latest = db.get_a2a_task(task_id)
        return A2AJsonRpcResponse(
            id=rpc.id,
            result=_a2a_task_from_row(latest) if latest else {},
        ).model_dump()

    # ══════════════════════════════════════════════════════════════════════════
    # ROUTE: Task status polling
    # ══════════════════════════════════════════════════════════════════════════

    @app.get("/a2a/tasks/{task_id}")
    async def a2a_get_task(task_id: str, authorization: str = Header(None)):
        """Poll the current status of an A2A task."""
        auth.get_current_user(authorization)
        row = db.get_a2a_task(task_id)
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")
        return _a2a_task_from_row(row)

    # ══════════════════════════════════════════════════════════════════════════
    # ROUTE: SSE event stream (standalone)
    # ══════════════════════════════════════════════════════════════════════════

    @app.get("/a2a/tasks/{task_id}/events")
    async def a2a_task_events(task_id: str, authorization: str = Header(None)):
        """SSE endpoint to stream events for a task that is already running."""
        auth.get_current_user(authorization)
        row = db.get_a2a_task(task_id)
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")

        # If task is already finished, return events as a JSON list
        if row["status"] in ("completed", "failed", "canceled"):
            events = [
                {"type": "status", "taskId": task_id,
                 "status": {"state": row["status"], "message": row.get("error") or ""}},
            ]
            for art in row.get("result_artifacts", []):
                events.append({"type": "artifact", "taskId": task_id, "artifact": art})
            return JSONResponse(events)

        # Otherwise stream live
        q = _a2a_event_queues.get(task_id)
        if not q:
            # No active queue — task may have completed between check and here
            return JSONResponse([{
                "type": "status", "taskId": task_id,
                "status": {"state": row["status"], "message": "No active stream"},
            }])

        async def _stream():
            try:
                while True:
                    event = await q.get()
                    if event is None:
                        break
                    yield f"data: {json.dumps(event)}\n\n"
            finally:
                pass

        return _SSEResponse(_stream(), media_type="text/event-stream")

    # ══════════════════════════════════════════════════════════════════════════
    # ROUTE: Cancel (REST shortcut)
    # ══════════════════════════════════════════════════════════════════════════

    @app.post("/a2a/tasks/{task_id}/cancel")
    async def a2a_cancel_task(task_id: str, authorization: str = Header(None)):
        """Cancel an A2A task via REST."""
        auth.get_current_user(authorization)
        row = db.get_a2a_task(task_id)
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")
        db.update_a2a_task_status(task_id, "canceled")
        return {"taskId": task_id, "status": "canceled"}

    logger.info("A2A routes registered: /.well-known/agent.json, /a2a, /a2a/tasks/*")

else:
    logger.info("A2A protocol layer DISABLED (set ENABLE_A2A=true to enable)")


@app.get("/")
async def root():
    return {
        "message": "Orchestrator v5.0 - MCP & A2A Enabled",
        "status": "running",
        "protocols": {
            "mcp_enabled": ENABLE_MCP,
            "a2a_enabled": ENABLE_A2A
        },
        "mcp_endpoints": {
            "initialize": "/mcp/initialize",
            "tools": "/mcp/tools/list",
            "call_tool": "/mcp/tools/call",
            "resources": "/mcp/resources/list",
            "read_resource": "/mcp/resources/read",
            "prompts": "/mcp/prompts/list",
            "get_prompt": "/mcp/prompts/get"
        } if ENABLE_MCP else None,
        "a2a_endpoints": {
            "agent_card": "/.well-known/agent.json",
            "json_rpc": "/a2a",
            "tasks": "/a2a/tasks/*"
        } if ENABLE_A2A else None
    }

# ══════════════════════════════════════════════════════════════════════════
# WEBSOCKET ROUTES: Real-time Trace Streaming
# ══════════════════════════════════════════════════════════════════════════

@app.websocket("/ws/traces")
async def websocket_all_traces(websocket: WebSocket):
    """WebSocket endpoint for streaming all trace events."""
    await websocket.accept()
    trace_mgr = get_trace_manager()
    trace_mgr.add_connection(websocket, trace_id=None)

    try:
        # Send initial list of recent traces
        recent_traces = trace_mgr.get_recent_traces(limit=10)
        await websocket.send_json({
            "type": "initial_traces",
            "traces": recent_traces
        })

        # Keep connection alive and handle client messages
        while True:
            try:
                data = await websocket.receive_text()
                # Client can request specific trace details
                if data.startswith("get_trace:"):
                    trace_id = data.split(":", 1)[1]
                    trace_data = trace_mgr.get_trace(trace_id)
                    if trace_data:
                        await websocket.send_json({
                            "type": "trace_details",
                            **trace_data
                        })
            except WebSocketDisconnect:
                break
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        trace_mgr._remove_connection(websocket)

@app.websocket("/ws/traces/{trace_id}")
async def websocket_single_trace(websocket: WebSocket, trace_id: str):
    """WebSocket endpoint for streaming a specific trace."""
    await websocket.accept()
    trace_mgr = get_trace_manager()
    trace_mgr.add_connection(websocket, trace_id=trace_id)

    try:
        # Send existing trace data if available
        trace_data = trace_mgr.get_trace(trace_id)
        if trace_data:
            await websocket.send_json({
                "type": "trace_details",
                **trace_data
            })

        # Keep connection alive
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        trace_mgr._remove_connection(websocket)

@app.get("/traces")
async def list_traces(limit: int = 20):
    """Get list of recent traces."""
    trace_mgr = get_trace_manager()
    return {"traces": trace_mgr.get_recent_traces(limit=limit)}

@app.get("/traces/{trace_id}")
async def get_trace_details(trace_id: str):
    """Get detailed trace data."""
    trace_mgr = get_trace_manager()
    trace_data = trace_mgr.get_trace(trace_id)
    if not trace_data:
        raise HTTPException(status_code=404, detail="Trace not found")
    return trace_data

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8004)
