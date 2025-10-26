# content_agent.py
import os
import json
import time
import logging
import uuid
from typing import Optional, List, Dict, Any, Union
from datetime import datetime

import requests
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from groq import Groq

from fastapi.responses import FileResponse
# Load env
load_dotenv()

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Groq client
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY not set in environment.")
groq_client = Groq(api_key=GROQ_API_KEY)

# Config: endpoints of your other microservices
KEYWORD_EXTRACTOR_BASE = os.getenv("KEYWORD_EXTRACTOR_BASE", "http://127.0.0.1:8001")
GAP_ANALYZER_BASE = os.getenv("GAP_ANALYZER_BASE", "http://127.0.0.1:8002")
CRAWLER_BASE = os.getenv("CRAWLER_BASE", "http://127.0.0.1:8000")

# App
app = FastAPI(title="Content Generation Agent", version="1.0.0")

# Models
class AnalyzeContentRequest(BaseModel):
    page_json: Dict[str, Any]
    keywords: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None  # direct keywords/gap JSON (if provided)
    keywords_job_id: Optional[str] = None      # or pass an extractor job id to fetch
    site_url: Optional[str] = None             # optional site url for context
    target_tone: Optional[str] = "conversational"  # tone for suggestions
    max_replacements: Optional[int] = 10

class AnalyzeContentResponse(BaseModel):
    job_id: str
    status: str
    analysis: Optional[Dict[str, Any]] = None
    message: Optional[str] = None

class GenerateSocialRequest(BaseModel):
    keywords: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None
    keywords_job_id: Optional[str] = None
    platforms: Optional[List[str]] = ["linkedin", "facebook", "twitter", "instagram"]
    tone: Optional[str] = "professional"
    hashtags: Optional[List[str]] = []
    brand_name: Optional[str] = None
    industry: Optional[str] = None
    location: Optional[str] = None
    target_audience: Optional[str] = None
    unique_selling_points: Optional[List[str]] = []
    competitor_insights: Optional[str] = None
    user_request: Optional[str] = None
    image_style: Optional[str] = "photorealistic"

class GenerateSocialResponse(BaseModel):
    job_id: str
    status: str
    posts: Optional[Dict[str, Any]] = None
    message: Optional[str] = None

class GenerateBlogRequest(BaseModel):
    business_details: str
    keywords: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None
    keywords_job_id: Optional[str] = None
    crawled_content: Optional[Dict[str, Any]] = None # For existing websites
    gap_analysis: Optional[Dict[str, Any]] = None
    target_tone: Optional[str] = "informative"
    blog_length: Optional[str] = "medium" # short, medium, long

class GenerateBlogResponse(BaseModel):
    job_id: str
    status: str
    blog_html: Optional[str] = None
    message: Optional[str] = None

# In-memory jobstore (optional persist to file if needed)
jobs: Dict[str, Dict[str, Any]] = {}

# Helpers
def save_temp_file(prefix: str, content: bytes) -> str:
    os.makedirs("tmp", exist_ok=True)
    fname = f"tmp/{prefix}_{int(time.time())}_{uuid.uuid4().hex[:6]}.json"
    with open(fname, "wb") as f:
        f.write(content)
    return fname

def load_json_file(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(Exception))
def fetch_keywords_file_from_extractor(job_id: str) -> Dict[str, Any]:
    """Call the keyword extraction service /download endpoint and return parsed JSON."""
    download_url = f"{KEYWORD_EXTRACTOR_BASE}/download/{job_id}"
    logger.info(f"Fetching keywords file from extractor: {download_url}")
    r = requests.get(download_url, timeout=60)
    r.raise_for_status()
    # r.content is JSON file bytes; parse
    try:
        data = r.json()
        return data
    except Exception:
        # fallback: save to temp file and read
        tmp = save_temp_file("keywords", r.content)
        return load_json_file(tmp)

def normalize_keywords_input(keywords: Optional[Dict[str, Any]], keywords_job_id: Optional[str]) -> Dict[str, Any]:
    """Return a keywords dict from either provided keywords or fetched job id result."""
    if keywords:
        return keywords
    if keywords_job_id:
        data = fetch_keywords_file_from_extractor(keywords_job_id)
        # The extractor may return a list of competitor entries; wrap or reduce to useful shape
        # We'll try to return the whole JSON and let the Groq prompt pick what it needs
        return {"source": "extractor_job", "data": data}
    raise ValueError("Either 'keywords' or 'keywords_job_id' must be provided.")

