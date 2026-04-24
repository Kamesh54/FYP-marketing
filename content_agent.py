# content_agent.py
import os
import json
import time
import logging
import uuid
import re
from typing import Optional, List, Dict, Any, Union
from datetime import datetime

import requests
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from groq import Groq

# Knowledge graph context (optional — gracefully disabled if Neo4j is unavailable)
try:
    from graph.graph_context import get_brand_knowledge_context, format_kg_context_for_prompt
    KG_AVAILABLE = True
except Exception:
    KG_AVAILABLE = False
    def get_brand_knowledge_context(brand_name): return {"available": False}  # noqa
    def format_kg_context_for_prompt(ctx): return ""  # noqa

from fastapi.responses import FileResponse

# Load env
load_dotenv()

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import shared global cooldown (accessible to ALL agents) — after logger is set up
try:
    from shared_cooldown import is_model_on_cooldown, get_cooldown_remaining, handle_groq_429
    SHARED_COOLDOWN_AVAILABLE = True
except ImportError:
    SHARED_COOLDOWN_AVAILABLE = False
    logger.warning("shared_cooldown not found; cooldown will not be shared across agents.")


def _is_rate_limited_error(error_text: str) -> bool:
    text = (error_text or "").lower()
    return "429" in text or "rate_limit" in text or "too many requests" in text


def _parse_retry_after_seconds(error_text: str) -> float:
    text = error_text or ""
    m = re.search(r"try again in\s+(\d+)m(\d+(?:\.\d+)?)s", text, flags=re.IGNORECASE)
    if m:
        return float(m.group(1)) * 60.0 + float(m.group(2))

    s = re.search(r"try again in\s+(\d+(?:\.\d+)?)\s*(?:seconds?|s)", text, flags=re.IGNORECASE)
    if s:
        return float(s.group(1))

    return 45.0

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
    variant_label: Optional[str] = None
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


def _get_groq_model_candidates(primary_model: str) -> List[str]:
    """Return ordered model list: primary first, then configured fallbacks."""
    fallback_raw = os.getenv(
        "GROQ_FALLBACK_MODELS",
        "meta-llama/llama-4-scout-17b-16e-instruct,qwen/qwen3-32b,openai/gpt-oss-120b,openai/gpt-oss-20b,llama-3.1-8b-instant,llama3-8b-8192",
    )
    models = [primary_model]
    models.extend([m.strip() for m in fallback_raw.split(",") if m.strip()])

    deduped: List[str] = []
    for m in models:
        if m not in deduped:
            deduped.append(m)
    return deduped

