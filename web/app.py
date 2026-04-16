"""
Flask Web UI Backend.
Provides REST API for the frontend.
"""
from flask import Flask, jsonify, request, render_template
from pathlib import Path


def create_app(monitor_ref=None, config_ref=None, db_ref=None):
    app = Flask(__name__, template_folder="templates", static_folder="static")

    app.monitor = monitor_ref
    app.config_obj = config_ref
    app.db = db_ref

    @app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        return response

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/settings")
    def settings_page():
        return render_template("settings.html")

    @app.route("/positions")
    def positions_page():
        return render_template("positions.html")

    @app.route("/history")
    def history_page():
        return render_template("history.html")

    # --- REST API ---

    @app.route("/api/status")
    def api_status():
        """System status."""
        monitor = app.monitor
        import time
        import math
        settlement_dt = None
        settlement_ts = None
        countdown_seconds = None
        if monitor:
            # Use filtered rates (same logic as frontend) to get nearest settlement
            all_rates = monitor.get_current_rates()
            nearest_ts = None
            for ex_rates in all_rates.values():
                for fr in ex_rates.values():
                    if fr.next_settlement <= 0:
                        continue
                    # Only consider symbols present in at least 2 exchanges
                    count = sum(
                        1 for ex, rates in all_rates.items()
                        if fr.symbol in rates and rates[fr.symbol].next_settlement > 0
                    )
                    if count < 2:
                        continue
                    # Check settlement time diff < 5min across exchanges
                    settlements = [
                        rates[fr.symbol].next_settlement
                        for rates in all_rates.values()
                        if fr.symbol in rates and rates[fr.symbol].next_settlement > 0
                    ]
                    if not settlements:
                        continue
                    if max(settlements) - min(settlements) > 300:
                        continue
                    if nearest_ts is None or fr.next_settlement < nearest_ts:
                        nearest_ts = fr.next_settlement

            if nearest_ts:
                settlement_ts = nearest_ts
                from datetime import datetime, timezone, timedelta
                settlement_dt = datetime.fromtimestamp(nearest_ts, tz=timezone(timedelta(hours=8)))
                countdown_seconds = math.floor(max(0, nearest_ts - time.time()))

        return jsonify({
            "monitor_enabled": app.config_obj.monitor.enabled if app.config_obj else True,
            "next_settlement": settlement_dt.isoformat() if settlement_dt else None,
            "next_settlement_ts": settlement_ts,
            "countdown_seconds": countdown_seconds,
            "current_positions": len(monitor.get_positions()) if monitor else 0,
        })

    @app.route("/api/rates")
    def api_rates():
        """Live funding rates."""
        monitor = app.monitor
        if not monitor:
            return jsonify([])
        all_rates = monitor.get_current_rates()
        # Flatten to list
        rows = []
        symbols = set()
        for ex_rates in all_rates.values():
            symbols.update(ex_rates.keys())
        for sym in sorted(symbols):
            row = {"symbol": sym}
            for ex, rates in all_rates.items():
                fr = rates.get(sym)
                if fr:
                    row[f"{ex}_rate"] = fr.rate_percent
                    row[f"{ex}_next_settlement_ts"] = fr.next_settlement
                else:
                    row[f"{ex}_rate"] = None
                    row[f"{ex}_next_settlement_ts"] = None
            rows.append(row)
        return jsonify(rows)

    @app.route("/api/positions")
    def api_positions():
        """Current positions."""
        monitor = app.monitor
        if not monitor:
            return jsonify([])
        result = []
        for symbol, pos in monitor.get_positions().items():
            item = dict(pos)
            item["symbol"] = symbol
            result.append(item)
        return jsonify(result)

    @app.route("/api/positions/<symbol>/close", methods=["POST"])
    def api_close_position(symbol):
        """Manually close a position."""
        monitor = app.monitor
        if not monitor:
            return jsonify({"error": "monitor not available"}), 500
        result = monitor.close_position(symbol)
        return jsonify({
            "symbol": symbol,
            "status": result.get("status", "closed"),
            "close_results": result.get("close_results", {}),
        })

    @app.route("/api/history")
    def api_history():
        """Paginated history records. Returns {items, total, limit, offset}."""
        limit = request.args.get("limit", 20, type=int)
        offset = request.args.get("offset", 0, type=int)
        if limit is None or limit < 1:
            limit = 20
        if offset is None or offset < 0:
            offset = 0
        if app.db:
            return jsonify(app.db.get_history(limit=limit, offset=offset))
        return jsonify({"items": [], "total": 0, "limit": limit, "offset": offset})

    @app.route("/api/config")
    def api_config():
        """Read config."""
        if not app.config_obj:
            return jsonify({})
        import copy
        cfg = copy.deepcopy(app.config_obj._raw)
        for ex in cfg.get("exchanges", {}).values():
            ex["api_key"] = "***" if ex.get("api_key") else ""
            ex["api_secret"] = "***" if ex.get("api_secret") else ""
        # Convert seconds to minutes for display
        for field in ("pre_open_seconds", "pre_settlement_seconds", "post_settlement_close_seconds"):
            if field in cfg.get("strategy", {}):
                cfg["strategy"][field] = cfg["strategy"][field] // 60
        return jsonify(cfg)

    @app.route("/api/config", methods=["POST"])
    def api_update_config():
        """Update config (hot reload). Only overwrites specified fields."""
        if not app.config_obj:
            return jsonify({"error": "config not available"}), 500
        try:
            data = request.get_json()
            if not isinstance(data, dict):
                return jsonify({"error": "request body must be a JSON object"}), 400

            # Validate: only allow updating known top-level keys with dict values
            allowed_keys = {"monitor", "strategy", "notification"}
            for key in data:
                if key not in allowed_keys:
                    return jsonify({"error": f"unknown config key: {key}"}), 400
                if not isinstance(data[key], dict):
                    return jsonify({"error": f"config key '{key}' must be an object"}), 400

            # Convert minutes to seconds for time-window fields (read-only, not user-settable)
            # but still store correctly in case config file is manually edited
            for field in ("pre_open_seconds", "pre_settlement_seconds", "post_settlement_close_seconds"):
                if field in data.get("strategy", {}):
                    data["strategy"][field] = data["strategy"][field] * 60

            def deep_update(target, source):
                for key, value in source.items():
                    if isinstance(value, dict) and isinstance(target.get(key), dict):
                        deep_update(target[key], value)
                    else:
                        target[key] = value

            deep_update(app.config_obj._raw, data)
            with open(app.config_obj._config_path, "w", encoding="utf-8") as f:
                import yaml
                yaml.dump(app.config_obj._raw, f, allow_unicode=True, default_flow_style=False)
            app.config_obj.reload()
            return jsonify({"status": "ok"})
        except Exception as e:
            return jsonify({"error": "Failed to update config"}), 500

    return app
