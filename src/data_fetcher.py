import requests
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
    def __init__(self, base_url: str = "http://localhost:18081/api"):
        self.base_url = base_url
        self.session = requests.Session()
    
    def _get(self, endpoint: str) -> Optional[Any]:
        """Make GET request to API endpoint"""
        try:
            url = f"{self.base_url}{endpoint}"
            response = self.session.get(url, timeout=10)
            if response.status_code == 200:
                try:
                    return response.json()
                except json.JSONDecodeError:
                    return response.text.strip()
            else:
                logger.warning(f"Failed to fetch {endpoint}: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Error fetching {endpoint}: {e}")
            return None
    
    def check_sync_status(self) -> bool:
        """Check if lnd is synced to chain"""
        result = self._get("/status/synced-to-chain")
        return result == "true" if result else False
    
    def get_block_height(self) -> Optional[int]:
        """Get current block height"""
        result = self._get("/status/block-height")
        return int(result) if result else None
    
    def get_open_channels(self) -> List[str]:
        """Get list of all open channel IDs"""
        result = self._get("/status/open-channels")
        return result if isinstance(result, list) else []
    
    def get_all_channels(self) -> List[str]:
        """Get list of all channel IDs (open, closed, etc)"""
        result = self._get("/status/all-channels")
        return result if isinstance(result, list) else []
    
    def get_channel_details(self, channel_id: str) -> ChannelData:
        """Fetch comprehensive data for a specific channel"""
        logger.info(f"Fetching data for channel {channel_id}")
        
        basic_info = self._get(f"/channel/{channel_id}/") or {}
        balance = self._get(f"/channel/{channel_id}/balance") or {}
        policies = self._get(f"/channel/{channel_id}/policies") or {}
        fee_report = self._get(f"/channel/{channel_id}/fee-report") or {}
        flow_report = self._get(f"/channel/{channel_id}/flow-report") or {}
        flow_report_7d = self._get(f"/channel/{channel_id}/flow-report/last-days/7") or {}
        flow_report_30d = self._get(f"/channel/{channel_id}/flow-report/last-days/30") or {}
        rating = self._get(f"/channel/{channel_id}/rating")
        warnings = self._get(f"/channel/{channel_id}/warnings") or []
        
        # Fetch rebalance data
        rebalance_data = {
            "source_costs": self._get(f"/channel/{channel_id}/rebalance-source-costs") or 0,
            "source_amount": self._get(f"/channel/{channel_id}/rebalance-source-amount") or 0,
            "target_costs": self._get(f"/channel/{channel_id}/rebalance-target-costs") or 0,
            "target_amount": self._get(f"/channel/{channel_id}/rebalance-target-amount") or 0,
            "support_as_source": self._get(f"/channel/{channel_id}/rebalance-support-as-source-amount") or 0,
            "support_as_target": self._get(f"/channel/{channel_id}/rebalance-support-as-target-amount") or 0
        }
        
        return ChannelData(
            channel_id=channel_id,
            basic_info=basic_info,
            balance=balance,
            policies=policies,
            fee_report=fee_report,
            flow_report=flow_report,
            flow_report_7d=flow_report_7d,
            flow_report_30d=flow_report_30d,
            rating=float(rating) if rating else None,
            rebalance_data=rebalance_data,
            warnings=warnings if isinstance(warnings, list) else []
        )
    
    def get_node_data(self, pubkey: str) -> Dict[str, Any]:
        """Fetch comprehensive data for a specific node"""
        logger.info(f"Fetching data for node {pubkey[:10]}...")
        
        return {
            "pubkey": pubkey,
            "alias": self._get(f"/node/{pubkey}/alias"),
            "open_channels": self._get(f"/node/{pubkey}/open-channels") or [],
            "all_channels": self._get(f"/node/{pubkey}/all-channels") or [],
            "balance": self._get(f"/node/{pubkey}/balance") or {},
            "fee_report": self._get(f"/node/{pubkey}/fee-report") or {},
            "fee_report_7d": self._get(f"/node/{pubkey}/fee-report/last-days/7") or {},
            "fee_report_30d": self._get(f"/node/{pubkey}/fee-report/last-days/30") or {},
            "flow_report": self._get(f"/node/{pubkey}/flow-report") or {},
            "flow_report_7d": self._get(f"/node/{pubkey}/flow-report/last-days/7") or {},
            "flow_report_30d": self._get(f"/node/{pubkey}/flow-report/last-days/30") or {},
            "on_chain_costs": self._get(f"/node/{pubkey}/on-chain-costs") or {},
            "rating": self._get(f"/node/{pubkey}/rating"),
            "warnings": self._get(f"/node/{pubkey}/warnings") or []
        }
    
    def fetch_all_data(self) -> Dict[str, Any]:
        """Fetch all channel and node data"""
        logger.info("Starting comprehensive data fetch...")
        
        # Check sync status
        if not self.check_sync_status():
            logger.warning("Node is not synced to chain!")
        
        # Get basic info
        block_height = self.get_block_height()
        open_channels = self.get_open_channels()
        all_channels = self.get_all_channels()
        
        logger.info(f"Block height: {block_height}")
        logger.info(f"Open channels: {len(open_channels)}")
        logger.info(f"Total channels: {len(all_channels)}")
        
        # Fetch detailed channel data
        channels_data = {}
        for channel_id in open_channels:
            try:
                channels_data[channel_id] = self.get_channel_details(channel_id)
            except Exception as e:
                logger.error(f"Error fetching channel {channel_id}: {e}")
        
        # Get unique node pubkeys from channel data
        node_pubkeys = set()
        for channel_data in channels_data.values():
            if 'remotePubkey' in channel_data.basic_info:
                node_pubkeys.add(channel_data.basic_info['remotePubkey'])
        
        # Fetch node data
        nodes_data = {}
        for pubkey in node_pubkeys:
            try:
                nodes_data[pubkey] = self.get_node_data(pubkey)
            except Exception as e:
                logger.error(f"Error fetching node {pubkey[:10]}...: {e}")
        
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
    fetcher = LightningDataFetcher()
    all_data = fetcher.fetch_all_data()
    fetcher.save_data(all_data, "lightning-fee-optimizer/data/lightning_data.json")