"""Fee optimization engine based on real channel data analysis"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from ..analysis.analyzer import ChannelMetrics
from ..utils.config import Config

logger = logging.getLogger(__name__)
console = Console()


class OptimizationStrategy(Enum):
    """Available optimization strategies"""
    AGGRESSIVE = "aggressive"  # Maximize fees even if it reduces flow
    BALANCED = "balanced"      # Balance between fees and flow
    CONSERVATIVE = "conservative"  # Maintain flow, modest fee increases


@dataclass
class FeeRecommendation:
    """Fee optimization recommendation for a channel"""
    channel_id: str
    current_fee_rate: int
    recommended_fee_rate: int
    reason: str
    expected_impact: str
    confidence: str
    priority: str
    current_earnings: float
    projected_earnings: float
    
    @property
    def fee_change_pct(self) -> float:
        if self.current_fee_rate == 0:
            return float('inf')
        return ((self.recommended_fee_rate - self.current_fee_rate) / self.current_fee_rate) * 100


class FeeOptimizer:
    """Optimize channel fees based on performance metrics"""
    
    def __init__(self, config: Config, strategy: OptimizationStrategy = OptimizationStrategy.BALANCED):
        self.config = config
        self.strategy = strategy
        
        # Fee optimization parameters based on real data analysis
        self.HIGH_FLOW_THRESHOLD = 10_000_000  # 10M sats
        self.LOW_FLOW_THRESHOLD = 1_000_000    # 1M sats
        self.HIGH_BALANCE_THRESHOLD = 0.8      # 80% local balance
        self.LOW_BALANCE_THRESHOLD = 0.2       # 20% local balance
        self.MIN_FEE_RATE = 1                  # Minimum 1 ppm
        self.MAX_FEE_RATE = 5000               # Maximum 5000 ppm
        
        # Strategy-specific parameters
        if strategy == OptimizationStrategy.AGGRESSIVE:
            self.FEE_INCREASE_FACTOR = 2.0
            self.FLOW_PRESERVATION_WEIGHT = 0.3
        elif strategy == OptimizationStrategy.CONSERVATIVE:
            self.FEE_INCREASE_FACTOR = 1.2
            self.FLOW_PRESERVATION_WEIGHT = 0.8
        else:  # BALANCED
            self.FEE_INCREASE_FACTOR = 1.5
            self.FLOW_PRESERVATION_WEIGHT = 0.6
    
    def optimize_fees(self, metrics: Dict[str, ChannelMetrics]) -> List[FeeRecommendation]:
        """Generate fee optimization recommendations"""
        recommendations = []
        
        # Categorize channels for different optimization strategies
        high_performers = []
        underperformers = []
        imbalanced_channels = []
        inactive_channels = []
        
        for channel_id, metric in metrics.items():
            if metric.overall_score >= 70:
                high_performers.append((channel_id, metric))
            elif metric.monthly_flow > self.HIGH_FLOW_THRESHOLD and metric.monthly_earnings < 1000:
                underperformers.append((channel_id, metric))
            elif metric.local_balance_ratio > self.HIGH_BALANCE_THRESHOLD or metric.local_balance_ratio < self.LOW_BALANCE_THRESHOLD:
                imbalanced_channels.append((channel_id, metric))
            elif metric.monthly_flow < self.LOW_FLOW_THRESHOLD:
                inactive_channels.append((channel_id, metric))
        
        # Generate recommendations for each category
        recommendations.extend(self._optimize_high_performers(high_performers))
        recommendations.extend(self._optimize_underperformers(underperformers))
        recommendations.extend(self._optimize_imbalanced_channels(imbalanced_channels))
        recommendations.extend(self._optimize_inactive_channels(inactive_channels))
        
        # Sort by priority and projected impact
        recommendations.sort(key=lambda r: (
            {"high": 3, "medium": 2, "low": 1}[r.priority],
            r.projected_earnings - r.current_earnings
        ), reverse=True)
        
        return recommendations
    
    def _optimize_high_performers(self, channels: List[Tuple[str, ChannelMetrics]]) -> List[FeeRecommendation]:
        """Optimize high-performing channels - be conservative"""
        recommendations = []
        
        for channel_id, metric in channels:
            current_rate = self._get_current_fee_rate(metric)
            
            # For high performers, only small adjustments
            if metric.flow_efficiency > 0.8 and metric.profitability_score > 80:
                # Perfect channels - minimal increase
                new_rate = min(current_rate * 1.1, self.MAX_FEE_RATE)
                reason = "Excellent performance - minimal fee increase to test demand elasticity"
                confidence = "high"
            elif metric.monthly_flow > self.HIGH_FLOW_THRESHOLD * 5:  # Very high flow
                # High volume channels can handle small increases
                new_rate = min(current_rate * 1.2, self.MAX_FEE_RATE)
                reason = "Very high flow volume supports modest fee increase"
                confidence = "high"
            else:
                continue  # Don't change already good performers
            
            recommendation = FeeRecommendation(
                channel_id=channel_id,
                current_fee_rate=current_rate,
                recommended_fee_rate=int(new_rate),
                reason=reason,
                expected_impact="Increased revenue with minimal flow reduction",
                confidence=confidence,
                priority="low",
                current_earnings=metric.monthly_earnings,
                projected_earnings=metric.monthly_earnings * (new_rate / max(current_rate, 1))
            )
            recommendations.append(recommendation)
        
        return recommendations
    
    def _optimize_underperformers(self, channels: List[Tuple[str, ChannelMetrics]]) -> List[FeeRecommendation]:
        """Optimize underperforming channels - high flow but low fees"""
        recommendations = []
        
        for channel_id, metric in channels:
            current_rate = self._get_current_fee_rate(metric)
            
            # Calculate optimal fee based on flow and market rates
            flow_volume = metric.monthly_flow
            
            if flow_volume > 50_000_000:  # >50M sats flow
                # Very high flow - can support higher fees
                target_rate = max(50, current_rate * self.FEE_INCREASE_FACTOR)
                reason = "Extremely high flow with very low fees - significant opportunity"
                confidence = "high"
                priority = "high"
            elif flow_volume > 20_000_000:  # >20M sats flow
                target_rate = max(30, current_rate * 1.8)
                reason = "High flow volume supports increased fees"
                confidence = "high"
                priority = "high"
            else:
                target_rate = max(20, current_rate * 1.4)
                reason = "Good flow volume allows modest fee increase"
                confidence = "medium"
                priority = "medium"
            
            new_rate = min(target_rate, self.MAX_FEE_RATE)
            
            # Estimate impact based on demand elasticity
            elasticity = self._estimate_demand_elasticity(metric)
            flow_reduction = min(0.3, (new_rate / max(current_rate, 1) - 1) * elasticity)
            projected_flow = flow_volume * (1 - flow_reduction)
            projected_earnings = (projected_flow / 1_000_000) * new_rate  # sats per million * ppm
            
            recommendation = FeeRecommendation(
                channel_id=channel_id,
                current_fee_rate=current_rate,
                recommended_fee_rate=int(new_rate),
                reason=reason,
                expected_impact=f"Estimated {flow_reduction*100:.1f}% flow reduction, {(projected_earnings/metric.monthly_earnings-1)*100:.1f}% earnings increase",
                confidence=confidence,
                priority=priority,
                current_earnings=metric.monthly_earnings,
                projected_earnings=projected_earnings
            )
            recommendations.append(recommendation)
        
        return recommendations
    
    def _optimize_imbalanced_channels(self, channels: List[Tuple[str, ChannelMetrics]]) -> List[FeeRecommendation]:
        """Optimize imbalanced channels to encourage rebalancing"""
        recommendations = []
        
        for channel_id, metric in channels:
            current_rate = self._get_current_fee_rate(metric)
            
            if metric.local_balance_ratio > self.HIGH_BALANCE_THRESHOLD:
                # Too much local balance - reduce fees to encourage outbound flow
                if current_rate > 20:
                    new_rate = max(self.MIN_FEE_RATE, int(current_rate * 0.8))
                    reason = "Reduce fees to encourage outbound flow and rebalance channel"
                    expected_impact = "Increased outbound flow, better channel balance"
                    priority = "medium"
                else:
                    continue  # Already low fees
                    
            elif metric.local_balance_ratio < self.LOW_BALANCE_THRESHOLD:
                # Too little local balance - increase fees to slow outbound flow
                new_rate = min(self.MAX_FEE_RATE, int(current_rate * 1.5))
                reason = "Increase fees to reduce outbound flow and preserve local balance"
                expected_impact = "Reduced outbound flow, better balance preservation"
                priority = "medium"
            else:
                continue
            
            recommendation = FeeRecommendation(
                channel_id=channel_id,
                current_fee_rate=current_rate,
                recommended_fee_rate=new_rate,
                reason=reason,
                expected_impact=expected_impact,
                confidence="medium",
                priority=priority,
                current_earnings=metric.monthly_earnings,
                projected_earnings=metric.monthly_earnings * 0.9  # Conservative estimate
            )
            recommendations.append(recommendation)
        
        return recommendations
    
    def _optimize_inactive_channels(self, channels: List[Tuple[str, ChannelMetrics]]) -> List[FeeRecommendation]:
        """Handle inactive or low-activity channels"""
        recommendations = []
        
        for channel_id, metric in channels:
            current_rate = self._get_current_fee_rate(metric)
            
            if metric.monthly_flow == 0:
                # Completely inactive - try very low fees to attract flow
                new_rate = self.MIN_FEE_RATE
                reason = "Channel is inactive - set minimal fees to attract initial flow"
                priority = "low"
            else:
                # Low activity - modest fee reduction to encourage use
                new_rate = max(self.MIN_FEE_RATE, int(current_rate * 0.7))
                reason = "Low activity - reduce fees to encourage more routing"
                priority = "medium"
            
            if new_rate != current_rate:
                recommendation = FeeRecommendation(
                    channel_id=channel_id,
                    current_fee_rate=current_rate,
                    recommended_fee_rate=new_rate,
                    reason=reason,
                    expected_impact="Potential to activate dormant channel",
                    confidence="low",
                    priority=priority,
                    current_earnings=metric.monthly_earnings,
                    projected_earnings=100  # Conservative estimate for inactive channels
                )
                recommendations.append(recommendation)
        
        return recommendations
    
    def _get_current_fee_rate(self, metric: ChannelMetrics) -> int:
        """Extract current fee rate from channel metrics"""
        return metric.channel.current_fee_rate
    
    def _estimate_demand_elasticity(self, metric: ChannelMetrics) -> float:
        """Estimate demand elasticity based on channel characteristics"""
        # Higher elasticity = more sensitive to price changes
        
        base_elasticity = 0.5  # Conservative baseline
        
        # High-volume routes tend to be less elastic (fewer alternatives)
        if metric.monthly_flow > 50_000_000:
            return 0.2
        elif metric.monthly_flow > 20_000_000:
            return 0.3
        elif metric.monthly_flow > 5_000_000:
            return 0.4
        
        # Low activity channels are more elastic
        if metric.monthly_flow < 1_000_000:
            return 0.8
        
        return base_elasticity
    
    def print_recommendations(self, recommendations: List[FeeRecommendation]):
        """Print optimization recommendations"""
        if not recommendations:
            console.print("[yellow]No optimization recommendations generated[/yellow]")
            return
        
        # Summary panel
        total_current_earnings = sum(r.current_earnings for r in recommendations)
        total_projected_earnings = sum(r.projected_earnings for r in recommendations)
        improvement = ((total_projected_earnings / max(total_current_earnings, 1)) - 1) * 100
        
        summary = f"""