def safe_groq_chat(prompt: str, model: str = "llama-3.3-70b-versatile", timeout: int = 120,
                   system_instruction: Optional[str] = None, strict_json: bool = True) -> Dict[str, Any]:
    """
    Call Groq aiming for strict JSON. If that fails, retry without response_format and sanitize output.
    Uses SHARED GLOBAL cooldown to prevent repeated 429s across all agents.
    """
    if not groq_client:
        return {
            "error": "groq_unavailable",
            "message": "Groq client is not configured.",
        }

    logger.info("Calling Groq (strict JSON)...")
    messages: List[Dict[str, str]] = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.append({"role": "user", "content": prompt})

    models_to_try = _get_groq_model_candidates(model)
    last_error = ""
    saw_rate_limit = False

    for candidate_model in models_to_try:
        # === HARD CHECK: Is this model on global cooldown? ===
        if SHARED_COOLDOWN_AVAILABLE and is_model_on_cooldown(candidate_model):
            remaining = get_cooldown_remaining(candidate_model)
            if remaining is not None:
                logger.info(f"Skipping model {candidate_model} due to active cooldown ({remaining:.1f}s left)")
            continue

        try:
            request_kwargs: Dict[str, Any] = {
                "model": candidate_model,
                "messages": messages,
                "timeout": timeout,
            }
            if strict_json:
                request_kwargs["response_format"] = {"type": "json_object"}

            resp = groq_client.chat.completions.create(**request_kwargs)
            try:
                parsed = json.loads(resp.choices[0].message.content)
                if isinstance(parsed, dict):
                    parsed.setdefault("_model_used", candidate_model)
                return parsed
            except Exception as e:
                logger.warning(f"Strict JSON parse failed on {candidate_model}: {e}. Falling back to sanitize.")
                text = resp.choices[0].message.content or ""
                start = text.find("{")
                end = text.rfind("}")
                if start != -1 and end != -1 and end > start:
                    candidate = text[start:end+1]
                    try:
                        parsed = json.loads(candidate)
                        if isinstance(parsed, dict):
                            parsed.setdefault("_model_used", candidate_model)
                        return parsed
                    except Exception:
                        pass
                return {"raw_text": text, "_model_used": candidate_model}
        except Exception as e:
            last_error = str(e)
            
            # === SHARED COOLDOWN: On 429, register with global cooldown ===
            if _is_rate_limited_error(last_error):
                saw_rate_limit = True
                if SHARED_COOLDOWN_AVAILABLE:
                    # Let shared_cooldown parse and set the cooldown
                    try:
                        error_dict = {}
                        # Try to extract error dict from exception
                        if hasattr(e, 'response'):
                            try:
                                error_dict = e.response.json()
                            except:
                                error_dict = {"error": {"message": last_error}}
                        else:
                            error_dict = {"error": {"message": last_error}}
                        handle_groq_429(candidate_model, error_dict)
                    except Exception as cooldown_err:
                        logger.warning(f"Failed to set shared cooldown: {cooldown_err}")

            if not strict_json:
                mode_label = "strict JSON" if strict_json else "standard"
                logger.error(f"Groq {mode_label} request failed on {candidate_model}: {e}")
                continue

            mode_label = "strict JSON" if strict_json else "standard"
            logger.warning(f"Groq {mode_label} request failed on {candidate_model}: {e}. Retrying without response_format...")

            relaxed_prompt = prompt + "\n\nReturn ONLY a valid JSON object. No prose, no code fences."
            retry_messages: List[Dict[str, str]] = []
            if system_instruction:
                retry_messages.append({"role": "system", "content": system_instruction})
            retry_messages.append({"role": "user", "content": relaxed_prompt})

            try:
                resp2 = groq_client.chat.completions.create(
                    model=candidate_model,
                    messages=retry_messages,
                    timeout=timeout,
                )
                text = resp2.choices[0].message.content or ""
                start = text.find("{")
                end = text.rfind("}")
                if start != -1 and end != -1 and end > start:
                    candidate = text[start:end+1]
                    try:
                        parsed = json.loads(candidate)
                        if isinstance(parsed, dict):
                            parsed.setdefault("_model_used", candidate_model)
                        return parsed
                    except Exception as e2:
                        logger.warning(f"Relaxed parse failed on {candidate_model}: {e2}")
                return {"raw_text": text, "_model_used": candidate_model}
            except Exception as e2:
                last_error = str(e2)
                
                # === SHARED COOLDOWN: On 429 during relaxed retry ===
                if _is_rate_limited_error(last_error):
                    saw_rate_limit = True
                    if SHARED_COOLDOWN_AVAILABLE:
                        try:
                            error_dict = {}
                            if hasattr(e2, 'response'):
                                try:
                                    error_dict = e2.response.json()
                                except:
                                    error_dict = {"error": {"message": last_error}}
                            else:
                                error_dict = {"error": {"message": last_error}}
                            handle_groq_429(candidate_model, error_dict)
                        except Exception as cooldown_err:
                            logger.warning(f"Failed to set shared cooldown: {cooldown_err}")
                
                logger.error(f"Groq relaxed request failed on {candidate_model}: {e2}")
                continue

    if saw_rate_limit:
        return {
            "error": "rate_limited",
            "message": "Groq limits reached on all configured models.",
            "models_attempted": models_to_try,
        }

    return {
        "error": "groq_request_failed",
        "message": last_error or "Unknown Groq failure",
        "models_attempted": models_to_try,
    }

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
    user_request: Optional[str] = None,
    kg_context: Optional[str] = None
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

