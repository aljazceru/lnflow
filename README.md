# Lightning Policy Manager

Next-generation Lightning Network channel fee optimization with advanced inbound fee strategies, machine learning, and automatic rollback protection.

## Quick Start

### 1. Setup Environment
```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt


```

### 2. Generate Configuration
```bash
# Create a sample policy configuration
./lightning_policy.py generate-config my_policy.conf
```

### 3. Test Policies (Dry Run)
```bash
# Test your policies without applying changes
./lightning_policy.py -c my_policy.conf apply --dry-run
```

### 4. Apply Policies
```bash
# Apply fee changes via high-performance gRPC
./lightning_policy.py -c my_policy.conf apply

# Or use REST API
./lightning_policy.py --prefer-rest -c my_policy.conf apply
```

## Key Features

### Intelligent Inbound Fee Strategies
```ini
[balance-drain-channels]
chan.min_ratio = 0.8              # High local balance
strategy = balance_based
inbound_fee_ppm = -100            # Encourage inbound flow
```

### Automatic Rollback Protection  
```ini
[revenue-channels]
strategy = revenue_max
enable_auto_rollback = true       # Monitor performance
rollback_threshold = 0.25         # Rollback if revenue drops >25%
```



### Advanced Analytics
- **Policy performance tracking**
- **Revenue optimization reports**  
- **Channel analysis and insights**
- **Historical data learning**


## Documentation

- **[Lightning Policy Guide](docs/LIGHTNING_POLICY_README.md)** - Complete feature overview
- **[Security Analysis](docs/SECURITY_ANALYSIS_REPORT.md)** - Comprehensive security audit  
- **[gRPC Integration](docs/GRPC_UPGRADE.md)** - High-performance setup guide
- **[Experiment Guide](docs/EXPERIMENT_GUIDE.md)** - Advanced experimentation

## CLI Commands

```bash
# Policy Management
./lightning_policy.py apply          # Apply policies
./lightning_policy.py status         # Show policy status
./lightning_policy.py rollback       # Check/execute rollbacks
./lightning_policy.py daemon --watch # Run in daemon mode

# Analysis & Reports
./lightning_policy.py report         # Performance report
./lightning_policy.py test-channel   # Test specific channel

# Configuration
./lightning_policy.py generate-config # Create sample config
```

## Configuration Options

```bash
# gRPC (preferred - 10x faster)
--lnd-grpc-host localhost:10009      # LND gRPC endpoint
--prefer-grpc                        # Use gRPC (default)

# REST API (fallback)  
--lnd-rest-url https://localhost:8080 # LND REST endpoint
--prefer-rest                         # Force REST API

# Authentication
--lnd-dir ~/.lnd                     # LND directory
--macaroon-path admin.macaroon       # Macaroon file
```

## Testing

```bash
# Run tests
python -m pytest test_optimizer.py

# Test with your configuration
./lightning_policy.py -c your_config.conf apply --dry-run

# Test specific channel
./lightning_policy.py -c your_config.conf test-channel CHANNEL_ID
```
