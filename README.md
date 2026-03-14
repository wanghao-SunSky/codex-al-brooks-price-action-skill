# Al Brooks Price Action Skill

这是一个给 Codex / AI Agent 使用的行情分析 skill。

如果你想看完整的中文工作流说明，直接看：

- [WORKFLOW_CN.md](./WORKFLOW_CN.md)

它的目标是：

- 根据用户发来的截图或文字描述，推断要看的标的、周期和行情区间
- 自动抓取真实 OHLCV bar 数据和 EMA 数据
- 自动生成一张标准 K 线图
- 再按 Al Brooks 价格行为框架输出结构化分析和交易建议

## 适用场景

- 用户发一张图，让 agent 帮忙看行情
- 用户直接说“看下最近 2 小时行情”
- 用户只说“分析下 BTC 短线”
- 用户希望 agent 先去抓真实数据，再给分析，而不是只靠截图猜

## 当前默认规则

如果用户说的是泛化短线 BTC 请求，但没有明确指定交易所、合约类型和周期，例如：

- `查下 BTC 最近半小时的线`
- `看下最近 2 小时行情`
- `分析下 BTC 短线`

系统默认按下面处理：

- 标的：`BINANCE:BTCUSDT.P`
- 市场：`CRYPTO`
- 周期：`5m`
- 历史数据源：`Binance`

也就是说：

- `最近半小时` 默认会抓 `Binance BTC 永续合约 5 分钟线`
- `最近 2 小时` 默认也会抓 `Binance BTC 永续合约 5 分钟线`

## 当前能做什么

- 文本请求时自动抓真实 bar 数据
- 计算 EMA20 / EMA50
- 根据真实数据自动生成 K 线图
- 有截图时，模型可以同时看用户截图和系统生成图
- 输出带有 `bull case / bear case / wait` 的结构化分析

## 当前数据源

- Crypto 历史多根 bar：`Binance`
- TradingView 最新单根快照：`tvscreener`
- 非 crypto 历史数据：`yfinance`

说明：

- `tvscreener` 目前主要用于最新一根周期快照
- 多根历史 K 线分析，crypto 默认走 Binance

## 仓库结构

```text
.
├── README.md
├── SKILL.md
├── agents/
│   └── openai.yaml
├── references/
│   ├── brooks-framework.md
│   ├── output-template.md
│   ├── request-parsing.md
│   └── safety.md
└── scripts/
    ├── build_market_bundle.py
    ├── fetch_bars.py
    ├── render_chart.py
    └── requirements.txt
```

## 关键文件说明

- `SKILL.md`
  - skill 主说明书
  - 定义触发条件、默认值、执行流程、分析要求
- `references/request-parsing.md`
  - 说明如何把用户文字或截图信息转成 symbol、timeframe、recent 等参数
- `references/brooks-framework.md`
  - Al Brooks 价格行为分析框架
- `references/output-template.md`
  - 最终回答的输出模板
- `references/safety.md`
  - 风险提示、假设边界和表达约束
- `scripts/fetch_bars.py`
  - 负责抓取真实 bar 数据并计算 EMA
- `scripts/render_chart.py`
  - 把 bar 数据渲染成 K 线图
- `scripts/build_market_bundle.py`
  - 一键执行“抓数据 + 画图 + 打包上下文”

## 执行流程

### 1. 用户输入

用户可以：

- 直接发一句话，例如 `看下最近 2 小时行情`
- 发截图并补一句话，例如 `看这张图，帮我分析 BTC 短线`

### 2. 大模型理解请求

模型会先判断：

- 用户要看哪个标的
- 要看哪个周期
- 要看最近多久
- 有没有需要套用默认值

### 3. 程序抓取真实数据

程序会调用：

- `scripts/fetch_bars.py`

拿到：

- `open`
- `high`
- `low`
- `close`
- `volume`
- `ema_20`
- `ema_50`

### 4. 程序生成标准图

程序会调用：

- `scripts/render_chart.py`

输出一张和 bar 数据完全同源的 `chart.png`。

### 5. 程序打包 bundle

程序会调用：

- `scripts/build_market_bundle.py`

统一生成：

- `bars.json`
- `chart.png`
- `bundle.json`

### 6. 大模型分析

模型最终会同时参考：

- 用户截图（如果有）
- `bars.json`
- `chart.png`
- `bundle.json`
- Al Brooks 分析框架

然后输出结构化交易分析。

## 三个核心产物

### `bars.json`

原始结构化行情数据，包含每一根 bar 的：

- 时间戳
- open / high / low / close
- volume
- ema_20 / ema_50
- body / wick / direction 等派生字段

### `chart.png`

根据 `bars.json` 自动生成的标准 K 线图。

它的作用是：

- 让模型不仅能看数字，也能看图形结构
- 让图和真实数据完全同源

### `bundle.json`

本次分析的总索引文件，记录：

- 最终使用的 symbol
- timeframe
- provider
- summary
- 默认假设
- 产物文件路径

## 安装

把整个目录放到：

```bash
~/.codex/skills/al-brooks-price-action
```

或者按你自己的 skill 管理方式安装。

## 依赖安装

```bash
python3 -m pip install -r scripts/requirements.txt
```

## 手动运行示例

### 1. 直接抓取最近 2 小时 BTC 永续 5 分钟数据

```bash
python3 scripts/build_market_bundle.py \
  --symbol BINANCE:BTCUSDT.P \
  --market CRYPTO \
  --timeframe 5m \
  --recent 2h
```

### 2. 直接抓取最近半小时 BTC 永续 5 分钟数据

```bash
python3 scripts/build_market_bundle.py \
  --symbol BINANCE:BTCUSDT.P \
  --market CRYPTO \
  --timeframe 5m \
  --recent 30m
```

### 3. 只取 bar 数据

```bash
python3 scripts/fetch_bars.py \
  --symbol BINANCE:BTCUSDT.P \
  --market CRYPTO \
  --timeframe 5m \
  --recent 2h \
  --ema 20 50
```

## 注意事项

- 这不是投资承诺工具，只能做分析辅助
- 如果截图信息不完整，系统会采用默认值并在输出里说明假设
- 当前版本已经支持“真实数据 + 自动生成图”的双通道分析
- 纯截图到精确 bar 区间的自动对齐，后续还可以继续增强
