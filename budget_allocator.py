"""
Budget Allocator Agent
Implements Parametric Multi-Armed Bandit for budget allocation across campaigns/agents.

Based on Paper 1: Data-efficient budget allocation with censored data handling.
Uses shifted/scaled logistic functions to model saturation clicks and cost.
"""

import numpy as np
import logging
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime
from scipy.optimize import minimize
from scipy.stats import poisson
from scipy.special import expit  # Logistic function

logger = logging.getLogger(__name__)

@dataclass
class CampaignState:
    """State for a single campaign/ad group."""
    campaign_id: str
    total_budget_spent: float = 0.0
    total_clicks: int = 0
    total_impressions: int = 0
    observations: List[Tuple[float, int, int]] = None  # (budget, clicks, impressions)
    is_censored: bool = False  # True if budget ran out before saturation
    
    def __post_init__(self):
        if self.observations is None:
            self.observations = []

class ParametricBandit:
    """
    Parametric Multi-Armed Bandit for budget allocation.
    Models saturation clicks and cost using shifted/scaled logistic functions.
    """
    
    def __init__(
        self,
        campaigns: List[str],
        max_budget_per_campaign: float = 1000.0,
        initial_budget_split: Optional[Dict[str, float]] = None
    ):
        self.campaigns = campaigns
        self.max_budget_per_campaign = max_budget_per_campaign
        
        # Initialize campaign states
        self.campaign_states = {
            cid: CampaignState(campaign_id=cid)
            for cid in campaigns
        }
        
        # Initialize parameters for each campaign
        # θ = (n^sat, φ, α, β) where:
        # n^sat: saturation clicks
        # φ: cost parameter
        # α, β: logistic function parameters
        self.parameters = {
            cid: {
                'n_sat': 1000.0,  # Initial guess for saturation clicks
                'phi': 0.5,       # Cost parameter
                'alpha': 1.0,     # Logistic scale
                'beta': 100.0     # Logistic shift
            }
            for cid in campaigns
        }
        
        # Initial budget allocation
        if initial_budget_split:
            self.budget_allocations = initial_budget_split
        else:
            # Equal split
            equal_share = 1.0 / len(campaigns)
            self.budget_allocations = {cid: equal_share for cid in campaigns}
    
    def logistic_saturation(self, budget: float, n_sat: float, alpha: float, beta: float) -> float:
        """
        Shifted/scaled logistic function for saturation clicks.
        
        n(b) = n^sat * σ(α * (b - β))
        where σ is the logistic function
        """
        return n_sat * expit(alpha * (budget - beta))
    
    def cost_function(self, budget: float, phi: float) -> float:
        """
        Cost as function of budget.
        
        cost(b) = φ * b
        """
        return phi * budget
    
    def log_likelihood_censored(
        self,
        campaign_id: str,
        observations: List[Tuple[float, int, int]]
    ) -> float:
        """
        Log-likelihood for censored data using survival function.
        
        For censored observations (budget ran out), we use:
        P(n ≥ n_observed | budget) = 1 - CDF(n_observed)
        """
        params = self.parameters[campaign_id]
        n_sat = params['n_sat']
        alpha = params['alpha']
        beta = params['beta']
        
        log_likelihood = 0.0
        
        for budget, clicks, impressions in observations:
            # Expected clicks from logistic model
            expected_clicks = self.logistic_saturation(budget, n_sat, alpha, beta)
            
            # Use Poisson distribution for clicks
            # For non-censored: P(n = clicks | λ = expected_clicks)
            # For censored: P(n ≥ clicks | λ = expected_clicks) = 1 - CDF(clicks)
            
            if expected_clicks > 0:
                if self.campaign_states[campaign_id].is_censored:
                    # Censored: use survival function
                    prob = 1 - poisson.cdf(clicks - 1, expected_clicks)
                    log_likelihood += np.log(max(prob, 1e-10))
                else:
                    # Non-censored: use PMF
                    prob = poisson.pmf(clicks, expected_clicks)
                    log_likelihood += np.log(max(prob, 1e-10))
        
        return log_likelihood
    
    def update_parameters(self, campaign_id: str):
        """
        Update parameters using maximum likelihood estimation.
        Handles both censored and non-censored observations.
        """
        observations = self.campaign_states[campaign_id].observations
        if len(observations) < 2:
            return  # Need at least 2 observations
        
        # Objective: maximize log-likelihood
        def neg_log_likelihood(params):
            n_sat, phi, alpha, beta = params
            
            # Constraints
            if n_sat <= 0 or alpha <= 0 or beta < 0:
                return 1e10
            
            # Temporarily update parameters
            old_params = self.parameters[campaign_id].copy()
            self.parameters[campaign_id] = {
                'n_sat': n_sat,
                'phi': phi,
                'alpha': alpha,
                'beta': beta
            }
            
            # Calculate log-likelihood
            ll = self.log_likelihood_censored(campaign_id, observations)
            
            # Restore old parameters
            self.parameters[campaign_id] = old_params
            
            return -ll  # Negative because we minimize
        
        # Initial guess
        current = self.parameters[campaign_id]
        x0 = [current['n_sat'], current['phi'], current['alpha'], current['beta']]
        
        # Bounds
        bounds = [
            (1.0, 100000.0),    # n_sat
            (0.01, 10.0),       # phi
            (0.1, 10.0),        # alpha
            (0.0, 10000.0)      # beta
        ]
        
        try:
            result = minimize(
                neg_log_likelihood,
                x0,
                bounds=bounds,
                method='L-BFGS-B'
            )
            
            if result.success:
                n_sat, phi, alpha, beta = result.x
                self.parameters[campaign_id] = {
                    'n_sat': n_sat,
                    'phi': phi,
                    'alpha': alpha,
                    'beta': beta
                }
                logger.info(f"Updated parameters for {campaign_id}: n_sat={n_sat:.1f}, phi={phi:.3f}")
        except Exception as e:
            logger.error(f"Parameter update failed for {campaign_id}: {e}")
    
    def add_observation(
        self,
        campaign_id: str,
        budget: float,
        clicks: int,
        impressions: int,
        is_censored: bool = False
    ):
        """Add observation and update parameters."""
        state = self.campaign_states[campaign_id]
        state.observations.append((budget, clicks, impressions))
        state.total_budget_spent += budget
        state.total_clicks += clicks
        state.total_impressions += impressions
        state.is_censored = is_censored
        
        # Update parameters
        self.update_parameters(campaign_id)
    
    def expected_clicks(self, campaign_id: str, budget: float) -> float:
        """Get expected clicks for a given budget."""
        params = self.parameters[campaign_id]
        return self.logistic_saturation(
            budget,
            params['n_sat'],
            params['alpha'],
            params['beta']
        )
    
    def expected_cost(self, campaign_id: str, budget: float) -> float:
        """Get expected cost for a given budget."""
        params = self.parameters[campaign_id]
        return self.cost_function(budget, params['phi'])
    
    def allocate_budget(
        self,
        total_budget: float,
        method: str = 'ucb'  # 'ucb', 'thompson', 'greedy'
    ) -> Dict[str, float]:
        """
        Allocate budget across campaigns using bandit strategy.
        
        Returns: Dict mapping campaign_id to budget allocation
        """
        if method == 'ucb':
            return self._ucb_allocation(total_budget)
        elif method == 'thompson':
            return self._thompson_allocation(total_budget)
        else:  # greedy
            return self._greedy_allocation(total_budget)
    
    def _ucb_allocation(self, total_budget: float) -> Dict[str, float]:
        """
        Upper Confidence Bound allocation.
        Balances exploration and exploitation.
        """
        allocations = {}
        
        # Calculate UCB for each campaign
        ucbs = {}
        for cid in self.campaigns:
            state = self.campaign_states[cid]
            
            # Estimate ROI (clicks per dollar)
            if state.total_budget_spent > 0:
                avg_clicks_per_dollar = state.total_clicks / state.total_budget_spent
            else:
                avg_clicks_per_dollar = 0.0
            
            # Confidence interval (simplified)
            n_obs = len(state.observations)
            confidence = 2.0 * np.sqrt(np.log(n_obs + 1) / (n_obs + 1))
            
            ucbs[cid] = avg_clicks_per_dollar + confidence
        
        # Allocate proportionally to UCB
        total_ucb = sum(ucbs.values())
        if total_ucb > 0:
            for cid in self.campaigns:
                allocations[cid] = (ucbs[cid] / total_ucb) * total_budget
        else:
            # Equal allocation
            equal_share = total_budget / len(self.campaigns)
            allocations = {cid: equal_share for cid in self.campaigns}
        
        return allocations
    
    def _thompson_allocation(self, total_budget: float) -> Dict[str, float]:
        """
        Thompson Sampling allocation.
        Samples from posterior distribution of ROI.
        """
        allocations = {}
        
        # Sample ROI for each campaign
        sampled_rois = {}
        for cid in self.campaigns:
            state = self.campaign_states[cid]
            
            if state.total_budget_spent > 0:
                # Use Beta distribution for clicks/success rate
                # Simplified: use normal approximation
                mean_roi = state.total_clicks / state.total_budget_spent
                std_roi = np.sqrt(mean_roi / state.total_budget_spent) if state.total_budget_spent > 0 else 1.0
                
                # Sample from posterior
                sampled_rois[cid] = np.random.normal(mean_roi, std_roi)
                sampled_rois[cid] = max(0, sampled_rois[cid])  # Ensure non-negative
            else:
                sampled_rois[cid] = 1.0  # Optimistic prior
        
        # Allocate proportionally
        total_roi = sum(sampled_rois.values())
        if total_roi > 0:
            for cid in self.campaigns:
                allocations[cid] = (sampled_rois[cid] / total_roi) * total_budget
        else:
            equal_share = total_budget / len(self.campaigns)
            allocations = {cid: equal_share for cid in self.campaigns}
        
        return allocations
    
    def _greedy_allocation(self, total_budget: float) -> Dict[str, float]:
        """
        Greedy allocation based on best observed ROI.
        """
        allocations = {}
        
        # Calculate ROI for each campaign
        rois = {}
        for cid in self.campaigns:
            state = self.campaign_states[cid]
            if state.total_budget_spent > 0:
                rois[cid] = state.total_clicks / state.total_budget_spent
            else:
                rois[cid] = 0.0
        
        # Allocate to best performers
        total_roi = sum(rois.values())
        if total_roi > 0:
            for cid in self.campaigns:
                allocations[cid] = (rois[cid] / total_roi) * total_budget
        else:
            equal_share = total_budget / len(self.campaigns)
            allocations = {cid: equal_share for cid in self.campaigns}
        
        return allocations
    
    def get_campaign_stats(self, campaign_id: str) -> Dict:
        """Get statistics for a campaign."""
        state = self.campaign_states[campaign_id]
        params = self.parameters[campaign_id]
        
        return {
            'campaign_id': campaign_id,
            'total_budget_spent': state.total_budget_spent,
            'total_clicks': state.total_clicks,
            'total_impressions': state.total_impressions,
            'ctr': state.total_clicks / state.total_impressions if state.total_impressions > 0 else 0.0,
            'cpc': state.total_budget_spent / state.total_clicks if state.total_clicks > 0 else 0.0,
            'n_sat': params['n_sat'],
            'phi': params['phi'],
            'observations': len(state.observations),
            'is_censored': state.is_censored
        }

