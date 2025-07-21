"""Channel performance analyzer"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import numpy as np
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from ..api.client import LndManageClient
from ..models.channel import Channel
from ..utils.config import Config

logger = logging.getLogger(__name__)
console = Console()


class ChannelMetrics:
    """Calculated metrics for a channel"""
    
    def __init__(self, channel: Channel):
        self.channel = channel
        self.calculate_metrics()
    
    def calculate_metrics(self):
        """Calculate all channel metrics"""
        # Basic metrics
        self.capacity = self.channel.capacity_sat_int
        self.local_balance_ratio = self.channel.local_balance_ratio
        
        # Flow metrics
        if self.channel.flow_report:
            self.monthly_flow = self.channel.total_flow_sats  # Already in sats
            self.flow_direction = "outbound" if self.channel.net_flow_sats < 0 else "inbound"
            self.flow_imbalance = abs(self.channel.net_flow_sats) / max(1, self.monthly_flow)
        else:
            self.monthly_flow = 0
            self.flow_direction = "none"
            self.flow_imbalance = 0
        
        # Fee metrics
        if self.channel.fee_report:
            self.monthly_earnings = self.channel.total_fees_sats  # Already in sats
            self.earnings_per_million = (self.monthly_earnings * 1_000_000) / max(1, self.monthly_flow)
        else:
            self.monthly_earnings = 0
            self.earnings_per_million = 0
        
        # Rebalance metrics
        if self.channel.rebalance_report:
            self.rebalance_costs = self.channel.rebalance_report.net_rebalance_cost / 1000  # Convert to sats
            self.net_profit = self.monthly_earnings - self.rebalance_costs
            self.roi = (self.net_profit / max(1, self.rebalance_costs)) if self.rebalance_costs > 0 else float('inf')
        else:
            self.rebalance_costs = 0
            self.net_profit = self.monthly_earnings
            self.roi = float('inf')
        
        # Performance scores
        self.profitability_score = self._calculate_profitability_score()
        self.activity_score = self._calculate_activity_score()
        self.efficiency_score = self._calculate_efficiency_score()
        self.flow_efficiency = self._calculate_flow_efficiency()
        self.overall_score = (self.profitability_score + self.activity_score + self.efficiency_score) / 3
    
    def _calculate_profitability_score(self) -> float:
        """Score based on net profit and ROI (0-100)"""
        if self.net_profit <= 0:
            return 0
        
        # Normalize profit (assume 10k sats/month is excellent)
        profit_score = min(100, (self.net_profit / 10000) * 100)
        
        # ROI score (assume 200% ROI is excellent)
        roi_score = min(100, (self.roi / 2.0) * 100) if self.roi != float('inf') else 100
        
        return (profit_score + roi_score) / 2
    
    def _calculate_activity_score(self) -> float:
        """Score based on flow volume and consistency (0-100)"""
        if self.monthly_flow == 0:
            return 0
        
        # Normalize flow (assume 10M sats/month is excellent)
        flow_score = min(100, (self.monthly_flow / 10_000_000) * 100)
        
        # Balance score (perfect balance = 100)
        balance_score = (1 - self.flow_imbalance) * 100
        
        return (flow_score + balance_score) / 2
    
    def _calculate_efficiency_score(self) -> float:
        """Score based on earnings efficiency (0-100)"""
        # Earnings per million sats routed (assume 1000 ppm is excellent)
        efficiency = min(100, (self.earnings_per_million / 1000) * 100)
        
        # Penalty for high rebalance costs
        if self.monthly_earnings > 0:
            cost_ratio = self.rebalance_costs / self.monthly_earnings
            cost_penalty = max(0, 1 - cost_ratio) * 100
            return (efficiency + cost_penalty) / 2
        
        return efficiency
    
    def _calculate_flow_efficiency(self) -> float:
        """Calculate flow efficiency (how balanced the flow is)"""
        if self.monthly_flow == 0:
            return 0.0
        
        # Perfect efficiency is 0 net flow (balanced bidirectional)
        return 1.0 - (abs(self.channel.net_flow_sats) / self.monthly_flow)


class ChannelAnalyzer:
    """Analyze channel performance and prepare optimization data"""
    
    def __init__(self, client: LndManageClient, config: Config):
        self.client = client
        self.config = config
    
    async def analyze_channels(self, channel_ids: List[str]) -> Dict[str, ChannelMetrics]:
        """Analyze all channels and return metrics"""
        # Fetch all channel data
        channel_data = await self.client.fetch_all_channel_data(channel_ids)
        
        # Convert to Channel models and calculate metrics
        metrics = {}
        for data in channel_data:
            try:
                # Add timestamp if not present
                if 'timestamp' not in data:
                    data['timestamp'] = datetime.utcnow().isoformat()
                
                channel = Channel(**data)
                channel_id = channel.channel_id_compact
                metrics[channel_id] = ChannelMetrics(channel)
                
                logger.debug(f"Analyzed channel {channel_id}: {metrics[channel_id].overall_score:.1f} score")
                
            except Exception as e:
                channel_id = data.get('channelIdCompact', data.get('channel_id', 'unknown'))
                logger.error(f"Failed to analyze channel {channel_id}: {e}")
                logger.debug(f"Channel data keys: {list(data.keys())}")
        
        return metrics
    
    def categorize_channels(self, metrics: Dict[str, ChannelMetrics]) -> Dict[str, List[ChannelMetrics]]:
        """Categorize channels by performance"""
        categories = {
            'high_performers': [],
            'profitable': [],
            'active_unprofitable': [],
            'inactive': [],
            'problematic': []
        }
        
        for channel_metrics in metrics.values():
            if channel_metrics.overall_score >= 70:
                categories['high_performers'].append(channel_metrics)
            elif channel_metrics.net_profit > 100:  # 100 sats profit
                categories['profitable'].append(channel_metrics)
            elif channel_metrics.monthly_flow > 1_000_000:  # 1M sats flow
                categories['active_unprofitable'].append(channel_metrics)
            elif channel_metrics.monthly_flow == 0:
                categories['inactive'].append(channel_metrics)
            else:
                categories['problematic'].append(channel_metrics)
        
        return categories
    
    def print_analysis(self, metrics: Dict[str, ChannelMetrics]):
        """Print analysis results"""
        categories = self.categorize_channels(metrics)
        
        # Summary panel
        total_channels = len(metrics)
        total_capacity = sum(m.capacity for m in metrics.values())
        total_earnings = sum(m.monthly_earnings for m in metrics.values())
        total_costs = sum(m.rebalance_costs for m in metrics.values())
        total_profit = sum(m.net_profit for m in metrics.values())
        
        summary = f"""
