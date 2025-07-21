#!/usr/bin/env python3
"""Test the Lightning Fee Optimizer with real data"""

import asyncio
import sys
import logging
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.api.client import LndManageClient
from src.analysis.analyzer import ChannelAnalyzer
from src.strategy.optimizer import FeeOptimizer, OptimizationStrategy
from src.utils.config import Config

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_system():
    """Test the complete optimization system"""
    print("🔍 Testing Lightning Fee Optimizer")
    
    # Initialize configuration
    config_file = Path("config/default.json")
    config = Config.load(str(config_file) if config_file.exists() else None)
    
    async with LndManageClient(config.api.base_url) as client:
        print("\n✅ Checking node connection...")
        if not await client.is_synced():
            print("❌ Node is not synced to chain!")
            return
        
        block_height = await client.get_block_height()
        print(f"📦 Current block height: {block_height}")
        
        print("\n📊 Fetching channel data...")
        # Get first few channels for testing
        response = await client.get_open_channels()
        if isinstance(response, dict) and 'channels' in response:
            channel_ids = response['channels'][:5]  # Test with first 5 channels
        else:
            channel_ids = response[:5] if isinstance(response, list) else []
        
        if not channel_ids:
            print("❌ No channels found!")
            return
        
        print(f"🔗 Found {len(channel_ids)} channels to test with")
        
        # Analyze channels
        analyzer = ChannelAnalyzer(client, config)
        print("\n🔬 Analyzing channel performance...")
        try:
            metrics = await analyzer.analyze_channels(channel_ids)
            print(f"✅ Successfully analyzed {len(metrics)} channels")
            
            # Print analysis
            print("\n📈 Channel Analysis Results:")
            analyzer.print_analysis(metrics)
            
            # Test optimization
            print("\n⚡ Generating fee optimization recommendations...")
            optimizer = FeeOptimizer(config.optimization, OptimizationStrategy.BALANCED)
            recommendations = optimizer.optimize_fees(metrics)
            
            print(f"✅ Generated {len(recommendations)} recommendations")
            optimizer.print_recommendations(recommendations)
            
            # Save recommendations
            output_file = "test_recommendations.json"
            optimizer.save_recommendations(recommendations, output_file)
            print(f"\n💾 Saved recommendations to {output_file}")
            
        except Exception as e:
            logger.exception("Failed during analysis")
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_system())