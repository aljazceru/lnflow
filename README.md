# Lightning Policy Manager

Next-generation Lightning Network channel fee optimization with advanced inbound fee strategies, machine learning, and automatic rollback protection.

## Overview

Lightning Policy Manager is an intelligent fee management system that enhances the popular **charge-lnd** tool with:
- **Advanced inbound fee strategies** (beyond simple discounts)
- **Automatic rollback protection** for safety
- **Machine learning optimization** from historical data
- **Revenue maximization focus** vs simple rule-based approaches  
- **High-performance gRPC integration** with REST fallback
- **Comprehensive security** with method whitelisting
- **Complete charge-lnd compatibility**

## Repository Structure

```
lightning-fee-optimizer/
├── README.md                       # This file
├── pyproject.toml                  # Modern Python project config
├── requirements.txt                # Python dependencies
├── .gitignore                      # Git ignore rules
├──
├── src/                            # Main application source
│   ├── main.py                     # Application entry point
│   ├── api/                        # LND API clients
│   ├── experiment/                 # Experiment framework
│   ├── analysis/                   # Channel analysis
│   ├── policy/                     # Policy management engine
│   ├── strategy/                   # Fee optimization strategies
│   ├── utils/                      # Utilities & database
│   └── models/                     # Data models
├──
├── scripts/                        # Automation scripts
│   ├── setup_grpc.sh               # Secure gRPC setup
│   ├── advanced_fee_strategy.sh    # Advanced fee management
│   └── *.sh                       # Other automation scripts
├──
├── examples/                       # Configuration examples
│   ├── basic_policy.conf          # Simple policy example
│   └── advanced_policy.conf       # Advanced features demo
├──
├── docs/                           # Documentation
│   ├── LIGHTNING_POLICY_README.md    # Detailed guide
│   ├── SECURITY_ANALYSIS_REPORT.md   # Security audit
│   ├── GRPC_UPGRADE.md               # gRPC integration
│   └── *.md                          # Other documentation
├──
├── lightning_policy.py             # Main CLI tool
├── lightning_experiment.py        # Experiment runner
├── analyze_data.py                 # Data analysis tool
└── test_*.py                      # Test files
```

## Quick Start

### 1. Setup Environment
```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Setup secure gRPC (optional, for better performance)
./scripts/setup_grpc.sh
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

### High-Performance gRPC
- **10x faster** fee updates than REST
- **Native LND interface** (same as charge-lnd)
- **Automatic fallback** to REST if gRPC unavailable
- **Secure by design** - only fee management operations allowed

### Advanced Analytics
- **Policy performance tracking**
- **Revenue optimization reports**  
- **Channel analysis and insights**
- **Historical data learning**

## Security Features

- **Method whitelisting** - only fee management operations allowed
- **Runtime validation** - dangerous operations blocked
- **Comprehensive audit** - all operations logged
- **No fund movement** - only channel fee updates
- **Production-ready** - enterprise security standards

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

## Comparison with charge-lnd

| Feature | charge-lnd | Lightning Policy Manager |
|---------|------------|-------------------------|
| **Basic Fee Management** | Yes | Enhanced |
| **Inbound Fee Support** | Limited | Advanced strategies |
| **Performance Monitoring** | No | Automatic rollbacks |
| **Machine Learning** | No | Data-driven optimization |
| **API Performance** | gRPC only | gRPC + REST fallback |
| **Security** | Basic | Enterprise-grade |
| **Revenue Focus** | Rule-based | Revenue optimization |

## Testing

```bash
# Run tests
python -m pytest test_optimizer.py

# Test with your configuration
./lightning_policy.py -c your_config.conf apply --dry-run

# Test specific channel
./lightning_policy.py -c your_config.conf test-channel CHANNEL_ID
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Ensure security standards are maintained
6. Submit a pull request

## License

This project enhances and builds upon the open-source charge-lnd tool while adding significant new capabilities for Lightning Network fee optimization.

## Related Projects

- **[charge-lnd](https://github.com/accumulator/charge-lnd)** - Original fee management tool
- **[LND](https://github.com/lightningnetwork/lnd)** - Lightning Network Daemon

---

**Supercharge your Lightning Network channel fee management with intelligent, automated optimization!**