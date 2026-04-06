# 永续合约资金费率套利系统 — 设计文档

## 1. Overview

在 Binance、Bybit、BYDFi、MEXC 四个交易所之间，自动扫描永续合约的资金费率差机会。当两家交易所的同币种费率差扣除成本后仍有利润时，通过双向锁仓（FOK 限价单）执行套利。在结算前 10 分钟开仓，结算后立即平仓。每笔操作（无论成功失败）均通过 Lark 发送详细通知，并通过 Web UI 实时监控。

## 2. Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   funding_arbitrage                       │
│                                                          │
│  ┌──────────┐   ┌────────────┐   ┌──────────┐          │
│  │  Config  │──▶│  Monitor   │──▶│ Notifier │          │
│  │  (YAML)  │   │  Loop      │   │  (Lark)  │          │
│  └──────────┘   └─────┬──────┘   └──────────┘          │
│                       │                                 │
│                ┌──────▼──────┐                          │
│                │  Strategy   │                          │
│                │  Engine     │                          │
│                └──────┬──────┘                          │
│                       │                                 │
│  ┌──────────┬─────────┼─────────┬──────────┐          │
│  │          │         │         │          │          │
│  ▼          ▼         ▼         ▼          ▼          │
│ Binance   Bybit     BYDFi     MEXC                    │
│ Adapter  Adapter   Adapter   Adapter                    │
└─────────────────────────────────────────────────────────┘
                       │
         ┌─────────────┼─────────────┬─────────────┐    │
         ▼             ▼             ▼             ▼    │
      Binance       Bybit         BYDFi        MEXC    │
    Futures API  Futures API   Futures API  Futures API │
```

### Components

| Component | Responsibility |
|-----------|---------------|
| Config | 读写 YAML 配置文件，运行时热加载 |
| Monitor Loop | 每 N 秒轮询四所资金费率，基于 API 返回的 next_settlement 动态判断是否在结算窗口内 |
| Strategy Engine | 两两配对计算费率差，过滤阈值，按并发数排序选机会 |
| Exchange Adapter | 封装 ccxt，统一接口：Binance/Bybit/MEXC；BYDFi 用原生 API |
| Execution Engine | FOK 限价单下单、成交监听、部分成交则对冲止损 |
| Notifier | Lark Webhook 通知（详细模式） |
| Web UI (Flask + 原生 JS) | Dashboard / Settings / Positions / History |

### Data Flow

1. Monitor Loop 每 60s 轮询四所最新资金费率（含 next_settlement 时间戳）
2. Monitor 基于各交易所 API 返回的 next_settlement 判断是否进入结算前窗口（pre_settlement_seconds），支持任意结算频率（1h / 2h / 4h / 8h 等）
3. Strategy Engine 两两配对，筛除 < min_rate_diff 的组合
4. 如果并发数未满，选最优机会（费率差最大）
4. Execution Engine 同时向两边发 FOK 限价单
5. 监听成交：两边都成 → 挂平仓单；一边不成 → 取消另一边 + 止损 + 告警
6. 到结算时间后自动平仓
7. 每笔结果无论成功失败均发 Lark 详细通知

## 3. 配置文件

文件：`config.yaml`

```yaml
# 交易所 API 密钥
exchanges:
  binance:
    enabled: true
    api_key: "xxx"
    api_secret: "xxx"
    testnet: false

  bybit:
    enabled: true
    api_key: "xxx"
    api_secret: "xxx"
    testnet: false

  bydfi:
    enabled: true
    api_key: "xxx"
    api_secret: "xxx"
    testnet: false

  mexc:
    enabled: true
    api_key: "xxx"
    api_secret: "xxx"

# 套利策略
strategy:
  min_rate_diff: 0.01          # 触发阈值（百分比）
  position_mode: "fixed"       # fixed | percent | dynamic
  position_value: 1000          # fixed: 每边 USDT 数量
  position_percent: 5           # percent: 账户资产百分比
  max_concurrent: 3             # 同时最多几笔套利
  pre_settlement_seconds: 600   # 结算前多久开仓（秒）
  partial_fill_action: "cancel_and_stop"  # 单边失败处理

# 监控控制
monitor:
  enabled: true
  # 时间段列表（降级兜底用，当 API 获取失败时启用）
  # 空或无此字段 = 24h 全天候；格式: "HH:MM-HH:MM" UTC
  time_windows:
    - "23:50-00:10"
    - "07:50-08:10"
    - "15:50-16:10"
  polling_interval: 60          # 轮询间隔（秒）

# 通知
notification:
  enabled: true
  lark_webhook: "https://open.larksuite.com/..."
  detail_level: "detailed"      # detailed | summary
```

## 4. Web UI (Streamlit)

访问地址：`http://localhost:8888`