def safe_groq_chat(prompt: str, model: str = "llama-3.3-70b-versatile", timeout: int = 120) -> Dict[str, Any]:
    """Call Groq aiming for strict JSON. If that fails, retry without response_format and sanitize output."""
    logger.info("Calling Groq (strict JSON)...")
    try:
        resp = groq_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        try:
            return json.loads(resp.choices[0].message.content)
        except Exception as e:
            logger.warning(f"Strict JSON parse failed: {e}. Falling back to sanitize.")
            text = resp.choices[0].message.content or ""
            # Try to extract JSON substring
            start = text.find("{"); end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                candidate = text[start:end+1]
                try:
                    return json.loads(candidate)
                except Exception:
                    pass
            return {"raw_text": text}
    except Exception as e:
        # Retry without response_format if server rejected strict JSON (e.g., json_validate_failed)
        logger.warning(f"Groq strict JSON request failed: {e}. Retrying without response_format...")
        relaxed_prompt = prompt + "\n\nReturn ONLY a valid JSON object. No prose, no code fences."
        resp2 = groq_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": relaxed_prompt}],
        )
        text = resp2.choices[0].message.content or ""
        # Sanitize to JSON
        start = text.find("{"); end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = text[start:end+1]
            try:
                return json.loads(candidate)
            except Exception as e2:
                logger.warning(f"Relaxed parse still failed: {e2}. Returning raw text.")
        return {"raw_text": text}

# Core prompt builders
def build_analyze_prompt(page_json: Dict[str, Any], keywords_obj: Dict[str, Any], site_url: Optional[str], tone: str, max_replacements: int) -> str:
    """
    Prompt Groq to analyze the page JSON and keyword gap data, and return a structured JSON indicating:
    - page_parts: list of { selector, current_text, issue, suggested_text, priority_score }
    - meta: { page_title, url, content_length }
    """
    # Keep prompt compact and instruct strict JSON output.
    # We will pass page_json and keywords as JSON strings inside the prompt.
    page_str = json.dumps(page_json, ensure_ascii=False)[:20000]  # truncate if extremely large
    keywords_str = json.dumps(keywords_obj, ensure_ascii=False)[:20000]
    prompt = f"""
You are an SEO & content optimization expert.

You are given:
1) A webpage structured JSON (headers, paragraphs, etc.) that represents an existing page.
2) A keyword-gap JSON (competitor keywords / gap analysis output) representing which keywords the site is missing or should emphasize.

Task:
- Identify up to {max_replacements} discrete page parts (for example: hero headline, product features section, pricing blurb, meta title, meta description, H2 sections, call-to-action) that should be changed to improve SEO and conversion given the keywords.
- For each part you identify, return:
  - id: short identifier
  - part_type: one of ["meta_title","meta_description","hero_headline","hero_subhead","h2_section","paragraph","cta","feature_bullet","image_alt"]
  - current_text: a short excerpt from the provided page JSON
  - issue: one-line reason why change is needed (SEO/semantic/clarity/keyword-miss)
  - priority: integer 1-5 (1 highest priority)
  - suggested_text: a concise replacement text (one or two lines) optimized for the product and keywords
  - suggested_notes: optional short guidance (tone, length, attributes)
- Also return a short "changes_summary" and a "content_action_plan" (ordered steps).

Input page JSON (truncated if long):
{page_str}

Input keywords/gap JSON (truncated if long):
{keywords_str}

Site URL: {site_url or "N/A"}
Tone: {tone}

Return ONLY a JSON object with keys:
{{
  "page_parts": [ ... ],
  "changes_summary": "short text",
  "content_action_plan": [ "step1", "step2", ... ],
  "meta": {{ "page_title": "", "url": "", "content_length": 0 }}
}}

Be strict JSON - don't include extra commentary.
"""
    return prompt

