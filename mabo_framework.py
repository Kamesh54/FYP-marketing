import numpy as np
import json
import logging
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from scipy.optimize import minimize
import hashlib

logger = logging.getLogger(__name__)

@dataclass
class CoordinationState:
    """Global coordination variables p_k for MABO framework."""
    iteration: int
    coordination_vars: Dict[str, float]  # p_k for each agent
    lagrange_multipliers: Dict[str, float]  # λ_k (shadow prices)
    budget_allocations: Dict[str, float]  # B_j for each campaign/agent
    total_budget: float
    convergence_threshold: float = 1e-4
    last_update: datetime = None
    
    def __post_init__(self):
        if self.last_update is None:
            self.last_update = datetime.now()
    
    def to_dict(self) -> Dict:
        """Serialize to dictionary."""
        data = asdict(self)
        data['last_update'] = self.last_update.isoformat() if self.last_update else None
        return data
    
    @classmethod
    def from_dict(cls, data: Dict):
        """Deserialize from dictionary."""
        if data.get('last_update'):
            data['last_update'] = datetime.fromisoformat(data['last_update'])
        return cls(**data)

@dataclass
class LocalBOState:
    """Local Bayesian Optimization state for an agent."""
    agent_name: str
    observed_points: List[np.ndarray]  # X_i,t
    observed_values: List[float]  # f_i(X_i,t)
    gp_mean: Optional[np.ndarray] = None
    gp_cov: Optional[np.ndarray] = None
    best_point: Optional[np.ndarray] = None
    best_value: float = np.inf
    iteration: int = 0
    
    def add_observation(self, x: np.ndarray, f_x: float):
        """Add new observation to the GP."""
        self.observed_points.append(x)
        self.observed_values.append(f_x)
        self.iteration += 1
        
        if f_x < self.best_value:
            self.best_value = f_x
            self.best_point = x.copy()

@dataclass
class RewardQueue:
    """Queue for delayed rewards with stabilization."""
    content_id: str
    state_hash: str
    action: str
    expected_delay_hours: float
    reward: Optional[float] = None
    engagement_rate: Optional[float] = None
    cost: Optional[float] = None          # kept for ADMM budget tracking, NOT used in reward
    execution_time: Optional[float] = None
    content_approved: Optional[bool] = None
    critic_score: Optional[float] = None  # LLM critic / readability score  [0, 1]
    keyword_relevance: Optional[float] = None  # keyword alignment score     [0, 1]
    created_at: datetime = None
    stabilized_at: Optional[datetime] = None
    is_stabilized: bool = False
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
    
    def check_stabilization(self) -> bool:
        """Check if reward has stabilized (passed delay window)."""
        if self.is_stabilized:
            return True
        
        elapsed = (datetime.now() - self.created_at).total_seconds() / 3600
        if elapsed >= self.expected_delay_hours:
            self.is_stabilized = True
            self.stabilized_at = datetime.now()
            return True
        return False

# ==================== GLOBAL COORDINATOR ====================

