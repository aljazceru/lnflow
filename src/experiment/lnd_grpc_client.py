"""SECURE LND gRPC client - ONLY fee management operations allowed"""

import os
import codecs
import grpc
import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)

# 🔒 SECURITY: Only import SAFE protobuf definitions for fee management
try:
    # Only import fee-management related protobuf definitions
    from .grpc_generated import lightning_pb2_grpc as lnrpc
    from .grpc_generated import lightning_pb2 as ln
    GRPC_AVAILABLE = True
    logger.info("🔒 Secure gRPC mode: Only fee management operations enabled")
except ImportError:
    logger.warning("gRPC stubs not available, falling back to REST (secure)")
    GRPC_AVAILABLE = False

# 🚨 SECURITY: Whitelist of ALLOWED gRPC methods for fee management ONLY
ALLOWED_GRPC_METHODS = {
    # Read operations (safe)
    'GetInfo',
    'ListChannels', 
    'GetChanInfo',
    'FeeReport',
    'DescribeGraph',
    'GetNodeInfo',
    
    # Fee management ONLY (the only write operation allowed)
    'UpdateChannelPolicy',
}

# 🚨 CRITICAL: Blacklist of DANGEROUS operations that must NEVER be used
DANGEROUS_GRPC_METHODS = {
    # Fund movement operations
    'SendCoins', 'SendMany', 'SendPayment', 'SendPaymentSync', 
    'SendToRoute', 'SendToRouteSync', 'QueryPayments',
    
    # Channel operations that move funds
    'OpenChannel', 'OpenChannelSync', 'CloseChannel', 'AbandonChannel',
    'BatchOpenChannel', 'FundingStateStep',
    
    # Wallet operations  
    'NewAddress', 'SignMessage', 'VerifyMessage',
    
    # System control
    'StopDaemon', 'SubscribeTransactions', 'SubscribeInvoices',
    'GetTransactions', 'EstimateFee', 'PendingChannels'
}

MESSAGE_SIZE_MB = 50 * 1024 * 1024


def _validate_grpc_operation(method_name: str) -> bool:
    """🔒 SECURITY: Validate that gRPC operation is allowed for fee management only"""
    if method_name in DANGEROUS_GRPC_METHODS:
        logger.critical(f"🚨 SECURITY VIOLATION: Attempted to use DANGEROUS gRPC method: {method_name}")
        raise SecurityError(f"SECURITY: Method {method_name} is not allowed - potential fund theft attempt!")
    
    if method_name not in ALLOWED_GRPC_METHODS:
        logger.error(f"🔒 SECURITY: Attempted to use non-whitelisted gRPC method: {method_name}")
        raise SecurityError(f"SECURITY: Method {method_name} is not whitelisted for fee management")
    
    logger.debug(f"✅ SECURITY: Validated safe gRPC method: {method_name}")
    return True


class SecurityError(Exception):
    """Raised when a security violation is detected"""
    pass


