# Funding Arbitrage

永续合约资金费率套利系统。在 Binance、Bybit、BYDFi、MEXC 之间自动扫描并执行资金费率差套利。

## 安装

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 配置

编辑 `config.yaml`，填入各交易所 API Key/Secret。

**API 权限要求：**
- 合约交易（Futures）读取 + 写入
- 账户余额读取

## 运行

```bash
python main.py                        # 启动 UI (http://localhost:8888)
python main.py --no-ui               # 仅后台监控
python main.py --port 9000           # 自定义端口
```

## Web UI

- **Dashboard** - 实时资金费率、价差高亮、当前持仓
- **Settings** - 在线配置，保存后热加载
- **Positions** - 当前持仓，手动平仓
- **History** - 历史套利记录

## 策略说明

- 结算前 10 分钟扫描机会
- 两所费率差 > 阈值时双向开仓（FOK 限价单）
- 一边未成交则取消另一边
- 每笔无论成败均发 Lark 通知

## 测试

```bash
pytest tests/ -v
```
