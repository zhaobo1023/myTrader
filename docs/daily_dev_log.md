# myTrader 每日开发日志

---

## 2026-04-14 大盘总览 Dashboard Phase 1 数据补全与性能优化

### 今日工作内容

#### 1. 数据管道补全

Dashboard 部署到线上后发现 6 个板块大量指标为空，根本原因是数据管道未在线上执行过。

**数据管道现状梳理：**

| 管道 | 功能 | 状态 |
|------|------|------|
| `macro_fetcher` | 指数序列、QVIX、北向资金、国债、PMI、M2、AH溢价 | 首次执行，补全 25 个指标 13,443 条记录 |
| `dashboard fetcher` | 成交额、涨跌家数、涨跌停、融资、创新高低 | 补全 60 天历史数据 |
| `sentiment fear_index` | VIX/OVX/GVZ 恐慌指数 | 存在异常（VIX=0.0），待排查 |

#### 2. AKShare 云服务器 IP 限流问题

**问题：** `index_zh_a_hist`（东财 Web 接口）在阿里云服务器上被封，所有指数日线数据拉取失败。

**解决方案：** 修改 `macro_fetcher.py` 中的 `fetch_index_daily` 函数，添加三级回退机制：

```
index_zh_a_hist (东财 Web) -> stock_zh_index_daily_em (东财 App) -> stock_zh_index_daily (新浪)
```

stock_zh_index_daily_em 在云服务器可用，成功拉取了 CSI300/CSI500/CSI1000 等 7 个核心指数 549 天数据。

**仍不可用的指数（接口均被封）：**
- `idx_growth300`（沪深300成长，000918）-- 导致风格板块 style.direction=unknown
- `idx_equity_fund`（偏股混合基金指数，885001）
- `idx_hk_dividend`（港股通高股息，930914）

#### 3. 成交额数据修正

**问题：** `stock_zh_index_daily(symbol="sh000001")` 返回的 volume 字段是**成交量（股数）**，不是**成交额（元）**。导致页面显示"成交额 546 亿"（实际应为 2.15 万亿）。

**解决方案：** 修改 `fetcher.py` 中的 `fetch_market_volume`：
- 主方案：使用 `stock_sse_deal_daily`（上交所）+ `stock_szse_summary`（深交所）获取两市真实成交额
- 回退方案：使用新浪接口的 volume（股数，精度较低）
- 回填 60 个交易日的历史数据

修正后：4月13日成交额 = SSE 9203亿 + SZSE 12318亿 = **21522 亿元**

#### 4. 性能优化（122s -> 2.8s）

**问题：** Dashboard API 首次请求耗时 122 秒，原因是 `calc_temperature` 中调用 `calc_market_turnover()`，该函数对 `trade_stock_daily` 表执行 `AVG(turnover_rate) ... GROUP BY trade_date ... INTERVAL 400 DAY` 全表扫描，在线上大表上极其缓慢甚至触发 OOM。

**解决方案：** 移除对 `trade_stock_daily` 的依赖，改用 `macro_data.market_volume` 的分位数排名计算成交量活跃度。

**效果：**
- 冷计算：122s -> 2.8s（43x 提升）
- 缓存命中：< 0.1s

#### 5. 日期显示修正

**问题：** `updated_at` 使用 `date.today()` 显示为 2026-04-14（非交易日），应显示最近交易日。

**解决方案：** 新增 `_get_latest_trade_date()` 从 `macro_data` 表查询 `idx_csi300` 的最新日期。

#### 6. MA 阈值修正

**问题：** 趋势板块要求 `len(csi300) >= 250` 个交易日，但 `_load_macro` 用 `days=300` 自然日回溯只能获取约 199 个交易日。

**解决方案：**
- `_load_macro` 的 `days` 参数从 300 改为 500
- MA 最低要求从 250 降为 60（MA250 在数据不足时设为 None）

---

### 修改的文件

| 文件 | 改动说明 |
|------|---------|
| `data_analyst/fetchers/macro_fetcher.py` | fetch_index_daily 三级回退；默认起始日期改为 2024-01-01 |
| `data_analyst/market_dashboard/calculator.py` | 移除 trade_stock_daily 查询；MA 阈值放宽；updated_at 取最近交易日 |
| `data_analyst/market_dashboard/fetcher.py` | fetch_market_volume 改用交易所成交额 API |

### 相关 Git 提交

```
ac34a6c fix: market_volume use turnover amount (yuan) instead of shares
3c2de70 perf: replace slow trade_stock_daily query with macro_data volume
6eaeeb8 fix: dashboard trend section require 60+ days instead of 250+
fcf9dba fix: macro_fetcher index fallback to stock_zh_index_daily_em
```

