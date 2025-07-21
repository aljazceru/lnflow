#!/bin/bash

# Lightning Fee Optimizer - Apply Recommendations Script
# Generated from final_recommendations.json
# 
# WARNING: This script will modify your Lightning Network channel fees!
# 
# SAFETY CHECKLIST:
# [ ] Backup your current channel policies: lncli describegraph > channel_policies_backup.json
# [ ] Test on a small subset first
# [ ] Monitor channels after applying changes
# [ ] Have a rollback plan ready
#
# DO NOT RUN THIS SCRIPT WITHOUT REVIEWING EACH COMMAND!

set -e  # Exit on any error

echo "🔍 Lightning Fee Optimizer - Fee Update Script"
echo "⚠️  WARNING: This will modify your channel fees!"
echo ""
read -p "Are you sure you want to continue? (yes/no): " confirm

if [[ $confirm != "yes" ]]; then
    echo "Aborted."
    exit 0
fi

echo ""
echo "📊 Applying fee recommendations..."
echo "💾 Consider backing up current policies first:"
echo "   lncli describegraph > channel_policies_backup.json"
echo ""

# Function to convert compact channel ID to channel point
# Note: This requires querying the channel to get the channel point
get_channel_point() {
    local channel_id=$1
    # Query lnd to get channel info and extract channel point
    lncli getchaninfo --chan_id $channel_id 2>/dev/null | jq -r '.chan_point // empty' || echo ""
}

# Function to update channel policy with error handling
update_channel_fee() {
    local channel_id=$1
    local current_rate=$2
    local new_rate=$3
    local reason="$4"
    local priority="$5"
    local confidence="$6"
    
    echo "----------------------------------------"
    echo "Channel: $channel_id"
    echo "Priority: $priority | Confidence: $confidence"
    echo "Current Rate: ${current_rate} ppm → New Rate: ${new_rate} ppm"
    echo "Reason: $reason"
    echo ""
    
    # Get channel point (required for lncli updatechanpolicy)
    channel_point=$(get_channel_point $channel_id)
    
    if [[ -z "$channel_point" ]]; then
        echo "❌ ERROR: Could not find channel point for $channel_id"
        echo "   You may need to update manually using the compact format"
        echo "   Command: lncli updatechanpolicy --chan_id $channel_id --fee_rate $new_rate"
        echo ""
        return 1
    fi
    
    echo "Channel Point: $channel_point"
    
    # Build the lncli command
    cmd="lncli updatechanpolicy --chan_point \"$channel_point\" --fee_rate $new_rate"
    
    echo "Command: $cmd"
    
    # Uncomment the next line to actually execute the command
    # eval $cmd
    
    echo "✅ Command prepared (not executed - remove comments to apply)"
    echo ""
}

echo "==================== HIGH PRIORITY RECOMMENDATIONS ===================="
echo "These are high-confidence recommendations for well-performing channels"
echo ""

# High Priority / High Confidence Recommendations
update_channel_fee "803265x3020x1" 209 229 "Excellent performance - minimal fee increase to test demand elasticity" "low" "high"
update_channel_fee "779651x576x1" 10 11 "Excellent performance - minimal fee increase to test demand elasticity" "low" "high"
update_channel_fee "880360x2328x1" 88 96 "Excellent performance - minimal fee increase to test demand elasticity" "low" "high"
update_channel_fee "890401x1900x1" 10 11 "Excellent performance - minimal fee increase to test demand elasticity" "low" "high"
update_channel_fee "890416x1202x3" 10 11 "Excellent performance - minimal fee increase to test demand elasticity" "low" "high"
update_channel_fee "890416x1202x2" 47 51 "Excellent performance - minimal fee increase to test demand elasticity" "low" "high"
update_channel_fee "890416x1202x1" 10 11 "Excellent performance - minimal fee increase to test demand elasticity" "low" "high"
update_channel_fee "890416x1202x0" 10 11 "Excellent performance - minimal fee increase to test demand elasticity" "low" "high"
update_channel_fee "721508x1824x1" 10 11 "Excellent performance - minimal fee increase to test demand elasticity" "low" "high"
update_channel_fee "776941x111x1" 10 11 "Excellent performance - minimal fee increase to test demand elasticity" "low" "high"

echo ""
echo "==================== MEDIUM PRIORITY RECOMMENDATIONS ===================="
echo "These recommendations address channel balance and activity issues"
echo ""

