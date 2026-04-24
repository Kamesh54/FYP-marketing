"""
Cost Estimation Model
Estimates workflow costs based on agent usage, tokens, and API calls
"""
import logging
from math import ceil
from typing import List, Dict, Any
from database import get_db_connection

logger = logging.getLogger(__name__)
CREDITS_PER_USD = 1000
MIN_REQUEST_CREDITS = 1

# Cost model for each agent (default values, can be updated in database)
DEFAULT_AGENT_COSTS = {
    "webcrawler": {
        "time_cost_per_second": 0.0001,
        "avg_execution_time": 15,
        "token_cost_per_1k": 0.0,
        "avg_tokens": 0,
        "api_cost_per_call": 0.0
    },
    "seo_agent": {
        "time_cost_per_second": 0.0001,
        "avg_execution_time": 30,
        "token_cost_per_1k": 0.0,
        "avg_tokens": 0,
        "api_cost_per_call": 0.0
    },
    "keyword_extractor": {
        "time_cost_per_second": 0.0001,
        "avg_execution_time": 20,
        "token_cost_per_1k": 0.0006,  # Groq pricing
        "avg_tokens": 500,
        "api_cost_per_call": 0.0
    },
    "gap_analyzer": {
        "time_cost_per_second": 0.0001,
        "avg_execution_time": 25,
        "token_cost_per_1k": 0.0006,
        "avg_tokens": 800,
        "api_cost_per_call": 0.005  # SerpAPI cost
    },
    "content_agent_blog": {
        "time_cost_per_second": 0.0001,
        "avg_execution_time": 40,
        "token_cost_per_1k": 0.0006,
        "avg_tokens": 2000,
        "api_cost_per_call": 0.0
    },
    "content_agent_social": {
        "time_cost_per_second": 0.0001,
        "avg_execution_time": 15,
        "token_cost_per_1k": 0.0006,
        "avg_tokens": 500,
        "api_cost_per_call": 0.0
    },
    "image_generator": {
        "time_cost_per_second": 0.0001,
        "avg_execution_time": 50,
        "token_cost_per_1k": 0.0,
        "avg_tokens": 0,
        "api_cost_per_call": 0.05  # Runway cost per image
    },
    "social_poster": {
        "time_cost_per_second": 0.0001,
        "avg_execution_time": 10,
        "token_cost_per_1k": 0.0,
        "avg_tokens": 0,
        "api_cost_per_call": 0.0  # Free but rate-limited
    }
}

def get_agent_cost_params(agent_name: str) -> Dict[str, float]:
    """Get cost parameters for an agent from database or defaults."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT token_cost, time_cost, api_cost_per_call 
            FROM agent_costs 
            WHERE agent_name = ?
            """, (agent_name,))
            row = cursor.fetchone()
            
            if row:
                return {
                    "token_cost_per_1k": row[0],
                    "time_cost_per_second": row[1],
                    "api_cost_per_call": row[2]
                }
    except Exception as e:
        logger.warning(f"Could not fetch agent costs from DB: {e}")
    
    # Return defaults if not in database
    if agent_name in DEFAULT_AGENT_COSTS:
        return DEFAULT_AGENT_COSTS[agent_name]
    
    return {
        "time_cost_per_second": 0.0001,
        "avg_execution_time": 10,
        "token_cost_per_1k": 0.0,
        "avg_tokens": 0,
        "api_cost_per_call": 0.0
    }

def estimate_agent_cost(agent_name: str, estimated_tokens: int = None) -> Dict[str, Any]:
    """
    Estimate cost for a single agent execution.
    
    Returns:
        {
            "agent": str,
            "time_cost": float,
            "token_cost": float,
            "api_cost": float,
            "total_cost": float,
            "estimated_time": float (seconds)
        }
    """
    params = get_agent_cost_params(agent_name)
    defaults = DEFAULT_AGENT_COSTS.get(agent_name, {})
    
    # Time cost
    exec_time = defaults.get("avg_execution_time", 10)
    time_cost = exec_time * params.get("time_cost_per_second", 0.0001)
    
    # Token cost
    tokens = estimated_tokens or defaults.get("avg_tokens", 0)
    token_cost = (tokens / 1000) * params.get("token_cost_per_1k", 0.0)
    
    # API cost
    api_cost = params.get("api_cost_per_call", 0.0)
    
    total_cost = time_cost + token_cost + api_cost
    
    return {
        "agent": agent_name,
        "time_cost": round(time_cost, 6),
        "token_cost": round(token_cost, 6),
        "api_cost": round(api_cost, 6),
        "total_cost": round(total_cost, 6),
        "estimated_time": exec_time
    }

