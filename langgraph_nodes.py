"""
LangGraph Nodes — each function is a node in the StateGraph.
Nodes read from / write to the shared MarketingState.
All agent calls go through the agent_adapters package (no HTTP).
"""
import logging
import json
from typing import Dict, Any
import database as db

try:
    import cost_model
except ImportError:
    pass

from langgraph_state import MarketingState

logger = logging.getLogger("langgraph.nodes")


# ══════════════════════════════════════════════════════════════════════════════
# ROUTER NODE
# ══════════════════════════════════════════════════════════════════════════════

async def router_node(state: MarketingState) -> Dict[str, Any]:
    """Classify user intent using the intelligent router."""
    from intelligent_router import route_user_query
    import asyncio

    user_message = state.get("user_message", "")
    conversation_history = state.get("conversation_history", [])

    try:
        route_result = await route_user_query(user_message, conversation_history)

        intent = route_result.get("intent", "general_chat")
        confidence = route_result.get("confidence", 0.0)
        params = route_result.get("params", {})
        workflow = route_result.get("workflow_plan", {})

        logger.info(f"Router: intent={intent}, confidence={confidence:.2f}")

        return {
            "intent": intent,
            "confidence": confidence,
            "extracted_params": params,
            "workflow_plan": workflow if isinstance(workflow, dict) else {},
            "current_step": "router",
            "steps_completed": ["router"],
        }
    except Exception as e:
        logger.error(f"Router node failed: {e}")
        return {
            "intent": "general_chat",
            "confidence": 0.0,
            "extracted_params": {},
            "errors": [f"Router error: {e}"],
            "current_step": "router",
            "steps_completed": ["router"],
        }


# ══════════════════════════════════════════════════════════════════════════════
# GENERAL CHAT NODE
# ══════════════════════════════════════════════════════════════════════════════

async def chat_node(state: MarketingState) -> Dict[str, Any]:
    """Handle general conversation with LLM."""
    from intelligent_router import generate_conversational_response

    user_message = state.get("user_message", "")
    conversation_history = state.get("conversation_history", [])
    brand_context = state.get("brand_context_summary", "")

    try:
        response = await generate_conversational_response(
            user_message, conversation_history, brand_context
        )
        return {
            "response_text": response,
            "current_step": "chat",
            "steps_completed": state.get("steps_completed", []) + ["chat"],
        }
    except Exception as e:
        logger.error(f"Chat node failed: {e}")
        return {
            "response_text": f"I apologize, I encountered an error: {str(e)}",
            "errors": state.get("errors", []) + [f"Chat error: {e}"],
            "current_step": "chat",
        }


# ══════════════════════════════════════════════════════════════════════════════
# BRAND SETUP NODE
# ══════════════════════════════════════════════════════════════════════════════

