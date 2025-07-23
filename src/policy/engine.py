"""Advanced Policy-Based Fee Manager - Improved charge-lnd with Inbound Fees"""

import configparser
import logging
import re
from typing import Dict, List, Optional, Any, Tuple, Union
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class FeeStrategy(Enum):
    """Fee calculation strategies"""
    STATIC = "static"
    PROPORTIONAL = "proportional"
    COST_RECOVERY = "cost_recovery"
    ONCHAIN_FEE = "onchain_fee"
    BALANCE_BASED = "balance_based"
    FLOW_BASED = "flow_based"
    REVENUE_MAX = "revenue_max"
    INBOUND_DISCOUNT = "inbound_discount"
    INBOUND_PREMIUM = "inbound_premium"


class PolicyType(Enum):
    """Policy execution types"""
    FINAL = "final"        # Stop processing after match
    NON_FINAL = "non_final"  # Continue processing after match (for defaults)


@dataclass
class FeePolicy:
    """Fee policy with inbound fee support"""
    # Basic fee structure
    base_fee_msat: Optional[int] = None
    fee_ppm: Optional[int] = None
    time_lock_delta: Optional[int] = None
    
    # Inbound fee structure (the key improvement over charge-lnd)
    inbound_base_fee_msat: Optional[int] = None
    inbound_fee_ppm: Optional[int] = None
    
    # Strategy and behavior
    strategy: FeeStrategy = FeeStrategy.STATIC
    policy_type: PolicyType = PolicyType.FINAL
    
    # Limits and constraints
    min_fee_ppm: Optional[int] = None
    max_fee_ppm: Optional[int] = None
    min_inbound_fee_ppm: Optional[int] = None
    max_inbound_fee_ppm: Optional[int] = None
    
    # Advanced features
    enable_auto_rollback: bool = True
    rollback_threshold: float = 0.3  # 30% revenue drop
    learning_enabled: bool = True


@dataclass
class PolicyMatcher:
    """Improved matching criteria (inspired by charge-lnd but more powerful)"""
    
    # Channel criteria
    chan_id: Optional[List[str]] = None
    chan_capacity_min: Optional[int] = None
    chan_capacity_max: Optional[int] = None
    chan_balance_ratio_min: Optional[float] = None
    chan_balance_ratio_max: Optional[float] = None
    chan_age_min_days: Optional[int] = None
    chan_age_max_days: Optional[int] = None
    
    # Node criteria  
    node_id: Optional[List[str]] = None
    node_alias: Optional[List[str]] = None
    node_capacity_min: Optional[int] = None
    
    # Activity criteria (enhanced from charge-lnd)
    activity_level: Optional[List[str]] = None  # inactive, low, medium, high
    flow_7d_min: Optional[int] = None
    flow_7d_max: Optional[int] = None
    revenue_7d_min: Optional[int] = None
    
    # Network criteria (new)
    alternative_routes_min: Optional[int] = None
    peer_fee_ratio_min: Optional[float] = None  # Our fee / peer fee ratio
    peer_fee_ratio_max: Optional[float] = None
    
    # Time-based criteria (new)
    time_of_day: Optional[List[int]] = None  # Hour ranges
    day_of_week: Optional[List[int]] = None  # Day ranges


@dataclass
class PolicyRule:
    """Complete policy rule with matcher and fee policy"""
    name: str
    matcher: PolicyMatcher
    policy: FeePolicy
    priority: int = 100
    enabled: bool = True
    
    # Performance tracking (new feature)
    applied_count: int = 0
    revenue_impact: float = 0.0
    last_applied: Optional[datetime] = None


