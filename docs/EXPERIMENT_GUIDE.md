# Lightning Fee Optimization Experiment Guide

## Quick Start

1. **Install dependencies**:
```bash
pip install -r requirements.txt
```

2. **Initialize experiment**:
```bash
./lightning_experiment.py init --duration 7 --dry-run
```

3. **Check status**:
```bash
./lightning_experiment.py status
```

4. **Run single test cycle**:
```bash
./lightning_experiment.py cycle --dry-run
```

5. **Run full experiment**:
```bash
./lightning_experiment.py run --interval 30 --dry-run
```

## Commands

### `init` - Initialize Experiment
```bash
./lightning_experiment.py init [OPTIONS]

Options:
  --duration INTEGER       Experiment duration in days (default: 7)
  --macaroon-path TEXT    Path to admin.macaroon file
  --cert-path TEXT        Path to tls.cert file  
  --dry-run               Simulate without actual fee changes
```

**Example**: Initialize 5-day experiment with LND connection
```bash
./lightning_experiment.py init --duration 5 --macaroon-path ~/.lnd/data/chain/bitcoin/mainnet/admin.macaroon
```

### `status` - Show Current Status
```bash
./lightning_experiment.py status
```

Shows:
- Current experiment phase
- Elapsed time
- Data collection progress
- Recent activity summary

### `channels` - Show Channel Details  
```bash
./lightning_experiment.py channels [--group GROUP]
```

**Examples**:
```bash
./lightning_experiment.py channels                    # All channels
./lightning_experiment.py channels --group control    # Control group only
./lightning_experiment.py channels --group treatment_a # Treatment A only
```

### `changes` - Show Recent Fee Changes
```bash
./lightning_experiment.py changes [--hours HOURS]
```

**Example**:
```bash
./lightning_experiment.py changes --hours 12  # Last 12 hours
```

### `performance` - Show Performance Summary
```bash
./lightning_experiment.py performance
```

Shows revenue, flow efficiency, and balance health by experiment group.

### `cycle` - Run Single Cycle
```bash
./lightning_experiment.py cycle [OPTIONS]

Options:
  --dry-run               Simulate without actual changes
  --macaroon-path TEXT    Path to admin.macaroon
  --cert-path TEXT        Path to tls.cert
```

### `run` - Run Continuous Experiment
```bash
./lightning_experiment.py run [OPTIONS]

Options:
  --interval INTEGER      Collection interval in minutes (default: 30)
  --max-cycles INTEGER    Maximum cycles to run
  --dry-run              Simulate without actual changes
  --macaroon-path TEXT   Path to admin.macaroon
  --cert-path TEXT       Path to tls.cert
```

**Example**: Run for 100 cycles with 15-minute intervals
```bash
./lightning_experiment.py run --interval 15 --max-cycles 100 --macaroon-path ~/.lnd/admin.macaroon
```

### `report` - Generate Report
```bash
./lightning_experiment.py report [--output FILE]
```

**Example**:
```bash
./lightning_experiment.py report --output results.json
```

### `reset` - Reset Experiment
```bash
./lightning_experiment.py reset [--backup]
```

## Experiment Design

### Channel Groups

**Control Group (40%)**: No fee changes, baseline measurement
**Treatment A (30%)**: Balance-based optimization
- Reduce fees when local balance >80%  
- Increase fees when local balance <20%
- Apply inbound fees to control flow direction

**Treatment B (20%)**: Flow-based optimization  
- Increase fees on high-flow channels to test elasticity
- Reduce fees on dormant channels to activate

**Treatment C (10%)**: Advanced multi-strategy
- Game-theoretic competitive positioning
- Risk-adjusted optimization
- Network topology considerations

### Experiment Phases

1. **Baseline (24h)**: Data collection, no changes
2. **Initial (48h)**: Conservative 25% fee adjustments  
3. **Moderate (48h)**: 40% fee adjustments
4. **Aggressive (48h)**: Up to 50% fee adjustments
5. **Stabilization (24h)**: No changes, final measurement

### Safety Features

- **Automatic Rollbacks**: 30% revenue drop or 60% flow reduction
- **Maximum Changes**: 2 fee changes per channel per day
- **Fee Limits**: 1-5000 ppm range, max 50% change per update
- **Real-time Monitoring**: Health checks after each change

## Data Collection

### Collected Every 30 Minutes
- Channel balances and policies
- Flow reports and fee earnings  
- Peer connection status
- Network topology changes

### Stored Data
- `experiment_data/experiment_config.json` - Setup and parameters
- `experiment_data/experiment_data.csv` - Time series data
- `experiment_data/experiment_data.json` - Detailed data with metadata
- `experiment.log` - Operational logs

## Example Workflow

### 1. Development/Testing
```bash
# Start with dry-run to test setup
./lightning_experiment.py init --duration 1 --dry-run
./lightning_experiment.py status
./lightning_experiment.py cycle --dry-run
```

### 2. Real Experiment  
```bash
# Initialize with LND connection
./lightning_experiment.py init --duration 7 --macaroon-path ~/.lnd/admin.macaroon

# Run automated experiment
./lightning_experiment.py run --interval 30 --macaroon-path ~/.lnd/admin.macaroon

# Monitor progress (in another terminal)
watch -n 60 './lightning_experiment.py status'
```

### 3. Analysis
```bash
# Check performance during experiment
./lightning_experiment.py performance
./lightning_experiment.py changes --hours 24

# Generate final report
./lightning_experiment.py report --output final_results.json
```

## Tips

**Start Small**: Begin with `--dry-run` to validate setup and logic

**Monitor Closely**: Check status frequently during first few cycles

**Conservative Approach**: Use shorter duration (1-2 days) for initial runs

**Safety First**: Experiment will auto-rollback on revenue/flow drops

**Data Backup**: Use `reset --backup` to save data before resetting

**Log Analysis**: Check `experiment.log` for detailed operational information

## Troubleshooting

**"No experiment running"**: Run `init` command first

**"Failed to connect to LND"**: Check macaroon path and LND REST API accessibility

**"Channel not found"**: Ensure LND Manage API is running and accessible

**Permission errors**: Check file permissions for macaroon and cert files

**Network errors**: Verify URLs and network connectivity to APIs