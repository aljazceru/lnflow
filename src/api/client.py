"""LND Manage API Client"""

import asyncio
import logging
from typing import List, Dict, Any, Optional
import httpx
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class LndManageClient:
    """Client for interacting with LND Manage API"""

    def __init__(self, base_url: str = "http://localhost:18081", max_concurrent: int = 10):
        self.base_url = base_url.rstrip('/')
        self.client: Optional[httpx.AsyncClient] = None
        self.max_concurrent = max_concurrent
        self._semaphore: Optional[asyncio.Semaphore] = None
    
    async def __aenter__(self):
        # Use connection pooling with limits
        limits = httpx.Limits(max_connections=50, max_keepalive_connections=20)
        self.client = httpx.AsyncClient(timeout=30.0, limits=limits)
        self._semaphore = asyncio.Semaphore(self.max_concurrent)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()
    
    async def _get(self, endpoint: str) -> Any:
        """Make GET request to API"""
        if not self.client:
            raise RuntimeError("Client not initialized. Use async with statement.")
        
        url = f"{self.base_url}{endpoint}"
        logger.debug(f"GET {url}")
        
        try:
            response = await self.client.get(url)
            response.raise_for_status()
            
            # Handle plain text responses (like alias endpoint)
            content_type = response.headers.get('content-type', '')
            if 'text/plain' in content_type:
                return response.text
            
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"API request failed: {e}")
            raise
    
    async def is_synced(self) -> bool:
        """Check if node is synced to chain"""
        try:
            result = await self._get("/api/status/synced-to-chain")
            return result is True
        except Exception:
            return False
    
    async def get_block_height(self) -> int:
        """Get current block height"""
        return await self._get("/api/status/block-height")
    
    async def get_open_channels(self) -> List[str]:
        """Get list of open channel IDs"""
        return await self._get("/api/status/open-channels")
    
    async def get_all_channels(self) -> List[str]:
        """Get list of all channel IDs (open, closed, etc)"""
        return await self._get("/api/status/all-channels")
    
    async def get_channel_details(self, channel_id: str) -> Dict[str, Any]:
        """Get comprehensive channel details"""
        return await self._get(f"/api/channel/{channel_id}/details")
    
    async def get_channel_info(self, channel_id: str) -> Dict[str, Any]:
        """Get basic channel information"""
        return await self._get(f"/api/channel/{channel_id}/")
    
    async def get_channel_balance(self, channel_id: str) -> Dict[str, Any]:
        """Get channel balance information"""
        return await self._get(f"/api/channel/{channel_id}/balance")
    
    async def get_channel_policies(self, channel_id: str) -> Dict[str, Any]:
        """Get channel fee policies"""
        return await self._get(f"/api/channel/{channel_id}/policies")
    
    async def get_channel_flow_report(self, channel_id: str, days: Optional[int] = None) -> Dict[str, Any]:
        """Get channel flow report"""
        if days:
            return await self._get(f"/api/channel/{channel_id}/flow-report/last-days/{days}")
        return await self._get(f"/api/channel/{channel_id}/flow-report")
    
    async def get_channel_fee_report(self, channel_id: str) -> Dict[str, Any]:
        """Get channel fee earnings report"""
        return await self._get(f"/api/channel/{channel_id}/fee-report")
    
    async def get_channel_rating(self, channel_id: str) -> int:
        """Get channel rating"""
        return await self._get(f"/api/channel/{channel_id}/rating")
    
    async def get_channel_warnings(self, channel_id: str) -> List[str]:
        """Get channel warnings"""
        return await self._get(f"/api/channel/{channel_id}/warnings")
    
    async def get_channel_rebalance_info(self, channel_id: str) -> Dict[str, Any]:
        """Get channel rebalancing information"""
        tasks = [
            self._get(f"/api/channel/{channel_id}/rebalance-source-costs"),
            self._get(f"/api/channel/{channel_id}/rebalance-source-amount"),
            self._get(f"/api/channel/{channel_id}/rebalance-target-costs"),
            self._get(f"/api/channel/{channel_id}/rebalance-target-amount"),
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        return {
            'source_costs': results[0] if not isinstance(results[0], Exception) else 0,
            'source_amount': results[1] if not isinstance(results[1], Exception) else 0,
            'target_costs': results[2] if not isinstance(results[2], Exception) else 0,
            'target_amount': results[3] if not isinstance(results[3], Exception) else 0,
        }
    
    async def get_node_alias(self, pubkey: str) -> str:
        """Get node alias"""
        try:
            return await self._get(f"/api/node/{pubkey}/alias")
        except Exception:
            return pubkey[:8] + "..."
    
    async def get_node_details(self, pubkey: str) -> Dict[str, Any]:
        """Get comprehensive node details"""
        return await self._get(f"/api/node/{pubkey}/details")
    
    async def get_node_rating(self, pubkey: str) -> int:
        """Get node rating"""
        return await self._get(f"/api/node/{pubkey}/rating")
    
    async def get_node_warnings(self, pubkey: str) -> List[str]:
        """Get node warnings"""
        return await self._get(f"/api/node/{pubkey}/warnings")
    
    async def fetch_all_channel_data(self, channel_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Fetch comprehensive data for all channels using the /details endpoint with concurrency limiting"""
        if channel_ids is None:
            # Get channel IDs from the API response
            response = await self.get_open_channels()
            if isinstance(response, dict) and 'channels' in response:
                channel_ids = response['channels']
            else:
                channel_ids = response if isinstance(response, list) else []

        logger.info(f"Fetching data for {len(channel_ids)} channels (max {self.max_concurrent} concurrent)")

        # Fetch data for all channels concurrently with semaphore limiting
        tasks = []
        for channel_id in channel_ids:
            tasks.append(self._fetch_single_channel_data_limited(channel_id))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out failed requests
        channel_data = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Failed to fetch data for channel {channel_ids[i]}: {result}")
            else:
                channel_data.append(result)

        logger.info(f"Successfully fetched data for {len(channel_data)}/{len(channel_ids)} channels")
        return channel_data

    async def _fetch_single_channel_data_limited(self, channel_id: str) -> Dict[str, Any]:
        """Fetch channel data with semaphore limiting to prevent overwhelming the API"""
        if self._semaphore is None:
            # Fallback if semaphore not initialized (shouldn't happen in normal use)
            return await self._fetch_single_channel_data(channel_id)

        async with self._semaphore:
            return await self._fetch_single_channel_data(channel_id)
    
    async def _fetch_single_channel_data(self, channel_id: str) -> Dict[str, Any]:
        """Fetch all data for a single channel using the details endpoint"""
        try:
            # The /details endpoint provides all the data we need
            channel_data = await self.get_channel_details(channel_id)
            channel_data['timestamp'] = datetime.utcnow().isoformat()
            return channel_data
        except Exception as e:
            logger.error(f"Failed to fetch details for channel {channel_id}: {e}")
            # Fallback to individual endpoints if details fails
            return await self._fetch_single_channel_data_fallback(channel_id)
    
    async def _fetch_single_channel_data_fallback(self, channel_id: str) -> Dict[str, Any]:
        """Fallback method to fetch channel data using individual endpoints"""
        # Fetch basic info first
        try:
            info = await self.get_channel_info(channel_id)
        except Exception as e:
            logger.error(f"Failed to fetch basic info for channel {channel_id}: {e}")
            return {'channelIdCompact': channel_id, 'timestamp': datetime.utcnow().isoformat()}
        
        # Fetch additional data concurrently
        tasks = {
            'balance': self.get_channel_balance(channel_id),
            'policies': self.get_channel_policies(channel_id),
            'flow_7d': self.get_channel_flow_report(channel_id, 7),
            'flow_30d': self.get_channel_flow_report(channel_id, 30),
            'fee_report': self.get_channel_fee_report(channel_id),
            'rating': self.get_channel_rating(channel_id),
            'warnings': self.get_channel_warnings(channel_id),
            'rebalance': self.get_channel_rebalance_info(channel_id),
        }
        
        results = {}
        for key, task in tasks.items():
            try:
                results[key] = await task
            except Exception as e:
                logger.debug(f"Failed to fetch {key} for channel {channel_id}: {e}")
                results[key] = None
        
        # Combine all data
        channel_data = {
            **info,
            'timestamp': datetime.utcnow().isoformat(),
            **results
        }
        
        # Fetch node alias if we have the remote pubkey
        if 'remotePubkey' in info:
            try:
                channel_data['remoteAlias'] = await self.get_node_alias(info['remotePubkey'])
            except Exception:
                channel_data['remoteAlias'] = None
        
        return channel_data