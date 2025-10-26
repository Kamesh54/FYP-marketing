"""
Reinforcement Learning Agent
Q-Learning implementation for optimal agent routing and resource allocation
"""
import os
import json
import hashlib
import random
import logging
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime, timedelta
from database import (
    get_q_value, update_q_value, save_rl_experience,
    get_social_metrics, get_db_connection
)

logger = logging.getLogger(__name__)

# Q-Learning parameters
ALPHA = 0.1          # Learning rate
GAMMA = 0.9          # Discount factor
EPSILON = 0.1        # Exploration rate
MIN_EXPERIENCES = 10 # Minimum experiences before using Q-values

# Action space: Different agent workflow combinations
ACTIONS = {
    "full_workflow": ["webcrawler", "seo_agent", "keyword_extractor", "gap_analyzer", "content_agent_blog"],
    "quick_blog": ["keyword_extractor", "content_agent_blog"],
    "comprehensive_blog": ["webcrawler", "keyword_extractor", "gap_analyzer", "content_agent_blog"],
    "social_basic": ["content_agent_social", "image_generator"],
    "social_full": ["keyword_extractor", "content_agent_social", "image_generator", "social_poster"],
    "seo_only": ["webcrawler", "seo_agent"],
    "research_only": ["gap_analyzer"],
    "content_only": ["content_agent_blog"]
}

class State:
    """
    Represents the current state for RL decision making.
    """
    def __init__(
        self,
        intent: str,
        user_engagement_avg: float = 0.0,
        time_of_day: int = 12,
        day_of_week: int = 3,
        content_type: str = "blog",
        has_brand_profile: bool = False,
        has_website: bool = False,
        previous_cost_ratio: float = 1.0
    ):
        self.intent = intent
        self.user_engagement_avg = user_engagement_avg  # Historical engagement rate (0-100)
        self.time_of_day = time_of_day  # Hour (0-23)
        self.day_of_week = day_of_week  # Day (0-6, Monday=0)
        self.content_type = content_type  # "blog", "social", "seo"
        self.has_brand_profile = has_brand_profile
        self.has_website = has_website
        self.previous_cost_ratio = previous_cost_ratio  # cost vs reward from past actions
    
    def to_vector(self) -> List[float]:
        """Convert state to numerical vector for hashing."""
        return [
            hash(self.intent) % 100 / 100.0,
            self.user_engagement_avg / 100.0,
            self.time_of_day / 24.0,
            self.day_of_week / 7.0,
            hash(self.content_type) % 100 / 100.0,
            float(self.has_brand_profile),
            float(self.has_website),
            min(self.previous_cost_ratio, 2.0) / 2.0  # Normalize to 0-1
        ]
    
    def to_hash(self) -> str:
        """Create hash of state for Q-table lookup."""
        vector_str = ",".join([f"{v:.3f}" for v in self.to_vector()])
        return hashlib.md5(vector_str.encode()).hexdigest()[:16]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "intent": self.intent,
            "user_engagement_avg": self.user_engagement_avg,
            "time_of_day": self.time_of_day,
            "day_of_week": self.day_of_week,
            "content_type": self.content_type,
            "has_brand_profile": self.has_brand_profile,
            "has_website": self.has_website,
            "previous_cost_ratio": self.previous_cost_ratio
        }

def calculate_reward(
    engagement_rate: float,
    cost_usd: float,
    execution_time_minutes: float,
    content_approved: bool = True
) -> float:
    """
    Calculate reward based on outcomes.
    
    Reward formula:
    reward = (engagement_rate * 100) - (cost_usd * 10) + (time_saved_minutes * 0.5) + approval_bonus
    
    Args:
        engagement_rate: Social media engagement rate (0-1)
        cost_usd: Cost of workflow in USD
        execution_time_minutes: Time taken in minutes
        content_approved: Whether user approved the content
    
    Returns:
        Reward value (can be positive or negative)
    """
    # Engagement component (0-100 points)
    engagement_reward = engagement_rate * 100
    
    # Cost penalty (higher cost = lower reward)
    cost_penalty = cost_usd * 10
    
    # Time bonus (faster = better, but capped)
    time_saved = max(0, 5 - execution_time_minutes)  # Assume 5 min baseline
    time_bonus = time_saved * 0.5
    
    # Approval bonus
    approval_bonus = 10 if content_approved else -5
    
    reward = engagement_reward - cost_penalty + time_bonus + approval_bonus
    
    return reward

