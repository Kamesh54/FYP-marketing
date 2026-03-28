"""
Webcrawler Adapter — calls WebCrawler class directly (no HTTP).
"""
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("adapter.webcrawler")


def run_webcrawler(url: str, max_pages: int = 5, delay: float = 0.5,
                   timeout: int = 10) -> Dict[str, Any]:
    """
    Crawl a website and return extracted content.
    Returns dict with keys: content (str), pages_count (int), pages (list).
    """
    from webcrawler import WebCrawler

    try:
        crawler = WebCrawler(delay=delay, timeout=timeout)
        pages = crawler.crawl(url, max_pages=max_pages)

        # Combine all page content into a single string
        combined_content = ""
        for page in pages:
            headers = page.get("headers", [])
            header_text = " ".join([h.get("text", "") for h in headers])
            paragraphs = page.get("paragraphs", [])
            paragraph_text = " ".join(paragraphs)
            page_content = f"{header_text} {paragraph_text}".strip()
            combined_content += f" {page_content}"

        combined_content = combined_content.strip()
        logger.info(f"Crawled {len(pages)} pages from {url}, "
                    f"{len(combined_content)} chars extracted")

        return {
            "content": combined_content,
            "pages_count": len(pages),
            "pages": pages,
            "url": url,
        }
    except Exception as e:
        logger.error(f"Webcrawler adapter failed for {url}: {e}")
        return {
            "content": "",
            "pages_count": 0,
            "pages": [],
            "url": url,
            "error": str(e),
        }
