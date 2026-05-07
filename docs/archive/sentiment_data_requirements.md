# 舆情监控数据需求与测试方案

## 一、数据需求分析

### 1. 恐慌指数数据 (Fear Index)

**数据源**: yfinance
**更新频率**: 每小时
**数据项**:
- VIX (^VIX) - 标普500波动率指数
- OVX (^OVX) - 原油波动率指数  
- GVZ (^GVZ) - 黄金波动率指数
- US10Y (^TNX) - 美国10年期国债收益率

**依赖**:
```bash
pip install yfinance>=0.2.40
```

**测试命令**:
```bash
python -m data_analyst.sentiment.run_monitor --task fear-index --dry-run
```

---

### 2. 新闻数据 (News)

**数据源**: akshare
**更新频率**: 每天
**数据项**:
- 个股新闻（标题、内容、来源、发布时间）
- 支持按股票代码查询

**依赖**:
```bash
pip install akshare>=1.14.0
```

**测试命令**:
```bash
# 获取比亚迪近3天新闻
python -m data_analyst.sentiment.run_monitor --task news-sentiment --stock 002594 --days 3 --dry-run
```

---

### 3. 情感分析数据 (Sentiment)

**数据源**: DashScope LLM API
**更新频率**: 实时（基于新闻）
**数据项**:
- 情感倾向 (positive/negative/neutral)
- 情感强度 (1-5)
- 关键实体、关键词
- 摘要、市场影响

**依赖**:
```bash
pip install dashscope>=1.17.0
export DASHSCOPE_API_KEY=your_api_key_here
```

**测试命令**:
```bash
# 需要先获取新闻，然后进行情感分析
python -m data_analyst.sentiment.run_monitor --task news-sentiment --stock 002594 --days 1 --env local
```

---

### 4. 事件信号数据 (Events)

**数据源**: 基于新闻的关键词匹配
**更新频率**: 每天
**数据项**:
- 事件类型 (bullish/bearish/policy)
- 事件类别（资产重组、回购增持等）
- 交易信号 (strong_buy/buy/hold/sell/strong_sell)
- 匹配的关键词

**依赖**: 无额外依赖（基于新闻数据）

**测试命令**:
```bash
python -m data_analyst.sentiment.run_monitor --task event-detection --keywords "资产重组,回购增持,业绩预增" --days 3 --dry-run
```

---

### 5. Polymarket 数据

**数据源**: Polymarket Gamma API
**更新频率**: 每天
**数据项**:
- 市场问题
- Yes 概率
- 交易量
- 聪明钱信号

**依赖**: 无额外依赖（HTTP 请求）

**测试命令**:
```bash
python -m data_analyst.sentiment.run_monitor --task polymarket --keywords "tariff,fed,election" --min-volume 1000000 --dry-run
```

---

## 二、数据库准备

### 1. 执行数据库迁移

```bash
# 查看待执行的迁移
cd /Users/zhaobo/data0/person/myTrader
make migrate-status

# 执行迁移（创建4张表）
make migrate

# 或手动执行
alembic upgrade head
```

### 2. 验证表创建

```bash
# 连接数据库查看表
python -c "
from config.db import execute_query
result = execute_query('SHOW TABLES LIKE \"trade_%\"', env='local')
for row in result:
    print(row)
"
```

预期输出应包含：
- trade_fear_index
- trade_news_sentiment
- trade_event_signal
- trade_polymarket_snapshot

---

## 三、小批量测试方案

### 阶段1: 恐慌指数测试 ✅ 无需 API Key

**目标**: 验证 yfinance 数据获取和存储

```bash
# 1. 安装依赖
pip install yfinance

# 2. Dry-run 测试（不保存数据库）
python -m data_analyst.sentiment.run_monitor --task fear-index --dry-run

# 3. 实际保存到数据库
python -m data_analyst.sentiment.run_monitor --task fear-index --env local

# 4. 验证数据
python -c "
from config.db import execute_query
result = execute_query('SELECT * FROM trade_fear_index ORDER BY trade_date DESC LIMIT 1', env='local')
print(result)
"
```

**预期结果**:
- VIX, OVX, GVZ, US10Y 都有数值
- fear_greed_score 在 0-100 之间
- market_regime 为 5 种状态之一

---

### 阶段2: 新闻获取测试 ✅ 无需 API Key

**目标**: 验证 akshare 新闻获取

```bash
# 1. 安装依赖
pip install akshare

# 2. 测试获取比亚迪新闻（dry-run）
python -m data_analyst.sentiment.run_monitor --task news-sentiment --stock 002594 --days 1 --dry-run

# 3. 测试其他股票
python -m data_analyst.sentiment.run_monitor --task news-sentiment --stock 600519 --days 1 --dry-run
```

**预期结果**:
- 能获取到新闻列表
- 新闻包含标题、内容、来源、发布时间

---

### 阶段3: 情感分析测试 ⚠️ 需要 API Key

**目标**: 验证 LLM 情感分析

```bash
# 1. 安装依赖
pip install dashscope

# 2. 配置 API Key
export DASHSCOPE_API_KEY=your_key_here
# 或在 .env 文件中添加

# 3. 小批量测试（1条新闻）
python -m data_analyst.sentiment.run_monitor --task news-sentiment --stock 002594 --days 1 --env local

# 4. 验证数据
python -c "
from config.db import execute_query
result = execute_query('SELECT * FROM trade_news_sentiment ORDER BY created_at DESC LIMIT 5', env='local')
for row in result:
    print(f'{row[\"news_title\"][:30]}... -> {row[\"sentiment\"]} ({row[\"sentiment_strength\"]}/5)')
"
```