[bold]Channel Summary[/bold]
Total Channels: {total_channels}
Total Capacity: {total_capacity:,} sats
Monthly Earnings: {total_earnings:,.0f} sats
Monthly Costs: {total_costs:,.0f} sats
Net Profit: {total_profit:,.0f} sats
        """
        console.print(Panel(summary.strip(), title="Network Overview"))
        
        # Category breakdown
        console.print("\n[bold]Channel Categories[/bold]")
        for category, channels in categories.items():
            if channels:
                console.print(f"\n[cyan]{category.replace('_', ' ').title()}:[/cyan] {len(channels)} channels")
                
                # Top channels in category
                top_channels = sorted(channels, key=lambda x: x.overall_score, reverse=True)[:5]
                table = Table(show_header=True, header_style="bold magenta")
                table.add_column("Channel", style="dim")
                table.add_column("Alias")
                table.add_column("Score", justify="right")
                table.add_column("Profit", justify="right")
                table.add_column("Flow", justify="right")
                
                for ch in top_channels:
                    table.add_row(
                        ch.channel.channel_id_compact[:16] + "..." if len(ch.channel.channel_id_compact) > 16 else ch.channel.channel_id_compact,
                        ch.channel.remote_alias or "Unknown",
                        f"{ch.overall_score:.1f}",
                        f"{ch.net_profit:,.0f}",
                        f"{ch.monthly_flow/1_000_000:.1f}M"
                    )
                
                console.print(table)