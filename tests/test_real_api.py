"""
Real API integration test for market order execution.
Uses the same adapters and executor as production.
"""
import sys
import os
import time
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from config import Config
from exchanges.binance import BinanceAdapter
from exchanges.bybit import BybitAdapter
from executor import ExecutionEngine


def build_adapters():
    cfg = Config("config.yaml")
    adapters = {}
    for name, ex_cfg in cfg.exchanges.items():
        if not ex_cfg.enabled:
            continue
        if name == "binance":
            adapters[name] = BinanceAdapter(ex_cfg.api_key, ex_cfg.api_secret, ex_cfg.testnet)
        elif name == "bybit":
            adapters[name] = BybitAdapter(ex_cfg.api_key, ex_cfg.api_secret, ex_cfg.testnet)
    return adapters


def get_real_prices(adapters):
    """Get real prices from both exchanges using direct HTTP API."""
    import requests

    # Binance testnet price (correct)
    resp = requests.get(
        "https://testnet.binancefuture.com/fapi/v1/ticker/price",
        params={"symbol": "BTCUSDT"},
        timeout=10,
    )
    price_binance = float(resp.json()["price"])

    # Bybit testnet: use indexPrice (markPrice is corrupted on testnet)
    resp = requests.get(
        "https://api-testnet.bybit.com/v5/market/tickers",
        params={"category": "linear", "symbol": "BTCUSDT"},
        timeout=10,
    )
    items = resp.json().get("result", {}).get("list", [])
    price_bybit = float(items[0]["indexPrice"]) if items else None

    print(f"\nReal prices: binance={price_binance}, bybit={price_bybit}")
    return price_binance, price_bybit


def _test_market_order_status_poll(adapters):
    """Test: place market order, poll status every second for 10 seconds."""
    print("\n=== Test: Market Order Status Polling ===")

    for name, adapter in adapters.items():
        print(f"\n--- {name} ---")

        # Set leverage
        ok = adapter.set_leverage("BTC-USDT", 10)
        print(f"  set_leverage(10): {ok}")

        # Get real price
        prices = get_real_prices(adapters)
        price = prices[0] if name == "binance" else prices[1]
        # Minimum: 100 USDT / price
        qty = max(0.002, 100 / price)
        print(f"  qty={qty} (min 100 USDT notional)")

        # Place market BUY
        print(f"  Placing MARKET BUY {qty} BTC-USDT...")
        order_id = adapter.place_market_order("BTC-USDT", "BUY", qty)
        print(f"  order_id: {order_id}")

        if order_id is None:
            print(f"  FAIL: order_id is None")
            continue

        # Poll status every second, 10 attempts
        print(f"  Polling status (every 1s, 10 attempts):")
        for attempt in range(10):
            time.sleep(1)
            status = adapter.get_order_status("BTC-USDT", order_id)
            print(f"    attempt {attempt + 1}: '{status}'")
            if status in ("filled", "cancelled", "partial"):
                print(f"  Settled: {status}")
                break

        # Close position
        print(f"  Closing position...")
        result = adapter.close_position("BTC-USDT")
        print(f"  close_position: {result}")


def _test_executor_market_flow(adapters, price_a, price_b):
    """Test: run full executor flow with market orders."""
    print(f"\n=== Test: Executor Market Order Flow ===")
    print(f"  prices: binance={price_a}, bybit={price_b}")

    adapter_a = adapters["binance"]
    adapter_b = adapters["bybit"]

    # Minimum qty: 100 USDT / price
    qty = max(0.002, min(100 / price_a, 100 / price_b))
    print(f"  qty={qty} BTC")

    # Set leverage
    adapter_a.set_leverage("BTC-USDT", 10)
    adapter_b.set_leverage("BTC-USDT", 10)

    engine = ExecutionEngine(timeout=30, poll_interval=1.0)

    print(f"  Executing arbitrage: binance BUY / bybit SELL qty={qty}")
    result = engine.execute_arbitrage(
        symbol="BTC-USDT",
        adapter_a=adapter_a,
        adapter_b=adapter_b,
        side_a="BUY",
        side_b="SELL",
        quantity_a=qty,
        quantity_b=qty,
        price_a=price_a,
        price_b=price_b,
        order_type="market",
    )

    print(f"\n  RESULT:")
    print(f"    status     : {result.status}")
    print(f"    order_a_id : {result.order_a_id}")
    print(f"    order_b_id : {result.order_b_id}")
    print(f"    fill_price_a: {result.fill_price_a}")
    print(f"    fill_price_b: {result.fill_price_b}")
    print(f"    error_a    : {result.error_a}")
    print(f"    error_b    : {result.error_b}")

    # Cleanup
    if result.status in ("filled", "partial_fill"):
        print(f"\n  Cleanup: closing positions...")
        adapter_a.close_position("BTC-USDT")
        adapter_b.close_position("BTC-USDT")

    return result


def main():
    print("=" * 60)
    print("REAL API INTEGRATION TEST — BTC-USDT Market Orders")
    print("=" * 60)

    adapters = build_adapters()
    print(f"Adapters: {list(adapters.keys())}")

    price_a, price_b = get_real_prices(adapters)
    _test_market_order_status_poll(adapters)
    result = _test_executor_market_flow(adapters, price_a, price_b)

    print("\n" + "=" * 60)
    if result.status == "filled":
        print("PASS: Both market orders filled successfully.")
    else:
        print(f"FAIL: status={result.status}")
        print(f"  order_a_id: {result.order_a_id}")
        print(f"  order_b_id: {result.order_b_id}")
        print(f"  error_a: {result.error_a}")
        print(f"  error_b: {result.error_b}")
        print("  Check logs above for order statuses.")


if __name__ == "__main__":
    main()
