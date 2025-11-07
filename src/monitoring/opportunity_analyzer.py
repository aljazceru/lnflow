"""Routing Opportunity Analyzer - Identify and quantify missed routing opportunities"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple, Protocol
from dataclasses import dataclass
from collections import defaultdict

from .htlc_monitor import HTLCMonitor, ChannelFailureStats, FailureReason

logger = logging.getLogger(__name__)


class LNDManageClient(Protocol):
    """Protocol for LND Manage API client"""
    async def get_channel_details(self, channel_id: str) -> Dict:
        """Get channel details"""
        ...


@dataclass
class MissedOpportunity:
    """Represents a missed routing opportunity on a channel"""
    channel_id: str
    peer_alias: Optional[str] = None
    peer_pubkey: Optional[str] = None

    # Failure statistics
    total_failures: int = 0
    liquidity_failures: int = 0
    fee_failures: int = 0
    failure_rate: float = 0.0

    # Revenue impact
    missed_revenue_sats: float = 0.0
    potential_monthly_revenue_sats: float = 0.0
    missed_volume_sats: float = 0.0

    # Current channel state
    current_capacity_sats: int = 0
    current_local_balance_sats: int = 0
    current_remote_balance_sats: int = 0
    current_outbound_fee_ppm: int = 0
    current_inbound_fee_ppm: int = 0

    # Recommendations
    recommendation_type: str = "unknown"  # rebalance, lower_fees, increase_capacity
    recommended_action: str = ""
    urgency_score: float = 0.0  # 0-100

    def __str__(self):
        return (
            f"Channel {self.channel_id[:16]}... ({self.peer_alias or 'Unknown'})\n"
            f"  Missed Revenue: {self.missed_revenue_sats:.2f} sats "
            f"(potential {self.potential_monthly_revenue_sats:.0f} sats/month)\n"
            f"  Failures: {self.total_failures} "
            f"(liquidity: {self.liquidity_failures}, fees: {self.fee_failures})\n"
            f"  Recommendation: {self.recommended_action} (urgency: {self.urgency_score:.0f}/100)"
        )


class OpportunityAnalyzer:
    """Analyze HTLC data to identify and quantify routing opportunities"""

    def __init__(self,
                 htlc_monitor: HTLCMonitor,
                 lnd_manage_client: Optional[LNDManageClient] = None,
                 min_opportunity_sats: int = 100,
                 analysis_window_hours: int = 24):
        """
        Initialize opportunity analyzer

        Args:
            htlc_monitor: HTLC monitor instance with collected data
            lnd_manage_client: LND Manage API client for channel details
            min_opportunity_sats: Minimum missed sats to consider
            analysis_window_hours: Time window for analysis
        """
        self.htlc_monitor = htlc_monitor
        self.lnd_manage_client = lnd_manage_client
        self.min_opportunity_sats = min_opportunity_sats
        self.analysis_window_hours = analysis_window_hours

    async def analyze_opportunities(self,
                                   include_channel_details: bool = True) -> List[MissedOpportunity]:
        """
        Analyze all channels and identify missed routing opportunities

        Returns:
            List of MissedOpportunity objects sorted by urgency
        """
        opportunities = []

        # Get channels with significant missed opportunities
        top_failures = self.htlc_monitor.get_top_missed_opportunities(limit=50)

        for stats in top_failures:
            opportunity = await self._analyze_channel_opportunity(stats, include_channel_details)
            if opportunity and opportunity.missed_revenue_sats >= self.min_opportunity_sats:
                opportunities.append(opportunity)

        # Sort by urgency score
        opportunities.sort(key=lambda x: x.urgency_score, reverse=True)

        logger.info(f"Found {len(opportunities)} significant routing opportunities")
        return opportunities

    async def _analyze_channel_opportunity(self,
                                          stats: ChannelFailureStats,
                                          include_details: bool) -> Optional[MissedOpportunity]:
        """Analyze a single channel for opportunities"""
        try:
            opportunity = MissedOpportunity(channel_id=stats.channel_id)

            # Basic failure stats
            opportunity.total_failures = stats.failed_forwards
            opportunity.liquidity_failures = stats.liquidity_failures
            opportunity.fee_failures = stats.fee_failures
            opportunity.failure_rate = stats.failure_rate
            opportunity.missed_revenue_sats = stats.missed_revenue_sats
            opportunity.missed_volume_sats = stats.total_missed_amount_msat / 1000

            # Calculate potential monthly revenue (extrapolate from current period)
            hours_monitored = (datetime.now(timezone.utc) - stats.first_seen).total_seconds() / 3600
            if hours_monitored > 0:
                hours_in_month = 24 * 30
                opportunity.potential_monthly_revenue_sats = (
                    stats.missed_revenue_sats * hours_in_month / hours_monitored
                )

            # Get current channel details if available
            if include_details and self.lnd_manage_client:
                await self._enrich_with_channel_details(opportunity)

            # Generate recommendations
            self._generate_recommendations(opportunity, stats)

            return opportunity

        except Exception as e:
            logger.error(f"Error analyzing channel {stats.channel_id}: {e}")
            return None

    async def _enrich_with_channel_details(self, opportunity: MissedOpportunity):
        """Fetch and add current channel details"""
        try:
            channel_data = await self.lnd_manage_client.get_channel_details(opportunity.channel_id)

            # Extract channel state
            if 'capacity' in channel_data:
                opportunity.current_capacity_sats = int(channel_data['capacity'])

            balance = channel_data.get('balance', {})
            if balance:
                opportunity.current_local_balance_sats = int(balance.get('localBalanceSat', 0))
                opportunity.current_remote_balance_sats = int(balance.get('remoteBalanceSat', 0))

            # Extract peer info
            peer = channel_data.get('peer', {})
            if peer:
                opportunity.peer_alias = peer.get('alias')
                opportunity.peer_pubkey = peer.get('pubKey')

            # Extract fee policies
            policies = channel_data.get('policies', {})
            local_policy = policies.get('local', {})
            if local_policy:
                opportunity.current_outbound_fee_ppm = int(local_policy.get('feeRatePpm', 0))
                opportunity.current_inbound_fee_ppm = int(local_policy.get('inboundFeeRatePpm', 0))

        except Exception as e:
            logger.debug(f"Could not enrich channel {opportunity.channel_id}: {e}")

    def _generate_recommendations(self,
                                 opportunity: MissedOpportunity,
                                 stats: ChannelFailureStats):
        """Generate actionable recommendations based on failure patterns"""

        # Calculate urgency score (0-100)
        urgency = 0

        # Factor 1: Missed revenue (0-40 points)
        revenue_score = min(40, (opportunity.missed_revenue_sats / 1000) * 4)
        urgency += revenue_score

        # Factor 2: Failure frequency (0-30 points)
        frequency_score = min(30, stats.failed_forwards / 10 * 30)
        urgency += frequency_score

        # Factor 3: Failure rate (0-30 points)
        rate_score = stats.failure_rate * 30
        urgency += rate_score

        opportunity.urgency_score = min(100, urgency)

        # Determine recommendation type based on failure patterns
        liquidity_ratio = stats.liquidity_failures / max(stats.failed_forwards, 1)
        fee_ratio = stats.fee_failures / max(stats.failed_forwards, 1)

        if liquidity_ratio > 0.6:
            # Primarily liquidity issues
            local_ratio = 0
            if opportunity.current_capacity_sats > 0:
                local_ratio = (
                    opportunity.current_local_balance_sats /
                    opportunity.current_capacity_sats
                )

            if local_ratio < 0.2:
                opportunity.recommendation_type = "rebalance_inbound"
                opportunity.recommended_action = (
                    f"Add inbound liquidity. Current: {local_ratio*100:.0f}% local. "
                    f"Target: 50% for optimal routing."
                )
            elif local_ratio > 0.8:
                opportunity.recommendation_type = "rebalance_outbound"
                opportunity.recommended_action = (
                    f"Add outbound liquidity. Current: {local_ratio*100:.0f}% local. "
                    f"Target: 50% for optimal routing."
                )
            else:
                opportunity.recommendation_type = "increase_capacity"
                potential_monthly = opportunity.potential_monthly_revenue_sats
                opportunity.recommended_action = (
                    f"Channel capacity insufficient for demand. "
                    f"Consider opening additional channel. "
                    f"Potential: {potential_monthly:.0f} sats/month"
                )

        elif fee_ratio > 0.3:
            # Primarily fee issues
            opportunity.recommendation_type = "lower_fees"
            current_fee = opportunity.current_outbound_fee_ppm
            suggested_fee = max(1, int(current_fee * 0.7))  # Reduce by 30%
            missed_monthly = opportunity.potential_monthly_revenue_sats

            opportunity.recommended_action = (
                f"Reduce fees from {current_fee} ppm to ~{suggested_fee} ppm. "
                f"Lost revenue: {missed_monthly:.0f} sats/month due to high fees."
            )

        else:
            # Mixed or unknown
            opportunity.recommendation_type = "investigate"
            opportunity.recommended_action = (
                f"Mixed failure patterns. Review channel manually. "
                f"{stats.failed_forwards} failures, {opportunity.missed_revenue_sats:.0f} sats lost."
            )

    async def get_top_opportunities(self, limit: int = 10) -> List[MissedOpportunity]:
        """Get top N opportunities by urgency"""
        all_opportunities = await self.analyze_opportunities()
        return all_opportunities[:limit]

    async def get_liquidity_opportunities(self) -> List[MissedOpportunity]:
        """Get opportunities that can be solved by rebalancing"""
        all_opportunities = await self.analyze_opportunities()
        return [
            opp for opp in all_opportunities
            if opp.recommendation_type in ('rebalance_inbound', 'rebalance_outbound')
        ]

    async def get_fee_opportunities(self) -> List[MissedOpportunity]:
        """Get opportunities that can be solved by fee adjustments"""
        all_opportunities = await self.analyze_opportunities()
        return [
            opp for opp in all_opportunities
            if opp.recommendation_type == 'lower_fees'
        ]

    async def get_capacity_opportunities(self) -> List[MissedOpportunity]:
        """Get opportunities requiring capacity increases"""
        all_opportunities = await self.analyze_opportunities()
        return [
            opp for opp in all_opportunities
            if opp.recommendation_type == 'increase_capacity'
        ]

    def generate_report(self, opportunities: List[MissedOpportunity]) -> str:
        """Generate a human-readable report of opportunities"""
        if not opportunities:
            return "No significant routing opportunities detected."

        total_missed = sum(opp.missed_revenue_sats for opp in opportunities)
        total_potential = sum(opp.potential_monthly_revenue_sats for opp in opportunities)

        report_lines = [
            "=" * 80,
            "MISSED ROUTING OPPORTUNITIES REPORT",
            "=" * 80,
            f"Analysis Period: Last {self.analysis_window_hours} hours",
            f"Total Missed Revenue: {total_missed:.2f} sats",
            f"Potential Monthly Revenue: {total_potential:.0f} sats/month",
            f"Opportunities Found: {len(opportunities)}",
            "",
            "TOP OPPORTUNITIES (by urgency):",
            "-" * 80,
        ]

        for i, opp in enumerate(opportunities[:10], 1):
            report_lines.extend([
                f"\n{i}. {str(opp)}",
            ])

        # Summary by type
        by_type = defaultdict(list)
        for opp in opportunities:
            by_type[opp.recommendation_type].append(opp)

        report_lines.extend([
            "",
            "=" * 80,
            "SUMMARY BY RECOMMENDATION TYPE:",
            "-" * 80,
        ])

        for rec_type, opps in sorted(by_type.items()):
            total = sum(o.potential_monthly_revenue_sats for o in opps)
            report_lines.append(
                f"{rec_type.upper()}: {len(opps)} channels, "
                f"potential {total:.0f} sats/month"
            )

        report_lines.append("=" * 80)

        return "\n".join(report_lines)

    async def export_opportunities_json(self, opportunities: List[MissedOpportunity]) -> Dict:
        """Export opportunities as JSON-serializable dict"""
        return {
            'analysis_timestamp': datetime.now(timezone.utc).isoformat(),
            'analysis_window_hours': self.analysis_window_hours,
            'total_opportunities': len(opportunities),
            'total_missed_revenue_sats': sum(o.missed_revenue_sats for o in opportunities),
            'total_potential_monthly_sats': sum(o.potential_monthly_revenue_sats for o in opportunities),
            'opportunities': [
                {
                    'channel_id': opp.channel_id,
                    'peer_alias': opp.peer_alias,
                    'peer_pubkey': opp.peer_pubkey,
                    'total_failures': opp.total_failures,
                    'liquidity_failures': opp.liquidity_failures,
                    'fee_failures': opp.fee_failures,
                    'failure_rate': opp.failure_rate,
                    'missed_revenue_sats': opp.missed_revenue_sats,
                    'potential_monthly_revenue_sats': opp.potential_monthly_revenue_sats,
                    'current_capacity_sats': opp.current_capacity_sats,
                    'current_local_balance_sats': opp.current_local_balance_sats,
                    'current_outbound_fee_ppm': opp.current_outbound_fee_ppm,
                    'recommendation_type': opp.recommendation_type,
                    'recommended_action': opp.recommended_action,
                    'urgency_score': opp.urgency_score
                }
                for opp in opportunities
            ]
        }
