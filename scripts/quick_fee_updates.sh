#!/bin/bash

# Quick Fee Updates - Lightning Fee Optimizer Recommendations
# 
# This script contains the essential lncli commands to apply fee recommendations.
# Copy and paste individual commands or run sections as needed.
#
# ALWAYS test with a few channels first before applying all changes!

echo "Lightning Network Fee Optimization Commands"
echo "=========================================="
echo ""

echo "🥇 HIGH CONFIDENCE RECOMMENDATIONS (Apply first)"
echo "These are proven high-performers with minimal risk:"
echo ""

# Minimal increases on top-performing channels (highest confidence)
echo "# Top performing channels - minimal increases to test demand elasticity:"
echo "lncli updatechanpolicy --chan_id 803265x3020x1 --fee_rate 229  # 209→229 ppm (+9.6%) - RecklessApotheosis"
echo "lncli updatechanpolicy --chan_id 779651x576x1 --fee_rate 11    # 10→11 ppm (+10%) - WalletOfSatoshi.com"
echo "lncli updatechanpolicy --chan_id 880360x2328x1 --fee_rate 96   # 88→96 ppm (+9.1%) - Voltage"
echo "lncli updatechanpolicy --chan_id 890401x1900x1 --fee_rate 11   # 10→11 ppm (+10%) - DeutscheBank|CLN"
echo "lncli updatechanpolicy --chan_id 890416x1202x3 --fee_rate 11   # 10→11 ppm (+10%) - LNShortcut.ovh"
echo "lncli updatechanpolicy --chan_id 890416x1202x2 --fee_rate 51   # 47→51 ppm (+8.5%) - ln.BitSoapBox.com"
echo "lncli updatechanpolicy --chan_id 890416x1202x1 --fee_rate 11   # 10→11 ppm (+10%) - Fopstronaut"
echo "lncli updatechanpolicy --chan_id 890416x1202x0 --fee_rate 11   # 10→11 ppm (+10%) - HIGH-WAY.ME"
echo "lncli updatechanpolicy --chan_id 721508x1824x1 --fee_rate 11   # 10→11 ppm (+10%) - node_way_jose"
echo "lncli updatechanpolicy --chan_id 776941x111x1 --fee_rate 11    # 10→11 ppm (+10%) - B4BYM"
echo ""

echo "⚖️ BALANCE MANAGEMENT RECOMMENDATIONS (Monitor closely)"
echo "These address channel liquidity imbalances:"
echo ""

echo "# Reduce fees to encourage OUTBOUND flow (channels with too much local balance):"
echo "lncli updatechanpolicy --chan_id 845867x2612x0 --fee_rate 80   # 100→80 ppm (-20%)"
echo "lncli updatechanpolicy --chan_id 902317x2151x0 --fee_rate 28   # 36→28 ppm (-22.2%)"
echo "lncli updatechanpolicy --chan_id 903561x1516x0 --fee_rate 72   # 90→72 ppm (-20%)"
echo "lncli updatechanpolicy --chan_id 900023x1554x0 --fee_rate 22   # 28→22 ppm (-21.4%)"
echo "lncli updatechanpolicy --chan_id 893297x1850x1 --fee_rate 23   # 29→23 ppm (-20.7%)"
echo "lncli updatechanpolicy --chan_id 902817x2318x1 --fee_rate 24   # 31→24 ppm (-22.6%)"
echo "lncli updatechanpolicy --chan_id 904664x2249x4 --fee_rate 104  # 130→104 ppm (-20%)"
echo "lncli updatechanpolicy --chan_id 903294x1253x1 --fee_rate 102  # 128→102 ppm (-20.3%)"
echo "lncli updatechanpolicy --chan_id 902797x1125x0 --fee_rate 106  # 133→106 ppm (-20%)"
echo ""

echo "# Increase fees to PRESERVE local balance (channels being drained):"
echo "lncli updatechanpolicy --chan_id 881262x147x1 --fee_rate 375   # 250→375 ppm (+50%)"
echo "lncli updatechanpolicy --chan_id 691130x155x1 --fee_rate 282   # 188→282 ppm (+50%)"
echo "lncli updatechanpolicy --chan_id 903613x2575x1 --fee_rate 303  # 202→303 ppm (+50%)"
echo "lncli updatechanpolicy --chan_id 878853x1612x1 --fee_rate 445  # 297→445 ppm (+49.8%)"
echo "lncli updatechanpolicy --chan_id 799714x355x0 --fee_rate 367   # 245→367 ppm (+49.8%)"
echo ""

echo "🔄 LOW ACTIVITY CHANNEL ACTIVATION (Lower confidence)"
echo "Reduce fees to try activating dormant channels:"
echo ""

echo "# Low activity channels - reduce fees to encourage routing:"
echo "lncli updatechanpolicy --chan_id 687420x2350x1 --fee_rate 25   # 37→25 ppm (-32.4%) - volcano"
echo "lncli updatechanpolicy --chan_id 691153x813x1 --fee_rate 7     # 10→7 ppm (-30%) - WOWZAA"
echo "lncli updatechanpolicy --chan_id 896882x554x1 --fee_rate 49    # 71→49 ppm (-31%)"
echo ""

echo "📊 MONITORING COMMANDS"
echo "Use these to track your changes:"
echo ""

echo "# Check current fee policies:"
echo "lncli listchannels | jq '.channels[] | select(.chan_id | startswith(\"803265\") or startswith(\"779651\") or startswith(\"880360\")) | {chan_id: .chan_id[0:13], local_balance, remote_balance, fee_per_kw}'"
echo ""

echo "# Monitor routing revenue:"
echo "lncli fwdinghistory --start_time=\$(date -d '24 hours ago' +%s) | jq '.forwarding_events | length'"
echo ""

echo "# Check specific channel balance:"
echo "lncli listchannels --chan_id CHANNEL_ID"
echo ""

echo "🚀 RECOMMENDED IMPLEMENTATION ORDER:"
echo ""
echo "Week 1: Apply HIGH CONFIDENCE recommendations (10 channels)"
echo "        Expected revenue increase: ~+15,000 sats/month"
echo ""
echo "Week 2: Apply balance management for OUTBOUND flow (9 channels)"
echo "        Monitor for improved balance distribution"
echo ""
echo "Week 3: Apply balance preservation increases (5 channels)"
echo "        Watch for reduced outbound flow on these channels"
echo ""
echo "Week 4: Try low activity activation (3 channels)"
echo "        Lowest confidence - may not have significant impact"
echo ""

echo "⚠️ SAFETY REMINDERS:"
echo "- Changes take time to propagate through the network"
echo "- Monitor for 48+ hours before making more changes"
echo "- Keep a log of what you change and when"
echo "- Have the original fee rates ready for rollback"
echo ""

echo "Original rates for quick rollback:"
echo "lncli updatechanpolicy --chan_id 803265x3020x1 --fee_rate 209  # Rollback"
echo "lncli updatechanpolicy --chan_id 779651x576x1 --fee_rate 10    # Rollback"
echo "lncli updatechanpolicy --chan_id 880360x2328x1 --fee_rate 88   # Rollback"
echo "# ... (keep full list handy)"