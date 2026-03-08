"""
Validation Metrics for MABO Framework
Tracks convergence, cumulative regret, and budget constraint satisfaction.
"""

import numpy as np
import logging
import math
from typing import Dict, List, Optional, Any
from datetime import datetime
from database import get_db_connection
from mabo_framework import CoordinationState

logger = logging.getLogger(__name__)

class ValidationMetrics:
    """
    Tracks validation metrics for MABO framework:
    1. Convergence of coordination parameters
    2. Cumulative regret vs baselines
    3. Budget constraint satisfaction
    """
    
    def __init__(self):
        self.regret_history: List[float] = []
        self.budget_violations: List[float] = []
        self.coordination_history: List[Dict] = []
    
    def track_coordination_convergence(
        self,
        coordination_state: CoordinationState
    ) -> Dict:
        """
        Track convergence of coordination parameters p_k.
        Convergence: ||p_{k+1} - p_k|| < threshold
        """
        state_dict = {
            'iteration': coordination_state.iteration,
            'coordination_vars': coordination_state.coordination_vars.copy(),
            'lagrange_multipliers': coordination_state.lagrange_multipliers.copy(),
            'budget_allocations': coordination_state.budget_allocations.copy(),
            'timestamp': datetime.now().isoformat()
        }
        
        self.coordination_history.append(state_dict)
        
        # Calculate convergence metric
        if len(self.coordination_history) >= 2:
            prev = self.coordination_history[-2]
            curr = self.coordination_history[-1]
            
            # Calculate L2 norm of change in coordination variables
            prev_vars = np.array(list(prev['coordination_vars'].values()))
            curr_vars = np.array(list(curr['coordination_vars'].values()))
            
            change_norm = np.linalg.norm(curr_vars - prev_vars)
            
            converged = change_norm < coordination_state.convergence_threshold
            
            return {
                'iteration': coordination_state.iteration,
                'change_norm': float(change_norm),
                'converged': converged,
                'threshold': coordination_state.convergence_threshold
            }
        else:
            return {
                'iteration': coordination_state.iteration,
                'change_norm': float('inf'),
                'converged': False,
                'threshold': coordination_state.convergence_threshold
            }
    
    def calculate_regret(
        self,
        actual_reward: float,
        baseline_reward: float,
        method: str = 'epsilon_greedy'  # 'epsilon_greedy', 'random', 'greedy'
    ) -> float:
        """
        Calculate instantaneous regret.
        Regret = baseline_reward - actual_reward
        (Positive regret means we did worse than baseline)
        """
        regret = baseline_reward - actual_reward
        self.regret_history.append(regret)
        return regret
    
    def get_cumulative_regret(self) -> Dict:
        """
        Calculate cumulative regret over time.
        """
        if len(self.regret_history) == 0:
            return {
                'cumulative_regret': 0.0,
                'average_regret': 0.0,
                'total_samples': 0
            }
        
        cumulative = np.cumsum(self.regret_history)
        cumulative_regret = float(cumulative[-1])
        average_regret = float(np.mean(self.regret_history))
        
        return {
            'cumulative_regret': cumulative_regret,
            'average_regret': average_regret,
            'total_samples': len(self.regret_history),
            'regret_trend': 'decreasing' if len(self.regret_history) > 10 and 
                           np.mean(self.regret_history[-10:]) < np.mean(self.regret_history[:10])
                           else 'increasing'
        }
    
    def check_budget_constraint(
        self,
        total_budget: float,
        actual_spending: Dict[str, float]
    ) -> Dict:
        """
        Check if budget constraint is satisfied.
        Constraint: sum(B_j) <= B_max
        """
        total_spent = sum(actual_spending.values())
        violation = total_spent - total_budget
        
        self.budget_violations.append(violation)
        
        satisfied = violation <= 0
        
        return {
            'total_budget': total_budget,
            'total_spent': total_spent,
            'violation': violation,
            'satisfied': satisfied,
            'utilization_rate': total_spent / total_budget if total_budget > 0 else 0.0
        }
    
    def get_budget_statistics(self) -> Dict:
        """
        Get statistics about budget constraint satisfaction.
        """
        if len(self.budget_violations) == 0:
            return {
                'total_violations': 0,
                'average_violation': 0.0,
                'max_violation': 0.0,
                'satisfaction_rate': 1.0
            }
        
        violations = np.array(self.budget_violations)
        positive_violations = violations[violations > 0]
        
        avg_violation = float(np.mean(violations))
        max_violation = float(np.max(violations))
        min_violation = float(np.min(violations))
        
        # Replace inf/nan with None
        if math.isinf(avg_violation) or math.isnan(avg_violation):
            avg_violation = None
        if math.isinf(max_violation) or math.isnan(max_violation):
            max_violation = None
        if math.isinf(min_violation) or math.isnan(min_violation):
            min_violation = None
        
        return {
            'total_violations': len(positive_violations),
            'average_violation': avg_violation,
            'max_violation': max_violation,
            'min_violation': min_violation,
            'satisfaction_rate': 1.0 - (len(positive_violations) / len(violations)) if len(violations) > 0 else 1.0
        }
    
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
    
    def get_comprehensive_report(self) -> Dict:
        """
        Get comprehensive validation report.
        """
        convergence = None
        if len(self.coordination_history) >= 2:
            # Get latest convergence metric
            latest = self.coordination_history[-1]
            prev = self.coordination_history[-2]
            prev_vars = np.array(list(prev['coordination_vars'].values()))
            curr_vars = np.array(list(latest['coordination_vars'].values()))
            change_norm = float(np.linalg.norm(curr_vars - prev_vars))
            # Replace inf with None
            if np.isinf(change_norm) or np.isnan(change_norm):
                change_norm = None
            convergence = {
                'latest_change_norm': change_norm,
                'iterations_tracked': len(self.coordination_history)
            }
        
        report = {
            'convergence': convergence,
            'regret': self.get_cumulative_regret(),
            'budget': self.get_budget_statistics(),
            'summary': {
                'is_converging': convergence is not None and convergence.get('latest_change_norm') is not None and convergence['latest_change_norm'] < 0.01,
                'regret_trending_down': self.get_cumulative_regret().get('regret_trend') == 'decreasing',
                'budget_satisfied': self.get_budget_statistics()['satisfaction_rate'] > 0.95
            }
        }
        
        # Sanitize for JSON
        return self._sanitize_for_json(report)
    
    def save_metrics_to_db(self):
        """Save metrics to database for persistence."""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Save regret history
                if self.regret_history:
                    cursor.execute("""
                        INSERT INTO validation_metrics
                        (metric_type, value, timestamp)
                        VALUES (?, ?, ?)
                    """, ('regret', self.regret_history[-1], datetime.now()))
                
                # Save budget violations
                if self.budget_violations:
                    cursor.execute("""
                        INSERT INTO validation_metrics
                        (metric_type, value, timestamp)
                        VALUES (?, ?, ?)
                    """, ('budget_violation', self.budget_violations[-1], datetime.now()))
                
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to save validation metrics: {e}")

# Global instance
_validation_metrics = ValidationMetrics()

def get_validation_metrics() -> ValidationMetrics:
    """Get global validation metrics instance."""
    return _validation_metrics

