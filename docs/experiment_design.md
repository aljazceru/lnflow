# Lightning Fee Optimization Experiment Design

## Experiment Overview

**Duration**: 7 days  
**Objective**: Validate fee optimization strategies with controlled A/B testing  
**Fee Changes**: Maximum 2 times daily (morning 09:00 UTC, evening 21:00 UTC)  
**Risk Management**: Conservative approach with automatic rollbacks  

## Core Hypotheses to Test

### H1: Balance-Based Fee Strategy
**Hypothesis**: Channels with >80% local balance benefit from fee reductions, channels with <20% benefit from increases
- **Treatment**: Dynamic balance-based fee adjustments
- **Control**: Static fees
- **Metric**: Balance improvement + revenue change

### H2: Flow-Based Optimization  
**Hypothesis**: High-flow channels (>10M sats/month) can support 20-50% fee increases without significant flow loss
- **Treatment**: Graduated fee increases on high-flow channels
- **Control**: Current fees maintained
- **Metric**: Revenue per unit of flow

### H3: Competitive Response Theory
**Hypothesis**: Fee changes trigger competitive responses within 24-48 hours
- **Treatment**: Staggered fee changes across similar channels
- **Control**: Simultaneous changes
- **Metric**: Peer fee change correlation

### H4: Inbound Fee Effectiveness
**Hypothesis**: Inbound fees improve channel balance and reduce rebalancing costs
- **Treatment**: Strategic inbound fees (+/- based on balance)
- **Control**: Zero inbound fees
- **Metric**: Balance distribution + rebalancing frequency

### H5: Time-of-Day Optimization
**Hypothesis**: Optimal fee rates vary by time-of-day/week patterns
- **Treatment**: Dynamic hourly rate adjustments
- **Control**: Static rates
- **Metric**: Hourly revenue optimization

## Experimental Design

### Channel Selection Strategy

```
Total Channels: 41
├── Control Group (40%): 16 channels - No changes, baseline measurement
├── Treatment Group A (30%): 12 channels - Balance-based optimization  
├── Treatment Group B (20%): 8 channels - Flow-based optimization
└── Treatment Group C (10%): 5 channels - Advanced multi-strategy
```

**Selection Criteria**:
- Stratified sampling by capacity (small <1M, medium 1-5M, large >5M)
- Mix of active vs inactive channels
- Different peer types (routing nodes, wallets, exchanges)
- Geographic/timezone diversity if identifiable

### Randomization Protocol

1. **Baseline Period**: 24 hours pre-experiment with full data collection
2. **Random Assignment**: Channels randomly assigned to groups using `channel_id` hash
3. **Matched Pairs**: Similar channels split between control/treatment when possible
4. **Stratified Randomization**: Ensure representative distribution across capacity tiers

## Data Collection Framework

### Primary Data Sources

#### LND Manage API (Every 30 minutes)
- Channel balances and policies
- Flow reports (hourly aggregation)
- Fee earnings
- Warnings and status changes
- Node peer information

#### LND REST API (Every 15 minutes - New)
- Real-time payment forwarding events
- Channel state changes
- Network graph updates  
- Peer connection status
- Payment success/failure rates

#### Network Monitoring (Every 5 minutes)
- Network topology changes
- Competitor fee updates
- Global liquidity metrics
- Payment route availability

### Data Collection Schema

```python
{
  "timestamp": "2024-01-15T09:00:00Z",
  "experiment_hour": 24,  # Hours since experiment start
  "channel_data": {
    "channel_id": "803265x3020x1",
    "experiment_group": "treatment_a",
    "current_policy": {
      "outbound_fee_rate": 229,
      "inbound_fee_rate": 25,
      "base_fee": 0
    },
    "balance": {
      "local_sat": 1479380,
      "remote_sat": 6520620,
      "ratio": 0.185
    },
    "flow_metrics": {
      "forwarded_in_msat": 45230000,
      "forwarded_out_msat": 38120000,
      "fee_earned_msat": 2340,
      "events_count": 12
    },
    "network_position": {
      "peer_fee_rates": [209, 250, 180, 300],
      "alternative_routes": 8,
      "liquidity_rank_percentile": 0.75
    }
  }
}
```

## Fee Adjustment Strategy

### Conservative Bounds
- **Maximum Increase**: +50% or +100ppm per change, whichever is smaller
- **Maximum Decrease**: -30% or -50ppm per change, whichever is smaller  
- **Absolute Limits**: 1-2000 ppm range
- **Daily Change Limit**: Maximum 2 adjustments per 24h period

### Adjustment Schedule
```
Day 1-2: Baseline + Initial adjustments (25% changes)
Day 3-4: Moderate adjustments (40% changes) 
Day 5-6: Aggressive testing (50% changes)
Day 7: Stabilization and measurement
```

### Treatment Protocols

#### Treatment A: Balance-Based Optimization
```python
if local_balance_ratio > 0.8:
    new_fee = current_fee * 0.8  # Reduce to encourage outbound
    inbound_fee = -20  # Discount inbound
elif local_balance_ratio < 0.2:
    new_fee = current_fee * 1.3  # Increase to preserve local
    inbound_fee = +50  # Charge for inbound
```

