"""
Intelligent Router
Uses sentence-transformer embeddings for intent classification (no API tokens).
Groq LLM is retained only for generate_conversational_response (generative output).
"""
import os
import json
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
import numpy as np
from groq import Groq
from llm_client import llm_chat as _llm_chat
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# ── Embedding-based intent classifier (lazy-loaded on first use) ───────────────
# Defer loading until first request so that all processes started by start.bat
# do NOT all load the ~90 MB model simultaneously, which exhausts the Windows
# paging file (OSError: The paging file is too small).
os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")   # use cached model only
os.environ.setdefault("HF_DATASETS_OFFLINE", "1")
import contextlib, io as _io
logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)

_st_model           = None   # populated on first call to _ensure_model()
_intent_embeddings  = None   # populated on first call to _ensure_model()

# One representative sentence per intent
INTENT_EXAMPLES: Dict[str, str] = {
    "general_chat":        "hello what can you do help me understand this",
    "seo_analysis":        "analyse my website SEO audit check page optimisation",
    "blog_generation":     "write a blog post create an article generate content",
    "social_post":         "create a social media post generate instagram caption",
    "competitor_research": "analyse competitors keyword gap market research rival brands",
    "metrics_report":      "show analytics display performance metrics engagement stats",
    "brand_setup":         "my business is called set up brand profile add brand details",
    "daily_schedule":      "schedule posts automate content set up recurring tasks",
    "campaign_planning":   "plan a marketing campaign multi-day schedule launch event",
    "image_generation":    "generate a marketing image create visual content AI banner",
    "deep_research":       "deep research on a domain topic competitor landscape",
    "critic_review":       "review score content critique writing quality brand fit",
    "campaign_post":       "post content immediately to instagram publish now",
}

def _ensure_model() -> None:
    """Lazy-load the SentenceTransformer model on first use."""
    global _st_model, _intent_embeddings
    if _st_model is not None:
        return
    try:
        from sentence_transformers import SentenceTransformer
        with contextlib.redirect_stderr(_io.StringIO()):
            _st_model = SentenceTransformer("all-MiniLM-L6-v2", local_files_only=True)
    except Exception:
        # If the cached model is missing, allow a one-time download
        from sentence_transformers import SentenceTransformer
        with contextlib.redirect_stderr(_io.StringIO()):
            _st_model = SentenceTransformer("all-MiniLM-L6-v2")
    _intent_embeddings = {
        intent: _st_model.encode(example, normalize_embeddings=True)
        for intent, example in INTENT_EXAMPLES.items()
    }
    logger.info("Embedding-based intent classifier ready (%d intents)", len(_intent_embeddings))

# Intent categories
INTENTS = {
    "general_chat":       "General conversation, greetings, questions about capabilities",
    "seo_analysis":       "Analyze website SEO, check page optimization, audit existing site",
    "blog_generation":    "Create blog post, write article, generate content for website",
    "social_post":        "Create social media post, generate tweet/instagram/linkedin content",
    "competitor_research":"Analyze competitors, keyword gap analysis, market research",
    "metrics_report":     "Show analytics, display performance metrics, engagement stats",
    "brand_setup":        "Set up brand profile, add brand details, auto-extract from URL",
    "daily_schedule":     "Schedule posts, automate content, set up recurring tasks",
    "campaign_planning":  "Plan a marketing campaign, multi-day schedule, launch or event",
    # New intents
    "image_generation":   "Generate a marketing image or video, create visual content with AI",
    "deep_research":      "Deep research on a domain, topic, or competitor landscape",
    "critic_review":      "Review or score content, critique writing quality or brand fit",
    "campaign_post":      "Post content immediately to LinkedIn, X, Instagram, or Reddit",
}


@dataclass
class WorkflowPlan:
    """Describes which agents to run and what to pass between them."""
    intent: str
    agents: List[str] = field(default_factory=list)
    params: Dict[str, Any] = field(default_factory=dict)
    requires_hitl: bool = False
    requires_image: bool = False
    requires_critic: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent": self.intent,
            "agents": self.agents,
            "params": self.params,
            "requires_hitl": self.requires_hitl,
            "requires_image": self.requires_image,
            "requires_critic": self.requires_critic,
        }


