import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import logging
import json
import os
import uuid
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List, Dict
import re
from collections import Counter
from datetime import datetime
from groq import Groq
from llm_client import llm_chat_json as _llm_json
from dotenv import load_dotenv
import time
try:
    from graph.dual_write_helper import sync_new_competitor
except Exception:
    def sync_new_competitor(*args, **kwargs):
        pass

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Groq API key
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY environment variable not set.")

# Job status file
JOB_STATUS_FILE = "gap_job_status.json"

# FastAPI app
app = FastAPI(title="Keyword Gap Analysis API", description="API for performing keyword gap analysis")

# Request and response models
class KeywordGapRequest(BaseModel):
    company_name: str
    company_url: Optional[str] = None  # Make this field optional
    product_description: str
    max_competitors: Optional[int] = 3
    max_pages_per_site: Optional[int] = 1

class KeywordGapResponse(BaseModel):
    job_id: str
    status: str
    message: str
    results_file: Optional[str] = None
    competitors_analyzed: Optional[int] = None
    total_keywords: Optional[int] = None

# In-memory job storage
job_status = {}

# Load job_status from file on startup
def load_job_status():
    global job_status
    if os.path.exists(JOB_STATUS_FILE):
        try:
            with open(JOB_STATUS_FILE, "r", encoding="utf-8") as f:
                loaded_status = json.load(f)
                for job_id, status in loaded_status.items():
                    if status.get("start_time"):
                        status["start_time"] = datetime.fromisoformat(status["start_time"])
                    if status.get("end_time"):
                        status["end_time"] = datetime.fromisoformat(status["end_time"])
                job_status.update(loaded_status)
            logger.info(f"Loaded job status from {JOB_STATUS_FILE}")
        except Exception as e:
            logger.error(f"Failed to load job status from {JOB_STATUS_FILE}: {e}")

