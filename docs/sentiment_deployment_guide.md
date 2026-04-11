# 舆情监控模块部署指南

## ✅ 已完成工作

### 1. 代码开发 (100%)
- ✅ 后端核心模块 (11个文件)
- ✅ API 路由 (7个端点)
- ✅ 前端页面 (6个组件)
- ✅ 任务调度 (4个定时任务)
- ✅ 单元测试 (8个测试文件)
- ✅ 文档 (README + 测试报告)

### 2. 数据库迁移 (100%)
- ✅ 迁移脚本已创建: `d1e2f3a4b5c6_add_sentiment_tables.py`
- ✅ 已执行迁移: `alembic upgrade d1e2f3a4b5c6`
- ✅ 4张表已创建:
  - `trade_fear_index`
  - `trade_news_sentiment`
  - `trade_event_signal`
  - `trade_polymarket_snapshot`

### 3. Git 提交
- `fc492c4` - 集成计划文档
- `64924da` - T1.1-T1.4 后端核心
- `48e4155` - T1.5-T1.11 完整后端
- `84bda3e` - Phase 2 API 路由
- `f5f737d` - Phase 3-5 前端/调度/测试
- `9a7e657` - Code review 和测试改进

---

## 📋 数据需求清单

### 必需依赖（无需 API Key）

#### 1. yfinance - 恐慌指数
```bash
pip install yfinance>=0.2.40
```
**数据项**:
- VIX (^VIX) - 标普500波动率
- OVX (^OVX) - 原油波动率
- GVZ (^GVZ) - 黄金波动率
- US10Y (^TNX) - 10年期国债收益率

**测试命令**:
```bash
python -m data_analyst.sentiment.run_monitor --task fear-index --dry-run
```

#### 2. akshare - 新闻数据
```bash
pip install akshare>=1.14.0
```
**数据项**:
- 个股新闻（标题、内容、来源、时间）

**测试命令**:
```bash
python -m data_analyst.sentiment.run_monitor --task news-sentiment --stock 002594 --days 3 --dry-run
```

### 可选依赖（需要 API Key）

#### 3. DashScope - LLM 情感分析
```bash
pip install dashscope>=1.17.0
export DASHSCOPE_API_KEY=your_key_here
```
**用途**: 新闻情感分析（positive/negative/neutral）

**测试命令**:
```bash
python -m data_analyst.sentiment.run_monitor --task news-sentiment --stock 002594 --days 1 --env local
```

---

## 🚀 快速开始测试

### 方案 A: 最小化测试（无需 API Key）

#### 步骤1: 安装基础依赖
```bash
cd /Users/zhaobo/data0/person/myTrader
pip install yfinance akshare
```

#### 步骤2: 测试恐慌指数（Dry-run）
```bash
python -m data_analyst.sentiment.run_monitor --task fear-index --dry-run
```

**预期输出**:
```
VIX: 25.0
OVX: 50.0
GVZ: 20.0
US10Y: 4.3
Fear/Greed Score: 35
Market Regime: fear
```

#### 步骤3: 测试新闻获取（Dry-run）
```bash
python -m data_analyst.sentiment.run_monitor --task news-sentiment --stock 002594 --days 1 --dry-run
```

**预期输出**:
```
Fetched 10 news items for 002594
- 比亚迪发布年报...
- 新能源汽车销量...
```

#### 步骤4: 测试事件检测（Dry-run）
```bash
python -m data_analyst.sentiment.run_monitor --task event-detection --keywords "资产重组,回购" --days 3 --dry-run
```

---

### 方案 B: 完整测试（需要数据库）

#### 步骤1: 确保数据库可访问
```bash
# 检查数据库连接
python -c "from config.db import test_connection; print(test_connection())"
```

#### 步骤2: 运行测试脚本
```bash
python scripts/test_sentiment_data.py
```

**测试内容**:
1. ✅ 数据库表检查
2. ✅ 恐慌指数获取
3. ✅ 新闻获取
4. ✅ 事件检测
5. ✅ 数据存储

#### 步骤3: 实际保存数据
```bash
# 保存恐慌指数到数据库
python -m data_analyst.sentiment.run_monitor --task fear-index --env local

# 验证数据
python -c "
from config.db import execute_query
result = execute_query('SELECT * FROM trade_fear_index ORDER BY trade_date DESC LIMIT 1', env='local')
print(result)
"
```

---

## 📊 数据抓取计划

### 第一阶段: 恐慌指数（推荐先测试）

**优点**:
- ✅ 无需 API Key
- ✅ 数据稳定可靠
- ✅ 每小时更新一次
- ✅ 数据量小

**命令**:
```bash
# Dry-run 测试
python -m data_analyst.sentiment.run_monitor --task fear-index --dry-run

# 实际保存
python -m data_analyst.sentiment.run_monitor --task fear-index --env local
```