{kg_context or ''}"""
    
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
  "image_prompts": ["Photorealistic image prompt 1 for {brand}{' in ' + location if location else ' '} prominently featuring brand name '{brand}' in the image text", "Photorealistic image prompt 2 for {brand} prominence for '{brand}'"],
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

def build_blog_prompt(business_details: str, keywords_obj: Dict[str, Any], crawled_content: Optional[Dict[str, Any]], gap_analysis: Optional[Dict[str, Any]], target_tone: str, blog_length: str, variant_label: Optional[str] = None, kg_context: Optional[str] = None) -> str:
    keywords_str = json.dumps(keywords_obj, ensure_ascii=False)[:15000]
    gap_str = json.dumps(gap_analysis, ensure_ascii=False)[:15000] if gap_analysis else "N/A"
    crawled_str = json.dumps(crawled_content, ensure_ascii=False)[:20000] if crawled_content else "N/A"
    kg_str = kg_context or ""

    # Determine CSS style based on variant - ENHANCED with next-level design
    if variant_label and "Option A" in variant_label:
        css_style_instruction = """
   - Use a sophisticated, research-focused design with NEXT-LEVEL features:
     * Deep, professional color scheme (navy blues, charcoal grays, accent with gold/amber)
     * Elegant serif fonts for headings (Georgia, 'Times New Roman', or similar) with variable font weights
     * Generous white space and wide margins with CSS Grid/Flexbox layouts
     * Glassmorphism effects on cards (backdrop-filter: blur, semi-transparent backgrounds)
     * Subtle gradients, multi-layered shadows, and depth with CSS transforms
     * Academic/research paper aesthetic with refined typography and reading-friendly line heights
     * Premium feel with sophisticated hover effects, scale transforms, and smooth transitions
     * Data visualization-friendly color palette with gradient overlays
     * Parallax scrolling effects for hero sections
     * Advanced CSS animations using @keyframes for micro-interactions"""
    elif variant_label and "Option B" in variant_label:
        css_style_instruction = """
   - Use a vibrant, conversion-focused design with NEXT-LEVEL features:
     * Bold, energetic color scheme (bright blues, vibrant oranges, energetic greens) with gradient overlays
     * Modern sans-serif fonts (Inter, 'Segoe UI', system fonts) with variable font weights
     * Dynamic layouts with CSS Grid cards, masonry-style sections, and asymmetric designs
     * Eye-catching call-to-action buttons with pulse animations, gradient backgrounds, and 3D hover effects
     * Modern gradient backgrounds, animated gradients, and bold typography with text shadows
     * Social media-friendly, shareable aesthetic with floating action buttons
     * Conversion-optimized with prominent CTAs, sticky headers, and scroll-triggered animations
     * Glassmorphism on navigation and cards
     * Advanced hover states with transform and filter effects"""
    else:
        css_style_instruction = """
   - Use a PREMIUM, next-level modern design with:
     * Advanced CSS Grid and Flexbox for sophisticated layouts
     * Modern color palette with CSS custom properties (variables) for theming
     * Glassmorphism effects, gradient overlays, and backdrop filters
     * Smooth animations, micro-interactions, and scroll-triggered effects
     * Professional typography with optimal line heights and letter spacing
     * Advanced shadows, borders, and depth effects
     * Responsive design with mobile-first approach and breakpoint optimization"""

    prompt = f"""
You are an expert blog post writer for SEO and content marketing, with ADVANCED knowledge of modern HTML5, CSS3, and JavaScript (ES6+) for creating PREMIUM, next-level blog websites.

Given the following information:
- Business Details: {business_details}
- Keyword Insights (JSON): {keywords_str}
- Competitor Gap Analysis (JSON): {gap_str}
- Existing Website Content (JSON, if applicable): {crawled_str}

