import httpx
import asyncio
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class ChannelData:
    channel_id: str
    basic_info: Dict[str, Any]
    balance: Dict[str, Any]
    policies: Dict[str, Any]
    fee_report: Dict[str, Any]
    flow_report: Dict[str, Any]
    flow_report_7d: Dict[str, Any]
    flow_report_30d: Dict[str, Any]
    rating: Optional[float]
    rebalance_data: Dict[str, Any]
    warnings: List[str]

class LightningDataFetcher:
    """Async Lightning Network data fetcher using httpx for non-blocking I/O"""

    def __init__(self, base_url: str = "http://localhost:18081/api", max_concurrent: int = 10):
        self.base_url = base_url
        self.max_concurrent = max_concurrent
        self.client: Optional[httpx.AsyncClient] = None
        self._semaphore: Optional[asyncio.Semaphore] = None

    async def __aenter__(self):
        """Async context manager entry"""
        limits = httpx.Limits(max_connections=50, max_keepalive_connections=20)
        self.client = httpx.AsyncClient(timeout=10.0, limits=limits)
        self._semaphore = asyncio.Semaphore(self.max_concurrent)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.client:
            await self.client.aclose()

    async def _get(self, endpoint: str) -> Optional[Any]:
        """Make async GET request to API endpoint"""
        if not self.client:
            raise RuntimeError("Client not initialized. Use async with statement.")

        try:
            url = f"{self.base_url}{endpoint}"
            response = await self.client.get(url)
            if response.status_code == 200:
                content_type = response.headers.get('content-type', '')
                if 'application/json' in content_type:
                    return response.json()
                else:
                    return response.text.strip()
            else:
                logger.warning(f"Failed to fetch {endpoint}: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Error fetching {endpoint}: {e}")
            return None
    
    async def check_sync_status(self) -> bool:
        """Check if lnd is synced to chain"""
        result = await self._get("/status/synced-to-chain")
        return result == "true" if result else False

    async def get_block_height(self) -> Optional[int]:
        """Get current block height"""
        result = await self._get("/status/block-height")
        return int(result) if result else None

    async def get_open_channels(self) -> List[str]:
        """Get list of all open channel IDs"""
        result = await self._get("/status/open-channels")
        return result if isinstance(result, list) else []

    async def get_all_channels(self) -> List[str]:
        """Get list of all channel IDs (open, closed, etc)"""
        result = await self._get("/status/all-channels")
        return result if isinstance(result, list) else []
    
    async def get_channel_details(self, channel_id: str) -> ChannelData:
        """Fetch comprehensive data for a specific channel using concurrent requests"""
        logger.info(f"Fetching data for channel {channel_id}")

        # Fetch all data concurrently for better performance
        tasks = {
            'basic_info': self._get(f"/channel/{channel_id}/"),
            'balance': self._get(f"/channel/{channel_id}/balance"),
            'policies': self._get(f"/channel/{channel_id}/policies"),
            'fee_report': self._get(f"/channel/{channel_id}/fee-report"),
            'flow_report': self._get(f"/channel/{channel_id}/flow-report"),
            'flow_report_7d': self._get(f"/channel/{channel_id}/flow-report/last-days/7"),
            'flow_report_30d': self._get(f"/channel/{channel_id}/flow-report/last-days/30"),
            'rating': self._get(f"/channel/{channel_id}/rating"),
            'warnings': self._get(f"/channel/{channel_id}/warnings"),
            'rebalance_source_costs': self._get(f"/channel/{channel_id}/rebalance-source-costs"),
            'rebalance_source_amount': self._get(f"/channel/{channel_id}/rebalance-source-amount"),
            'rebalance_target_costs': self._get(f"/channel/{channel_id}/rebalance-target-costs"),
            'rebalance_target_amount': self._get(f"/channel/{channel_id}/rebalance-target-amount"),
            'rebalance_support_source': self._get(f"/channel/{channel_id}/rebalance-support-as-source-amount"),
            'rebalance_support_target': self._get(f"/channel/{channel_id}/rebalance-support-as-target-amount"),
        }

        # Execute all requests concurrently
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        data = dict(zip(tasks.keys(), results))

        # Build rebalance data
        rebalance_data = {
            "source_costs": data.get('rebalance_source_costs') or 0,
            "source_amount": data.get('rebalance_source_amount') or 0,
            "target_costs": data.get('rebalance_target_costs') or 0,
            "target_amount": data.get('rebalance_target_amount') or 0,
            "support_as_source": data.get('rebalance_support_source') or 0,
            "support_as_target": data.get('rebalance_support_target') or 0
        }

        return ChannelData(
            channel_id=channel_id,
            basic_info=data.get('basic_info') or {},
            balance=data.get('balance') or {},
            policies=data.get('policies') or {},
            fee_report=data.get('fee_report') or {},
            flow_report=data.get('flow_report') or {},
            flow_report_7d=data.get('flow_report_7d') or {},
            flow_report_30d=data.get('flow_report_30d') or {},
            rating=float(data['rating']) if data.get('rating') else None,
            rebalance_data=rebalance_data,
            warnings=data.get('warnings') if isinstance(data.get('warnings'), list) else []
        )
    
    async def get_node_data(self, pubkey: str) -> Dict[str, Any]:
        """Fetch comprehensive data for a specific node using concurrent requests"""
        logger.info(f"Fetching data for node {pubkey[:10]}...")

        # Fetch all node data concurrently
        tasks = {
            "alias": self._get(f"/node/{pubkey}/alias"),
            "open_channels": self._get(f"/node/{pubkey}/open-channels"),
            "all_channels": self._get(f"/node/{pubkey}/all-channels"),
            "balance": self._get(f"/node/{pubkey}/balance"),
            "fee_report": self._get(f"/node/{pubkey}/fee-report"),
            "fee_report_7d": self._get(f"/node/{pubkey}/fee-report/last-days/7"),
            "fee_report_30d": self._get(f"/node/{pubkey}/fee-report/last-days/30"),
            "flow_report": self._get(f"/node/{pubkey}/flow-report"),
            "flow_report_7d": self._get(f"/node/{pubkey}/flow-report/last-days/7"),
            "flow_report_30d": self._get(f"/node/{pubkey}/flow-report/last-days/30"),
            "on_chain_costs": self._get(f"/node/{pubkey}/on-chain-costs"),
            "rating": self._get(f"/node/{pubkey}/rating"),
            "warnings": self._get(f"/node/{pubkey}/warnings")
        }

        # Execute all requests concurrently
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        data = dict(zip(tasks.keys(), results))

        return {
            "pubkey": pubkey,
            "alias": data.get('alias'),
            "open_channels": data.get('open_channels') or [],
            "all_channels": data.get('all_channels') or [],
            "balance": data.get('balance') or {},
            "fee_report": data.get('fee_report') or {},
            "fee_report_7d": data.get('fee_report_7d') or {},
            "fee_report_30d": data.get('fee_report_30d') or {},
            "flow_report": data.get('flow_report') or {},
            "flow_report_7d": data.get('flow_report_7d') or {},
            "flow_report_30d": data.get('flow_report_30d') or {},
            "on_chain_costs": data.get('on_chain_costs') or {},
            "rating": data.get('rating'),
            "warnings": data.get('warnings') or []
        }
    
    async def fetch_all_data(self) -> Dict[str, Any]:
        """Fetch all channel and node data with concurrency limiting"""
        logger.info("Starting comprehensive data fetch...")

        # Check sync status
        if not await self.check_sync_status():
            logger.warning("Node is not synced to chain!")

        # Get basic info
        block_height = await self.get_block_height()
        open_channels = await self.get_open_channels()
        all_channels = await self.get_all_channels()

        logger.info(f"Block height: {block_height}")
        logger.info(f"Open channels: {len(open_channels)}")
        logger.info(f"Total channels: {len(all_channels)}")

        # Fetch detailed channel data with semaphore limiting
        async def fetch_channel_limited(channel_id: str):
            async with self._semaphore:
                try:
                    return channel_id, await self.get_channel_details(channel_id)
                except Exception as e:
                    logger.error(f"Error fetching channel {channel_id}: {e}")
                    return channel_id, None

        channel_tasks = [fetch_channel_limited(cid) for cid in open_channels]
        channel_results = await asyncio.gather(*channel_tasks)
        channels_data = {cid: data for cid, data in channel_results if data is not None}

        # Get unique node pubkeys from channel data
        node_pubkeys = set()
        for channel_data in channels_data.values():
            if 'remotePubkey' in channel_data.basic_info:
                node_pubkeys.add(channel_data.basic_info['remotePubkey'])

        # Fetch node data with semaphore limiting
        async def fetch_node_limited(pubkey: str):
            async with self._semaphore:
                try:
                    return pubkey, await self.get_node_data(pubkey)
                except Exception as e:
                    logger.error(f"Error fetching node {pubkey[:10]}...: {e}")
                    return pubkey, None

        node_tasks = [fetch_node_limited(pubkey) for pubkey in node_pubkeys]
        node_results = await asyncio.gather(*node_tasks)
        nodes_data = {pubkey: data for pubkey, data in node_results if data is not None}

        return {
            "block_height": block_height,
            "open_channels": open_channels,
            "all_channels": all_channels,
            "channels": channels_data,
            "nodes": nodes_data
        }
    
    def save_data(self, data: Dict[str, Any], filename: str = "lightning_data.json"):
        """Save fetched data to JSON file"""
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        logger.info(f"Data saved to {filename}")

if __name__ == "__main__":
    async def main():
        async with LightningDataFetcher() as fetcher:
            all_data = await fetcher.fetch_all_data()
            fetcher.save_data(all_data, "lightning_data.json")

    asyncio.run(main())