**数据验证**:
```sql
SELECT * FROM trade_fear_index ORDER BY trade_date DESC LIMIT 5;
```

---

### 第二阶段: 新闻数据

**优点**:
- ✅ 无需 API Key
- ✅ 数据丰富

**注意**:
- ⚠️ 部分股票可能无新闻
- ⚠️ 建议选择活跃股票测试

**推荐测试股票**:
- 002594 (比亚迪)
- 600519 (贵州茅台)
- 000858 (五粮液)

**命令**:
```bash
# 测试多只股票
python -m data_analyst.sentiment.run_monitor --task news-sentiment --stock 002594 --days 3 --dry-run
python -m data_analyst.sentiment.run_monitor --task news-sentiment --stock 600519 --days 3 --dry-run
```

---

### 第三阶段: 事件检测

**优点**:
- ✅ 基于新闻数据，无需额外 API
- ✅ 自动生成交易信号

**命令**:
```bash
python -m data_analyst.sentiment.run_monitor --task event-detection --keywords "资产重组,回购增持,业绩预增" --days 3 --env local
```

**数据验证**:
```sql
SELECT event_category, signal, COUNT(*) as cnt 
FROM trade_event_signal 
GROUP BY event_category, signal;
```

---

### 第四阶段: Polymarket（可选）

**优点**:
- ✅ 无需 API Key
- ✅ 预测市场数据

**命令**:
```bash
python -m data_analyst.sentiment.run_monitor --task polymarket --keywords "tariff,fed,election" --min-volume 100000 --env local
```

---

### 第五阶段: LLM 情感分析（可选）

**要求**:
- ⚠️ 需要 DashScope API Key
- ⚠️ 需要 API 余额

**配置**:
```bash
# 在 .env 文件中添加
DASHSCOPE_API_KEY=sk-xxxxx

# 或临时设置
export DASHSCOPE_API_KEY=sk-xxxxx
```

**命令**:
```bash
# 小批量测试（1条新闻）
python -m data_analyst.sentiment.run_monitor --task news-sentiment --stock 002594 --days 1 --env local
```

---

## 🔧 故障排查

### 问题1: 数据库连接超时
```
pymysql.err.OperationalError: (2003, "Can't connect to MySQL server")
```

**解决方案**:
1. 检查数据库服务是否运行
2. 检查 `.env` 中的数据库配置
3. 确认网络连接
4. 使用 `--dry-run` 模式测试（不需要数据库）

### 问题2: yfinance 获取失败
```
Failed to fetch VIX: ...
```

**解决方案**:
1. 检查网络连接
2. 确认 ticker 代码正确
3. 稍后重试（可能是 API 限流）

### 问题3: akshare 无新闻
```
No news found for stock ...
```

**解决方案**:
1. 换其他活跃股票测试
2. 增加 `--days` 参数
3. 检查股票代码是否正确

---

## 📈 定时任务配置

在 `tasks/07_sentiment.yaml` 中已定义4个定时任务：

1. **update_fear_index** - 每小时更新恐慌指数
2. **scan_news_sentiment** - 每天8点扫描新闻
3. **detect_event_signals** - 每天9点检测事件
4. **monitor_polymarket** - 每天10点监控预测市场

**启用定时任务**:
```bash
# 查看任务列表
python -m scheduler list --tag sentiment

# Dry-run 测试
python -m scheduler run update_fear_index --dry-run

# 实际执行
python -m scheduler run update_fear_index
```

---

## 🎯 推荐测试顺序

### 立即可测试（无需数据库）
```bash
# 1. 恐慌指数
python -m data_analyst.sentiment.run_monitor --task fear-index --dry-run

# 2. 新闻获取
python -m data_analyst.sentiment.run_monitor --task news-sentiment --stock 002594 --days 1 --dry-run

# 3. 事件检测
python -m data_analyst.sentiment.run_monitor --task event-detection --keywords "资产重组" --days 3 --dry-run
```

### 数据库可用后测试
```bash
# 运行完整测试脚本
python scripts/test_sentiment_data.py

# 或手动测试
python -m data_analyst.sentiment.run_monitor --task fear-index --env local
```

---

## 📝 下一步建议

1. **立即测试**: 运行 dry-run 命令验证数据获取功能
2. **数据库准备**: 确保数据库可访问后再保存数据
3. **小批量抓取**: 先测试1-2天的数据
4. **验证数据**: 检查数据完整性和准确性
5. **配置定时任务**: 设置自动化数据更新
6. **API 测试**: 启动 API 服务测试端点
7. **前端验证**: 访问 `/sentiment` 页面查看展示

---

## 📞 支持

如遇问题，请检查：
1. `docs/sentiment_data_requirements.md` - 详细数据需求
2. `docs/sentiment_test_report.md` - 测试报告
3. `data_analyst/sentiment/README.md` - 模块使用说明
4. 日志输出 - 查看详细错误信息