{kg_str}

Task:
Generate a COMPREHENSIVE, NEXT-LEVEL blog post in **HTML format** with PREMIUM design and advanced interactivity.

1. CONTENT STRUCTURE:
   - Create an engaging, SEO-friendly title with proper H1 tag.
   - Include a compelling hero section with the title and a brief intro.
   - Add a dynamic Table of Contents (TOC) that auto-generates from H2/H3 headings with smooth scroll navigation.
   - Include an introduction, several body paragraphs with relevant subheadings (H2, H3).
   - Incorporate the provided keywords naturally throughout the content.
   - Address insights from the competitor gap analysis to provide unique value.
   - Add visually appealing blockquotes, lists, and code blocks (if applicable).
   - Include a conclusion section with a strong, animated call-to-action button.
   - Use semantic HTML5 structure (<header>, <nav>, <main>, <article>, <section>, <aside>, <footer>).
   - Add proper meta tags for SEO (title, description, Open Graph tags).

2. PREMIUM DESIGN (CSS) - NEXT LEVEL:
   - Provide fully responsive CSS (mobile-first, scaling up to tablets and desktops).
{css_style_instruction}
   - Include a STICKY, responsive navigation bar with glassmorphism effect (backdrop-filter: blur).
   - Add a READING PROGRESS BAR at the top that fills as user scrolls (use CSS linear-gradient).
   - Create a floating Table of Contents sidebar (desktop) or collapsible section (mobile).
   - Style headings with gradient text effects, shadows, and smooth animations.
   - Design premium call-to-action buttons with gradient backgrounds, hover animations, and 3D effects.
   - Add glassmorphism cards for sections with backdrop-filter and semi-transparent backgrounds.
   - Include smooth scroll behavior and parallax effects for hero sections.
   - Add advanced hover effects: scale transforms, color transitions, shadow elevations.
   - Create a dark mode toggle button with smooth theme transition.
   - Style blockquotes with left border accent, italic text, and background highlights.
   - Add social sharing buttons (Twitter, Facebook, LinkedIn) with hover animations.
   - Include a "Back to Top" floating button with smooth fade-in/out and scroll animation.
   - Add reading time calculator display near the title.
   - Use CSS custom properties (variables) for theming and easy color changes.
   - Implement advanced animations: fade-in, slide-up, scale-in using @keyframes.
   - Add micro-interactions: button ripples, card lift effects, text highlight on scroll.
   - Ensure accessibility: proper contrast ratios, ARIA labels, focus states, skip links.

3. ADVANCED INTERACTIVITY (JavaScript):
   - Implement a working mobile navigation toggle (hamburger menu with smooth animation).
   - Add smooth scroll functionality for internal links and TOC navigation.
   - Create a READING PROGRESS BAR that updates dynamically on scroll.
   - Implement Intersection Observer API for scroll-triggered animations (fade-in sections).
   - Add a "Back to Top" button that appears after scrolling 300px with smooth animation.
   - Calculate and display READING TIME based on word count (average 200 words/minute).
   - Generate Table of Contents automatically from H2/H3 headings with click-to-scroll.
   - Implement DARK MODE toggle with localStorage persistence.
   - Add social sharing functionality (Twitter, Facebook, LinkedIn) with proper URL encoding.
   - Create smooth scroll behavior for all anchor links.
   - Add scroll spy to highlight current section in TOC.
   - Implement lazy loading for images (if any) using Intersection Observer.
   - Add copy-to-clipboard functionality for code blocks (if present).
   - Create smooth page transitions and entrance animations.

4. PREMIUM FEATURES TO INCLUDE:
   - Hero section with gradient background and animated text.
   - Sticky header that changes appearance on scroll.
   - Floating action buttons for social sharing.
   - Reading progress indicator at top of page.
   - Table of contents with active section highlighting.
   - Reading time display.
   - Dark mode toggle with smooth transition.
   - Smooth scroll behavior throughout.
   - Advanced animations and micro-interactions.
   - Responsive image handling (if images are included).
   - Print-friendly styles using @media print.

