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
from datetime import datetime
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse

import requests
import boto3
from botocore.exceptions import NoCredentialsError, ClientError
from fastapi import FastAPI, HTTPException, UploadFile, File, Header, Depends, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential
from groq import Groq
from contextlib import asynccontextmanager
import tweepy
from instagrapi import Client as InstaClient
from fastapi.middleware.cors import CORSMiddleware
from langsmith import traceable

# Import new modules
import auth
import database as db
import intelligent_router as router
import cost_model
import rl_agent
from scheduler import start_scheduler, get_scheduler_status
from metrics_collector import get_aggregated_metrics, collect_metrics_for_post, MetricsCollector

# --- Configuration & Setup ---
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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

# --- Microservice Base URLs ---
CRAWLER_BASE = "http://127.0.0.1:8000"
KEYWORD_EXTRACTOR_BASE = "http://127.0.0.1:8001"
GAP_ANALYZER_BASE = "http://127.0.0.1:8002"
CONTENT_AGENT_BASE = "http://127.0.0.1:8003"

# --- Initialize Clients ---
groq_client = Groq(api_key=GROQ_API_KEY)
s3_client = boto3.client('s3', aws_access_key_id=AWS_ACCESS_KEY_ID, aws_secret_access_key=AWS_SECRET_ACCESS_KEY) if AWS_ACCESS_KEY_ID else None
insta_client = InstaClient()

# --- Lifespan Context Manager ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events."""
    # Startup
    logger.info("Starting Orchestrator v5.0...")
    try:
        db.initialize_database()
        start_scheduler()
        logger.info("Orchestrator started successfully")
    except Exception as e:
        logger.error(f"Startup error: {e}")
    
    yield  # Application runs
    
    # Shutdown (if needed)
    logger.info("Orchestrator shutting down...")

# --- App Setup ---
app = FastAPI(title="Orchestrator Agent", version="5.0.0", lifespan=lifespan)
origins = ["*"]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
os.makedirs("reports", exist_ok=True)
os.makedirs("uploads", exist_ok=True)
os.makedirs("generated_images", exist_ok=True)
os.makedirs("previews", exist_ok=True)

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

class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str

class ChatResponse(BaseModel):
    session_id: str
    response: str
    formatted_response: Optional[str] = None
    intent: Optional[str] = None
    content_preview_id: Optional[str] = None
    workflow_cost: Optional[Dict] = None

class SessionResponse(BaseModel):
    id: str
    title: str
    created_at: str
    last_active: str

class ContentApprovalRequest(BaseModel):
    approved: bool
    platform: Optional[str] = None  # For social posts

# ==================== AUTHENTICATION ENDPOINTS ====================

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
            "last_login": user['last_login']
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
    result_format: str = "json"
) -> Any:
    """Call an agent microservice and wait for result."""
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

@traceable(run_type="tool", name="📊 SEO Agent")
def run_seo_agent(url: str) -> str:
    """Run SEO analysis agent."""
    try:
        result = subprocess.run(["python", "seo_agent.py", url], capture_output=True, text=True, check=True, timeout=120)
        match = re.search(r"(report_.*\.html)", result.stdout)
        if match:
            original_path = match.group(0)
            new_path = f"reports/{os.path.basename(original_path)}"
            if os.path.exists(original_path):
                os.rename(original_path, new_path)
                logger.info(f"SEO report saved to {new_path}")
            return new_path
        raise Exception("Could not find report filename in SEO agent output.")
    except subprocess.CalledProcessError as e:
        error_output = e.stderr or e.stdout
        logger.error(f"Failed to run SEO agent. Stderr: {e.stderr}\nStdout: {e.stdout}")
        raise Exception(f"SEO Agent failed: {error_output}")