class GlobalCoordinator:
    """
    Global Coordinator for MABO Framework.
    Manages coordination variables p_k and enforces global constraints.
    """
    
    def __init__(
        self,
        total_budget: float,
        agents: List[str],
        rho: float = 0.1,  # ADMM penalty parameter
        max_iterations: int = 100,
        convergence_threshold: float = 1e-4
    ):
        self.total_budget = total_budget
        self.agents = agents
        self.rho = rho
        self.max_iterations = max_iterations
        self.convergence_threshold = convergence_threshold
        
        # Initialize coordination state
        self.coordination_state = CoordinationState(
            iteration=0,
            coordination_vars={agent: 0.0 for agent in agents},
            lagrange_multipliers={agent: 0.0 for agent in agents},
            budget_allocations={agent: total_budget / len(agents) for agent in agents},
            total_budget=total_budget
        )
    
    def update_coordination_vars(
        self,
        local_actions: Dict[str, np.ndarray],
        local_costs: Dict[str, float],
        local_rewards: Dict[str, float]
    ) -> CoordinationState:
        """
        Update coordination variables p_k using ADMM update.
        
        p_{k+1} = p_k + ρ * (sum(x_i) - budget_constraint)
        """
        # Calculate total resource usage
        total_usage = sum(local_costs.get(agent, 0.0) for agent in self.agents)
        budget_violation = total_usage - self.total_budget
        
        # Update coordination variables (ADMM)
        for agent in self.agents:
            # Update Lagrange multiplier (shadow price)
            self.coordination_state.lagrange_multipliers[agent] += \
                self.rho * (local_costs.get(agent, 0.0) - 
                           self.coordination_state.budget_allocations.get(agent, 0.0))
            
            # Update coordination variable
            self.coordination_state.coordination_vars[agent] = \
                self.coordination_state.budget_allocations.get(agent, 0.0) - \
                local_costs.get(agent, 0.0)
        
        # Update budget allocations based on performance
        self._update_budget_allocations(local_rewards, local_costs)
        
        self.coordination_state.iteration += 1
        self.coordination_state.last_update = datetime.now()
        
        return self.coordination_state
    
    def _update_budget_allocations(
        self,
        local_rewards: Dict[str, float],
        local_costs: Dict[str, float]
    ):
        """Update budget allocations based on ROI (reward/cost ratio)."""
        if not local_rewards or not local_costs:
            return
        
        # Calculate ROI for each agent
        rois = {}
        for agent in self.agents:
            cost = local_costs.get(agent, 0.0)
            reward = local_rewards.get(agent, 0.0)
            if cost > 0:
                rois[agent] = reward / cost
            else:
                rois[agent] = 0.0
        
        # Normalize ROIs to get allocation weights
        total_roi = sum(rois.values())
        if total_roi > 0:
            for agent in self.agents:
                weight = rois[agent] / total_roi
                self.coordination_state.budget_allocations[agent] = \
                    weight * self.total_budget
        else:
            # Equal allocation if no ROI data
            equal_share = self.total_budget / len(self.agents)
            for agent in self.agents:
                self.coordination_state.budget_allocations[agent] = equal_share
    
    def get_coordination_term(self, agent: str) -> float:
        """
        Get coordination term δ_i(x_i, p_i,k) for agent.
        
        δ_i = λ_i * (cost_i - p_i) + (ρ/2) * ||cost_i - p_i||²
        """
        lambda_i = self.coordination_state.lagrange_multipliers.get(agent, 0.0)
        p_i = self.coordination_state.coordination_vars.get(agent, 0.0)
        
        # This will be augmented with actual cost when agent calls it
        return lambda_i, p_i
    
    def check_convergence(self) -> bool:
        """Check if coordination variables have converged."""
        if self.coordination_state.iteration < 2:
            return False
        
        # Check if coordination vars are stable
        # (In practice, compare with previous iteration)
        return False  # Simplified - would compare with previous state
    
    def get_state(self) -> CoordinationState:
        """Get current coordination state."""
        return self.coordination_state

# ==================== LOCAL BAYESIAN OPTIMIZATION ====================

