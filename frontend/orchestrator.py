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
from datetime import datetime
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse

import requests
import boto3
from botocore.exceptions import NoCredentialsError, ClientError
from fastapi import FastAPI, HTTPException, UploadFile, File, Header, BackgroundTasks, Query
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential
from groq import Groq
from contextlib import asynccontextmanager
import tweepy
from instagrapi import Client as InstaClient
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

# Import new modules
import auth
import database as db
import intelligent_router as router
import cost_model
# import rl_agent  # Deprecated - replaced with MABO
import mabo_agent
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
    response_options: Optional[List[Dict[str, Any]]] = None
    clarification_request: Optional[Dict[str, Any]] = None

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
    """Generate image using Runway ML with S3 reference images."""
    if not RUNWAY_API_KEY:
        raise ValueError("RUNWAY_API_KEY not set.")
    headers = {"Authorization": f"Bearer {RUNWAY_API_KEY}", "Content-Type": "application/json", "X-Runway-Version": "2024-11-06"}
    payload = {"promptText": prompt, "ratio": "1920:1080", "seed": int(datetime.now().timestamp()) % 4294967295, "model": "gen4_image"}
    if reference_images: 
        # Process reference images - expect S3 URLs or HTTP/HTTPS URLs
        processed_refs = []
        for img in reference_images:
            if not img:
                continue
            # Check if it's a URL (starts with http:// or https://)
            if img.startswith(('http://', 'https://')):
                # It's already a URL (S3 or other), use it directly
                processed_refs.append(img)
                logger.info(f"Using reference image URL: {img}")
            elif os.path.exists(img) and os.path.isfile(img):
                # Local file - upload to S3 first, then use S3 URL
                try:
                    logger.info(f"Uploading local reference image to S3: {img}")
                    # Generate S3 key
                    file_ext = os.path.splitext(img)[1]
                    unique_id = uuid.uuid4().hex[:8]
                    timestamp = datetime.now().strftime("%Y%m%d")
                    s3_key = f"reference-images/{timestamp}_{unique_id}{file_ext}"
                    
                    # Determine content type
                    content_type_map = {
                        '.jpg': 'image/jpeg',
                        '.jpeg': 'image/jpeg',
                        '.png': 'image/png',
                        '.gif': 'image/gif',
                        '.webp': 'image/webp'
                    }
                    content_type = content_type_map.get(file_ext.lower(), 'image/jpeg')
                    
                    # Upload to S3
                    if s3_client and AWS_S3_BUCKET_NAME:
                        s3_client.upload_file(img, AWS_S3_BUCKET_NAME, s3_key, ExtraArgs={'ContentType': content_type, 'ACL': 'public-read'})
                        s3_url = f"https://{AWS_S3_BUCKET_NAME}.s3.amazonaws.com/{s3_key}"
                        processed_refs.append(s3_url)
                        logger.info(f"Local image uploaded to S3: {s3_url}")
                    else:
                        logger.warning(f"S3 not configured, skipping local file: {img}")
                except Exception as upload_error:
                    logger.warning(f"Failed to upload local image to S3: {upload_error}, skipping")
            else:
                logger.warning(f"Invalid reference image (not a URL or local file): {img}, skipping")
        
        if processed_refs:
            payload["referenceImages"] = [{"uri": img} for img in processed_refs]
            logger.info(f"Using {len(processed_refs)} reference image(s) for Runway generation")
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
        response_options: Optional[List[Dict[str, Any]]] = None
        
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
                
                # Get optimized workflow from MABO agent
                mabo = mabo_agent.get_mabo_agent()
                state_context = mabo.create_state_from_context(
                    intent=intent,
                    user_id=user_id,
                    content_type="seo",
                    has_website=True
                )
                agents = mabo.get_optimized_workflow(state_context, use_mabo=True)
                
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
            # Check if we have required business details BEFORE starting generation
            brand_profile = db.get_brand_profile(user_id)
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
                    url = extracted_params.get("url") or await router.extract_url_from_message(req.message)
                    crawled_data = None
                    
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
                    
                    logger.info(f"✓ Using existing brand profile: {brand_info.get('brand_name')}")
            else:
                # No brand profile - try to extract from message, but ask if missing
                url = extracted_params.get("url") or await router.extract_url_from_message(req.message)
                crawled_data = None
                
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
                
                # Try to extract brand info from conversation
                brand_info = await extract_brand_info(
                    user_id,
                    req.message,
                    url=url,
                    crawled_data=crawled_data,
                    conversation_history=history_for_router
                )
                
                # Check if essential fields are present
                if not brand_info.get('brand_name') or brand_info.get('brand_name') == 'My Business':
                    response_text = "I need your business name to create personalized blog content. What's your business or brand name?"
                    brand_info = None  # Don't proceed
                elif not brand_info.get('industry') or brand_info.get('industry') in ['General', '']:
                    response_text = f"Thanks! I have your business name ({brand_info.get('brand_name')}). What industry is your business in? (e.g., Restaurant, E-commerce, Tech, Healthcare, etc.)"
                    brand_info = None  # Don't proceed
                else:
                    logger.info(f"✓ Brand info extracted from conversation: {brand_info.get('brand_name')} in {brand_info.get('location', 'N/A')}")
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
                        
                        variant_configs = [
                            {
                                "label": "Option A · Research-Driven Depth",
                                "tone": "informative",
                                "length": "long",
                                "workflow": primary_workflow,
                                "source": "mabo"
                            },
                            {
                                "label": "Option B · Fast Conversion Story",
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
                                    result_format="html"
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
                                
                                response_options.append({
                                    "option_id": option_id,
                                    "label": variant["label"],
                                    "tone": variant["tone"].title(),
                                    "workflow_name": variant["workflow"]["workflow_name"],
                                    "workflow_agents": variant["workflow"]["agents"],
                                    "cost": workflow_cost_estimate["total_cost"],
                                    "cost_display": cost_model.format_cost_display(workflow_cost_estimate["total_cost"]),
                                    "preview_url": f"/preview/blog/{content_id}",
                                    "content_id": content_id,
                                    "content_type": "blog",
                                    "state_hash": state_hash
                                })
                            except Exception as variant_error:
                                logger.error(f"Variant generation failed ({variant['label']}): {variant_error}", exc_info=True)
                                continue
                        
                        if response_options:
                            option_lines = "\n".join([
                                f"- {opt['label']}: {opt['tone']} tone · {opt['cost_display']} · workflow `{opt['workflow_name']}`"
                                for opt in response_options
                            ])
                            response_text = f"""📝 **Two Draft Blogs Ready**

I've produced two variations for *{brand_info.get('brand_name', 'your brand')}*. Review the cards below and pick the one that best fits your campaign.

{option_lines}

Tap a card to preview and lock in your preferred option. Once you choose, I'll tailor the workflow and budget around it."""
                        else:
                            response_text = "⚠️ I couldn't generate the blog variations right now. Please try again or adjust your prompt."
                    except Exception as e:
                        logger.error(f"Blog generation error: {e}", exc_info=True)
                        response_text = f"⚠️ Blog generation encountered an error: {str(e)}\n\nPlease try again with a different topic."
                except Exception as e:
                    logger.error(f"Blog generation setup error: {e}", exc_info=True)
                    response_text = f"⚠️ Blog generation encountered an error: {str(e)}\n\nPlease try again with a different topic."
            else:
                # Missing required fields - response_text already set above asking for info
                pass
        
        elif intent == "social_post":
            # Check if we have required business details BEFORE starting generation
            brand_profile = db.get_brand_profile(user_id)
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
                    url = extracted_params.get("url") or await router.extract_url_from_message(req.message)
                    crawled_data = None
                    
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
                    
                    logger.info(f"✓ Using existing brand profile: {brand_info.get('brand_name')}")
            else:
                # No brand profile - try to extract from message, but ask if missing
                url = extracted_params.get("url") or await router.extract_url_from_message(req.message)
                crawled_data = None
                
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
                
                # Try to extract brand info from conversation
                brand_info = await extract_brand_info(
                    user_id,
                    req.message,
                    url=url,
                    crawled_data=crawled_data,
                    conversation_history=history_for_router
                )
                
                # Check if essential fields are present
                if not brand_info.get('brand_name') or brand_info.get('brand_name') == 'My Business':
                    response_text = "I need your business name to create personalized social media content. What's your business or brand name?"
                    brand_info = None  # Don't proceed
                elif not brand_info.get('industry') or brand_info.get('industry') in ['General', '']:
                    response_text = f"Thanks! I have your business name ({brand_info.get('brand_name')}). What industry is your business in? (e.g., Restaurant, E-commerce, Tech, Healthcare, etc.)"
                    brand_info = None  # Don't proceed
                else:
                    logger.info(f"✓ Brand info extracted from conversation: {brand_info.get('brand_name')} in {brand_info.get('location', 'N/A')}")
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
                        "competitor_insights": gap_analysis.get("content_gaps_summary", "") if gap_analysis else "",
                        "user_request": req.message,
                        "platforms": ["twitter", "instagram"],
                        "tone": "professional"
                    }
                    
                    variant_configs = [
                        {
                            "label": "Option A · Authority Launch",
                            "tone": "professional",
                            "workflow": primary_workflow,
                            "source": "mabo"
                        },
                        {
                            "label": "Option B · Conversational Buzz",
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
                            post_preview = json.dumps({
                                "twitter": twitter_post.get('copy', ''),
                                "instagram": instagram_post.get('copy', '')
                            })
                            image_prompts = social_data.get('image_prompts', [])
                            image_prompt = image_prompts[0] if image_prompts else f"Professional, high-quality social media image for {brand_info.get('brand_name', 'brand')} in {brand_info.get('industry', 'business')} industry, located in {brand_info.get('location', 'their area')}, showcasing {req.message[:50]}, {brand_info.get('unique_selling_points', ['quality service'])[0] if brand_info.get('unique_selling_points') else 'professional service'}, photorealistic style, modern design"
                            
                            # Get reference images from brand profile (S3 URLs)
                            reference_images = []
                            try:
                                brand_profile = db.get_brand_profile(user_id)
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
                            
                            # Generate image during preview (before approval)
                            image_path = None
                            try:
                                logger.info(f"Generating preview image for variant {variant['label']}...")
                                # Build comprehensive image prompt with business context
                                detailed_prompt = f"{image_prompt}. Brand: {brand_info.get('brand_name', '')}. Industry: {brand_info.get('industry', '')}. Location: {brand_info.get('location', '')}. Target audience: {brand_info.get('target_audience', '')}. Unique selling points: {', '.join(brand_info.get('unique_selling_points', []))}"
                                image_path = generate_image_with_runway(detailed_prompt, reference_images if reference_images else None)
                                logger.info(f"Preview image generated: {image_path}")
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
                                "platforms": ["twitter", "instagram"],
                                "hashtags": twitter_post.get('hashtags', []),
                                "keywords_used": keywords_data.get("keywords", [])[:5] if isinstance(keywords_data, dict) else [],
                                "image_prompt": image_prompt,
                                "image_path": image_path,  # Store generated image path
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
                            preview_url = f"/preview/image/{image_path}" if image_path else None
                            
                            db.save_generated_content(
                                content_id=content_id,
                                session_id=session_id,
                                content_type="post",
                                content=post_preview,
                                preview_url=preview_url,
                                metadata=metadata
                            )
                            
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
                            
                            response_options.append({
                                "option_id": option_id,
                                "label": variant["label"],
                                "tone": variant["tone"].title(),
                                "workflow_name": variant["workflow"]["workflow_name"],
                                "workflow_agents": variant["workflow"]["agents"],
                                "cost": workflow_cost_estimate["total_cost"],
                                "cost_display": cost_model.format_cost_display(workflow_cost_estimate["total_cost"]),
                                "content_id": content_id,
                                "content_type": "post",
                                "state_hash": state_hash,
                                "preview_text": f"{variant['label']} ready. Use preview to inspect each platform."
                            })
                        except Exception as variant_error:
                            logger.error(f"Social variant failed ({variant['label']}): {variant_error}", exc_info=True)
                            continue
                    
                    if response_options:
                        option_lines = "\n".join([
                            f"- {opt['label']}: {opt['tone']} tone · {opt['cost_display']} · workflow `{opt['workflow_name']}`"
                            for opt in response_options
                        ])
                        response_text = f"""📣 **Two Social Concepts Ready**

Pick the vibe that matches your campaign momentum:

{option_lines}

Select a card to commit the workflow and I'll generate visuals plus scheduling steps."""
                    else:
                        response_text = "⚠️ I couldn't generate social concepts right now. Please try again."
                except Exception as e:
                    logger.error(f"Social post error: {e}", exc_info=True)
                    response_text = f"⚠️ Post generation error: {str(e)}\n\nPlease try again with a different prompt."
            else:
                # Missing required fields - response_text already set above asking for info
                pass
        
        elif intent == "metrics_report":
            # Show metrics dashboard link
            response_text = "📊 **Social Media Metrics**\n\nView your performance metrics on the dashboard:\n\n[Open Metrics Dashboard](/metrics.html)\n\nI can also show specific metrics here. What would you like to see?"
        
        else:
            # Fallback
            response_text = await router.generate_conversational_response(req.message, history_for_router)
        
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
            brand_profile = db.get_brand_profile(user_id)
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
            response_options=response_options,
            clarification_request=clarification_request
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
        selection_message = f"✅ Locked in **{variant.get('label', 'your preferred option')}**. I'll continue with workflow `{variant['workflow_name']}`."
        
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
                s3_url = host_on_s3(preview_path, f"blogs/{content_id}.html")
                db.update_content_status(content_id, "approved", s3_url)
                return {"message": "Blog published successfully", "url": s3_url}
            
            elif content['type'] == 'post':
                # Post to social media platforms
                try:
                    metadata = content.get('metadata', {})
                    image_path = metadata.get('image_path') or content.get('preview_url')
                    post_data = metadata.get('post_copy') or {}
                    hashtags = metadata.get('hashtags', [])
                    platforms = metadata.get('platforms', ['twitter', 'instagram'])
                    
                    # Generate image if not exists
                    if not image_path or not os.path.exists(image_path):
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
                            logger.error(f"Image generation failed: {img_error}")
                            raise HTTPException(status_code=500, detail="Image generation failed")
                    
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
            # Update brand profile if it's a logo
            if asset_type == "logo":
                brand_profile = db.get_brand_profile(user_id)
                if brand_profile:
                    db.update_brand_profile(
                        user_id=user_id,
                        brand_name=brand_profile.get('brand_name'),
                        contacts=brand_profile.get('contacts'),
                        location=brand_profile.get('location'),
                        logo_url=s3_url
                    )
                else:
                    # Create brand profile with logo
                    db.save_brand_profile(
                        user_id=user_id,
                        brand_name="My Business",
                        contacts=None,
                        location=None,
                        logo_url=s3_url
                    )
            
            # Store in user assets (add to metadata or create new table entry)
            # For now, we'll store in brand profile metadata
            brand_profile = db.get_brand_profile(user_id)
            if brand_profile:
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
                
                db.update_brand_profile(
                    user_id=user_id,
                    brand_name=brand_profile.get('brand_name'),
                    contacts=brand_profile.get('contacts'),
                    location=brand_profile.get('location'),
                    logo_url=brand_profile.get('logo_url'),
                    metadata=metadata
                )
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

@app.get("/")
async def root():
    return {"message": "Orchestrator v5.0", "status": "running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8004)