@traceable(run_type="tool", name="🎨 RunwayML Image Gen")
def generate_image_with_runway(prompt: str, reference_images: Optional[List[str]] = None) -> str:
    """Generate image using Runway ML."""
    if not RUNWAY_API_KEY:
        raise ValueError("RUNWAY_API_KEY not set.")
    headers = {"Authorization": f"Bearer {RUNWAY_API_KEY}", "Content-Type": "application/json", "X-Runway-Version": "2024-11-06"}
    payload = {"promptText": prompt, "ratio": "1920:1080", "seed": int(datetime.now().timestamp()) % 4294967295, "model": "gen4_image"}
    if reference_images: 
        payload["referenceImages"] = [{"uri": img} for img in reference_images]
    try:
        response = requests.post("https://api.dev.runwayml.com/v1/text_to_image", json=payload, headers=headers)
        response.raise_for_status()
        task_id = response.json().get("id")
        for _ in range(60):
            time.sleep(5)
            status_res = requests.get(f"https://api.dev.runwayml.com/v1/tasks/{task_id}", headers=headers)
            status_res.raise_for_status()
            data = status_res.json()
            if data['status'] == 'SUCCEEDED':
                image_url = data['output'][0]
                local_path = f"generated_images/{task_id}.jpg"
                save_file_from_url(image_url, local_path)
                return local_path
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
        if platform == "twitter":
            auth = tweepy.OAuth1UserHandler(TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET)
            api_v1 = tweepy.API(auth)
            client = tweepy.Client(consumer_key=TWITTER_API_KEY, consumer_secret=TWITTER_API_SECRET, access_token=TWITTER_ACCESS_TOKEN, access_token_secret=TWITTER_ACCESS_TOKEN_SECRET)
            media = api_v1.media_upload(filename=image_path)
            post_result = client.create_tweet(text=text, media_ids=[media.media_id_string])
            post_url = f"https://twitter.com/user/status/{post_result.data['id']}"
        elif platform == "instagram":
            if not os.path.exists("instagram.json"):
                insta_client.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
                insta_client.dump_settings("instagram.json")
            else:
                insta_client.load_settings("instagram.json")
                insta_client.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
            media = insta_client.photo_upload(path=image_path, caption=text)
            post_url = f"https://www.instagram.com/p/{media.code}/"
        return post_url
    except Exception as e:
        logger.error(f"Social Post Error ({platform}): {e}")
        raise

@traceable(run_type="tool", name="☁️ AWS S3 Hoster")
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
    
    # If metadata exists (from DB), flatten it
    if 'metadata' in brand_info and isinstance(brand_info['metadata'], dict):
        metadata = brand_info['metadata']
        return {
            "brand_name": brand_info.get('brand_name', 'My Business'),
            "location": brand_info.get('location'),
            "contacts": brand_info.get('contacts'),
            "industry": metadata.get('industry', 'General'),
            "description": metadata.get('description', ''),
            "target_audience": metadata.get('target_audience', ''),
            "unique_selling_points": metadata.get('unique_selling_points', []),
            "website": metadata.get('website', '')
        }
    
    # Already flattened (from fresh extraction)
    return brand_info

