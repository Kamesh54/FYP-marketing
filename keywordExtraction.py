import requests
import json
import re
import os
import time
import uuid
from collections import Counter
from rake_nltk import Rake
import nltk
from fastapi import FastAPI, HTTPException, BackgroundTasks
from starlette.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List
import serpapi
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import logging
from dotenv import load_dotenv
from datetime import datetime
import unicodedata
from groq import Groq
from llm_failover import groq_chat_with_failover

_PLACEHOLDER_BRANDS = {
    "",
    "company",
    "my business",
    "business",
    "brand",
    "unknown",
    "n/a",
    "na",
    "none",
}


def _extract_seed_value(statement: str, labels: List[str]) -> str:
    if not statement:
        return ""
    for line in statement.splitlines():
        raw = line.strip()
        if not raw or ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        if key.strip().lower() in labels:
            return value.strip()
    return ""


def _is_valid_brand_seed(name: str) -> bool:
    if not name:
        return False
    return name.strip().lower() not in _PLACEHOLDER_BRANDS


def _tokenize_seed(text: str) -> List[str]:
    if not text:
        return []
    tokens = re.findall(r"[a-zA-Z0-9]{3,}", text.lower())
    stop = {"and", "the", "with", "for", "from", "best", "top", "brand", "brands", "company", "companies"}
    return [t for t in tokens if t not in stop]


def _build_fallback_domains(brand_seed: str, industry_seed: str) -> List[str]:
    if _is_valid_brand_seed(brand_seed):
        if industry_seed:
            return [
                f"{brand_seed} {industry_seed} competitors",
                f"top {industry_seed} brands",
                f"{industry_seed} alternatives to {brand_seed}",
            ]
        return [
            f"{brand_seed} competitors",
            f"alternatives to {brand_seed}",
            f"brands similar to {brand_seed}",
        ]
    if industry_seed:
        return [
            f"top {industry_seed} brands",
            f"{industry_seed} companies",
            f"best {industry_seed} manufacturers",
        ]
    return ["top brands in this market", "direct competitors in this industry"]


def _filter_domains_by_seed(domains: List[str], brand_seed: str, industry_seed: str) -> List[str]:
    """
    Filter domains by brand/industry seed tokens. 
    If filtering removes too many results, return Groq output as-is.
    Only use fallback if BOTH seed is empty AND Groq returned nothing valid.
    """
    cleaned = [d.strip() for d in domains if isinstance(d, str) and d.strip()]
    if not cleaned:
        return _build_fallback_domains(brand_seed, industry_seed)

    # If we have a valid brand seed, filter by it
    seed_tokens = set(_tokenize_seed(brand_seed) + _tokenize_seed(industry_seed))
    
    # If no meaningful seed tokens, return Groq's output as-is
    # (Groq is smart enough to stay in the category with just industry hint)
    if not seed_tokens:
        logger.info(f"No seed tokens found, trusting Groq output as-is")
        return cleaned[:5]

    # Filter domains: each must contain at least one seed token
    filtered = [
        d for d in cleaned
        if any(token in d.lower() for token in seed_tokens)
    ]

    # If filtering removed everything, log and return Groq output anyway
    if not filtered:
        logger.warning(f"Seed filter removed all domains. Groq output: {cleaned}")
        logger.warning(f"Seed tokens: {seed_tokens}")
        # Return Groq output instead of fallback (Groq is better informed)
        return cleaned[:5]
    
    return filtered[:5]

