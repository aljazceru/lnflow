#!/usr/bin/env python3
"""Analyze collected channel data to understand patterns"""

import json
import os
from pathlib import Path
import pandas as pd
import numpy as np
from typing import Dict, List, Any

def load_channel_data(data_dir: Path) -> List[Dict[str, Any]]:
    """Load all channel detail files"""
    channels = []
    channel_files = data_dir.glob("channels/*_details.json")
    
    for file in channel_files:
        with open(file, 'r') as f:
            try:
                data = json.load(f)
                channels.append(data)
            except Exception as e:
                print(f"Error loading {file}: {e}")
    
    return channels

def analyze_channels(channels: List[Dict[str, Any]]) -> pd.DataFrame:
    """Convert channel data to DataFrame for analysis"""
    rows = []
    
    for ch in channels:
        row = {
            'channel_id': ch.get('channelIdCompact', ''),
            'capacity': int(ch.get('capacitySat', 0)),
            'local_balance': int(ch.get('balance', {}).get('localBalanceSat', 0)),
            'remote_balance': int(ch.get('balance', {}).get('remoteBalanceSat', 0)),
            'local_fee_rate': ch.get('policies', {}).get('local', {}).get('feeRatePpm', 0),
            'remote_fee_rate': ch.get('policies', {}).get('remote', {}).get('feeRatePpm', 0),
            'earned_msat': int(ch.get('feeReport', {}).get('earnedMilliSat', 0)),
            'sourced_msat': int(ch.get('feeReport', {}).get('sourcedMilliSat', 0)),
            'total_sent_msat': int(ch.get('flowReport', {}).get('totalSentMilliSat', 0)),
            'total_received_msat': int(ch.get('flowReport', {}).get('totalReceivedMilliSat', 0)),
            'forwarded_sent_msat': int(ch.get('flowReport', {}).get('forwardedSentMilliSat', 0)),
            'forwarded_received_msat': int(ch.get('flowReport', {}).get('forwardedReceivedMilliSat', 0)),
            'remote_alias': ch.get('remoteAlias', 'Unknown'),
            'active': ch.get('status', {}).get('active', False),
            'private': ch.get('status', {}).get('private', False),
            'open_initiator': ch.get('openInitiator', ''),
            'num_updates': int(ch.get('numUpdates', 0)),
            'rating': ch.get('rating', {}).get('rating', -1),
        }
        
        # Calculate derived metrics
        row['balance_ratio'] = row['local_balance'] / row['capacity'] if row['capacity'] > 0 else 0.5
        row['total_flow_sats'] = (row['total_sent_msat'] + row['total_received_msat']) / 1000
        row['net_flow_sats'] = (row['total_received_msat'] - row['total_sent_msat']) / 1000
        row['total_fees_sats'] = (row['earned_msat'] + row['sourced_msat']) / 1000
        row['fee_per_flow'] = row['total_fees_sats'] / row['total_flow_sats'] if row['total_flow_sats'] > 0 else 0
        
        rows.append(row)
    
    return pd.DataFrame(rows)