def select_action(state: State, exploration: bool = True) -> str:
    """
    Select action using epsilon-greedy policy.
    
    Args:
        state: Current state
        exploration: Whether to allow exploration (epsilon-greedy)
    
    Returns:
        Action name (key from ACTIONS dict)
    """
    state_hash = state.to_hash()
    
    # Exploration: random action
    if exploration and random.random() < EPSILON:
        action = random.choice(list(ACTIONS.keys()))
        logger.info(f"Exploring: selected random action '{action}'")
        return action
    
    # Exploitation: choose best known action
    q_values = {}
    for action in ACTIONS.keys():
        q_values[action] = get_q_value(state_hash, action)
    
    # If all Q-values are 0 (no experience), use heuristics
    if all(v == 0 for v in q_values.values()):
        action = select_action_heuristic(state)
        logger.info(f"No Q-values found, using heuristic: '{action}'")
        return action
    
    # Select action with highest Q-value
    best_action = max(q_values, key=q_values.get)
    logger.info(f"Exploiting: selected best action '{best_action}' (Q={q_values[best_action]:.3f})")
    return best_action

def select_action_heuristic(state: State) -> str:
    """
    Heuristic-based action selection when no Q-values exist.
    Uses domain knowledge about what works well.
    """
    # For SEO analysis
    if state.intent == "seo_analysis":
        return "seo_only"
    
    # For blog generation
    if state.intent == "blog_generation":
        if state.has_website:
            return "comprehensive_blog"
        elif state.user_engagement_avg > 50:  # High engagement users get full workflow
            return "full_workflow"
        else:
            return "quick_blog"
    
    # For social posts
    if state.intent == "social_post":
        if state.user_engagement_avg > 60:
            return "social_full"
        else:
            return "social_basic"
    
    # For competitor research
    if state.intent == "competitor_research":
        return "research_only"
    
    # Default: quick workflow
    return "quick_blog"

def update_q_table(state: State, action: str, reward: float, next_state: Optional[State] = None):
    """
    Update Q-value using Q-learning update rule.
    
    Q(s,a) = Q(s,a) + α * (reward + γ * max(Q(s',a')) - Q(s,a))
    """
    state_hash = state.to_hash()
    current_q = get_q_value(state_hash, action)
    
    # If there's a next state, consider future rewards
    if next_state:
        next_state_hash = next_state.to_hash()
        next_q_values = [get_q_value(next_state_hash, a) for a in ACTIONS.keys()]
        max_next_q = max(next_q_values) if next_q_values else 0
    else:
        max_next_q = 0
    
    # Q-learning update
    new_q = current_q + ALPHA * (reward + GAMMA * max_next_q - current_q)
    
    # Update in database
    update_q_value(state_hash, action, new_q)
    logger.info(f"Updated Q({state_hash[:8]}, {action}): {current_q:.3f} → {new_q:.3f} (reward: {reward:.2f})")

def get_user_engagement_average(user_id: int, days: int = 30) -> float:
    """Get user's average engagement rate from historical metrics."""
    try:
        metrics = get_social_metrics(user_id=user_id, days=days)
        if not metrics:
            return 0.0
        
        # Calculate average engagement rate
        total_engagement = sum(m['engagement_rate'] for m in metrics)
        avg_engagement = total_engagement / len(metrics)
        return avg_engagement
    except Exception as e:
        logger.error(f"Error calculating engagement average: {e}")
        return 0.0

