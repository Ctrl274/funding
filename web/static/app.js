// funding_arbitrage web/static/app.js

function escapeHtml(str) {
    if (str === null || str === undefined) return "";
    return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function api(url, options) {
    return fetch(url, options || {}).then(function(r) {
        return r.json().then(function(data) {
            return data;
        }).catch(function() {
            return null;
        });
    });
}

function showToast(message, type) {
    var container = document.getElementById("toast-container");
    if (!container) return;
    var toast = document.createElement("div");
    toast.className = "toast " + (type || "success");
    toast.textContent = message;
    container.appendChild(toast);
    // Trigger reflow for animation
    toast.offsetHeight;
    toast.classList.add("show");
    setTimeout(function() {
        toast.classList.remove("show");
        setTimeout(function() { container.removeChild(toast); }, 200);
    }, 3000);
}

function refreshStatus() {
    api("/api/status").then(function(data) {
        if (!data) return;
        document.getElementById("monitor-status").textContent =
            data.monitor_enabled ? "Running" : "Stopped";
        document.getElementById("next-settlement").textContent =
            data.next_settlement ? new Date(data.next_settlement).toLocaleString() : "N/A";
        document.getElementById("position-count").textContent = data.current_positions;
    });
}

function refreshRates() {
    api("/api/rates").then(function(rows) {
        var tbody = document.getElementById("rates-body");
        if (!rows || rows.length === 0) {
            tbody.innerHTML = "<tr><td colspan='7'><div class='empty-state'><div class='empty-text'>No funding rate data available</div></div></td></tr>";
            return;
        }
        var allEx = ["binance", "bybit", "bydfi", "mexc"];
        var html = "";
        for (var i = 0; i < rows.length; i++) {
            var row = rows[i];
            var rates = [];
            var settlements = [];
            for (var j = 0; j < allEx.length; j++) {
                var ex = allEx[j];
                var rateKey = ex + "_rate";
                var tsKey = ex + "_next_settlement_ts";
                if (row[rateKey] !== null && row[rateKey] !== undefined) {
                    rates.push({ ex: ex, val: row[rateKey] });
                    var ts = row[tsKey];
                    if (ts && ts > 0) {
                        settlements.push(ts);
                    }
                }
            }
            if (rates.length < 2) continue;

            // Filter out pairs with misaligned settlement times (>5min diff)
            if (settlements.length >= 2) {
                var maxTs = Math.max.apply(null, settlements);
                var minTs = Math.min.apply(null, settlements);
                if ((maxTs - minTs) > 300) continue;
            }

            var maxRate = Math.max.apply(null, rates.map(function(r) { return r.val; }));
            var minRate = Math.min.apply(null, rates.map(function(r) { return r.val; }));
            var diff = maxRate - minRate;

            var fullCells = "";
            for (var k = 0; k < allEx.length; k++) {
                var ex2 = allEx[k];
                var r = null;
                for (var m = 0; m < rates.length; m++) {
                    if (rates[m].ex === ex2) { r = rates[m]; break; }
                }
                if (r) {
                    var cls = r.val > 0 ? "positive" : "negative";
                    fullCells += "<td class='" + cls + "'>" + r.val.toFixed(4) + "%</td>";
                } else {
                    fullCells += "<td>-</td>";
                }
            }

            // Next settlement: use the earliest from available exchanges
            var settlementStr = "-";
            if (settlements.length > 0) {
                var nearestTs = Math.min.apply(null, settlements);
                var remaining = Math.max(0, Math.floor(nearestTs - Date.now() / 1000));
                var mm = Math.floor(remaining / 60);
                var ss = remaining % 60;
                settlementStr = mm + "m " + ss + "s";
            }

            var rowClass = diff >= 0.01 ? " class='highlight'" : "";
            html += "<tr" + rowClass + ">" +
                "<td>" + escapeHtml(row.symbol) + "</td>" +
                fullCells +
                "<td class='" + (diff >= 0.01 ? "positive" : "") + "'>" + diff.toFixed(4) + "%</td>" +
                "<td>" + escapeHtml(settlementStr) + "</td>" +
                "</tr>";
        }
        tbody.innerHTML = html || "<tr><td colspan='7'><div class='empty-state'><div class='empty-text'>No pairs match the current filter criteria</div></div></td></tr>";
    });
}

function refreshPositions() {
    api("/api/positions").then(function(positions) {
        var tbody = document.getElementById("positions-body");
        if (!positions || positions.length === 0) {
            tbody.innerHTML = "<tr><td colspan='6'><div class='empty-state'><div class='empty-text'>No open positions</div></div></td></tr>";
            return;
        }
        var html = "";
        for (var i = 0; i < positions.length; i++) {
            var p = positions[i];
            var openTime = new Date(p.open_time).toLocaleString();
            var safeSymbol = escapeHtml(p.symbol);
            html += "<tr>" +
                "<td>" + safeSymbol + "</td>" +
                "<td>" + escapeHtml(p.high_exchange) + " (" + escapeHtml(p.side_a) + ")</td>" +
                "<td>" + escapeHtml(p.low_exchange) + " (" + escapeHtml(p.side_b) + ")</td>" +
                "<td>" + escapeHtml(p.quantity) + "</td>" +
                "<td>" + escapeHtml(openTime) + "</td>" +
                "<td><button data-symbol=\"" + safeSymbol + "\" class=\"close-btn\">Close</button></td>" +
                "</tr>";
        }
        tbody.innerHTML = html;
        // Attach click handlers after rendering
        var buttons = tbody.querySelectorAll(".close-btn");
        for (var b = 0; b < buttons.length; b++) {
            buttons[b].addEventListener("click", function() {
                closePosition(this.getAttribute("data-symbol"), this);
            });
        }
    });
}

function closePosition(symbol, btn) {
    if (!confirm("Close " + symbol + " position?")) return;
    if (btn) {
        btn.classList.add("loading");
        btn.textContent = "Closing...";
        btn.disabled = true;
    }
    api("/api/positions/" + symbol + "/close", { method: "POST" }).then(function() {
        refreshPositions();
        refreshStatus();
        if (btn) {
            btn.classList.remove("loading");
            btn.textContent = "Close";
            btn.disabled = false;
        }
        showToast("Position " + symbol + " closed", "success");
    }).catch(function() {
        if (btn) {
            btn.classList.remove("loading");
            btn.textContent = "Close";
            btn.disabled = false;
        }
        showToast("Failed to close position " + symbol, "error");
    });
}

function refreshHistory() {
    api("/api/history").then(function(history) {
        var tbody = document.getElementById("history-body");
        if (!history || history.length === 0) {
            tbody.innerHTML = "<tr><td colspan='6'><div class='empty-state'><div class='empty-text'>No trade history yet</div></div></td></tr>";
            return;
        }
        var html = "";
        for (var i = 0; i < history.length; i++) {
            var h = history[i];
            var profit = h.profit !== null ? "$" + parseFloat(h.profit).toFixed(2) : "-";
            var profitCls = h.profit > 0 ? "positive" : h.profit < 0 ? "negative" : "";
            html += "<tr>" +
                "<td>" + escapeHtml(h.created_at) + "</td>" +
                "<td>" + escapeHtml(h.symbol) + "</td>" +
                "<td>" + escapeHtml(h.high_exchange) + "-" + escapeHtml(h.low_exchange) + "</td>" +
                "<td class='" + (parseFloat(h.rate_diff) > 0 ? "positive" : h.rate_diff < 0 ? "negative" : "") + "'>" + parseFloat(h.rate_diff).toFixed(4) + "%</td>" +
                "<td>" + escapeHtml(h.result) + "</td>" +
                "<td class='" + profitCls + "'>" + profit + "</td>" +
                "</tr>";
        }
        tbody.innerHTML = html;
    });
}

function loadConfig() {
    api("/api/config").then(function(cfg) {
        if (!cfg) return;
        var setVal = function(id, val) {
            var el = document.getElementById(id);
            if (el) el.value = val;
        };
        setVal("polling-interval", cfg.monitor ? cfg.monitor.polling_interval : 60);
        setVal("min-rate-diff", cfg.strategy ? cfg.strategy.min_rate_diff : 0.01);
        setVal("max-concurrent", cfg.strategy ? cfg.strategy.max_concurrent : 3);
        setVal("position-value", cfg.strategy ? cfg.strategy.position_value : 1000);
        setVal("position-percent", cfg.strategy ? cfg.strategy.position_percent : 5);
        setVal("leverage", cfg.strategy ? cfg.strategy.leverage : 5);
        var modeEl = document.getElementById("position-mode");
        if (modeEl && cfg.strategy) modeEl.value = cfg.strategy.position_mode || "fixed";
        setVal("lark-webhook", cfg.notification ? cfg.notification.lark_webhook : "");
        var cb = document.getElementById("monitor-enabled");
        if (cb) cb.checked = cfg.monitor ? cfg.monitor.enabled : false;
    });
}

function saveConfig(e) {
    e.preventDefault();
    var form = e.target;
    var btn = document.getElementById("save-btn");
    if (btn) { btn.classList.add("loading"); btn.disabled = true; }

    var data = {
        monitor: {
            enabled: form.querySelector("#monitor-enabled").checked,
            polling_interval: parseInt(form.querySelector("#polling-interval").value, 10),
        },
        strategy: {
            min_rate_diff: parseFloat(form.querySelector("#min-rate-diff").value),
            max_concurrent: parseInt(form.querySelector("#max-concurrent").value, 10),
            position_value: parseFloat(form.querySelector("#position-value").value),
            position_mode: form.querySelector("#position-mode").value,
            position_percent: parseFloat(form.querySelector("#position-percent").value),
            leverage: parseInt(form.querySelector("#leverage").value, 10),
        },
        notification: {
            lark_webhook: form.querySelector("#lark-webhook").value,
        },
    };

    function handleResult(r) {
        if (btn) { btn.classList.remove("loading"); btn.disabled = false; }
        if (r && r.status === "ok") showToast("Config saved and reloaded", "success");
        else showToast("Error saving config", "error");
    }

    api("/api/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
    }).then(handleResult).catch(function() {
        handleResult(null);
    });
}