async def extract_brand_info(user_id: int, user_input: str, url: Optional[str] = None, crawled_data: Optional[str] = None, conversation_history: Optional[List[Dict]] = None, force_new: bool = False) -> Dict[str, Any]:
    """Extract and save brand information using LLM from user input, conversation history, and/or crawled website data."""
    try:
        # Check if brand profile already exists (skip if force_new=True)
        if not force_new:
            existing_profile = db.get_brand_profile(user_id)
            if existing_profile:
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
        
        prompt = f"""Extract detailed business information from the following content (including conversation history):
        
IMPORTANT: Look through the ENTIRE conversation history to find business details that the user may have mentioned earlier.

{content_to_analyze}

Extract and return JSON with these fields:
- brand_name: The business/company name (REQUIRED - extract from content or use domain name if from website)
- contacts: Email, phone, or other contact info (extract if found)
- location: Business location, city, state, or address (extract if mentioned)
- industry: Type of business or industry (be specific: e.g., "Italian Restaurant", "E-commerce Fashion")
- description: Detailed description of what the business does (2-3 sentences)
- target_audience: Who are the target customers (if identifiable)
- unique_selling_points: Key differentiators or unique features (array of strings)

If this is a website, extract the brand name from the domain, title, or content.
Return ONLY valid JSON. Be thorough and extract all available information."""

        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.3
        )
        
        extracted = json.loads(response.choices[0].message.content)
        logger.info(f"Brand extraction result: {extracted}")
        
        # Ensure brand_name is not empty - use domain as fallback
        brand_name = extracted.get("brand_name", "").strip()
        if not brand_name and url:
            # Extract domain name as fallback
            from urllib.parse import urlparse
            domain = urlparse(url).netloc.replace('www.', '')
            brand_name = domain.split('.')[0].title()
        if not brand_name:
            brand_name = "My Business"
        
        # Convert contacts to string if it's a dict
        contacts_data = extracted.get("contacts")
        if isinstance(contacts_data, dict):
            # Format contacts dict as string
            contacts_str = ", ".join([f"{k}: {v}" for k, v in contacts_data.items()])
        elif contacts_data:
            contacts_str = str(contacts_data)
        else:
            contacts_str = None
        
        # Save to database with all extracted metadata
        brand_id = db.save_brand_profile(
            user_id=user_id,
            brand_name=brand_name,
            contacts=contacts_str,
            location=extracted.get("location"),
            metadata={
                "industry": extracted.get("industry", ""),
                "description": extracted.get("description", ""),
                "target_audience": extracted.get("target_audience", ""),
                "unique_selling_points": extracted.get("unique_selling_points", []),
                "website": url if url else ""
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
    """Generate a descriptive title for the session using LLM."""
    if len(messages) < 2:
        return "New Chat"
    
    try:
        # Get first meaningful exchange
        first_exchange = "\n".join([f"{m['role']}: {m['content'][:100]}" for m in messages[:4]])
        
        prompt = f"""Based on this conversation, generate a short, descriptive title (3-6 words):

{first_exchange}

Return only the title, nothing else."""

        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=20
        )
        
        title = response.choices[0].message.content.strip()
        return title[:50]  # Limit length
        
    except Exception as e:
        logger.error(f"Title generation error: {e}")
        return "New Chat"

# ==================== MAIN CHAT ENDPOINT ====================

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest, authorization: str = Header(None)):
    """
    Main chat endpoint with intelligent routing.
    """
    try:
        # Authenticate user
        payload = auth.get_current_user(authorization)
        user_id = payload['user_id']
        
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
        
        # Route the query using intelligent router
        routing_result = await router.route_user_query(req.message, history_for_router)
        intent = routing_result["intent"]
        confidence = routing_result["confidence"]
        extracted_params = routing_result["extracted_params"]
        
        logger.info(f"Routed to intent: {intent} (confidence: {confidence})")
        
        response_text = ""
        content_preview_id = None
        workflow_cost = None
        
        # Handle different intents
        if intent == "general_chat":
            # Generate conversational response
            response_text = await router.generate_conversational_response(req.message, history_for_router)
        
        elif intent == "brand_setup":
            # Extract and save brand information from conversation
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
                            {"url": url},
                            download_path_template="/download/{job_id}"
                        )
                        crawled_data = crawl_result.get("extracted_text", "")
                        logger.info(f"Website crawled successfully: {len(crawled_data)} characters")
                    except Exception as e:
                        logger.warning(f"Website crawl failed: {e}, continuing without crawled data")
                
                # Force fresh extraction by deleting existing profile first
                try:
                    db.delete_brand_profile(user_id)
                    logger.info(f"Deleted old brand profile for user {user_id}")
                except Exception as e:
                    logger.warning(f"Could not delete old profile: {e}")
                
                # Extract brand info from conversation history (force_new=True)
                brand_info = await extract_brand_info(
                    user_id, 
                    req.message, 
                    url=url, 
                    crawled_data=crawled_data,
                    conversation_history=history_for_router,
                    force_new=True
                )
                
                logger.info(f"✓ Brand profile created: {brand_info.get('brand_name')} in {brand_info.get('location', 'N/A')}")
                
                response_text = f"""✅ **Brand Profile Saved!**

**Business Name:** {brand_info.get('brand_name', 'My Business')}
**Industry:** {brand_info.get('industry', 'Not specified')}
**Location:** {brand_info.get('location', 'Not specified')}
**Description:** {brand_info.get('description', 'Not specified')}

Your business information has been saved. You can now:
- Generate blog posts
- Create social media content
- Analyze your website's SEO

What would you like me to do next?"""
                
            except Exception as e:
                logger.error(f"Brand setup error: {e}", exc_info=True)
                response_text = f"I've noted your business information. What would you like me to help you create?"
        
        elif intent == "seo_analysis":
            # SEO Analysis workflow
            url = extracted_params.get("url") or await router.extract_url_from_message(req.message)
            if not url:
                response_text = "Please provide a URL to analyze. For example: 'Analyze https://example.com'"
            else:
                response_text = "I'm analyzing your website's SEO. This will take a few moments..."
                
                # Get optimized workflow from RL agent
                state = rl_agent.create_state_from_context(
                    intent=intent,
                    user_id=user_id,
                    content_type="seo",
                    has_website=True
                )
                agents = rl_agent.get_optimized_workflow(state, use_rl=True)
                
                # Estimate cost
                cost_estimate = cost_model.estimate_workflow_cost(agents)
                workflow_cost = cost_estimate
                
                try:
                    # Execute workflow
                    crawl_data = call_agent_job("WebCrawler", f"{CRAWLER_BASE}/crawl", {"start_url": url, "max_pages": 1})
                    report_path = run_seo_agent(url)
                    
                    response_text = f"✅ **SEO Analysis Complete!**\n\nI've analyzed {url} and generated a comprehensive report.\n\n**Key Findings:**\n- Page crawled successfully\n- SEO report generated\n\n[View Full Report](/reports/{os.path.basename(report_path)})\n\nWould you like me to:\n- Generate a blog post?\n- Create social media content?\n- Analyze competitors?"
                    
                except Exception as e:
                    response_text = f"⚠️ Analysis encountered an error: {str(e)}\n\nPlease try again or provide a different URL."
        
        elif intent == "blog_generation":
            # Blog generation workflow with comprehensive analysis
            response_text = "I'll create a blog post for you. Analyzing your business and competitors..."
            
            # Step 1: Extract URL if present
            url = extracted_params.get("url") or await router.extract_url_from_message(req.message)
            crawled_data = None
            
            # Step 2: Crawl website if URL provided
            if url:
                try:
                    logger.info(f"Crawling website: {url}")
                    crawl_result = call_agent_job(
                        "WebCrawler",
                        f"{CRAWLER_BASE}/crawl",
                        {"url": url},
                        download_path_template="/download/{job_id}"
                    )
                    crawled_data = crawl_result.get("extracted_text", "")
                    logger.info(f"Website crawled successfully: {len(crawled_data)} characters")
                except Exception as e:
                    logger.warning(f"Website crawl failed: {e}, continuing without crawled data")
            
            # Step 3: Extract comprehensive brand information from conversation history
            brand_profile = db.get_brand_profile(user_id)
            if not brand_profile:
                # Pass conversation history to extract business details mentioned earlier
                brand_info = await extract_brand_info(
                    user_id, 
                    req.message, 
                    url=url, 
                    crawled_data=crawled_data,
                    conversation_history=history_for_router
                )
                logger.info(f"✓ Brand info extracted from conversation: {brand_info.get('brand_name')} in {brand_info.get('location', 'N/A')}")
            else:
                brand_info = normalize_brand_info(brand_profile)
                logger.info(f"✓ Using existing brand profile: {brand_info.get('brand_name')}")
            
            # Get optimized workflow
            state = rl_agent.create_state_from_context(
                intent=intent,
                user_id=user_id,
                content_type="blog",
                has_brand_profile=brand_profile is not None
            )
            agents = rl_agent.get_optimized_workflow(state, use_rl=True)
            workflow_cost = cost_model.estimate_workflow_cost(agents)
            
            try:
                # Step 4: Build comprehensive business context for keyword extraction
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
                
                # Step 5: Extract keywords from comprehensive business context
                logger.info("Extracting keywords from business context")
                keywords_data = call_agent_job(
                    "KeywordExtractor",
                    f"{KEYWORD_EXTRACTOR_BASE}/extract-keywords",
                    {"customer_statement": business_context_for_keywords, "max_results": 10},
                    download_path_template="/download/{job_id}"
                )
                
                # Step 6: Run competitor gap analysis
                gap_analysis = None
                try:
                    logger.info("Running competitor gap analysis")
                    
                    # Build product description from brand info
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
                
                # Step 7: Create comprehensive business context for content generation
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