def build_social_prompt(
    keywords_obj: Dict[str, Any], 
    platforms: List[str], 
    tone: str, 
    hashtags: List[str], 
    brand_name: Optional[str], 
    image_style: str,
    industry: Optional[str] = None,
    location: Optional[str] = None,
    target_audience: Optional[str] = None,
    unique_selling_points: Optional[List[str]] = None,
    competitor_insights: Optional[str] = None,
    user_request: Optional[str] = None
) -> str:
    keywords_str = json.dumps(keywords_obj, ensure_ascii=False)[:15000]
    brand = brand_name or "My Business"
    
    # Build comprehensive business context
    business_context = f"""
=== BUSINESS PROFILE ===
Brand: {brand}
Industry: {industry or 'General'}
Location: {location or 'Not specified'}
Target Audience: {target_audience or 'General audience'}
Unique Selling Points: {', '.join(unique_selling_points) if unique_selling_points else 'Quality and service'}

=== USER REQUEST ===
{user_request or 'Create engaging social media content'}

=== COMPETITOR INSIGHTS ===
{competitor_insights or 'Stand out with unique value proposition'}
"""
    
    prompt = f"""
You are an expert social media content creator for brand marketing.

{business_context}

=== KEYWORD INSIGHTS (from SEO analysis) ===
{keywords_str}

Create highly engaging, location-aware social media posts that:
1. Specifically address the user's request: {user_request or 'general promotion'}
2. Highlight the business's unique strengths{' in ' + location if location else ''}
3. Appeal to the target audience: {target_audience or 'general audience'}
4. Incorporate relevant keywords naturally
5. Include location-based hashtags if location is provided

Return ONLY a valid JSON object with this EXACT structure:

{{
  "posts": {{
    "twitter": {{
      "copy": "tweet text here (mention location if relevant)",
      "length": 280,
      "call_to_action": "CTA here",
      "hashtags": ["#RelevantHashtag", "#{brand.replace(' ', '')}", {'"#' + location.replace(' ', '') + '"' if location else '""'}]
    }},
    "instagram": {{
      "copy": "instagram caption here (mention location and unique selling points)",
      "length": 300,
      "call_to_action": "CTA here",
      "hashtags": ["#RelevantHashtag", "#{brand.replace(' ', '')}", {'"#' + location.replace(' ', '') + '"' if location else '""'}, "#{''.join(industry.split()[:2]) if industry else 'Business'}"]
    }}
  }},
  "image_prompts": ["Photorealistic image prompt 1 for {brand}{' in ' + location if location else ''}", "Photorealistic image prompt 2 for {brand}"],
  "meta": {{
    "brand_name": "{brand}",
    "location": "{location or 'N/A'}",
    "industry": "{industry or 'General'}",
    "generated_at": "{datetime.utcnow().isoformat()}Z"
  }}
}}

Requirements:
- Posts must be relevant to: {user_request or 'business promotion'}
- Mention location ({location}) if provided
- Highlight unique selling points
- Keep Twitter under 280 characters
- Include brand name and location in hashtags
- Make image prompts {image_style}, specific to {brand}{' in ' + location if location else ''}, and relevant to the user's request
- Tone: {tone}

IMPORTANT: Return ONLY valid JSON. No extra text, explanations, or markdown formatting.
"""
    return prompt

def build_blog_prompt(business_details: str, keywords_obj: Dict[str, Any], crawled_content: Optional[Dict[str, Any]], gap_analysis: Optional[Dict[str, Any]], target_tone: str, blog_length: str) -> str:
    keywords_str = json.dumps(keywords_obj, ensure_ascii=False)[:15000]
    gap_str = json.dumps(gap_analysis, ensure_ascii=False)[:15000] if gap_analysis else "N/A"
    crawled_str = json.dumps(crawled_content, ensure_ascii=False)[:20000] if crawled_content else "N/A"

    prompt = f"""
You are an expert blog post writer for SEO and content marketing, with advanced knowledge of HTML, CSS, and JavaScript for responsive design.

Given the following information:
- Business Details: {business_details}
- Keyword Insights (JSON): {keywords_str}
- Competitor Gap Analysis (JSON): {gap_str}
- Existing Website Content (JSON, if applicable): {crawled_str}

Task:
Generate a comprehensive blog post in **HTML format** enhanced with **CSS and JavaScript**.
The blog post should:
1. Content:
   - Have an engaging and SEO-friendly title.
   - Include an introduction, several body paragraphs with relevant subheadings (H2, H3).
   - Incorporate the provided keywords naturally throughout the content.
   - Address insights from the competitor gap analysis to provide unique value.
   - Conclude with a strong call to action.
   - Use semantic HTML5 structure (<header>, <main>, <section>, <article>, <footer>).

2. Design (CSS):
   - Provide fully responsive CSS (mobile-first, scaling up to tablets and desktops).
   - Use a clean, modern, and professional design with proper typography and spacing.
   - Include a responsive navigation bar (collapsible into a hamburger menu on mobile).
   - Style headings, paragraphs, call-to-action buttons, and blockquotes.
   - Add hover effects and smooth transitions for interactive elements.
   - Ensure accessibility (contrast, readable font sizes, ARIA roles if needed).

3. Interactivity (JavaScript):
   - Include a working mobile navigation toggle (hamburger menu).
   - Add smooth scroll functionality for internal links.
   - Include a "Back to Top" button that appears on scroll.
   - Add simple entrance animations (fade-in, slide-up) for sections when they enter the viewport.

4. Output:
   - The final result must be valid HTML with embedded CSS (<style>) and JavaScript (<script>).
   - Do NOT use external libraries (e.g., Bootstrap, jQuery). Use only vanilla CSS and JavaScript.
   - Ensure the code is production-ready and optimized for performance.
   - Target Tone: {target_tone}
   - Desired Length: {blog_length} (e.g., short: ~500 words, medium: ~1000 words, long: ~1500+ words)

Return ONLY a JSON object with a single key "html_content" containing the full HTML, CSS, and JS of the blog post.
Example: {{"html_content": "<!DOCTYPE html><html>...</html>"}}
"""

    return prompt

