"""
MABO Agent - Main Integration Module
Replaces RL agent with Multi-Agent Bayesian Optimization framework.

This module provides a drop-in replacement for rl_agent.py that uses
the MABO framework for workflow optimization.
"""

import numpy as np
import json
import logging
import hashlib
from typing import Dict, List, Optional, Any
from datetime import datetime
from mabo_framework import (
    GlobalCoordinator,
    LocalBayesianOptimizer,
    CoordinationState,
    LocalBOState
)
from budget_allocator import BudgetAllocatorAgent
from performance_monitor import PerformanceMonitorAgent
from feedback_analyzer import FeedbackAnalyzerAgent
from database import get_db_connection
from memory import find_similar_by_text, find_similar_by_visual

logger = logging.getLogger(__name__)

# Agent definitions (matching RL agent structure)
AGENTS = {
    "webcrawler":          {"dim": 2, "bounds": [(0, 1), (0, 10)]},
    "seo_agent":           {"dim": 2, "bounds": [(0, 1), (0, 30)]},
    "keyword_extractor":   {"dim": 2, "bounds": [(0, 1), (0, 15)]},
    "gap_analyzer":        {"dim": 2, "bounds": [(0, 1), (0, 20)]},
    "content_agent_blog":  {"dim": 2, "bounds": [(0, 1), (0, 25)]},
    "content_agent_social":{"dim": 2, "bounds": [(0, 1), (0, 10)]},
    "image_generator":     {"dim": 2, "bounds": [(0, 1), (0, 45)]},
    "social_poster":       {"dim": 2, "bounds": [(0, 1), (0, 5)]},
    # New agents
    "research_agent":      {"dim": 2, "bounds": [(0, 1), (0, 20)]},
    "brand_agent":         {"dim": 2, "bounds": [(0, 1), (0, 5)]},
    "critic_agent":        {"dim": 2, "bounds": [(0, 1), (0, 8)]},
    "campaign_agent":      {"dim": 2, "bounds": [(0, 1), (0, 15)]},
}

# Workflow definitions (matching RL agent)
WORKFLOWS = {
    "full_workflow":           ["webcrawler", "research_agent", "seo_agent", "keyword_extractor",
                                "gap_analyzer", "content_agent_blog", "critic_agent"],
    "quick_blog":              ["keyword_extractor", "content_agent_blog", "critic_agent"],
    "comprehensive_blog":      ["research_agent", "keyword_extractor", "gap_analyzer",
                                "content_agent_blog", "critic_agent"],
    "social_basic":            ["content_agent_social", "image_generator", "critic_agent"],
    "social_full":             ["keyword_extractor", "content_agent_social", "image_generator",
                                "critic_agent", "social_poster"],
    "seo_only":                ["webcrawler", "seo_agent"],
    "research_only":           ["research_agent", "gap_analyzer"],
    "content_only":            ["content_agent_blog", "critic_agent"],
    "brand_setup":             ["brand_agent"],
    "campaign_schedule":       ["campaign_agent"],
    "full_campaign_pipeline":  ["research_agent", "keyword_extractor", "content_agent_blog",
                                "image_generator", "critic_agent", "campaign_agent"],
}