# Balance Management (Medium Priority)
update_channel_fee "845867x2612x0" 100 80 "Reduce fees to encourage outbound flow and rebalance channel" "medium" "medium"
update_channel_fee "881262x147x1" 250 375 "Increase fees to reduce outbound flow and preserve local balance" "medium" "medium"
update_channel_fee "902317x2151x0" 36 28 "Reduce fees to encourage outbound flow and rebalance channel" "medium" "medium"
update_channel_fee "903561x1516x0" 90 72 "Reduce fees to encourage outbound flow and rebalance channel" "medium" "medium"
update_channel_fee "900023x1554x0" 28 22 "Reduce fees to encourage outbound flow and rebalance channel" "medium" "medium"
update_channel_fee "691130x155x1" 188 282 "Increase fees to reduce outbound flow and preserve local balance" "medium" "medium"
update_channel_fee "903613x2575x1" 202 303 "Increase fees to reduce outbound flow and preserve local balance" "medium" "medium"
update_channel_fee "893297x1850x1" 29 23 "Reduce fees to encourage outbound flow and rebalance channel" "medium" "medium"
update_channel_fee "902817x2318x1" 31 24 "Reduce fees to encourage outbound flow and rebalance channel" "medium" "medium"
update_channel_fee "904664x2249x4" 130 104 "Reduce fees to encourage outbound flow and rebalance channel" "medium" "medium"
update_channel_fee "903294x1253x1" 128 102 "Reduce fees to encourage outbound flow and rebalance channel" "medium" "medium"
update_channel_fee "902797x1125x0" 133 106 "Reduce fees to encourage outbound flow and rebalance channel" "medium" "medium"
update_channel_fee "878853x1612x1" 297 445 "Increase fees to reduce outbound flow and preserve local balance" "medium" "medium"
update_channel_fee "799714x355x0" 245 367 "Increase fees to reduce outbound flow and preserve local balance" "medium" "medium"

echo ""
echo "==================== LOW ACTIVITY CHANNEL ACTIVATION ===================="
echo "These channels have low activity - reducing fees to encourage routing"
echo ""

# Low Activity Channels (Lower Confidence)
update_channel_fee "687420x2350x1" 37 25 "Low activity - reduce fees to encourage more routing" "medium" "low"
update_channel_fee "691153x813x1" 10 7 "Low activity - reduce fees to encourage more routing" "medium" "low"
update_channel_fee "896882x554x1" 71 49 "Low activity - reduce fees to encourage more routing" "medium" "low"

echo ""
echo "==================== MANUAL ALTERNATIVES ===================="
echo "If channel points cannot be resolved, use these alternative commands:"
echo ""

echo "# High-confidence increases (test these first):"
echo "lncli updatechanpolicy --chan_id 803265x3020x1 --fee_rate 229  # Current: 209 ppm"
echo "lncli updatechanpolicy --chan_id 779651x576x1 --fee_rate 11    # Current: 10 ppm"
echo "lncli updatechanpolicy --chan_id 880360x2328x1 --fee_rate 96   # Current: 88 ppm"
echo ""
echo "# Balance management (monitor carefully):"
echo "lncli updatechanpolicy --chan_id 881262x147x1 --fee_rate 375   # Current: 250 ppm (increase)"
echo "lncli updatechanpolicy --chan_id 691130x155x1 --fee_rate 282   # Current: 188 ppm (increase)"
echo "lncli updatechanpolicy --chan_id 845867x2612x0 --fee_rate 80   # Current: 100 ppm (decrease)"
echo ""
echo "# Low activity activation (lower confidence):"
echo "lncli updatechanpolicy --chan_id 687420x2350x1 --fee_rate 25   # Current: 37 ppm"
echo "lncli updatechanpolicy --chan_id 691153x813x1 --fee_rate 7     # Current: 10 ppm"

echo ""
echo "==================== MONITORING COMMANDS ===================="
echo "Use these commands to monitor the effects of your changes:"
echo ""

echo "# Check current channel policies:"
echo "lncli listchannels | jq '.channels[] | {chan_id, local_balance, remote_balance, fee_per_kw}'"
echo ""
echo "# Monitor channel activity:"
echo "lncli fwdinghistory --max_events 100"
echo ""
echo "# Check specific channel info:"
echo "lncli getchaninfo --chan_id CHANNEL_ID"
echo ""
echo "# View routing activity:"
echo "lncli listforwards --max_events 50"

echo ""
echo "==================== ROLLBACK INFORMATION ===================="
echo "To rollback changes, use the original fee rates:"
echo ""

echo "# Original fee rates for rollback:"
echo "lncli updatechanpolicy --chan_id 803265x3020x1 --fee_rate 209"
echo "lncli updatechanpolicy --chan_id 779651x576x1 --fee_rate 10"
echo "lncli updatechanpolicy --chan_id 880360x2328x1 --fee_rate 88"
echo "lncli updatechanpolicy --chan_id 890401x1900x1 --fee_rate 10"
echo "lncli updatechanpolicy --chan_id 881262x147x1 --fee_rate 250"
echo "lncli updatechanpolicy --chan_id 691130x155x1 --fee_rate 188"
echo "lncli updatechanpolicy --chan_id 845867x2612x0 --fee_rate 100"
echo "# ... (add more as needed)"

echo ""
echo "🎯 IMPLEMENTATION STRATEGY:"
echo "1. Start with HIGH PRIORITY recommendations (high confidence)"
echo "2. Wait 24-48 hours and monitor routing activity"
echo "3. Apply MEDIUM PRIORITY balance management changes gradually"
echo "4. Monitor for 1 week before applying low activity changes"
echo "5. Keep detailed logs of what you change and when"
echo ""
echo "⚠️  Remember: Channel fee changes take time to propagate through the network!"
echo "📊 Monitor your earnings and routing activity after each change."
echo ""
echo "To execute this script and actually apply changes:"
echo "1. Review each command carefully"
echo "2. Uncomment the 'eval \$cmd' line in the update_channel_fee function"
echo "3. Run the script: ./apply_fee_recommendations.sh"