def brand_setup_node(state: MarketingState) -> Dict[str, Any]:
    """Extract brand information from URL or user input."""
    from agent_adapters import extract_brand_from_url
    from database import save_brand_profile

    params = state.get("extracted_params", {})
    user_message = state.get("user_message", "")
    user_id = state.get("user_id", 0)

    # Try to extract URL from params or message
    url = params.get("url", "")
    brand_name = params.get("brand_name", "")

    if not url:
        # Try to extract URL from user message
        import re
        url_match = re.search(r'https?://[^\s]+', user_message)
        if url_match:
            url = url_match.group()

    if url:
        result = extract_brand_from_url(brand_name or "Brand", url)
        final_name = result.get("brand_name", brand_name)

        # Save to database
        try:
            save_brand_profile(
                user_id=user_id,
                brand_name=final_name,
                description=result.get("extracted_data", {}).get("description", ""),
                target_audience=result.get("extracted_data", {}).get("target_audience", ""),
                tone=result.get("extracted_data", {}).get("tone", "professional"),
                colors=result.get("colors", []),
                website_url=url,
                logo_url=result.get("logo_url", ""),
                auto_extracted=True,
            )
        except Exception as db_err:
            logger.warning(f"Could not save brand profile: {db_err}")

        response = (
            f"✅ I've analyzed **{final_name}** and extracted the brand profile!\n\n"
            f"**Industry:** {result.get('extracted_data', {}).get('industry', 'N/A')}\n"
            f"**Tone:** {result.get('extracted_data', {}).get('tone', 'N/A')}\n"
            f"**Target Audience:** {result.get('extracted_data', {}).get('target_audience', 'N/A')}\n"
        )

        return {
            "brand_extraction_result": result,
            "brand_info": result.get("extracted_data", {}),
            "response_text": response,
            "current_step": "brand_setup",
            "steps_completed": state.get("steps_completed", []) + ["brand_setup"],
        }
    else:
        # Fallback to analyzing user_message directly when no URL is given
        from agent_adapters import extract_brand_signals
        result = extract_brand_signals(brand_name or "", "", user_message)
        
        extracted_name = result.get("brand_name", "").strip()
        _PLACEHOLDERS = {"not specified", "not provided", "unknown", "n/a", "", "none", "brand"}
        
        if extracted_name and extracted_name.lower() not in _PLACEHOLDERS:
            # We got a legitimate brand name natively from the text message!
            final_name = extracted_name
            import uuid
            
            try:
                save_brand_profile(
                    user_id=user_id,
                    brand_name=final_name,
                    description=result.get("description", ""),
                    target_audience=result.get("target_audience", ""),
                    tone=result.get("tone", "professional"),
                    colors=result.get("colors", []),
                    website_url="",
                    logo_url="",
                    auto_extracted=False,
                )
            except Exception as db_err:
                logger.warning(f"Could not save manual brand profile: {db_err}")

            response = (
                f"✅ I've established the brand profile for **{final_name}**!\n\n"
                f"**Industry:** {result.get('industry', 'N/A')}\n"
                f"**Tone:** {result.get('tone', 'N/A')}\n"
                f"**Target Audience:** {result.get('target_audience', 'N/A')}\n"
                f"*(No website URL provided; profile generated from your description)*"
            )

            return {
                "brand_extraction_result": {"extracted_data": result, "brand_name": final_name},
                "brand_info": result,
                "response_text": response,
                "current_step": "brand_setup",
                "steps_completed": state.get("steps_completed", []) + ["brand_setup"],
            }
        else:
            return {
                "response_text": "I'd love to set up your brand profile! Please share your website URL, or just tell me your brand name and industry, and I'll create your profile automatically.",
                "clarification_needed": True,
                "current_step": "brand_setup",
                "steps_completed": state.get("steps_completed", []) + ["brand_setup"],
            }


# ══════════════════════════════════════════════════════════════════════════════
# CRAWL NODE
# ══════════════════════════════════════════════════════════════════════════════

def crawl_node(state: MarketingState) -> Dict[str, Any]:
    """Crawl a website for SEO analysis or content extraction."""
    from agent_adapters import run_webcrawler

    params = state.get("extracted_params", {})
    url = params.get("url", "")

    if not url:
        user_msg = state.get("user_message", "")
        import re
        url_match = re.search(r'https?://[^\s]+', user_msg)
        if url_match:
            url = url_match.group()

    if not url:
        return {
            "crawled_data": {"content": "", "error": "No URL provided"},
            "errors": state.get("errors", []) + ["No URL for crawling"],
            "current_step": "crawl",
        }

    result = run_webcrawler(url, max_pages=5)
    logger.info(f"Crawl node: {result.get('pages_count', 0)} pages from {url}")

    return {
        "crawled_data": result,
        "current_step": "crawl",
        "steps_completed": state.get("steps_completed", []) + ["crawl"],
    }


# ══════════════════════════════════════════════════════════════════════════════
# KEYWORD EXTRACTION NODE
# ══════════════════════════════════════════════════════════════════════════════

def keyword_node(state: MarketingState) -> Dict[str, Any]:
    """Extract keywords from the business context or user message."""
    from agent_adapters import run_keyword_extraction

    user_message = state.get("user_message", "")
    brand_context = state.get("brand_context_summary", "")
    params = state.get("extracted_params", {})

    # Build query from available context
    query = params.get("topic", user_message)
    if brand_context:
        query = f"{query} {brand_context[:200]}"

    result = run_keyword_extraction(query, max_results=5, max_pages=1)
    logger.info(f"Keyword node: {result.get('competitors_processed', 0)} competitors analyzed")

    return {
        "keywords_data": result,
        "current_step": "keywords",
        "steps_completed": state.get("steps_completed", []) + ["keywords"],
    }


# ══════════════════════════════════════════════════════════════════════════════
# GAP ANALYSIS NODE
# ══════════════════════════════════════════════════════════════════════════════

