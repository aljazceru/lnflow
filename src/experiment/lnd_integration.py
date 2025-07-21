"""LND REST API integration for real-time fee changes during experiments"""

import asyncio
import logging
import json
import base64
from typing import Dict, List, Optional, Any
from pathlib import Path
import httpx
import ssl
from datetime import datetime

logger = logging.getLogger(__name__)


class LNDRestClient:
    """LND REST API client for fee management during experiments"""
    
    def __init__(self, 
                 lnd_rest_url: str = "https://localhost:8080",
                 cert_path: str = None,
                 macaroon_path: str = None,
                 macaroon_hex: str = None):
        """
        Initialize LND REST client
        
        Args:
            lnd_rest_url: LND REST API URL (usually https://localhost:8080)
            cert_path: Path to tls.cert file (optional for localhost)
            macaroon_path: Path to admin.macaroon file
            macaroon_hex: Hex-encoded admin macaroon (alternative to file)
        """
        self.base_url = lnd_rest_url.rstrip('/')
        self.cert_path = cert_path
        
        # Load macaroon
        if macaroon_hex:
            self.macaroon_hex = macaroon_hex
        elif macaroon_path:
            self.macaroon_hex = self._load_macaroon_hex(macaroon_path)
        else:
            # Try default locations
            default_paths = [
                Path.home() / ".lnd" / "data" / "chain" / "bitcoin" / "mainnet" / "admin.macaroon",
                Path("/home/bitcoin/.lnd/data/chain/bitcoin/mainnet/admin.macaroon"),
                Path("./admin.macaroon")
            ]
            
            self.macaroon_hex = None
            for path in default_paths:
                if path.exists():
                    self.macaroon_hex = self._load_macaroon_hex(str(path))
                    break
            
            if not self.macaroon_hex:
                raise ValueError("Could not find admin.macaroon file. Please specify macaroon_path or macaroon_hex")
        
        # Setup SSL context
        self.ssl_context = self._create_ssl_context()
        
        # HTTP client will be created in async context
        self.client: Optional[httpx.AsyncClient] = None
    
    def _load_macaroon_hex(self, macaroon_path: str) -> str:
        """Load macaroon file and convert to hex"""
        try:
            with open(macaroon_path, 'rb') as f:
                macaroon_bytes = f.read()
                return macaroon_bytes.hex()
        except Exception as e:
            raise ValueError(f"Failed to load macaroon from {macaroon_path}: {e}")
    
    def _create_ssl_context(self) -> ssl.SSLContext:
        """Create SSL context for LND connection"""
        context = ssl.create_default_context()
        
        if self.cert_path:
            context.load_verify_locations(self.cert_path)
        else:
            # For localhost, allow self-signed certificates
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        
        return context
    
    async def __aenter__(self):
        """Async context manager entry"""
        self.client = httpx.AsyncClient(
            timeout=30.0,
            verify=self.ssl_context if not self.base_url.startswith('http://') else False
        )
        
        # Test connection
        try:
            info = await self.get_node_info()
            logger.info(f"Connected to LND node: {info.get('alias', 'Unknown')} - {info.get('identity_pubkey', '')[:16]}...")
        except Exception as e:
            logger.error(f"Failed to connect to LND: {e}")
            raise
        
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.client:
            await self.client.aclose()
    
    def _get_headers(self) -> Dict[str, str]:
        """Get HTTP headers with macaroon authentication"""
        return {
            'Grpc-Metadata-macaroon': self.macaroon_hex,
            'Content-Type': 'application/json'
        }
    
    async def _request(self, method: str, endpoint: str, **kwargs) -> Any:
        """Make authenticated request to LND REST API"""
        if not self.client:
            raise RuntimeError("Client not initialized. Use async with statement.")
        
        url = f"{self.base_url}{endpoint}"
        headers = self._get_headers()
        
        logger.debug(f"{method} {url}")
        
        try:
            response = await self.client.request(method, url, headers=headers, **kwargs)
            response.raise_for_status()
            
            if response.headers.get('content-type', '').startswith('application/json'):
                return response.json()
            else:
                return response.text
                
        except httpx.HTTPError as e:
            logger.error(f"LND REST API error: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Response: {e.response.text}")
            raise
    
    async def get_node_info(self) -> Dict[str, Any]:
        """Get node information"""
        return await self._request('GET', '/v1/getinfo')
    
    async def list_channels(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """List all channels"""
        params = {'active_only': 'true' if active_only else 'false'}
        result = await self._request('GET', '/v1/channels', params=params)
        return result.get('channels', [])
    
    async def get_channel_info(self, chan_id: str) -> Dict[str, Any]:
        """Get information about specific channel"""
        return await self._request('GET', f'/v1/graph/edge/{chan_id}')
    
    async def update_channel_policy(self, 
                                  chan_point: str = None,
                                  chan_id: str = None,
                                  base_fee_msat: int = 0,
                                  fee_rate: int = None,
                                  fee_rate_ppm: int = None,
                                  inbound_fee_rate_ppm: int = 0,
                                  inbound_base_fee_msat: int = 0,
                                  time_lock_delta: int = 80,
                                  max_htlc_msat: str = None,
                                  min_htlc_msat: str = "1000") -> Dict[str, Any]:
        """
        Update channel fee policy
        
        Args:
            chan_point: Channel point (funding_txid:output_index)
            chan_id: Channel ID (alternative to chan_point)
            base_fee_msat: Base fee in millisatoshis
            fee_rate: Fee rate in satoshis per million (deprecated)
            fee_rate_ppm: Fee rate in parts per million
            inbound_fee_rate_ppm: Inbound fee rate in ppm
            inbound_base_fee_msat: Inbound base fee in msat
            time_lock_delta: Time lock delta
            max_htlc_msat: Maximum HTLC size
            min_htlc_msat: Minimum HTLC size
        """
        
        if not chan_point and not chan_id:
            raise ValueError("Must specify either chan_point or chan_id")
        
        # If only chan_id provided, try to get chan_point
        if chan_id and not chan_point:
            chan_point = await self._get_chan_point_from_id(chan_id)
        
        # Use fee_rate_ppm if provided, otherwise fee_rate
        if fee_rate_ppm is not None:
            actual_fee_rate = fee_rate_ppm
        elif fee_rate is not None:
            actual_fee_rate = fee_rate
        else:
            raise ValueError("Must specify either fee_rate or fee_rate_ppm")
        
        # Build request payload
        policy_update = {
            "base_fee_msat": str(base_fee_msat),
            "fee_rate": actual_fee_rate,  # LND REST API uses 'fee_rate' for ppm
            "time_lock_delta": time_lock_delta
        }
        
        # Add optional parameters
        if min_htlc_msat:
            policy_update["min_htlc_msat"] = str(min_htlc_msat)
        if max_htlc_msat:
            policy_update["max_htlc_msat"] = str(max_htlc_msat)
        
        # Add inbound fees if non-zero
        if inbound_fee_rate_ppm != 0 or inbound_base_fee_msat != 0:
            policy_update["inbound_fee_rate_ppm"] = inbound_fee_rate_ppm
            policy_update["inbound_base_fee_msat"] = str(inbound_base_fee_msat)
        
        request_payload = {
            "chan_point": {
                "funding_txid_str": chan_point.split(':')[0],
                "output_index": int(chan_point.split(':')[1])
            },
            **policy_update
        }
        
        logger.info(f"Updating channel {chan_point} policy: fee_rate={actual_fee_rate}ppm, inbound={inbound_fee_rate_ppm}ppm")
        
        return await self._request('POST', '/v1/graph/node/update_node_announcement', json=request_payload)
    
    async def _get_chan_point_from_id(self, chan_id: str) -> str:
        """Convert channel ID to channel point"""
        try:
            # List channels and find matching channel
            channels = await self.list_channels(active_only=False)
            
            for channel in channels:
                if channel.get('chan_id') == chan_id:
                    return channel.get('channel_point', '')
            
            # If not found in local channels, try network graph
            try:
                edge_info = await self.get_channel_info(chan_id)
                return edge_info.get('channel_point', '')
            except:
                pass
            
            raise ValueError(f"Could not find channel point for channel ID {chan_id}")
            
        except Exception as e:
            logger.error(f"Failed to get channel point for {chan_id}: {e}")
            raise
    
    async def get_forwarding_events(self, 
                                  start_time: Optional[int] = None,
                                  end_time: Optional[int] = None,
                                  index_offset: int = 0,
                                  max_events: int = 100) -> Dict[str, Any]:
        """Get forwarding events for fee analysis"""
        
        params = {
            'index_offset': str(index_offset),
            'max_events': str(max_events)
        }
        
        if start_time:
            params['start_time'] = str(start_time)
        if end_time:
            params['end_time'] = str(end_time)
        
        return await self._request('GET', '/v1/switch', params=params)
    
    async def get_channel_balance(self) -> Dict[str, Any]:
        """Get channel balance information"""
        return await self._request('GET', '/v1/balance/channels')
    
    async def get_payments(self, 
                          include_incomplete: bool = False,
                          index_offset: int = 0,
                          max_payments: int = 100,
                          reversed: bool = True) -> Dict[str, Any]:
        """Get payment history"""
        
        params = {
            'include_incomplete': 'true' if include_incomplete else 'false',
            'index_offset': str(index_offset),
            'max_payments': str(max_payments),
            'reversed': 'true' if reversed else 'false'
        }
        
        return await self._request('GET', '/v1/payments', params=params)
    
    async def describe_graph(self, include_unannounced: bool = False) -> Dict[str, Any]:
        """Get network graph information"""
        params = {'include_unannounced': 'true' if include_unannounced else 'false'}
        return await self._request('GET', '/v1/graph', params=params)
    
    async def get_network_info(self) -> Dict[str, Any]:
        """Get network information and statistics"""
        return await self._request('GET', '/v1/graph/info')


class ExperimentLNDIntegration:
    """Integration layer between experiment controller and LND"""
    
    def __init__(self, lnd_rest_client: LNDRestClient):
        self.lnd_client = lnd_rest_client
        self.fee_change_log: List[Dict[str, Any]] = []
    
    async def apply_fee_change(self, channel_id: str, outbound_fee: int, inbound_fee: int = 0, reason: str = "") -> bool:
        """Apply fee change with logging and error handling"""
        
        try:
            # Record attempt
            change_record = {
                'timestamp': datetime.utcnow().isoformat(),
                'channel_id': channel_id,
                'outbound_fee_before': None,
                'outbound_fee_after': outbound_fee,
                'inbound_fee_before': None,
                'inbound_fee_after': inbound_fee,
                'reason': reason,
                'success': False,
                'error': None
            }
            
            # Get current policy for comparison
            try:
                channels = await self.lnd_client.list_channels()
                current_channel = None
                
                for ch in channels:
                    if ch.get('chan_id') == channel_id:
                        current_channel = ch
                        break
                
                if current_channel:
                    change_record['outbound_fee_before'] = current_channel.get('local_chan_reserve_sat', 0)
                    # Note: LND REST API structure may vary, adjust field names as needed
                
            except Exception as e:
                logger.warning(f"Could not get current policy for {channel_id}: {e}")
            
            # Apply the change
            result = await self.lnd_client.update_channel_policy(
                chan_id=channel_id,
                fee_rate_ppm=outbound_fee,
                inbound_fee_rate_ppm=inbound_fee,
                base_fee_msat=0,
                time_lock_delta=80
            )
            
            change_record['success'] = True
            change_record['result'] = result
            
            logger.info(f"Successfully updated fees for channel {channel_id}: {outbound_fee}ppm outbound, {inbound_fee}ppm inbound")
            
        except Exception as e:
            change_record['success'] = False
            change_record['error'] = str(e)
            
            logger.error(f"Failed to update fees for channel {channel_id}: {e}")
            
        finally:
            self.fee_change_log.append(change_record)
        
        return change_record['success']
    
    async def get_real_time_channel_data(self, channel_id: str) -> Optional[Dict[str, Any]]:
        """Get real-time channel data from LND"""
        
        try:
            channels = await self.lnd_client.list_channels()
            
            for channel in channels:
                if channel.get('chan_id') == channel_id:
                    # Enrich with forwarding data
                    forwarding_events = await self.lnd_client.get_forwarding_events(
                        max_events=100
                    )
                    
                    # Filter events for this channel
                    channel_events = [
                        event for event in forwarding_events.get('forwarding_events', [])
                        if event.get('chan_id_in') == channel_id or event.get('chan_id_out') == channel_id
                    ]
                    
                    channel['recent_forwarding_events'] = channel_events
                    return channel
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get real-time data for channel {channel_id}: {e}")
            return None
    
    async def validate_channel_health(self, channel_id: str) -> Dict[str, Any]:
        """Validate channel health after fee changes"""
        
        health_check = {
            'channel_id': channel_id,
            'timestamp': datetime.utcnow().isoformat(),
            'is_active': False,
            'is_online': False,
            'balance_ok': False,
            'recent_activity': False,
            'warnings': []
        }
        
        try:
            channel_data = await self.get_real_time_channel_data(channel_id)
            
            if not channel_data:
                health_check['warnings'].append('Channel not found')
                return health_check
            
            # Check if channel is active
            health_check['is_active'] = channel_data.get('active', False)
            if not health_check['is_active']:
                health_check['warnings'].append('Channel is inactive')
            
            # Check peer online status
            health_check['is_online'] = channel_data.get('remote_pubkey') is not None
            
            # Check balance extremes
            local_balance = int(channel_data.get('local_balance', 0))
            remote_balance = int(channel_data.get('remote_balance', 0))
            total_balance = local_balance + remote_balance
            
            if total_balance > 0:
                local_ratio = local_balance / total_balance
                health_check['balance_ok'] = 0.05 < local_ratio < 0.95
                
                if local_ratio <= 0.05:
                    health_check['warnings'].append('Channel severely depleted (local <5%)')
                elif local_ratio >= 0.95:
                    health_check['warnings'].append('Channel severely unbalanced (local >95%)')
            
            # Check recent activity
            recent_events = channel_data.get('recent_forwarding_events', [])
            health_check['recent_activity'] = len(recent_events) > 0
            
            if not health_check['recent_activity']:
                health_check['warnings'].append('No recent forwarding activity')
            
        except Exception as e:
            health_check['warnings'].append(f'Health check failed: {str(e)}')
        
        return health_check
    
    def get_fee_change_summary(self) -> Dict[str, Any]:
        """Get summary of fee changes made during experiment"""
        
        successful_changes = [log for log in self.fee_change_log if log['success']]
        failed_changes = [log for log in self.fee_change_log if not log['success']]
        
        return {
            'total_attempts': len(self.fee_change_log),
            'successful_changes': len(successful_changes),
            'failed_changes': len(failed_changes),
            'success_rate': len(successful_changes) / max(len(self.fee_change_log), 1),
            'channels_modified': len(set(log['channel_id'] for log in successful_changes)),
            'latest_changes': self.fee_change_log[-10:] if self.fee_change_log else [],
            'error_summary': {}
        }
    
    def save_fee_change_log(self, filepath: str) -> None:
        """Save fee change log to file"""
        
        try:
            with open(filepath, 'w') as f:
                json.dump(self.fee_change_log, f, indent=2, default=str)
            
            logger.info(f"Fee change log saved to {filepath}")
            
        except Exception as e:
            logger.error(f"Failed to save fee change log: {e}")


# Example usage and testing
async def test_lnd_connection():
    """Test LND connection and basic operations"""
    
    try:
        async with LNDRestClient() as lnd:
            # Test basic connection
            info = await lnd.get_node_info()
            print(f"Connected to: {info.get('alias')} ({info.get('identity_pubkey', '')[:16]}...)")
            
            # List channels
            channels = await lnd.list_channels()
            print(f"Found {len(channels)} active channels")
            
            if channels:
                # Test getting channel info
                test_channel = channels[0]
                chan_id = test_channel.get('chan_id')
                print(f"Test channel: {chan_id}")
                
                # This would be uncommented for actual fee change testing:
                # await lnd.update_channel_policy(
                #     chan_id=chan_id,
                #     fee_rate_ppm=100,
                #     inbound_fee_rate_ppm=10
                # )
                # print("Fee policy updated successfully")
    
    except Exception as e:
        print(f"LND connection test failed: {e}")


if __name__ == "__main__":
    # Test the LND connection
    asyncio.run(test_lnd_connection())