Please create a comprehensive, SEO-optimized blog post that:
1. Addresses the user's specific request: {req.message}
2. Highlights the business's unique strengths and location
3. Incorporates the extracted keywords naturally
4. Fills identified content gaps in the market
5. Appeals to the target audience
"""
                
                # Step 8: Generate blog content
                logger.info("Generating blog content")
                blog_html = call_agent_job(
                    "ContentAgent",
                    f"{CONTENT_AGENT_BASE}/generate-blog",
                    {
                        "business_details": business_context,
                        "keywords": keywords_data,
                        "target_tone": "informative",
                        "blog_length": "medium"
                    },
                    download_path_template="/download/html/{job_id}",
                    result_format="html"
                )
                
                # Save as preview
                content_id = str(uuid.uuid4())
                preview_path = f"previews/blog_{content_id}.html"
                os.makedirs("previews", exist_ok=True)
                with open(preview_path, "w", encoding="utf-8") as f:
                    f.write(blog_html)
                
                db.save_generated_content(
                    content_id=content_id,
                    session_id=session_id,
                    content_type="blog",
                    content=blog_html,
                    preview_url=f"/preview/blog/{content_id}",
                    metadata={
                        "brand_name": brand_info.get("brand_name", "My Business"),
                        "location": brand_info.get("location"),
                        "industry": brand_info.get("industry"),
                        "topic": req.message,
                        "keywords_used": keywords_data.get("keywords", [])[:5] if isinstance(keywords_data, dict) else []
                    }
                )
                
                content_preview_id = content_id
                response_text = f"""✅ **Blog Post Generated!**

