"""Configuration management for Lightning Fee Optimizer"""

import os
from typing import Optional, Dict, Any
from pathlib import Path
from dataclasses import dataclass, asdict
import json
from dotenv import load_dotenv


@dataclass
class OptimizationConfig:
    """Fee optimization configuration"""
    # Fee rate limits (ppm)
    min_fee_rate: int = 1
    max_fee_rate: int = 5000

    # Flow thresholds (sats)
    high_flow_threshold: int = 10_000_000
    low_flow_threshold: int = 1_000_000

    # Balance thresholds (ratio)
    high_balance_threshold: float = 0.8
    low_balance_threshold: float = 0.2

    # Strategy parameters
    fee_increase_factor: float = 1.5
    flow_preservation_weight: float = 0.6

    # Minimum changes to recommend
    min_fee_change_ppm: int = 5
    min_earnings_improvement: float = 100  # sats

    # Performance metric thresholds for scoring
    excellent_monthly_profit_sats: int = 10_000  # 10k sats/month
    excellent_monthly_flow_sats: int = 10_000_000  # 10M sats/month
    excellent_earnings_per_million_ppm: int = 1000  # 1000 ppm
    excellent_roi_ratio: float = 2.0  # 200% ROI

    # Channel categorization thresholds
    high_performance_score: float = 70.0
    min_profitable_sats: int = 100
    min_active_flow_sats: int = 1_000_000

    # Capacity tier thresholds (sats)
    high_capacity_threshold: int = 5_000_000
    medium_capacity_threshold: int = 1_000_000


@dataclass 
class APIConfig:
    """API connection configuration"""
    base_url: str = "http://localhost:18081"
    timeout: int = 30
    max_retries: int = 3
    retry_delay: float = 1.0


@dataclass
class Config:
    """Main configuration"""
    api: APIConfig
    optimization: OptimizationConfig
    
    # Runtime options
    verbose: bool = False
    dry_run: bool = True
    
    def __init__(self, config_file: Optional[str] = None):
        # Load defaults
        self.api = APIConfig()
        self.optimization = OptimizationConfig()
        self.verbose = False
        self.dry_run = True
        
        # Load from environment
        self._load_from_env()
        
        # Load from config file if provided
        if config_file:
            self._load_from_file(config_file)
    
    def _load_from_env(self):
        """Load configuration from environment variables"""
        load_dotenv()
        
        # API configuration
        if os.getenv('LFO_API_URL'):
            self.api.base_url = os.getenv('LFO_API_URL')
        if os.getenv('LFO_API_TIMEOUT'):
            self.api.timeout = int(os.getenv('LFO_API_TIMEOUT'))
        
        # Optimization parameters
        if os.getenv('LFO_MIN_FEE_RATE'):
            self.optimization.min_fee_rate = int(os.getenv('LFO_MIN_FEE_RATE'))
        if os.getenv('LFO_MAX_FEE_RATE'):
            self.optimization.max_fee_rate = int(os.getenv('LFO_MAX_FEE_RATE'))
        if os.getenv('LFO_HIGH_FLOW_THRESHOLD'):
            self.optimization.high_flow_threshold = int(os.getenv('LFO_HIGH_FLOW_THRESHOLD'))
        
        # Runtime options
        if os.getenv('LFO_VERBOSE'):
            self.verbose = os.getenv('LFO_VERBOSE').lower() in ('true', '1', 'yes')
        if os.getenv('LFO_DRY_RUN'):
            self.dry_run = os.getenv('LFO_DRY_RUN').lower() in ('true', '1', 'yes')
    
    def _load_from_file(self, config_file: str):
        """Load configuration from JSON file"""
        path = Path(config_file)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {config_file}")
        
        with open(path, 'r') as f:
            data = json.load(f)
        
        # Update API config
        if 'api' in data:
            for key, value in data['api'].items():
                if hasattr(self.api, key):
                    setattr(self.api, key, value)
        
        # Update optimization config
        if 'optimization' in data:
            for key, value in data['optimization'].items():
                if hasattr(self.optimization, key):
                    setattr(self.optimization, key, value)
        
        # Update runtime options
        if 'verbose' in data:
            self.verbose = data['verbose']
        if 'dry_run' in data:
            self.dry_run = data['dry_run']
    
    def save_to_file(self, config_file: str):
        """Save configuration to JSON file"""
        data = {
            'api': asdict(self.api),
            'optimization': asdict(self.optimization),
            'verbose': self.verbose,
            'dry_run': self.dry_run
        }
        
        path = Path(config_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
    
    @classmethod
    def load(cls, config_file: Optional[str] = None) -> 'Config':
        """Load configuration from file or environment"""
        return cls(config_file)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary"""
        return {
            'api': asdict(self.api),
            'optimization': asdict(self.optimization),
            'verbose': self.verbose,
            'dry_run': self.dry_run
        }