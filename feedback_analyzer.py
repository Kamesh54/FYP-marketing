"""
Feedback Analyzer Agent
Implements batch mode update architecture for MABO framework.

Based on Paper 4: Updates occur once per learning cycle using complete batch
of stabilized rewards. Prevents overreaction to single delayed data points.
"""

import logging
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from mabo_framework import (
    GlobalCoordinator,
    LocalBayesianOptimizer,
    RewardQueue
)
from performance_monitor import PerformanceMonitorAgent
from database import get_db_connection

logger = logging.getLogger(__name__)

class FeedbackAnalyzerAgent:
    """
    Analyzes feedback and performs batch updates to MABO framework.
    Only updates once per learning cycle with complete stabilized batch.
    """
    
    def __init__(
        self,
        coordinator: GlobalCoordinator,
        local_optimizers: Dict[str, LocalBayesianOptimizer],
        performance_monitor: PerformanceMonitorAgent,
        update_frequency_hours: float = 24.0  # Daily updates
    ):
        self.coordinator = coordinator
        self.local_optimizers = local_optimizers
        self.performance_monitor = performance_monitor
        self.update_frequency_hours = update_frequency_hours
        self.last_update_time = datetime.now()
        self.pending_updates: List[RewardQueue] = []
    
    def should_update(self) -> bool:
        """
        Check if it's time for a batch update.
        """
        elapsed = (datetime.now() - self.last_update_time).total_seconds() / 3600
        return elapsed >= self.update_frequency_hours
    
    def collect_stabilized_batch(self) -> List[RewardQueue]:
        """
        Collect all stabilized rewards for batch processing.
        """
        stabilized = self.performance_monitor.get_stabilized_rewards()
        self.pending_updates.extend(stabilized)
        logger.info(f"Collected {len(stabilized)} stabilized rewards for batch update")
        return stabilized
    
    def perform_batch_update(self) -> Dict:
        """
        Perform batch update to MABO framework.
        This is the main learning step that happens once per cycle.
        """
        if not self.should_update():
            return {
                'status': 'not_ready',
                'message': f'Next update in {self.update_frequency_hours - (datetime.now() - self.last_update_time).total_seconds() / 3600:.1f} hours'
            }
        
        # Collect stabilized rewards
        stabilized = self.collect_stabilized_batch()
        
        if len(stabilized) == 0:
            logger.info("No stabilized rewards available for batch update")
            return {
                'status': 'no_data',
                'message': 'No stabilized rewards available'
            }
        
        # Group rewards by agent/action
        rewards_by_agent: Dict[str, List[RewardQueue]] = {}
        for reward_item in stabilized:
            # Extract agent from action (simplified - would parse action properly)
            agent = self._extract_agent_from_action(reward_item.action)
            if agent not in rewards_by_agent:
                rewards_by_agent[agent] = []
            rewards_by_agent[agent].append(reward_item)
        
        # Update local optimizers
        local_actions = {}
        local_costs = {}
        local_rewards = {}
        
        for agent, reward_items in rewards_by_agent.items():
            if agent not in self.local_optimizers:
                continue
            
            # Aggregate rewards for this agent
            total_reward = sum(item.reward for item in reward_items if item.reward is not None)
            total_cost = sum(item.cost for item in reward_items if item.cost is not None)
            avg_reward = total_reward / len(reward_items) if reward_items else 0.0
            
            # Get last action (simplified - would track actual actions)
            # For now, use a default action vector
            action_vector = self._get_action_vector(agent, reward_items[0].action)
            
            # Update local BO
            self.local_optimizers[agent].add_observation(
                action_vector,
                -avg_reward  # Negative because we minimize cost
            )
            
            local_actions[agent] = action_vector
            local_costs[agent] = total_cost
            local_rewards[agent] = total_reward
        
        # Update global coordinator
        coordination_state = self.coordinator.update_coordination_vars(
            local_actions,
            local_costs,
            local_rewards
        )
        
        # Clean up processed rewards
        processed_ids = [item.content_id for item in stabilized]
        self.performance_monitor.cleanup_processed_rewards(processed_ids)
        self.pending_updates = []
        
        self.last_update_time = datetime.now()
        
        logger.info(f"Batch update complete: {len(stabilized)} rewards processed, "
                   f"coordination iteration {coordination_state.iteration}")
        
        return {
            'status': 'success',
            'rewards_processed': len(stabilized),
            'agents_updated': list(local_actions.keys()),
            'coordination_iteration': coordination_state.iteration,
            'convergence': self.coordinator.check_convergence()
        }
    
    def _extract_agent_from_action(self, action: str) -> str:
        """
        Extract agent name from action string.
        Simplified - would parse properly based on action format.
        """
        # Map actions to agents (simplified)
        action_to_agent = {
            'full_workflow': 'content_agent_blog',
            'quick_blog': 'content_agent_blog',
            'comprehensive_blog': 'content_agent_blog',
            'social_basic': 'content_agent_social',
            'social_full': 'content_agent_social',
            'seo_only': 'seo_agent',
            'research_only': 'gap_analyzer',
            'content_only': 'content_agent_blog'
        }
        return action_to_agent.get(action, 'unknown')
    
    def _get_action_vector(self, agent: str, action: str) -> np.ndarray:
        """
        Convert action string to action vector for local BO.
        Simplified - would use actual action encoding.
        """
        # Simple encoding: hash action to vector
        action_hash = hash(action) % 1000
        return np.array([action_hash / 1000.0, len(action) / 100.0])
    
    def get_update_status(self) -> Dict:
        """
        Get status of feedback analyzer.
        """
        stabilized = self.performance_monitor.get_stabilized_rewards()
        time_since_update = (datetime.now() - self.last_update_time).total_seconds() / 3600
        
        return {
            'last_update': self.last_update_time.isoformat(),
            'time_since_update_hours': time_since_update,
            'pending_rewards': len(self.pending_updates),
            'stabilized_rewards': len(stabilized),
            'ready_for_update': self.should_update(),
            'update_frequency_hours': self.update_frequency_hours
        }
    
    def force_update(self) -> Dict:
        """
        Force an immediate batch update (for testing/debugging).
        """
        self.last_update_time = datetime.now() - timedelta(hours=self.update_frequency_hours + 1)
        return self.perform_batch_update()