---

### 当前 Dashboard 数据状态

| 板块 | 等级 | 关键指标 | 完整度 |
|------|------|---------|--------|
| 温度 | 常温 (score=45) | 成交额 21522 亿, 量比 1.04, 分位 37.1%, 涨停 59/跌停 4 | 5/7 |
| 趋势 | 震荡蓄势 | MA5/20/250 上方, MA60 下方, MACD 零轴下收敛, ADX=23.4 | 5/6 |
| 情绪 | 中性 (score=49) | QVIX=15.94, 北向-67.75 亿, 创新高 130/低 49 | 5/7 |
| 风格 | scale=均衡 | 大小盘中性, style 数据不足 | 部分 |
| 股债 | 股票吸引力强 | 19 点序列 | 完整 |
| 宏观 | 顺风 (score=2) | PMI=50.4(扩张), AH 溢价=11.51(低) | 4/6 |

---

### 待解决问题

#### P0 - 需尽快修复

1. **`advance_decline`（涨跌家数）缺失**
   - 原因：`stock_zh_a_spot_em`（东财 EM 接口）在云服务器被封
   - 方案：可用 `stock_market_activity_legu`（乐股网）替代，该接口已验证可用且返回涨跌家数
   - 影响：温度板块缺少涨跌家数比

2. **`trade_fear_index` VIX=0.0 异常**
   - 原因：sentiment 模块的 fear_index 数据写入异常，VIX 值为 0
   - 方案：排查 `data_analyst/sentiment/fear_index.py` 的数据拉取逻辑
   - 影响：情绪和宏观板块的 VIX 指标不准确

3. **`idx_growth300`（沪深300成长）不可用**
   - 原因：三个 AKShare 接口均在云服务器被封
   - 方案 A：找替代指数（如 399370 国证成长）
   - 方案 B：用创业板指（399006）代替成长风格
   - 影响：风格板块 style.direction 显示"数据不足"

#### P1 - 短期优化

4. **`margin_change_5d` 为空**
   - 原因：融资数据只有 1 天（刚开始采集），需积累 5 天以上
   - 方案：自然积累，每日执行 dashboard fetcher 即可
   - 预计：5 个交易日后自动解决

5. **`m2_yoy` 最新值为空**
   - 原因：AKShare 的 M2 数据滞后，目前只到 2025-09
   - 方案：这是数据源本身的滞后性，月度数据正常延迟 1-2 个月

6. **`svd` 状态 unknown**
   - 原因：线上数据库没有 `trade_svd_market_state` 表
   - 方案：在线上执行 SVD 模块的数据回填，或忽略该指标

7. **定时任务未配置**
   - dashboard fetcher 和 macro_fetcher 尚未加入每日调度
   - 需要添加到 `tasks/` YAML 配置中

#### P2 - 中期改进

8. **前端 UI 优化**
   - 信号卡片的数据展示需根据实际数据调整布局
   - Sparkline 图表需验证视觉效果
   - 移动端适配

9. **信号变化日志（signal_log）为空**
   - 需要实现每日计算结果的持久化和 diff 比较逻辑
   - 存储每日各板块 level 变化记录

10. **API 缓存刷新机制**
    - 当前 Redis 缓存 6 小时 TTL
    - 需要在每日数据更新后主动刷新缓存

---

### 技术总结

**AKShare 在云服务器的可用性矩阵：**

| 接口 | 数据源 | 云服务器可用 | 备注 |
|------|--------|:---:|------|
| `stock_zh_index_daily` | 新浪 | YES | 只有 volume（股数），无成交额 |
| `stock_zh_index_daily_em` | 东财 App | YES | 大部分指数可用 |
| `index_zh_a_hist` | 东财 Web | NO | IP 被封 |
| `stock_zh_a_spot_em` | 东财 EM | NO | IP 被封 |
| `stock_sse_deal_daily` | 上交所 | YES | 成交额、换手率等 |
| `stock_szse_summary` | 深交所 | YES | 成交额、市值等 |
| `stock_market_activity_legu` | 乐股 | YES | 涨跌家数、涨停数 |
| `index_option_50etf_qvix` | 东财 | YES | 中国波指 |
| `stock_hsgt_hist_em` | 东财 EM | YES | 北向资金 |
| `bond_zh_us_rate` | 东财 | YES | 国债收益率 |
| `macro_china_pmi` | 东财 | YES | PMI 数据 |
| `stock_zt_pool_em` | 东财 EM | YES | 涨停池 |

