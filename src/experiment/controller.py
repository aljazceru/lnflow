"""Experimental controller for Lightning fee optimization testing"""

import asyncio
import logging
import json
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from enum import Enum
import pandas as pd
import numpy as np
from pathlib import Path

from ..api.client import LndManageClient
from ..analysis.analyzer import ChannelMetrics, ChannelAnalyzer
from ..utils.config import Config

logger = logging.getLogger(__name__)


class ParameterSet(Enum):
    """Parameter sets for different optimization strategies"""
    BASELINE = "baseline"           # No changes, measurement only
    CONSERVATIVE = "conservative"   # Conservative balance-based optimization
    AGGRESSIVE = "aggressive"       # Aggressive flow-based optimization  
    ADVANCED = "advanced"           # Advanced multi-strategy optimization
    STABILIZATION = "stabilization" # Final measurement period


class ChannelSegment(Enum):
    """Channel segments based on characteristics (not experiment groups)"""
    HIGH_CAP_ACTIVE = "high_cap_active"       # >5M sats, high activity
    HIGH_CAP_INACTIVE = "high_cap_inactive"   # >5M sats, low activity
    MED_CAP_ACTIVE = "med_cap_active"         # 1-5M sats, active
    MED_CAP_INACTIVE = "med_cap_inactive"     # 1-5M sats, inactive
    LOW_CAP_ACTIVE = "low_cap_active"         # <1M sats, active
    LOW_CAP_INACTIVE = "low_cap_inactive"     # <1M sats, inactive


class ExperimentPhase(Enum):
    """Experiment phases"""
    BASELINE = "baseline"
    INITIAL = "initial" 
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"
    STABILIZATION = "stabilization"
    COMPLETE = "complete"


@dataclass
class ExperimentChannel:
    """Channel configuration for experiment"""
    channel_id: str
    segment: ChannelSegment  # Channel segment based on characteristics
    baseline_fee_rate: int
    baseline_inbound_fee: int
    current_fee_rate: int
    current_inbound_fee: int
    capacity_sat: int        # Actual capacity in sats
    monthly_flow_msat: int   # Monthly flow volume
    peer_pubkey: str         # Peer public key for competitive analysis
    original_metrics: Optional[Dict] = None
    change_history: List[Dict] = None
    
    def __post_init__(self):
        if self.change_history is None:
            self.change_history = []
    
    @property
    def capacity_tier(self) -> str:
        """Backward compatibility property"""
        if self.capacity_sat > 5_000_000:
            return "large"
        elif self.capacity_sat > 1_000_000:
            return "medium"
        else:
            return "small"
    
    @property 
    def activity_level(self) -> str:
        """Backward compatibility property"""
        if self.monthly_flow_msat > 10_000_000:
            return "high"
        elif self.monthly_flow_msat > 1_000_000:
            return "medium"
        elif self.monthly_flow_msat > 0:
            return "low"
        else:
            return "inactive"


@dataclass
class ExperimentDataPoint:
    """Single data collection point"""
    timestamp: datetime
    experiment_hour: int
    channel_id: str
    segment: ChannelSegment     # Channel segment
    parameter_set: ParameterSet # Active parameter set at this time
    phase: ExperimentPhase      # Experiment phase
    
    # Fee policy
    outbound_fee_rate: int
    inbound_fee_rate: int
    base_fee_msat: int
    
    # Balance metrics
    local_balance_sat: int
    remote_balance_sat: int
    local_balance_ratio: float
    
    # Flow metrics  
    forwarded_in_msat: int = 0
    forwarded_out_msat: int = 0
    fee_earned_msat: int = 0
    routing_events: int = 0
    
    # Network context
    peer_fee_rates: List[int] = None
    alternative_routes: int = 0
    
    # Derived metrics
    revenue_rate_per_hour: float = 0.0
    flow_efficiency: float = 0.0
    balance_health_score: float = 0.0
    
    def __post_init__(self):
        if self.peer_fee_rates is None:
            self.peer_fee_rates = []
        
        # Calculate derived metrics
        total_capacity = self.local_balance_sat + self.remote_balance_sat
        if total_capacity > 0:
            self.local_balance_ratio = self.local_balance_sat / total_capacity
        
        total_flow = self.forwarded_in_msat + self.forwarded_out_msat
        if total_flow > 0:
            self.flow_efficiency = min(self.forwarded_in_msat, self.forwarded_out_msat) / (total_flow / 2)
        
        # Balance health: closer to 50% = higher score
        self.balance_health_score = 1.0 - abs(self.local_balance_ratio - 0.5) * 2