def create_state_from_context(
    intent: str,
    user_id: int,
    content_type: str = "blog",
    has_brand_profile: bool = False,
    has_website: bool = False
) -> State:
    """
    Create State object from current context.
    """
    now = datetime.now()
    
    # Get user's historical engagement
    engagement_avg = get_user_engagement_average(user_id)
    
    # Get previous cost ratio (simplified - could be more sophisticated)
    previous_cost_ratio = 1.0  # Default neutral
    
    return State(
        intent=intent,
        user_engagement_avg=engagement_avg,
        time_of_day=now.hour,
        day_of_week=now.weekday(),
        content_type=content_type,
        has_brand_profile=has_brand_profile,
        has_website=has_website,
        previous_cost_ratio=previous_cost_ratio
    )

def get_optimized_workflow(state: State, use_rl: bool = True) -> List[str]:
    """
    Get optimized workflow for current state.
    
    Args:
        state: Current state
        use_rl: Whether to use RL or fall back to heuristics
    
    Returns:
        List of agent names to execute
    """
    if use_rl:
        action = select_action(state, exploration=True)
    else:
        action = select_action_heuristic(state)
    
    agents = ACTIONS.get(action, ACTIONS["quick_blog"])
    logger.info(f"Selected workflow '{action}': {agents}")
    return agents

def record_experience_and_update(
    state: State,
    action: str,
    engagement_rate: float,
    cost_usd: float,
    execution_time_minutes: float,
    content_approved: bool
):
    """
    Record experience and update Q-table.
    """
    # Calculate reward
    reward = calculate_reward(engagement_rate, cost_usd, execution_time_minutes, content_approved)
    
    # Save experience to database
    save_rl_experience(
        state_vector=json.dumps(state.to_dict()),
        action_taken=action,
        reward=reward,
        next_state_vector=None  # Could track next state if continuing conversation
    )
    
    # Update Q-table
    update_q_table(state, action, reward)
    
    logger.info(f"Recorded experience: action={action}, reward={reward:.2f}")

def train_from_historical_data(days: int = 30, min_samples: int = 10):
    """
    Train Q-table from historical data in database.
    This can be run periodically to improve the model.
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Get historical experiences
            cursor.execute("""
            SELECT state_vector, action_taken, reward, timestamp
            FROM rl_state
            WHERE timestamp >= datetime('now', '-' || ? || ' days')
            ORDER BY timestamp ASC
            """, (days,))
            
            experiences = cursor.fetchall()
            
            if len(experiences) < min_samples:
                logger.info(f"Insufficient data for training ({len(experiences)} samples)")
                return
            
            logger.info(f"Training from {len(experiences)} historical experiences...")
            
            for exp in experiences:
                state_dict = json.loads(exp[0])
                action = exp[1]
                reward = exp[2]
                
                # Reconstruct state
                state = State(**state_dict)
                
                # Update Q-table
                update_q_table(state, action, reward)
            
            logger.info("Training complete")
            
    except Exception as e:
        logger.error(f"Error training from historical data: {e}")

def get_q_table_summary() -> Dict[str, Any]:
    """Get summary statistics of Q-table for monitoring."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Count total entries
            cursor.execute("SELECT COUNT(*) FROM q_table")
            total_entries = cursor.fetchone()[0]
            
            # Get average Q-value
            cursor.execute("SELECT AVG(q_value), MIN(q_value), MAX(q_value) FROM q_table")
            avg_q, min_q, max_q = cursor.fetchone()
            
            # Get most common actions
            cursor.execute("""
            SELECT action, AVG(q_value) as avg_q, COUNT(*) as count
            FROM q_table
            GROUP BY action
            ORDER BY avg_q DESC
            LIMIT 5
            """)
            top_actions = [
                {"action": row[0], "avg_q_value": round(row[1], 3), "states": row[2]}
                for row in cursor.fetchall()
            ]
            
            return {
                "total_state_action_pairs": total_entries,
                "average_q_value": round(avg_q, 3) if avg_q else 0,
                "min_q_value": round(min_q, 3) if min_q else 0,
                "max_q_value": round(max_q, 3) if max_q else 0,
                "top_actions": top_actions
            }
    except Exception as e:
        logger.error(f"Error getting Q-table summary: {e}")
        return {}