[bold]Optimization Summary[/bold]
Total Recommendations: {len(recommendations)}
Current Monthly Earnings: {total_current_earnings:,.0f} sats
Projected Monthly Earnings: {total_projected_earnings:,.0f} sats
Estimated Improvement: {improvement:+.1f}%
        """
        console.print(Panel(summary.strip(), title="Fee Optimization Results"))
        
        # Detailed recommendations table
        console.print("\n[bold]Detailed Recommendations[/bold]")
        
        # Group by priority
        for priority in ["high", "medium", "low"]:
            priority_recs = [r for r in recommendations if r.priority == priority]
            if not priority_recs:
                continue
                
            console.print(f"\n[cyan]{priority.title()} Priority ({len(priority_recs)} channels):[/cyan]")
            
            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("Channel", width=16)
            table.add_column("Current", justify="right")
            table.add_column("→", justify="center", width=3)
            table.add_column("Recommended", justify="right")
            table.add_column("Change", justify="right")
            table.add_column("Reason", width=30)
            table.add_column("Impact", width=20)
            
            for rec in priority_recs[:10]:  # Show top 10 per priority
                change_color = "green" if rec.recommended_fee_rate > rec.current_fee_rate else "red"
                change_text = f"[{change_color}]{rec.fee_change_pct:+.0f}%[/{change_color}]"
                
                table.add_row(
                    rec.channel_id[:16] + "...",
                    f"{rec.current_fee_rate}",
                    "→",
                    f"{rec.recommended_fee_rate}",
                    change_text,
                    rec.reason[:30] + "..." if len(rec.reason) > 30 else rec.reason,
                    rec.expected_impact[:20] + "..." if len(rec.expected_impact) > 20 else rec.expected_impact
                )
            
            console.print(table)
    
    def save_recommendations(self, recommendations: List[FeeRecommendation], output_path: str):
        """Save recommendations to file"""
        data = []
        for rec in recommendations:
            data.append({
                'channel_id': rec.channel_id,
                'current_fee_rate': rec.current_fee_rate,
                'recommended_fee_rate': rec.recommended_fee_rate,
                'fee_change_pct': rec.fee_change_pct,
                'reason': rec.reason,
                'expected_impact': rec.expected_impact,
                'confidence': rec.confidence,
                'priority': rec.priority,
                'current_earnings': rec.current_earnings,
                'projected_earnings': rec.projected_earnings
            })
        
        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2)