class MABOAgent:
    """
    Main MABO Agent that replaces RL agent functionality.
    Provides workflow selection using Multi-Agent Bayesian Optimization.
    """
    
    def __init__(
        self,
        total_budget: float = 1000.0,
        agents: Optional[List[str]] = None,
        update_frequency_hours: float = 24.0
    ):
        self.total_budget = total_budget
        self.agents = agents or list(AGENTS.keys())
        self.update_frequency_hours = update_frequency_hours
        
        # Initialize Global Coordinator
        self.coordinator = GlobalCoordinator(
            total_budget=total_budget,
            agents=self.agents
        )
        
        # Initialize Local BO optimizers for each agent
        self.local_optimizers = {}
        for agent_name in self.agents:
            if agent_name in AGENTS:
                config = AGENTS[agent_name]
                self.local_optimizers[agent_name] = LocalBayesianOptimizer(
                    agent_name=agent_name,
                    action_dim=config["dim"],
                    bounds=config["bounds"]
                )
        
        # Initialize Performance Monitor
        self.performance_monitor = PerformanceMonitorAgent(
            default_delay_hours=24.0
        )
        
        # Initialize Feedback Analyzer
        self.feedback_analyzer = FeedbackAnalyzerAgent(
            coordinator=self.coordinator,
            local_optimizers=self.local_optimizers,
            performance_monitor=self.performance_monitor,
            update_frequency_hours=update_frequency_hours
        )
        
        # Initialize Budget Allocator
        self.budget_allocator = BudgetAllocatorAgent(
            total_budget=total_budget,
            campaigns=self.agents,
            allocation_method='ucb'
        )
        
        # Load state from database
        self._load_state()
    
    def _load_state(self):
        """Load MABO state from database."""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Load coordination state
                cursor.execute("""
                    SELECT iteration, coordination_vars, lagrange_multipliers, 
                           budget_allocations, total_budget
                    FROM mabo_coordination_state
                    ORDER BY iteration DESC
                    LIMIT 1
                """)
                row = cursor.fetchone()
                if row:
                    self.coordinator.coordination_state = CoordinationState(
                        iteration=row[0],
                        coordination_vars=json.loads(row[1]),
                        lagrange_multipliers=json.loads(row[2]),
                        budget_allocations=json.loads(row[3]),
                        total_budget=row[4]
                    )
                
                # Load local BO states
                for agent_name in self.agents:
                    cursor.execute("""
                        SELECT observed_points, observed_values, best_point, best_value, iteration
                        FROM mabo_local_bo_state
                        WHERE agent_name = ?
                    """, (agent_name,))
                    row = cursor.fetchone()
                    if row and agent_name in self.local_optimizers:
                        optimizer = self.local_optimizers[agent_name]
                        optimizer.state.observed_points = [
                            np.array(p) for p in json.loads(row[0])
                        ]
                        optimizer.state.observed_values = json.loads(row[1])
                        if row[2]:
                            optimizer.state.best_point = np.array(json.loads(row[2]))
                        optimizer.state.best_value = row[3]
                        optimizer.state.iteration = row[4]
                        optimizer.update_gp()
                
                logger.info("MABO state loaded from database")
        except Exception as e:
            logger.error(f"Failed to load MABO state: {e}")
    
    def _save_state(self):
        """Save MABO state to database (robust JSON serialization)."""
        def _to_serializable(o):
            if o is None:
                return None
            if isinstance(o, np.ndarray):
                return o.tolist()
            if isinstance(o, (np.integer, np.floating)):
                return float(o)
            if isinstance(o, datetime):
                return o.isoformat()
            # Let json fallback raise TypeError for unknown objects
            raise TypeError(f"Type not serializable: {type(o)}")

        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                # Ensure coordinator.state exists and provide safe defaults
                coord_state = getattr(self.coordinator, "coordination_state", None)
                if coord_state is None:
                    coord_state = type("CS", (), {
                        "iteration": 0,
                        "coordination_vars": {},
                        "lagrange_multipliers": {},
                        "budget_allocations": {},
                        "total_budget": getattr(self, "total_budget", 0.0),
                        "last_update": datetime.utcnow().isoformat()
                    })()

                # Serialize safely using json.dumps + custom handler
                coordination_vars = json.dumps(coord_state.coordination_vars, default=_to_serializable)
                lagrange = json.dumps(coord_state.lagrange_multipliers, default=_to_serializable)
                budgets = json.dumps(coord_state.budget_allocations, default=_to_serializable)
                total_budget = getattr(coord_state, "total_budget", getattr(self, "total_budget", 0.0))
                last_update = getattr(coord_state, "last_update", datetime.utcnow().isoformat())

                cursor.execute("""
                    INSERT OR REPLACE INTO mabo_coordination_state
                    (iteration, coordination_vars, lagrange_multipliers, 
                     budget_allocations, total_budget, last_update)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    int(getattr(coord_state, "iteration", 0)),
                    coordination_vars,
                    lagrange,
                    budgets,
                    float(total_budget),
                    last_update
                ))

                # Local BO states
                for agent_name, optimizer in self.local_optimizers.items():
                    st = optimizer.state
                    obs_points = [p.tolist() if hasattr(p, "tolist") else p for p in getattr(st, "observed_points", [])]
                    obs_vals = list(getattr(st, "observed_values", []))
                    best_point = getattr(st, "best_point", None)
                    best_point_json = json.dumps(best_point.tolist() if best_point is not None and hasattr(best_point, "tolist") else best_point, default=_to_serializable)
                    best_value = float(getattr(st, "best_value", float("inf")) or float("inf"))
                    iteration = int(getattr(st, "iteration", 0))

                    cursor.execute("""
                        INSERT OR REPLACE INTO mabo_local_bo_state
                        (agent_name, observed_points, observed_values, 
                         best_point, best_value, iteration, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        agent_name,
                        json.dumps(obs_points, default=_to_serializable),
                        json.dumps(obs_vals, default=_to_serializable),
                        best_point_json,
                        best_value,
                        iteration,
                        datetime.utcnow()
                    ))

                # commit happens in get_db_connection contextmanager
                logger.info("MABO state saved to database (robust save)")
        except Exception as e:
            logger.exception("Failed to save MABO state: %s", e)
    
    def create_state_from_context(
        self,
        intent: str,
        user_id: int,
        content_type: str = "blog",
        has_brand_profile: bool = False,
        has_website: bool = False
    ) -> Dict[str, Any]:
        """
        Create state context (simplified for MABO - state is encoded in action selection).
        Returns state hash for tracking.
        """
        state_dict = {
            "intent": intent,
            "user_id": user_id,
            "content_type": content_type,
            "has_brand_profile": has_brand_profile,
            "has_website": has_website,
            "timestamp": datetime.now().isoformat()
        }
        
        # Create deterministic hash
        state_str = json.dumps(state_dict, sort_keys=True)
        state_hash = hashlib.md5(state_str.encode()).hexdigest()[:16]
        
        return {
            "state_dict": state_dict,
            "state_hash": state_hash
        }
    
    def get_optimized_workflow_details(
        self,
        state_context: Dict[str, Any],
        use_mabo: bool = True
    ) -> Dict[str, Any]:
        """Return workflow metadata for optimized plan."""
        intent = state_context.get("state_dict", {}).get("intent", "blog_generation")
        
        if not use_mabo:
            workflow_name = self._heuristic_workflow_selection(intent, state_context)
        else:
            workflow_name = self._select_workflow_mabo(intent, state_context)
        # compute lightweight alignment score using memory (if embeddings present)
        alignment_score = None
        try:
            # prefer explicit embeddings if provided in state_context
            text_vec = state_context.get('text_vector')
            vis_vec = state_context.get('visual_vector')
            if text_vec:
                sims = find_similar_by_text(text_vec, top_k=3)
                if sims:
                    # use the stored alignment_score if available, else 0.0
                    alignment_score = float(sims[0].get('alignment_score') or 0.0)
            elif vis_vec:
                sims = find_similar_by_visual(vis_vec, top_k=3)
                if sims:
                    alignment_score = float(sims[0].get('alignment_score') or 0.0)
        except Exception:
            alignment_score = None
        
        agents = WORKFLOWS.get(workflow_name, WORKFLOWS["quick_blog"])
        logger.info(f"MABO selected workflow '{workflow_name}': {agents}")
        return {
            "workflow_name": workflow_name,
            "agents": agents,
            "alignment_score": alignment_score
        }
    
    def get_optimized_workflow(
        self,
        state_context: Dict[str, Any],
        use_mabo: bool = True
    ) -> List[str]:
        """
        Backwards-compatible wrapper returning only agent list.
        """
        details = self.get_optimized_workflow_details(state_context, use_mabo=use_mabo)
        return details["agents"]
    
    def get_alternative_workflow_details(
        self,
        intent: str,
        state_context: Dict[str, Any],
        exclude_workflow: Optional[str] = None
    ) -> Dict[str, Any]:
        """Provide a secondary workflow option distinct from primary."""
        fallback_name = self._heuristic_workflow_selection(intent, state_context)
        
        if exclude_workflow and fallback_name == exclude_workflow:
            # Pick a deterministic alternative to ensure variety
            intent_defaults = {
                "blog_generation": ["quick_blog", "comprehensive_blog", "content_only"],
                "social_post": ["social_full", "social_basic"],
                "seo_analysis": ["seo_only", "research_only"],
                "competitor_research": ["research_only", "quick_blog"]
            }
            for candidate in intent_defaults.get(intent, ["quick_blog", "full_workflow"]):
                if candidate != exclude_workflow and candidate in WORKFLOWS:
                    fallback_name = candidate
                    break
        
        agents = WORKFLOWS.get(fallback_name, WORKFLOWS["quick_blog"])
        return {
            "workflow_name": fallback_name,
            "agents": agents
        }
    
    def _select_workflow_mabo(
        self,
        intent: str,
        state_context: Dict[str, Any]
    ) -> str:
        """
        Select workflow using MABO framework.
        Uses local BO optimizers to select best action for each agent.
        """
        # Map intent to primary agent
        intent_to_agent = {
            "blog_generation": "content_agent_blog",
            "social_post": "content_agent_social",
            "seo_analysis": "seo_agent",
            "competitor_research": "gap_analyzer"
        }
        
        primary_agent = intent_to_agent.get(intent, "content_agent_blog")
        
        # Get action from primary agent's local BO
        if primary_agent in self.local_optimizers:
            optimizer = self.local_optimizers[primary_agent]
            action_vector = optimizer.select_action(self.coordinator)
            
            # Map action vector to workflow (simplified)
            # In practice, this would be learned from experience
            workflow_name = self._action_vector_to_workflow(
                primary_agent,
                action_vector,
                intent
            )
        else:
            workflow_name = self._heuristic_workflow_selection(intent, state_context)
        
        return workflow_name
    
    def _action_vector_to_workflow(
        self,
        agent: str,
        action_vector: np.ndarray,
        intent: str
    ) -> str:
        """
        Map action vector to workflow name.
        Simplified - would use learned mapping.
        """
        # Use heuristic for now, but could learn this mapping
        if intent == "blog_generation":
            if agent == "content_agent_blog":
                return "comprehensive_blog"
            return "quick_blog"
        elif intent == "social_post":
            return "social_full"
        elif intent == "seo_analysis":
            return "seo_only"
        else:
            return "quick_blog"
    
    def _heuristic_workflow_selection(
        self,
        intent: str,
        state_context: Dict[str, Any]
    ) -> str:
        """Heuristic workflow selection (fallback) returning workflow name."""
        state_dict = state_context.get("state_dict", {})
        has_website = state_dict.get("has_website", False)
        
        if intent == "seo_analysis":
            return "seo_only"
        elif intent == "blog_generation":
            if has_website:
                return "comprehensive_blog"
            return "quick_blog"
        elif intent == "social_post":
            return "social_basic"
        elif intent == "competitor_research":
            return "research_only"
        else:
            return "quick_blog"
    
    def register_workflow_execution(
        self,
        content_id: str,
        state_hash: str,
        action: str,
        cost: float,
        execution_time: float,
        expected_delay_hours: Optional[float] = None
    ):
        """
        Register workflow execution for reward tracking.
        Replaces rl_agent.record_experience_and_update() but queues instead.
        """
        # Register with performance monitor
        self.performance_monitor.register_workflow_start(
            content_id,
            state_hash,
            action,
            expected_delay_hours
        )
        
        # Update immediate metrics
        self.performance_monitor.update_immediate_metrics(
            content_id,
            cost,
            execution_time,
            content_approved=False  # Will be updated when approved
        )
        
        logger.info(f"Registered workflow execution: {content_id}, cost={cost:.2f}")
        
        # Persist MABO state promptly so the execution is durable
        try:
            self._save_state()
        except Exception:
            logger.exception("Failed to save MABO state after registering execution")
    
    def update_content_approval(
        self,
        content_id: str,
        approved: bool
    ):
        """Update content approval status."""
        self.performance_monitor.update_immediate_metrics(
            content_id,
            cost=None,  # Don't update cost
            execution_time=None,  # Don't update time
            content_approved=approved
        )
    
    def update_engagement_metrics(
        self,
        content_id: str,
        engagement_rate: float
    ):
        """Update delayed engagement metrics."""
        self.performance_monitor.update_delayed_metrics(
            content_id,
            engagement_rate
        )
    
    def perform_batch_update(self) -> Dict:
        """
        Trigger batch update of MABO framework.
        Should be called periodically (e.g., daily).
        """
        return self.feedback_analyzer.perform_batch_update()

    def record_social_feedback(self, content_id: str, platform: str, reward: float,
                               langsmith_run_id: Optional[str] = None):
        """
        Feed delayed social-media performance reward back into MABO and LangSmith.
        reward: 0.0–1.0 normalised engagement rate / platform score.
        """
        self.update_engagement_metrics(content_id, reward)
        from langsmith_tracer import record_mabo_reward
        if langsmith_run_id:
            record_mabo_reward(langsmith_run_id, reward, platform)
        logger.info(f"[MABO] Social feedback recorded — content={content_id} "
                    f"platform={platform} reward={reward:.3f}")

    def trigger_prompt_evolution(self, agent_name: str, context_type: str,
                                  feedback: str, current_score: float) -> Optional[str]:
        """
        Ask the prompt optimizer to evolve a prompt based on collected feedback.
        Returns new version_id or None on failure.
        """
        try:
            from prompt_optimizer import evolve_prompt
            vid = evolve_prompt(agent_name, context_type, feedback, current_score)
            logger.info(f"[MABO] Prompt evolved for {agent_name}/{context_type} → {vid}")
            return vid
        except Exception as e:
            logger.error(f"Prompt evolution failed: {e}")
            return None
    
    def _sanitize_for_json(self, obj: Any) -> Any:
        """Replace inf/nan values with None for JSON serialization."""
        import math
        if isinstance(obj, dict):
            return {k: self._sanitize_for_json(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._sanitize_for_json(item) for item in obj]
        elif isinstance(obj, float):
            if math.isinf(obj) or math.isnan(obj):
                return None
            return obj
        else:
            return obj
    
    def get_mabo_stats(self) -> Dict[str, Any]:
        """
        Get MABO framework statistics.
        Replaces rl_agent.get_q_table_summary()
        """
        coordination_state = self.coordinator.get_state()
        monitor_status = self.performance_monitor.check_stabilization_status()
        analyzer_status = self.feedback_analyzer.get_update_status()
        
        # Get local BO stats
        local_bo_stats = {}
        for agent_name, optimizer in self.local_optimizers.items():
            state = optimizer.state
            best_val = state.best_value
            # Replace inf with None for JSON serialization
            if best_val == float('inf') or best_val == np.inf:
                best_val = None
            local_bo_stats[agent_name] = {
                "observations": len(state.observed_points),
                "best_value": best_val,
                "iteration": state.iteration
            }
        
        stats = {
            "coordination": {
                "iteration": coordination_state.iteration,
                "total_budget": coordination_state.total_budget,
                "budget_allocations": coordination_state.budget_allocations,
                "converged": self.coordinator.check_convergence()
            },
            "performance_monitor": monitor_status,
            "feedback_analyzer": analyzer_status,
            "local_optimizers": local_bo_stats
        }
        
        # Sanitize for JSON
        return self._sanitize_for_json(stats)

# Global MABO agent instance
_mabo_agent_instance: Optional[MABOAgent] = None

def get_mabo_agent(
    total_budget: float = 1000.0,
    agents: Optional[List[str]] = None
) -> MABOAgent:
    """Get or create global MABO agent instance."""
    global _mabo_agent_instance
    if _mabo_agent_instance is None:
        _mabo_agent_instance = MABOAgent(
            total_budget=total_budget,
            agents=agents
        )
    return _mabo_agent_instance

