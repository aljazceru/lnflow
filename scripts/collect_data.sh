#!/bin/bash

# Script to collect comprehensive channel data from LND Manage API

API_URL="http://localhost:18081"
OUTPUT_DIR="data_samples"
mkdir -p $OUTPUT_DIR

echo "Collecting Lightning Network data..."

# Get node status
echo "Fetching node status..."
curl -s $API_URL/api/status/synced-to-chain > $OUTPUT_DIR/synced_status.json
curl -s $API_URL/api/status/block-height > $OUTPUT_DIR/block_height.txt

# Get all channels
echo "Fetching channel list..."
curl -s $API_URL/api/status/open-channels > $OUTPUT_DIR/open_channels.json
curl -s $API_URL/api/status/all-channels > $OUTPUT_DIR/all_channels.json

# Extract channel IDs
CHANNELS=$(curl -s $API_URL/api/status/open-channels | jq -r '.channels[]')

# Create channel details directory
mkdir -p $OUTPUT_DIR/channels

# Fetch detailed data for each channel
echo "Fetching detailed channel data..."
for channel in $CHANNELS; do
    echo "Processing channel: $channel"
    
    # Create safe filename
    safe_channel=$(echo $channel | tr ':' '_')
    
    # Fetch all channel data
    curl -s $API_URL/api/channel/$channel/details > $OUTPUT_DIR/channels/${safe_channel}_details.json
    
    # Also fetch specific reports for analysis
    curl -s $API_URL/api/channel/$channel/flow-report/last-days/7 > $OUTPUT_DIR/channels/${safe_channel}_flow_7d.json
    curl -s $API_URL/api/channel/$channel/flow-report/last-days/30 > $OUTPUT_DIR/channels/${safe_channel}_flow_30d.json
done

# Get unique remote pubkeys
echo "Extracting remote node information..."
PUBKEYS=$(cat $OUTPUT_DIR/channels/*_details.json | jq -r '.remotePubkey' | sort -u)

# Create node details directory
mkdir -p $OUTPUT_DIR/nodes

# Fetch node data
for pubkey in $PUBKEYS; do
    echo "Processing node: $pubkey"
    
    # Create safe filename (first 16 chars of pubkey)
    safe_pubkey=$(echo $pubkey | cut -c1-16)
    
    # Fetch node data
    curl -s $API_URL/api/node/$pubkey/alias > $OUTPUT_DIR/nodes/${safe_pubkey}_alias.txt
    curl -s $API_URL/api/node/$pubkey/details > $OUTPUT_DIR/nodes/${safe_pubkey}_details.json
    curl -s $API_URL/api/node/$pubkey/rating > $OUTPUT_DIR/nodes/${safe_pubkey}_rating.json
done

echo "Data collection complete! Results saved in $OUTPUT_DIR/"

# Create summary
echo -e "\n=== Summary ===" > $OUTPUT_DIR/summary.txt
echo "Total open channels: $(echo $CHANNELS | wc -w)" >> $OUTPUT_DIR/summary.txt
echo "Unique remote nodes: $(echo $PUBKEYS | wc -w)" >> $OUTPUT_DIR/summary.txt
echo "Data collected at: $(date)" >> $OUTPUT_DIR/summary.txt