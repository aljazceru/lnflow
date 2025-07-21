"""Advanced fee optimization engine with game theory and risk modeling"""

import logging
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import json
import math
from datetime import datetime, timedelta
from scipy.optimize import minimize_scalar
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from ..analysis.analyzer import ChannelMetrics
from ..utils.config import Config
from .optimizer import FeeRecommendation, OptimizationStrategy

logger = logging.getLogger(__name__)
console = Console()


@dataclass
class NetworkPosition:
    """Channel's position in network topology"""
    betweenness_centrality: float
    closeness_centrality: float
    alternative_routes: int
    competitive_channels: int
    liquidity_scarcity_score: float


@dataclass
class RiskAssessment:
    """Risk analysis for fee changes"""
    channel_closure_risk: float  # 0-1
    liquidity_lock_risk: float   # 0-1
    competitive_retaliation: float  # 0-1
    revenue_volatility: float    # Standard deviation
    confidence_interval: Tuple[float, float]  # 95% CI for projections


@dataclass
class AdvancedRecommendation(FeeRecommendation):
    """Enhanced recommendation with risk and game theory"""
    network_position: NetworkPosition
    risk_assessment: RiskAssessment
    game_theory_score: float
    elasticity_model: str
    update_timing: str
    competitive_context: str
    
    @property
    def risk_adjusted_return(self) -> float:
        """Calculate risk-adjusted return using Sharpe-like ratio"""
        if self.risk_assessment.revenue_volatility == 0:
            return self.projected_earnings - self.current_earnings
        
        return (self.projected_earnings - self.current_earnings) / self.risk_assessment.revenue_volatility


class ElasticityModel(Enum):
    """Different elasticity modeling approaches"""
    SIMPLE_THRESHOLD = "simple_threshold"
    NETWORK_TOPOLOGY = "network_topology"
    COMPETITIVE_ANALYSIS = "competitive_analysis"
    HISTORICAL_RESPONSE = "historical_response"