def gap_analysis_node(state: MarketingState) -> Dict[str, Any]:
    """Perform keyword gap analysis."""
    from agent_adapters import run_gap_analysis

    brand_info = state.get("brand_info", {}) or {}
    params = state.get("extracted_params", {})

    company_name = brand_info.get("brand_name", params.get("brand_name", "Company"))
    product_desc = brand_info.get("description", state.get("user_message", ""))
    company_url = brand_info.get("website_url") or params.get("url")

    result = run_gap_analysis(
        company_name=company_name,
        product_description=product_desc,
        company_url=company_url,
        max_competitors=3,
    )
    logger.info(f"Gap analysis node completed for {company_name}")

    return {
        "gap_analysis": result,
        "current_step": "gap_analysis",
        "steps_completed": state.get("steps_completed", []) + ["gap_analysis"],
    }


# ══════════════════════════════════════════════════════════════════════════════
# REDDIT RESEARCH NODE
# ══════════════════════════════════════════════════════════════════════════════

def reddit_node(state: MarketingState) -> Dict[str, Any]:
    """Fetch Reddit community insights for content generation."""
    from agent_adapters import run_reddit_research

    keywords_data = state.get("keywords_data", {})
    brand_info = state.get("brand_info", {}) or {}
    params = state.get("extracted_params", {})

    # Build keyword list
    keywords = []
    if keywords_data:
        for comp in keywords_data.get("competitors", []):
            keywords.extend(comp.get("short_keywords", [])[:3])
    if not keywords:
        keywords = [state.get("user_message", "marketing")[:50]]

    brand_name = brand_info.get("brand_name", params.get("brand_name", ""))

    result = run_reddit_research(
        keywords=keywords[:8],
        brand_name=brand_name,
        max_subreddits=3,
    )
    logger.info(f"Reddit node: available={result.get('available', False)}")

    return {
        "reddit_insights": result,
        "current_step": "reddit_research",
        "steps_completed": state.get("steps_completed", []) + ["reddit_research"],
    }


# ══════════════════════════════════════════════════════════════════════════════
# BLOG CONTENT NODE
# ══════════════════════════════════════════════════════════════════════════════

def blog_content_node(state: MarketingState) -> Dict[str, Any]:
    """Generate two variants of a blog article using keywords, gap analysis, and reddit insights."""
    from agent_adapters import generate_blog
    import database as db
    import uuid
    import os

    params = state.get("extracted_params", {})
    brand_info = state.get("brand_info", {}) or {}
    session_id = state.get("session_id", "local_test")

    # Build business details from available context
    business_details = state.get("user_message", "")
    if brand_info:
        business_details += f"\nBrand: {brand_info.get('brand_name', '')}"
        business_details += f"\nIndustry: {brand_info.get('industry', '')}"
        business_details += f"\nTarget audience: {brand_info.get('target_audience', '')}"

    # Consolidate keywords
    kw_data = state.get("keywords_data", {})
    consolidated_kw = {}
    if kw_data:
        all_short = []
        all_long = []
        for comp in kw_data.get("competitors", []):
            all_short.extend(comp.get("short_keywords", []))
            all_long.extend(comp.get("long_tail_keywords", []))
        consolidated_kw = {
            "short_keywords": list(set(all_short))[:15],
            "long_tail_keywords": list(set(all_long))[:15],
        }

    variant_configs = [
        {"label": "Option A · Research-Driven Depth", "tone": "informative", "length": 1500},
        {"label": "Option B · Fast Conversion Story", "tone": "persuasive", "length": 800}
    ]

    response_options = []
    os.makedirs("previews", exist_ok=True)

    for variant in variant_configs:
        try:
            option_id = f"opt_{uuid.uuid4().hex[:8]}"
            
            result = generate_blog(
                business_details=business_details,
                keywords=consolidated_kw or None,
                gap_analysis=state.get("gap_analysis"),
                reddit_insights=state.get("reddit_insights"),
                brand_context=state.get("brand_context_summary", ""),
                tone=variant["tone"],
                word_count=variant["length"]
            )
            
            blog_html = result.get("html", "")
            
            content_id = str(uuid.uuid4())
            preview_path = f"previews/blog_{content_id}.html"
            with open(preview_path, "w", encoding="utf-8") as f:
                f.write(blog_html)
                
            keywords_used = consolidated_kw.get("short_keywords", [])[:5] if consolidated_kw else []
            metadata = {
                "brand_name": brand_info.get("brand_name", "My Business"),
                "location": brand_info.get("location"),
                "industry": brand_info.get("industry"),
                "topic": state.get("user_message", ""),
                "keywords_used": keywords_used,
                "option_id": option_id,
                "variant_label": variant["label"],
                "variant_tone": variant["tone"],
                "workflow_name": "LangGraph Agent Workflow",
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
                workflow_name="LangGraph Orchestrator",
                state_hash="graph",
                label=variant["label"],
                metadata={"estimated_cost": 0.005}
            )

            response_options.append({
                "option_id": option_id,
                "label": variant["label"],
                "tone": variant["tone"].title(),
                "workflow_name": "LangGraph Agent Workflow",
                "workflow_agents": ["WebCrawler", "KeywordExtractor", "GapAnalyzer", "ContentAgent", "CriticAgent"],
                "cost": 0.0050,
                "cost_display": "$0.0050",
                "preview_url": f"/preview/blog/{content_id}",
                "content_id": content_id,
                "content_type": "blog",
                "state_hash": "graph",
            })
            
        except Exception as e:
            logger.error(f"Failed to generate explicit blog HTML variant: {e}", exc_info=True)

    final_response = "📍 **Two Draft Blogs Ready**\n\nI've produced two variations based on our data. Click `Preview` to read them!"
    if not response_options:
        final_response = "I'm sorry, an error occurred while generating the blogs."

    logger.info(f"Blog content node: generated {len(response_options)} HTML variants.")

    return {
        "blog_result": {"variants": len(response_options)},
        "response_options": response_options,
        "response_text": final_response,
        "current_step": "blog_generate",
        "steps_completed": state.get("steps_completed", []) + ["blog_generate"],
    }