class InboundFeeStrategy:
    """Advanced inbound fee strategies (major improvement over charge-lnd)"""
    
    @staticmethod
    def calculate_liquidity_discount(local_balance_ratio: float, 
                                   intensity: float = 0.5) -> int:
        """
        Calculate inbound discount based on liquidity needs
        
        High local balance = bigger discount to encourage inbound routing
        Low local balance = smaller discount to preserve balance
        """
        if local_balance_ratio > 0.8:
            # Very high local balance - aggressive discount
            return -int(50 * intensity)
        elif local_balance_ratio > 0.6:
            # High local balance - moderate discount  
            return -int(30 * intensity)
        elif local_balance_ratio > 0.4:
            # Balanced - small discount
            return -int(10 * intensity)
        else:
            # Low local balance - minimal or no discount
            return max(-5, -int(5 * intensity))
    
    @staticmethod
    def calculate_flow_based_inbound(flow_in_7d: int, flow_out_7d: int,
                                   capacity: int) -> int:
        """Calculate inbound fees based on flow patterns"""
        flow_ratio = flow_in_7d / max(flow_out_7d, 1)
        
        if flow_ratio > 2.0:
            # Too much inbound flow - charge premium
            return min(50, int(20 * flow_ratio))
        elif flow_ratio < 0.5:
            # Too little inbound flow - offer discount
            return max(-100, -int(30 * (1 / flow_ratio)))
        else:
            # Balanced flow - neutral
            return 0
    
    @staticmethod
    def calculate_competitive_inbound(our_outbound_fee: int, 
                                    peer_fees: List[int]) -> int:
        """Calculate inbound fees based on competitive landscape"""
        if not peer_fees:
            return 0
            
        avg_peer_fee = sum(peer_fees) / len(peer_fees)
        
        if our_outbound_fee > avg_peer_fee * 1.5:
            # We're expensive - offer inbound discount
            return -int((our_outbound_fee - avg_peer_fee) * 0.3)
        elif our_outbound_fee < avg_peer_fee * 0.7:
            # We're cheap - can charge inbound premium
            return int((avg_peer_fee - our_outbound_fee) * 0.2)
        else:
            # Competitive pricing - neutral inbound
            return 0


