# 中文工作流说明

## 1. 这套东西到底是什么

这套仓库在 Codex 里的安装形态是一个 `skill`，但实际运行方式已经不是单纯提示词，而是一个带脚本编排的行情分析工作流。

可以把它理解成：

- `SKILL.md` 负责定义规则和调用顺序
- Python 脚本负责抓数据、算指标、画图、打包
- 大模型负责理解请求、看图、按 Al Brooks 框架分析并输出结论

所以更准确的描述是：

- 技术载体是 `skill`
- 运行方式是一个轻量级 `agent workflow`

## 2. 系统目标

这套 skill 的目标是解决下面这类需求：

- 用户发截图，让 agent 看行情
- 用户直接说“看下最近 2 小时行情”
- 用户只说“分析下 BTC 短线”
- 用户希望 agent 不要只靠截图猜，而是先抓真实数据再分析

系统会尽量同时准备四类信息：

- 用户截图
- 真实 bar 数据
- EMA 数据
- 根据真实 bar 自动生成的 K 线图

## 3. 仓库结构与职责

```text
.
├── README.md
├── WORKFLOW_CN.md
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

### `SKILL.md`

主说明书，定义：

- 什么时候触发这个 skill
- 默认值是什么
- 请求解析规则
- 先抓数据再分析的顺序
- 输出结构要求

### `agents/openai.yaml`

skill 的元信息，主要给 Codex/界面层使用，包括：

- skill 名称
- 描述
- 默认 prompt

### `references/request-parsing.md`

输入解析规则，主要说明：

- 文字请求怎么转成参数
- 截图场景下优先识别什么信息
- 模糊表达怎么补默认值

### `references/brooks-framework.md`

Al Brooks 价格行为分析框架，主要约束模型在分析时要看：

- 当前是趋势、区间还是过渡状态
- Always In 方向
- 关键位置
- 信号棒质量
- 突破、失败突破、双顶双底等典型形态

### `references/output-template.md`

输出模板，要求最终回答至少覆盖：

- 市场背景
- 结构判断
- bull case
- bear case
- wait 条件
- 入场、失效、目标位

### `references/safety.md`

风控和表达边界，约束模型：

- 不要伪造数据
- 不要把结果说成确定性
- 必须说明假设和风险

### `scripts/fetch_bars.py`

底层数据引擎，负责：

- 规范 symbol
- 解析 timeframe / recent / start / end
- 选择 provider
- 抓 OHLCV
- 计算 EMA
- 输出结构化 `bars.json`

### `scripts/render_chart.py`

图表渲染器，负责：

- 读取 bar 数据
- 绘制 K 线
- 绘制 EMA20 / EMA50
- 输出 `chart.png`

### `scripts/build_market_bundle.py`

当前最接近“agent 编排器”的脚本，负责：

- 设定默认参数
- 调用 `fetch_bars.py`
- 调用 `render_chart.py`
- 生成最终的 `bundle.json`

## 4. 默认规则

这是当前最关键的默认行为。

当用户的请求比较模糊，只表达了“看 BTC 短线”或“看最近半小时行情”，没有明确指定交易所、合约类型、周期时，系统默认：

- 标的：`BINANCE:BTCUSDT.P`
- 市场：`CRYPTO`
- 周期：`5m`
- 历史数据源：`Binance`

也就是：

- `查下 BTC 最近半小时的线`
  - 默认等价于：看 `Binance BTC 永续合约 5 分钟` 最近 `30m`
- `看下最近 2 小时行情`
  - 默认等价于：看 `Binance BTC 永续合约 5 分钟` 最近 `2h`

## 5. 数据源分工

这套系统不是所有情况都走同一个接口，而是分工处理。

### Crypto 历史多根 bar

默认走 `Binance`。

适用场景：

- 最近半小时
- 最近 2 小时
- 最近 1 天
- 任意需要多根历史 K 线的 crypto 分析

### TradingView 最新单根快照

走 `tvscreener`。

适用场景：

- 对齐 TradingView 当前最新一根 bar 的快照值
- 需要最新周期的 O/H/L/C 和 EMA

限制：

- 当前主要是最新一根快照
- 不能替代完整历史序列

### 非 crypto 历史数据

走 `yfinance`。

适用场景：

- 美股
- 港股
- A 股
- 指数
- ETF

## 6. 程序自动执行什么，大模型介入什么

这是整个流程里最重要的边界。

### 大模型负责

- 识别用户意图
- 读取用户截图
- 从自然语言里抽取 symbol / timeframe / range
- 决定是否使用默认值
- 决定何时调用脚本
- 按 Brooks 理论分析行情
- 组织最终输出

### 程序脚本负责

- 请求外部市场数据
- 计算 EMA
- 生成结构化 bar 数据
- 生成图
- 打包上下文文件

## 7. 完整执行流程

下面按真实运行顺序说明。

### 第 1 步：用户发起请求

输入可能是：

- 一句文字
- 一张截图
- 截图加一句文字

例如：

- `看下最近 2 小时行情`
- `查下 BTC 最近半小时的线`
- `看这张图，帮我分析 BTC 短线`

### 第 2 步：大模型解析请求

模型先判断：

- 有没有明确标的
- 有没有明确 timeframe
- 有没有明确时间范围
- 是否需要套默认值

如果请求是模糊短线 BTC，就会自动补全为：

- `BINANCE:BTCUSDT.P`
- `CRYPTO`
- `5m`
- `recent=30m` 或 `2h`

### 第 3 步：调用 bundle 编排脚本

模型应触发：

```bash
python3 scripts/build_market_bundle.py
```

或者带参数：

```bash
python3 scripts/build_market_bundle.py \
  --symbol BINANCE:BTCUSDT.P \
  --market CRYPTO \
  --timeframe 5m \
  --recent 2h
