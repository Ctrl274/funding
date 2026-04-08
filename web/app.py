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
            settlement_dt = monitor.get_next_settlement()
            if settlement_dt:
                settlement_ts = settlement_dt.timestamp()
                countdown_seconds = math.floor(max(0, settlement_ts - time.time()))

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
        return jsonify(list(monitor.get_positions().values()))

    @app.route("/api/positions/<symbol>/close", methods=["POST"])
    def api_close_position(symbol):
        """Manually close a position."""
        monitor = app.monitor
        if not monitor:
            return jsonify({"error": "monitor not available"}), 500
        monitor.close_position(symbol)
        return jsonify({"symbol": symbol, "status": "closed"})

    @app.route("/api/history")
    def api_history():
        """History records."""
        limit = request.args.get("limit", 100, type=int)
        if limit is None or limit < 1:
            limit = 100
        if app.db:
            return jsonify(app.db.get_history(limit=limit))
        return jsonify([])

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