**经验教训：**
- 云服务器使用 AKShare 必须有备用接口，东财 Web 端接口限制最严格
- `stock_zh_index_daily` 的 volume 字段是股数不是金额，需要用交易所官方接口获取成交额
- 对大表（如 trade_stock_daily）的聚合查询不适合放在实时 API 中，应预计算存入 macro_data
- `_load_macro(days=N)` 的 `N` 是自然日，转换为交易日约乘以 250/365

---

*文档维护：每次开发后更新此文件，新日期追加在上方*

---

## 2026-04-14 策略系统重构与数据完备性监控

### 今日工作内容

#### 1. 预设策略从 Threading 迁移到 Celery

**问题：** 之前使用 threading 执行策略任务，微盘股策略卡住（运行6小时+），无法监控和重试。

**解决方案：**
- 创建 `/root/app/api/tasks/celery_app.py` 配置 Celery Beat 定时任务
- 修改 `/root/app/api/tasks/preset_strategies.py` 使用 Celery 任务
- 添加 `_get_recent_occurrence_counts()` 统计5日出现次数

**定时任务配置：**
```python
'watchlist-scan': '0 16:30 * * 1-5'      # 工作日 16:30 扫描自选股
'preset-strategies': '0 19:30 * * 1-5'  # 工作日 19:30 运行预设策略
'log-bias-daily': '0 16:00 * * 1-5'     # 工作日 16:00 对数乖离率
```

#### 2. 策略日期逻辑修复

**问题：** 策略使用 `date.today()` 作为日期，导致盘后运行时日期不匹配。

**解决：** 从数据库查询最新交易日期：
```python
trade_date_rows = execute_query(
    "SELECT MAX(trade_date) AS max_date FROM trade_stock_daily WHERE ..."
)
trade_date_str = str(trade_date_rows[0]['max_date'])
```

#### 3. 动量反转策略5日出现次数统计

**功能：** 显示每只股票在最近5日内的出现次数，便于识别频繁信号股票。

**实现：**
- 后端：`_get_recent_occurrence_counts(stock_codes, days=5)`
- 前端：策略信号表格新增"5日出现"列
- 颜色标识：≥3次红色，≥2次橙色
- 已回填历史数据（04-12、04-13）

#### 4. 数据完备性检查系统

**问题：** 各数据表状态未知，缺少监控。

**解决方案：**
- 创建 `scheduler/check_data_completeness.py` 每日检查脚本
- 新建 `trade_data_health` 表存储检查历史
- API 端点：
  - `GET /api/analysis/health-check/latest` - 最新检查结果
  - `GET /api/analysis/health-check/summary` - 状态摘要
  - `POST /api/analysis/health-check/run` - 手动触发检查

**检查状态分类：**
| 状态 | 含义 |
|------|------|
| ok | 数据正常 |
| warning | 数据滞后1-3天 |
| critical | 数据滞后>3天 |
| empty | 空表 |

#### 5. 前端修复

**问题修复：**
- 统一 API 环境变量：`NEXT_PUBLIC_API_URL` → `NEXT_PUBLIC_API_BASE_URL`
- 修复搜索接口指向 localhost 的问题
- 隐藏组合管理入口（暂时）

#### 6. Docker 部署问题修复

**问题1：** uvicorn 找不到
```
exec: "uvicorn": executable file not found in PATH
```
**原因：** `-v /root/app/.pip_cache:/root/.local` 覆盖了镜像中的依赖
**解决：** 移除该卷挂载

**问题2：** RAG_API_KEY 未配置
**解决：** 配置 DashScope API Key 到环境变量

#### 7. 数据完备性检查结果

| 数据表 | 记录数 | 最新日期 | 状态 |
|--------|--------|----------|------|
| trade_stock_daily | 662万+ | 2026-04-13 | ✅ OK |
| trade_stock_daily_basic | 567万+ | 2026-04-10 | ⚠️ 滞后3天 |
| trade_stock_rps | 658万+ | 2026-03-31 | 🔴 滞后13天 |
| trade_log_bias_daily | 3,180 | 2026-04-10 | ⚠️ 滞后3天 |
| financial_income | 0 | - | ❌ 空表 |
| financial_balance | 0 | - | ❌ 空表 |
| financial_dividend | 0 | - | ❌ 空表 |

**待办事项：**
- [ ] 下载财务数据（一页纸研报需要）
- [ ] 更新 daily_basic 数据
- [ ] 更新 RPS 数据
- [ ] 更新 extended_factor 数据

---

*文档维护：每次开发后更新此文件，新日期追加在上方*