def estimate_workflow_cost(agents: List[str]) -> Dict[str, Any]:
    """
    Estimate total cost for a workflow consisting of multiple agents.
    
    Args:
        agents: List of agent names in execution order
    
    Returns:
        {
            "agents": List[Dict],  # Individual agent costs
            "total_cost": float,
            "total_time": float,
            "breakdown": {
                "time_cost": float,
                "token_cost": float,
                "api_cost": float
            }
        }
    """
    agent_costs = []
    total_time = 0
    total_time_cost = 0
    total_token_cost = 0
    total_api_cost = 0
    
    for agent in agents:
        cost_estimate = estimate_agent_cost(agent)
        agent_costs.append(cost_estimate)
        total_time += cost_estimate["estimated_time"]
        total_time_cost += cost_estimate["time_cost"]
        total_token_cost += cost_estimate["token_cost"]
        total_api_cost += cost_estimate["api_cost"]
    
    total_cost = total_time_cost + total_token_cost + total_api_cost
    
    return {
        "agents": agent_costs,
        "total_cost": round(total_cost, 4),
        "total_time": round(total_time, 1),
        "credits_estimate": usd_cost_to_credits(total_cost),
        "breakdown": {
            "time_cost": round(total_time_cost, 6),
            "token_cost": round(total_token_cost, 6),
            "api_cost": round(total_api_cost, 6)
        },
        "cost_usd": f"${round(total_cost, 4)}"
    }


def usd_cost_to_credits(cost: float) -> int:
    """Convert estimated USD cost to integer credits."""
    try:
        numeric_cost = float(cost)
    except (TypeError, ValueError):
        numeric_cost = 0.0
    return max(MIN_REQUEST_CREDITS, int(ceil(max(0.0, numeric_cost) * CREDITS_PER_USD)))


def format_credits_display(credits: int) -> str:
    """Format an integer credit amount for the UI."""
    credits = max(0, int(credits))
    return f"{credits} credit" if credits == 1 else f"{credits} credits"

def calculate_actual_cost(agent_name: str, execution_time: float, tokens_used: int = 0) -> float:
    """
    Calculate actual cost after agent execution.
    
    Args:
        agent_name: Name of the agent
        execution_time: Actual execution time in seconds
        tokens_used: Actual tokens consumed
    
    Returns:
        Actual cost in USD
    """
    params = get_agent_cost_params(agent_name)
    
    time_cost = execution_time * params.get("time_cost_per_second", 0.0001)
    token_cost = (tokens_used / 1000) * params.get("token_cost_per_1k", 0.0)
    api_cost = params.get("api_cost_per_call", 0.0)
    
    return time_cost + token_cost + api_cost

def format_cost_display(cost: float) -> str:
    """Format cost for user-friendly display."""
    if cost < 0.01:
        return f"${cost:.6f} (less than 1¢)"
    elif cost < 1.0:
        return f"${cost:.4f} (~{int(cost * 100)}¢)"
    else:
        return f"${cost:.2f}"


def format_cost_display(cost: float) -> str:
    """Format estimated cost as credits for user-facing display."""
    return format_credits_display(usd_cost_to_credits(cost))

def get_cost_tier(total_cost: float) -> str:
    """Categorize cost into tiers for UI display."""
    if total_cost < 0.01:
        return "minimal"  # Green
    elif total_cost < 0.05:
        return "low"      # Light green
    elif total_cost < 0.20:
        return "moderate" # Yellow
    else:
        return "high"     # Orange/Red

def should_show_cost_warning(total_cost: float, threshold: float = 0.20) -> bool:
    """Determine if cost warning should be shown to user."""
    return total_cost > threshold

def optimize_workflow_for_cost(agents: List[str], max_cost: float = 0.15) -> List[str]:
    """
    Optimize workflow to stay under maximum cost.
    Remove or replace expensive agents if needed.
    
    Returns optimized list of agents.
    """
    estimate = estimate_workflow_cost(agents)
    
    if estimate["total_cost"] <= max_cost:
        return agents  # No optimization needed
    
    # Optimization strategies
    optimized = agents.copy()
    
    # Strategy 1: Skip gap_analyzer if we already have keyword_extractor
    if "gap_analyzer" in optimized and "keyword_extractor" in optimized:
        if estimate["total_cost"] > max_cost:
            optimized.remove("gap_analyzer")
            logger.info("Removed gap_analyzer to optimize costs")
    
    # Strategy 2: Skip webcrawler if we're over budget and have other sources
    if "webcrawler" in optimized and len(optimized) > 2:
        new_estimate = estimate_workflow_cost(optimized)
        if new_estimate["total_cost"] > max_cost:
            optimized.remove("webcrawler")
            logger.info("Removed webcrawler to optimize costs")
    
    # Re-estimate
    final_estimate = estimate_workflow_cost(optimized)
    logger.info(f"Optimized workflow cost: ${final_estimate['total_cost']:.4f}")
    
    return optimized