# ══════════════════════════════════════════════════════════════════════════════
# SOCIAL CONTENT NODE
# ══════════════════════════════════════════════════════════════════════════════

def social_content_node(state: MarketingState) -> Dict[str, Any]:
    """Generate social media posts with variants and UI previews."""
    from agent_adapters import generate_social, generate_image
    import database as db
    import uuid
    import os

    params = state.get("extracted_params", {})
    brand_info = state.get("brand_info", {}) or {}
    session_id = state.get("session_id", "local_test")
    
    active_brand = state.get("active_brand", "default_brand")
    actual_brand_name = brand_info.get("brand_name") or active_brand

    chosen_platform = params.get("platform", "twitter").lower()
    if chosen_platform == "x":
        chosen_platform = "twitter"

    platforms = [chosen_platform]

    kw_data = state.get("keywords_data", {})
    consolidated_kw = {}
    if kw_data:
        all_short = []
        for comp in kw_data.get("competitors", []):
            all_short.extend(comp.get("short_keywords", []))
        consolidated_kw = {"short_keywords": list(set(all_short))[:10]}

    variant_configs = [
        {"label": "Option A · Authority Launch", "tone": "professional"},
        {"label": "Option B · Conversational Buzz", "tone": "playful"}
    ]

    response_options = []
    os.makedirs("previews", exist_ok=True)
    
    all_social_data = {}

    for variant in variant_configs:
        try:
            option_id = f"opt_{uuid.uuid4().hex[:8]}"
            
            social_data = generate_social(
                keywords=consolidated_kw or None,
                gap_analysis=state.get("gap_analysis"),
                platforms=platforms,
                brand_name=actual_brand_name,
                brand_context=state.get("brand_context_summary", ""),
                tone=variant["tone"],
                topic=state.get("user_message", "")
            )
            
            posts = social_data.get('posts', {})
            post_data = posts.get(chosen_platform, {})
            primary_copy = post_data.get('copy', '')
            
            image_prompts = social_data.get('image_prompts', [])
            image_prompt = image_prompts[0] if image_prompts else state.get("user_message", "marketing visual")
            
            # Generate image synchronously
            image_result = generate_image(
                prompt=image_prompt,
                brand_name=actual_brand_name
            )
            
            image_path = image_result.get("local_path")
            fallback_url = image_result.get("url")
            
            if image_path:
                clean_path = image_path.replace("\\", "/")
                preview_url = f"/preview/image/{clean_path}"
            else:
                preview_url = fallback_url
            
            content_id = str(uuid.uuid4())
            metadata = {
                "brand_name": actual_brand_name,
                "platforms": platforms,
                "option_id": option_id,
                "variant_label": variant["label"],
                "variant_tone": variant["tone"],
                "workflow_name": "LangGraph Agent Workflow",
                "post_copy": {chosen_platform: primary_copy},
                "image_path": image_path
            }
            
            import json
            
            post_preview = f"{chosen_platform.title()} Post:\n{primary_copy}"
            if post_data.get('hashtags'):
                post_preview += f"\n\nHashtags: {' '.join(post_data.get('hashtags'))}"
            
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
                workflow_name="LangGraph Orchestrator",
                state_hash="graph",
                label=variant["label"],
                metadata={"estimated_cost": 0.002}
            )

            response_options.append({
                "option_id": option_id,
                "label": variant["label"],
                "tone": variant["tone"].title(),
                "workflow_name": "LangGraph Agent Workflow",
                "workflow_agents": ["KeywordExtractor", "GapAnalyzer", "ContentAgent"],
                "cost": 0.0020,
                "cost_display": "$0.0020",
                "content_id": content_id,
                "content_type": "post",
                "state_hash": "graph",
                "platform": chosen_platform,
                "twitter_copy": primary_copy if chosen_platform == "twitter" else "",
                "instagram_copy": primary_copy if chosen_platform == "instagram" else "",
                "hashtags": post_data.get('hashtags', []),
                "preview_url": preview_url,
                "preview_text": f"{variant['label']} ready for {chosen_platform.title()}.",
            })
            
            all_social_data[variant["label"]] = social_data
            
        except Exception as e:
            logger.error(f"Failed to generate explicit social post variant: {e}", exc_info=True)

    final_response = "📍 **Two Social Post Concepts Ready**\n\nI've produced two variations. Review the cards below!"
    if not response_options:
        final_response = "I'm sorry, an error occurred while generating the posts."

    return {
        "social_data": all_social_data,
        "response_options": response_options,
        "response_text": final_response,
        "current_step": "social_generate",
        "steps_completed": state.get("steps_completed", []) + ["social_generate"],
    }