```

### 第 4 步：bundle 脚本调用取数脚本

`build_market_bundle.py` 会调用：

```bash
python3 scripts/fetch_bars.py ...
```

由 `fetch_bars.py` 负责：

- 规范 symbol
- 选择数据源
- 拉取历史 bar
- 计算 EMA20 / EMA50
- 输出 `bars.json`

### 第 5 步：取数脚本输出 `bars.json`

`bars.json` 是最底层的结构化行情数据，包含每一根 bar 的：

- 时间戳
- open
- high
- low
- close
- volume
- ema_20
- ema_50
- body
- upper_wick
- lower_wick
- direction

### 第 6 步：bundle 脚本调用画图脚本

`build_market_bundle.py` 接着调用：

```bash
python3 scripts/render_chart.py ...
```

由 `render_chart.py` 负责把 `bars.json` 可视化成一张标准 K 线图。

输出文件：

- `chart.png`

### 第 7 步：bundle 脚本生成 `bundle.json`

`bundle.json` 是本次分析的总入口文件，会记录：

- symbol
- timeframe
- provider
- summary
- request 原始参数
- assumptions 默认假设
- artifacts 产物路径

### 第 8 步：大模型读取上下文并分析

大模型最终会同时参考：

- 用户截图
- `bars.json`
- `chart.png`
- `bundle.json`
- Al Brooks 框架
- 输出模板
- 风险约束

然后输出行情分析。

## 8. 三个核心产物分别是什么

### `bars.json`

用途：

- 原始数据明细
- 最可靠的数据来源
- 所有数字判断都应优先基于它

### `chart.png`

用途：

- `bars.json` 的图像化结果
- 方便看趋势、区间、突破、回踩
- 保证图和数据完全同源

### `bundle.json`

用途：

- 本次分析的索引页
- 让模型知道本次到底用了什么参数和默认假设
- 告诉模型数据文件和图片文件放在哪里

## 9. 文本请求时的工作方式

例如用户说：

```text
看下最近 2 小时行情
```

当前流程是：

1. 模型判定这是一个模糊短线请求
2. 模型补默认值为 `BINANCE:BTCUSDT.P + 5m + recent 2h`
3. 程序抓 Binance 永续合约历史 bar
4. 程序计算 EMA
5. 程序生成 `bars.json`
6. 程序生成 `chart.png`
7. 程序生成 `bundle.json`
8. 模型结合 Brooks 理论输出分析

## 10. 截图请求时的工作方式

### 截图加文字

这是当前最稳的使用方式。

例如：

```text
看这张图，分析 BTC 最近 2 小时行情
```

这时模型会同时拿到：

- 用户截图
- 程序抓到的真实数据
- 程序生成的标准图

所以最终分析既能看你原始图表风格，也能校验真实 bar。

### 只有截图，没有补文字

当前版本也能工作，但自动化程度还不算完整。

已经做到的：

- 模型可以直接看图
- 可以根据截图做初步结构判断

还没完全做到的：

- OCR 精确识别 symbol / timeframe / 可见区间
- 把截图里看到的那一段 K 线精确映射到真实历史 bar

所以目前最佳实践仍然是：

- 发截图时顺手补一句文字

例如：

- `这是 BTC 5 分钟图，帮我结合真实数据一起看`
- `看这张图，按最近 2 小时行情分析`

## 11. 为什么这套东西已经有 agent 味道

因为它已经具备了典型 agent workflow 的几个要素：

- 有明确目标
  - 不是闲聊，而是完成一次行情分析任务
- 有工具调用
  - 会取数、算指标、画图、打包
- 有中间状态
  - `bars.json`、`chart.png`、`bundle.json`
- 有规则和默认策略
  - 默认 BTC 永续、默认 5m、默认 Binance
- 有模型和程序的协作分工

所以它不只是一个提示词文件。

## 12. 为什么它现在仍然算 skill，而不是完整独立 agent

因为它还缺少一些更重的自治能力，例如：

- 长期持久状态
- 自主重试和恢复
- 完整 OCR 管线
- 截图到 bar 的精确自动对齐
- 后台持续运行

所以当前最准确的说法是：

- 它是一个安装在 Codex 里的 `skill`
- 但它已经实现了明显的 `agent workflow`

## 13. 当前建议用法

### 最稳的文字请求

- `查下 BTC 最近半小时的线`
- `看下最近 2 小时行情`
- `分析下 BTC 短线`

### 最稳的截图请求

- `看这张图，分析 BTC 最近 2 小时行情`
- `这是 BTC 图，帮我结合真实数据一起看`

## 14. 当前版本的边界

已经支持：

- 文本请求自动抓数据
- 自动算 EMA
- 自动生成图
- 默认短线 BTC 走 Binance 永续 5m
- 截图和真实数据可以同时进入分析流程

还可以继续增强：

- 截图 OCR
- 截图时间范围精确识别
- 自动标注关键高低点和信号棒
- 更接近 TradingView 风格的图表渲染

## 15. 一句话总结

这套仓库当前的本质是：

1. 大模型先理解用户请求和截图
2. 程序自动抓真实行情数据
3. 程序自动生成标准图
4. 程序自动打包为 bundle
5. 大模型再按 Al Brooks 框架做分析

因此它已经不是单纯“写了一份 skill 文档”，而是一套由 skill 驱动的行情分析工作流。
