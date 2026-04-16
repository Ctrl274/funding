// funding_arbitrage web/static/app.js

/* === Theme Module === */
var Theme = {
    _theme: "dark",
    init: function() {
        var saved = localStorage.getItem("theme");
        Theme._theme = (saved === "light" || saved === "dark") ? saved : "dark";
        Theme.apply();
        var btn = document.getElementById("theme-toggle");
        if (btn) btn.addEventListener("click", Theme.toggle);
    },
    apply: function() {
        document.documentElement.setAttribute("data-theme", Theme._theme);
        var btn = document.getElementById("theme-toggle");
        if (btn) btn.innerHTML = Theme._theme === "dark" ? "&#9788;" : "&#9790;";
    },
    toggle: function() {
        Theme._theme = Theme._theme === "dark" ? "light" : "dark";
        localStorage.setItem("theme", Theme._theme);
        Theme.apply();
    }
};

/* === Utilities === */
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
    toast.offsetHeight;
    toast.classList.add("show");
    setTimeout(function() {
        toast.classList.remove("show");
        setTimeout(function() { container.removeChild(toast); }, 200);
    }, 3000);
}

/* === Language toggle init === */
function initLangToggle() {
    var btn = document.getElementById("lang-toggle");
    if (btn) btn.addEventListener("click", I18N.toggleLang);
}

/* === Dashboard === */
function refreshStatus() {
    api("/api/status").then(function(data) {
        if (!data) return;
        document.getElementById("monitor-status").textContent =
            data.monitor_enabled ? I18N.t("running") : I18N.t("stopped");
        document.getElementById("next-settlement").textContent =
            data.next_settlement ? new Date(data.next_settlement).toLocaleString() : I18N.t("n_a");
        document.getElementById("position-count").textContent = data.current_positions;
    });
}

function refreshRates() {
    api("/api/rates").then(function(rows) {
        var tbody = document.getElementById("rates-body");
        if (!tbody) return;
        if (!rows || rows.length === 0) {
            tbody.innerHTML = "<tr><td colspan='7'><div class='empty-state'><div class='empty-text'>" + escapeHtml(I18N.t("empty_rates")) + "</div></div></td></tr>";
            return;
        }
        var allEx = ["binance", "bybit", "bydfi", "mexc"];
        var items = [];
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

            if (settlements.length >= 2) {
                var maxTs = Math.max.apply(null, settlements);
                var minTs = Math.min.apply(null, settlements);
                if ((maxTs - minTs) > 300) continue;
            }

            var maxRate = Math.max.apply(null, rates.map(function(r) { return r.val; }));
            var minRate = Math.min.apply(null, rates.map(function(r) { return r.val; }));
            var diff = maxRate - minRate;

            var nearestTs = settlements.length > 0 ? Math.min.apply(null, settlements) : Infinity;

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

            var settlementStr = "-";
            if (settlements.length > 0) {
                var remaining = Math.max(0, Math.floor(nearestTs - Date.now() / 1000));
                var mm = Math.floor(remaining / 60);
                var ss = remaining % 60;
                settlementStr = mm + "m " + ss + "s";
            }

            items.push({ nearestTs: nearestTs, diff: diff, html: "<tr" + (diff >= 0.01 ? " class='highlight'" : "") + ">" +
                "<td>" + escapeHtml(row.symbol) + "</td>" +
                fullCells +
                "<td class='" + (diff >= 0.01 ? "positive" : "") + "'>" + diff.toFixed(4) + "%</td>" +
                "<td>" + escapeHtml(settlementStr) + "</td>" +
                "</tr>" });
        }
        // Sort: nearest settlement first, then by diff descending
        items.sort(function(a, b) {
            if (a.nearestTs !== b.nearestTs) return a.nearestTs - b.nearestTs;
            return b.diff - a.diff;
        });
        var html = "";
        for (var x = 0; x < items.length; x++) {
            html += items[x].html;
        }
        tbody.innerHTML = html || "<tr><td colspan='7'><div class='empty-state'><div class='empty-text'>" + escapeHtml(I18N.t("empty_rates_filter")) + "</div></div></td></tr>";
    });
}