# ══════════════════════════════════════════════════════════════════════════════
# IMAGE GENERATION NODE
# ══════════════════════════════════════════════════════════════════════════════

def image_node(state: MarketingState) -> Dict[str, Any]:
    """Generate an image for social posts or blog."""
    from agent_adapters import generate_image

    social_data = state.get("social_data", {})
    brand_info = state.get("brand_info", {}) or {}
    params = state.get("extracted_params", {})

    # Get image prompt from social data or params
    image_prompt = params.get("image_prompt", "")
    if not image_prompt and social_data:
        # Try to get from first platform's data
        for platform, pdata in social_data.items():
            if isinstance(pdata, dict) and "image_prompt" in pdata:
                image_prompt = pdata["image_prompt"]
                break

    if not image_prompt:
        image_prompt = state.get("user_message", "marketing visual")

    result = generate_image(
        prompt=image_prompt,
        brand_name=brand_info.get("brand_name", ""),
        negative_prompt=params.get("negative_prompt", ""),
        duration=params.get("duration", None),
    )

    logger.info(f"Image node: url={result.get('url', 'None')}")

    return {
        "image_result": result,
        "current_step": "image_generate",
        "steps_completed": state.get("steps_completed", []) + ["image_generate"],
    }


# ══════════════════════════════════════════════════════════════════════════════
# CRITIC NODE
# ══════════════════════════════════════════════════════════════════════════════

def critic_node(state: MarketingState) -> Dict[str, Any]:
    """Evaluate generated content quality."""
    from agent_adapters import run_critique

    intent = state.get("intent", "blog_generation")
    user_id = state.get("user_id")
    brand_info = state.get("brand_info", {}) or {}

    # Determine which content to critique
    content_text = ""
    content_type = "blog"

    if state.get("blog_result"):
        content_text = state["blog_result"].get("html", "")
        content_type = "blog"
    elif state.get("response_options") and state["response_options"][0].get("content_type") == "post":
        # Concatenate text from response options for critique
        parts = []
        for opt in state["response_options"]:
            copy = opt.get("twitter_copy") or opt.get("instagram_copy") or ""
            if copy:
                parts.append(copy)
        content_text = "\n\n".join(parts)
        content_type = "social_post"

    if not content_text:
        return {
            "critic_result": {"passed": True, "overall_score": 1.0, "critique_text": "No content to evaluate"},
            "current_step": "critic",
            "steps_completed": state.get("steps_completed", []) + ["critic"],
        }

    result = run_critique(
        content_text=content_text,
        original_intent=state.get("user_message", ""),
        content_type=content_type,
        brand_name=brand_info.get("brand_name", "") or state.get("active_brand", ""),
        user_id=user_id,
        session_id=state.get("session_id"),
        content_id=state.get("content_id"),
    )

    logger.info(f"Critic node: overall={result.get('overall_score', 0):.2f}, passed={result.get('passed', False)}")

    return {
        "critic_result": result,
        "current_step": "critic",
        "steps_completed": state.get("steps_completed", []) + ["critic"],
    }