# ---------------- Utility ----------------
def clean_text(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("utf-8")
    return text

# ---------------- NLTK Setup ----------------
nltk_packages = {
    "stopwords": "corpora/stopwords",
    "punkt": "tokenizers/punkt",
    "punkt_tab": "tokenizers/punkt_tab"
}
for package, resource in nltk_packages.items():
    try:
        nltk.data.find(resource)
    except LookupError:
        print(f"Downloading NLTK resource: {package}")
        try:
            nltk.download(package, quiet=True)
        except Exception as e:
            print(f"Warning: Could not download {package}: {e}")

# ---------------- Env + Logging ----------------
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SERPAPI_API_KEY = os.getenv('SERPAPI_API_KEY')
if not SERPAPI_API_KEY:
    raise ValueError("SERPAPI_API_KEY not set.")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY not set.")
groq_client = Groq(api_key=GROQ_API_KEY)

CACHE_DIR = "cache"
os.makedirs(CACHE_DIR, exist_ok=True)
JOB_STATUS_FILE = "job_status.json"

app = FastAPI(title="Keyword Extraction API", description="Extract competitor keywords with Groq+SerpAPI")

# ---------------- Models ----------------
class KeywordExtractionRequest(BaseModel):
    customer_statement: str
    max_results: Optional[int] = 5
    max_pages: Optional[int] = 1

class KeywordExtractionResponse(BaseModel):
    job_id: str
    status: str
    message: str
    results_file: Optional[str] = None
    competitors_processed: Optional[int] = None
    total_keywords: Optional[int] = None

job_status = {}

# ---------------- Job Status Helpers ----------------
def load_job_status():
    global job_status
    if os.path.exists(JOB_STATUS_FILE):
        try:
            with open(JOB_STATUS_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                for job_id, status in loaded.items():
                    if status.get("start_time"):
                        status["start_time"] = datetime.fromisoformat(status["start_time"])
                    if status.get("end_time"):
                        status["end_time"] = datetime.fromisoformat(status["end_time"])
                job_status.update(loaded)
        except Exception as e:
            logger.error(f"Failed to load job status: {e}")

def save_job_status():
    try:
        serializable = {}
        for job_id, status in job_status.items():
            serializable[job_id] = status.copy()
            if status.get("start_time"):
                serializable[job_id]["start_time"] = status["start_time"].isoformat()
            if status.get("end_time"):
                serializable[job_id]["end_time"] = status["end_time"].isoformat()
        with open(JOB_STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(serializable, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Failed to save job status: {e}")

load_job_status()

# ---------------- Groq Domain Normalizer ----------------
def extract_domains_with_groq(statement: str) -> List[str]:
    """Use Groq to identify the brand's industry and generate competitor search queries."""
    # Truncate very long crawled text to avoid token limits
    truncated = statement[:3000] if len(statement) > 3000 else statement
    brand_seed = _extract_seed_value(truncated, ["business", "brand", "brand name", "business name", "company", "company name", "product", "product name"])
    industry_seed = _extract_seed_value(truncated, ["industry", "niche", "category"])

    logger.info(f"[EXTRACT_DOMAINS] Extracted seeds from statement: brand_seed='{brand_seed}', industry_seed='{industry_seed}'")

    prompt = f"""
Analyze the following text from a company's website and identify:
1. What industry/niche this company operates in (e.g. bicycles, cosmetics, packaged water)
2. What specific products or services they offer
3. Identify the primary country or market region they operate in (e.g., India, US). If the text suggests they are based in a specific country (like India), make sure the competitors you find are local to that same country.
4. Generate search queries that would find their direct competitors (other brands/companies selling similar products in their specific market).

Website text: "{truncated}"

Return ONLY a JSON object with a "domains" key containing a list of 3-5 search queries to find real competitor brands.
For example, if the company is based in India, the queries MUST include "India" (e.g. "top bicycle brands in India", "best Indian cycle manufacturers").
Focus on the company's PRIMARY business. Do NOT include generic terms like "e-commerce", "software", or "online grocery" unless that IS their core business.

Primary brand/product seed (must stay in this same market): "{brand_seed or 'Not provided'}"
Industry seed (if provided): "{industry_seed or 'Not provided'}"
IMPORTANT: Every query must stay in the same category as the seed. If seed indicates helmets/cycling gear, do not output queries for water, food, software, or unrelated products.

Example for an Indian bicycle company: {{"domains": ["top bicycle brands India", "best cycling companies in India", "mountain bike manufacturers India"]}}
Example for a global cosmetics brand: {{"domains": ["top skincare brands", "best cosmetics companies", "beauty product brands"]}}
"""

    response, _used_model = groq_chat_with_failover(
        groq_client,
        messages=[{"role": "user", "content": prompt}],
        primary_model="llama-3.3-70b-versatile",
        logger=logger,
        response_format={"type": "json_object"},
    )

    try:
        parsed = json.loads(response.choices[0].message.content)
        domains = parsed.get("domains", []) if isinstance(parsed, dict) else parsed
        logger.info(f"[EXTRACT_DOMAINS] Groq output: {domains}")
        filtered_domains = _filter_domains_by_seed(domains, brand_seed, industry_seed)
        logger.info(f"[EXTRACT_DOMAINS] Groq extracted competitor search queries: {domains}")
        if filtered_domains != domains:
            logger.info(f"[EXTRACT_DOMAINS] Seed-filtered competitor queries: {filtered_domains}")
        return filtered_domains
    except Exception as e:
        logger.error(f"Failed to parse Groq response: {e}")
        fallback = _build_fallback_domains(brand_seed, industry_seed)
        logger.info(f"[EXTRACT_DOMAINS] Using fallback queries: {fallback}")
        return fallback

# ---------------- SerpAPI ----------------
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(Exception)
)
def get_serpapi_results(query: str, max_results: int = 5) -> List[dict]:
    """Fetch competitors from SerpAPI."""
    logger.info(f"Fetching SerpAPI results for query: {query}")
    try:
        params = {
            "q": query,
            "api_key": SERPAPI_API_KEY,
            "num": max_results,
            "engine": "google"
        }

        data = None
        try:
            # New serpapi client style
            res = serpapi.search(params)
            if hasattr(res, "as_dict"):
                data = res.as_dict()
            elif hasattr(res, "get_dict"):
                data = res.get_dict()
            elif isinstance(res, dict):
                data = res
        except Exception:
            # Fallback to legacy client(s)
            try:
                from serpapi import GoogleSearch  # sometimes available
            except Exception:
                from google_search_results import GoogleSearch  # legacy package
            search = GoogleSearch(params)
            if hasattr(search, "get_dict"):
                data = search.get_dict()
            else:
                data = search.get_json()

        if not isinstance(data, dict):
            data = {}
        results = data.get("organic_results", [])
        competitors = []
        for r in results:
            title = r.get("title", "Unknown")
            link = r.get("link", "")
            if link:
                competitors.append({"name": title, "url": link, "content": None})
        return competitors[:max_results]
    except Exception as e:
        logger.error(f"SerpAPI request failed: {e}")
        raise

# ---------------- Crawler ----------------
def crawl_url_with_service(url: str, max_pages: int = 1) -> str:
    crawler_url = "http://127.0.0.1:8000/crawl"
    req = {"start_url": url, "delay": 0.5, "timeout": 10, "max_pages": max_pages}
    try:
        resp = requests.post(crawler_url, json=req, timeout=30)
        resp.raise_for_status()
        job_id = resp.json().get("job_id")
        if not job_id: return ""
        status_url = f"http://127.0.0.1:8000/status/{job_id}"
        for _ in range(60):
            time.sleep(1)
            s = requests.get(status_url, timeout=10).json()
            if s.get("status") == "completed":
                json_file = s.get("json_file")
                if json_file and os.path.exists(json_file):
                    with open(json_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    combined = " ".join(
                        " ".join([h.get('text', '') for h in p.get('headers', [])]) + " " +
                        " ".join(p.get('paragraphs', [])) for p in data
                    )
                    return clean_text(combined)
            elif s.get("status") == "failed":
                return ""
        return ""
    except Exception as e:
        logger.error(f"Crawl failed for {url}: {e}")
        return ""

# ---------------- Keyword Extraction ----------------
def extract_keywords_from_text(text: str, max_keywords: int = 50) -> dict:
    if not text: return {"short_keywords": [], "long_tail_keywords": [], "keyword_count": {}}
    rake_short = Rake(min_length=1, max_length=2)
    rake_short.extract_keywords_from_text(text)
    short_phrases = rake_short.get_ranked_phrases()[:max_keywords]
    rake_long = Rake(min_length=3, max_length=4)
    rake_long.extract_keywords_from_text(text)
    long_phrases = rake_long.get_ranked_phrases()[:max_keywords]
    return {
        "short_keywords": short_phrases[:25],
        "long_tail_keywords": long_phrases[:25],
        "keyword_count": dict(Counter(re.findall(r"\b[a-zA-Z]{2,}\b", text.lower())))
    }

# ---------------- Background Task ----------------
async def extract_keywords_background(customer_statement: str, max_results: int, max_pages: int, job_id: str):
    try:
        job_status[job_id] = {"status": "running", "message": "In progress...", "start_time": datetime.now()}
        save_job_status()

        # Step 1: Normalize to domains
        domains = extract_domains_with_groq(customer_statement)
        if not domains:
            raise Exception("No domains extracted")

        all_competitor_data = []
        seen_urls = set()  # dedup by URL

        # Step 2: For each domain query, collect multiple competitors
        for d in domains:
            logger.info(f"Searching for competitors in domain: {d}")
            query = d  # Already a well-formed search query from Groq
            serp_results = get_serpapi_results(query, max_results=max_results)
            for comp in serp_results:
                url = comp.get("url", "")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                content = crawl_url_with_service(url, max_pages=max_pages)
                if content:
                    kws = extract_keywords_from_text(content, max_keywords=50)
                    all_competitor_data.append({
                        "domain": d,
                        "competitor_name": comp["name"],
                        "url": url,
                        "short_keywords": kws["short_keywords"],
                        "long_tail_keywords": kws["long_tail_keywords"],
                        "content_length": len(content)
                    })

                # Stop at 10 unique competitors
                if len(all_competitor_data) >= 10:
                    break

            if len(all_competitor_data) >= 10:
                break

        output_file = f"competitor_keywords_{job_id[:8]}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(all_competitor_data, f, indent=4, ensure_ascii=False)

        job_status[job_id] = {
            "status": "completed",
            "message": "Completed",
            "results_file": output_file,
            "competitors_processed": len(all_competitor_data),
            "total_keywords": sum(len(c["short_keywords"]) + len(c["long_tail_keywords"]) for c in all_competitor_data),
            "end_time": datetime.now()
        }
        save_job_status()
    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}")
        job_status[job_id] = {"status": "failed", "message": str(e), "end_time": datetime.now()}
        save_job_status()

# ---------------- API Endpoints ----------------
@app.post("/extract-keywords", response_model=KeywordExtractionResponse)
async def start_keyword_extraction(request: KeywordExtractionRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    job_status[job_id] = {"status": "started", "message": "Started", "start_time": datetime.now()}
    save_job_status()
    background_tasks.add_task(extract_keywords_background, request.customer_statement, request.max_results, request.max_pages, job_id)
    return KeywordExtractionResponse(job_id=job_id, status="started", message="Job started")

@app.get("/status/{job_id}", response_model=KeywordExtractionResponse)
async def get_status(job_id: str):
    if job_id not in job_status: raise HTTPException(status_code=404, detail="Job not found")
    s = job_status[job_id]
    return KeywordExtractionResponse(job_id=job_id, status=s["status"], message=s["message"], results_file=s.get("results_file"), competitors_processed=s.get("competitors_processed"), total_keywords=s.get("total_keywords"))

@app.get("/download/{job_id}")
async def download(job_id: str):
    if job_id not in job_status: raise HTTPException(status_code=404, detail="Job not found")
    s = job_status[job_id]
    if s["status"] != "completed": raise HTTPException(status_code=400, detail="Not completed yet")
    rf = s.get("results_file")
    if not rf or not os.path.exists(rf): raise HTTPException(status_code=404, detail="Results not found")
    return FileResponse(path=rf, filename=os.path.basename(rf), media_type="application/json")

@app.get("/jobs")
async def list_jobs():
    return {"jobs": [
        {"job_id": jid, "status": s["status"], "message": s["message"], "competitors_processed": s.get("competitors_processed"), "total_keywords": s.get("total_keywords"), "start_time": s.get("start_time").isoformat() if s.get("start_time") else None}
        for jid, s in job_status.items()
    ]}

@app.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    if job_id not in job_status: raise HTTPException(status_code=404, detail="Job not found")
    s = job_status[job_id]; rf = s.get("results_file")
    if rf and os.path.exists(rf): os.remove(rf)
    del job_status[job_id]; save_job_status()
    return {"message": f"Job {job_id} deleted"}

@app.get("/")
async def root():
    return {"message": "Keyword Extraction API with Groq domain normalization", "version": "2.0.0"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
