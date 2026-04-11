# Sentiment Monitoring Module

舆情监控与感知模块，用于实时监控市场情绪、新闻事件和预测市场。

## 功能模块

### 1. 恐慌指数监控
- **VIX**: 标普500波动率指数
- **OVX**: 原油波动率指数
- **GVZ**: 黄金波动率指数
- **US10Y**: 美国10年期国债收益率
- **综合评分**: 0-100恐慌/贪婪评分
- **风险传导**: 检测OVX与VIX共振

### 2. 新闻情感分析
- 基于 AKShare 获取个股新闻
- 使用 DashScope LLM 进行情感分析
- 提取关键实体和关键词
- 评估市场影响

### 3. 事件驱动信号
- 关键词匹配检测事件
- 事件类型：利好/利空/政策
- 自动生成交易信号
- 支持的事件类别：
  - 利好：资产重组、回购增持、业绩预增、股权激励、大额订单、战略合作
  - 利空：股东减持、业绩预减、违规处罚、商誉减值、退市风险
  - 政策：货币政策、产业政策、监管新规

### 4. Polymarket 预测市场
- 搜索预测市场
- 检测聪明钱信号（交易量>$1M且概率极端）
- 监控关键事件概率变化

## CLI 使用

```bash
# 获取恐慌指数
python -m data_analyst.sentiment.run_monitor --task fear-index

# 新闻情感分析
python -m data_analyst.sentiment.run_monitor --task news-sentiment --stock 002594 --days 3

# 事件检测
python -m data_analyst.sentiment.run_monitor --task event-detection --keywords "资产重组,回购增持" --days 3

# Polymarket 监控
python -m data_analyst.sentiment.run_monitor --task polymarket --keywords "tariff,fed,election" --min-volume 1000000

# Dry-run 模式（不保存数据库）
python -m data_analyst.sentiment.run_monitor --task fear-index --dry-run

# 指定数据库环境
python -m data_analyst.sentiment.run_monitor --task fear-index --env prod
```

## API 端点

```
GET  /api/sentiment/fear-index              # 获取当前恐慌指数
GET  /api/sentiment/fear-index/history      # 获取历史数据
GET  /api/sentiment/news                    # 获取新闻列表
POST /api/sentiment/news/analyze            # 分析单条新闻
GET  /api/sentiment/events                  # 获取事件信号
GET  /api/sentiment/polymarket              # 搜索预测市场
GET  /api/sentiment/overview                # 获取概览数据
```

## 数据库表

- `trade_fear_index`: 恐慌指数历史
- `trade_news_sentiment`: 新闻情感分析结果
- `trade_event_signal`: 事件信号记录
- `trade_polymarket_snapshot`: Polymarket 快照

## 定时任务

在 `tasks/07_sentiment.yaml` 中定义了4个定时任务：

1. `update_fear_index`: 每小时更新恐慌指数
2. `scan_news_sentiment`: 每天早上8点扫描新闻
3. `detect_event_signals`: 每天早上9点检测事件
4. `monitor_polymarket`: 每天早上10点监控预测市场

## 环境变量

```bash
# DashScope API Key (用于LLM情感分析)
DASHSCOPE_API_KEY=your_api_key_here
```

## 前端页面

访问 `/sentiment` 查看舆情监控页面，包含：
- 恐慌指数面板
- 新闻舆情面板
- 事件信号面板
- 预测市场面板