#### Treatment B: Flow-Based Optimization  
```python
if monthly_flow > 10_000_000:
    new_fee = current_fee * 1.2  # Test demand elasticity
elif monthly_flow < 1_000_000:
    new_fee = current_fee * 0.7  # Activate dormant channels
```

#### Treatment C: Advanced Multi-Strategy
- Game-theoretic competitive response
- Risk-adjusted optimization  
- Network topology considerations
- Dynamic inbound fee management

## Automated Data Collection System

### Architecture
```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Data Sources  │────│  Collection API  │────│   TimeSeries    │
│                 │    │                  │    │    Database     │
│ • LND Manage    │    │ • Rate limiting  │    │                 │
│ • LND REST      │    │ • Error handling │    │ • InfluxDB      │
│ • Network Graph │    │ • Data validation│    │ • 5min retention│
│ • External APIs │    │ • Retry logic    │    │ • Aggregations  │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │
                       ┌──────────────────┐
                       │  Analysis Engine │
                       │                  │
                       │ • Statistical    │
                       │ • Visualization  │
                       │ • Alerts         │
                       │ • Reporting      │
                       └──────────────────┘
```

### Safety Mechanisms

#### Real-time Monitoring
- **Revenue Drop Alert**: >20% revenue decline triggers investigation
- **Flow Loss Alert**: >50% flow reduction triggers rollback consideration  
- **Balance Alert**: Channels reaching 95%+ local balance get priority attention
- **Peer Disconnection**: Monitor for correlation with fee changes

#### Automatic Rollback Triggers
```python
rollback_conditions = [
    "revenue_decline > 30% for 4+ hours",
    "flow_reduction > 60% for 2+ hours", 
    "channel_closure_detected",
    "peer_disconnection_rate > 20%",
    "rebalancing_costs > fee_earnings"
]
```

## Success Metrics & KPIs

### Primary Metrics
1. **Revenue Optimization**: Sats earned per day
2. **Capital Efficiency**: Revenue per sat of capacity  
3. **Flow Efficiency**: Maintained routing volume
4. **Balance Health**: Time spent in 30-70% local balance range

### Secondary Metrics
1. **Network Position**: Betweenness centrality maintenance
2. **Competitive Response**: Peer fee adjustment correlation
3. **Rebalancing Costs**: Reduction in manual rebalancing
4. **Payment Success Rate**: Forwarding success percentage

### Statistical Tests
- **A/B Testing**: Chi-square tests for categorical outcomes
- **Revenue Analysis**: Paired t-tests for before/after comparison
- **Time Series**: ARIMA modeling for trend analysis
- **Correlation Analysis**: Pearson/Spearman for fee-flow relationships

## Risk Management Protocol

### Financial Safeguards
- **Maximum Portfolio Loss**: 5% of monthly revenue
- **Per-Channel Loss Limit**: 10% of individual channel revenue
- **Emergency Stop**: Manual override capability
- **Rollback Budget**: Reserve 20% of expected gains for rollbacks

### Channel Health Monitoring
```python
health_checks = {
    "balance_extreme": "local_ratio < 0.05 or local_ratio > 0.95",
    "flow_stoppage": "zero_flow_hours > 6",
    "fee_spiral": "fee_changes > 4_in_24h",
    "peer_issues": "peer_offline_time > 2_hours"
}
```

## Implementation Timeline

### Pre-Experiment (Day -1)
- [ ] Deploy data collection infrastructure
- [ ] Validate API connections and data quality
- [ ] Run baseline measurements for 24 hours  
- [ ] Confirm randomization assignments
- [ ] Test rollback procedures

### Experiment Week (Days 1-7)
- [ ] **Day 1**: Start treatments, first fee adjustments
- [ ] **Day 2**: Monitor initial responses, adjust if needed
- [ ] **Day 3-4**: Scale up changes based on early results
- [ ] **Day 5-6**: Peak experimental phase  
- [ ] **Day 7**: Stabilization and final measurements

### Post-Experiment (Day +1)
- [ ] Complete data analysis
- [ ] Statistical significance testing
- [ ] Generate recommendations
- [ ] Plan follow-up experiments

## Expected Outcomes

### Hypothesis Validation
Each hypothesis will be tested with 95% confidence intervals:
- **Significant Result**: p-value < 0.05 with meaningful effect size
- **Inconclusive**: Insufficient data or conflicting signals  
- **Null Result**: No significant improvement over control

### Learning Objectives
1. **Elasticity Calibration**: Real demand elasticity measurements
2. **Competitive Dynamics**: Understanding of market responses
3. **Optimal Update Frequency**: Balance between optimization and stability
4. **Risk Factors**: Identification of high-risk scenarios
5. **Strategy Effectiveness**: Ranking of different optimization approaches

### Deliverables
1. **Experiment Report**: Statistical analysis of all hypotheses
2. **Improved Algorithm**: Data-driven optimization model
3. **Risk Assessment**: Updated risk management framework
4. **Best Practices**: Operational guidelines for fee management
5. **Future Research**: Roadmap for additional experiments

This experimental framework will provide the empirical foundation needed to transform theoretical optimization into proven, profitable strategies.