# Save job_status to file
def save_job_status():
    try:
        serializable_status = {}
        for job_id, status in job_status.items():
            serializable_status[job_id] = status.copy()
            if status.get("start_time"):
                serializable_status[job_id]["start_time"] = status["start_time"].isoformat()
            if status.get("end_time"):
                serializable_status[job_id]["end_time"] = status["end_time"].isoformat()
        with open(JOB_STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(serializable_status, f, indent=4, ensure_ascii=False)
        logger.info(f"Saved job status to {JOB_STATUS_FILE}")
    except Exception as e:
        logger.error(f"Failed to save job status to {JOB_STATUS_FILE}: {e}")

# Load job status on startup
load_job_status()

class GapAnalyzer:
    def __init__(self):
        pass  # groq_client replaced by llm_client 3-model fallback chain

    def _extract_keywords_from_text(self, text: str, max_keywords: int = 50) -> Dict:
        """Lightweight keyword extraction from raw text without external services.
        - short_keywords: 1-2 word phrases
        - long_tail_keywords: 3-4 word phrases
        """
        if not text:
            return {"short_keywords": [], "long_tail_keywords": []}

        tokens = re.findall(r"[a-zA-Z]{2,}", text.lower())
        if not tokens:
            return {"short_keywords": [], "long_tail_keywords": []}

        def ngrams(words: List[str], n: int) -> List[str]:
            return [" ".join(words[i:i+n]) for i in range(len(words) - n + 1)]

        unigram_counts = Counter(tokens)
        bigram_counts = Counter(ngrams(tokens, 2))
        trigram_counts = Counter(ngrams(tokens, 3))
        fourgram_counts = Counter(ngrams(tokens, 4))

        # Score short keywords favoring bigrams slightly over unigrams
        short_scores = Counter()
        for term, count in unigram_counts.items():
            short_scores[term] += count
        for term, count in bigram_counts.items():
            short_scores[term] += count * 1.5

        long_scores = Counter()
        for term, count in trigram_counts.items():
            long_scores[term] += count
        for term, count in fourgram_counts.items():
            long_scores[term] += count * 1.2

        short_keywords = [t for t, _ in short_scores.most_common(max_keywords) if 1 <= len(t.split()) <= 2][:25]
        long_tail_keywords = [t for t, _ in long_scores.most_common(max_keywords) if 3 <= len(t.split()) <= 4][:25]

        return {"short_keywords": short_keywords, "long_tail_keywords": long_tail_keywords}

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=5, max=20),
        retry=retry_if_exception_type((requests.exceptions.RequestException, requests.exceptions.Timeout))
    )
    def crawl_company_website(self, company_url: str, max_pages: int = 1) -> str:
        """Crawl the company website using the web crawler service."""
        logger.info(f"Starting crawl for company website: {company_url}")
        crawler_url = "http://127.0.0.1:8000/crawl"
        crawl_request = {
            "start_url": company_url,
            "delay": 0.5,
            "timeout": 10,
            "max_pages": max_pages
        }
        try:
            response = requests.post(crawler_url, json=crawl_request, timeout=120)
            response.raise_for_status()
            job_data = response.json()
            job_id = job_data.get("job_id")
            if not job_id:
                logger.error(f"No job_id returned from crawler for {company_url}")
                raise Exception("No job_id returned from crawler")
            
            status_url = f"http://127.0.0.1:8000/status/{job_id}"
            max_attempts = 600  # 10 minutes
            for attempt in range(max_attempts):
                time.sleep(2)
                status_response = requests.get(status_url, timeout=10)
                status_response.raise_for_status()
                status_data = status_response.json()
                status = status_data.get("status")
                
                logger.info(f"Crawl attempt {attempt + 1}: Status = {status}")
                
                if status == "completed":
                    json_file = status_data.get("json_file")
                    if json_file and os.path.exists(json_file):
                        try:
                            with open(json_file, 'r', encoding='utf-8') as f:
                                crawl_data = json.load(f)
                                combined_content = ""
                                for page in crawl_data:
                                    headers = page.get('headers', [])
                                    header_text = " ".join([h.get('text', '') for h in headers])
                                    paragraphs = page.get('paragraphs', [])
                                    paragraph_text = " ".join(paragraphs)
                                    page_content = f"{header_text} {paragraph_text}".strip()
                                    combined_content += f" {page_content}"
                                combined_content = combined_content.strip()
                                logger.info(f"Extracted {len(combined_content)} characters from {company_url}")
                                return combined_content
                        except Exception as e:
                            logger.error(f"Error reading crawl results from {json_file}: {e}")
                            raise
                    else:
                        logger.error(f"No JSON file found: {json_file}")
                        raise Exception("No JSON file found")
                elif status == "failed":
                    message = status_data.get("message", "Unknown error")
                    logger.error(f"Crawl failed for {company_url}: {message}")
                    raise Exception(f"Crawl failed: {message}")
            
            logger.error(f"Crawl timeout for {company_url}")
            raise Exception("Crawl timeout")
        except requests.exceptions.RequestException as e:
            logger.error(f"Error crawling company website {company_url}: {e}")
            raise Exception(f"Failed to crawl company website: {str(e)}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=5, max=20),
        retry=retry_if_exception_type((requests.exceptions.RequestException, requests.exceptions.Timeout))
    )
    def extract_company_keywords(self, content: str) -> Dict:
        """Extract keywords directly from the company's crawled content (local processing)."""
        logger.info(f"Extracting company keywords from {len(content)} characters (local)")
        try:
            return self._extract_keywords_from_text(content, max_keywords=50)
        except Exception as e:
            logger.error(f"Local company keyword extraction failed: {e}")
            raise Exception(f"Failed to extract company keywords locally: {str(e)}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=5, max=20),
        retry=retry_if_exception_type((requests.exceptions.RequestException, requests.exceptions.Timeout))
    )
    def extract_competitor_keywords(self, company_name: str, max_competitors: int = 3) -> List[Dict]:
        """Extract competitor keywords using the keyword extraction service (updated schema)."""
        logger.info(f"Extracting competitor keywords for: {company_name}")
        keyword_service_url = "http://127.0.0.1:8001/extract-keywords"
        extraction_request = {
            "customer_statement": f"{company_name} competitors and alternatives in the same market.",
            "max_results": max_competitors,
            "max_pages": 1
        }
        try:
            response = requests.post(
                keyword_service_url,
                json=extraction_request,
                timeout=120  # Increased timeout to 120 seconds
            )
            response.raise_for_status()
            job_data = response.json()
            job_id = job_data.get("job_id")
            
            if not job_id:
                logger.error(f"No job_id returned from keyword extraction service for {company_name}")
                raise Exception("No job_id returned from keyword extraction service")
            
            # Poll for completion
            status_url = f"http://127.0.0.1:8001/status/{job_id}"
            max_attempts = 600  # 10 minutes
            for attempt in range(max_attempts):
                time.sleep(2)
                status_response = requests.get(status_url, timeout=10)
                status_response.raise_for_status()
                status_data = status_response.json()
                status = status_data.get("status")
                
                logger.info(f"Keyword extraction attempt {attempt + 1}: Status = {status}")
                
                if status == "completed":
                    results_file = status_data.get("results_file")
                    if results_file and os.path.exists(results_file):
                        try:
                            with open(results_file, 'r', encoding='utf-8') as f:
                                competitor_data = json.load(f)
                            logger.info(f"Extracted keywords for {len(competitor_data)} competitors")
                            return competitor_data
                        except Exception as e:
                            logger.error(f"Error reading keyword results from {results_file}: {e}")
                            raise
                    else:
                        logger.error(f"No results file found: {results_file}")
                        raise Exception("No results file found")
                elif status == "failed":
                    message = status_data.get("message", "Unknown error")
                    logger.error(f"Keyword extraction failed: {message}")
                    raise Exception(f"Keyword extraction failed: {message}")
            
            logger.error(f"Keyword extraction timeout for {company_name}")
            raise Exception("Keyword extraction timeout")
        except requests.exceptions.RequestException as e:
            logger.error(f"Error extracting competitor keywords: {e}")
            raise Exception(f"Failed to extract competitor keywords: {str(e)}")

    def perform_gap_analysis(self, company_keywords: Dict, competitor_data: List[Dict], product_description: str) -> Dict:
        """Perform keyword gap analysis using Groq API."""
        logger.info("Performing keyword gap analysis")
        try:
            company_short = company_keywords.get("short_keywords", [])
            company_long = company_keywords.get("long_tail_keywords", [])
            all_competitor_short = []
            all_competitor_long = []
            
            for comp in competitor_data:
                all_competitor_short.extend(comp.get("short_keywords", []))
                all_competitor_long.extend(comp.get("long_tail_keywords", []))
            
            # Remove duplicates
            all_competitor_short = list(set(all_competitor_short))
            all_competitor_long = list(set(all_competitor_long))
            
            # Find missing and unique keywords
            missing_short = [kw for kw in all_competitor_short if kw not in company_short]
            missing_long = [kw for kw in all_competitor_long if kw not in company_long]
            unique_short = [kw for kw in company_short if kw not in all_competitor_short]
            unique_long = [kw for kw in company_long if kw not in all_competitor_long]
            
            # Build simplified prompt (no JSON schema inline, rely on response_format)
            prompt = f"""
            You are an SEO expert performing a keyword gap analysis for a company.
            Company description: {product_description}

            Missing short keywords (competitors have, company doesn't): {', '.join(missing_short[:10])}
            Missing long-tail keywords: {', '.join(missing_long[:10])}
            Unique company short keywords: {', '.join(unique_short[:10])}
            Unique company long-tail keywords: {', '.join(unique_long[:10])}

            Return your analysis in JSON with the following keys:
            - organic_opportunities: contains "short" and "long_tail"
            - recommendations: list of recommendations
            - competitive_insights: list of insights
            """

            try:
                analysis_data, _model = _llm_json(
                    [{"role": "user", "content": prompt}]
                )
                logger.info("Gap analysis via model: %s", _model)
            except Exception as e:
                logger.error(f"LLM gap analysis failed: {e}")
                analysis_data = {
                    "organic_opportunities": {"short": [], "long_tail": []},
                    "recommendations": [],
                    "competitive_insights": []
                }

            return {
                "missing_keywords": {
                    "short": missing_short[:10],
                    "long_tail": missing_long[:10]
                },
                "unique_company_keywords": {
                    "short": unique_short[:10],
                    "long_tail": unique_long[:10]
                },
                "organic_opportunities": {
                    "short": analysis_data.get("organic_opportunities", {}).get("short", [])[:5],
                    "long_tail": analysis_data.get("organic_opportunities", {}).get("long_tail", [])[:5]
                },
                "recommendations": analysis_data.get("recommendations", [])[:5],
                "competitive_insights": analysis_data.get("competitive_insights", [])[:3]
            }
        except Exception as e:
            logger.error(f"Error performing gap analysis: {e}")
            raise Exception(f"Failed to perform gap analysis: {str(e)}")

