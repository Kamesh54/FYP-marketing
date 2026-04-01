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
# TRACE HELPER FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def emit_trace(state: MarketingState, event_type: str, node: str, data: Dict[str, Any]) -> None:
    """Helper to emit trace events without failing the node."""
    trace_id = state.get("trace_id")
    if not trace_id:
        return
    try:
        from trace_manager import get_trace_manager
        trace_mgr = get_trace_manager()
        trace_mgr.add_event(trace_id, event_type, node, data)
    except Exception as e:
        logger.warning(f"Failed to emit trace: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# ROUTER NODE
# ══════════════════════════════════════════════════════════════════════════════

async def router_node(state: MarketingState) -> Dict[str, Any]:
    """Classify user intent using the intelligent router.

    Uses the same logic as intelligent_router.py:
    1. Sentence-transformer embedding cosine similarity (primary, ~5ms, no tokens)
    2. Hard rules (e.g. brand questions → general_chat)
    3. LLM fallback via Groq if embeddings fail

    After classification, creates MABO state context and selects optimized
    workflow + content parameters (tone, template, quality_weight).
    """
    from intelligent_router import route_user_query, get_workflow_plan

    user_message = state.get("user_message", "")
    conversation_history = state.get("conversation_history", [])
    user_id = state.get("user_id", 0)

    # Emit trace event
    emit_trace(state, "start", "router", {"user_message": user_message[:100]})

    try:
        route_result = await route_user_query(user_message, conversation_history)

        intent = route_result.get("intent", "general_chat")
        confidence = route_result.get("confidence", 0.0)
        extracted_params = route_result.get("extracted_params", {})
        requires_url = route_result.get("requires_url", False)
        requires_brand_info = route_result.get("requires_brand_info", False)

        # Merge any platform from the request into extracted_params
        # (mirrors the orchestrator's platform-detection behaviour)
        if not extracted_params.get("platform"):
            lower_msg = user_message.lower()
            if any(k in lower_msg for k in ["twitter", " x ", "tweet", "x post", "on x"]):
                extracted_params["platform"] = "twitter"
            elif any(k in lower_msg for k in ["instagram", "insta", " ig ", "ig post", "on ig"]):
                extracted_params["platform"] = "instagram"

        # Build the workflow plan using the same mapping as intelligent_router
        workflow_plan = get_workflow_plan(intent, extracted_params)
        workflow_dict = workflow_plan.to_dict() if workflow_plan else {}

        # ── MABO Integration ─────────────────────────────────────────────
        # Create state context and get optimized workflows from MABO
        mabo_workflow_primary = None
        mabo_workflow_alt = None
        state_hash = "graph"
        mabo_content_params = None

        try:
            import mabo_agent
            from mabo_agent import extract_content_params

            mabo = mabo_agent.get_mabo_agent()

            # Determine content type for MABO
            content_type_map = {
                "blog_generation": "blog",
                "social_post": "social",
                "social_media_post": "social",
                "seo_analysis": "seo",
                "competitor_research": "research",
                "deep_research": "research",
            }
            content_type = content_type_map.get(intent, "blog")

            has_brand = state.get("brand_info") is not None
            has_website = bool(extracted_params.get("url"))

            state_context = mabo.create_state_from_context(
                intent=intent,
                user_id=user_id,
                content_type=content_type,
                has_brand_profile=has_brand,
                has_website=has_website,
            )
            state_hash = state_context["state_hash"]

            # Primary workflow from MABO's Bayesian Optimization
            mabo_workflow_primary = mabo.get_optimized_workflow_details(
                state_context, use_mabo=True
            )
            # Secondary workflow (baseline heuristic, different from primary)
            mabo_workflow_alt = mabo.get_alternative_workflow_details(
                intent,
                state_context,
                exclude_workflow=mabo_workflow_primary["workflow_name"],
            )

            # Extract 5D content params from MABO's action vector
            # (tone, template_style, quality_weight, content_length, budget)
            intent_to_mabo_agent = {
                "blog_generation": "content_agent_blog",
                "social_post": "content_agent_social",
                "social_media_post": "content_agent_social",
            }
            mabo_agent_name = intent_to_mabo_agent.get(intent)
            if mabo_agent_name and mabo_agent_name in mabo.local_optimizers:
                action_vector = mabo.local_optimizers[mabo_agent_name].select_action(
                    mabo.coordinator
                )
                mabo_content_params = extract_content_params(action_vector)
                logger.info(
                    f"MABO content params: qw={mabo_content_params['quality_weight']:.2f}, "
                    f"tone={mabo_content_params['tone']:.2f}, "
                    f"template={mabo_content_params['template_name']}"
                )

            logger.info(
                f"MABO: primary_wf={mabo_workflow_primary['workflow_name']}, "
                f"alt_wf={mabo_workflow_alt['workflow_name']}, "
                f"state_hash={state_hash}"
            )
        except Exception as mabo_err:
            logger.warning(f"MABO integration skipped: {mabo_err}")

        logger.info(f"Router: intent={intent}, confidence={confidence:.2f}, "
                    f"params={extracted_params}, requires_url={requires_url}")

        # Emit completion trace event
        emit_trace(state, "complete", "router", {
            "intent": intent,
            "confidence": confidence,
            "extracted_params": extracted_params,
            "workflow": mabo_workflow_primary["workflow_name"] if mabo_workflow_primary else None
        })

        return {
            "intent": intent,
            "confidence": confidence,
            "extracted_params": extracted_params,
            "workflow_plan": workflow_dict,
            "mabo_workflow_primary": mabo_workflow_primary,
            "mabo_workflow_alt": mabo_workflow_alt,
            "state_hash": state_hash,
            "mabo_content_params": mabo_content_params,
            "current_step": "router",
            "steps_completed": ["router"],
        }
    except Exception as e:
        logger.error(f"Router node failed: {e}")

        # Emit error trace event
        emit_trace(state, "error", "router", {"error": str(e)})

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

    emit_trace(state, "start", "chat", {
        "user_message": user_message[:100],
        "has_brand_context": bool(brand_context)
    })

    try:
        response = await generate_conversational_response(
            user_message, conversation_history, brand_context
        )

        emit_trace(state, "complete", "chat", {
            "response_length": len(response),
            "response_preview": response[:150]
        })

        return {
            "response_text": response,
            "current_step": "chat",
            "steps_completed": state.get("steps_completed", []) + ["chat"],
        }
    except Exception as e:
        logger.error(f"Chat node failed: {e}")
        emit_trace(state, "error", "chat", {"error": str(e)})
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

    emit_trace(state, "start", "keywords", {"message": "Extracting keywords from context"})

    user_message = state.get("user_message", "")
    brand_context = state.get("brand_context_summary", "")
    params = state.get("extracted_params", {})

    # Build query from available context
    query = params.get("topic", user_message)
    if brand_context:
        query = f"{query} {brand_context[:200]}"

    result = run_keyword_extraction(query, max_results=5, max_pages=1)
    competitors_count = result.get('competitors_processed', 0)
    logger.info(f"Keyword node: {competitors_count} competitors analyzed")

    emit_trace(state, "complete", "keywords", {
        "competitors_analyzed": competitors_count,
        "total_keywords": len(result.get("competitors", []))
    })

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

    emit_trace(state, "start", "gap_analysis", {"brand": company_name})

    result = run_gap_analysis(
        company_name=company_name,
        product_description=product_desc,
        company_url=company_url,
        max_competitors=3,
    )
    logger.info(f"Gap analysis node completed for {company_name}")

    # Extract gap count from the nested structure
    gap_analysis = result.get("gap_analysis", {})
    missing_kw = gap_analysis.get("missing_keywords", {})
    gap_count = len(missing_kw.get("short", [])) + len(missing_kw.get("long_tail", []))

    logger.info(f"Gap analysis found {gap_count} keyword gaps")

    emit_trace(state, "complete", "gap_analysis", {
        "brand": company_name,
        "gaps_found": gap_count,
        "missing_short": len(missing_kw.get("short", [])),
        "missing_long_tail": len(missing_kw.get("long_tail", []))
    })

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

    emit_trace(state, "start", "reddit_research", {"keywords": keywords[:3]})

    result = run_reddit_research(
        keywords=keywords[:8],
        brand_name=brand_name,
        max_subreddits=3,
    )
    is_available = result.get('available', False)
    logger.info(f"Reddit node: available={is_available}")

    emit_trace(state, "complete", "reddit_research", {
        "available": is_available,
        "insights_count": len(result.get("insights", []))
    })

    return {
        "reddit_insights": result,
        "current_step": "reddit_research",
        "steps_completed": state.get("steps_completed", []) + ["reddit_research"],
    }


# ══════════════════════════════════════════════════════════════════════════════
# BLOG CONTENT NODE
# ══════════════════════════════════════════════════════════════════════════════

def blog_content_node(state: MarketingState) -> Dict[str, Any]:
    """Generate two blog variants using MABO-optimized workflows.

    MABO integration (mirrors orchestrator lines 1600-1870):
    - Uses mabo_workflow_primary / mabo_workflow_alt for workflow names
    - Real cost estimation via cost_model.estimate_workflow_cost()
    - Registers executions with mabo.register_workflow_execution()
    - Saves vector memory via memory.write_campaign_entity()
    - Tags variants with proper workflow_name, state_hash, source
    """
    from agent_adapters import generate_blog
    import database as db
    import uuid
    import os

    params = state.get("extracted_params", {})
    brand_info = state.get("brand_info", {}) or {}
    session_id = state.get("session_id", "local_test")
    user_id = state.get("user_id", 0)
    state_hash = state.get("state_hash", "graph")

    # MABO workflow details from router_node
    mabo_primary = state.get("mabo_workflow_primary") or {}
    mabo_alt = state.get("mabo_workflow_alt") or {}
    mabo_content_params = state.get("mabo_content_params") or {}

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

    # ── MABO-influenced variant configs ──────────────────────────────────
    # Map MABO quality_weight to word count: higher quality → longer content
    mabo_qw = mabo_content_params.get("quality_weight", 0.5)
    mabo_tone_val = mabo_content_params.get("tone", 0.5)
    primary_length = int(1500 + mabo_qw * 1500)   # 1500-3000 words based on quality_weight
    alt_length = 1200  # baseline bumped up from 800 logic for more comprehensive posts

    # MABO tone aggressiveness maps to tone label
    if mabo_tone_val >= 0.65:
        mabo_tone_label = "bold"
    elif mabo_tone_val >= 0.35:
        mabo_tone_label = "informative"
    else:
        mabo_tone_label = "nurturing"

    variant_configs = [
        {
            "label": "Option A · Research-Driven Depth",
            "tone": mabo_tone_label,
            "length": primary_length,
            "workflow": mabo_primary,
            "source": "mabo",
        },
        {
            "label": "Option B · Fast Conversion Story",
            "tone": "persuasive",
            "length": alt_length,
            "workflow": mabo_alt,
            "source": "baseline",
        },
    ]

    response_options = []
    os.makedirs("previews", exist_ok=True)

    emit_trace(state, "start", "blog_generate", {
        "variants_to_generate": len(variant_configs),
        "brand": brand_info.get("brand_name", "")
    })

    # ── MABO agent instance (lazy, fault-tolerant) ───────────────────────
    mabo = None
    try:
        import mabo_agent
        mabo = mabo_agent.get_mabo_agent()
    except Exception as ma_err:
        logger.warning(f"MABO agent not available for blog tracking: {ma_err}")

    for variant in variant_configs:
        try:
            option_id = f"opt_{uuid.uuid4().hex[:8]}"

            # ── Cost estimation (real, not hardcoded) ─────────────────────
            wf_agents = variant["workflow"].get("agents", []) if variant["workflow"] else []
            try:
                if wf_agents:
                    workflow_cost_estimate = cost_model.estimate_workflow_cost(wf_agents)
                    logger.info(f"Cost estimate for {wf_agents}: {workflow_cost_estimate}")
                else:
                    workflow_cost_estimate = {"total_cost": 0.005, "total_time": 30}
                    logger.warning(f"No agents in workflow, using fallback cost")
            except Exception as cost_err:
                logger.error(f"Cost estimation failed: {cost_err}", exc_info=True)
                workflow_cost_estimate = {"total_cost": 0.005, "total_time": 30}

            variant_cost = workflow_cost_estimate.get("total_cost", 0.005)

            # Cap cost at reasonable maximum (prevent display bugs)
            if variant_cost > 1.0:
                logger.warning(f"Unusually high cost {variant_cost}, capping at $0.02")
                variant_cost = 0.02

            try:
                cost_display = cost_model.format_cost_display(variant_cost)
            except Exception:
                cost_display = f"${variant_cost:.4f}"

            result = generate_blog(
                business_details=business_details,
                keywords=consolidated_kw or None,
                gap_analysis=state.get("gap_analysis"),
                reddit_insights=state.get("reddit_insights"),
                brand_context=state.get("brand_context_summary", ""),
                tone=variant["tone"],
                word_count=variant["length"],
            )

            blog_html = result.get("html", "")

            content_id = str(uuid.uuid4())
            preview_path = f"previews/blog_{content_id}.html"
            with open(preview_path, "w", encoding="utf-8") as f:
                f.write(blog_html)

            wf_name = variant["workflow"].get("workflow_name", "LangGraph Agent Workflow") if variant["workflow"] else "LangGraph Agent Workflow"
            keywords_used = consolidated_kw.get("short_keywords", [])[:5] if consolidated_kw else []
            metadata = {
                "brand_name": brand_info.get("brand_name", "My Business"),
                "location": brand_info.get("location"),
                "industry": brand_info.get("industry"),
                "topic": state.get("user_message", ""),
                "keywords_used": keywords_used,
                "option_id": option_id,
                "selection_group": state_hash,
                "variant_label": variant["label"],
                "variant_tone": variant["tone"],
                "workflow_name": wf_name,
                "workflow_agents": wf_agents,
                "workflow_source": variant["source"],
            }

            db.save_generated_content(
                content_id=content_id,
                session_id=session_id,
                content_type="blog",
                content=blog_html,
                preview_url=f"/preview/blog/{content_id}",
                metadata=metadata,
            )

            db.save_workflow_variant(
                option_id=option_id,
                session_id=session_id,
                content_id=content_id,
                workflow_name=wf_name,
                state_hash=state_hash,
                label=variant["label"],
                metadata={
                    "tone": variant["tone"],
                    "length": variant["length"],
                    "cost_estimate": workflow_cost_estimate,
                },
            )

            # ── MABO execution registration ──────────────────────────────
            if mabo:
                try:
                    mabo.register_workflow_execution(
                        content_id=content_id,
                        state_hash=state_hash,
                        action=wf_name,
                        cost=variant_cost,
                        execution_time=workflow_cost_estimate.get("total_time", 30),
                    )
                except Exception as reg_err:
                    logger.warning(f"MABO registration failed: {reg_err}")

            # ── Vector memory persistence ────────────────────────────────
            try:
                import memory
                rich_text = f"{state.get('user_message', '')}. {business_details}"
                text_embedding = memory.get_text_embedding(rich_text)
                memory_entity = {
                    "campaign_id": content_id,
                    "text_vector": text_embedding.tolist() if hasattr(text_embedding, "tolist") else text_embedding,
                    "text_model": "all-MiniLM-L6-v2",
                    "context_metadata": metadata,
                    "alignment_score": 1.0,
                    "source": "langgraph",
                    "tags": [brand_info.get("industry", "General")],
                }
                memory.write_campaign_entity(memory_entity)
                logger.info(f"Memory saved for blog {content_id}")
            except Exception as mem_err:
                logger.warning(f"Failed to save vector memory: {mem_err}")

            response_options.append({
                "option_id": option_id,
                "label": variant["label"],
                "tone": variant["tone"].title(),
                "workflow_name": wf_name,
                "workflow_agents": wf_agents,
                "cost": variant_cost,
                "cost_display": cost_display,
                "preview_url": f"/preview/blog/{content_id}",
                "content_id": content_id,
                "content_type": "blog",
                "state_hash": state_hash,
            })

        except Exception as e:
            logger.error(f"Failed to generate explicit blog HTML variant: {e}", exc_info=True)

    final_response = "📍 **Two Draft Blogs Ready**\n\nI've produced two variations based on our data. Click `Preview` to read them!"
    if not response_options:
        final_response = "I'm sorry, an error occurred while generating the blogs."

    logger.info(f"Blog content node: generated {len(response_options)} HTML variants.")

    emit_trace(state, "complete", "blog_generate", {
        "variants_generated": len(response_options),
        "options": [opt["label"] for opt in response_options]
    })

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
    """Generate social media post variants using MABO-optimized workflows.

    MABO integration (mirrors orchestrator lines 2080-2340):
    - Uses mabo_workflow_primary / mabo_workflow_alt for variant workflow names
    - Real cost estimation via cost_model.estimate_workflow_cost()
    - Registers executions with mabo.register_workflow_execution()
    - Saves text + visual embeddings via memory.write_campaign_entity()
    - Tags variants with proper workflow_name, state_hash, source
    """
    from agent_adapters import generate_social, generate_image
    import database as db
    import uuid
    import os

    params = state.get("extracted_params", {})
    brand_info = state.get("brand_info", {}) or {}
    session_id = state.get("session_id", "local_test")
    user_id = state.get("user_id", 0)
    state_hash = state.get("state_hash", "graph")

    active_brand = state.get("active_brand", "default_brand")
    actual_brand_name = brand_info.get("brand_name") or active_brand

    # MABO workflow details from router_node
    mabo_primary = state.get("mabo_workflow_primary") or {}
    mabo_alt = state.get("mabo_workflow_alt") or {}

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
        {
            "label": "Option A · Authority Launch",
            "tone": "professional",
            "workflow": mabo_primary,
            "source": "mabo",
        },
        {
            "label": "Option B · Conversational Buzz",
            "tone": "playful",
            "workflow": mabo_alt,
            "source": "baseline",
        },
    ]

    response_options = []
    os.makedirs("previews", exist_ok=True)
    all_social_data = {}

    # ── MABO agent instance (lazy, fault-tolerant) ───────────────────────
    mabo = None
    try:
        import mabo_agent
        mabo = mabo_agent.get_mabo_agent()
    except Exception as ma_err:
        logger.warning(f"MABO agent not available for social tracking: {ma_err}")

    for variant in variant_configs:
        try:
            option_id = f"opt_{uuid.uuid4().hex[:8]}"

            # ── Cost estimation ──────────────────────────────────────────
            wf_agents = variant["workflow"].get("agents", []) if variant["workflow"] else []
            try:
                workflow_cost_estimate = cost_model.estimate_workflow_cost(wf_agents) if wf_agents else {}
            except Exception:
                workflow_cost_estimate = {"total_cost": 0.002, "total_time": 20}

            variant_cost = workflow_cost_estimate.get("total_cost", 0.002)
            try:
                cost_display = cost_model.format_cost_display(variant_cost)
            except Exception:
                cost_display = f"${variant_cost:.4f}"

            social_data = generate_social(
                keywords=consolidated_kw or None,
                gap_analysis=state.get("gap_analysis"),
                platforms=platforms,
                brand_name=actual_brand_name,
                brand_context=state.get("brand_context_summary", ""),
                tone=variant["tone"],
                topic=state.get("user_message", ""),
            )

            posts = social_data.get("posts", {})
            post_data = posts.get(chosen_platform, {})
            primary_copy = post_data.get("copy", "")

            image_prompts = social_data.get("image_prompts", [])
            image_prompt = image_prompts[0] if image_prompts else state.get("user_message", "marketing visual")

            # Generate image synchronously
            image_result = generate_image(
                prompt=image_prompt,
                brand_name=actual_brand_name,
            )

            image_path = image_result.get("local_path")
            fallback_url = image_result.get("url")

            if image_path:
                clean_path = image_path.replace("\\", "/")
                preview_url = f"/preview/image/{clean_path}"
            else:
                preview_url = fallback_url

            content_id = str(uuid.uuid4())
            wf_name = variant["workflow"].get("workflow_name", "LangGraph Agent Workflow") if variant["workflow"] else "LangGraph Agent Workflow"

            metadata = {
                "brand_name": actual_brand_name,
                "location": brand_info.get("location"),
                "industry": brand_info.get("industry"),
                "target_audience": brand_info.get("target_audience"),
                "unique_selling_points": brand_info.get("unique_selling_points", []),
                "platforms": platforms,
                "hashtags": post_data.get("hashtags", []),
                "keywords_used": consolidated_kw.get("short_keywords", [])[:5] if consolidated_kw else [],
                "image_prompt": image_prompt,
                "image_path": image_path,
                "option_id": option_id,
                "selection_group": state_hash,
                "variant_label": variant["label"],
                "variant_tone": variant["tone"],
                "workflow_name": wf_name,
                "workflow_agents": wf_agents,
                "workflow_source": variant["source"],
                "post_copy": {chosen_platform: primary_copy},
                "full_post_data": social_data,
            }

            post_preview = f"{chosen_platform.title()} Post:\n{primary_copy}"
            if post_data.get("hashtags"):
                post_preview += f"\n\nHashtags: {' '.join(post_data.get('hashtags'))}"

            db.save_generated_content(
                content_id=content_id,
                session_id=session_id,
                content_type="post",
                content=post_preview,
                preview_url=preview_url,
                metadata=metadata,
            )

            db.save_workflow_variant(
                option_id=option_id,
                session_id=session_id,
                content_id=content_id,
                workflow_name=wf_name,
                state_hash=state_hash,
                label=variant["label"],
                metadata={
                    "tone": variant["tone"],
                    "cost_estimate": workflow_cost_estimate,
                },
            )

            # ── MABO execution registration ──────────────────────────────
            if mabo:
                try:
                    mabo.register_workflow_execution(
                        content_id=content_id,
                        state_hash=state_hash,
                        action=wf_name,
                        cost=variant_cost,
                        execution_time=workflow_cost_estimate.get("total_time", 20),
                    )
                except Exception as reg_err:
                    logger.warning(f"MABO registration failed (social): {reg_err}")

            # ── Vector memory persistence (text + visual) ────────────────
            try:
                import memory
                rich_text = (
                    f"Social Post ({variant['tone']}): {state.get('user_message', '')}. "
                    f"{chosen_platform.title()}: {primary_copy}"
                )
                text_embedding = memory.get_text_embedding(rich_text)

                visual_embedding = None
                if image_path and os.path.exists(image_path):
                    try:
                        from tools import embedding
                        img_model = embedding.load_image_model()
                        visual_embedding = embedding.embed_image(img_model, image_path).tolist()
                    except Exception as ve:
                        logger.warning(f"Visual embedding failed: {ve}")

                memory_entity = {
                    "campaign_id": content_id,
                    "text_vector": text_embedding.tolist() if hasattr(text_embedding, "tolist") else text_embedding,
                    "visual_vector": visual_embedding,
                    "text_model": "all-MiniLM-L6-v2",
                    "visual_model": "clip-ViT-B-32" if visual_embedding else None,
                    "context_metadata": metadata,
                    "alignment_score": 1.0,
                    "source": "langgraph",
                    "tags": ["social", brand_info.get("industry", "General"), variant["tone"]],
                }
                memory.write_campaign_entity(memory_entity)
                logger.info(f"Social memory saved for {content_id}")
            except Exception as mem_err:
                logger.warning(f"Failed to save social vector memory: {mem_err}")

            response_options.append({
                "option_id": option_id,
                "label": variant["label"],
                "tone": variant["tone"].title(),
                "workflow_name": wf_name,
                "workflow_agents": wf_agents,
                "cost": variant_cost,
                "cost_display": cost_display,
                "content_id": content_id,
                "content_type": "post",
                "state_hash": state_hash,
                "platform": chosen_platform,
                "twitter_copy": primary_copy if chosen_platform == "twitter" else "",
                "instagram_copy": primary_copy if chosen_platform == "instagram" else "",
                "hashtags": post_data.get("hashtags", []),
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
    """Generate an image for social posts or blog with full brand visual identity."""
    from agent_adapters import generate_image
    import json

    emit_trace(state, "start", "image_gen", {"message": "Generating image with brand visual identity"})

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

    # ═══ ENRICH IMAGE PROMPT WITH BRAND VISUAL IDENTITY ═══
    brand_visual_context = []

    # Add brand colors
    colors = brand_info.get("colors", [])
    if colors and len(colors) > 0:
        if isinstance(colors, str):
            try:
                colors = json.loads(colors)
            except:
                colors = [colors]
        colors_str = ", ".join(colors) if isinstance(colors, list) else str(colors)
        brand_visual_context.append(f"using brand colors: {colors_str}")

    # Add fonts for visual style description
    fonts = brand_info.get("fonts", [])
    if fonts and len(fonts) > 0:
        if isinstance(fonts, str):
            try:
                fonts = json.loads(fonts)
            except:
                fonts = [fonts]
        fonts_str = ", ".join(fonts) if isinstance(fonts, list) else str(fonts)
        brand_visual_context.append(f"visual style inspired by fonts: {fonts_str}")

    # Add brand tone to influence mood
    tone = brand_info.get("tone") or brand_info.get("tone_preference")
    if tone:
        brand_visual_context.append(f"{tone} mood")

    # Add industry context
    industry = brand_info.get("industry")
    if industry and industry != "General":
        brand_visual_context.append(f"{industry} industry aesthetic")

    # Enhance the original prompt with brand visual identity
    if brand_visual_context:
        enhanced_prompt = f"{image_prompt}, {', '.join(brand_visual_context)}"
    else:
        enhanced_prompt = image_prompt

    logger.info(f"Image generation prompt enhanced with brand identity: {enhanced_prompt[:200]}")

    result = generate_image(
        prompt=enhanced_prompt,
        brand_name=brand_info.get("brand_name", ""),
        negative_prompt=params.get("negative_prompt", ""),
        duration=params.get("duration", None),
    )

    logger.info(f"Image node: url={result.get('url', 'None')}")

    emit_trace(state, "complete", "image_gen", {
        "image_url": result.get("url", ""),
        "original_prompt": image_prompt,
        "enhanced_prompt": enhanced_prompt,
        "brand_colors": colors if colors else None,
    })

    return {
        "image_result": result,
        "current_step": "image_generate",
        "steps_completed": state.get("steps_completed", []) + ["image_generate"],
    }


# ══════════════════════════════════════════════════════════════════════════════
# CRITIC NODE
# ══════════════════════════════════════════════════════════════════════════════

def critic_node(state: MarketingState) -> Dict[str, Any]:
    """Evaluate generated content quality and feed scores back to MABO.

    MABO feedback loop (mirrors orchestrator lines 1828-1847 / 2312-2331):
    - Calls mabo.update_engagement_metrics(content_id, critic_score)
    - Calls mabo.update_content_approval(content_id, approved=passed)
    - Calls prompt_optimizer.score_latest_for_agent() for prompt evolution
    """
    from agent_adapters import run_critique

    emit_trace(state, "start", "critic", {"message": "Evaluating content quality"})

    intent = state.get("intent", "blog_generation")
    user_id = state.get("user_id")
    brand_info = state.get("brand_info", {}) or {}

    # Determine which content to critique
    content_text = ""
    content_type = "blog"
    content_ids = []

    # Check for content in response_options
    if state.get("response_options"):
        response_opts = state["response_options"]

        if response_opts and isinstance(response_opts, list) and len(response_opts) > 0:
            first_opt = response_opts[0]

            # Collect content_ids first
            for opt in response_opts:
                if opt.get("content_id"):
                    content_ids.append(opt["content_id"])

            # For blog content, we need to load it from database since it's not in state
            if first_opt.get("content_type") == "blog":
                content_type = "blog"
                # Load content from database using first content_id
                if content_ids:
                    try:
                        import database as db
                        from database import get_db_connection
                        with get_db_connection() as conn:
                            cursor = conn.cursor()
                            cursor.execute('SELECT content FROM generated_content WHERE id = ?', (content_ids[0],))
                            row = cursor.fetchone()
                            if row:
                                content_text = row[0]
                                logger.info(f"Critic: Loaded {len(content_text)} chars from DB for content_id={content_ids[0]}")
                            else:
                                logger.warning(f"Critic: Content not found in DB for content_id={content_ids[0]}")
                    except Exception as db_err:
                        logger.error(f"Critic: Failed to load content from DB: {db_err}")

            # For social post content - concatenate copies
            elif first_opt.get("content_type") == "post" or first_opt.get("twitter_copy") or first_opt.get("instagram_copy"):
                content_type = "social_post"
                parts = []
                for opt in response_opts:
                    copy = opt.get("twitter_copy") or opt.get("instagram_copy") or ""
                    if copy:
                        parts.append(copy)
                content_text = "\n\n".join(parts)

    # If still no content, return early
    if not content_text:
        logger.warning(f"Critic node: No content found to evaluate. response_options={bool(state.get('response_options'))}, content_ids={content_ids}")
        emit_trace(state, "complete", "critic", {
            "skipped": True,
            "reason": "no_content"
        })
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
        content_id=content_ids[0] if content_ids else state.get("content_id"),
    )

    overall_score = result.get("overall_score", 0)
    passed = result.get("passed", False)

    logger.info(f"Critic node: overall={overall_score:.2f}, passed={passed}")

    # ── MABO Feedback Loop ───────────────────────────────────────────────
    # Feed critic score into MABO as an immediate quality reward
    try:
        import mabo_agent
        mabo = mabo_agent.get_mabo_agent()

        for cid in content_ids:
            if cid:
                mabo.update_engagement_metrics(cid, float(overall_score))
                if passed:
                    mabo.update_content_approval(cid, approved=True)
                logger.info(
                    f"[MABO] Critic reward fed: content={cid} "
                    f"overall={overall_score:.2f} passed={passed}"
                )
    except Exception as mabo_err:
        logger.warning(f"MABO feedback loop skipped: {mabo_err}")

    # ── Prompt Evolution Scoring ─────────────────────────────────────────
    try:
        from prompt_optimizer import score_latest_for_agent
        agent_name = "content_agent"
        score_latest_for_agent(agent_name, content_type, float(overall_score))
        logger.info(f"[PromptOptimizer] Scored {agent_name}/{content_type}: {overall_score:.2f}")
    except Exception as pe:
        logger.warning(f"[PromptOptimizer] Scoring skipped: {pe}")

    emit_trace(state, "complete", "critic", {
        "overall_score": overall_score,
        "passed": passed,
        "content_ids_evaluated": len(content_ids)
    })

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