# Map intents to canonical workflow plans
INTENT_WORKFLOW_MAP: Dict[str, WorkflowPlan] = {
    "blog_generation": WorkflowPlan(
        intent="blog_generation",
        agents=["keyword_extractor", "content_agent_blog", "critic_agent"],
        requires_critic=True,
    ),
    "social_post": WorkflowPlan(
        intent="social_post",
        agents=["content_agent_social", "critic_agent"],
        requires_critic=True,
    ),
    "image_generation": WorkflowPlan(
        intent="image_generation",
        agents=["image_agent"],
        requires_image=True, requires_critic=False,
    ),
    "deep_research": WorkflowPlan(
        intent="deep_research",
        agents=["research_agent"],
        requires_critic=False,
    ),
    "competitor_research": WorkflowPlan(
        intent="competitor_research",
        agents=["research_agent", "gap_analyzer"],
        requires_critic=False,
    ),
    "seo_analysis": WorkflowPlan(
        intent="seo_analysis",
        agents=["webcrawler", "seo_agent"],
        requires_critic=False,
    ),
    "brand_setup": WorkflowPlan(
        intent="brand_setup",
        agents=["brand_agent"],
        requires_critic=False,
    ),
    "campaign_planning": WorkflowPlan(
        intent="campaign_planning",
        agents=["keyword_extractor", "content_agent_blog", "critic_agent", "campaign_agent"],
        requires_critic=True,
    ),
    "campaign_post": WorkflowPlan(
        intent="campaign_post",
        agents=["campaign_agent"],
        requires_critic=False,
    ),
    "general_chat": WorkflowPlan(
        intent="general_chat", agents=[], requires_critic=False,
    ),
    "metrics_report": WorkflowPlan(
        intent="metrics_report", agents=[], requires_critic=False,
    ),
}

def build_routing_prompt(user_message: str, conversation_history: List[Dict[str, str]]) -> str:
    """Build prompt for intent classification."""
    # Summarize recent history (last 3 exchanges)
    history_context = ""
    if conversation_history:
        recent = conversation_history[-6:]  # Last 3 exchanges (user + assistant)
        history_context = "\n".join([
            f"{msg['role']}: {msg['content'][:100]}..." 
            for msg in recent
        ])
    
    prompt = f"""You are an intelligent routing assistant for a multi-agent SEO and content marketing system.

Your task is to classify the user's intent and extract relevant parameters.

Available intents and their descriptions:
{json.dumps(INTENTS, indent=2)}

Recent conversation context:
{history_context if history_context else "No previous context"}

Current user message: "{user_message}"

Analyze the user's message and determine:
1. The primary intent (choose from the list above)
2. Confidence level (0.0 to 1.0)
3. Any relevant parameters extracted from the message

CRITICAL ROUTING RULES:
- "brand_setup" is ONLY for when the user is PROVIDING new business information or explicitly asking to set up / update their profile (e.g. "my business is X", "set up my brand", "here is my website URL").
- Questions ASKING ABOUT their own stored business data (e.g. "what is my brand name?", "tell me my product name", "what is my industry?", "show my profile") must be routed as "general_chat" — NOT brand_setup.
- "competitor_research" is for requests like "who are my competitors", "analyse my competition", "find competitors in my industry".

Examples:
- "Check my website's SEO" → intent: "seo_analysis", confidence: 0.95, params: {{"requires_url": true}}
- "Write a blog about AI trends" → intent: "blog_generation", confidence: 0.9, params: {{"topic": "AI trends"}}
- "Plan a 1-week Christmas sale" → intent: "campaign_planning", confidence: 0.95, params: {{"duration": "7 days", "theme": "Christmas sale", "domain": "retail"}}
- "Create a 3-day launch campaign for my coffee shop" → intent: "campaign_planning", confidence: 0.95, params: {{"duration": "3 days", "theme": "launch", "domain": "coffee shop"}}
- "Post on Twitter about our new product" → intent: "social_post", confidence: 0.9, params: {{"platform": "twitter", "topic": "new product"}}
- "My business name is Kames Coffee" → intent: "brand_setup", confidence: 0.95, params: {{}}
- "What is my brand name?" → intent: "general_chat", confidence: 0.9, params: {{}}
- "Can you tell my product name" → intent: "general_chat", confidence: 0.9, params: {{}}
- "What industry am I in?" → intent: "general_chat", confidence: 0.9, params: {{}}
- "Who are my competitors?" → intent: "competitor_research", confidence: 0.95, params: {{}}

Return ONLY a JSON object with this structure:
{{
    "intent": "intent_name",
    "confidence": 0.95,
    "requires_url": false,
    "requires_brand_info": false,
    "extracted_params": {{
        "topic": "optional topic",
        "platform": "optional platform",
        "url": "optional url",
        "duration": "optional duration (e.g. '7 days')",
        "theme": "optional campaign theme",
        "domain": "optional business domain"
    }},
    "suggested_response": "Brief suggestion of what action to take"
}}
"""
    return prompt

