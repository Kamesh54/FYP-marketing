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
    "punkt": "tokenizers/punkt"
}
for package, resource in nltk_packages.items():
    try:
        nltk.data.find(resource)
    except LookupError:
        print(f"Downloading NLTK resource: {package}")
        nltk.download(package, quiet=True)

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
    print("statement", statement)
    """Use Groq to identify product/market domains from customer statement."""
    prompt = f"""
    Analyze the customer statement: "{statement}".
    Identify the relevant product/market domains with location (like cloud kitchen, online grocery, etc).
    Return ONLY a JSON list of strings (domains).
    Example: ["CRM chennai", "ERP chennai"]
    """

    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )

    try:
        parsed = json.loads(response.choices[0].message.content)
        domains = parsed.get("domains", []) if isinstance(parsed, dict) else parsed
        logger.info(f"Groq extracted domains: {domains}")
        return domains
    except Exception as e:
        logger.error(f"Failed to parse Groq response: {e}")
        return []

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

        # Step 2: For each domain, search competitors
        for d in domains:
            logger.info(f"Searching for competitors in domain: {d}")
            query = f"{d} software site"
            serp_results = get_serpapi_results(query, max_results=max_results)
            if serp_results:
              comp = serp_results[0]  # Take only the first result
              content = crawl_url_with_service(comp["url"], max_pages=max_pages)
              if content:
                kws = extract_keywords_from_text(content, max_keywords=50)
                all_competitor_data.append({
            "domain": d,
            "competitor_name": comp["name"],
            "url": comp["url"],
            "short_keywords": kws["short_keywords"],
            "long_tail_keywords": kws["long_tail_keywords"],
            "content_length": len(content)
        })

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