/* === Positions === */
function refreshPositions() {
    api("/api/positions").then(function(positions) {
        var tbody = document.getElementById("positions-body");
        if (!tbody) return;
        if (!positions || positions.length === 0) {
            tbody.innerHTML = "<tr><td colspan='7'><div class='empty-state'><div class='empty-text'>" + escapeHtml(I18N.t("empty_positions")) + "</div></div></td></tr>";
            return;
        }
        var html = "";
        for (var i = 0; i < positions.length; i++) {
            var p = positions[i];
            // open_time is Unix timestamp in seconds (float), Date needs milliseconds
            var openTime = new Date(parseFloat(p.open_time) * 1000).toLocaleString();
            var safeSymbol = escapeHtml(p.symbol);
            var qa = p.quantity_a != null ? p.quantity_a : p.quantity;
            var qb = p.quantity_b != null ? p.quantity_b : "-";
            html += "<tr>" +
                "<td>" + safeSymbol + "</td>" +
                "<td>" + escapeHtml(p.high_exchange) + " (" + escapeHtml(p.side_a) + ")</td>" +
                "<td>" + escapeHtml(p.low_exchange) + " (" + escapeHtml(p.side_b) + ")</td>" +
                "<td>" + escapeHtml(qa) + "</td>" +
                "<td>" + escapeHtml(qb) + "</td>" +
                "<td>" + escapeHtml(openTime) + "</td>" +
                "<td><button data-symbol=\"" + safeSymbol + "\" class=\"close-btn\">" + escapeHtml(I18N.t("btn_close")) + "</button></td>" +
                "</tr>";
        }
        tbody.innerHTML = html;
        var buttons = tbody.querySelectorAll(".close-btn");
        for (var b = 0; b < buttons.length; b++) {
            buttons[b].addEventListener("click", function() {
                closePosition(this.getAttribute("data-symbol"), this);
            });
        }
    });
}

function closePosition(symbol, btn) {
    var msg = I18N.t("confirm_close", { symbol: symbol });
    if (!confirm(msg)) return;
    if (btn) {
        btn.classList.add("loading");
        btn.textContent = I18N.t("btn_closing");
        btn.disabled = true;
    }
    api("/api/positions/" + symbol + "/close", { method: "POST" }).then(function(data) {
        refreshPositions();
        refreshStatus();
        // Show result based on actual exchange status
        if (data.status === "closed") {
            showToast(I18N.t("toast_position_closed", { symbol: symbol }), "success");
        } else if (data.status === "partial") {
            var failed = [];
            var results = data.close_results || {};
            for (var ex in results) {
                if (!results[ex].success) {
                    failed.push(ex);
                }
            }
            var detail = failed.length ? " (" + failed.join(", ") + " failed)" : "";
            showToast(I18N.t("toast_position_closed_partial", { symbol: symbol }) + detail, "warning");
        } else {
            showToast(I18N.t("toast_close_failed", { symbol: symbol }), "error");
        }
    }).catch(function() {
        if (btn) {
            btn.classList.remove("loading");
            btn.textContent = I18N.t("btn_close");
            btn.disabled = false;
        }
        showToast(I18N.t("toast_close_failed", { symbol: symbol }), "error");
    });
}

/* === History === */
var _historyPage = { limit: 20, offset: 0, total: 0 };

function refreshHistory() {
    var params = "?limit=" + _historyPage.limit + "&offset=" + _historyPage.offset;
    api("/api/history" + params).then(function(data) {
        if (!data) return;
        var history = data.items || [];
        _historyPage.total = data.total || 0;
        _historyPage.limit = data.limit || 20;
        _historyPage.offset = data.offset || 0;

        renderHistoryTable(history);
        renderHistoryPagination();
    });
}

