// funding_arbitrage web/static/i18n.js

var I18N = {
    _lang: "zh",
    _dict: {
        zh: {
            // Nav
            "nav.dashboard": "Dashboard",
            "nav.settings": "Settings",
            "nav.positions": "Positions",
            "nav.history": "History",
            // Page titles
            "title.dashboard": "Dashboard",
            "title.settings": "Settings",
            "title.positions": "Positions",
            "title.history": "Trade History",
            // Dashboard
            "system_status": "System Status",
            "monitor": "Monitor",
            "next_settlement": "Next Settlement",
            "current_positions": "Current Positions",
            "funding_rates": "Funding Rates (Live)",
            "th_symbol": "Symbol",
            "th_binance": "Binance",
            "th_bybit": "Bybit",
            "th_bydfi": "BYDFi",
            "th_mexc": "MEXC",
            "th_max_diff": "Max Diff",
            "th_next_settlement": "Next Settlement",
            "empty_rates": "No funding rate data available",
            "empty_rates_filter": "No pairs match the current filter criteria",
            // Settings
            "monitor_settings": "Monitor Settings",
            "monitor_enabled": "Monitor Enabled",
            "polling_interval": "Polling Interval (seconds)",
            "min_rate_diff": "Min Rate Diff (%)",
            "max_concurrent": "Max Concurrent",
            "position_value": "Position Value (USDT per side)",
            "position_mode": "Position Mode",
            "mode_fixed": "Fixed",
            "mode_percent": "Percent",
            "order_type": "Order Type",
            "order_limit": "Limit (IOC/FOK)",
            "order_market": "Market",
            "position_percent": "Position Percent (%)",
            "leverage": "Leverage",
            "lark_webhook": "Lark Webhook URL",
            "btn_save_reload": "Save & Reload",
            // Positions
            "current_positions_panel": "Current Positions",
            "th_long_exchange": "Long Exchange",
            "th_short_exchange": "Short Exchange",
            "th_quantity": "Quantity",
            "th_open_time": "Open Time",
            "th_action": "Action",
            "btn_close": "Close",
            "btn_closing": "Closing...",
            "empty_positions": "No open positions",
            // History
            "th_time": "Time",
            "th_pair": "Pair",
            "th_rate_diff": "Rate Diff",
            "th_result": "Result",
            "th_profit": "Profit",
            "empty_history": "No trade history yet",
            // Dynamic text
            "running": "Running",
            "stopped": "Stopped",
            "n_a": "N/A",
            // Toast messages
            "toast_config_saved": "Config saved and reloaded",
            "toast_config_error": "Error saving config",
            "toast_position_closed": "Position {symbol} closed",
            "toast_close_failed": "Failed to close position {symbol}",
            // Confirm
            "confirm_close": "Close {symbol} position?"
        },
        en: {
            "nav.dashboard": "Dashboard",
            "nav.settings": "Settings",
            "nav.positions": "Positions",
            "nav.history": "History",
            "title.dashboard": "Dashboard",
            "title.settings": "Settings",
            "title.positions": "Positions",
            "title.history": "Trade History",
            "system_status": "System Status",
            "monitor": "Monitor",
            "next_settlement": "Next Settlement",
            "current_positions": "Current Positions",
            "funding_rates": "Funding Rates (Live)",
            "th_symbol": "Symbol",
            "th_binance": "Binance",
            "th_bybit": "Bybit",
            "th_bydfi": "BYDFi",
            "th_mexc": "MEXC",
            "th_max_diff": "Max Diff",
            "th_next_settlement": "Next Settlement",
            "empty_rates": "No funding rate data available",
            "empty_rates_filter": "No pairs match the current filter criteria",
            "monitor_settings": "Monitor Settings",
            "monitor_enabled": "Monitor Enabled",
            "polling_interval": "Polling Interval (seconds)",
            "min_rate_diff": "Min Rate Diff (%)",
            "max_concurrent": "Max Concurrent",
            "position_value": "Position Value (USDT per side)",
            "position_mode": "Position Mode",
            "mode_fixed": "Fixed",
            "mode_percent": "Percent",
            "order_type": "Order Type",
            "order_limit": "Limit (IOC/FOK)",
            "order_market": "Market",
            "position_percent": "Position Percent (%)",
            "leverage": "Leverage",
            "lark_webhook": "Lark Webhook URL",
            "btn_save_reload": "Save & Reload",
            "current_positions_panel": "Current Positions",
            "th_long_exchange": "Long Exchange",
            "th_short_exchange": "Short Exchange",
            "th_quantity": "Quantity",
            "th_open_time": "Open Time",
            "th_action": "Action",
            "btn_close": "Close",
            "btn_closing": "Closing...",
            "empty_positions": "No open positions",
            "th_time": "Time",
            "th_pair": "Pair",
            "th_rate_diff": "Rate Diff",
            "th_result": "Result",
            "th_profit": "Profit",
            "empty_history": "No trade history yet",
            "running": "Running",
            "stopped": "Stopped",
            "n_a": "N/A",
            "toast_config_saved": "Config saved and reloaded",
            "toast_config_error": "Error saving config",
            "toast_position_closed": "Position {symbol} closed",
            "toast_close_failed": "Failed to close position {symbol}",
            "confirm_close": "Close {symbol} position?"
        }
    }
};

I18N.init = function() {
    var saved = localStorage.getItem("lang");
    I18N._lang = (saved === "en" || saved === "zh") ? saved : "zh";
    I18N.applyAll();
};

I18N.t = function(key, params) {
    var val = I18N._dict[I18N._lang][key] || I18N._dict.en[key] || key;
    if (params) {
        for (var k in params) {
            val = val.replace("{" + k + "}", params[k]);
        }
    }
    return val;
};

I18N.setLang = function(lang) {
    I18N._lang = lang;
    localStorage.setItem("lang", lang);
    I18N.applyAll();
    // Re-render dynamic content
    if (typeof refreshStatus === "function") refreshStatus();
    if (typeof refreshRates === "function") refreshRates();
    if (typeof refreshPositions === "function") refreshPositions();
    if (typeof refreshHistory === "function") refreshHistory();
};

I18N.toggleLang = function() {
    I18N.setLang(I18N._lang === "zh" ? "en" : "zh");
};

I18N.applyAll = function() {
    var els = document.querySelectorAll("[data-i18n]");
    for (var i = 0; i < els.length; i++) {
        var el = els[i];
        var key = el.getAttribute("data-i18n");
        var text = I18N.t(key);
        if (el.tagName === "OPTION") {
            el.textContent = text;
        } else if (el.tagName === "INPUT" && el.type !== "checkbox") {
            el.placeholder = text;
        } else {
            el.textContent = text;
        }
    }
    // Update lang toggle button text
    var toggleBtn = document.getElementById("lang-toggle");
    if (toggleBtn) toggleBtn.textContent = I18N._lang === "zh" ? "EN" : "ZH";
    // Update html lang attribute
    document.documentElement.lang = I18N._lang;
};