class ExperimentController:
    """Main experiment controller"""
    
    def __init__(self, config: Config, lnd_manage_url: str, lnd_rest_url: Optional[str] = None):
        self.config = config
        self.lnd_manage_url = lnd_manage_url
        self.lnd_rest_url = lnd_rest_url or "http://localhost:8080"
        
        self.experiment_channels: Dict[str, ExperimentChannel] = {}
        self.data_points: List[ExperimentDataPoint] = []
        self.experiment_start: Optional[datetime] = None
        self.current_phase: ExperimentPhase = ExperimentPhase.BASELINE
        
        # Experiment parameters - Sequential parameter testing
        self.PARAMETER_SET_DURATION_HOURS = {
            ParameterSet.BASELINE: 24,        # Day 1: Baseline measurement
            ParameterSet.CONSERVATIVE: 48,    # Days 2-3: Conservative optimization
            ParameterSet.AGGRESSIVE: 48,      # Days 4-5: Aggressive optimization
            ParameterSet.ADVANCED: 48,        # Days 6-7: Advanced multi-strategy
            ParameterSet.STABILIZATION: 24   # Day 8: Final measurement
        }
        self.current_parameter_set: ParameterSet = ParameterSet.BASELINE
        
        # Safety limits
        self.MAX_FEE_INCREASE_PCT = 0.5  # 50%
        self.MAX_FEE_DECREASE_PCT = 0.3  # 30%  
        self.MAX_DAILY_CHANGES = 2
        self.ROLLBACK_REVENUE_THRESHOLD = 0.3  # 30% revenue drop
        self.ROLLBACK_FLOW_THRESHOLD = 0.6     # 60% flow reduction
        
        # Data storage
        self.experiment_data_dir = Path("experiment_data")
        self.experiment_data_dir.mkdir(exist_ok=True)
    
    async def initialize_experiment(self, duration_days: int = 7) -> bool:
        """Initialize experiment with channel assignments and baseline measurement"""
        
        logger.info("Initializing Lightning fee optimization experiment")
        
        # Collect baseline data
        async with LndManageClient(self.lnd_manage_url) as client:
            if not await client.is_synced():
                raise RuntimeError("Node not synced to chain")
            
            # Get all channel data
            channel_data = await client.fetch_all_channel_data()
            
            # Analyze channels for experiment assignment
            analyzer = ChannelAnalyzer(client, self.config)
            metrics = {}
            
            for data in channel_data:
                try:
                    from ..models.channel import Channel
                    if 'timestamp' not in data:
                        data['timestamp'] = datetime.utcnow().isoformat()
                    
                    channel = Channel(**data)
                    channel_id = channel.channel_id_compact
                    # Create simplified metrics from channel data  
                    metrics[channel_id] = {
                        'capacity': 0,  # Will be filled from channel data
                        'monthly_flow': 0,
                        'channel': {
                            'current_fee_rate': 10,
                            'peer_pubkey': 'unknown'
                        }
                    }
                    
                except Exception as e:
                    logger.warning(f"Failed to process channel data: {e}")
                    continue
        
        # Assign channels to segments based on characteristics
        self._assign_channel_segments(metrics)
        
        # Set experiment parameters
        self.experiment_start = datetime.utcnow()
        self.current_phase = ExperimentPhase.BASELINE
        
        logger.info(f"Experiment initialized with {len(self.experiment_channels)} channels")
        logger.info(f"Segments: {self._get_segment_counts()}")
        
        return True
    
    def _assign_channel_segments(self, metrics: Dict[str, Any]) -> None:
        """Assign channels to segments based on characteristics (not random assignment)"""
        
        for channel_id, metric_data in metrics.items():
            capacity = getattr(metric_data, 'capacity', 0)
            monthly_flow = getattr(metric_data, 'monthly_flow', 0)
            current_fee = getattr(metric_data, 'channel', {}).get('current_fee_rate', 10)
            peer_pubkey = getattr(metric_data, 'channel', {}).get('peer_pubkey', 'unknown')
            
            # Determine segment based on capacity and activity
            if capacity > 5_000_000:  # High capacity
                if monthly_flow > 10_000_000:
                    segment = ChannelSegment.HIGH_CAP_ACTIVE
                else:
                    segment = ChannelSegment.HIGH_CAP_INACTIVE
            elif capacity > 1_000_000:  # Medium capacity
                if monthly_flow > 1_000_000:
                    segment = ChannelSegment.MED_CAP_ACTIVE
                else:
                    segment = ChannelSegment.MED_CAP_INACTIVE
            else:  # Low capacity
                if monthly_flow > 100_000:
                    segment = ChannelSegment.LOW_CAP_ACTIVE
                else:
                    segment = ChannelSegment.LOW_CAP_INACTIVE
            
            # Create ExperimentChannel object
            exp_channel = ExperimentChannel(
                channel_id=channel_id,
                segment=segment,
                baseline_fee_rate=current_fee,
                baseline_inbound_fee=0,  # Most channels start with 0 inbound fee
                current_fee_rate=current_fee,
                current_inbound_fee=0,
                capacity_sat=capacity,
                monthly_flow_msat=monthly_flow,
                peer_pubkey=peer_pubkey,
                original_metrics=metric_data
            )
            
            self.experiment_channels[channel_id] = exp_channel
        
        logger.info(f"Assigned {len(self.experiment_channels)} channels to segments")
    
    def _get_segment_counts(self) -> Dict[str, int]:
        """Get channel count by segment"""
        counts = {}
        for segment in ChannelSegment:
            counts[segment.value] = sum(1 for ch in self.experiment_channels.values() if ch.segment == segment)
        return counts
    
    async def run_experiment_cycle(self) -> bool:
        """Run one experiment cycle (data collection + fee adjustments)"""
        
        if not self.experiment_start:
            raise RuntimeError("Experiment not initialized")
        
        current_time = datetime.utcnow()
        experiment_hours = (current_time - self.experiment_start).total_seconds() / 3600
        
        # Determine current parameter set and phase
        hours_elapsed = 0
        for param_set in [ParameterSet.BASELINE, ParameterSet.CONSERVATIVE, ParameterSet.AGGRESSIVE, ParameterSet.ADVANCED, ParameterSet.STABILIZATION]:
            duration = self.PARAMETER_SET_DURATION_HOURS[param_set]
            if experiment_hours < hours_elapsed + duration:
                self.current_parameter_set = param_set
                # Map parameter set to phase for backward compatibility
                phase_mapping = {
                    ParameterSet.BASELINE: ExperimentPhase.BASELINE,
                    ParameterSet.CONSERVATIVE: ExperimentPhase.INITIAL,
                    ParameterSet.AGGRESSIVE: ExperimentPhase.MODERATE,
                    ParameterSet.ADVANCED: ExperimentPhase.AGGRESSIVE,
                    ParameterSet.STABILIZATION: ExperimentPhase.STABILIZATION
                }
                self.current_phase = phase_mapping[param_set]
                break
            hours_elapsed += duration
        else:
            self.current_parameter_set = ParameterSet.STABILIZATION
            self.current_phase = ExperimentPhase.COMPLETE
        
        logger.info(f"Running experiment cycle - Hour {experiment_hours:.1f}, Parameter Set: {self.current_parameter_set.value}, Phase: {self.current_phase.value}")
        
        # Collect current data
        await self._collect_data_point(experiment_hours)
        
        # Apply fee changes based on current parameter set
        if self.current_parameter_set not in [ParameterSet.BASELINE, ParameterSet.STABILIZATION]:
            await self._apply_fee_changes()
        
        # Check safety conditions
        await self._check_safety_conditions()
        
        # Save data
        self._save_experiment_data()
        
        return self.current_phase != ExperimentPhase.COMPLETE
    
    async def _collect_data_point(self, experiment_hours: float) -> None:
        """Collect data point for all channels"""
        
        async with LndManageClient(self.lnd_manage_url) as client:
            for channel_id, exp_channel in self.experiment_channels.items():
                try:
                    # Get current channel data
                    channel_details = await client.get_channel_details(channel_id)
                    
                    # Create data point
                    data_point = ExperimentDataPoint(
                        timestamp=datetime.utcnow(),
                        experiment_hour=int(experiment_hours),
                        channel_id=channel_id,
                        segment=exp_channel.segment,
                        parameter_set=self.current_parameter_set,
                        phase=self.current_phase,
                        outbound_fee_rate=channel_details.get('policies', {}).get('local', {}).get('feeRatePpm', 0),
                        inbound_fee_rate=channel_details.get('policies', {}).get('local', {}).get('inboundFeeRatePpm', 0),
                        base_fee_msat=int(channel_details.get('policies', {}).get('local', {}).get('baseFeeMilliSat', '0')),
                        local_balance_sat=channel_details.get('balance', {}).get('localBalanceSat', 0),
                        remote_balance_sat=channel_details.get('balance', {}).get('remoteBalanceSat', 0),
                        forwarded_in_msat=channel_details.get('flowReport', {}).get('forwardedReceivedMilliSat', 0),
                        forwarded_out_msat=channel_details.get('flowReport', {}).get('forwardedSentMilliSat', 0),
                        fee_earned_msat=channel_details.get('feeReport', {}).get('earnedMilliSat', 0)
                    )
                    
                    self.data_points.append(data_point)
                    
                except Exception as e:
                    logger.error(f"Failed to collect data for channel {channel_id}: {e}")
    
    async def _apply_fee_changes(self) -> None:
        """Apply fee changes based on current parameter set to all appropriate channels"""
        
        changes_applied = 0
        
        for channel_id, exp_channel in self.experiment_channels.items():
            # Check if channel should be optimized with current parameter set
            if await self._should_change_fees(exp_channel):
                new_fees = self._calculate_new_fees(exp_channel)
                
                if new_fees:
                    success = await self._apply_channel_fee_change(channel_id, new_fees)
                    if success:
                        changes_applied += 1
                        
                        # Record change with parameter set info
                        change_record = {
                            'timestamp': datetime.utcnow().isoformat(),
                            'channel_id': channel_id,
                            'parameter_set': self.current_parameter_set.value,
                            'phase': self.current_phase.value,
                            'old_fee': exp_channel.current_fee_rate,
                            'new_fee': new_fees['outbound_fee'],
                            'old_inbound': exp_channel.current_inbound_fee,
                            'new_inbound': new_fees['inbound_fee'],
                            'reason': new_fees['reason'],
                            'success': True
                        }
                        exp_channel.change_history.append(change_record)
                        
                        # Save to database
                        self.db.save_fee_change(self.experiment_id, change_record)
                        
                        # Update current values
                        exp_channel.current_fee_rate = new_fees['outbound_fee']
                        exp_channel.current_inbound_fee = new_fees['inbound_fee']
                        
                        # Update in database
                        self.db.update_channel_fees(self.experiment_id, channel_id, 
                                                   new_fees['outbound_fee'], new_fees['inbound_fee'])
        
        logger.info(f"Applied {changes_applied} fee changes using {self.current_parameter_set.value} parameters")
    
    def _calculate_new_fees(self, exp_channel: ExperimentChannel) -> Optional[Dict[str, Any]]:
        """Calculate new fees based on current parameter set and channel characteristics"""
        
        # Get latest data for channel from database
        recent_data = self.db.get_recent_data_points(exp_channel.channel_id, hours=24)
        if not recent_data:
            return None
        
        # Convert database row to object with needed attributes
        latest_row = recent_data[0]  # Most recent data point
        class LatestData:
            def __init__(self, row):
                self.local_balance_ratio = row['local_balance_ratio']
                
        latest = LatestData(latest_row)
        current_fee = exp_channel.current_fee_rate
        
        # Parameter set based optimization intensity
        intensity_multipliers = {
            ParameterSet.CONSERVATIVE: 0.2,  # Conservative changes
            ParameterSet.AGGRESSIVE: 0.5,    # Aggressive changes
            ParameterSet.ADVANCED: 0.7       # Advanced optimization
        }
        intensity = intensity_multipliers.get(self.current_parameter_set, 0.2)
        
        new_fees = None
        
        if self.current_parameter_set == ParameterSet.CONSERVATIVE:
            # Conservative balance-based optimization for all channels
            new_fees = self._calculate_balance_based_fees(exp_channel, latest, current_fee, intensity)
            
        elif self.current_parameter_set == ParameterSet.AGGRESSIVE:
            # Aggressive flow-based optimization for all channels
            new_fees = self._calculate_flow_based_fees(exp_channel, latest, current_fee, intensity)
            
        elif self.current_parameter_set == ParameterSet.ADVANCED:
            # Advanced multi-strategy based on channel segment
            new_fees = self._calculate_advanced_fees(exp_channel, latest, current_fee, intensity)
        
        return new_fees
    
    def _calculate_balance_based_fees(self, exp_channel: ExperimentChannel, latest: ExperimentDataPoint, 
                                    current_fee: int, intensity: float) -> Optional[Dict[str, Any]]:
        """Balance-focused optimization - improve current fees based on balance state"""
        
        current_inbound = exp_channel.current_inbound_fee
        
        if latest.local_balance_ratio > 0.75:
            # High local balance - improve outbound incentives
            new_outbound = max(1, current_fee - int(50 * intensity))  # Reduce outbound fee
            new_inbound = current_inbound - int(20 * intensity)  # Better inbound discount
            reason = f"[BALANCE] Improve outbound incentives (local={latest.local_balance_ratio:.2f})"
        elif latest.local_balance_ratio < 0.25:
            # Low local balance - improve revenue from what we have
            new_outbound = min(3000, current_fee + int(100 * intensity))  # Increase outbound fee
            new_inbound = current_inbound + int(30 * intensity)  # Charge more for inbound
            reason = f"[BALANCE] Maximize revenue on scarce local balance (local={latest.local_balance_ratio:.2f})"
        else:
            # Well balanced - optimize for revenue based on segment
            if exp_channel.segment in [ChannelSegment.HIGH_CAP_ACTIVE, ChannelSegment.MED_CAP_ACTIVE]:
                new_outbound = current_fee + int(25 * intensity)  # Gradual fee increase
                new_inbound = current_inbound + int(10 * intensity)  # Small inbound fee
                reason = f"[BALANCE] Revenue optimization on balanced {exp_channel.segment.value}"
            else:
                # Try to activate inactive channels
                new_outbound = max(1, current_fee - int(25 * intensity))
                new_inbound = current_inbound - int(15 * intensity)
                reason = f"[BALANCE] Activation incentive for {exp_channel.segment.value}"
        
        # Ensure inbound fees don't go too negative
        new_inbound = max(new_inbound, -100)
        
        return {
            'outbound_fee': new_outbound,
            'inbound_fee': new_inbound,
            'reason': reason
        }
    
    def _calculate_flow_based_fees(self, exp_channel: ExperimentChannel, latest: ExperimentDataPoint,
                                 current_fee: int, intensity: float) -> Optional[Dict[str, Any]]:
        """Flow-focused optimization - improve fees based on activity patterns"""
        
        current_inbound = exp_channel.current_inbound_fee
        
        # Get recent flow data to make informed decisions
        recent_data = self.db.get_recent_data_points(exp_channel.channel_id, hours=24)
        
        if len(recent_data) >= 2:
            recent_flow = sum(row['forwarded_in_msat'] + row['forwarded_out_msat'] for row in recent_data[:3])
            older_flow = sum(row['forwarded_in_msat'] + row['forwarded_out_msat'] for row in recent_data[-2:]) if len(recent_data) > 2 else 0
            flow_trend = "increasing" if recent_flow > older_flow else "decreasing"
        else:
            flow_trend = "unknown"
        
        # Strategy based on channel segment and flow trend
        if exp_channel.segment in [ChannelSegment.HIGH_CAP_ACTIVE, ChannelSegment.MED_CAP_ACTIVE]:
            # Active channels - push fees higher for more revenue
            if flow_trend == "increasing":
                new_outbound = current_fee + int(75 * intensity)  # Significant increase
                new_inbound = current_inbound + int(20 * intensity)
                reason = f"[FLOW] Capitalize on increasing flow in {exp_channel.segment.value}"
            else:
                new_outbound = current_fee + int(35 * intensity)  # Moderate increase
                new_inbound = current_inbound + int(10 * intensity)
                reason = f"[FLOW] Revenue optimization on active {exp_channel.segment.value}"
                
        elif exp_channel.segment in [ChannelSegment.HIGH_CAP_INACTIVE, ChannelSegment.MED_CAP_INACTIVE]:
            # Inactive channels - improve activation incentives
            new_outbound = max(1, current_fee - int(75 * intensity))  # More attractive fees
            new_inbound = current_inbound - int(25 * intensity)  # Better inbound incentives
            reason = f"[FLOW] Improve activation for {exp_channel.segment.value}"
            
        elif exp_channel.segment == ChannelSegment.LOW_CAP_ACTIVE:
            # Small active channels - modest improvements
            new_outbound = current_fee + int(50 * intensity)
            new_inbound = current_inbound + int(15 * intensity)
            reason = f"[FLOW] Revenue boost on small active channel"
            
        else:  # LOW_CAP_INACTIVE
            # Small inactive channels - make them more competitive
            new_outbound = max(1, current_fee - int(30 * intensity))
            new_inbound = current_inbound - int(20 * intensity)
            reason = f"[FLOW] Make small inactive channel more competitive"
        
        # Keep inbound fees reasonable
        new_inbound = max(new_inbound, -150)
        
        return {
            'outbound_fee': new_outbound,
            'inbound_fee': new_inbound,
            'reason': reason
        }
    
    def _calculate_advanced_fees(self, exp_channel: ExperimentChannel, latest: ExperimentDataPoint,
                               current_fee: int, intensity: float) -> Optional[Dict[str, Any]]:
        """Advanced optimization - maximize revenue using all available data"""
        
        current_inbound = exp_channel.current_inbound_fee
        
        # Get performance data to make smart decisions
        recent_data = self.db.get_recent_data_points(exp_channel.channel_id, hours=48)
        
        if len(recent_data) >= 3:
            recent_revenue = sum(row['fee_earned_msat'] for row in recent_data[:5])
            older_revenue = sum(row['fee_earned_msat'] for row in recent_data[-5:]) if len(recent_data) > 5 else 0
            revenue_trend = "improving" if recent_revenue > older_revenue else "declining"
        else:
            revenue_trend = "unknown"
        
        balance_imbalance = abs(latest.local_balance_ratio - 0.5) * 2  # 0-1 scale
        
        # Advanced revenue-maximizing strategy
        if exp_channel.segment == ChannelSegment.HIGH_CAP_ACTIVE:
            if revenue_trend == "improving":
                # Revenue is growing - push fees higher
                new_outbound = current_fee + int(100 * intensity)
                new_inbound = current_inbound + int(25 * intensity)
                reason = f"[ADVANCED] Revenue growing on high-cap active - push fees higher"
            elif balance_imbalance > 0.5:
                # Revenue stable but imbalanced - fix balance for long-term revenue
                if latest.local_balance_ratio > 0.5:
                    new_outbound = current_fee - int(50 * intensity)
                    new_inbound = current_inbound - int(30 * intensity)
                    reason = f"[ADVANCED] Fix balance for sustained revenue (local={latest.local_balance_ratio:.2f})"
                else:
                    new_outbound = current_fee + int(75 * intensity)
                    new_inbound = current_inbound + int(40 * intensity)
                    reason = f"[ADVANCED] Preserve remaining balance for revenue"
            else:
                # Well-balanced and good revenue - optimize carefully
                new_outbound = current_fee + int(50 * intensity)
                new_inbound = current_inbound + int(15 * intensity)
                reason = f"[ADVANCED] Careful revenue optimization on balanced high-cap"
                
        elif exp_channel.segment == ChannelSegment.HIGH_CAP_INACTIVE:
            # High value target - make it profitable
            new_outbound = max(1, current_fee - int(100 * intensity))
            new_inbound = current_inbound - int(50 * intensity)
            reason = f"[ADVANCED] Unlock high-cap inactive potential"
            
        elif "ACTIVE" in exp_channel.segment.value:
            # Other active channels - focus on revenue growth
            if revenue_trend == "improving":
                new_outbound = current_fee + int(75 * intensity)
                new_inbound = current_inbound + int(20 * intensity)
            else:
                new_outbound = current_fee + int(40 * intensity)
                new_inbound = current_inbound + int(10 * intensity)
            reason = f"[ADVANCED] Revenue focus on {exp_channel.segment.value} (trend: {revenue_trend})"
            
        else:
            # Inactive channels - strategic activation
            if balance_imbalance > 0.7:
                # Very imbalanced - use for rebalancing
                new_outbound = max(1, current_fee - int(80 * intensity))
                new_inbound = current_inbound - int(40 * intensity)
                reason = f"[ADVANCED] Strategic rebalancing via {exp_channel.segment.value}"
            else:
                # Gentle activation
                new_outbound = max(1, current_fee - int(40 * intensity))
                new_inbound = current_inbound - int(20 * intensity)
                reason = f"[ADVANCED] Gentle activation of {exp_channel.segment.value}"
        
        # Keep fees within reasonable bounds
        new_outbound = min(new_outbound, 5000)  # Cap at 5000 ppm
        new_inbound = max(new_inbound, -200)    # Don't go too negative
        
        return {
            'outbound_fee': new_outbound,
            'inbound_fee': new_inbound,
            'reason': reason
        }
    
    async def _should_change_fees(self, exp_channel: ExperimentChannel) -> bool:
        """Determine if channel should have fee change"""
        
        # Check daily change limit
        today_changes = [
            change for change in exp_channel.change_history
            if (datetime.utcnow() - datetime.fromisoformat(change['timestamp'])).days == 0
        ]
        
        if len(today_changes) >= self.MAX_DAILY_CHANGES:
            return False
        
        # Only change twice daily at scheduled times
        current_hour = datetime.utcnow().hour
        if current_hour not in [9, 21]:  # 9 AM and 9 PM UTC
            return False
        
        # Check if we changed recently (at least 4 hours gap)
        if exp_channel.change_history:
            last_change = datetime.fromisoformat(exp_channel.change_history[-1]['timestamp'])
            if (datetime.utcnow() - last_change).total_seconds() < 4 * 3600:
                return False
        
        return True
    
    async def _apply_channel_fee_change(self, channel_id: str, new_fees: Dict[str, Any]) -> bool:
        """Apply fee change to channel via LND"""
        
        try:
            # Note: This would need actual LND REST API implementation
            # For now, we'll simulate the change
            logger.info(f"Applying fee change to {channel_id}: {new_fees}")
            
            # In real implementation:
            # await self.lnd_rest_client.update_channel_policy(
            #     chan_id=channel_id,
            #     fee_rate=new_fees['outbound_fee'],
            #     inbound_fee_rate=new_fees['inbound_fee']
            # )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to apply fee change to {channel_id}: {e}")
            return False
    
    async def _check_safety_conditions(self) -> None:
        """Check safety conditions and trigger rollbacks if needed"""
        
        for channel_id, exp_channel in self.experiment_channels.items():
            # All channels are eligible for optimization (no control group)
            
            # Get recent data points
            recent_data = [
                dp for dp in self.data_points 
                if dp.channel_id == channel_id and 
                   (datetime.utcnow() - dp.timestamp).total_seconds() < 4 * 3600
            ]
            
            if len(recent_data) < 2:
                continue
            
            # Check for revenue decline
            recent_revenue = sum(dp.fee_earned_msat for dp in recent_data[-4:])  # Last 4 hours
            baseline_revenue = sum(dp.fee_earned_msat for dp in recent_data[:4])  # First 4 hours
            
            if baseline_revenue > 0:
                revenue_decline = 1 - (recent_revenue / baseline_revenue)
                
                if revenue_decline > self.ROLLBACK_REVENUE_THRESHOLD:
                    logger.warning(f"Revenue decline detected for {channel_id}: {revenue_decline:.1%}")
                    await self._rollback_channel(channel_id, "revenue_decline")
            
            # Check for flow reduction
            recent_flow = sum(dp.forwarded_in_msat + dp.forwarded_out_msat for dp in recent_data[-4:])
            baseline_flow = sum(dp.forwarded_in_msat + dp.forwarded_out_msat for dp in recent_data[:4])
            
            if baseline_flow > 0:
                flow_reduction = 1 - (recent_flow / baseline_flow)
                
                if flow_reduction > self.ROLLBACK_FLOW_THRESHOLD:
                    logger.warning(f"Flow reduction detected for {channel_id}: {flow_reduction:.1%}")
                    await self._rollback_channel(channel_id, "flow_reduction")
    
    async def _rollback_channel(self, channel_id: str, reason: str) -> None:
        """Rollback channel to baseline fees"""
        
        exp_channel = self.experiment_channels.get(channel_id)
        if not exp_channel:
            return
        
        rollback_fees = {
            'outbound_fee': exp_channel.baseline_fee_rate,
            'inbound_fee': exp_channel.baseline_inbound_fee,
            'reason': f'ROLLBACK: {reason}'
        }
        
        success = await self._apply_channel_fee_change(channel_id, rollback_fees)
        
        if success:
            # Record rollback
            rollback_record = {
                'timestamp': datetime.utcnow().isoformat(),
                'phase': self.current_phase.value,
                'old_fee': exp_channel.current_fee_rate,
                'new_fee': exp_channel.baseline_fee_rate,
                'old_inbound': exp_channel.current_inbound_fee,
                'new_inbound': exp_channel.baseline_inbound_fee,
                'reason': f'ROLLBACK: {reason}'
            }
            exp_channel.change_history.append(rollback_record)
            
            exp_channel.current_fee_rate = exp_channel.baseline_fee_rate
            exp_channel.current_inbound_fee = exp_channel.baseline_inbound_fee
            
            logger.info(f"Rolled back channel {channel_id} due to {reason}")
    
    def _load_existing_experiment(self) -> None:
        """Load existing experiment if available"""
        existing = self.db.get_current_experiment()
        if existing:
            self.experiment_id = existing['id']
            self.experiment_start = datetime.fromisoformat(existing['start_time'])
            
            # Load channels
            channels_data = self.db.get_experiment_channels(self.experiment_id)
            for ch_data in channels_data:
                segment = ChannelSegment(ch_data['segment'])
                exp_channel = ExperimentChannel(
                    channel_id=ch_data['channel_id'],
                    segment=segment,
                    baseline_fee_rate=ch_data['baseline_fee_rate'],
                    baseline_inbound_fee=ch_data['baseline_inbound_fee'],
                    current_fee_rate=ch_data['current_fee_rate'],
                    current_inbound_fee=ch_data['current_inbound_fee'],
                    capacity_sat=ch_data['capacity_sat'],
                    monthly_flow_msat=ch_data['monthly_flow_msat'],
                    peer_pubkey=ch_data['peer_pubkey'],
                    original_metrics=json.loads(ch_data['original_metrics']) if ch_data['original_metrics'] else {}
                )
                
                # Load change history
                change_history = self.db.get_channel_change_history(ch_data['channel_id'])
                exp_channel.change_history = change_history
                
                self.experiment_channels[ch_data['channel_id']] = exp_channel
            
            logger.info(f"Loaded existing experiment {self.experiment_id} with {len(self.experiment_channels)} channels")
    
    def _save_experiment_channels(self) -> None:
        """Save channel configurations to database"""
        for channel_id, exp_channel in self.experiment_channels.items():
            channel_data = {
                'channel_id': channel_id,
                'segment': exp_channel.segment.value,
                'capacity_sat': exp_channel.capacity_sat,
                'monthly_flow_msat': exp_channel.monthly_flow_msat,
                'peer_pubkey': exp_channel.peer_pubkey,
                'baseline_fee_rate': exp_channel.baseline_fee_rate,
                'baseline_inbound_fee': exp_channel.baseline_inbound_fee,
                'current_fee_rate': exp_channel.current_fee_rate,
                'current_inbound_fee': exp_channel.current_inbound_fee,
                'original_metrics': exp_channel.original_metrics
            }
            self.db.save_channel(self.experiment_id, channel_data)
    
    def _save_experiment_config(self) -> None:
        """Legacy method - configuration now saved in database"""
        logger.info("Experiment configuration saved to database")
    
    def _save_experiment_data(self) -> None:
        """Save experiment data points"""
        
        # Convert to DataFrame for easy analysis
        data_dicts = [asdict(dp) for dp in self.data_points]
        df = pd.DataFrame(data_dicts)
        
        # Save as CSV
        csv_path = self.experiment_data_dir / "experiment_data.csv"
        df.to_csv(csv_path, index=False)
        
        # Save as JSON for detailed analysis
        json_path = self.experiment_data_dir / "experiment_data.json"
        with open(json_path, 'w') as f:
            json.dump(data_dicts, f, indent=2, default=str)
        
        logger.debug(f"Experiment data saved: {len(self.data_points)} data points")
    
    def generate_experiment_report(self) -> Dict[str, Any]:
        """Generate comprehensive experiment report"""
        
        if not self.data_points:
            return {"error": "No experiment data available"}
        
        df = pd.DataFrame([asdict(dp) for dp in self.data_points])
        
        # Basic statistics
        report = {
            'experiment_summary': {
                'start_time': self.experiment_start.isoformat(),
                'total_data_points': len(self.data_points),
                'total_channels': len(self.experiment_channels),
                'group_distribution': self._get_group_counts(),
                'phases_completed': list(set(dp.phase.value for dp in self.data_points))
            },
            
            'performance_by_group': {},
            'statistical_tests': {},
            'hypothesis_results': {},
            'safety_events': []
        }
        
        # Performance analysis by group
        for group in ExperimentGroup:
            group_data = df[df['group'] == group.value]
            
            if len(group_data) > 0:
                report['performance_by_group'][group.value] = {
                    'avg_revenue_per_hour': group_data['fee_earned_msat'].mean(),
                    'avg_flow_efficiency': group_data['flow_efficiency'].mean(),
                    'avg_balance_health': group_data['balance_health_score'].mean(),
                    'total_fee_changes': len([
                        ch for ch in self.experiment_channels.values()
                        if ch.group == group and len(ch.change_history) > 0
                    ])
                }
        
        # Safety events
        for channel_id, exp_channel in self.experiment_channels.items():
            rollbacks = [
                change for change in exp_channel.change_history 
                if 'ROLLBACK' in change['reason']
            ]
            if rollbacks:
                report['safety_events'].append({
                    'channel_id': channel_id,
                    'group': exp_channel.group.value,
                    'rollback_count': len(rollbacks),
                    'rollback_reasons': [r['reason'] for r in rollbacks]
                })
        
        return report