class LocalBayesianOptimizer:
    """
    Local Bayesian Optimization for individual agents.
    Implements GP-UCB acquisition function with coordination term.
    """
    
    def __init__(
        self,
        agent_name: str,
        action_dim: int,
        bounds: List[Tuple[float, float]],
        kernel_length_scale: float = 1.0,
        kernel_variance: float = 1.0,
        noise_variance: float = 0.01,
        beta: float = 2.0  # UCB exploration parameter
    ):
        self.agent_name = agent_name
        self.action_dim = action_dim
        self.bounds = np.array(bounds)
        self.kernel_length_scale = kernel_length_scale
        self.kernel_variance = kernel_variance
        self.noise_variance = noise_variance
        self.beta = beta
        
        self.state = LocalBOState(
            agent_name=agent_name,
            observed_points=[],
            observed_values=[]
        )
    
    def rbf_kernel(self, x1: np.ndarray, x2: np.ndarray) -> float:
        """Radial Basis Function (RBF) kernel."""
        diff = x1 - x2
        return self.kernel_variance * np.exp(
            -0.5 * np.sum(diff ** 2) / (self.kernel_length_scale ** 2)
        )

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Cosine similarity between two vectors."""
        if a is None or b is None:
            return 0.0
        na = np.linalg.norm(a)
        nb = np.linalg.norm(b)
        if na == 0 or nb == 0:
            return 0.0
        return float(np.dot(a, b) / (na * nb))

    def composite_kernel(self, x1: Any, x2: Any, w_text: float = 0.6, w_vis: float = 0.3, w_time: float = 0.1) -> float:
        """
        Composite kernel supporting multimodal observations.
        If observations are standard numeric arrays, fall back to RBF.
        If observations are dicts with `text_vector` and `visual_vector`, compute a weighted sum.
        """
        try:
            # If x1/x2 are dict-like multimodal observations
            if isinstance(x1, dict) and isinstance(x2, dict):
                text_sim = self._cosine_similarity(
                    np.array(x1.get('text_vector', [])),
                    np.array(x2.get('text_vector', []))
                )
                vis_sim = self._cosine_similarity(
                    np.array(x1.get('visual_vector', [])),
                    np.array(x2.get('visual_vector', []))
                )
                # time similarity can be a simple kernel on timestamps if present
                t1 = x1.get('context_metadata', {}).get('timestamp')
                t2 = x2.get('context_metadata', {}).get('timestamp')
                time_sim = 0.0
                if t1 and t2:
                    # Convert to numerical seconds since epoch
                    try:
                        import dateutil.parser as dp
                        s1 = dp.isoparse(t1).timestamp()
                        s2 = dp.isoparse(t2).timestamp()
                        # Gaussian on time difference
                        dt = float(s1 - s2)
                        time_sim = np.exp(-0.5 * (dt ** 2) / (self.kernel_length_scale ** 2))
                    except Exception:
                        time_sim = 0.0

                return float(w_text * text_sim + w_vis * vis_sim + w_time * time_sim)
            # Fallback: numeric arrays -> RBF
            if isinstance(x1, (list, tuple)) or isinstance(x2, (list, tuple)):
                xa = np.array(x1)
                xb = np.array(x2)
                return self.rbf_kernel(xa, xb)
            if isinstance(x1, np.ndarray) and isinstance(x2, np.ndarray):
                return self.rbf_kernel(x1, x2)
        except Exception:
            logger.exception("Error in composite_kernel")
        # Default fallback
        try:
            xa = np.array(x1)
            xb = np.array(x2)
            return self.rbf_kernel(xa, xb)
        except Exception:
            return 0.0
    
    def update_gp(self):
        """Update Gaussian Process posterior from observations."""
        if len(self.state.observed_points) == 0:
            return
        
        n = len(self.state.observed_points)
        X = np.array(self.state.observed_points)
        y = np.array(self.state.observed_values)
        
        # Compute kernel matrix (use composite kernel if multimodal dicts detected)
        K = np.zeros((n, n))
        for i in range(n):
            for j in range(n):
                try:
                    K[i, j] = self.composite_kernel(X[i], X[j])
                except Exception:
                    K[i, j] = self.rbf_kernel(np.array(X[i]), np.array(X[j]))
        
        # Add noise
        K += self.noise_variance * np.eye(n)
        
        # GP posterior mean and covariance
        # μ(x*) = k(x*, X)^T (K + σ²I)^(-1) y
        # σ²(x*) = k(x*, x*) - k(x*, X)^T (K + σ²I)^(-1) k(x*, X)
        try:
            K_inv = np.linalg.inv(K)
            self.state.gp_mean = K_inv @ y
            self.state.gp_cov = K
        except np.linalg.LinAlgError:
            logger.warning(f"GP update failed for {self.agent_name}, using default")
            self.state.gp_mean = np.zeros(n)
            self.state.gp_cov = K
    
    def predict(self, x: np.ndarray) -> Tuple[float, float]:
        """
        Predict mean and variance at point x.
        Returns: (mean, std)
        """
        if len(self.state.observed_points) == 0:
            return 0.0, self.kernel_variance
        
        X = np.array(self.state.observed_points)
        y = np.array(self.state.observed_values)
        n = len(X)
        
        # Compute kernel vector
        k_star = np.array([self.rbf_kernel(x, X[i]) for i in range(n)])
        
        # Compute kernel matrix
        K = np.zeros((n, n))
        for i in range(n):
            for j in range(n):
                K[i, j] = self.rbf_kernel(X[i], X[j])
        K += self.noise_variance * np.eye(n)
        
        try:
            K_inv = np.linalg.inv(K)
            mean = k_star.T @ K_inv @ y
            k_star_star = self.kernel_variance
            var = k_star_star - k_star.T @ K_inv @ k_star
            std = np.sqrt(max(var, 1e-10))
            return mean, std
        except np.linalg.LinAlgError:
            return 0.0, self.kernel_variance
    
    def acquisition_function(
        self,
        x: np.ndarray,
        coordination_term: float = 0.0
    ) -> float:
        """
        GP-UCB acquisition function with coordination term.
        
        α(x) = μ(x) - β*σ(x) + δ(x, p)
        """
        mean, std = self.predict(x)
        ucb = mean - self.beta * std  # Negative because we minimize cost
        return ucb + coordination_term
    
    def select_action(
        self,
        coordinator: GlobalCoordinator
    ) -> np.ndarray:
        """
        Select next action using augmented acquisition function.
        
        x_{i,t} = argmin_x [α_i(x) + δ_i(x, p_i,k)]
        """
        # Get coordination term
        lambda_i, p_i = coordinator.get_coordination_term(self.agent_name)
        
        # Define augmented acquisition function
        def augmented_acq(x):
            # Estimate cost from x (simplified - would use actual cost model)
            estimated_cost = np.sum(x)  # Placeholder
            coordination_penalty = lambda_i * (estimated_cost - p_i) + \
                                 (coordinator.rho / 2) * (estimated_cost - p_i) ** 2
            
            return self.acquisition_function(x, coordination_penalty)
        
        # Optimize acquisition function
        best_x = None
        best_acq = np.inf
        
        # Multi-start optimization
        for _ in range(10):
            x0 = np.random.uniform(
                self.bounds[:, 0],
                self.bounds[:, 1],
                size=self.action_dim
            )
            
            result = minimize(
                augmented_acq,
                x0,
                bounds=self.bounds,
                method='L-BFGS-B'
            )
            
            if result.success and result.fun < best_acq:
                best_acq = result.fun
                best_x = result.x
        
        if best_x is None:
            # Fallback to random point
            best_x = np.random.uniform(
                self.bounds[:, 0],
                self.bounds[:, 1],
                size=self.action_dim
            )
        
        return best_x
    
    def add_observation(self, x: np.ndarray, f_x: float):
        """Add observation and update GP."""
        self.state.add_observation(x, f_x)
        self.update_gp()
    
    def get_state(self) -> LocalBOState:
        """Get current local BO state."""
        return self.state

# ==================== REWARD STABILIZATION ====================

class RewardStabilizer:
    """
    Manages delayed rewards with stabilization queue.
    Prevents premature updates until rewards are confirmed.
    """
    
    def __init__(self, default_delay_hours: float = 24.0):
        self.default_delay_hours = default_delay_hours
        self.reward_queue: List[RewardQueue] = []
    
    def queue_reward(
        self,
        content_id: str,
        state_hash: str,
        action: str,
        expected_delay_hours: Optional[float] = None
    ) -> RewardQueue:
        """Queue a reward that will arrive later."""
        delay = expected_delay_hours or self.default_delay_hours
        reward_item = RewardQueue(
            content_id=content_id,
            state_hash=state_hash,
            action=action,
            expected_delay_hours=delay
        )
        self.reward_queue.append(reward_item)
        logger.info(f"Queued reward for {content_id}, delay={delay}h")
        return reward_item
    
    def update_reward(
        self,
        content_id: str,
        engagement_rate: Optional[float] = None,
        cost: Optional[float] = None,
        execution_time: Optional[float] = None,
        content_approved: Optional[bool] = None,
        critic_score: Optional[float] = None,
        keyword_relevance: Optional[float] = None
    ):
        """Update reward data for a queued item."""
        for item in self.reward_queue:
            if item.content_id == content_id:
                if engagement_rate is not None:
                    item.engagement_rate = engagement_rate
                if cost is not None:
                    item.cost = cost  # stored for ADMM budget tracking only
                if execution_time is not None:
                    item.execution_time = execution_time
                if content_approved is not None:
                    item.content_approved = content_approved
                if critic_score is not None:
                    item.critic_score = critic_score
                if keyword_relevance is not None:
                    item.keyword_relevance = keyword_relevance

                # Calculate reward when the minimum required signal is available.
                # engagement_rate and content_approved are required;
                # critic_score and keyword_relevance default to 0.5 if not yet received.
                if item.engagement_rate is not None and item.content_approved is not None:
                    item.reward = self._calculate_reward(
                        item.engagement_rate,
                        item.cost or 0.0,
                        item.execution_time or 0.0,
                        item.content_approved,
                        critic_score=item.critic_score if item.critic_score is not None else 0.5,
                        keyword_relevance=item.keyword_relevance if item.keyword_relevance is not None else 0.5,
                    )
                break
    
    def _calculate_reward(
        self,
        engagement_rate: float,
        cost: float,
        execution_time: float,
        content_approved: bool,
        critic_score: float = 0.5,
        keyword_relevance: float = 0.5
    ) -> float:
        """
        Calculate normalised content quality reward.

        Design principle
        ----------------
        Cost is NOT part of the reward — it is a hard constraint enforced
        by ADMM via Lagrange multipliers (see GlobalCoordinator.update_coordination).
        Including cost here as well would double-penalise spending and cause
        the GP to converge to zero-budget configurations regardless of quality.

        Reward components (all in [0, 1]):
          0.50 × engagement_rate_norm  — direct audience response signal
          0.30 × critic_score          — LLM critic / readability / SEO quality gate
          0.20 × keyword_relevance     — alignment with extracted target keywords

        Optional approval gate: if content is not approved, apply a −0.15 penalty
        to discourage low-quality outputs without completely zeroing the signal.
        """
        # Normalise engagement: typical IG rate 1-5%; treat 10%+ as perfect score
        engagement_norm = min(1.0, engagement_rate / 0.10)

        # Weighted quality composite
        reward = (
            0.50 * engagement_norm
            + 0.30 * min(1.0, max(0.0, critic_score))
            + 0.20 * min(1.0, max(0.0, keyword_relevance))
        )

        # Approval gate penalty (soft — does not zero the reward)
        if not content_approved:
            reward = max(0.0, reward - 0.15)

        return float(reward)
    
    def get_stabilized_rewards(self) -> List[RewardQueue]:
        """Get all stabilized rewards ready for batch update."""
        stabilized = []
        for item in self.reward_queue:
            if item.check_stabilization() and item.reward is not None:
                stabilized.append(item)
        return stabilized
    
    def remove_stabilized(self, content_ids: List[str]):
        """Remove stabilized items from queue."""
        self.reward_queue = [
            item for item in self.reward_queue
            if item.content_id not in content_ids
        ]

