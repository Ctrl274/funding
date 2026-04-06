"""
Config loader with hot-reload.
Reads config.yaml from project root.
Hot-reloads on every property access (low-frequency, no timer needed).
"""
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Any


@dataclass
class ExchangeConfig:
    enabled: bool
    api_key: str
    api_secret: str
    testnet: bool = False


@dataclass
class StrategyConfig:
    min_rate_diff: float
    position_mode: str
    position_value: float
    position_percent: float
    max_concurrent: int
    pre_settlement_seconds: int
    partial_fill_action: str


@dataclass
class MonitorConfig:
    enabled: bool
    time_windows: List[str]
    polling_interval: int


@dataclass
class NotificationConfig:
    enabled: bool
    lark_webhook: str
    detail_level: str


class Config:
    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = Path(__file__).parent / "config.yaml"
        self._path = Path(config_path)
        self._raw = self._load()

    def _load(self) -> Dict[str, Any]:
        with open(self._path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def reload(self):
        self._raw = self._load()

    @property
    def exchanges(self) -> Dict[str, ExchangeConfig]:
        result = {}
        for name, cfg in self._raw.get("exchanges", {}).items():
            result[name] = ExchangeConfig(
                enabled=cfg.get("enabled", False),
                api_key=cfg.get("api_key", ""),
                api_secret=cfg.get("api_secret", ""),
                testnet=cfg.get("testnet", False),
            )
        return result

    def get_enabled_exchanges(self) -> List[str]:
        return [name for name, cfg in self.exchanges.items() if cfg.enabled]

    @property
    def strategy(self) -> StrategyConfig:
        s = self._raw.get("strategy", {})
        return StrategyConfig(
            min_rate_diff=s.get("min_rate_diff", 0.01),
            position_mode=s.get("position_mode", "fixed"),
            position_value=s.get("position_value", 1000),
            position_percent=s.get("position_percent", 5),
            max_concurrent=s.get("max_concurrent", 3),
            pre_settlement_seconds=s.get("pre_settlement_seconds", 600),
            partial_fill_action=s.get("partial_fill_action", "cancel_and_stop"),
        )

    @property
    def monitor(self) -> MonitorConfig:
        m = self._raw.get("monitor", {})
        return MonitorConfig(
            enabled=m.get("enabled", True),
            time_windows=m.get("time_windows", []),
            polling_interval=m.get("polling_interval", 60),
        )

    @property
    def notification(self) -> NotificationConfig:
        n = self._raw.get("notification", {})
        return NotificationConfig(
            enabled=n.get("enabled", True),
            lark_webhook=n.get("lark_webhook", ""),
            detail_level=n.get("detail_level", "detailed"),
        )