class PolicyEngine:
    """Advanced policy-based fee manager"""
    
    def __init__(self, config_file: Optional[str] = None):
        self.rules: List[PolicyRule] = []
        self.defaults: Dict[str, Any] = {}
        self.performance_history: Dict[str, List[Dict]] = {}
        
        if config_file:
            self.load_config(config_file)
    
    def load_config(self, config_file: str) -> None:
        """Load policy configuration (improved charge-lnd format)"""
        config = configparser.ConfigParser()
        config.read(config_file)
        
        for section_name in config.sections():
            section = config[section_name]
            
            # Parse matcher criteria
            matcher = self._parse_matcher(section)
            
            # Parse fee policy
            policy = self._parse_policy(section)
            
            # Create rule
            rule = PolicyRule(
                name=section_name,
                matcher=matcher,
                policy=policy,
                priority=section.getint('priority', 100),
                enabled=section.getboolean('enabled', True)
            )
            
            self.rules.append(rule)
        
        # Sort rules by priority
        self.rules.sort(key=lambda r: r.priority)
        logger.info(f"Loaded {len(self.rules)} policy rules")
    
    def _parse_matcher(self, section: configparser.SectionProxy) -> PolicyMatcher:
        """Parse matching criteria from config section"""
        matcher = PolicyMatcher()
        
        # Channel criteria
        if 'chan.id' in section:
            matcher.chan_id = [x.strip() for x in section['chan.id'].split(',')]
        if 'chan.min_capacity' in section:
            matcher.chan_capacity_min = section.getint('chan.min_capacity')
        if 'chan.max_capacity' in section:
            matcher.chan_capacity_max = section.getint('chan.max_capacity')
        if 'chan.min_ratio' in section:
            matcher.chan_balance_ratio_min = section.getfloat('chan.min_ratio')
        if 'chan.max_ratio' in section:
            matcher.chan_balance_ratio_max = section.getfloat('chan.max_ratio')
        if 'chan.min_age_days' in section:
            matcher.chan_age_min_days = section.getint('chan.min_age_days')
        
        # Node criteria
        if 'node.id' in section:
            matcher.node_id = [x.strip() for x in section['node.id'].split(',')]
        if 'node.alias' in section:
            matcher.node_alias = [x.strip() for x in section['node.alias'].split(',')]
        if 'node.min_capacity' in section:
            matcher.node_capacity_min = section.getint('node.min_capacity')
        
        # Activity criteria (enhanced)
        if 'activity.level' in section:
            matcher.activity_level = [x.strip() for x in section['activity.level'].split(',')]
        if 'flow.7d.min' in section:
            matcher.flow_7d_min = section.getint('flow.7d.min')
        if 'flow.7d.max' in section:
            matcher.flow_7d_max = section.getint('flow.7d.max')
        
        # Network criteria (new)
        if 'network.min_alternatives' in section:
            matcher.alternative_routes_min = section.getint('network.min_alternatives')
        if 'peer.fee_ratio.min' in section:
            matcher.peer_fee_ratio_min = section.getfloat('peer.fee_ratio.min')
        if 'peer.fee_ratio.max' in section:
            matcher.peer_fee_ratio_max = section.getfloat('peer.fee_ratio.max')
        
        return matcher
    
    def _parse_policy(self, section: configparser.SectionProxy) -> FeePolicy:
        """Parse fee policy from config section"""
        policy = FeePolicy()
        
        # Basic fee structure
        if 'base_fee_msat' in section:
            policy.base_fee_msat = section.getint('base_fee_msat')
        if 'fee_ppm' in section:
            policy.fee_ppm = section.getint('fee_ppm')
        if 'time_lock_delta' in section:
            policy.time_lock_delta = section.getint('time_lock_delta')
        
        # Inbound fee structure (key improvement)
        if 'inbound_base_fee_msat' in section:
            policy.inbound_base_fee_msat = section.getint('inbound_base_fee_msat')
        if 'inbound_fee_ppm' in section:
            policy.inbound_fee_ppm = section.getint('inbound_fee_ppm')
        
        # Strategy
        if 'strategy' in section:
            try:
                policy.strategy = FeeStrategy(section['strategy'])
            except ValueError:
                logger.warning(f"Unknown strategy: {section['strategy']}, using STATIC")
        
        # Policy type
        if 'final' in section:
            policy.policy_type = PolicyType.FINAL if section.getboolean('final') else PolicyType.NON_FINAL
        
        # Limits
        if 'min_fee_ppm' in section:
            policy.min_fee_ppm = section.getint('min_fee_ppm')
        if 'max_fee_ppm' in section:
            policy.max_fee_ppm = section.getint('max_fee_ppm')
        if 'min_inbound_fee_ppm' in section:
            policy.min_inbound_fee_ppm = section.getint('min_inbound_fee_ppm')
        if 'max_inbound_fee_ppm' in section:
            policy.max_inbound_fee_ppm = section.getint('max_inbound_fee_ppm')
        
        # Advanced features
        if 'enable_auto_rollback' in section:
            policy.enable_auto_rollback = section.getboolean('enable_auto_rollback')
        if 'rollback_threshold' in section:
            policy.rollback_threshold = section.getfloat('rollback_threshold')
        if 'learning_enabled' in section:
            policy.learning_enabled = section.getboolean('learning_enabled')
        
        return policy
    
    def match_channel(self, channel_data: Dict[str, Any]) -> List[PolicyRule]:
        """Find matching policies for a channel"""
        matching_rules = []
        channel_id = channel_data.get('channel_id', 'unknown')
        
        logger.debug(f"Evaluating policies for channel {channel_id}:")
        logger.debug(f"  Channel Data: capacity={channel_data.get('capacity', 0):,}, "
                    f"balance_ratio={channel_data.get('local_balance_ratio', 0.5):.2%}, "
                    f"activity={channel_data.get('activity_level', 'unknown')}")
        
        for rule in self.rules:
            if not rule.enabled:
                logger.debug(f"  Skipping disabled policy: {rule.name}")
                continue
                
            if self._channel_matches(channel_data, rule.matcher):
                matching_rules.append(rule)
                logger.debug(f"  ✓ MATCHED policy: {rule.name} (priority {rule.priority})")
                
                # Stop if this is a final policy
                if rule.policy.policy_type == PolicyType.FINAL:
                    logger.debug(f"  Stopping at final policy: {rule.name}")
                    break
            else:
                logger.debug(f"  ✗ SKIPPED policy: {rule.name}")
        
        logger.debug(f"  Final matches for {channel_id}: {[r.name for r in matching_rules]}")
        return matching_rules
    
    def _channel_matches(self, channel_data: Dict[str, Any], matcher: PolicyMatcher) -> bool:
        """Check if channel matches policy criteria with detailed debug logging"""
        
        # Channel ID matching
        if matcher.chan_id:
            channel_id = channel_data.get('channel_id', '')
            if channel_id not in matcher.chan_id:
                logger.debug(f"    ✗ Channel ID mismatch: {channel_id} not in {matcher.chan_id}")
                return False
            logger.debug(f"    ✓ Channel ID matches: {channel_id}")
        
        # Capacity matching
        capacity = channel_data.get('capacity', 0)
        if matcher.chan_capacity_min:
            if capacity < matcher.chan_capacity_min:
                logger.debug(f"    ✗ Capacity too small: {capacity:,} < {matcher.chan_capacity_min:,}")
                return False
            logger.debug(f"    ✓ Capacity min OK: {capacity:,} >= {matcher.chan_capacity_min:,}")
        if matcher.chan_capacity_max:
            if capacity > matcher.chan_capacity_max:
                logger.debug(f"    ✗ Capacity too large: {capacity:,} > {matcher.chan_capacity_max:,}")
                return False
            logger.debug(f"    ✓ Capacity max OK: {capacity:,} <= {matcher.chan_capacity_max:,}")
        
        # Balance ratio matching
        balance_ratio = channel_data.get('local_balance_ratio', 0.5)
        if matcher.chan_balance_ratio_min:
            if balance_ratio < matcher.chan_balance_ratio_min:
                logger.debug(f"    ✗ Balance ratio too low: {balance_ratio:.2%} < {matcher.chan_balance_ratio_min:.2%}")
                return False
            logger.debug(f"    ✓ Balance ratio min OK: {balance_ratio:.2%} >= {matcher.chan_balance_ratio_min:.2%}")
        if matcher.chan_balance_ratio_max:
            if balance_ratio > matcher.chan_balance_ratio_max:
                logger.debug(f"    ✗ Balance ratio too high: {balance_ratio:.2%} > {matcher.chan_balance_ratio_max:.2%}")
                return False
            logger.debug(f"    ✓ Balance ratio max OK: {balance_ratio:.2%} <= {matcher.chan_balance_ratio_max:.2%}")
        
        # Node ID matching
        if matcher.node_id:
            peer_id = channel_data.get('peer_pubkey', '')
            if peer_id not in matcher.node_id:
                logger.debug(f"    ✗ Peer ID mismatch: {peer_id[:16]}... not in target list")
                return False
            logger.debug(f"    ✓ Peer ID matches: {peer_id[:16]}...")
        
        # Activity level matching
        if matcher.activity_level:
            activity = channel_data.get('activity_level', 'inactive')
            if activity not in matcher.activity_level:
                logger.debug(f"    ✗ Activity level mismatch: '{activity}' not in {matcher.activity_level}")
                return False
            logger.debug(f"    ✓ Activity level matches: '{activity}' in {matcher.activity_level}")
        
        # Flow matching
        flow_7d = channel_data.get('flow_7d', 0)
        if matcher.flow_7d_min:
            if flow_7d < matcher.flow_7d_min:
                logger.debug(f"    ✗ Flow too low: {flow_7d:,} < {matcher.flow_7d_min:,}")
                return False
            logger.debug(f"    ✓ Flow min OK: {flow_7d:,} >= {matcher.flow_7d_min:,}")
        if matcher.flow_7d_max:
            if flow_7d > matcher.flow_7d_max:
                logger.debug(f"    ✗ Flow too high: {flow_7d:,} > {matcher.flow_7d_max:,}")
                return False
            logger.debug(f"    ✓ Flow max OK: {flow_7d:,} <= {matcher.flow_7d_max:,}")
        
        logger.debug(f"    ✓ All criteria passed")
        return True
    
    def calculate_fees(self, channel_data: Dict[str, Any]) -> Tuple[int, int, int, int]:
        """
        Calculate optimal fees for a channel
        
        Returns:
            (outbound_fee_ppm, outbound_base_fee, inbound_fee_ppm, inbound_base_fee)
        """
        matching_rules = self.match_channel(channel_data)
        
        if not matching_rules:
            # Use defaults
            return (1000, 0, 0, 0)  # Default values
        
        # Apply policies in order (non-final policies first, then final)
        outbound_fee_ppm = None
        outbound_base_fee = None
        inbound_fee_ppm = None
        inbound_base_fee = None
        
        for rule in matching_rules:
            policy = rule.policy
            
            # Calculate based on strategy
            if policy.strategy == FeeStrategy.STATIC:
                if policy.fee_ppm is not None:
                    outbound_fee_ppm = policy.fee_ppm
                if policy.base_fee_msat is not None:
                    outbound_base_fee = policy.base_fee_msat
                if policy.inbound_fee_ppm is not None:
                    inbound_fee_ppm = policy.inbound_fee_ppm
                if policy.inbound_base_fee_msat is not None:
                    inbound_base_fee = policy.inbound_base_fee_msat
                    
            elif policy.strategy == FeeStrategy.BALANCE_BASED:
                balance_ratio = channel_data.get('local_balance_ratio', 0.5)
                base_fee = policy.fee_ppm or 1000
                
                if balance_ratio > 0.8:
                    # High local balance - reduce fees to encourage outbound
                    outbound_fee_ppm = max(1, int(base_fee * 0.5))
                    inbound_fee_ppm = InboundFeeStrategy.calculate_liquidity_discount(balance_ratio, 1.0)
                elif balance_ratio < 0.2:
                    # Low local balance - increase fees to preserve
                    outbound_fee_ppm = min(5000, int(base_fee * 2.0))
                    inbound_fee_ppm = max(0, int(base_fee * 0.1))
                else:
                    # Balanced
                    outbound_fee_ppm = base_fee
                    inbound_fee_ppm = InboundFeeStrategy.calculate_liquidity_discount(balance_ratio, 0.5)
            
            elif policy.strategy == FeeStrategy.FLOW_BASED:
                flow_in = channel_data.get('flow_in_7d', 0)
                flow_out = channel_data.get('flow_out_7d', 0) 
                capacity = channel_data.get('capacity', 1000000)
                base_fee = policy.fee_ppm or 1000
                
                # Flow-based outbound fee
                flow_utilization = (flow_in + flow_out) / capacity
                if flow_utilization > 0.1:
                    # High utilization - increase fees
                    outbound_fee_ppm = min(5000, int(base_fee * (1 + flow_utilization * 2)))
                else:
                    # Low utilization - decrease fees
                    outbound_fee_ppm = max(1, int(base_fee * 0.7))
                
                # Flow-based inbound fee
                inbound_fee_ppm = InboundFeeStrategy.calculate_flow_based_inbound(flow_in, flow_out, capacity)
            
            elif policy.strategy == FeeStrategy.INBOUND_DISCOUNT:
                # Special strategy focused on inbound fee optimization
                balance_ratio = channel_data.get('local_balance_ratio', 0.5)
                outbound_fee_ppm = policy.fee_ppm or 1000
                inbound_fee_ppm = InboundFeeStrategy.calculate_liquidity_discount(balance_ratio, 1.0)
                
            elif policy.strategy == FeeStrategy.REVENUE_MAX:
                # Data-driven revenue maximization (uses historical performance)
                historical_data = self.performance_history.get(channel_data['channel_id'], [])
                if historical_data:
                    # Find the fee level that generated the most revenue
                    best_performance = max(historical_data, key=lambda x: x.get('revenue_per_day', 0))
                    outbound_fee_ppm = best_performance.get('outbound_fee_ppm', policy.fee_ppm or 1000)
                    inbound_fee_ppm = best_performance.get('inbound_fee_ppm', 0)
                else:
                    # No historical data - use conservative approach
                    outbound_fee_ppm = policy.fee_ppm or 1000
                    inbound_fee_ppm = 0
        
        # Apply limits
        final_rule = matching_rules[-1] if matching_rules else None
        if final_rule:
            policy = final_rule.policy
            
            if policy.min_fee_ppm is not None:
                outbound_fee_ppm = max(outbound_fee_ppm or 0, policy.min_fee_ppm)
            if policy.max_fee_ppm is not None:
                outbound_fee_ppm = min(outbound_fee_ppm or 5000, policy.max_fee_ppm)
            if policy.min_inbound_fee_ppm is not None:
                inbound_fee_ppm = max(inbound_fee_ppm or 0, policy.min_inbound_fee_ppm)
            if policy.max_inbound_fee_ppm is not None:
                inbound_fee_ppm = min(inbound_fee_ppm or 0, policy.max_inbound_fee_ppm)
        
        # Ensure safe inbound fees (cannot make total fee negative)
        if inbound_fee_ppm and inbound_fee_ppm < 0:
            max_discount = -int(outbound_fee_ppm * 0.8)  # Max 80% discount
            inbound_fee_ppm = max(inbound_fee_ppm, max_discount)
        
        return (
            outbound_fee_ppm or 1000,
            outbound_base_fee or 0,
            inbound_fee_ppm or 0,
            inbound_base_fee or 0
        )
    
    def update_performance_history(self, channel_id: str, fee_data: Dict[str, Any], 
                                 performance_data: Dict[str, Any]) -> None:
        """Update performance history for learning-enabled policies"""
        if channel_id not in self.performance_history:
            self.performance_history[channel_id] = []
        
        entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'outbound_fee_ppm': fee_data.get('outbound_fee_ppm'),
            'inbound_fee_ppm': fee_data.get('inbound_fee_ppm'),
            'revenue_per_day': performance_data.get('revenue_msat_per_day', 0),
            'flow_per_day': performance_data.get('flow_msat_per_day', 0),
            'routing_events': performance_data.get('routing_events', 0)
        }
        
        self.performance_history[channel_id].append(entry)
        
        # Keep only last 30 days of history
        cutoff = datetime.utcnow() - timedelta(days=30)
        self.performance_history[channel_id] = [
            e for e in self.performance_history[channel_id]
            if datetime.fromisoformat(e['timestamp']) > cutoff
        ]
    
    def get_policy_performance_report(self) -> Dict[str, Any]:
        """Generate performance report for all policies"""
        report = {
            'policy_performance': [],
            'total_rules': len(self.rules),
            'active_rules': len([r for r in self.rules if r.enabled])
        }
        
        for rule in self.rules:
            if rule.applied_count > 0:
                avg_revenue_impact = rule.revenue_impact / rule.applied_count
                report['policy_performance'].append({
                    'name': rule.name,
                    'applied_count': rule.applied_count,
                    'avg_revenue_impact': avg_revenue_impact,
                    'last_applied': rule.last_applied.isoformat() if rule.last_applied else None,
                    'strategy': rule.policy.strategy.value
                })
        
        return report


