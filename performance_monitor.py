"""
Performance Monitor Agent
Implements reward queuing and stabilization for delayed rewards.

Based on Paper 4: Handles real-world data lag and prevents premature updates.
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime
from mabo_framework import RewardStabilizer, RewardQueue
from database import get_db_connection

logger = logging.getLogger(__name__)

class PerformanceMonitorAgent:
    """
    Monitors performance and manages reward stabilization.
    Ensures rewards are only used after they've stabilized.
    """
    
    def __init__(self, default_delay_hours: float = 24.0):
        self.stabilizer = RewardStabilizer(default_delay_hours)
        self.default_delay_hours = default_delay_hours
    
    def register_workflow_start(
        self,
        content_id: str,
        state_hash: str,
        action: str,
        expected_delay_hours: Optional[float] = None
    ):
        """
        Register that a workflow has started.
        Queue the reward for later stabilization.
        """
        reward_item = self.stabilizer.queue_reward(
            content_id,
            state_hash,
            action,
            expected_delay_hours
        )
        logger.info(f"Registered workflow start: {content_id}, action={action}")
        return reward_item
    
    def update_immediate_metrics(
        self,
        content_id: str,
        cost: float,
        execution_time: float,
        content_approved: bool
    ):
        """
        Update immediate metrics (available right after workflow).
        """
        self.stabilizer.update_reward(
            content_id,
            cost=cost,
            execution_time=execution_time,
            content_approved=content_approved
        )
        logger.info(f"Updated immediate metrics for {content_id}")
    
    def update_delayed_metrics(
        self,
        content_id: str,
        engagement_rate: float
    ):
        """
        Update delayed metrics (engagement rate from social media).
        """
        self.stabilizer.update_reward(
            content_id,
            engagement_rate=engagement_rate
        )
        logger.info(f"Updated delayed metrics for {content_id}: engagement={engagement_rate:.3f}")
    
    def get_stabilized_rewards(self) -> List[RewardQueue]:
        """
        Get all rewards that have stabilized and are ready for batch update.
        """
        stabilized = self.stabilizer.get_stabilized_rewards()
        logger.info(f"Found {len(stabilized)} stabilized rewards")
        return stabilized
    
    def check_stabilization_status(self) -> Dict:
        """
        Get status of reward queue.
        """
        total = len(self.stabilizer.reward_queue)
        stabilized = len(self.stabilizer.get_stabilized_rewards())
        pending = total - stabilized
        
        return {
            'total_rewards': total,
            'stabilized': stabilized,
            'pending': pending,
            'stabilization_rate': stabilized / total if total > 0 else 0.0
        }
    
    def cleanup_processed_rewards(self, content_ids: List[str]):
        """
        Remove processed rewards from queue.
        """
        self.stabilizer.remove_stabilized(content_ids)
        logger.info(f"Cleaned up {len(content_ids)} processed rewards")