class AdvancedFeeOptimizer:
    """Advanced fee optimizer with game theory, risk modeling, and competitive intelligence"""
    
    def __init__(self, config: Config, strategy: OptimizationStrategy = OptimizationStrategy.BALANCED):
        self.config = config
        self.strategy = strategy
        
        # Advanced parameters
        self.NETWORK_UPDATE_COST = 0.1  # Cost per update as % of revenue
        self.COMPETITOR_RESPONSE_DELAY = 3  # Days for competitor response
        self.RISK_FREE_RATE = 0.05  # Annual risk-free rate (5%)
        self.LIQUIDITY_PREMIUM = 0.02  # Premium for liquidity provision
        
        # Elasticity modeling parameters
        self.ELASTICITY_MODELS = {
            ElasticityModel.NETWORK_TOPOLOGY: self._calculate_topology_elasticity,
            ElasticityModel.COMPETITIVE_ANALYSIS: self._calculate_competitive_elasticity,
            ElasticityModel.HISTORICAL_RESPONSE: self._calculate_historical_elasticity
        }
        
    def optimize_fees_advanced(self, metrics: Dict[str, ChannelMetrics]) -> List[AdvancedRecommendation]:
        """Generate advanced fee optimization recommendations with risk and game theory"""
        
        # Phase 1: Analyze network positions
        network_positions = self._analyze_network_positions(metrics)
        
        # Phase 2: Model competitive landscape
        competitive_context = self._analyze_competitive_landscape(metrics)
        
        # Phase 3: Calculate risk assessments
        risk_assessments = self._calculate_risk_assessments(metrics, competitive_context)
        
        # Phase 4: Generate game-theoretic recommendations
        recommendations = []
        
        for channel_id, metric in metrics.items():
            # Multi-objective optimization
            recommendation = self._optimize_single_channel_advanced(
                channel_id, metric, 
                network_positions.get(channel_id),
                risk_assessments.get(channel_id),
                competitive_context
            )
            
            if recommendation:
                recommendations.append(recommendation)
        
        # Phase 5: Strategic timing and coordination
        recommendations = self._optimize_update_timing(recommendations)
        
        # Phase 6: Portfolio-level optimization
        recommendations = self._portfolio_optimization(recommendations)
        
        return sorted(recommendations, key=lambda x: x.risk_adjusted_return, reverse=True)
    
    def _analyze_network_positions(self, metrics: Dict[str, ChannelMetrics]) -> Dict[str, NetworkPosition]:
        """Analyze each channel's position in the network topology"""
        positions = {}
        
        for channel_id, metric in metrics.items():
            # Estimate network position based on flow patterns and capacity
            capacity_percentile = self._calculate_capacity_percentile(metric.capacity)
            flow_centrality = self._estimate_flow_centrality(metric)
            
            # Estimate alternative routes (simplified model)
            alternative_routes = self._estimate_alternative_routes(metric)
            
            # Competitive channel analysis
            competitive_channels = self._count_competitive_channels(metric)
            
            # Liquidity scarcity in local topology
            scarcity_score = self._calculate_liquidity_scarcity(metric)
            
            positions[channel_id] = NetworkPosition(
                betweenness_centrality=flow_centrality,
                closeness_centrality=capacity_percentile,
                alternative_routes=alternative_routes,
                competitive_channels=competitive_channels,
                liquidity_scarcity_score=scarcity_score
            )
        
        return positions
    
    def _calculate_topology_elasticity(self, metric: ChannelMetrics, position: NetworkPosition) -> float:
        """Calculate demand elasticity based on network topology"""
        
        # Base elasticity from position
        if position.alternative_routes < 3:
            base_elasticity = 0.2  # Low elasticity - few alternatives
        elif position.alternative_routes < 10:
            base_elasticity = 0.4  # Medium elasticity
        else:
            base_elasticity = 0.8  # High elasticity - many alternatives
        
        # Adjust for competitive pressure
        competition_factor = min(1.5, position.competitive_channels / 5.0)
        
        # Adjust for liquidity scarcity
        scarcity_factor = 1.0 - (position.liquidity_scarcity_score * 0.5)
        
        return base_elasticity * competition_factor * scarcity_factor
    
    def _calculate_competitive_elasticity(self, metric: ChannelMetrics, competitive_context: Dict) -> float:
        """Calculate elasticity based on competitive analysis"""
        
        current_rate = metric.channel.current_fee_rate
        market_rates = competitive_context.get('peer_fee_rates', [current_rate])
        
        if not market_rates or len(market_rates) < 2:
            return 0.5  # Default if no competitive data
        
        # Position in fee distribution
        percentile = np.percentile(market_rates, current_rate) / 100.0
        
        if percentile < 0.25:  # Low fees - higher elasticity
            return 0.8
        elif percentile < 0.75:  # Medium fees
            return 0.5
        else:  # High fees - lower elasticity (if still routing)
            return 0.3 if metric.monthly_flow > 0 else 1.0
    
    def _calculate_historical_elasticity(self, metric: ChannelMetrics) -> float:
        """Calculate elasticity based on historical response patterns"""
        
        # Simplified model - would need historical fee change data
        # High flow consistency suggests lower elasticity
        if metric.monthly_flow > 0 and metric.flow_efficiency > 0.7:
            return 0.3  # Consistent high flow - price insensitive
        elif metric.monthly_flow > 1_000_000:
            return 0.5  # Moderate flow
        else:
            return 0.8  # Low flow - price sensitive
    
    def _calculate_risk_assessments(self, metrics: Dict[str, ChannelMetrics], competitive_context: Dict) -> Dict[str, RiskAssessment]:
        """Calculate risk assessment for each channel"""
        assessments = {}
        
        for channel_id, metric in metrics.items():
            # Channel closure risk (based on peer behavior patterns)
            closure_risk = self._estimate_closure_risk(metric)
            
            # Liquidity lock-up risk
            lock_risk = self._estimate_liquidity_risk(metric)
            
            # Competitive retaliation risk
            retaliation_risk = self._estimate_retaliation_risk(metric, competitive_context)
            
            # Revenue volatility (simplified model)
            volatility = self._estimate_revenue_volatility(metric)
            
            # Confidence intervals
            ci_lower, ci_upper = self._calculate_confidence_intervals(metric)
            
            assessments[channel_id] = RiskAssessment(
                channel_closure_risk=closure_risk,
                liquidity_lock_risk=lock_risk,
                competitive_retaliation=retaliation_risk,
                revenue_volatility=volatility,
                confidence_interval=(ci_lower, ci_upper)
            )
        
        return assessments
    
    def _optimize_single_channel_advanced(self, 
                                        channel_id: str, 
                                        metric: ChannelMetrics,
                                        position: Optional[NetworkPosition],
                                        risk: Optional[RiskAssessment],
                                        competitive_context: Dict) -> Optional[AdvancedRecommendation]:
        """Optimize single channel with advanced modeling"""
        
        if not position or not risk:
            return None
        
        current_rate = metric.channel.current_fee_rate
        
        # Multi-objective optimization function
        def objective_function(new_rate: float) -> float:
            """Objective function combining revenue, risk, and strategic value"""
            
            # Calculate elasticity using best available model
            if position.alternative_routes > 0:
                elasticity = self._calculate_topology_elasticity(metric, position)
                model_used = ElasticityModel.NETWORK_TOPOLOGY
            else:
                elasticity = self._calculate_competitive_elasticity(metric, competitive_context)
                model_used = ElasticityModel.COMPETITIVE_ANALYSIS
            
            # Revenue impact
            rate_change = new_rate / max(current_rate, 1) - 1
            flow_reduction = min(0.5, abs(rate_change) * elasticity)
            
            if rate_change > 0:  # Fee increase
                new_flow = metric.monthly_flow * (1 - flow_reduction)
            else:  # Fee decrease
                new_flow = metric.monthly_flow * (1 + flow_reduction * 0.5)  # Asymmetric response
            
            projected_revenue = (new_flow / 1_000_000) * new_rate
            
            # Risk adjustment
            risk_penalty = (risk.channel_closure_risk * 0.3 + 
                          risk.competitive_retaliation * 0.2 + 
                          risk.liquidity_lock_risk * 0.1) * projected_revenue
            
            # Network update cost
            update_cost = projected_revenue * self.NETWORK_UPDATE_COST
            
            # Strategic value (network position)
            strategic_bonus = (position.liquidity_scarcity_score * 
                             position.betweenness_centrality * 
                             projected_revenue * 0.1)
            
            return -(projected_revenue - risk_penalty - update_cost + strategic_bonus)
        
        # Optimize within reasonable bounds
        min_rate = max(1, current_rate * 0.5)
        max_rate = min(5000, current_rate * 3.0)
        
        try:
            result = minimize_scalar(objective_function, bounds=(min_rate, max_rate), method='bounded')
            optimal_rate = int(result.x)
            
            if abs(optimal_rate - current_rate) < 5:  # Not worth changing
                return None
            
            # Create recommendation
            elasticity = self._calculate_topology_elasticity(metric, position)
            flow_change = (optimal_rate / max(current_rate, 1) - 1) * elasticity
            projected_flow = metric.monthly_flow * (1 - abs(flow_change))
            projected_earnings = (projected_flow / 1_000_000) * optimal_rate
            
            # Determine strategy context
            reason = self._generate_advanced_reasoning(metric, position, risk, current_rate, optimal_rate)
            confidence = self._calculate_recommendation_confidence(risk, position)
            priority = self._calculate_strategic_priority(position, risk, projected_earnings - metric.monthly_earnings)
            
            game_theory_score = self._calculate_game_theory_score(position, competitive_context)
            
            return AdvancedRecommendation(
                channel_id=channel_id,
                current_fee_rate=current_rate,
                recommended_fee_rate=optimal_rate,
                reason=reason,
                expected_impact=f"Projected: {flow_change*100:.1f}% flow change, {((projected_earnings/max(metric.monthly_earnings,1))-1)*100:.1f}% revenue change",
                confidence=confidence,
                priority=priority,
                current_earnings=metric.monthly_earnings,
                projected_earnings=projected_earnings,
                network_position=position,
                risk_assessment=risk,
                game_theory_score=game_theory_score,
                elasticity_model=ElasticityModel.NETWORK_TOPOLOGY.value,
                update_timing=self._suggest_update_timing(risk, competitive_context),
                competitive_context=self._describe_competitive_context(competitive_context)
            )
            
        except Exception as e:
            logger.error(f"Optimization failed for channel {channel_id}: {e}")
            return None
    
    def _portfolio_optimization(self, recommendations: List[AdvancedRecommendation]) -> List[AdvancedRecommendation]:
        """Optimize recommendations at portfolio level"""
        
        # Sort by risk-adjusted returns
        recommendations.sort(key=lambda x: x.risk_adjusted_return, reverse=True)
        
        # Limit simultaneous updates to avoid network spam
        high_priority = [r for r in recommendations if r.priority == "high"][:5]
        medium_priority = [r for r in recommendations if r.priority == "medium"][:8]
        low_priority = [r for r in recommendations if r.priority == "low"][:3]
        
        # Stagger update timing
        for i, rec in enumerate(high_priority):
            if i > 0:
                rec.update_timing = f"Week {i+1} - High Priority"
        
        for i, rec in enumerate(medium_priority):
            rec.update_timing = f"Week {(i//3)+2} - Medium Priority"
        
        for i, rec in enumerate(low_priority):
            rec.update_timing = f"Week {(i//2)+4} - Low Priority"
        
        return high_priority + medium_priority + low_priority
    
    # Helper methods for calculations
    def _calculate_capacity_percentile(self, capacity: int) -> float:
        """Estimate channel capacity percentile"""
        # Simplified model - would need network-wide data
        if capacity > 10_000_000:
            return 0.9
        elif capacity > 1_000_000:
            return 0.7
        else:
            return 0.3
    
    def _estimate_flow_centrality(self, metric: ChannelMetrics) -> float:
        """Estimate flow-based centrality"""
        if metric.monthly_flow > 50_000_000:
            return 0.9
        elif metric.monthly_flow > 10_000_000:
            return 0.7
        elif metric.monthly_flow > 1_000_000:
            return 0.5
        else:
            return 0.2
    
    def _estimate_alternative_routes(self, metric: ChannelMetrics) -> int:
        """Estimate number of alternative routes"""
        # Simplified heuristic based on flow patterns
        if metric.flow_efficiency > 0.8:
            return 15  # High efficiency suggests many alternatives
        elif metric.flow_efficiency > 0.5:
            return 8
        else:
            return 3
    
    def _count_competitive_channels(self, metric: ChannelMetrics) -> int:
        """Estimate number of competing channels"""
        # Simplified model
        return max(1, int(metric.capacity / 1_000_000))
    
    def _calculate_liquidity_scarcity(self, metric: ChannelMetrics) -> float:
        """Calculate local liquidity scarcity score"""
        # Higher scarcity = more valuable liquidity
        if metric.local_balance_ratio < 0.2 or metric.local_balance_ratio > 0.8:
            return 0.8  # Imbalanced = scarce
        else:
            return 0.3  # Balanced = less scarce
    
    def _analyze_competitive_landscape(self, metrics: Dict[str, ChannelMetrics]) -> Dict:
        """Analyze competitive landscape"""
        fee_rates = [m.channel.current_fee_rate for m in metrics.values() if m.channel.current_fee_rate > 0]
        
        return {
            'peer_fee_rates': fee_rates,
            'median_fee': np.median(fee_rates) if fee_rates else 100,
            'fee_variance': np.var(fee_rates) if fee_rates else 1000,
            'market_concentration': len(set(fee_rates)) / max(len(fee_rates), 1)
        }
    
    def _estimate_closure_risk(self, metric: ChannelMetrics) -> float:
        """Estimate risk of channel closure from fee changes"""
        # Higher risk for channels with warnings or low activity
        risk = 0.1  # Base risk
        
        if metric.monthly_flow == 0:
            risk += 0.3
        if len(metric.channel.warnings) > 0:
            risk += 0.2
        if metric.local_balance_ratio > 0.95:
            risk += 0.2
        
        return min(1.0, risk)
    
    def _estimate_liquidity_risk(self, metric: ChannelMetrics) -> float:
        """Estimate liquidity lock-up risk"""
        # Higher capacity = higher lock-up risk
        return min(0.8, metric.capacity / 20_000_000)
    
    def _estimate_retaliation_risk(self, metric: ChannelMetrics, context: Dict) -> float:
        """Estimate competitive retaliation risk"""
        current_rate = metric.channel.current_fee_rate
        median_rate = context.get('median_fee', current_rate)
        
        # Risk increases if significantly above market
        if current_rate > median_rate * 2:
            return 0.7
        elif current_rate > median_rate * 1.5:
            return 0.4
        else:
            return 0.1
    
    def _estimate_revenue_volatility(self, metric: ChannelMetrics) -> float:
        """Estimate revenue volatility"""
        # Simplified model - would need historical data
        if metric.flow_efficiency > 0.8:
            return metric.monthly_earnings * 0.2  # Low volatility
        else:
            return metric.monthly_earnings * 0.5  # High volatility
    
    def _calculate_confidence_intervals(self, metric: ChannelMetrics) -> Tuple[float, float]:
        """Calculate 95% confidence intervals"""
        volatility = self._estimate_revenue_volatility(metric)
        lower = metric.monthly_earnings - 1.96 * volatility
        upper = metric.monthly_earnings + 1.96 * volatility
        return (lower, upper)
    
    def _generate_advanced_reasoning(self, metric: ChannelMetrics, position: NetworkPosition, 
                                   risk: RiskAssessment, current_rate: int, optimal_rate: int) -> str:
        """Generate sophisticated reasoning for recommendation"""
        
        rate_change = (optimal_rate - current_rate) / current_rate * 100
        
        if rate_change > 20:
            return f"Significant fee increase justified by high liquidity scarcity ({position.liquidity_scarcity_score:.2f}) and limited alternatives ({position.alternative_routes} routes)"
        elif rate_change > 5:
            return f"Moderate increase based on strong network position (centrality: {position.betweenness_centrality:.2f}) with acceptable risk profile"
        elif rate_change < -20:
            return f"Aggressive reduction to capture market share with {position.competitive_channels} competing channels"
        elif rate_change < -5:
            return f"Strategic decrease to improve utilization while maintaining profitability"
        else:
            return f"Minor adjustment optimizing risk-return profile in competitive environment"
    
    def _calculate_recommendation_confidence(self, risk: RiskAssessment, position: NetworkPosition) -> str:
        """Calculate confidence level"""
        
        risk_score = (risk.channel_closure_risk + risk.competitive_retaliation + risk.liquidity_lock_risk) / 3
        position_score = (position.betweenness_centrality + position.liquidity_scarcity_score) / 2
        
        if risk_score < 0.3 and position_score > 0.6:
            return "high"
        elif risk_score < 0.5 and position_score > 0.4:
            return "medium"
        else:
            return "low"
    
    def _calculate_strategic_priority(self, position: NetworkPosition, risk: RiskAssessment, 
                                    expected_gain: float) -> str:
        """Calculate strategic priority"""
        
        strategic_value = position.liquidity_scarcity_score * position.betweenness_centrality
        risk_adjusted_gain = expected_gain / (1 + risk.revenue_volatility)
        
        if strategic_value > 0.5 and risk_adjusted_gain > 1000:
            return "high"
        elif strategic_value > 0.3 or risk_adjusted_gain > 500:
            return "medium"
        else:
            return "low"
    
    def _calculate_game_theory_score(self, position: NetworkPosition, context: Dict) -> float:
        """Calculate game theory strategic score"""
        
        # Nash equilibrium considerations
        market_power = min(1.0, 1.0 / max(1, position.competitive_channels))
        network_value = position.betweenness_centrality * position.liquidity_scarcity_score
        
        return (market_power * 0.6 + network_value * 0.4) * 100
    
    def _suggest_update_timing(self, risk: RiskAssessment, context: Dict) -> str:
        """Suggest optimal timing for fee update"""
        
        if risk.competitive_retaliation > 0.6:
            return "During low activity period to minimize retaliation"
        elif context.get('fee_variance', 0) > 500:
            return "Immediately while market is volatile"
        else:
            return "Standard update cycle"
    
    def _describe_competitive_context(self, context: Dict) -> str:
        """Describe competitive context"""
        
        median_fee = context.get('median_fee', 100)
        concentration = context.get('market_concentration', 0.5)
        
        if concentration > 0.8:
            return f"Highly competitive market (median: {median_fee} ppm)"
        elif concentration > 0.5:
            return f"Moderately competitive (median: {median_fee} ppm)"
        else:
            return f"Concentrated market (median: {median_fee} ppm)"
    
    def _optimize_update_timing(self, recommendations: List[AdvancedRecommendation]) -> List[AdvancedRecommendation]:
        """Optimize timing to minimize network disruption"""
        
        # Group by timing preferences
        immediate = []
        delayed = []
        
        for rec in recommendations:
            if rec.risk_assessment.competitive_retaliation < 0.3:
                immediate.append(rec)
            else:
                delayed.append(rec)
        
        # Stagger updates
        for i, rec in enumerate(immediate[:5]):  # Limit to 5 immediate updates
            rec.update_timing = f"Immediate batch {i+1}"
        
        for i, rec in enumerate(delayed):
            rec.update_timing = f"Week {(i//3)+2}"
        
        return immediate + delayed