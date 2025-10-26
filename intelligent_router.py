"""
Intelligent LLM-Based Router
Uses Groq for intent classification and dynamic agent routing
"""
import os
import json
import logging
from typing import Dict, Any, List, Optional
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# Intent categories
INTENTS = {
    "general_chat": "General conversation, greetings, questions about capabilities",
    "seo_analysis": "Analyze website SEO, check page optimization, audit existing site",
    "blog_generation": "Create blog post, write article, generate content for website",
    "social_post": "Create social media post, generate tweet/instagram content",
    "competitor_research": "Analyze competitors, keyword gap analysis, market research",
    "metrics_report": "Show analytics, display performance metrics, engagement stats",
    "brand_setup": "Set up business profile, add contact info, configure brand details",
    "daily_schedule": "Schedule posts, automate content, set up recurring tasks"
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

Examples:
- "Check my website's SEO" → intent: "seo_analysis", confidence: 0.95, params: {{"requires_url": true}}
- "Write a blog about AI trends" → intent: "blog_generation", confidence: 0.9, params: {{"topic": "AI trends"}}
- "How are you doing?" → intent: "general_chat", confidence: 0.95, params: {{}}
- "Post on Twitter about our new product" → intent: "social_post", confidence: 0.9, params: {{"platform": "twitter", "topic": "new product"}}
- "Show me how my posts are performing" → intent: "metrics_report", confidence: 0.9, params: {{}}

Return ONLY a JSON object with this structure:
{{
    "intent": "intent_name",
    "confidence": 0.95,
    "requires_url": false,
    "requires_brand_info": false,
    "extracted_params": {{
        "topic": "optional topic",
        "platform": "optional platform",
        "url": "optional url"
    }},
    "suggested_response": "Brief suggestion of what action to take"
}}
"""
    return prompt

async def route_user_query(user_message: str, conversation_history: List[Dict[str, str]] = None) -> Dict[str, Any]:
    """
    Route user query to appropriate intent using Groq LLM.
    
    Returns:
        {
            "intent": str,
            "confidence": float,
            "requires_url": bool,
            "requires_brand_info": bool,
            "extracted_params": dict,
            "suggested_response": str
        }
    """
    if not groq_client:
        logger.error("Groq client not initialized")
        return {
            "intent": "general_chat",
            "confidence": 0.5,
            "requires_url": False,
            "requires_brand_info": False,
            "extracted_params": {},
            "suggested_response": "Unable to route request"
        }
    
    try:
        prompt = build_routing_prompt(user_message, conversation_history or [])
        
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=500
        )
        
        result = json.loads(response.choices[0].message.content)
        
        # Validate and normalize result
        intent = result.get("intent", "general_chat")
        if intent not in INTENTS:
            logger.warning(f"Unknown intent '{intent}', defaulting to general_chat")
            intent = "general_chat"
        
        routing_result = {
            "intent": intent,
            "confidence": float(result.get("confidence", 0.7)),
            "requires_url": result.get("requires_url", False),
            "requires_brand_info": result.get("requires_brand_info", False),
            "extracted_params": result.get("extracted_params", {}),
            "suggested_response": result.get("suggested_response", "")
        }
        
        logger.info(f"Routed to intent: {intent} (confidence: {routing_result['confidence']})")
        return routing_result
        
    except Exception as e:
        logger.error(f"Routing error: {e}")
        return {
            "intent": "general_chat",
            "confidence": 0.5,
            "requires_url": False,
            "requires_brand_info": False,
            "extracted_params": {},
            "suggested_response": "I'll help you with that. Could you provide more details?"
        }

async def generate_conversational_response(user_message: str, conversation_history: List[Dict[str, str]] = None) -> str:
    """
    Generate a conversational response for general_chat intent.
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
        
        # Add system prompt
        system_prompt = """You are a helpful AI assistant for an SEO and content marketing platform. You can:
- Analyze websites for SEO optimization
- Generate blog posts and articles
- Create social media content
- Provide competitor analysis
- Track social media metrics

Be friendly, concise, and helpful. Guide users on what actions they can take.
If they ask about capabilities, explain what you can do.
Keep responses under 100 words unless explaining something complex."""
        
        messages.insert(0, {"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_message})
        
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.7,
            max_tokens=300
        )
        
        return response.choices[0].message.content
        
    except Exception as e:
        logger.error(f"Conversational response error: {e}")
        return "I'm here to help! I can analyze your website's SEO, generate blog content, create social media posts, and more. What would you like to do?"

def determine_required_agents(intent: str, extracted_params: Dict[str, Any]) -> List[str]:
    """
    Determine which agents need to be invoked for a given intent.
    
    Returns list of agent names in execution order.
    """
    agent_workflows = {
        "seo_analysis": ["webcrawler", "seo_agent", "gap_analyzer"],
        "blog_generation": ["keyword_extractor", "gap_analyzer", "content_agent_blog"],
        "social_post": ["content_agent_social", "image_generator"],
        "competitor_research": ["gap_analyzer"],
        "metrics_report": [],  # Handled directly by metrics endpoints
        "brand_setup": [],  # Handled directly by brand extraction
        "daily_schedule": [],  # Handled by scheduler
        "general_chat": []  # No agents needed
    }
    
    agents = agent_workflows.get(intent, [])
    
    # Add conditional agents based on params
    if intent == "blog_generation" and extracted_params.get("has_website_url"):
        agents.insert(0, "webcrawler")
    
    if intent == "social_post" and extracted_params.get("auto_post", False):
        agents.append("social_poster")
    
    return agents

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
        "social_poster": 10
    }
    
    return sum(agent_times.get(agent, 10) for agent in agents)

async def extract_url_from_message(message: str) -> Optional[str]:
    """Extract URL from user message."""
    import re
    url_pattern = r'https?://(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&/=]*)'
    match = re.search(url_pattern, message)
    return match.group(0) if match else None

