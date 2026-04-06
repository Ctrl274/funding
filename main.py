"""
Funding Arbitrage System - Entry Point

Usage:
    python main.py                    # Start with UI (http://localhost:8888)
    python main.py --no-ui            # Background mode, no web UI
    python main.py --config prod.yaml # Custom config file
"""
import argparse
import logging
import sys
from pathlib import Path

from config import Config
from exchanges.binance import BinanceAdapter
from exchanges.bybit import BybitAdapter
from exchanges.bydfi import BydfiAdapter
from exchanges.mexc import MexcAdapter
from strategy import StrategyEngine
from executor import ExecutionEngine
from notifier import Notifier
from monitor import MonitorLoop
from db import Database

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def build_adapters(cfg: Config) -> dict:
    adapters = {}
    for name, ex_cfg in cfg.exchanges.items():
        if not ex_cfg.enabled:
            continue
        cls = {
            "binance": BinanceAdapter,
            "bybit": BybitAdapter,
            "bydfi": BydfiAdapter,
            "mexc": MexcAdapter,
        }.get(name)
        if cls:
            adapters[name] = cls(ex_cfg.api_key, ex_cfg.api_secret, ex_cfg.testnet)
    return adapters


def main():
    parser = argparse.ArgumentParser(description="Funding Arbitrage System")
    parser.add_argument("--config", default="config.yaml", help="Config file path")
    parser.add_argument("--no-ui", action="store_true", help="Skip web UI")
    parser.add_argument("--port", type=int, default=8888, help="Web UI port")
    args = parser.parse_args()

    cfg = Config(args.config)
    logger.info("Config loaded")

    adapters = build_adapters(cfg)
    logger.info(f"Adapters: {list(adapters.keys())}")

    strategy = StrategyEngine(
        min_rate_diff=cfg.strategy.min_rate_diff,
        max_concurrent=cfg.strategy.max_concurrent,
        position_mode=cfg.strategy.position_mode,
        position_value=cfg.strategy.position_value,
        position_percent=cfg.strategy.position_percent,
    )

    executor = ExecutionEngine()
    notifier = Notifier(
        webhook=cfg.notification.lark_webhook,
        detail_level=cfg.notification.detail_level,
    )
    db = Database()

    monitor = MonitorLoop(
        config=cfg,
        adapters=adapters,
        strategy=strategy,
        executor=executor,
        notifier=notifier,
    )

    if not args.no_ui:
        from web.app import create_app
        app = create_app(monitor_ref=monitor, config_ref=cfg, db_ref=db)
        logger.info(f"Starting web UI on http://localhost:{args.port}")
        monitor.start()
        app.run(host="0.0.0.0", port=args.port, debug=False, use_reloader=False)
    else:
        monitor.start()
        logger.info("Monitor running. Press Ctrl+C to stop.")
        try:
            import time
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            monitor.stop()
            logger.info("Stopped")


if __name__ == "__main__":
    main()