# ══════════════════════════════════════════════════════════════════════════════
# SEO ANALYSIS NODE
# ══════════════════════════════════════════════════════════════════════════════

def seo_node(state: MarketingState) -> Dict[str, Any]:
    """Perform SEO analysis on a URL."""
    from agent_adapters import run_seo_analysis

    crawled_data = state.get("crawled_data", {})
    url = crawled_data.get("url", "")

    if not url:
        params = state.get("extracted_params", {})
        url = params.get("url", "")

    if not url:
        return {
            "seo_result": {"error": "No URL provided for SEO analysis"},
            "current_step": "seo_analysis",
        }

    result = run_seo_analysis(url)
    logger.info(f"SEO node: score={result.get('overall_score', 0)} for {url}")

    return {
        "seo_result": result,
        "current_step": "seo_analysis",
        "steps_completed": state.get("steps_completed", []) + ["seo_analysis"],
    }


# ══════════════════════════════════════════════════════════════════════════════
# CAMPAIGN NODE
# ══════════════════════════════════════════════════════════════════════════════

def campaign_node(state: MarketingState) -> Dict[str, Any]:
    """Handle campaign planning and scheduling."""
    params = state.get("extracted_params", {})
    user_message = state.get("user_message", "")
    brand_info = state.get("brand_info", {}) or {}
    intent = state.get("intent", "campaign_planning")

    try:
        from campaign_planner import CampaignPlannerAgent
        from agent_adapters.campaign_adapter import schedule_campaign, execute_campaign_post
        
        topic = params.get("topic", user_message)
        
        if intent == "campaign_post":
            # Immediate posting
            user_id = state.get("user_id")
            platform = params.get("platform", "twitter")
            content = params.get("content_text") or params.get("content_template") or topic
            ai_generate = params.get("ai_generate", True)
            
            import asyncio
            import concurrent.futures
            loop = asyncio.get_event_loop()
            
            if loop.is_running():
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    post_res = pool.submit(
                        asyncio.run,
                        execute_campaign_post(
                            user_id=user_id or 0,
                            platform=platform,
                            content=content,
                            content_id=None,
                            ai_generate=ai_generate,
                            brand_name=brand_info.get("brand_name")
                        )
                    ).result()
            else:
                post_res = asyncio.run(
                    execute_campaign_post(
                        user_id=user_id or 0,
                        platform=platform,
                        content=content,
                        content_id=None,
                        ai_generate=ai_generate,
                        brand_name=brand_info.get("brand_name")
                    )
                )

            return {
                "campaign_result": post_res,
                "response_text": f"Campaign post requested: {post_res.get('status', 'unknown')}",
                "current_step": "campaign",
                "steps_completed": state.get("steps_completed", []) + ["campaign"],
            }
        else:
            planner = CampaignPlannerAgent()
            duration = params.get("duration_days", 7)
            result = planner.generate_proposals(topic, duration_days=duration)

            return {
                "campaign_result": result,
                "response_text": json.dumps(result, indent=2) if isinstance(result, dict) else str(result),
                "current_step": "campaign",
                "steps_completed": state.get("steps_completed", []) + ["campaign"],
            }
    except Exception as e:
        logger.error(f"Campaign node failed: {e}")
        return {
            "campaign_result": {"error": str(e)},
            "response_text": f"Campaign planning encountered an error: {e}",
            "current_step": "campaign",
            "errors": state.get("errors", []) + [f"Campaign error: {e}"],
        }


# ══════════════════════════════════════════════════════════════════════════════
# RESEARCH NODE
# ══════════════════════════════════════════════════════════════════════════════

