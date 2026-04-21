# 大盘总览数据修复记录

> 日期: 2026-04-21

## 已完成修复

### HIGH - 代码逻辑修复 (已提交部署)

| 问题 | 文件 | 修复方式 |
|------|------|----------|
| 成交量异常值污染 MA20 | `market_dashboard/calculator.py` | 滚动中位数 * 0.3 过滤异常值 |
| PMI null 误判为 contraction | `market_overview/calculator.py` | 显式 None 检查,返回 "unknown" |
| AH 溢价阈值错误 [120,140] | `market_overview/calculator.py` + `market_dashboard/calculator.py` | 改为 [15,30] (百分比格式) |
| MACD 状态命名歧义 | `market_dashboard/calculator.py` | 新增 `dif_above_dea` / `dif_below_dea` 状态 |
| new_high_60d 为 0 时无回退 | `market_dashboard/calculator.py` | 回退取最近非零记录 |

### MEDIUM - 数据缺失修复

| 问题 | 修复方式 | 状态 |
|------|----------|------|
| idx_sh / idx_gem 无数据 | macro_fetcher 新增注册 + 回填 312 行 | 已完成 (commit f7de6b0) |

## 待今晚执行 (大批量计算)

以下任务需大量 DB 查询,远程连接易超时,建议在服务器本地执行:

### 1. SVD 市场状态更新 (最后数据: 2026-04-02)

```bash
DB_ENV=online python -m data_analyst.market_monitor.run_monitor --latest
```

说明: 需查询全 A 股收益率矩阵做 SVD 分解,本地跑 MySQL 超时。

### 2. Dashboard 数据拉取 (margin/new_high_low 等)

```bash
DB_ENV=online python -c "
from data_analyst.market_dashboard.fetcher import fetch_all
fetch_all('2026-04-21', env='online')
"
```

说明: margin_balance 最后数据 4/10,new_high_low 需从 trade_stock_daily 聚合。

### 3. Fear Index 数据补全 (仅 5 条记录)

```bash
DB_ENV=online python -m data_analyst.sentiment.run_monitor --task fear-index
```

说明: 需调用外部 API 获取 VIX/OVX/GVZ/US10Y,数据源可用性不稳定。

## 非代码问题 (无需修复)

| 问题 | 原因 |
|------|------|
| Margin 数据滞后 (4/10) | 交易所两融数据报送延迟,非代码问题 |
| 成长/价值轮动显示"数据不足" | 依赖因子数据未计算,需先完成因子任务 |
| 5 年锚偏离 current=19.2 | 正确值 (idx_all_a 中证全指点位,非 PE) |

---

## V2 晨报（盘前早咖）上线测试

> 日期: 2026-04-21 | 状态: 代码已合并，服务器测试未完成

### 背景

基于"盘前早咖"公众号内容，新增 V2 晨报流水线：
- 文章来源：wechat2rss 抓取 → export JSON → Stage A LLM 逐条拆解 → Stage B 价值评分 + 生成晨报
- 结果存 `trade_briefing` 表 `session='morning_v2'`
- Celery Beat 08:35 自动触发（V1 08:30，V2 08:35），各自推一份飞书文档 + Bot 卡片

### 涉及文件

| 文件 | 说明 |
|------|------|
| `api/services/panqian_briefing_v2.py` | 新增，V2 核心服务 |
| `api/services/feishu_doc_publisher.py` | 新增 `publish_briefing_and_notify` 公共函数 |
| `api/tasks/briefing_tasks.py` | 新增 `publish_morning_briefing_v2` Celery 任务 |
| `api/tasks/celery_app.py` | 08:35 加入 V2 调度 |
| `api/services/article_digest_service.py` | 盘前早咖加入 `FEED_CATEGORY_MAP` |
| `scripts/export_wechat_articles.py` | 新增 `PANQIAN_FEEDS`，字数门槛 100 字，每天取 1 篇 |

### 待完成

- [ ] 确认 celery-worker / celery-beat 已用新代码重启
- [ ] 手动触发 V2，确认文章能拿到（`article_source` 应为 `export_json`）
- [ ] 确认飞书 Bot 卡片正常推送，对比 V1 / V2 效果

### 测试命令（服务器上按顺序执行）

```bash
# 1. 确认容器状态
docker ps --format "{{.Names}}\t{{.Status}}"

# 2. 重启 worker + beat（后台，不要等）
cd /root/app && docker compose restart celery-worker celery-beat &

# 3. 确认盘前早咖 feed_name 完全匹配
sqlite3 /root/wechat2rss/data/res.db "SELECT feed_id, name FROM rsses WHERE name LIKE '%早咖%';"

# 4. 手动触发 V2 生成（用 run 独立容器，避免 exec 阻塞）
cd /root/app && docker compose run --rm celery-worker python3 -c "
import asyncio
from api.services.panqian_briefing_v2 import generate_v2_briefing
r = asyncio.run(generate_v2_briefing(force=True))
print('source:', r['article_source'])
print('items:', r['items_count'])
print(r['content'][:500])
"

# 5. 完整推送（含飞书文档 + Bot 卡片）
cd /root/app && docker compose run --rm celery-worker python3 -c "
import asyncio
from api.services.panqian_briefing_v2 import generate_v2_briefing
from api.services.feishu_doc_publisher import publish_briefing_and_notify
r = asyncio.run(generate_v2_briefing(force=True))
if r['content'].startswith('[V2速递中止]'):
    print('ABORTED:', r['content'])
else:
    doc = publish_briefing_and_notify('V2晨报(盘前早咖) ' + r['date'], r['content'])
    print('Published:', doc['url'])
"
```

### 常见问题排查

| 现象 | 原因 | 处理 |
|------|------|------|
| `article_source: none` | 盘前早咖未订阅或 feed_name 不匹配 | 用步骤 3 确认 name，按实际名称修改 `PANQIAN_FEED_NAME` |
| `items: 0` | Stage A LLM 返回空数组 | 检查文章内容是否被截断或为广告页 |
| 飞书未收到卡片 | `FEISHU_OWNER_OPEN_ID` 或 token 问题 | 看 worker 日志 `grep panqian` |
| SSH 超时 / exec 卡住 | docker compose exec 在 restart 期间阻塞 | 改用 `docker compose run --rm` |
