# Missed Routing Opportunities Detection

Lightning Fee Optimizer now includes advanced **missed routing opportunity detection**, similar to [lightning-jet](https://github.com/itsneski/lightning-jet), to help you maximize routing revenue.

## Overview

This feature monitors HTLC (Hash Time Locked Contract) events and forwarding history to identify when your node could have routed payments but didn't due to:
- **Insufficient liquidity** (channel depleted)
- **High fees** (routing failed due to fee policies)
- **Channel imbalances** (one-sided channels)
- **Capacity constraints** (channel too small for demand)

## Features

### 1. Real-Time HTLC Monitoring
- Subscribes to LND's HTLC event stream
- Tracks forwarding successes and failures
- Identifies failure patterns by channel
- Calculates missed revenue in real-time

### 2. Opportunity Analysis
- Quantifies missed routing opportunities
- Calculates potential monthly revenue
- Generates urgency scores (0-100)
- Provides actionable recommendations

### 3. Recommendation Engine
Automatically recommends actions:
- **Rebalance** - Add inbound/outbound liquidity
- **Lower fees** - Reduce fee rates to capture volume
- **Increase capacity** - Open additional channels
- **Investigate** - Manual review needed

## Installation

The opportunity detection modules are included in the main lnflow package:

```bash
# Install dependencies (if not already installed)
pip install -r requirements.txt

# The HTLC analyzer CLI is ready to use
python lightning_htlc_analyzer.py --help
```

## Usage

### Quick Start - Analyze Historical Data

Analyze your last 24 hours of forwarding history:

```bash
python lightning_htlc_analyzer.py analyze --hours 24
```

Example output:
```
MISSED ROUTING OPPORTUNITIES

Rank  Channel              Peer                 Failures  Missed Revenue  Potential/Month  Urgency  Recommendation
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
1     8123456789abcdef... ACINQ                15        1,234.56 sats   12,345 sats      85       Rebalance Inbound
2     9876543210fedcba... CoinGate             8         543.21 sats     5,432 sats       62       Lower Fees
3     abcdef1234567890... Bitrefill            5         234.12 sats     2,341 sats       45       Increase Capacity
```

### Real-Time Monitoring

Monitor HTLC events in real-time (requires LND 0.14+):

```bash
python lightning_htlc_analyzer.py monitor --duration 24
```

This will:
1. Subscribe to HTLC events from your LND node
2. Track failures and successes in real-time
3. Display stats every minute
4. Analyze opportunities after monitoring period

### Advanced Usage

```bash
# Analyze specific time window
python lightning_htlc_analyzer.py analyze \
    --hours 168 \
    --lnd-dir ~/.lnd \
    --grpc-host localhost:10009 \
    --manage-url http://localhost:18081 \
    --output opportunities.json

# Monitor with custom LND setup
python lightning_htlc_analyzer.py monitor \
    --duration 48 \
    --lnd-dir /path/to/lnd \
    --grpc-host 192.168.1.100:10009 \
    --output realtime_opportunities.json

# Generate report from saved data
python lightning_htlc_analyzer.py report opportunities.json
```

## Programmatic Usage

You can also use the opportunity detection modules in your Python code:

```python
import asyncio
from src.monitoring.htlc_monitor import HTLCMonitor
from src.monitoring.opportunity_analyzer import OpportunityAnalyzer
from src.api.client import LndManageClient
from src.experiment.lnd_grpc_client import AsyncLNDgRPCClient

async def find_opportunities():
    # Setup clients
    async with AsyncLNDgRPCClient(lnd_dir='~/.lnd') as grpc_client:
        async with LndManageClient('http://localhost:18081') as lnd_manage:
            # Create monitor
            monitor = HTLCMonitor(
                grpc_client=grpc_client,
                history_hours=24,
                min_failure_count=3,
                min_missed_sats=100
            )

            # Start monitoring
            await monitor.start_monitoring()

            # Let it run for a while
            await asyncio.sleep(3600)  # 1 hour

            # Stop and analyze
            await monitor.stop_monitoring()

            # Analyze opportunities
            analyzer = OpportunityAnalyzer(monitor, lnd_manage)
            opportunities = await analyzer.analyze_opportunities()

            # Display top opportunities
            for opp in opportunities[:10]:
                print(f"{opp.channel_id}: {opp.recommended_action}")
                print(f"  Potential: {opp.potential_monthly_revenue_sats} sats/month")
                print(f"  Urgency: {opp.urgency_score}/100\n")

asyncio.run(find_opportunities())
```

## Understanding the Output

### Opportunity Metrics

- **Failures**: Number of failed forwards on this channel
- **Missed Revenue**: Fees you would have earned if forwards succeeded
- **Potential/Month**: Extrapolated monthly revenue opportunity
- **Urgency**: Score 0-100 based on revenue potential and failure frequency

### Urgency Score Calculation

```
Urgency = Revenue Score (0-40) + Frequency Score (0-30) + Rate Score (0-30)

Revenue Score = min(40, (missed_sats / 1000) * 4)
Frequency Score = min(30, (failures / 10) * 30)
Rate Score = failure_rate * 30
```

### Recommendation Types

| Type | Meaning | Action |
|------|---------|--------|
| `rebalance_inbound` | Channel has too much local balance | Add inbound liquidity (push sats to remote) |
| `rebalance_outbound` | Channel has too much remote balance | Add outbound liquidity (circular rebalance) |
| `lower_fees` | Fees too high relative to network | Reduce fee rates by ~30% |
| `increase_capacity` | Channel capacity insufficient | Open additional channel to this peer |
| `investigate` | Mixed failure patterns | Manual investigation needed |

## Integration with Policy Engine

The opportunity detection can inform your policy engine decisions:

```python
from src.policy.manager import PolicyManager
from src.monitoring.opportunity_analyzer import OpportunityAnalyzer

# Get opportunities
analyzer = OpportunityAnalyzer(monitor, lnd_manage_client)
fee_opportunities = await analyzer.get_fee_opportunities()

# Update policies for fee-constrained channels
for opp in fee_opportunities:
    print(f"Reducing fee on channel {opp.channel_id}")
    print(f"  Current: {opp.current_outbound_fee_ppm} ppm")
    print(f"  Recommended: {int(opp.current_outbound_fee_ppm * 0.7)} ppm")

# Apply via policy manager
policy_manager = PolicyManager(
    config_file='config/policies.conf',
    lnd_manage_url='http://localhost:18081',
    lnd_grpc_host='localhost:10009'
)

# Policies will automatically optimize for missed opportunities
```

## Configuration

### HTLC Monitor Settings

```python
monitor = HTLCMonitor(
    grpc_client=grpc_client,
    history_hours=24,           # How long to keep event history
    min_failure_count=3,        # Minimum failures to flag
    min_missed_sats=100         # Minimum missed revenue to flag
)
```

### Opportunity Analyzer Settings

```python
analyzer = OpportunityAnalyzer(
    htlc_monitor=monitor,
    lnd_manage_client=client,
    min_opportunity_sats=100,   # Minimum to report
    analysis_window_hours=24     # Time window for analysis
)
```

## Comparison with lightning-jet

| Feature | lnflow | lightning-jet |
|---------|--------|---------------|
| HTLC Event Monitoring | ✅ | ✅ |
| Forwarding History Analysis | ✅ | ✅ |
| Real-time Detection | ✅ | ✅ |
| Opportunity Quantification | ✅ | ⚠️ Limited |
| Actionable Recommendations | ✅ | ⚠️ Basic |
| Policy Engine Integration | ✅ | ❌ |
| Fee Optimization | ✅ | ❌ |
| Automated Rebalancing | 🔄 Coming Soon | ❌ |

## Requirements

- **LND Version**: 0.14.0+ (for HTLC subscriptions)
- **LND Manage API**: Running and accessible
- **gRPC Access**: admin.macaroon or charge-lnd.macaroon

## Troubleshooting

### "HTLC monitoring requires LND 0.14+"

Your LND version doesn't support HTLC event subscriptions. You can still use forwarding history analysis:

```bash
python lightning_htlc_analyzer.py analyze --hours 168
```

### "Failed to connect via gRPC"

Check your LND gRPC configuration:

```bash
# Verify gRPC is accessible
lncli --network=mainnet getinfo

# Check macaroon permissions
ls -la ~/.lnd/data/chain/bitcoin/mainnet/
```

### No opportunities detected

This could mean:
1. Your node is already well-optimized
2. Not enough routing volume
3. Monitoring period too short

Try increasing the analysis window:

```bash
python lightning_htlc_analyzer.py analyze --hours 168  # 7 days
```

## Performance

- HTLC monitoring: ~1-5 MB memory per 1000 events
- Analysis: <100ms for 100 channels
- Database: Event history auto-cleaned after configured TTL

## Future Enhancements

- [ ] Automated fee adjustment based on opportunities
- [ ] Integration with circular rebalancing
- [ ] Peer scoring based on routing success
- [ ] Network-wide opportunity comparison
- [ ] ML-based failure prediction
- [ ] Automated capacity management

## Examples

See [examples/htlc_monitoring.py](../examples/htlc_monitoring.py) for complete working examples.

## API Reference

See the inline documentation in:
- [`src/monitoring/htlc_monitor.py`](../src/monitoring/htlc_monitor.py)
- [`src/monitoring/opportunity_analyzer.py`](../src/monitoring/opportunity_analyzer.py)

## Contributing

Found a bug or have an enhancement idea? Open an issue or PR!

---

**Note**: This feature significantly extends the capabilities of charge-lnd by adding revenue optimization insights that aren't available in the original tool.