5. OUTPUT REQUIREMENTS:
   - The final result must be valid HTML5 with embedded CSS (<style>) and JavaScript (<script>).
   - Do NOT use external libraries (e.g., Bootstrap, jQuery, React). Use only vanilla CSS and JavaScript.
   - Use modern JavaScript (ES6+): arrow functions, const/let, template literals, async/await if needed.
   - Ensure the code is production-ready, optimized for performance, and follows best practices.
   - Target Tone: {target_tone}
   - Desired Length: {blog_length} (e.g., short: ~500 words, medium: ~1000 words, long: ~1500+ words)
   - Include proper error handling in JavaScript.
   - Optimize CSS with efficient selectors and avoid unnecessary specificity.

CRITICAL: Create a STUNNING, PREMIUM, next-level blog design that rivals top-tier modern websites. Use advanced CSS techniques (Grid, Flexbox, Custom Properties, Animations, Transforms, Filters, Backdrop Filters). Make it visually impressive, highly interactive, and professional. The design should feel modern, polished, and engaging.

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
        # Pull brand memory from knowledge graph before generating
        kg_context = ""
        if brand_name:
            try:
                raw_ctx = get_brand_knowledge_context(brand_name)
                kg_context = format_kg_context_for_prompt(raw_ctx)
                if raw_ctx.get("available"):
                    logger.info(f"KG context loaded for '{brand_name}': {raw_ctx.get('total_content_count', 0)} past pieces")
            except Exception as kg_err:
                logger.warning(f"KG context fetch failed (non-fatal): {kg_err}")

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
            user_request=user_request,
            kg_context=kg_context
        )

        # ── Prompt Optimizer wiring ──────────────────────────────────────
        _sys_instruction: Optional[str] = None
        _prompt_version_id: Optional[str] = None
        try:
            from prompt_optimizer import register_prompt
            from database import get_best_prompt as _db_best_prompt
            # Only use an evolved (scored) prompt as system instruction — never seed templates
            _best_row = _db_best_prompt("content_agent", "social_post")
            if _best_row:
                _sys_instruction = _best_row["prompt_text"]
                logger.info("[PromptOptimizer] Using evolved system instruction for social_post")
            _prompt_version_id = register_prompt("content_agent", "social_post", prompt)
            logger.info(f"[PromptOptimizer] Registered social_post prompt version {_prompt_version_id}")
        except Exception as _po_err:
            logger.warning(f"[PromptOptimizer] Social wiring skipped: {_po_err}")
        # ────────────────────────────────────────────────────────────────

        generated = safe_groq_chat(prompt, system_instruction=_sys_instruction)
        if not isinstance(generated, dict) or "posts" not in generated:
            # fallback wrapper
            generated = {"posts": {}, "image_prompts": [], "meta": {"brand_name": brand_name, "generated_at": datetime.utcnow().isoformat()}, "raw": generated}
        save_path = f"social_posts_{job_id[:8]}.json"
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(generated, f, indent=2, ensure_ascii=False)
        jobs[job_id].update({"status": "completed", "results_file": save_path, "posts": generated,
                              "prompt_version_id": _prompt_version_id, "end_time": datetime.now()})
    except Exception as e:
        logger.error(f"Social generation job {job_id} failed: {e}")
        jobs[job_id].update({"status": "failed", "message": str(e), "end_time": datetime.now()})