async def route_user_query(user_message: str, conversation_history: List[Dict[str, str]] = None) -> Dict[str, Any]:
    """
    Route user query to appropriate intent using sentence-transformer cosine similarity.
    No API tokens consumed — runs fully on CPU in ~5 ms.
    """
    try:
        _ensure_model()  # lazy-load on first request
        user_emb = _st_model.encode(user_message, normalize_embeddings=True)

        # Cosine similarity = dot product when both vectors are L2-normalised
        scores = {
            intent: float(np.dot(user_emb, emb))
            for intent, emb in _intent_embeddings.items()
        }
        best_intent = max(scores, key=scores.get)
        confidence  = round(scores[best_intent], 4)

        # Hard rule: questions *about* a brand should go to general_chat, not brand_setup
        lower_msg = user_message.lower()
        question_words   = ("what", "who", "which", "tell me", "show me", "is my", "are my")
        brand_query_words = ("brand", "business", "product", "industry", "competitor")
        if (
            best_intent == "brand_setup"
            and any(q in lower_msg for q in question_words)
            and any(b in lower_msg for b in brand_query_words)
        ):
            best_intent = "general_chat"

        # Extract URL if present in message
        url = await extract_url_from_message(user_message)

        routing_result = {
            "intent": best_intent,
            "confidence": confidence,
            "requires_url": url is not None,
            "requires_brand_info": best_intent in ("blog_generation", "social_post", "campaign_planning"),
            "extracted_params": {"url": url} if url else {},
            "suggested_response": f"Routing to {best_intent.replace('_', ' ')} workflow."
        }

        logger.info(f"[embedding-router] intent={best_intent}  confidence={confidence:.3f}")
        return routing_result

    except Exception as e:
        logger.error(f"Embedding routing error (likely PyTorch DLL issue): {e}")
        logger.info("Falling back to LLM-based intent routing...")
        try:
            prompt = build_routing_prompt(user_message, conversation_history)
            response = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            result_str = response.choices[0].message.content
            import json
            llm_result = json.loads(result_str)
            logger.info(f"[LLM-router] intent={llm_result.get('intent')} confidence={llm_result.get('confidence', 0.8)}")
            
            # Ensure URL is extracted correctly
            url = await extract_url_from_message(user_message)
            if url:
                llm_result["requires_url"] = True
                if "extracted_params" not in llm_result:
                    llm_result["extracted_params"] = {}
                llm_result["extracted_params"]["url"] = url
                
            return {
                "intent": llm_result.get("intent", "general_chat"),
                "confidence": llm_result.get("confidence", 0.8),
                "requires_url": llm_result.get("requires_url", url is not None),
                "requires_brand_info": llm_result.get("requires_brand_info", False),
                "extracted_params": llm_result.get("extracted_params", {}),
                "suggested_response": llm_result.get("suggested_response", "")
            }
        except Exception as llm_route_err:
            logger.error(f"LLM routing fallback also failed: {llm_route_err}")
            return {
                "intent": "general_chat",
                "confidence": 0.5,
                "requires_url": False,
                "requires_brand_info": False,
                "extracted_params": {},
                "suggested_response": "I'll help you with that. Could you provide more details?"
            }