async def perform_gap_analysis_background(
    company_name: str,
    company_url: Optional[str],  # Allow URL to be None
    product_description: str,
    max_competitors: int,
    max_pages: int,
    job_id: str
):
    """Background task to perform keyword gap analysis."""
    analyzer = GapAnalyzer()
    try:
        job_status[job_id] = {
            "status": "running",
            "message": "Keyword gap analysis in progress...",
            "start_time": datetime.now()
        }
        save_job_status()

        company_content = ""
        if company_url:
            # If a URL is provided, crawl the website as before
            logger.info(f"Job {job_id}: Crawling company website")
            company_content = analyzer.crawl_company_website(company_url, max_pages)
        else:
            # If no URL, use the product description as the source content
            logger.info(f"Job {job_id}: No company URL provided, using product description for keywords.")
            company_content = product_description
        
        # Extract company keywords
        logger.info(f"Job {job_id}: Extracting company keywords")
        company_keywords = analyzer.extract_company_keywords(company_content)
        
        # Extract competitor keywords
        logger.info(f"Job {job_id}: Extracting competitor keywords")
        competitor_data = analyzer.extract_competitor_keywords(company_name, max_competitors)
        
        # Perform gap analysis
        logger.info(f"Job {job_id}: Performing gap analysis")
        gap_analysis = analyzer.perform_gap_analysis(company_keywords, competitor_data, product_description)
        
        # Prepare results
        results = {
            "company_info": {
                "name": company_name,
                "url": company_url,
                "product_description": product_description
            },
            "company_keywords": {
                "short_keywords": company_keywords.get("short_keywords", []),
                "long_tail_keywords": company_keywords.get("long_tail_keywords", [])
            },
            "competitor_analysis": {
                "competitors_analyzed": len(competitor_data),
                "competitor_details": [
                    {
                        "name": comp["competitor_name"],
                        "url": comp["url"],
                        "short_keywords_count": len(comp.get("short_keywords", [])),
                        "long_tail_keywords_count": len(comp.get("long_tail_keywords", []))
                    }
                    for comp in competitor_data
                ]
            },
            "gap_analysis": gap_analysis,
            "summary": {
                "missing_short_keywords": len(gap_analysis["missing_keywords"]["short"]),
                "missing_long_tail_keywords": len(gap_analysis["missing_keywords"]["long_tail"]),
                "unique_company_keywords": len(gap_analysis["unique_company_keywords"]["short"]) + len(gap_analysis["unique_company_keywords"]["long_tail"]),
                "organic_opportunities": len(gap_analysis["organic_opportunities"]["short"]) + len(gap_analysis["organic_opportunities"]["long_tail"])
            }
        }
        
        output_file = f"gap_analysis_{job_id[:8]}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=4, ensure_ascii=False)
        
        # Best-effort: sync discovered competitors to the knowledge graph
        for comp in competitor_data:
            try:
                sync_new_competitor(comp)
            except Exception as e:
                logger.error(f"Failed to sync competitor to KG: {e}")
        
        job_status[job_id] = {
            "status": "completed",
            "message": "Keyword gap analysis completed successfully",
            "results_file": output_file,
            "competitors_analyzed": len(competitor_data),
            "total_keywords": sum(len(comp.get("short_keywords", [])) + len(comp.get("long_tail_keywords", [])) for comp in competitor_data),
            "end_time": datetime.now()
        }
        save_job_status()
        
        logger.info(f"Job {job_id}: Completed. Analyzed {len(competitor_data)} competitors")
    except Exception as e:
        logger.error(f"Job {job_id}: Failed with error: {e}")
        job_status[job_id] = {
            "status": "failed",
            "message": f"Keyword gap analysis failed: {str(e)}",
            "end_time": datetime.now()
        }
        save_job_status()