def _clean_markdown_wrapped_html(text: str) -> str:
    """Extract actual HTML from markdown code blocks or JSON wrappers."""
    if not text:
        return ""
    
    text = text.strip()
    
    # Remove markdown code block wrapper (```json ... ```)
    if text.startswith("```json"):
        text = text[7:]  # Remove ```json
    elif text.startswith("```html"):
        text = text[7:]  # Remove ```html
    elif text.startswith("```"):
        text = text[3:]  # Remove generic ```
    
    if text.endswith("```"):
        text = text[:-3]  # Remove closing ```
    
    text = text.strip()
    
    # If it's wrapped in JSON, extract the html_content field
    if text.startswith("{"):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                # Try various keys
                for key in ["html_content", "html", "content", "body"]:
                    if key in parsed:
                        return str(parsed[key]).strip()
                # If none found, return the first string value
                for v in parsed.values():
                    if isinstance(v, str):
                        return v.strip()
        except json.JSONDecodeError:
            pass
    
    # Return as-is if it's already HTML
    if text.startswith("<!DOCTYPE") or text.startswith("<html"):
        return text
    
    return text

async def generate_blog_background(business_details: str, keywords_obj: Dict[str, Any], crawled_content: Optional[Dict[str, Any]], gap_analysis: Optional[Dict[str, Any]], target_tone: str, blog_length: str, job_id: str, variant_label: Optional[str] = None):
    jobs[job_id] = {"status": "running", "start_time": datetime.now()}
    save_path = None
    try:
        # Pull brand memory from knowledge graph before generating
        kg_context = ""
        try:
            import re
            brand_match = re.search(r'(?:brand[_\s]*name|business[_\s]*name|company)[:\s]+([\w\s&\'\-\.]+)', business_details, re.IGNORECASE)
            brand_name_hint = brand_match.group(1).strip()[:60] if brand_match else ""
            if brand_name_hint:
                raw_ctx = get_brand_knowledge_context(brand_name_hint)
                kg_context = format_kg_context_for_prompt(raw_ctx)
                if raw_ctx.get("available"):
                    logger.info(f"KG context loaded for blog '{brand_name_hint}': {raw_ctx.get('total_content_count', 0)} past pieces")
        except Exception as kg_err:
            logger.warning(f"KG context fetch failed for blog (non-fatal): {kg_err}")

        prompt = build_blog_prompt(business_details, keywords_obj, crawled_content, gap_analysis, target_tone, blog_length, variant_label, kg_context=kg_context)

        # ── Prompt Optimizer wiring ──────────────────────────────────────
        _sys_instruction_blog: Optional[str] = None
        _prompt_version_id_blog: Optional[str] = None
        try:
            from prompt_optimizer import register_prompt
            from database import get_best_prompt as _db_best_prompt_blog
            # Only use an evolved (scored) prompt as system instruction — never seed templates
            _best_blog_row = _db_best_prompt_blog("content_agent", "blog")
            if _best_blog_row:
                _sys_instruction_blog = _best_blog_row["prompt_text"]
                logger.info("[PromptOptimizer] Using evolved system instruction for blog")
            _prompt_version_id_blog = register_prompt("content_agent", "blog", prompt)
            logger.info(f"[PromptOptimizer] Registered blog prompt version {_prompt_version_id_blog}")
        except Exception as _po_err:
            logger.warning(f"[PromptOptimizer] Blog wiring skipped: {_po_err}")
        # ────────────────────────────────────────────────────────────────

        blog_response = safe_groq_chat(
            prompt,
            system_instruction=_sys_instruction_blog,
            strict_json=False,
        )
        
        blog_html = blog_response.get("html_content", "")
        
        # Clean up markdown-wrapped responses
        blog_html = _clean_markdown_wrapped_html(blog_html)
        
        if not blog_html or blog_html.startswith("{"):
            logger.warning("Groq did not return valid 'html_content' for blog; using raw output.")
            blog_html = f"<html><body><h1>Error Generating Blog</h1><p>Could not generate blog content. Raw response: {json.dumps(blog_response)}</p></body></html>"

        save_path = f"blog_post_{job_id[:8]}.html"
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(blog_html)
        
        jobs[job_id].update({"status": "completed", "results_file": save_path, "blog_html": blog_html,
                              "prompt_version_id": _prompt_version_id_blog, "end_time": datetime.now()})
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
        job_id,
        req.variant_label
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
