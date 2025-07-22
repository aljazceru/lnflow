"""Policy Manager - Integration with existing Lightning fee optimization system"""

import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from pathlib import Path

from .engine import PolicyEngine, FeeStrategy, PolicyRule
from ..utils.database import ExperimentDatabase
from ..api.client import LndManageClient
from ..experiment.lnd_integration import LNDRestClient
from ..experiment.lnd_grpc_client import AsyncLNDgRPCClient

logger = logging.getLogger(__name__)


class PolicyManager:
    """Manages policy-based fee optimization with inbound fee support"""
    
    def __init__(self, 
                 config_file: str,
                 lnd_manage_url: str,
                 lnd_rest_url: str = "https://localhost:8080",
                 lnd_grpc_host: str = "localhost:10009",
                 lnd_dir: str = "~/.lnd",
                 database_path: str = "experiment_data/policy.db",
                 prefer_grpc: bool = True):
        
        self.policy_engine = PolicyEngine(config_file)
        self.lnd_manage_url = lnd_manage_url
        self.lnd_rest_url = lnd_rest_url
        self.lnd_grpc_host = lnd_grpc_host
        self.lnd_dir = lnd_dir
        self.prefer_grpc = prefer_grpc
        self.db = ExperimentDatabase(database_path)
        
        # Policy-specific tracking
        self.policy_session_id = None
        self.last_fee_changes: Dict[str, Dict] = {}
        self.rollback_candidates: Dict[str, datetime] = {}
        
        logger.info(f"Policy manager initialized with {len(self.policy_engine.rules)} rules")
    
    async def start_policy_session(self, session_name: str = None) -> int:
        """Start a new policy management session"""
        if not session_name:
            session_name = f"policy_session_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        
        self.policy_session_id = self.db.create_experiment(
            start_time=datetime.utcnow(),
            duration_days=999  # Ongoing policy management
        )
        
        logger.info(f"Started policy session {self.policy_session_id}: {session_name}")
        return self.policy_session_id
    
    async def apply_policies(self, dry_run: bool = False,
                           macaroon_path: str = None,
                           cert_path: str = None) -> Dict[str, Any]:
        """Apply policies to all channels"""
        
        if not self.policy_session_id:
            await self.start_policy_session()
        
        results = {
            'channels_processed': 0,
            'policies_applied': 0,
            'fee_changes': 0,
            'errors': [],
            'policy_matches': {},
            'performance_summary': {}
        }
        
        # Get all channel data
        async with LndManageClient(self.lnd_manage_url) as lnd_manage:
            channel_data = await lnd_manage.fetch_all_channel_data()
        
        # Initialize LND client (prefer gRPC, fallback to REST)
        lnd_client = None
        client_type = "unknown"
        
        if not dry_run:
            # Try gRPC first if preferred
            if self.prefer_grpc:
                try:
                    lnd_client = AsyncLNDgRPCClient(
                        lnd_dir=self.lnd_dir,
                        server=self.lnd_grpc_host,
                        macaroon_path=macaroon_path,
                        tls_cert_path=cert_path
                    )
                    await lnd_client.__aenter__()
                    client_type = "gRPC"
                    logger.info(f"Connected to LND via gRPC at {self.lnd_grpc_host}")
                except Exception as e:
                    logger.warning(f"Failed to connect via gRPC: {e}, falling back to REST")
                    lnd_client = None
            
            # Fallback to REST if gRPC failed or not preferred
            if lnd_client is None:
                try:
                    lnd_client = LNDRestClient(
                        lnd_rest_url=self.lnd_rest_url,
                        cert_path=cert_path,
                        macaroon_path=macaroon_path
                    )
                    await lnd_client.__aenter__()
                    client_type = "REST"
                    logger.info(f"Connected to LND via REST at {self.lnd_rest_url}")
                except Exception as e:
                    logger.error(f"Failed to connect to LND (both gRPC and REST failed): {e}")
                    results['errors'].append(f"LND connection failed: {e}")
                    return results
        
        try:
            for channel_info in channel_data:
                results['channels_processed'] += 1
                channel_id = channel_info.get('channelIdCompact')
                
                if not channel_id:
                    continue
                
                try:
                    # Enrich channel data for policy matching
                    enriched_data = await self._enrich_channel_data(channel_info, lnd_manage)
                    
                    # Find matching policies
                    matching_rules = self.policy_engine.match_channel(enriched_data)
                    
                    if not matching_rules:
                        logger.debug(f"No policies matched for channel {channel_id}")
                        continue
                    
                    # Record policy matches
                    results['policy_matches'][channel_id] = [rule.name for rule in matching_rules]
                    results['policies_applied'] += len(matching_rules)
                    
                    # Calculate new fees
                    outbound_fee, outbound_base, inbound_fee, inbound_base = \
                        self.policy_engine.calculate_fees(enriched_data)
                    
                    # Check if fees need to change
                    current_outbound = enriched_data.get('current_outbound_fee', 0)
                    current_inbound = enriched_data.get('current_inbound_fee', 0)
                    
                    if (outbound_fee != current_outbound or inbound_fee != current_inbound):
                        
                        # Apply fee change
                        if dry_run:
                            logger.info(f"[DRY-RUN] Would update {channel_id}: "
                                      f"outbound {current_outbound}→{outbound_fee}ppm, "
                                      f"inbound {current_inbound}→{inbound_fee}ppm")
                        else:
                            success = await self._apply_fee_change(
                                lnd_client, client_type, channel_id, channel_info,
                                outbound_fee, outbound_base, inbound_fee, inbound_base
                            )
                            
                            if success:
                                results['fee_changes'] += 1
                                
                                # Record change in database
                                change_record = {
                                    'timestamp': datetime.utcnow().isoformat(),
                                    'channel_id': channel_id,
                                    'parameter_set': 'policy_based',
                                    'phase': 'active',
                                    'old_fee': current_outbound,
                                    'new_fee': outbound_fee,
                                    'old_inbound': current_inbound,
                                    'new_inbound': inbound_fee,
                                    'reason': f"Policy: {', '.join([r.name for r in matching_rules])}",
                                    'success': True
                                }\
                                
                                self.db.save_fee_change(self.policy_session_id, change_record)
                                
                                # Track for rollback monitoring
                                self.last_fee_changes[channel_id] = {
                                    'timestamp': datetime.utcnow(),
                                    'old_outbound': current_outbound,
                                    'new_outbound': outbound_fee,
                                    'old_inbound': current_inbound,
                                    'new_inbound': inbound_fee,
                                    'policies': [r.name for r in matching_rules]
                                }
                                
                                # Update policy performance tracking
                                for rule in matching_rules:
                                    rule.applied_count += 1
                                    rule.last_applied = datetime.utcnow()
                        
                        # Enhanced logging with detailed channel and policy information
                        peer_alias = enriched_channel.get('peer', {}).get('alias', 'Unknown')
                        capacity_btc = capacity / 100_000_000
                        logger.info(
                            f"Policy applied to {channel_id} [{peer_alias}]:\n"
                            f"  Capacity: {capacity_btc:.3f} BTC ({capacity:,} sats)\n"
                            f"  Balance: {local_balance:,} / {remote_balance:,} (ratio: {balance_ratio:.2%})\n"
                            f"  Policies: {[r.name for r in matching_rules]}\n"
                            f"  Fee Change: {current_outbound} → {outbound_fee}ppm outbound, {current_inbound} → {inbound_fee}ppm inbound\n"
                            f"  Base Fees: {outbound_base}msat outbound, {inbound_base}msat inbound"
                        )
                    
                except Exception as e:
                    error_msg = f"Error processing channel {channel_id}: {e}"
                    logger.error(error_msg)
                    results['errors'].append(error_msg)
        
        finally:
            if lnd_client:
                await lnd_client.__aexit__(None, None, None)
        
        # Generate performance summary
        results['performance_summary'] = self.policy_engine.get_policy_performance_report()
        
        # Enhanced summary logging
        logger.info(
            f"Policy Application Summary:\n"
            f"  Channels Processed: {results.get('channels_processed', 0)}\n"
            f"  Fee Changes Applied: {results['fee_changes']}\n"
            f"  Policies Applied: {results['policies_applied']}\n"
            f"  Errors: {len(results['errors'])}\n"
            f"  Session ID: {results.get('session_id', 'N/A')}"
        )
        
        if results['errors']:
            logger.warning(f"Errors encountered during policy application:")
            for i, error in enumerate(results['errors'][:5], 1):  # Show first 5 errors
                logger.warning(f"  {i}. {error}")
            if len(results['errors']) > 5:
                logger.warning(f"  ... and {len(results['errors']) - 5} more errors")
        
        return results
    
    async def _enrich_channel_data(self, channel_info: Dict[str, Any], 
                                 lnd_manage: LndManageClient) -> Dict[str, Any]:
        """Enrich channel data with additional metrics for policy matching"""
        
        # Extract basic info
        channel_id = channel_info.get('channelIdCompact')
        capacity = int(channel_info.get('capacity', 0)) if channel_info.get('capacity') else 0
        
        logger.debug(f"Processing channel {channel_id}:")
        logger.debug(f"  Raw capacity: {channel_info.get('capacity')}")
        logger.debug(f"  Raw balance info: {channel_info.get('balance', {})}")
        logger.debug(f"  Raw policies: {channel_info.get('policies', {})}")
        logger.debug(f"  Raw peer info: {channel_info.get('peer', {})}")
        
        # Get balance info
        balance_info = channel_info.get('balance', {})
        local_balance = int(balance_info.get('localBalanceSat', 0)) if balance_info.get('localBalanceSat') else 0
        remote_balance = int(balance_info.get('remoteBalanceSat', 0)) if balance_info.get('remoteBalanceSat') else 0
        total_balance = local_balance + remote_balance
        balance_ratio = local_balance / total_balance if total_balance > 0 else 0.5
        
        # Get current fees
        policies = channel_info.get('policies', {})
        local_policy = policies.get('local', {})
        current_outbound_fee = int(local_policy.get('feeRatePpm', 0)) if local_policy.get('feeRatePpm') else 0
        current_inbound_fee = int(local_policy.get('inboundFeeRatePpm', 0)) if local_policy.get('inboundFeeRatePpm') else 0
        
        # Get flow data
        flow_info = channel_info.get('flowReport', {})
        flow_in_7d = int(flow_info.get('forwardedReceivedMilliSat', 0)) if flow_info.get('forwardedReceivedMilliSat') else 0
        flow_out_7d = int(flow_info.get('forwardedSentMilliSat', 0)) if flow_info.get('forwardedSentMilliSat') else 0
        
        # Calculate activity level
        total_flow_7d = flow_in_7d + flow_out_7d
        flow_ratio = total_flow_7d / capacity if capacity > 0 else 0
        
        if flow_ratio > 0.1:
            activity_level = "high"
        elif flow_ratio > 0.01:
            activity_level = "medium"
        elif flow_ratio > 0:
            activity_level = "low"
        else:
            activity_level = "inactive"
        
        # Get peer info
        peer_info = channel_info.get('peer', {})
        peer_pubkey = peer_info.get('pubKey', '')
        peer_alias = peer_info.get('alias', '')
        
        # Get revenue data
        fee_info = channel_info.get('feeReport', {})
        revenue_msat = int(fee_info.get('earnedMilliSat', 0)) if fee_info.get('earnedMilliSat') else 0
        
        # Return enriched data structure
        return {
            'channel_id': channel_id,
            'capacity': capacity,
            'local_balance_ratio': balance_ratio,
            'local_balance': local_balance,
            'remote_balance': remote_balance,
            'current_outbound_fee': current_outbound_fee,
            'current_inbound_fee': current_inbound_fee,
            'flow_in_7d': flow_in_7d,
            'flow_out_7d': flow_out_7d,
            'flow_7d': total_flow_7d,
            'activity_level': activity_level,
            'peer_pubkey': peer_pubkey,
            'peer_alias': peer_alias,
            'revenue_msat': revenue_msat,
            'flow_ratio': flow_ratio,
            
            # Additional calculated metrics
            'revenue_per_capacity': revenue_msat / capacity if capacity > 0 else 0,
            'flow_balance': abs(flow_in_7d - flow_out_7d) / max(flow_in_7d + flow_out_7d, 1),
            
            # Raw data for advanced policies
            'raw_channel_info': channel_info
        }
    
    async def _apply_fee_change(self, lnd_client, client_type: str, channel_id: str,
                              channel_info: Dict[str, Any],
                              outbound_fee: int, outbound_base: int,
                              inbound_fee: int, inbound_base: int) -> bool:
        """Apply fee change via LND API (gRPC preferred, REST fallback)"""
        
        try:
            # Get channel point for LND API
            chan_point = channel_info.get('channelPoint')
            if not chan_point:
                logger.error(f"No channel point found for {channel_id}")
                return False
            
            # Apply the policy using the appropriate client
            if client_type == "gRPC":
                # Use gRPC client - much faster!
                await lnd_client.update_channel_policy(
                    chan_point=chan_point,
                    base_fee_msat=outbound_base,
                    fee_rate_ppm=outbound_fee,
                    inbound_fee_rate_ppm=inbound_fee,
                    inbound_base_fee_msat=inbound_base,
                    time_lock_delta=80
                )
            else:
                # Use REST client as fallback
                await lnd_client.update_channel_policy(
                    chan_point=chan_point,
                    base_fee_msat=outbound_base,
                    fee_rate_ppm=outbound_fee,
                    inbound_fee_rate_ppm=inbound_fee,
                    inbound_base_fee_msat=inbound_base,
                    time_lock_delta=80
                )
            
            logger.info(
                f"Successfully applied fees via {client_type} to {channel_id}:\n"
                f"  Channel Point: {chan_point}\n"
                f"  Outbound: {outbound_fee}ppm (base: {outbound_base}msat)\n"
                f"  Inbound: {inbound_fee}ppm (base: {inbound_base}msat)\n"
                f"  Time Lock Delta: 80"
            )
            return True
            
        except Exception as e:
            logger.error(
                f"Failed to apply fees to {channel_id} via {client_type}:\n"
                f"  Error: {str(e)}\n"
                f"  Channel Point: {chan_point}\n"
                f"  Attempted Parameters:\n"
                f"    Outbound: {outbound_fee}ppm (base: {outbound_base}msat)\n"
                f"    Inbound: {inbound_fee}ppm (base: {inbound_base}msat)\n"
                f"    Time Lock Delta: 80\n"
                f"  Exception Type: {type(e).__name__}"
            )
            return False
    
    async def check_rollback_conditions(self) -> Dict[str, Any]:
        """Check if any channels need rollback due to performance degradation"""
        
        rollback_actions = []
        
        for channel_id, change_info in self.last_fee_changes.items():
            # Only check channels with rollback-enabled policies
            policies_used = change_info.get('policies', [])
            
            # Check if any policy has rollback enabled
            rollback_enabled = False
            rollback_threshold = 0.3  # Default
            
            for rule in self.policy_engine.rules:
                if rule.name in policies_used:
                    if rule.policy.enable_auto_rollback:
                        rollback_enabled = True
                        rollback_threshold = rule.policy.rollback_threshold
                        break
            
            if not rollback_enabled:
                continue
            
            # Check performance since the change
            change_time = change_info['timestamp']
            hours_since_change = (datetime.utcnow() - change_time).total_seconds() / 3600
            
            # Need at least 2 hours of data to assess impact
            if hours_since_change < 2:
                continue
            
            # Get recent performance data
            recent_data = self.db.get_recent_data_points(channel_id, hours=int(hours_since_change))
            
            if len(recent_data) < 2:
                continue
            
            # Calculate performance metrics
            recent_revenue = sum(row['fee_earned_msat'] for row in recent_data[:len(recent_data)//2])
            previous_revenue = sum(row['fee_earned_msat'] for row in recent_data[len(recent_data)//2:])
            
            if previous_revenue > 0:
                revenue_decline = 1 - (recent_revenue / previous_revenue)
                
                if revenue_decline > rollback_threshold:
                    rollback_actions.append({
                        'channel_id': channel_id,
                        'revenue_decline': revenue_decline,
                        'threshold': rollback_threshold,
                        'policies': policies_used,
                        'old_outbound': change_info['old_outbound'],
                        'old_inbound': change_info['old_inbound'],
                        'new_outbound': change_info['new_outbound'],
                        'new_inbound': change_info['new_inbound']
                    })
        
        return {
            'rollback_candidates': len(rollback_actions),
            'actions': rollback_actions
        }
    
    async def execute_rollbacks(self, rollback_actions: List[Dict],
                              lnd_rest: LNDRestClient = None) -> Dict[str, Any]:
        """Execute rollbacks for underperforming channels"""
        
        results = {
            'rollbacks_attempted': 0,
            'rollbacks_successful': 0,
            'errors': []
        }
        
        for action in rollback_actions:
            channel_id = action['channel_id']
            
            try:
                # Apply rollback
                if lnd_rest:
                    # Get channel info for chan_point
                    async with LndManageClient(self.lnd_manage_url) as lnd_manage:
                        channel_details = await lnd_manage.get_channel_details(channel_id)
                        chan_point = channel_details.get('channelPoint')
                        
                        if chan_point:
                            await lnd_rest.update_channel_policy(
                                chan_point=chan_point,
                                fee_rate_ppm=action['old_outbound'],
                                inbound_fee_rate_ppm=action['old_inbound'],
                                base_fee_msat=1000,
                                time_lock_delta=80
                            )
                            
                            results['rollbacks_successful'] += 1
                            
                            # Record rollback
                            rollback_record = {
                                'timestamp': datetime.utcnow().isoformat(),
                                'channel_id': channel_id,
                                'parameter_set': 'policy_rollback',
                                'phase': 'rollback',
                                'old_fee': action['new_outbound'],
                                'new_fee': action['old_outbound'],
                                'old_inbound': action['new_inbound'],
                                'new_inbound': action['old_inbound'],
                                'reason': f"ROLLBACK: Revenue declined {action['revenue_decline']:.1%}",
                                'success': True
                            }
                            
                            self.db.save_fee_change(self.policy_session_id, rollback_record)
                            
                            # Remove from tracking
                            if channel_id in self.last_fee_changes:
                                del self.last_fee_changes[channel_id]
                            
                            logger.info(f"Rolled back channel {channel_id} due to {action['revenue_decline']:.1%} revenue decline")
                
                results['rollbacks_attempted'] += 1
                
            except Exception as e:
                error_msg = f"Failed to rollback channel {channel_id}: {e}"
                logger.error(error_msg)
                results['errors'].append(error_msg)
        
        return results
    
    def get_policy_status(self) -> Dict[str, Any]:
        """Get current policy management status"""
        
        return {
            'session_id': self.policy_session_id,
            'total_rules': len(self.policy_engine.rules),
            'active_rules': len([r for r in self.policy_engine.rules if r.enabled]),
            'channels_with_changes': len(self.last_fee_changes),
            'rollback_candidates': len(self.rollback_candidates),
            'recent_changes': len([
                c for c in self.last_fee_changes.values()
                if (datetime.utcnow() - c['timestamp']).total_seconds() < 24 * 3600
            ]),
            'performance_report': self.policy_engine.get_policy_performance_report()
        }
    
    def save_config_template(self, filepath: str) -> None:
        """Save a sample configuration file"""
        from .engine import create_sample_config
        
        sample_config = create_sample_config()
        
        with open(filepath, 'w') as f:
            f.write(sample_config)
        
        logger.info(f"Sample configuration saved to {filepath}")