**预期结果**:
- 情感分析结果保存到数据库
- sentiment 为 positive/negative/neutral
- sentiment_strength 为 1-5

---

### 阶段4: 事件检测测试 ✅ 无需 API Key

**目标**: 验证事件检测和信号生成

```bash
# 基于已有新闻数据进行事件检测
python -m data_analyst.sentiment.run_monitor --task event-detection --keywords "资产重组,回购增持,业绩预增,股东减持" --days 3 --env local

# 验证数据
python -c "
from config.db import execute_query
result = execute_query('SELECT * FROM trade_event_signal ORDER BY created_at DESC LIMIT 5', env='local')
for row in result:
    print(f'{row[\"event_category\"]} -> {row[\"signal\"]} ({row[\"stock_code\"]})')
"
```

**预期结果**:
- 检测到事件并生成信号
- signal 为 strong_buy/buy/hold/sell/strong_sell

---

### 阶段5: Polymarket 测试 ✅ 无需 API Key

**目标**: 验证预测市场数据获取

```bash
# 搜索关税相关市场
python -m data_analyst.sentiment.run_monitor --task polymarket --keywords "tariff" --min-volume 100000 --env local

# 验证数据
python -c "
from config.db import execute_query
result = execute_query('SELECT * FROM trade_polymarket_snapshot ORDER BY snapshot_time DESC LIMIT 5', env='local')
for row in result:
    print(f'{row[\"market_question\"][:50]}... Yes: {row[\"yes_probability\"]}%')
"
```

**预期结果**:
- 获取到预测市场数据
- 识别出聪明钱信号

---

## 四、推荐测试顺序

### 第一步: 基础环境准备
```bash
# 1. 执行数据库迁移
cd /Users/zhaobo/data0/person/myTrader
make migrate

# 2. 安装基础依赖（不含 LLM）
pip install yfinance akshare
```

### 第二步: 测试恐慌指数（最简单）
```bash
# Dry-run 测试
python -m data_analyst.sentiment.run_monitor --task fear-index --dry-run

# 实际保存
python -m data_analyst.sentiment.run_monitor --task fear-index --env local
```

### 第三步: 测试新闻获取
```bash
# 测试几只重点股票
python -m data_analyst.sentiment.run_monitor --task news-sentiment --stock 002594 --days 1 --dry-run
python -m data_analyst.sentiment.run_monitor --task news-sentiment --stock 600519 --days 1 --dry-run
```

### 第四步: 测试事件检测
```bash
# 基于新闻检测事件
python -m data_analyst.sentiment.run_monitor --task event-detection --keywords "资产重组,回购" --days 3 --dry-run
```

### 第五步: 测试 Polymarket
```bash
python -m data_analyst.sentiment.run_monitor --task polymarket --keywords "tariff,fed" --min-volume 100000 --dry-run
```

### 第六步: 配置 LLM 并测试情感分析（可选）
```bash
# 需要先申请 DashScope API Key
export DASHSCOPE_API_KEY=your_key
python -m data_analyst.sentiment.run_monitor --task news-sentiment --stock 002594 --days 1 --env local
```

---

## 五、数据验证脚本

创建一个验证脚本来检查数据质量：

```python
# scripts/verify_sentiment_data.py
from config.db import execute_query

def verify_fear_index():
    """验证恐慌指数数据"""
    result = execute_query(
        'SELECT COUNT(*) as cnt FROM trade_fear_index',
        env='local'
    )
    print(f"恐慌指数记录数: {result[0]['cnt']}")
    
    latest = execute_query(
        'SELECT * FROM trade_fear_index ORDER BY trade_date DESC LIMIT 1',
        env='local'
    )
    if latest:
        print(f"最新数据: VIX={latest[0]['vix']}, Score={latest[0]['fear_greed_score']}")

def verify_news():
    """验证新闻数据"""
    result = execute_query(
        'SELECT COUNT(*) as cnt FROM trade_news_sentiment',
        env='local'
    )
    print(f"新闻记录数: {result[0]['cnt']}")

def verify_events():
    """验证事件数据"""
    result = execute_query(
        'SELECT event_type, COUNT(*) as cnt FROM trade_event_signal GROUP BY event_type',
        env='local'
    )
    for row in result:
        print(f"{row['event_type']}: {row['cnt']} 条")

if __name__ == '__main__':
    verify_fear_index()
    verify_news()
    verify_events()
```

---

## 六、常见问题

### Q1: yfinance 获取数据失败
**原因**: 网络问题或 ticker 代码错误
**解决**: 检查网络连接，确认 ticker 代码正确

### Q2: akshare 获取新闻为空
**原因**: 该股票当天无新闻或 API 限流
**解决**: 换其他股票测试，或增加 days 参数

### Q3: DashScope API 调用失败
**原因**: API Key 未配置或余额不足
**解决**: 检查环境变量，确认 API Key 有效

### Q4: 数据库连接失败
**原因**: 数据库未启动或配置错误
**解决**: 检查 .env 配置，确认数据库服务运行

---

## 七、监控指标

测试时关注以下指标：

1. **数据完整性**: 所有字段都有值
2. **数据准确性**: VIX 在合理范围（5-80）
3. **响应时间**: API 调用 < 5秒
4. **错误率**: < 5%
5. **数据新鲜度**: 时间戳正确

---

## 八、下一步计划

1. ✅ 执行数据库迁移
2. ✅ 测试恐慌指数获取
3. ✅ 测试新闻获取
4. ⚠️ 申请 DashScope API Key（可选）
5. ✅ 验证数据存储
6. ✅ 测试 API 端点
7. ✅ 配置定时任务