async def generate_conversational_response(
    user_message: str,
    conversation_history: List[Dict[str, str]] = None,
    brand_context: Optional[str] = None
) -> str:
    """
    Generate a conversational response for general_chat intent.
    Optionally accepts brand_context (pre-built summary of the user's business)
    so the LLM can answer brand-aware questions like "who are my competitors".
    """
    if not groq_client:
        return "I'm here to help you with SEO analysis, content generation, and social media marketing. What would you like to do?"
    
    try:
        # Build context from history
        messages = []
        if conversation_history:
            for msg in conversation_history[-10:]:  # Last 5 exchanges
                messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
        
        # Build system prompt — inject brand context when available
        brand_section = ""
        if brand_context:
            brand_section = f"""

=== USER'S BUSINESS CONTEXT ===
{brand_context}
================================
Use this context to answer business-specific questions directly without asking for details again.
If the user asks about competitors, mention their industry and location when analysing.
"""

        system_prompt = f"""You are a helpful AI assistant for an SEO and content marketing platform. You can:
- Analyze websites for SEO optimization
- Generate blog posts and articles
- Create social media content for Twitter/X or Instagram (one platform at a time — ask the user which one if they haven't specified)
- Publish posts directly to Twitter/X or Instagram via the Approve & Post button
- Provide competitor analysis
- Track social media metrics{brand_section}
IMPORTANT: This platform IS directly connected to Instagram and Twitter. Never say you cannot connect to social media accounts.
When users ask about posting to social media without specifying a platform, ask them: "Which platform would you like — Twitter/X or Instagram?"
When users ask about posting to Instagram or Twitter after choosing a platform, tell them to generate a social post first then click Approve & Post.

Be friendly, concise, and helpful. Guide users on what actions they can take.
Keep responses under 150 words unless explaining something complex."""
        
        messages.insert(0, {"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_message})
        
        response_text, model_used = _llm_chat(
            messages,
            temperature=0.7,
            max_tokens=400,
        )
        logger.debug("Conversational response via model: %s", model_used)
        return response_text
        
    except Exception as e:
        logger.error(f"Conversational response error: {e}")
        return "I'm here to help! I can analyze your website's SEO, generate blog content, create social media posts, and more. What would you like to do?"

def determine_required_agents(intent: str, extracted_params: Dict[str, Any]) -> List[str]:
    """
    Determine which agents need to be invoked for a given intent.
    Returns list of agent names in execution order.
    """
    plan = INTENT_WORKFLOW_MAP.get(intent)
    if plan:
        agents = list(plan.agents)
    else:
        agents = []

    # Add conditional agents based on extracted params
    if intent == "blog_generation" and extracted_params.get("has_website_url"):
        if "webcrawler" not in agents:
            agents.insert(0, "webcrawler")

    if intent == "social_post" and extracted_params.get("auto_post", False):
        if "campaign_agent" not in agents:
            agents.append("campaign_agent")

    return agents


def get_workflow_plan(intent: str, extracted_params: Dict[str, Any]) -> WorkflowPlan:
    """Return a WorkflowPlan for the given intent, with params merged in."""
    base: WorkflowPlan = INTENT_WORKFLOW_MAP.get(
        intent,
        WorkflowPlan(intent=intent, agents=[], requires_critic=False)
    )
    # Clone with params merged
    return WorkflowPlan(
        intent=base.intent,
        agents=list(base.agents),
        params={**base.params, **extracted_params},
        requires_hitl=base.requires_hitl,
        requires_image=base.requires_image,
        requires_critic=base.requires_critic,
    )


def estimate_workflow_time(agents: List[str]) -> float:
    """Estimate total workflow execution time in seconds."""
    agent_times = {
        "webcrawler": 15,
        "seo_agent": 30,
        "keyword_extractor": 20,
        "gap_analyzer": 25,
        "content_agent_blog": 40,
        "content_agent_social": 15,
        "image_generator": 50,
        "social_poster": 10,
        "research_agent": 45,
        "brand_agent": 20,
        "image_agent": 60,
        "critic_agent": 15,
        "campaign_agent": 10,
    }

    return sum(agent_times.get(agent, 10) for agent in agents)

async def extract_url_from_message(message: str) -> Optional[str]:
    """Extract URL from user message."""
    import re
    url_pattern = r'https?://(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&/=]*)'
    match = re.search(url_pattern, message)
    return match.group(0) if match else None

