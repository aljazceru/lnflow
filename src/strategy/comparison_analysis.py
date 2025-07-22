"""Comparison analysis between simple and advanced optimization approaches"""

import logging
from typing import Dict, List
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns

from ..analysis.analyzer import ChannelMetrics
from .optimizer import FeeOptimizer, OptimizationStrategy
from .advanced_optimizer import AdvancedFeeOptimizer
from ..utils.config import Config

logger = logging.getLogger(__name__)
console = Console()


class OptimizationComparison:
    """Compare simple vs advanced optimization approaches"""
    
    def __init__(self, config: Config):
        self.config = config
        self.simple_optimizer = FeeOptimizer(config.optimization, OptimizationStrategy.BALANCED)
        self.advanced_optimizer = AdvancedFeeOptimizer(config, OptimizationStrategy.BALANCED)
    
    def run_comparison(self, metrics: Dict[str, ChannelMetrics]) -> Dict[str, any]:
        """Run both optimizers and compare results"""
        
        console.print("[cyan]Running optimization comparison...[/cyan]")
        
        # Run simple optimization
        console.print("Running simple optimization...")
        simple_recommendations = self.simple_optimizer.optimize_fees(metrics)
        
        # Run advanced optimization  
        console.print("🧠 Running advanced optimization...")
        advanced_recommendations = self.advanced_optimizer.optimize_fees_advanced(metrics)
        
        # Perform comparison analysis
        comparison_results = self._analyze_differences(simple_recommendations, advanced_recommendations)
        
        # Display results
        self._display_comparison(simple_recommendations, advanced_recommendations, comparison_results)
        
        return {
            'simple': simple_recommendations,
            'advanced': advanced_recommendations,
            'comparison': comparison_results
        }
    
    def _analyze_differences(self, simple_recs, advanced_recs) -> Dict[str, any]:
        """Analyze differences between optimization approaches"""
        
        # Create mapping for easy comparison
        simple_map = {rec.channel_id: rec for rec in simple_recs}
        advanced_map = {rec.channel_id: rec for rec in advanced_recs}
        
        differences = []
        revenue_impact = {'simple': 0, 'advanced': 0}
        risk_considerations = 0
        timing_optimizations = 0
        
        # Compare recommendations for same channels
        for channel_id in set(simple_map.keys()).intersection(advanced_map.keys()):
            simple_rec = simple_map[channel_id]
            advanced_rec = advanced_map[channel_id]
            
            fee_diff = advanced_rec.recommended_fee_rate - simple_rec.recommended_fee_rate
            revenue_diff = advanced_rec.projected_earnings - simple_rec.projected_earnings
            
            # Count significant differences
            if abs(fee_diff) > 10:  # Significant fee difference
                differences.append({
                    'channel_id': channel_id,
                    'simple_fee': simple_rec.recommended_fee_rate,
                    'advanced_fee': advanced_rec.recommended_fee_rate,
                    'fee_difference': fee_diff,
                    'simple_revenue': simple_rec.projected_earnings,
                    'advanced_revenue': advanced_rec.projected_earnings,
                    'revenue_difference': revenue_diff,
                    'advanced_reasoning': advanced_rec.reason,
                    'risk_score': getattr(advanced_rec, 'risk_assessment', None)
                })
            
            revenue_impact['simple'] += simple_rec.projected_earnings
            revenue_impact['advanced'] += advanced_rec.projected_earnings
            
            # Count risk and timing considerations
            if hasattr(advanced_rec, 'risk_assessment'):
                risk_considerations += 1
            if hasattr(advanced_rec, 'update_timing') and 'Week' in advanced_rec.update_timing:
                timing_optimizations += 1
        
        return {
            'differences': differences,
            'revenue_impact': revenue_impact,
            'risk_considerations': risk_considerations,
            'timing_optimizations': timing_optimizations,
            'channels_with_different_recommendations': len(differences)
        }
    
    def _display_comparison(self, simple_recs, advanced_recs, comparison) -> None:
        """Display comprehensive comparison results"""
        
        # Summary statistics
        simple_total_revenue = sum(rec.projected_earnings for rec in simple_recs)
        advanced_total_revenue = sum(rec.projected_earnings for rec in advanced_recs)
        revenue_improvement = advanced_total_revenue - simple_total_revenue
        
        # Main comparison panel
        summary_text = f"""
[bold]Optimization Method Comparison[/bold]

Simple Optimizer:
  • Recommendations: {len(simple_recs)}
  • Projected Revenue: {simple_total_revenue:,.0f} sats/month
  • Approach: Rule-based thresholds

Advanced Optimizer:  
  • Recommendations: {len(advanced_recs)}
  • Projected Revenue: {advanced_total_revenue:,.0f} sats/month
  • Additional Revenue: {revenue_improvement:+,.0f} sats/month ({(revenue_improvement/max(simple_total_revenue,1)*100):+.1f}%)
  • Approach: Game theory + risk modeling + network topology

Key Improvements:
  • Risk-adjusted recommendations: {comparison['risk_considerations']} channels
  • Timing optimization: {comparison['timing_optimizations']} channels  
  • Different fee strategies: {comparison['channels_with_different_recommendations']} channels
        """
        
        console.print(Panel(summary_text.strip(), title="Comparison Summary"))
        
        # Detailed differences table
        if comparison['differences']:
            console.print("\n[bold]Significant Strategy Differences[/bold]")
            
            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("Channel", width=16)
            table.add_column("Simple", justify="right")
            table.add_column("Advanced", justify="right") 
            table.add_column("Δ Fee", justify="right")
            table.add_column("Δ Revenue", justify="right")
            table.add_column("Advanced Reasoning", width=40)
            
            for diff in comparison['differences'][:10]:  # Show top 10 differences
                fee_change = diff['fee_difference']
                revenue_change = diff['revenue_difference']
                
                fee_color = "green" if fee_change > 0 else "red"
                revenue_color = "green" if revenue_change > 0 else "red"
                
                table.add_row(
                    diff['channel_id'][:16] + "...",
                    f"{diff['simple_fee']} ppm",
                    f"{diff['advanced_fee']} ppm",
                    f"[{fee_color}]{fee_change:+d}[/{fee_color}]",
                    f"[{revenue_color}]{revenue_change:+,.0f}[/{revenue_color}]",
                    diff['advanced_reasoning'][:40] + "..." if len(diff['advanced_reasoning']) > 40 else diff['advanced_reasoning']
                )
            
            console.print(table)
        
        # Risk analysis comparison
        self._display_risk_analysis(advanced_recs)
        
        # Implementation strategy comparison
        self._display_implementation_comparison(simple_recs, advanced_recs)
    
    def _display_risk_analysis(self, advanced_recs) -> None:
        """Display risk analysis from advanced optimizer"""
        
        if not advanced_recs or not hasattr(advanced_recs[0], 'risk_assessment'):
            return
        
        console.print("\n[bold]Risk Analysis (Advanced Only)[/bold]")
        
        # Risk distribution
        risk_levels = {'low': 0, 'medium': 0, 'high': 0}
        total_risk_score = 0
        
        high_risk_channels = []
        
        for rec in advanced_recs:
            if hasattr(rec, 'risk_assessment') and rec.risk_assessment:
                risk = rec.risk_assessment
                total_risk = (risk.channel_closure_risk + risk.competitive_retaliation + risk.liquidity_lock_risk) / 3
                total_risk_score += total_risk
                
                if total_risk > 0.6:
                    risk_levels['high'] += 1
                    high_risk_channels.append((rec.channel_id, total_risk, rec.projected_earnings - rec.current_earnings))
                elif total_risk > 0.3:
                    risk_levels['medium'] += 1
                else:
                    risk_levels['low'] += 1
        
        avg_risk = total_risk_score / max(len(advanced_recs), 1)
        
        risk_text = f"""
Risk Distribution:
  • Low Risk: {risk_levels['low']} channels
  • Medium Risk: {risk_levels['medium']} channels  
  • High Risk: {risk_levels['high']} channels

Average Risk Score: {avg_risk:.2f} (0-1 scale)
        """
        
        console.print(Panel(risk_text.strip(), title="Risk Assessment"))
        
        # Show high-risk recommendations
        if high_risk_channels:
            console.print("\n[bold red]High-Risk Recommendations[/bold red]")
            
            table = Table(show_header=True)
            table.add_column("Channel")
            table.add_column("Risk Score", justify="right")
            table.add_column("Expected Gain", justify="right")
            table.add_column("Risk-Adjusted Return", justify="right")
            
            for channel_id, risk_score, gain in sorted(high_risk_channels, key=lambda x: x[1], reverse=True)[:5]:
                risk_adj_return = gain / (1 + risk_score)
                table.add_row(
                    channel_id[:16] + "...",
                    f"{risk_score:.2f}",
                    f"{gain:+,.0f}",
                    f"{risk_adj_return:+,.0f}"
                )
            
            console.print(table)
    
    def _display_implementation_comparison(self, simple_recs, advanced_recs) -> None:
        """Compare implementation strategies"""
        
        console.print("\n[bold]Implementation Strategy Comparison[/bold]")
        
        # Simple approach
        simple_text = f"""
[bold]Simple Approach:[/bold]
• Apply all {len(simple_recs)} changes immediately
• No timing considerations
• No risk assessment
• 10-60 min network flooding per change
• Total downtime: {len(simple_recs) * 30} minutes average
        """
        
        # Advanced approach timing analysis
        timing_groups = {}
        if advanced_recs and hasattr(advanced_recs[0], 'update_timing'):
            for rec in advanced_recs:
                timing = getattr(rec, 'update_timing', 'immediate')
                if timing not in timing_groups:
                    timing_groups[timing] = 0
                timing_groups[timing] += 1
        
        timing_summary = []
        for timing, count in sorted(timing_groups.items()):
            timing_summary.append(f"• {timing}: {count} channels")
        
        advanced_text = f"""
[bold]Advanced Approach:[/bold]
{chr(10).join(timing_summary) if timing_summary else "• Immediate: All channels"}
• Risk-based prioritization
• Network disruption minimization
• Competitive timing considerations
• Estimated total benefit increase: {(sum(rec.projected_earnings for rec in advanced_recs) / max(sum(rec.projected_earnings for rec in simple_recs), 1) - 1) * 100:.1f}%
        """
        
        # Side by side comparison
        columns = Columns([
            Panel(simple_text.strip(), title="Simple Strategy"),
            Panel(advanced_text.strip(), title="Advanced Strategy")
        ], equal=True)
        
        console.print(columns)
        
        # Recommendation
        console.print("\n[bold green]Recommendation[/bold green]")
        if len(advanced_recs) > 0 and hasattr(advanced_recs[0], 'risk_assessment'):
            console.print("Use the Advanced Optimizer for:")
            console.print("• Higher total returns with risk management")
            console.print("• Strategic timing to minimize network disruption")
            console.print("• Game-theoretic competitive positioning")
            console.print("• Portfolio-level optimization")
        else:
            console.print("Both approaches are similar for this dataset.")
            console.print("Consider advanced approach for larger, more complex channel portfolios.")