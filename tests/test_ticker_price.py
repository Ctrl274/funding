"""
Diagnose: bybit fetch_order always returns 'unknown'.
Run directly to see the actual exception.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
logging.basicConfig(level=logging.DEBUG, format="%(name)s: %(message)s")

from exchanges.bybit import BybitAdapter

adapter = BybitAdapter(
    "s1YL7K1oo8oJznkyjJ",
    "Le4gw3yX2ylMUyaYEVRjVgxlJ40iGXVKX9Tk",
    True,  # testnet
)

# First place a real order
adapter.set_leverage("BTC-USDT", 10)
print("Setting leverage: done")

print("\nPlacing market BUY 0.002 BTC-USDT...")
order_id = adapter.place_market_order("BTC-USDT", "BUY", 0.002)
print(f"order_id: {order_id}")

import time
time.sleep(1)

print(f"\nCalling get_order_status('{order_id}')...")
status = adapter.get_order_status("BTC-USDT", order_id)
print(f"status: {status}")

print(f"\nCalling ccxt fetch_order directly...")
try:
    order = adapter._client.fetch_order(order_id, adapter._normalize_symbol("BTC-USDT"))
    print(f"order: {order}")
except Exception as e:
    print(f"Exception type: {type(e).__name__}")
    print(f"Exception: {e}")

# Cleanup
print("\nClosing position...")
adapter.close_position("BTC-USDT")