I've created a comprehensive blog post for **{brand_info.get('brand_name', 'your business')}** {'in ' + brand_info.get('location') if brand_info.get('location') else ''}.

**Topic:** {req.message}
**Industry:** {brand_info.get('industry', 'General')}
**Keywords:** {', '.join(keywords_data.get('keywords', [])[:5]) if isinstance(keywords_data, dict) else 'Optimized'}

**Preview:** Click the preview card below to see the full blog.

**Actions:**
- Approve & Publish to S3
- Regenerate with changes
- Cancel"""
                
            except Exception as e:
                logger.error(f"Blog generation error: {e}", exc_info=True)
                response_text = f"⚠️ Blog generation encountered an error: {str(e)}\n\nPlease try again with a different topic."
        
        elif intent == "social_post":
            # Social media post generation with comprehensive analysis
            response_text = "Creating social media content for you. Analyzing your business and competitors..."
            
            # Step 1: Extract URL if present
            url = extracted_params.get("url") or await router.extract_url_from_message(req.message)
            crawled_data = None
            
            # Step 2: Crawl website if URL provided
            if url:
                try:
                    logger.info(f"Crawling website: {url}")
                    crawl_result = call_agent_job(
                        "WebCrawler",
                        f"{CRAWLER_BASE}/crawl",
                        {"url": url},
                        download_path_template="/download/{job_id}"
                    )
                    crawled_data = crawl_result.get("extracted_text", "")
                    logger.info(f"Website crawled successfully: {len(crawled_data)} characters")
                except Exception as e:
                    logger.warning(f"Website crawl failed: {e}, continuing without crawled data")
            
            # Step 3: Extract comprehensive brand information from conversation history
            brand_profile = db.get_brand_profile(user_id)
            if not brand_profile:
                # Pass conversation history to extract business details mentioned earlier
                brand_info = await extract_brand_info(
                    user_id, 
                    req.message, 
                    url=url, 
                    crawled_data=crawled_data,
                    conversation_history=history_for_router
                )
                logger.info(f"✓ Brand info extracted from conversation: {brand_info.get('brand_name')} in {brand_info.get('location', 'N/A')}")
            else:
                brand_info = normalize_brand_info(brand_profile)
                logger.info(f"✓ Using existing brand profile: {brand_info.get('brand_name')}")
            
            try:
                # Step 4: Build comprehensive business context for keyword extraction
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
                
                # Step 5: Extract keywords from comprehensive business context
                logger.info("Extracting keywords from business context")
                keywords_data = call_agent_job(
                    "KeywordExtractor",
                    f"{KEYWORD_EXTRACTOR_BASE}/extract-keywords",
                    {"customer_statement": business_context_for_keywords, "max_results": 8},
                    download_path_template="/download/{job_id}"
                )
                
                # Step 6: Run competitor gap analysis
                gap_analysis = None
                try:
                    logger.info("Running competitor gap analysis")
                    
                    # Build product description from brand info
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
                
                # Step 7: Create enriched social media content request
                social_context = {
                    "keywords": keywords_data,
                    "brand_name": brand_info.get("brand_name", "My Business"),
                    "industry": brand_info.get("industry", ""),
                    "location": brand_info.get("location", ""),
                    "target_audience": brand_info.get("target_audience", ""),
                    "unique_selling_points": brand_info.get("unique_selling_points", []),
                    "competitor_insights": gap_analysis.get("content_gaps_summary", "") if gap_analysis else "",
                    "user_request": req.message,
                    "platforms": ["twitter", "instagram"],
                    "tone": "professional"
                }
                
                # Step 8: Generate social content
                logger.info("Generating social media content")
                social_data = call_agent_job(
                    "ContentAgent",
                    f"{CONTENT_AGENT_BASE}/generate-social",
                    social_context
                )
                
                # Step 9: Generate image using Runway
                image_prompts = social_data.get('image_prompts', [])
                
                # Create contextual image prompt
                location_str = f" in {brand_info.get('location')}" if brand_info.get('location') else ""
                image_prompt = image_prompts[0] if image_prompts else f"Professional social media image for {brand_info.get('brand_name', 'a business')}{location_str}, about {req.message[:50]}, modern, high-quality, eye-catching"
                
                try:
                    image_path = generate_image_with_runway(image_prompt)
                    logger.info(f"Image generated: {image_path}")
                except Exception as img_error:
                    logger.warning(f"Image generation failed: {img_error}, using placeholder")
                    image_path = None
                
                # Save to preview
                content_id = str(uuid.uuid4())
                post_text = social_data['posts']['twitter']['copy']
                
                db.save_generated_content(
                    content_id=content_id,
                    session_id=session_id,
                    content_type="post",
                    content=post_text,
                    preview_url=image_path,
                    metadata={
                        "brand_name": brand_info.get("brand_name", "My Business"),
                        "location": brand_info.get("location"),
                        "industry": brand_info.get("industry"),
                        "platforms": ["twitter", "instagram"],
                        "hashtags": social_data['posts']['twitter'].get('hashtags', []),
                        "image_path": image_path,
                        "keywords_used": keywords_data.get("keywords", [])[:5] if isinstance(keywords_data, dict) else []
                    }
                )
                
                content_preview_id = content_id
                
                # Show preview with detailed info
                response_text = f"""✅ **Social Media Post Generated!**