# Background task implementations
async def analyze_content_background(page_json: Dict[str, Any], keywords_obj: Dict[str, Any], site_url: Optional[str], tone: str, max_replacements: int, job_id: str):
    jobs[job_id] = {"status": "running", "start_time": datetime.now()}
    save_path = None
    try:
        prompt = build_analyze_prompt(page_json, keywords_obj, site_url, tone, max_replacements)
        analysis = safe_groq_chat(prompt)
        # Validate structure minimally
        if not isinstance(analysis, dict) or "page_parts" not in analysis:
            logger.warning("Groq returned unexpected analysis structure; wrapping raw output.")
            analysis = {"page_parts": [], "changes_summary": "", "content_action_plan": [], "meta": {"page_title": "", "url": site_url or "", "content_length": 0}, "raw": analysis}
        # Save results
        save_path = f"content_analysis_{job_id[:8]}.json"
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(analysis, f, indent=2, ensure_ascii=False)
        jobs[job_id].update({"status": "completed", "results_file": save_path, "analysis": analysis, "end_time": datetime.now()})
    except Exception as e:
        logger.error(f"Content analysis job {job_id} failed: {e}")
        jobs[job_id].update({"status": "failed", "message": str(e), "end_time": datetime.now()})

async def generate_social_background(
    keywords_obj: Dict[str, Any], 
    platforms: List[str], 
    tone: str, 
    hashtags: List[str], 
    brand_name: Optional[str], 
    image_style: str, 
    job_id: str,
    industry: Optional[str] = None,
    location: Optional[str] = None,
    target_audience: Optional[str] = None,
    unique_selling_points: Optional[List[str]] = None,
    competitor_insights: Optional[str] = None,
    user_request: Optional[str] = None
):
    jobs[job_id] = {"status": "running", "start_time": datetime.now()}
    save_path = None
    try:
        prompt = build_social_prompt(
            keywords_obj, 
            platforms, 
            tone, 
            hashtags, 
            brand_name, 
            image_style,
            industry=industry,
            location=location,
            target_audience=target_audience,
            unique_selling_points=unique_selling_points,
            competitor_insights=competitor_insights,
            user_request=user_request
        )
        generated = safe_groq_chat(prompt)
        if not isinstance(generated, dict) or "posts" not in generated:
            # fallback wrapper
            generated = {"posts": {}, "image_prompts": [], "meta": {"brand_name": brand_name, "generated_at": datetime.utcnow().isoformat()}, "raw": generated}
        save_path = f"social_posts_{job_id[:8]}.json"
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(generated, f, indent=2, ensure_ascii=False)
        jobs[job_id].update({"status": "completed", "results_file": save_path, "posts": generated, "end_time": datetime.now()})
    except Exception as e:
        logger.error(f"Social generation job {job_id} failed: {e}")
        jobs[job_id].update({"status": "failed", "message": str(e), "end_time": datetime.now()})

async def generate_blog_background(business_details: str, keywords_obj: Dict[str, Any], crawled_content: Optional[Dict[str, Any]], gap_analysis: Optional[Dict[str, Any]], target_tone: str, blog_length: str, job_id: str):
    jobs[job_id] = {"status": "running", "start_time": datetime.now()}
    save_path = None
    try:
        prompt = build_blog_prompt(business_details, keywords_obj, crawled_content, gap_analysis, target_tone, blog_length)
        blog_response = safe_groq_chat(prompt)
        
        blog_html = blog_response.get("html_content", "")
        if not blog_html:
            logger.warning("Groq did not return 'html_content' for blog; using raw output.")
            blog_html = f"<html><body><h1>Error Generating Blog</h1><p>Could not generate blog content. Raw response: {json.dumps(blog_response)}</p></body></html>"

        save_path = f"blog_post_{job_id[:8]}.html"
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(blog_html)
        
        jobs[job_id].update({"status": "completed", "results_file": save_path, "blog_html": blog_html, "end_time": datetime.now()})
    except Exception as e:
        logger.error(f"Blog generation job {job_id} failed: {e}")
        jobs[job_id].update({"status": "failed", "message": str(e), "end_time": datetime.now()})