@app.post("/analyze-keyword-gap", response_model=KeywordGapResponse)
async def start_keyword_gap_analysis(request: KeywordGapRequest, background_tasks: BackgroundTasks):
    """Start a keyword gap analysis job."""
    logger.info(f"Received request: {request.model_dump_json()}")
    job_id = str(uuid.uuid4())
    job_status[job_id] = {
        "status": "started",
        "message": "Keyword gap analysis job started",
        "start_time": datetime.now()
    }
    save_job_status()
    background_tasks.add_task(
        perform_gap_analysis_background,
        request.company_name,
        request.company_url,
        request.product_description,
        request.max_competitors,
        request.max_pages_per_site,
        job_id
    )
    return KeywordGapResponse(
        job_id=job_id,
        status="started",
        message="Keyword gap analysis job started successfully"
    )

@app.get("/status/{job_id}", response_model=KeywordGapResponse)
async def get_keyword_gap_status(job_id: str):
    """Get the status of a keyword gap analysis job."""
    if job_id not in job_status:
        raise HTTPException(status_code=404, detail="Job not found")
    status = job_status[job_id]
    return KeywordGapResponse(
        job_id=job_id,
        status=status["status"],
        message=status["message"],
        results_file=status.get("results_file"),
        competitors_analyzed=status.get("competitors_analyzed"),
        total_keywords=status.get("total_keywords")
    )