def create_sample_config() -> str:
    """Create a sample configuration file showcasing improved features"""
    return """
# Improved charge-lnd configuration with advanced inbound fee support
# This configuration demonstrates the enhanced capabilities over original charge-lnd

[default]
# Non-final policy that sets defaults
final = false
base_fee_msat = 0
fee_ppm = 1000
time_lock_delta = 80
strategy = static

[high-capacity-active]
# High capacity channels that are active get revenue optimization
chan.min_capacity = 5000000
activity.level = high, medium
strategy = revenue_max
fee_ppm = 1500
inbound_fee_ppm = -50
enable_auto_rollback = true
rollback_threshold = 0.2
learning_enabled = true
priority = 10

[balance-drain-channels]
# Channels with too much local balance - encourage outbound routing
chan.min_ratio = 0.8
strategy = balance_based
inbound_fee_ppm = -100
inbound_base_fee_msat = -500
priority = 20

[balance-preserve-channels]
# Channels with low local balance - preserve liquidity
chan.max_ratio = 0.2
strategy = balance_based
fee_ppm = 2000
inbound_fee_ppm = 50
priority = 20

[flow-optimize-channels]
# Channels with good flow patterns - optimize for revenue
flow.7d.min = 1000000
strategy = flow_based
learning_enabled = true
priority = 30

[competitive-channels]
# Channels where we compete with many alternatives
network.min_alternatives = 5
peer.fee_ratio.min = 0.5
peer.fee_ratio.max = 1.5
strategy = inbound_discount
inbound_fee_ppm = -75
priority = 40

[premium-peers]
# Special rates for high-value peers
node.id = 033d8656219478701227199cbd6f670335c8d408a92ae88b962c49d4dc0e83e025
strategy = static
fee_ppm = 500
inbound_fee_ppm = -25
inbound_base_fee_msat = -200
priority = 5

[inactive-channels]
# Inactive channels - aggressive activation strategy
activity.level = inactive
strategy = balance_based
fee_ppm = 100
inbound_fee_ppm = -200
max_fee_ppm = 500
priority = 50

[discourage-routing]
# Channels we want to discourage routing through
chan.max_ratio = 0.1
chan.min_capacity = 250000
strategy = static
base_fee_msat = 0
fee_ppm = 3000
inbound_fee_ppm = 100
priority = 90

[catch-all]
# Final policy for any unmatched channels
strategy = static
fee_ppm = 1000
inbound_fee_ppm = 0
priority = 100
"""