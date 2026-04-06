// Funding Arbitrage - Frontend JS

function api(url, options) {
    options = options || {};
    return fetch(url, options).then(function(r) { return r.json(); });
}

function refreshStatus() {
    api("/api/status").then(function(data) {
        var el = document.getElementById("monitor-status");
        if (el) el.textContent = data.monitor_enabled ? "Running" : "Stopped";

        el = document.getElementById("next-settlement");
        if (el) el.textContent = data.next_settlement ? new Date(data.next_settlement).toLocaleString() : "N/A";

        el = document.getElementById("position-count");
        if (el) el.textContent = data.current_positions;
    });
}

function refreshRates() {
    api("/api/rates").then(function(rows) {
        var tbody = document.getElementById("rates-body");
        if (!tbody) return;

        if (!rows || rows.length === 0) {
            tbody.innerHTML = "<tr><td colspan=\"6\">No data</td></tr>";
            return;
        }

        var exchanges = ["binance", "bybit", "bydfi", "mexc"];
        tbody.innerHTML = rows.map(function(row) {
            var rates = [];
            exchanges.forEach(function(ex) {
                var key = ex + "_rate";
                if (row[key] !== null && row[key] !== undefined) {
                    rates.push({ ex: ex, val: row[key] });
                }
            });

            if (rates.length < 2) return "";

            var maxRate = -Infinity, minRate = Infinity;
            rates.forEach(function(r) {
                if (r.val > maxRate) maxRate = r.val;
                if (r.val < minRate) minRate = r.val;
            });
            var diff = (maxRate - minRate).toFixed(4);

            var cells = exchanges.map(function(ex) {
                var key = ex + "_rate";
                var val = row[key];
                if (val !== null && val !== undefined) {
                    var cls = val > 0 ? "positive" : "negative";
                    return "<td class=\"" + cls + "\">" + val.toFixed(4) + "%</td>";
                }
                return "<td>-</td>";
            }).join("");

            var highlight = parseFloat(diff) >= 0.01 ? "highlight" : "";
            var diffCls = parseFloat(diff) >= 0.01 ? "positive" : "";
            return "<tr class=\"" + highlight + "\"><td>" + row.symbol + "</td>" + cells + "<td class=\"" + diffCls + "\">" + diff + "%</td></tr>";
        }).join("");
    });
}

function refreshPositions() {
    api("/api/positions").then(function(positions) {
        var tbody = document.getElementById("positions-body");
        if (!tbody) return;

        if (!positions || positions.length === 0) {
            tbody.innerHTML = "<tr><td colspan=\"6\">No open positions</td></tr>";
            return;
        }

        tbody.innerHTML = positions.map(function(p) {
            var openTime = new Date(p.open_time * 1000).toLocaleString();
            return "<tr><td>" + p.symbol + "</td><td>" + p.high_exchange + " (" + p.side_a + ")</td><td>" + p.low_exchange + " (" + p.side_b + ")</td><td>" + p.quantity + "</td><td>" + openTime + "</td><td><button class=\"close-btn\" onclick=\"closePosition('" + p.symbol + "')\">Close</button></td></tr>";
        }).join("");
    });
}

function closePosition(symbol) {
    if (!confirm("Close " + symbol + " position?")) return;
    api("/api/positions/" + symbol + "/close", { method: "POST" }).then(function() {
        refreshPositions();
        refreshStatus();
    });
}

function refreshHistory() {
    api("/api/history").then(function(history) {
        var tbody = document.getElementById("history-body");
        if (!tbody) return;

        if (!history || history.length === 0) {
            tbody.innerHTML = "<tr><td colspan=\"6\">No history</td></tr>";
            return;
        }

        tbody.innerHTML = history.map(function(h) {
            var profit = h.profit !== null ? "$" + parseFloat(h.profit).toFixed(2) : "-";
            var profitCls = h.profit > 0 ? "positive" : (h.profit < 0 ? "negative" : "");
            return "<tr><td>" + h.created_at + "</td><td>" + h.symbol + "</td><td>" + h.high_exchange + "-" + h.low_exchange + "</td><td>" + parseFloat(h.rate_diff).toFixed(4) + "%</td><td>" + h.result + "</td><td class=\"" + profitCls + "\">" + profit + "</td></tr>";
        }).join("");
    });
}

function loadConfig() {
    api("/api/config").then(function(cfg) {
        if (!cfg) return;
        var setVal = function(id, val) {
            var el = document.getElementById(id);
            if (el) el.value = val;
        };
        if (cfg.monitor) {
            var cb = document.getElementById("monitor-enabled");
            if (cb) cb.checked = cfg.monitor.enabled;
            setVal("polling-interval", cfg.monitor.polling_interval);
        }
        if (cfg.strategy) {
            setVal("min-rate-diff", cfg.strategy.min_rate_diff);
            setVal("max-concurrent", cfg.strategy.max_concurrent);
        }
        if (cfg.notification) {
            setVal("lark-webhook", cfg.notification.lark_webhook);
        }
    });
}

function saveConfig(e) {
    e.preventDefault();
    var form = e.target;
    var data = {
        monitor: {
            enabled: form.querySelector("#monitor-enabled").checked,
            polling_interval: parseInt(form.querySelector("#polling-interval").value),
        },
        strategy: {
            min_rate_diff: parseFloat(form.querySelector("#min-rate-diff").value),
            max_concurrent: parseInt(form.querySelector("#max-concurrent").value),
        },
        notification: {
            lark_webhook: form.querySelector("#lark-webhook").value,
        },
    };
    api("/api/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
    }).then(function(r) {
        if (r.status === "ok") alert("Config saved and reloaded!");
        else alert("Error: " + JSON.stringify(r));
    });
}
