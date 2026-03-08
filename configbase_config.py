"""
Base Configuration for Operation Capital Vector
Centralized configuration management with environment variable fallbacks
"""
import os
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class AgentConfig:
    """Configuration for individual agent types"""
    hypothesis_workers: int = 3
    backtest_workers: int = 5
    execution_workers: int = 2
    sentinel_workers: int = 2
    cycle_interval_seconds: int = 300  # Main loop interval

@dataclass
class TradingConfig:
    """Trading-specific parameters"""
    min_win_rate: float = 0.55
    max_drawdown: float = -0.15
    min_expected_value: float = 0.002
    position_size_pct: float = 0.02  # 2% per trade
    stop_loss_pct: float = -0.015  # 1.5% stop loss
    take_profit_pct: float = 0.03   # 3% take profit

@dataclass
class NetworkConfig:
    """Network and RPC configuration"""
    base_rpc_url: str = "https://mainnet.base.org"
    flashbots_rpc_url: str = "https://rpc.flashbots.net"
    backup_rpcs: list = field(default_factory=lambda: [
        "https://base.publicnode.com",
        "https://1rpc.io/base"
    ])
    block_time_threshold: int = 15  # seconds
    max_reorg_depth: int = 2

@dataclass
class HardwareFundConfig:
    """Hardware fund routing configuration"""
    treasury_threshold_1: float = 1000.0  # USD
    treasury_threshold_2: float = 2500.0  # USD
    allocation_phase_1: float = 1.0  # 100% to trading
    allocation_phase_2: float = 0.7  # 70% to hardware, 30% trading
    hardware_wallet_address: Optional[str] = None

@dataclass
class FirebaseConfig:
    """Firebase Firestore configuration"""
    project_id: Optional[str] = None
    credentials_path: Optional[str] = None
    
    def validate(self) -> bool:
        """Validate Firebase configuration"""
        if not self.project_id:
            logger.error("Firebase project_id not configured")
            return False
        return True

class BaseConfig:
    """Main configuration singleton"""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(BaseConfig, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """Initialize configuration from environment variables"""
        # Firebase
        self.firebase = FirebaseConfig(
            project_id=os.getenv("FIREBASE_PROJECT_ID", "capital-vector"),
            credentials_path=os.getenv("FIREBASE_CREDENTIALS_PATH", "firebase-credentials.json")
        )
        
        # Agent Configuration
        self.agent = AgentConfig(
            hypothesis_workers=int(os.getenv("HYPOTHESIS_WORKERS", "3")),
            backtest_workers=int(os.getenv("BACKTEST_WORKERS", "5")),
            execution_workers=int(os.getenv("EXECUTION_WORKERS", "2")),
            cycle_interval_seconds=int(os.getenv("CYCLE_INTERVAL", "300"))
        )
        
        # Trading Configuration
        self.trading = TradingConfig(
            min_win_rate=float(os.getenv("MIN_WIN_RATE", "0.55")),
            max_drawdown=float(os.getenv("MAX_DRAWDOWN", "-0.15")),
            position_size_pct=float(os.getenv("POSITION_SIZE", "0.02"))
        )
        
        # Network Configuration
        self.network = NetworkConfig(
            base_rpc_url=os.getenv("BASE_RPC_URL", "https://mainnet.base.org"),
            block_time_threshold=int(os.getenv("BLOCK_TIME_THRESHOLD", "15"))
        )
        
        # Hardware Fund Configuration
        self.hardware_fund = HardwareFundConfig(
            treasury_threshold_1=float(os.getenv("TREASURY_THRESHOLD_1", "1000.0")),
            hardware_wallet_address=os.getenv("HARDWARE_WALLET_ADDRESS")
        )
        
        # System State
        self.system_mode: str = "NORMAL"  # NORMAL, DARK_MODE, PAUSED
        self.treasury_value: float = 0.0
        self.last_profit_timestamp: Optional[str] = None
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary for logging"""
        return {
            "system_mode": self.system_mode,
            "treasury_value": self.treasury_value,
            "agent_config": self.agent.__dict__,
            "trading_config": self.trading.__dict__,
            "hardware_fund_config": self.hardware_fund.__dict__
        }
    
    def validate_all(self) -> bool:
        """Validate all configurations"""
        validations = [
            ("Firebase", self.firebase.validate()),
            ("Trading Config", self.trading.position_size_pct > 0),
            ("Network Config", len(self.network.backup_rpcs) > 0)
        ]
        
        for name, result in validations:
            if not result:
                logger.error(f"Validation failed for {name}")
                return False
        
        logger.info("All configurations validated successfully")
        return True

# Global configuration instance
config = BaseConfig()