class BudgetAllocatorAgent:
    """
    Budget Allocator Agent that uses Parametric Bandit for allocation.
    """
    
    def __init__(
        self,
        total_budget: float,
        campaigns: List[str],
        allocation_method: str = 'ucb'
    ):
        self.total_budget = total_budget
        self.bandit = ParametricBandit(campaigns)
        self.allocation_method = allocation_method
    
    def allocate_daily_budget(self) -> Dict[str, float]:
        """Allocate daily budget across campaigns."""
        allocations = self.bandit.allocate_budget(
            self.total_budget,
            method=self.allocation_method
        )
        return allocations
    
    def update_from_observation(
        self,
        campaign_id: str,
        budget: float,
        clicks: int,
        impressions: int,
        is_censored: bool = False
    ):
        """Update bandit with new observation."""
        self.bandit.add_observation(
            campaign_id,
            budget,
            clicks,
            impressions,
            is_censored
        )
    
    def get_allocation_report(self) -> Dict:
        """Get detailed allocation report."""
        allocations = self.allocate_daily_budget()
        stats = {
            cid: self.bandit.get_campaign_stats(cid)
            for cid in self.bandit.campaigns
        }
        
        return {
            'total_budget': self.total_budget,
            'allocations': allocations,
            'campaign_stats': stats,
            'method': self.allocation_method
        }