def research_node(state: MarketingState) -> Dict[str, Any]:
    """Perform deep competitor/topic research."""
    from agent_adapters import run_deep_research

    params = state.get("extracted_params", {})
    user_message = state.get("user_message", "")

    domain = params.get("domain", params.get("url", ""))
    if not domain:
        # Try to extract domain from message
        import re
        url_match = re.search(r'(?:https?://)?(?:www\.)?([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', user_message)
        if url_match:
            domain = url_match.group(1)

    if not domain:
        return {
            "response_text": "I need a domain or website URL to perform research. Could you share the website you'd like me to analyze?",
            "clarification_needed": True,
            "current_step": "research",
        }

    result = run_deep_research(domain=domain, depth_level="standard")
    logger.info(f"Research node completed for {domain}")

    return {
        "research_result": result,
        "current_step": "research",
        "steps_completed": state.get("steps_completed", []) + ["research"],
    }


# ══════════════════════════════════════════════════════════════════════════════
# RESPONSE BUILDER NODE
# ══════════════════════════════════════════════════════════════════════════════

def response_builder_node(state: MarketingState) -> Dict[str, Any]:
    """
    Build the final user-facing response from the accumulated agent outputs.
    This is the terminal node — all workflow paths converge here.
    """
    intent = state.get("intent", "general_chat")
    response = state.get("response_text", "")

    # If response_text was already set by a previous node, use it
    if response:
        return {"current_step": "response_builder"}

    # Build response based on intent and available data
    parts = []

    if intent == "seo_analysis":
        seo = state.get("seo_result", {})
        if seo and not seo.get("error"):
            score = seo.get("overall_score", 0)
            parts.append(f"## SEO Analysis Results\n\n**Overall Score: {score}/100**\n")
            cat_scores = seo.get("category_scores", {})
            for cat, sc in cat_scores.items():
                parts.append(f"- **{cat.replace('_', ' ').title()}**: {sc}/100")
            recs = seo.get("recommendations", [])
            if recs:
                parts.append("\n### Top Recommendations")
                for r in recs[:5]:
                    parts.append(f"- [{r.get('priority', '')}] {r.get('issue', '')}: {r.get('suggestion', '')}")
        else:
            parts.append(f"SEO analysis could not be completed: {seo.get('error', 'Unknown error')}")

    elif intent == "blog_generation":
        blog = state.get("blog_result", {})
        critic = state.get("critic_result", {})
        if blog and blog.get("html"):
            parts.append(f"## {blog.get('title', 'Blog Post')}\n")
            parts.append(blog.get("html", ""))
            if critic:
                parts.append(f"\n\n**Quality Score:** {critic.get('overall_score', 'N/A')}")
                if not critic.get("passed", True):
                    parts.append(f"\n**Suggestions:** {', '.join(critic.get('improvement_suggestions', []))}")
        else:
            parts.append("Blog generation could not be completed.")

    elif intent == "social_post":
        options = state.get("response_options", [])
        if options:
            platform_label = options[0].get("platform", "Platform").title().replace("Twitter", "Twitter/X")
            parts.append(f"📣 **{len(options)} {platform_label} Post Concept{'s' if len(options) > 1 else ''} Ready**\n\nReview the cards below — each shows the generated image and {platform_label} copy. Hit **Approve & Post** on the one you like, or tap 🔄 to regenerate the image.")
        else:
            parts.append("Social post generation could not be completed.")

    elif intent == "competitor_research":
        research = state.get("research_result", {})
        if research and not research.get("error"):
            parts.append("## Research Brief\n")
            parts.append(research.get("research_brief", "No brief generated"))
            keywords = research.get("top_keywords", [])
            if keywords:
                parts.append(f"\n**Top Keywords:** {', '.join(keywords[:10])}")
        else:
            parts.append(f"Research could not be completed: {research.get('error', 'Unknown error')}")

    elif intent == "campaign_planning":
        campaign = state.get("campaign_result", {})
        if campaign and not campaign.get("error"):
            parts.append("## Campaign Proposals\n")
            parts.append(json.dumps(campaign, indent=2))
        else:
            parts.append("Campaign planning could not be completed.")

    else:
        parts.append("I've processed your request. Please let me know if you need anything else!")

    final_response = "\n".join(parts)

    return {
        "response_text": final_response,
        "current_step": "response_builder",
        "steps_completed": state.get("steps_completed", []) + ["response_builder"],
    }