function renderHistoryTable(history) {
    var tbody = document.getElementById("history-body");
    if (!tbody) return;
    if (!history || history.length === 0) {
        tbody.innerHTML = "<tr><td colspan='7'><div class='empty-state'><div class='empty-text'>" + escapeHtml(I18N.t("empty_history")) + "</div></div></td></tr>";
        return;
    }
    var html = "";
    for (var i = 0; i < history.length; i++) {
        var h = history[i];
        var profit = h.profit !== null ? "$" + parseFloat(h.profit).toFixed(2) : "-";
        var profitCls = h.profit > 0 ? "positive" : h.profit < 0 ? "negative" : "";
        var realized = h.realized_pnl !== null ? "$" + parseFloat(h.realized_pnl).toFixed(2) : "-";
        var realizedCls = h.realized_pnl > 0 ? "positive" : h.realized_pnl < 0 ? "negative" : "";
        var closeTime = h.close_time ? escapeHtml(h.close_time) : "-";
        html += "<tr>" +
            "<td>" + escapeHtml(h.created_at) + "</td>" +
            "<td>" + escapeHtml(h.symbol) + "</td>" +
            "<td>" + escapeHtml(h.high_exchange) + "-" + escapeHtml(h.low_exchange) + "</td>" +
            "<td class='" + (parseFloat(h.rate_diff) > 0 ? "positive" : h.rate_diff < 0 ? "negative" : "") + "'>" + parseFloat(h.rate_diff).toFixed(4) + "%</td>" +
            "<td>" + escapeHtml(h.result) + "</td>" +
            "<td>" + closeTime + "</td>" +
            "<td class='" + profitCls + "'>" + profit + "</td>" +
            "<td class='" + realizedCls + "'>" + realized + "</td>" +
            "</tr>";
    }
    tbody.innerHTML = html;
}

function renderHistoryPagination() {
    var prevBtn = document.getElementById("page-prev");
    var nextBtn = document.getElementById("page-next");
    var info = document.getElementById("page-info");
    if (!prevBtn || !nextBtn || !info) return;

    var total = _historyPage.total;
    var limit = _historyPage.limit;
    var offset = _historyPage.offset;
    var currentPage = Math.floor(offset / limit) + 1;
    var totalPages = Math.ceil(total / limit);

    info.textContent = total === 0 ? "-" : offset + 1 + "-" + Math.min(offset + limit, total) + " / " + total;
    prevBtn.disabled = offset <= 0;
    nextBtn.disabled = offset + limit >= total;

    prevBtn.onclick = function() {
        if (offset > 0) {
            _historyPage.offset = Math.max(0, offset - limit);
            refreshHistory();
        }
    };
    nextBtn.onclick = function() {
        if (offset + limit < total) {
            _historyPage.offset = offset + limit;
            refreshHistory();
        }
    };
}

/* === Settings === */
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
        setVal("pre-open-seconds", cfg.strategy ? cfg.strategy.pre_open_seconds : 15);
        setVal("pre-settlement-seconds", cfg.strategy ? cfg.strategy.pre_settlement_seconds : 5);
        setVal("post-settlement-close-seconds", cfg.strategy ? cfg.strategy.post_settlement_close_seconds : 2);
        var modeEl = document.getElementById("position-mode");
        if (modeEl && cfg.strategy) modeEl.value = cfg.strategy.position_mode || "fixed";
        var orderEl = document.getElementById("order-type");
        if (orderEl && cfg.strategy) orderEl.value = cfg.strategy.order_type || "limit";
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
            order_type: form.querySelector("#order-type").value,
            position_percent: parseFloat(form.querySelector("#position-percent").value),
            leverage: parseInt(form.querySelector("#leverage").value, 10),
            pre_open_seconds: parseInt(form.querySelector("#pre-open-seconds").value, 10),
            pre_settlement_seconds: parseInt(form.querySelector("#pre-settlement-seconds").value, 10),
            post_settlement_close_seconds: parseInt(form.querySelector("#post-settlement-close-seconds").value, 10),
        },
        notification: {
            lark_webhook: form.querySelector("#lark-webhook").value,
        },
    };

    function handleResult(r) {
        if (btn) { btn.classList.remove("loading"); btn.disabled = false; }
        if (r && r.status === "ok") showToast(I18N.t("toast_config_saved"), "success");
        else showToast(I18N.t("toast_config_error"), "error");
    }

    api("/api/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
    }).then(handleResult).catch(function() {
        handleResult(null);
    });
}

/* === Init language toggle on every page === */
document.addEventListener("DOMContentLoaded", initLangToggle);