@app.get("/download/json/{job_id}")
async def download_results(job_id: str):
    """Download the JSON results for a completed job."""
    if job_id not in job_status:
        raise HTTPException(status_code=404, detail="Job not found")
    status = job_status[job_id]
    if status["status"] != "completed":
        raise HTTPException(status_code=400, detail="Job not completed yet")
    results_file = status.get("results_file")
    if not results_file or not os.path.exists(results_file):
        raise HTTPException(status_code=404, detail="Results file not found")
    return FileResponse(
        path=results_file,
        filename=os.path.basename(results_file),
        media_type="application/json"
    )

@app.get("/jobs")
async def list_jobs():
    """List all keyword gap analysis jobs."""
    return {
        "jobs": [
            {
                "job_id": job_id,
                "status": status["status"],
                "message": status["message"],
                "competitors_analyzed": status.get("competitors_analyzed"),
                "total_keywords": status.get("total_keywords"),
                "start_time": status.get("start_time").isoformat() if status.get("start_time") else None
            }
            for job_id, status in job_status.items()
        ]
    }

@app.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    """Delete a job and its associated file."""
    if job_id not in job_status:
        raise HTTPException(status_code=404, detail="Job not found")
    status = job_status[job_id]
    results_file = status.get("results_file")
    if results_file and os.path.exists(results_file):
        try:
            os.remove(results_file)
            logger.info(f"Deleted file: {results_file}")
        except Exception as e:
            logger.error(f"Failed to delete file {results_file}: {e}")
    del job_status[job_id]
    save_job_status()
    return {"message": f"Job {job_id} deleted successfully"}

@app.get("/")
async def root():
    """API information."""
    return {
        "message": "Keyword Gap Analysis API",
        "version": "1.0.0",
        "endpoints": {
            "POST /analyze-keyword-gap": "Start a new keyword gap analysis job",
            "GET /status/{job_id}": "Get job status",
            "GET /download/{job_id}": "Download JSON results",
            "GET /jobs": "List all jobs",
            "DELETE /jobs/{job_id}": "Delete a job"
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8002)