### 页面 1: Dashboard
- 控制面板：监控开关、下次结算倒计时
- 资金费率监控表：实时显示各交易所各币对的最新资金费率，价差高亮
- 当前持仓：开仓时间、方向、预估收益

### 页面 2: Settings
- 表单化配置所有 config.yaml 参数
- 保存后热加载，无需重启

### 页面 3: Positions
- 当前所有持仓列表
- 支持手动平仓

### 页面 4: History
- 历史套利记录
- 包含：时间、币对、组合、方向、实际收益、状态（成功/失败）

## 5. API 接口

各交易所资金费率 endpoint：

| Exchange | Endpoint | Notes |
|----------|----------|-------|
| Binance | `GET /fapi/v1/premiumIndex` | 实时 funding rate |
| Bybit | `GET /v5/market/tickers?category=linear` | 包含 funding rate |
| BYDFi | `GET /swap/public/q/contracts` | 包含 funding rate（见 bydfi-openapi.md） |
| MEXC | `GET /api/v1/futures/funding_history` | 实时 funding rate |

各交易所下单 endpoint：

| Exchange | Order Type | Notes |
|----------|-----------|-------|
| Binance | `POST /fapi/v1/order` | timeInForce=GTC/IOC |
| Bybit | `POST /v5/order/create` | category=linear |
| BYDFi | `POST /swap/order/place` | orderType=IOC/FOK |
| MEXC | `POST /api/v1/futures/order` | orderType=IOT/FOK |

## 6. 利润计算

```
机会得分 = 费率差 - 实际手续费(%) - 滑点估算(%)
开仓收益 = 费率差(%) × 仓位价值 - (maker_fee × 2 + 滑点)
平仓盈亏 = 结算后两边资金费收入 - 平仓手续费
```

实际手续费从交易所 API 实时拉取（maker fee tier），滑点根据下单前查深度估算。

## 7. 结算时间

结算时间从各交易所 API 的 `nextFundingTime` 字段动态获取，不再硬编码时间点。

- **Binance USDT-M**: 8h 结算（00:00 / 08:00 / 16:00 UTC）
- **Bybit USDT 永续**: 8h 结算（00:00 / 08:00 / 16:00 UTC）
- **MEXC**: 8h 结算（00:00 / 08:00 / 16:00 UTC）
- **BYDFi**: 需验证（API 有 `nextFundingTime` 字段）

程序在 `next_settlement - pre_settlement_seconds` 时触发开仓扫描，到结算时间后自动平仓。支持任意结算频率（1h / 2h / 4h / 8h 等），无需修改代码。

## 8. 技术栈

- Python 3.11+
- `ccxt` — Binance/Bybit/MEXC 接口
- `requests` — BYDFi 及其他 HTTP 请求
- `APScheduler` — 定时调度
- `SQLite` — 套利记录持久化
- `Flask` — Web UI 后端（REST API）
- 原生 HTML + CSS + JavaScript — 前端（零构建工具）
- `httpx` — Lark Webhook 通知
- `PyYAML` — 配置文件读写

## 9. 文件结构

```
funding_arbitrage/
  config.yaml              # 配置文件
  requirements.txt         # 依赖
  config.py                # 配置加载与热更新
  monitor.py               # Monitor Loop
  strategy.py              # Strategy Engine
  exchanges/
    __init__.py
    base.py                # 交易所适配器基类
    binance.py             # Binance
    bybit.py               # Bybit
    bydfi.py               # BYDFi（原生 API）
    mexc.py                # MEXC
  executor.py              # Execution Engine（FOK 下单 + 监听）
  notifier.py              # Lark 通知
  db.py                    # SQLite 持久化
  web/
    app.py                 # Flask 后端（REST API）
    templates/
      index.html           # 主页面（Dashboard）
      settings.html        # Settings 页面
      positions.html       # Positions 页面
      history.html         # History 页面
    static/
      style.css            # 样式
      app.js               # 前端逻辑
  main.py                  # 入口
  docs/
    superpowers/
      specs/
        2026-03-31-funding-arbitrage-design.md
```

## 10. Error Handling

- 交易所 API 超时：重试 3 次，间隔指数退避
- 结算前窗口判断：基于 API 返回的 next_settlement 动态计算，adapter 异常时降级回退到 time_windows
- 单边 FOK 未成交：取消另一边，止损告警
- 结算时持仓无法平仓：立即告警，保留手动处理接口
- Lark 通知发送失败：降级写本地日志

## 11. 安全注意事项

- API 密钥仅存储在 config.yaml，不提交到代码仓库
- config.yaml 加入 .gitignore
- BYDFi API 签名：GET 参数按字母序排列，POST body 用 compact JSON