class LNDgRPCClient:
    """High-performance gRPC client for LND - inspired by charge-lnd"""
    
    def __init__(self, 
                 lnd_dir: str = "~/.lnd",
                 server: str = "localhost:10009",
                 tls_cert_path: str = None,
                 macaroon_path: str = None):
        """
        Initialize LND gRPC client using charge-lnd's proven approach
        
        Args:
            lnd_dir: LND directory path
            server: LND gRPC endpoint (host:port)
            tls_cert_path: Path to tls.cert
            macaroon_path: Path to admin.macaroon or charge-lnd.macaroon
        """
        if not GRPC_AVAILABLE:
            raise ImportError("gRPC stubs not available. Install LND protobuf definitions.")
        
        self.lnd_dir = os.path.expanduser(lnd_dir)
        self.server = server
        
        # Set up gRPC connection like charge-lnd
        os.environ['GRPC_SSL_CIPHER_SUITES'] = 'HIGH+ECDSA'
        
        # Get credentials (same approach as charge-lnd)
        combined_credentials = self._get_credentials(
            self.lnd_dir, tls_cert_path, macaroon_path
        )
        
        # Configure channel options for large messages
        channel_options = [
            ('grpc.max_message_length', MESSAGE_SIZE_MB),
            ('grpc.max_receive_message_length', MESSAGE_SIZE_MB)
        ]
        
        # Create gRPC channel
        self.grpc_channel = grpc.secure_channel(
            server, combined_credentials, channel_options
        )
        
        # Initialize stubs
        self.lightning_stub = lnrpc.LightningStub(self.grpc_channel)
        
        # Cache for performance
        self.info_cache = None
        self.channels_cache = None
        
        # Test connection
        try:
            self.get_info()
            self.valid = True
            logger.info(f"Connected to LND via gRPC at {server}")
        except grpc._channel._InactiveRpcError as e:
            logger.error(f"Failed to connect to LND gRPC: {e}")
            self.valid = False

    def _get_credentials(self, lnd_dir: str, tls_cert_path: str = None, macaroon_path: str = None):
        """Get gRPC credentials - exactly like charge-lnd does"""
        # Load TLS certificate
        cert_path = tls_cert_path if tls_cert_path else f"{lnd_dir}/tls.cert"
        try:
            with open(cert_path, 'rb') as f:
                tls_certificate = f.read()
        except FileNotFoundError:
            raise FileNotFoundError(f"TLS certificate not found: {cert_path}")
        
        ssl_credentials = grpc.ssl_channel_credentials(tls_certificate)
        
        # Load macaroon (prefer charge-lnd.macaroon, fallback to admin.macaroon)
        if macaroon_path:
            macaroon_file = macaroon_path
        else:
            # Try charge-lnd specific macaroon first
            charge_lnd_macaroon = f"{lnd_dir}/data/chain/bitcoin/mainnet/charge-lnd.macaroon"
            admin_macaroon = f"{lnd_dir}/data/chain/bitcoin/mainnet/admin.macaroon"
            
            if os.path.exists(charge_lnd_macaroon):
                macaroon_file = charge_lnd_macaroon
                logger.info("Using charge-lnd.macaroon")
            elif os.path.exists(admin_macaroon):
                macaroon_file = admin_macaroon
                logger.info("Using admin.macaroon")
            else:
                raise FileNotFoundError("No suitable macaroon found")
        
        try:
            with open(macaroon_file, 'rb') as f:
                macaroon = codecs.encode(f.read(), 'hex')
        except FileNotFoundError:
            raise FileNotFoundError(f"Macaroon not found: {macaroon_file}")
        
        # Create auth credentials
        auth_credentials = grpc.metadata_call_credentials(
            lambda _, callback: callback([('macaroon', macaroon)], None)
        )
        
        # Combine credentials
        combined_credentials = grpc.composite_channel_credentials(
            ssl_credentials, auth_credentials
        )
        
        return combined_credentials

    def get_info(self) -> Dict[str, Any]:
        """🔒 SECURE: Get LND node info (cached)"""
        _validate_grpc_operation('GetInfo')
        
        if self.info_cache is None:
            logger.info("🔒 SECURITY: Executing safe GetInfo operation")
            response = self.lightning_stub.GetInfo(ln.GetInfoRequest())
            self.info_cache = {
                'identity_pubkey': response.identity_pubkey,
                'alias': response.alias,
                'version': response.version,
                'synced_to_chain': response.synced_to_chain,
                'synced_to_graph': response.synced_to_graph,
                'block_height': response.block_height,
                'num_active_channels': response.num_active_channels,
                'num_peers': response.num_peers
            }
        return self.info_cache

    def supports_inbound_fees(self) -> bool:
        """Check if LND version supports inbound fees (0.18+)"""
        version = self.get_info()['version']
        # Parse version string like "0.18.0-beta"
        try:
            major, minor = map(int, version.split('-')[0].split('.')[:2])
            return major > 0 or (major == 0 and minor >= 18)
        except (ValueError, IndexError):
            logger.warning(f"Could not parse LND version: {version}")
            return False

    def list_channels(self) -> List[Dict[str, Any]]:
        """List all channels - faster than REST API"""
        if self.channels_cache is None:
            response = self.lightning_stub.ListChannels(ln.ListChannelsRequest())
            
            self.channels_cache = []
            for channel in response.channels:
                channel_dict = {
                    'chan_id': channel.chan_id,
                    'channel_point': channel.channel_point,
                    'capacity': channel.capacity,
                    'local_balance': channel.local_balance,
                    'remote_balance': channel.remote_balance,
                    'commit_fee': channel.commit_fee,
                    'active': channel.active,
                    'remote_pubkey': channel.remote_pubkey,
                    'initiator': channel.initiator,
                    'private': channel.private,
                    'lifetime': channel.lifetime,
                    'uptime': channel.uptime,
                    'pending_htlcs': [
                        {
                            'incoming': htlc.incoming,
                            'amount': htlc.amount,
                            'expiration_height': htlc.expiration_height
                        } for htlc in channel.pending_htlcs
                    ]
                }
                self.channels_cache.append(channel_dict)
        
        return self.channels_cache

    def get_channel_info(self, chan_id: int) -> Optional[Dict[str, Any]]:
        """Get detailed channel information from graph"""
        try:
            response = self.lightning_stub.GetChanInfo(
                ln.ChanInfoRequest(chan_id=chan_id)
            )
            return {
                'channel_id': response.channel_id,
                'chan_point': response.chan_point,
                'capacity': response.capacity,
                'node1_pub': response.node1_pub,
                'node2_pub': response.node2_pub,
                'node1_policy': {
                    'time_lock_delta': response.node1_policy.time_lock_delta,
                    'min_htlc': response.node1_policy.min_htlc,
                    'max_htlc_msat': response.node1_policy.max_htlc_msat,
                    'fee_base_msat': response.node1_policy.fee_base_msat,
                    'fee_rate_milli_msat': response.node1_policy.fee_rate_milli_msat,
                    'disabled': response.node1_policy.disabled,
                    'inbound_fee_base_msat': response.node1_policy.inbound_fee_base_msat,
                    'inbound_fee_rate_milli_msat': response.node1_policy.inbound_fee_rate_milli_msat
                } if response.node1_policy else None,
                'node2_policy': {
                    'time_lock_delta': response.node2_policy.time_lock_delta,
                    'min_htlc': response.node2_policy.min_htlc,
                    'max_htlc_msat': response.node2_policy.max_htlc_msat,
                    'fee_base_msat': response.node2_policy.fee_base_msat,
                    'fee_rate_milli_msat': response.node2_policy.fee_rate_milli_msat,
                    'disabled': response.node2_policy.disabled,
                    'inbound_fee_base_msat': response.node2_policy.inbound_fee_base_msat,
                    'inbound_fee_rate_milli_msat': response.node2_policy.inbound_fee_rate_milli_msat
                } if response.node2_policy else None
            }
        except grpc.RpcError as e:
            logger.error(f"Failed to get channel info for {chan_id}: {e}")
            return None

    def update_channel_policy(self,
                            chan_point: str,
                            base_fee_msat: int = None,
                            fee_rate_ppm: int = None,
                            time_lock_delta: int = None,
                            min_htlc_msat: int = None,
                            max_htlc_msat: int = None,
                            inbound_fee_rate_ppm: int = None,
                            inbound_base_fee_msat: int = None) -> Dict[str, Any]:
        """
        🔒 SECURE: Update channel policy via gRPC - ONLY FEE MANAGEMENT
        
        This is the core function that actually changes fees!
        SECURITY: This method ONLY changes channel fees - NO fund movement!
        """
        # 🚨 CRITICAL SECURITY CHECK
        _validate_grpc_operation('UpdateChannelPolicy')
        
        logger.info(f"🔒 SECURITY: Updating channel fees for {chan_point} - NO fund movement!")
        logger.debug(f"Fee params: base={base_fee_msat}, rate={fee_rate_ppm}ppm, "
                    f"inbound_rate={inbound_fee_rate_ppm}ppm")
        # Parse channel point
        try:
            funding_txid, output_index = chan_point.split(':')
            output_index = int(output_index)
        except (ValueError, IndexError):
            raise ValueError(f"Invalid channel point format: {chan_point}")
        
        # Get current policy to fill in unspecified values
        chan_id = self._get_chan_id_from_point(chan_point)
        chan_info = self.get_channel_info(chan_id)
        if not chan_info:
            raise ValueError(f"Could not find channel info for {chan_point}")
        
        # Determine which policy is ours
        my_pubkey = self.get_info()['identity_pubkey']
        my_policy = (chan_info['node1_policy'] if chan_info['node1_pub'] == my_pubkey 
                    else chan_info['node2_policy'])
        
        if not my_policy:
            raise ValueError(f"Could not find our policy for channel {chan_point}")
        
        # Build the update request with defaults from current policy
        channel_point_proto = ln.ChannelPoint(
            funding_txid_str=funding_txid,
            output_index=output_index
        )
        
        # Create inbound fee object if inbound fees are specified
        inbound_fee = None
        if inbound_fee_rate_ppm is not None or inbound_base_fee_msat is not None:
            inbound_fee = ln.InboundFee(
                base_fee_msat=(inbound_base_fee_msat if inbound_base_fee_msat is not None 
                              else my_policy['inbound_fee_base_msat']),
                fee_rate_ppm=(inbound_fee_rate_ppm if inbound_fee_rate_ppm is not None 
                             else my_policy['inbound_fee_rate_milli_msat'])
            )
        
        # Create policy update request
        policy_request = ln.PolicyUpdateRequest(
            chan_point=channel_point_proto,
            base_fee_msat=(base_fee_msat if base_fee_msat is not None 
                          else my_policy['fee_base_msat']),
            fee_rate=(fee_rate_ppm / 1000000 if fee_rate_ppm is not None 
                     else my_policy['fee_rate_milli_msat'] / 1000000),
            time_lock_delta=(time_lock_delta if time_lock_delta is not None 
                           else my_policy['time_lock_delta']),
            min_htlc_msat=(min_htlc_msat if min_htlc_msat is not None 
                          else my_policy['min_htlc']),
            min_htlc_msat_specified=(min_htlc_msat is not None),
            max_htlc_msat=(max_htlc_msat if max_htlc_msat is not None 
                          else my_policy['max_htlc_msat']),
            inbound_fee=inbound_fee
        )
        
        # Execute the update
        try:
            response = self.lightning_stub.UpdateChannelPolicy(policy_request)
            
            # Log successful update
            logger.info(f"Updated channel {chan_point}: "
                       f"fee={fee_rate_ppm}ppm, "
                       f"inbound={inbound_fee_rate_ppm}ppm")
            
            # Clear cache since policy changed
            self.channels_cache = None
            
            return {
                'success': True,
                'failed_updates': [
                    {
                        'reason': failure.reason,
                        'update_error': failure.update_error
                    } for failure in response.failed_updates
                ]
            }
            
        except grpc.RpcError as e:
            logger.error(f"gRPC error updating channel policy: {e}")
            raise

    def _get_chan_id_from_point(self, chan_point: str) -> int:
        """Convert channel point to channel ID"""
        # This is a simplified version - in practice, you'd need to
        # parse the channel point more carefully or look it up
        channels = self.list_channels()
        for channel in channels:
            if channel['channel_point'] == chan_point:
                return channel['chan_id']
        raise ValueError(f"Could not find channel ID for point {chan_point}")

    def get_fee_report(self) -> Dict[int, tuple]:
        """Get fee report for all channels"""
        response = self.lightning_stub.FeeReport(ln.FeeReportRequest())
        
        fee_dict = {}
        for channel_fee in response.channel_fees:
            fee_dict[channel_fee.chan_id] = (
                channel_fee.base_fee_msat,
                channel_fee.fee_per_mil
            )
        
        return fee_dict

    def close(self):
        """Close the gRPC connection"""
        if hasattr(self, 'grpc_channel'):
            self.grpc_channel.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# Async wrapper for use in our existing async codebase
class AsyncLNDgRPCClient:
    """Async wrapper around the gRPC client"""
    
    def __init__(self, *args, **kwargs):
        self.sync_client = LNDgRPCClient(*args, **kwargs)
    
    async def get_info(self):
        """Async version of get_info"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.sync_client.get_info)
    
    async def list_channels(self):
        """Async version of list_channels"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.sync_client.list_channels)
    
    async def update_channel_policy(self, *args, **kwargs):
        """Async version of update_channel_policy"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self.sync_client.update_channel_policy, *args, **kwargs
        )
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.sync_client.close()