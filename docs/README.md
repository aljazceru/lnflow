# Lightning Fee Optimizer

An intelligent Lightning Network channel fee optimization agent that analyzes your channel performance and suggests optimal fee strategies to maximize returns.

## Features

- **Real-time Data Analysis**: Ingests comprehensive channel data from LND Manage API
- **Intelligent Optimization**: Uses machine learning-inspired algorithms to optimize fees based on:
  - Channel flow patterns
  - Historical earnings
  - Balance distribution
  - Demand elasticity estimation
- **Multiple Strategies**: Conservative, Balanced, and Aggressive optimization approaches
- **Detailed Reporting**: Rich terminal output with categorized recommendations
- **Risk Assessment**: Confidence levels and impact projections for each recommendation

## Installation

```bash
# Clone the repository
git clone <repo-url>
cd lightning-fee-optimizer

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Requirements

- **LND Manage API**: Running at `http://localhost:18081` (or configured URL)
- **Python 3.8+**
- **Synced Lightning Node**: Must be synced to the blockchain

## Quick Start

1. **Test the connection**:
```bash
python test_optimizer.py
```

2. **Run analysis only** (no recommendations):
```bash
python -m src.main --analyze-only
```

3. **Generate optimization recommendations**:
```bash
python -m src.main --dry-run
```

4. **Save recommendations to file**:
```bash
python -m src.main --output recommendations.json
```

## Command Line Options

```bash
python -m src.main [OPTIONS]

Options:
  --api-url TEXT           LND Manage API URL [default: http://localhost:18081]
  --config PATH           Configuration file path
  --analyze-only          Only analyze channels without optimization
  --dry-run              Show recommendations without applying them
  --verbose, -v          Enable verbose logging
  --output, -o PATH      Output recommendations to file
  --help                 Show this message and exit
```

## Configuration

Create a `config.json` file to customize optimization parameters:

```json
{
  "api": {
    "base_url": "http://localhost:18081",
    "timeout": 30
  },
  "optimization": {
    "min_fee_rate": 1,
    "max_fee_rate": 5000,
    "high_flow_threshold": 10000000,
    "low_flow_threshold": 1000000,
    "high_balance_threshold": 0.8,
    "low_balance_threshold": 0.2,
    "fee_increase_factor": 1.5
  },
  "dry_run": true
}
```

## How It Works

### 1. Data Collection
- Fetches comprehensive channel data via LND Manage API
- Includes balance, flow reports, fee earnings, and policies
- Collects 7-day and 30-day historical data

### 2. Channel Analysis
The system calculates multiple performance metrics:

- **Profitability Score**: Based on net profit and ROI
- **Activity Score**: Flow volume and consistency
- **Efficiency Score**: Earnings per unit of flow
- **Flow Efficiency**: How balanced bidirectional flow is
- **Overall Score**: Weighted combination of all metrics

### 3. Channel Categorization
Channels are automatically categorized:

- **High Performers**: >70 overall score
- **Profitable**: Positive earnings >100 sats
- **Active Unprofitable**: High flow but low fees
- **Inactive**: <1M sats monthly flow
- **Problematic**: Issues requiring attention

### 4. Optimization Strategies

#### Conservative Strategy
- Minimal fee changes
- High flow preservation weight (0.8)
- 20% maximum fee increase

#### Balanced Strategy (Default)
- Moderate fee adjustments
- Balanced flow preservation (0.6)
- 50% maximum fee increase

#### Aggressive Strategy
- Significant fee increases
- Lower flow preservation (0.3)
- 100% maximum fee increase

### 5. Recommendation Generation

For each channel category, different optimization approaches:

**High Performers**: Minimal increases to test demand elasticity
**Underperformers**: Significant fee increases based on flow volume
**Imbalanced Channels**: Fee adjustments to encourage rebalancing
**Inactive Channels**: Fee reductions to attract routing

## Example Output

```
Lightning Fee Optimizer

✅ Checking node connection...
📦 Current block height: 906504

📊 Fetching channel data...
🔗 Found 41 channels

🔬 Analyzing channel performance...
✅ Successfully analyzed 41 channels

╭────────────────────────────── Network Overview ──────────────────────────────╮
│ Total Channels: 41                                                             │
│ Total Capacity: 137,420,508 sats                                              │
│ Monthly Earnings: 230,541 sats                                                │
│ Monthly Costs: 15,230 sats                                                    │
│ Net Profit: 215,311 sats                                                      │
╰────────────────────────────────────────────────────────────────────────────────╯

High Performers: 8 channels
┏━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━┳━━━━━━━┓
┃ Channel       ┃ Alias          ┃ Score ┃ Profit ┃  Flow ┃
┡━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━╇━━━━━━━┩
│ 779651x576x1  │ WalletOfSatoshi│  89.2 │ 36,385 │158.8M │
│ 721508x1824x1 │ node_way_jose  │  87.5 │  9,561 │ 65.5M │
└───────────────┴────────────────┴───────┴────────┴───────┘

⚡ Generating fee optimization recommendations...

╭────────────────────────── Fee Optimization Results ──────────────────────────╮
│ Total Recommendations: 23                                                      │
│ Current Monthly Earnings: 230,541 sats                                        │
│ Projected Monthly Earnings: 287,162 sats                                      │
│ Estimated Improvement: +24.6%                                                 │
╰────────────────────────────────────────────────────────────────────────────────╯
```

## Data Sources

The optimizer uses the following LND Manage API endpoints:
- `/api/status/` - Node status and health
- `/api/channel/{id}/details` - Comprehensive channel data
- `/api/channel/{id}/flow-report/last-days/{days}` - Flow analysis
- `/api/node/{pubkey}/details` - Peer information

## Integration with Balance of Satori

If you have Balance of Satori installed, you can use the recommendations to:

1. **Manually apply fee changes**: Use the recommended fee rates
2. **Rebalancing decisions**: Identify channels needing liquidity management
3. **Channel management**: Close underperforming channels, open new ones

## Safety Features

- **Dry-run by default**: Never applies changes automatically
- **Conservative limits**: Prevents extreme fee adjustments
- **Confidence scoring**: Each recommendation includes confidence level
- **Impact estimation**: Projected effects on flow and earnings

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

## Troubleshooting

**Connection Issues**:
- Verify LND Manage API is running
- Check API URL configuration
- Ensure node is synced

**No Recommendations**:
- Verify channels have sufficient historical data
- Check that channels are active
- Review configuration thresholds

**Performance Issues**:
- Reduce the number of channels analyzed
- Use configuration to filter by capacity
- Enable verbose logging to identify bottlenecks

## License

MIT License - see LICENSE file for details.