"""
Flask Web UI backend.
Provides REST API for the frontend.
"""
import math
import time
import yaml
from flask import Flask, jsonify, request, render_template


def create_app(monitor_ref=None, config_ref=None, db_ref=None):
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    app.monitor = monitor_ref
    app.config_obj = config_ref
    app.db = db_ref

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
        monitor = app.monitor
        settlement_dt = None
        countdown_seconds = None
        if monitor:
            settlement_dt = monitor.get_next_settlement()
            if settlement_dt:
                countdown_seconds = math.floor(max(0, settlement_dt.timestamp() - time.time()))
        return jsonify({
            "monitor_enabled": app.config_obj.monitor.enabled if app.config_obj else True,
            "next_settlement": settlement_dt.isoformat() if settlement_dt else None,
            "countdown_seconds": countdown_seconds,
            "current_positions": len(monitor.get_positions()) if monitor else 0,
        })

    @app.route("/api/rates")
    def api_rates():
        monitor = app.monitor
        if not monitor:
            return jsonify([])
        all_rates = monitor.get_current_rates()
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
                else:
                    row[f"{ex}_rate"] = None
            rows.append(row)
        return jsonify(rows)

    @app.route("/api/positions")
    def api_positions():
        monitor = app.monitor
        if not monitor:
            return jsonify([])
        return jsonify(list(monitor.get_positions().values()))

    @app.route("/api/positions/<path:symbol>/close", methods=["POST"])
    def api_close_position(symbol):
        monitor = app.monitor
        if not monitor:
            return jsonify({"error": "monitor not available"}), 500
        return jsonify({"symbol": symbol, "status": "closed"})

    @app.route("/api/history")
    def api_history():
        if not app.db:
            return jsonify([])
        limit = request.args.get("limit", 100, type=int)
        return jsonify(app.db.get_history(limit=limit))

    @app.route("/api/config")
    def api_config():
        if not app.config_obj:
            return jsonify({})
        cfg = app.config_obj._raw.copy()
        for ex in cfg.get("exchanges", {}).values():
            if ex.get("api_key"):
                ex["api_key"] = "***"
            if ex.get("api_secret"):
                ex["api_secret"] = "***"
        return jsonify(cfg)

    @app.route("/api/config", methods=["POST"])
    def api_update_config():
        if not app.config_obj:
            return jsonify({"error": "config not available"}), 500
        try:
            data = request.get_json()
            with open(app.config_obj._path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True)
            app.config_obj.reload()
            return jsonify({"status": "ok"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    return app
