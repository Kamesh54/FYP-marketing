"""
Brand Agent Adapter — calls brand extraction logic directly (no HTTP).
"""
import logging
import asyncio
from typing import Dict, Any, Optional

logger = logging.getLogger("adapter.brand")


async def _extract_brand_async(brand_name: str, website_url: str) -> Dict[str, Any]:
    """Async brand extraction: crawl + LLM analysis."""
    from brand_agent import _crawl_site, _extract_brand_signals, _extract_visual_assets

    try:
        raw_content, visual = await asyncio.gather(
            _crawl_site(website_url),
            _extract_visual_assets(website_url),
        )
        brand_data = await _extract_brand_signals(brand_name, website_url, raw_content)

        _PLACEHOLDERS = {"not specified", "not provided", "unknown", "n/a", "", "none"}
        extracted_name = brand_data.pop("brand_name", "").strip()
        final_brand_name = (
            extracted_name
            if extracted_name and extracted_name.lower() not in _PLACEHOLDERS
            else brand_name
        )

        final_logo = visual.get("logo_url") or ""
        final_colors = visual.get("colors") or brand_data.get("colors", [])

        return {
            "brand_name": final_brand_name,
            "logo_url": final_logo,
            "colors": final_colors,
            "auto_extracted": True,
            "extracted_data": brand_data,
            "website_url": website_url,
        }
    except Exception as e:
        logger.error(f"Brand extraction failed for {website_url}: {e}")
        return {
            "brand_name": brand_name,
            "auto_extracted": False,
            "error": str(e),
        }


def extract_brand_from_url(brand_name: str, website_url: str) -> Dict[str, Any]:
    """
    Extract brand signals from a website URL.
    Returns dict with brand_name, logo_url, colors, extracted_data, etc.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                result = pool.submit(
                    asyncio.run,
                    _extract_brand_async(brand_name, website_url)
                ).result()
            return result
        else:
            return asyncio.run(_extract_brand_async(brand_name, website_url))
    except Exception as e:
        logger.error(f"Brand adapter failed: {e}")
        return {"brand_name": brand_name, "auto_extracted": False, "error": str(e)}


def extract_brand_signals(brand_name: str, website_url: str,
                          raw_content: str) -> Dict[str, Any]:
    """
    Extract brand signals from already-crawled content (no re-crawl needed).
    """
    from brand_agent import _extract_brand_signals

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                result = pool.submit(
                    asyncio.run,
                    _extract_brand_signals(brand_name, website_url, raw_content)
                ).result()
            return result
        else:
            return asyncio.run(
                _extract_brand_signals(brand_name, website_url, raw_content)
            )
    except Exception as e:
        logger.error(f"Brand signal extraction failed: {e}")
        return {"brand_name": brand_name, "error": str(e)}