def ensure_keywords_object(keywords: Optional[Dict[str, Any]], keywords_job_id: Optional[str]) -> Dict[str, Any]:
    try:
        return normalize_keywords_input(keywords, keywords_job_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not obtain keywords: {e}")

# Endpoints
@app.post("/analyze-content", response_model=AnalyzeContentResponse)
async def analyze_content(req: AnalyzeContentRequest, background_tasks: BackgroundTasks):
    # validate input
    try:
        keywords_obj = ensure_keywords_object(req.keywords, req.keywords_job_id)
    except HTTPException as ex:
        raise ex

    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "queued", "start_time": datetime.now()}
    # schedule background task
    background_tasks.add_task(analyze_content_background, req.page_json, keywords_obj, req.site_url, req.target_tone, req.max_replacements, job_id)
    return AnalyzeContentResponse(job_id=job_id, status="started", message="Content analysis started")

@app.post("/generate-social", response_model=GenerateSocialResponse)
async def generate_social(req: GenerateSocialRequest, background_tasks: BackgroundTasks):
    try:
        keywords_obj = ensure_keywords_object(req.keywords, req.keywords_job_id)
    except HTTPException as ex:
        raise ex

    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "queued", "start_time": datetime.now()}
    background_tasks.add_task(
        generate_social_background, 
        keywords_obj, 
        req.platforms or ["linkedin"], 
        req.tone, 
        req.hashtags or [], 
        req.brand_name, 
        req.image_style, 
        job_id,
        industry=req.industry,
        location=req.location,
        target_audience=req.target_audience,
        unique_selling_points=req.unique_selling_points,
        competitor_insights=req.competitor_insights,
        user_request=req.user_request
    )
    return GenerateSocialResponse(job_id=job_id, status="started", message="Social generation started")

@app.post("/generate-blog", response_model=GenerateBlogResponse)
async def generate_blog(req: GenerateBlogRequest, background_tasks: BackgroundTasks):
    try:
        keywords_obj = ensure_keywords_object(req.keywords, req.keywords_job_id)
    except HTTPException as ex:
        raise ex

    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "queued", "start_time": datetime.now()}
    background_tasks.add_task(
        generate_blog_background,
        req.business_details,
        keywords_obj,
        req.crawled_content,
        req.gap_analysis,
        req.target_tone,
        req.blog_length,
        job_id
    )
    return GenerateBlogResponse(job_id=job_id, status="started", message="Blog generation started")

@app.get("/status/{job_id}")
async def get_job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    result = jobs[job_id].copy()
    # If results file exists, include path
    return result

@app.get("/download/json/{job_id}")
async def download_results(job_id: str):
    """Download the JSON results file for a completed job."""
    # 1. Check if the job exists
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[job_id]

    # 2. Check if the job is completed
    if job.get("status") != "completed":
        raise HTTPException(status_code=400, detail="Job is not yet complete.")

    # 3. Check if the results file path exists and the file is on disk
    results_file = job.get("results_file")
    if not results_file or not os.path.exists(results_file):
        raise HTTPException(status_code=404, detail="Results file not found. The job may have completed without generating a file.")

    # 4. Return the file as a response
    return FileResponse(
        path=results_file,
        filename=os.path.basename(results_file),
        media_type="application/json"
    )

@app.get("/download/html/{job_id}")
async def download_blog_html(job_id: str):
    """Download the HTML blog post for a completed job."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[job_id]

    if job.get("status") != "completed":
        raise HTTPException(status_code=400, detail="Job is not yet complete.")

    results_file = job.get("results_file")
    if not results_file or not os.path.exists(results_file):
        raise HTTPException(status_code=404, detail="Blog HTML file not found.")

    return FileResponse(
        path=results_file,
        filename=os.path.basename(results_file),
        media_type="text/html"
    )

@app.get("/")
async def root():
    return {"message": "Content Generation Agent", "version": "1.0.0", "endpoints": {
        "POST /analyze-content": "Analyze a page JSON with keyword insights",
        "POST /generate-social": "Generate social posts from keyword insights",
        "POST /generate-blog": "Generate a blog post from business details and keywords",
        "GET /status/{job_id}": "Get job status/results",
        "GET /download/json/{job_id}": "Download JSON results for a completed job",
        "GET /download/html/{job_id}": "Download HTML blog post for a completed job"
    }}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8003)