def print_analysis(df: pd.DataFrame):
    """Print detailed analysis of channels"""
    print("=== Channel Network Analysis ===\n")
    
    # Overall statistics
    print(f"Total Channels: {len(df)}")
    print(f"Total Capacity: {df['capacity'].sum():,} sats")
    print(f"Average Channel Size: {df['capacity'].mean():,.0f} sats")
    print(f"Total Local Balance: {df['local_balance'].sum():,} sats")
    print(f"Total Remote Balance: {df['remote_balance'].sum():,} sats")
    
    # Fee statistics
    print(f"\n=== Fee Statistics ===")
    print(f"Average Local Fee Rate: {df['local_fee_rate'].mean():.0f} ppm")
    print(f"Median Local Fee Rate: {df['local_fee_rate'].median():.0f} ppm")
    print(f"Fee Rate Range: {df['local_fee_rate'].min()} - {df['local_fee_rate'].max()} ppm")
    print(f"Total Fees Earned: {df['total_fees_sats'].sum():,.0f} sats")
    
    # Flow statistics
    print(f"\n=== Flow Statistics ===")
    active_channels = df[df['total_flow_sats'] > 0]
    print(f"Active Channels: {len(active_channels)} ({len(active_channels)/len(df)*100:.1f}%)")
    print(f"Total Flow: {df['total_flow_sats'].sum():,.0f} sats")
    print(f"Average Flow per Active Channel: {active_channels['total_flow_sats'].mean():,.0f} sats")
    
    # Balance distribution
    print(f"\n=== Balance Distribution ===")
    balanced = df[(df['balance_ratio'] > 0.3) & (df['balance_ratio'] < 0.7)]
    depleted = df[df['balance_ratio'] < 0.1]
    full = df[df['balance_ratio'] > 0.9]
    print(f"Balanced (30-70%): {len(balanced)} channels")
    print(f"Depleted (<10%): {len(depleted)} channels")
    print(f"Full (>90%): {len(full)} channels")
    
    # Top performers
    print(f"\n=== Top 10 Fee Earners ===")
    top_earners = df.nlargest(10, 'total_fees_sats')[['channel_id', 'remote_alias', 'capacity', 'total_fees_sats', 'local_fee_rate', 'balance_ratio']]
    print(top_earners.to_string(index=False))
    
    # High flow channels
    print(f"\n=== Top 10 High Flow Channels ===")
    high_flow = df.nlargest(10, 'total_flow_sats')[['channel_id', 'remote_alias', 'total_flow_sats', 'total_fees_sats', 'local_fee_rate']]
    print(high_flow.to_string(index=False))
    
    # Correlation analysis
    print(f"\n=== Correlation Analysis ===")
    correlations = {
        'Fee Rate vs Earnings': df['local_fee_rate'].corr(df['total_fees_sats']),
        'Flow vs Earnings': df['total_flow_sats'].corr(df['total_fees_sats']),
        'Capacity vs Flow': df['capacity'].corr(df['total_flow_sats']),
        'Balance Ratio vs Flow': df['balance_ratio'].corr(df['total_flow_sats']),
    }
    for metric, corr in correlations.items():
        print(f"{metric}: {corr:.3f}")
    
    # Fee optimization opportunities
    print(f"\n=== Optimization Opportunities ===")
    
    # High flow, low fee channels
    high_flow_low_fee = df[(df['total_flow_sats'] > df['total_flow_sats'].quantile(0.75)) & 
                           (df['local_fee_rate'] < df['local_fee_rate'].median())]
    print(f"\nHigh Flow + Low Fees ({len(high_flow_low_fee)} channels):")
    if len(high_flow_low_fee) > 0:
        print(high_flow_low_fee[['channel_id', 'remote_alias', 'total_flow_sats', 'local_fee_rate', 'total_fees_sats']].head())
    
    # Imbalanced high-value channels
    imbalanced = df[((df['balance_ratio'] < 0.2) | (df['balance_ratio'] > 0.8)) & 
                    (df['capacity'] > df['capacity'].median())]
    print(f"\nImbalanced High-Capacity Channels ({len(imbalanced)} channels):")
    if len(imbalanced) > 0:
        print(imbalanced[['channel_id', 'remote_alias', 'capacity', 'balance_ratio', 'net_flow_sats']].head())

if __name__ == "__main__":
    data_dir = Path("data_samples")
    
    print("Loading channel data...")
    channels = load_channel_data(data_dir)
    
    print(f"Loaded {len(channels)} channels\n")
    
    df = analyze_channels(channels)
    print_analysis(df)
    
    # Save processed data
    df.to_csv("channel_analysis.csv", index=False)
    print(f"\nAnalysis saved to channel_analysis.csv")