**Brand:** {brand_info.get('brand_name', 'My Business')} {'in ' + brand_info.get('location') if brand_info.get('location') else ''}
**Industry:** {brand_info.get('industry', 'General')}

**Post Content:**
{post_text}

**Hashtags:** {', '.join(social_data['posts']['twitter'].get('hashtags', []))}
**Keywords Used:** {', '.join(keywords_data.get('keywords', [])[:3]) if isinstance(keywords_data, dict) else 'Optimized'}

{'**Image:** Generated and ready for preview' if image_path else '**Image:** Will be generated on approval'}

**Actions:**
- Preview & Approve
- Regenerate
- Cancel"""
                
            except Exception as e:
                logger.error(f"Social post error: {e}", exc_info=True)
                response_text = f"⚠️ Post generation error: {str(e)}\n\nPlease try again with a different prompt."
        
        elif intent == "metrics_report":
            # Show metrics dashboard link
            response_text = "📊 **Social Media Metrics**\n\nView your performance metrics on the dashboard:\n\n[Open Metrics Dashboard](/metrics.html)\n\nI can also show specific metrics here. What would you like to see?"
        
        else:
            # Fallback
            response_text = await router.generate_conversational_response(req.message, history_for_router)
        
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
            workflow_cost=workflow_cost
        )
    
    except HTTPException:
        raise
    except Exception as e:
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
async def get_brand_profile(authorization: str = Header(None)):
    """Get user's brand profile."""
    try:
        payload = auth.get_current_user(authorization)
        user_id = payload['user_id']
        
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
                s3_url = host_on_s3(preview_path, f"blogs/{content_id}.html")
                db.update_content_status(content_id, "approved", s3_url)
                return {"message": "Blog published successfully", "url": s3_url}
            
            elif content['type'] == 'post':
                # Post to social media platforms
                try:
                    metadata = content.get('metadata', {})
                    image_path = metadata.get('image_path') or content.get('preview_url')
                    post_text = content['content']
                    hashtags = metadata.get('hashtags', [])
                    platforms = metadata.get('platforms', ['twitter', 'instagram'])
                    
                    # Add hashtags to post text
                    full_text = f"{post_text}\n\n{' '.join(hashtags)}" if hashtags else post_text
                    
                    # Generate image if not exists
                    if not image_path or not os.path.exists(image_path):
                        logger.info("Image not found, generating new image...")
                        image_prompt = f"Professional social media image for {metadata.get('brand_name', 'business')}"
                        try:
                            image_path = generate_image_with_runway(image_prompt)
                            logger.info(f"Image generated: {image_path}")
                        except Exception as img_error:
                            logger.error(f"Image generation failed: {img_error}")
                            raise HTTPException(status_code=500, detail="Image generation failed")
                    
                    # Post to social media platforms
                    post_urls = {}
                    errors = []
                    
                    for platform in platforms:
                        try:
                            logger.info(f"Posting to {platform}...")
                            post_url = post_to_social(platform, full_text, image_path)
                            post_urls[platform] = post_url
                            logger.info(f"✓ Posted to {platform}: {post_url}")
                            
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
                        
                        response_msg = f"✅ Post published successfully!\n\n"
                        for platform, url in post_urls.items():
                            response_msg += f"**{platform.title()}:** {url}\n"
                        
                        if errors:
                            response_msg += f"\n⚠️ Some platforms failed:\n" + "\n".join(errors)
                        
                        # Schedule background metrics collection (wait 30 seconds for APIs to update)
                        import time
                        def collect_metrics_delayed():
                            time.sleep(30)  # Give platforms time to update metrics
                            collect_metrics_for_post(content_id)
                        
                        background_tasks.add_task(collect_metrics_delayed)
                        logger.info(f"Scheduled metrics collection for content {content_id}")
                        
                        return {"message": response_msg, "urls": post_urls, "errors": errors if errors else None}
                    else:
                        raise HTTPException(status_code=500, detail=f"Failed to post to all platforms: {', '.join(errors)}")
                        
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
async def upload_file(session_id: str, file: UploadFile = File(...), authorization: str = Header(None)):
    """Upload file for processing."""
    try:
        payload = auth.get_current_user(authorization)
        local_path = f"uploads/{session_id}_{file.filename}"
        with open(local_path, "wb") as buffer:
            buffer.write(await file.read())
        return JSONResponse(content={"message": f"File '{file.filename}' uploaded", "path": local_path})
    except Exception as e:
        logger.error(f"Upload error: {e}")
        raise HTTPException(status_code=500, detail="Upload failed")

@app.get("/scheduler/status")
async def scheduler_status():
    """Get scheduler status."""
    return get_scheduler_status()

@app.get("/rl/stats")
async def rl_stats():
    """Get RL agent statistics."""
    return rl_agent.get_q_table_summary()

@app.get("/")
async def root():
    return {"message": "Orchestrator v5.0", "status": "running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8004)
