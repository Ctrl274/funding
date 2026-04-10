"""Configuration loader for the funding arbitrage system."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import yaml


@dataclass(frozen=True)
class ExchangeConfig:
    """Configuration for a single exchange."""

    enabled: bool = False
    api_key: str = ""
    api_secret: str = ""
    testnet: bool = False


@dataclass(frozen=True)
class StrategyConfig:
    """Configuration for the arbitrage strategy."""

    min_rate_diff: float = 0.01
    order_type: str = "limit"
    position_mode: str = "fixed"
    position_value: float = 1000
    position_percent: float = 5.0
    leverage: int = 5
    max_concurrent: int = 3
    pre_settlement_seconds: int = 600
    partial_fill_action: str = "cancel_and_stop"


@dataclass(frozen=True)
class MonitorConfig:
    """Configuration for the monitoring system."""

    enabled: bool = True
    time_windows: List[str] = field(default_factory=list)
    polling_interval: int = 60


@dataclass(frozen=True)
class NotificationConfig:
    """Configuration for notifications."""

    enabled: bool = True
    lark_webhook: str = ""
    detail_level: str = "detailed"


class Config:
    """Loads and provides access to the YAML configuration file."""

    def __init__(self, config_path: str) -> None:
        self._config_path = Path(config_path)
        self._raw: dict = {}
        self._load()

    def _load(self) -> None:
        """Read and parse the YAML configuration file."""
        with open(self._config_path, "r", encoding="utf-8") as fh:
            self._raw = yaml.safe_load(fh) or {}

    def reload(self) -> None:
        """Re-read the configuration file from disk."""
        self._load()

    @property
    def exchanges(self) -> Dict[str, ExchangeConfig]:
        """Return a dict of exchange name -> ExchangeConfig."""
        raw_exchanges = self._raw.get("exchanges", {})
        result = {}
        for name, data in raw_exchanges.items():
            result[name] = ExchangeConfig(
                enabled=data.get("enabled", False),
                api_key=data.get("api_key", ""),
                api_secret=data.get("api_secret", ""),
                testnet=data.get("testnet", False),
            )
        return result

    @property
    def strategy(self) -> StrategyConfig:
        """Return the strategy configuration."""
        data = self._raw.get("strategy", {})
        return StrategyConfig(
            min_rate_diff=data.get("min_rate_diff", 0.01),
            order_type=data.get("order_type", "limit"),
            position_mode=data.get("position_mode", "fixed"),
            position_value=data.get("position_value", 1000),
            position_percent=data.get("position_percent", 5.0),
            leverage=data.get("leverage", 5),
            max_concurrent=data.get("max_concurrent", 3),
            pre_settlement_seconds=data.get("pre_settlement_seconds", 600),
            partial_fill_action=data.get("partial_fill_action", "cancel_and_stop"),
        )

    @property
    def monitor(self) -> MonitorConfig:
        """Return the monitor configuration."""
        data = self._raw.get("monitor", {})
        return MonitorConfig(
            enabled=data.get("enabled", True),
            time_windows=data.get("time_windows", []),
            polling_interval=data.get("polling_interval", 60),
        )

    @property
    def notification(self) -> NotificationConfig:
        """Return the notification configuration."""
        data = self._raw.get("notification", {})
        return NotificationConfig(
            enabled=data.get("enabled", True),
            lark_webhook=data.get("lark_webhook", ""),
            detail_level=data.get("detail_level", "detailed"),
        )

    def get_enabled_exchanges(self) -> List[str]:
        """Return a list of exchange names that are enabled."""
        return [
            name
            for name, cfg in self.exchanges.items()
            if cfg.enabled
        ]
