# myTrader 每日开发日志

---

## 2026-04-17 (续) Briefing 生成改为 Celery 异步队列

### Briefing 异步化

**问题：** `GET /api/market/global-briefing?force=true` 同步调用 LLM 生成（~16s），前端等待响应期间阻塞 API worker，且用户体验差（长时间白屏等待）。

**方案：** 改为 Celery 异步任务 + 前端轮询。

**改动：**

1. **新增 Celery task** (`api/tasks/briefing_tasks.py`)
   - `generate_briefing_async(task_id, session)` — 按需生成 briefing 写入 DB，不发飞书

2. **新增 API 端点** (`api/routers/market.py`)
   - `POST /global-briefing/submit` — 提交异步任务，有缓存直接返回 `{status: "cached"}`，否则派发 Celery task 返回 `{task_id, status: "submitted"}`。内存 dict 去重防止重复提交
   - `GET /global-briefing/status?task_id=xxx` — 轮询 Celery AsyncResult，映射状态为 `pending|running|done|failed`，done 时附带完整 briefing 内容
   - 原有 `GET /global-briefing` 不变，向后兼容

3. **前端改造** (`web/src/app/sentiment/page.tsx`)
   - "重新生成" 按钮改为调用 `POST /submit`，拿到 task_id 后每 3s 轮询 `/status`
   - 新增 `generating` 状态和 `genError` 错误提示
   - 轮询到 done 时 refetch 刷新内容，failed 时显示红色错误提示
   - 组件卸载时自动清理 interval

**验证：**
- `POST /submit` 有缓存时返回 `{status: "cached"}` ✓
- Celery task 执行成功（~16s），日志完整 ✓
- `GET /status` 返回 `{status: "done", briefing: {...}}` ✓
- 原有 `GET /global-briefing` 正常返回 ✓
- 前端页面加载正常（HTTP 200）✓

### 文件变更

| 文件 | 改动 |
|------|------|
| `api/tasks/briefing_tasks.py` | +generate_briefing_async task |
| `api/routers/market.py` | +POST /submit, +GET /status, +内存去重 dict |
| `web/src/app/sentiment/page.tsx` | 重新生成改为 submit+poll 模式 |

---

## 2026-04-17 公众号精选报告三合一 / 晨报排障 / Celery Worker 重启

### 1. 公众号精选报告三合一

**问题：** 之前 nightly_digest 管道按 macro/broker/other 三个类别分别生成三篇独立报告发到飞书，导致跨篇重复严重（同一事件在多篇中反复叙述）、结构模板化（三篇共6段风险提示+6条推荐阅读）、信息密度低。

**改动：**
- 新增 `_REPORT_SYSTEM_COMBINED` prompt，按信息维度组织（宏观与政策 -> 行业与公司 -> 市场情绪与事件 -> 综合研判 -> 风险清单 -> 推荐原文），全局去重，2000字以内
- 新增 `_generate_combined_report()` 函数，将三类文章拼成一个 prompt 一次调用 LLM
- 修改 `generate_categorized_reports()` 主逻辑，从循环三次改为一次综合生成
- 旧 prompt 和函数保留不删，可回退

**效果：** 22篇文章 -> 1篇2233字综合报告（原先三篇合计约2800字），信息密度明显提升，风险和推荐各只出一次。

### 2. 报告持久化 (trade_article_report)

新建 `trade_article_report` 表，每次生成的报告自动写入 DB（report_date + report_type 唯一键，支持 upsert）。含 content/article_count/document_id/doc_url 字段。migration: `t1u2v3w4x5y6`。

### 3. 晨报未推送排障

**现象：** 今日 08:44 晨报内容已生成并存入 trade_briefing 表，但飞书未收到。

**根因：** Celery Worker 容器内代码已更新（含 briefing_tasks.py），但 worker 进程未重启，导致 `publish_morning_briefing` task 未注册。Beat 调度后 worker 报 `Received unregistered task`。

**修复：** `docker restart app-celery-worker-1`，重启后手动触发 `publish_latest_briefing('morning', force=True)` 补发。

### 4. Python 3.9 兼容性修复

`api/services/llm_client_factory.py` 中 `str | None` 类型注解在 Python 3.9 下报错（需 3.10+），改为 `Optional[str]`。

### 文件变更

| 文件 | 改动 |
|------|------|
| `api/services/article_digest_service.py` | +combined prompt, +_generate_combined_report(), +DB persist, 改 generate_categorized_reports() |
| `api/services/llm_client_factory.py` | fix: `str\|None` -> `Optional[str]` |
| `alembic/versions/t1u2v3w4x5y6_...py` | 新增 trade_article_report 表 migration |

---

## 2026-04-16 (续) 精选观点日报 / Celery 统一调度 / 晨报复盘优化

### 今日新增工作

#### 5. 精选观点日报 (wechat2rss -> LLM -> 飞书)

**背景：** 订阅了 29 个微信公众号，每日产出大量投资相关文章。需要自动筛选、提炼、生成高价值精选报告。

**数据流：**
```
wechat2rss (res.db) -> export脚本 (规则预筛) -> JSON文件
  -> Stage A: LLM粗筛 (分类+评级A/B/C/D+一句话) -> A/B级文章
  -> Stage B: LLM深度提炼 (事实/观点分离, 结构化JSON) -> DB
  -> Report: 交叉验证+去重+价值排序 -> 飞书文档(公开可读) + Bot卡片
```

| 组件 | 说明 |
|------|------|
| `scripts/export_wechat_articles.py` | 从 res.db 导出过去24h文章, 规则过滤(>1500字/标题黑名单/每源限3篇) |
| `api/services/article_digest_service.py` | 两阶段 LLM 筛选 + 结构化报告生成 |
| `api/tasks/data_pipeline_tasks.py` | Celery task wrapper, 包含 run_nightly_digest |
| `api/services/feishu_doc_publisher.py` | 飞书文档发布, 自动设置互联网分享可见 |

**报告结构（按内容维度分模块）：**
- 宏观与政策 -- 宏观数据、地缘政治、贸易相关
- 行业与公司 -- 行业趋势、公司基本面、财报数据
- 市场策略 -- 择时、仓位、风格切换
- 风险提示 -- 汇总去重
- 编辑点评 -- 2-3句话主线判断
- 推荐深入阅读 -- 1-2篇原文链接

**首次运行结果：** 30篇文章 -> 7A+15B -> 22篇深度提取 -> 1份报告, 0错误

---

#### 6. Celery Beat 统一调度 (35 任务)

**背景：** 项目存在两套调度系统 -- Celery Beat (20任务, 生产活跃) 和 YAML Scheduler (30+任务, 未激活)。统一到 Celery Beat 作为唯一生产调度入口。

| 修复项 | 修复前 | 修复后 |
|--------|--------|--------|
| 恐慌指数过度执行 | 每小时 = 24次/天 | 3次/天 (08:00/12:00/18:30) |
| 16:30 三任务冲突 | precheck + watchlist + sim_pool 同时 | 16:25/16:30/16:35 错开 |
| 5个 adapter 函数缺失 | Celery引用但不存在 | run_data_gate/factor_calc/indicator_calc/integrity_check/tech_scan |
| 15个 YAML 任务未纳入 | 只在 YAML 中定义 | 全部加入 beat_schedule |

**依赖链（时间间隔保证）：**
```
data_gate (18:00) -> factor_calc (18:30) -> indicator_calc (19:30)
  -> preset_strategies (20:10) -> theme_pool_score (20:40) -> dashboard_compute (21:00)
```
重任务间隔 30-40min, 轻任务间隔 5min, 避免 3.6GB 服务器 OOM。

**详细文档：** `docs/celery_schedule_consolidated.md`

---

#### 7. 晨报/复盘 Prompt 优化

| 改动 | 说明 |
|------|------|
| 拆分 SYSTEM_PROMPT | 晨报侧重"今日机会预判", 复盘侧重"盘面回顾+隔夜风险评估" |
| 新增数据健康报告 | `api/services/daily_health_report.py`, 检查5张核心表数据质量 |
| API 端点 | `POST /publish-briefing`, `GET/POST /data-health` |

---

### 涉及文件

| 文件 | 类型 | 说明 |
|------|------|------|
| `api/services/article_digest_service.py` | 新建 | 两阶段 LLM 文章摘要 + 精选报告 |
| `api/services/feishu_doc_publisher.py` | 新建 | 飞书文档发布(自动公开权限) |
| `api/services/daily_health_report.py` | 新建 | 数据健康日报 |
| `api/tasks/data_pipeline_tasks.py` | 新建 | 13个 Celery task wrapper |
| `api/tasks/briefing_tasks.py` | 新建 | 晨报/复盘 Celery tasks |
| `api/tasks/celery_app.py` | 重写 | 统一 35 任务 beat_schedule |
| `scheduler/adapters.py` | 修改 | 新增 5 个 adapter 函数 |
| `api/services/global_asset_briefing.py` | 修改 | 晨报/复盘 prompt 拆分 |
| `api/routers/market.py` | 修改 | 新增 API 端点 |
| `scripts/export_wechat_articles.py` | 新建 | wechat2rss 文章导出脚本 |
| `docs/celery_schedule_consolidated.md` | 新建 | 调度整合文档 |

---

## 2026-04-16 26 commits -- 认证移除 / 因子 OOM / 收盘简报分层 / 舆情研报 / CI/CD 修复 / API 502 排查

### 今日工作内容

#### 1. JWT 认证全局移除

**背景：** 个人项目无需多用户鉴权，JWT 中间件导致前端频繁 401，阻碍开发调试。

| 文件 | 改动 |
|------|------|
| `api/middleware/auth.py` | `get_current_user` 改为可选依赖，无 token 时返回 None 而非 401 |
| `api/routers/watchlist.py` | 移除 GET/DELETE 端点的 auth 依赖 |
| `api/main.py` | 全局禁用 JWT 鉴权 |

**效果：** 所有 API 端点开放访问，前端不再出现 401 错误。

---

#### 2. 自选股搜索 + 关注栏

| 功能 | 实现 |
|------|------|
| 搜索选股自动加入关注 | `POST /api/watchlist/auto-add`，搜索结果点击后自动关注 |
| 个股页关注栏 | `/stock` 页面顶部展示关注列表，点击跳转，支持删除 |
| 刷新同步 | 选择股票后刷新关注栏状态 |

---

#### 3. 因子计算 OOM 修复（两次迭代）

**问题：** ECS 3.6G RAM + 4G Swap，因子计算全表扫描导致 OOM。

**第一次修复 (5ae0070)：** 全表扫描改为增量批计算，按日期逐日计算仅缺失数据。

**第二次修复 (4cc88b4)：** 辅助数据（stock_basic/daily_basic）也改为分批加载，每批 500 只；Celery 调度间隔从 15s 拉宽到 60s，避免多个因子任务并发 OOM。

---

#### 4. 收盘简报（Briefing）升级

**Morning/Evening 分离：**
- `global_asset_briefing.py` -- 拆分为 `MORNING_PROMPT`（盘前概览）和 `EVENING_PROMPT`（收盘复盘）
- 盘前：全球资产隔夜表现 + 今日关注
- 盘后：A股行情总结 + 板块热点 + 涨跌停分析

**Briefing 结构升级为 5 层：**
1. 全球资产隔夜概览
2. A 股大盘表现（含成交额/涨跌家数/涨跌停）
3. ETF 表现与资金流向
4. 板块热点与涨跌停明细
5. 明日关注

**缓存优化：**
- Redis 缓存，盘前简报 08:00-12:00 有效，盘后简报 16:00-23:59 有效
- 前端 `useTimeAwareCache` hook 自动判断缓存有效性

**数据校验增强：**
- `freshness_guard` 检查数据新鲜度，核心指标缺失时拒绝生成
- AH 溢价指数描述修正（点值 ~11，非百分比）

---

#### 5. 外部文章摘要服务 (Article Digest)

新增 `article_digest_service.py`，抓取指定 URL 文章内容，LLM 生成中文摘要，写入飞书文档。

- 支持批量 URL 列表
- Celery 定时任务（每晚 21:00）
- 飞书文档自动发布

---

#### 6. 夜间精选观点报告 (Nightly Curated Opinion)

新增 `briefing_tasks.py` Celery 任务，每晚 21:30 生成精选市场观点报告：
- 从多个信源抓取当日市场观点
- LLM 筛选、分类、生成结构化报告
- 写入飞书文档供次日晨读

**Celery 调度整合：**
- 将散落在各处的 Celery 配置整合到 `celery_app.py`
- 统一调度：盘后扫描、简报生成、文章摘要、观点报告

---

#### 7. Celery 调度管道增强

**新增数据管道：**
- `data_pipeline_tasks.py` -- 每日 15:30 增量拉取 A 股日线价格数据

**ETF Log Bias 触发优化：**
- 强制重新触发机制（force re-trigger）
- Sparkline 日期标签修正

---

#### 8. CI/CD 部署修复

| 问题 | 修复 |
|------|------|
| SSH key 解析失败 | 替换 `appleboy/ssh-action` 为原生 `ssh` 命令 |
| 部署后 Nginx 配置不生效 | 部署脚本末尾加 `docker restart nginx` |
| PostHog 自托管占用过多资源 | 移除 PostHog，Celery 加入 CI/CD deploy |
| test.yml 缺少 workflow_call trigger | 补充触发器 |

---

#### 9. 策略系统优化

| 功能 | 说明 |
|------|------|
| 单行重算按钮 | 策略信号表格每行增加"重新计算"按钮，支持单独重算某只股票 |
| 5 日出现次数修复 | `momentum_reversal` 的 `_get_recent_occurrence_counts` 修复 |
| log_bias Celery 导入修复 | 修正 import 路径 |

---

#### 10. 数据完备度页面增强

| 改进 | 说明 |
|------|------|
| 完整度百分比条 | 顶部显示总完整度进度条 |
| Redis 缓存 | 查询结果缓存 1 小时，避免重复查库 |
| 并行查询 | 16 个维度并行查询，修复 504 超时（原 30s -> 3s） |
| 任务运行状态 Tab | 新增 Tab 展示 scheduler task runs 历史 |

---

#### 11. 数据健康微信 OG Image

新增 OG Image 生成，在微信分享 `/data-health` 链接时展示预览卡片。

---

#### 12. API 502 线上故障排查与修复

**现象：** `http://123.56.3.1/data-health` 和 `http://123.56.3.1/sentiment` 返回 502。

**根因：** `api/routers/documents.py` 使用 `UploadFile = File(...)`，FastAPI 要求 `python-multipart` 包。Dockerfile 用 `requirements-prod.txt` 构建镜像，但该文件缺少 `python-multipart`，导致 API 进程启动时崩溃（RuntimeError），所有 `/api/*` 请求 502。

**修复：**
1. 临时：容器内 `pip install python-multipart` + 重启，服务恢复
2. 根治：`requirements-prod.txt` 的 Web Framework 区段补上 `python-multipart>=0.0.6`

**教训：** 项目维护两份依赖文件（`requirements.txt` 和 `requirements-prod.txt`），新增运行时依赖时容易遗漏。建议后续统一为一份或加 CI 校验。

---

### 今日 Git 提交（26 个，按时间顺序）

```
7d33846 fix: repair momentum_reversal 5-day occurrence count and log_bias celery import
0dc5f27 fix: auto-add stock to watchlist on search select without auth
7951bd5 feat: add task run log, freshness guard, and data-health task status tab
0fc5c8e fix: remove auth from all watchlist endpoints (GET/DELETE)
81ce626 feat: show watchlist bar on /stock page with click-to-view and remove
21e9d8c fix: add workflow_call trigger to test.yml for reusable workflow
95b2c4c fix: disable JWT auth globally -- all API endpoints open
5ae0070 fix: replace full-table-scan with incremental batch calculation in all factor calculators
e793ae2 feat: add completeness % bar to data-health page
eabf7a1 perf: cache data-health results in Redis for 1 hour
f07ef9a fix: parallelize data-health queries to fix 504 timeout
481ee72 fix: refresh watchlist bar after selecting a stock from search
b1b340d chore: remove self-hosted PostHog, add Celery to CI/CD deploy
cec2783 fix: restart nginx in deploy to pick up config changes
c682335 fix: localize briefing abort message and fix false-positive data check
ca0cd92 ci: trigger deploy
f11c723 ci: test new deploy key
a42c690 fix: replace appleboy/ssh-action with native ssh to fix key parsing
393de14 feat: auto-load AI briefing with time-aware caching
e983680 fix: correct AH premium index description (point value ~11, not base=100)
21fedc3 feat: upgrade briefing to layered 5-section structure with ETF/limit data
55bc691 feat: add OG image for WeChat sharing card
96e9742 feat: add article digest service for external content integration
e0d553f feat: add per-row recalculate button for strategy runs
19e3bcf feat: ETF log bias force re-trigger + sparkline date labels
ddecbc3 feat: add daily stock price fetch to scheduler pipeline
aea17d6 fix: akshare fallback to Sina source, fix factor_calculator import
4cc88b4 fix: OOM prevention - batch-load auxiliary data in factor calculators + widen schedule gaps
3cec0cb feat: add nightly curated opinion report pipeline + consolidate Celery schedule
dab5b56 feat: differentiate morning/evening briefing prompts, resolve merge conflicts
33c1404 fix: auto-detect article export dir for Docker vs bare-metal
```

### 待完成

- [ ] `requirements-prod.txt` 与 `requirements.txt` 依赖一致性校验（CI 层面）
- [ ] 飞书文档发布服务 (`feishu_doc_publisher.py`) 的 token 配置和端到端测试
- [ ] 夜间观点报告的数据源和 prompt 调优
- [ ] Briefing 数据校验 T1-T4（昨日改进方案中的 P0 任务）

---

### Code Review 修复 (aea17d6..33c1404, 5 commits)

对今日 5 个提交做 code review, 发现并修复以下问题:

#### P0 -- 运行时崩溃

**1. article_digest_service DDL 列缺失**

`article_digest_service.py` 的 INSERT 语句引用 `digest_date`, `grade`, `summary`, `used_in_report` 四个列, 但 migration DDL (`r1s2t3u4v5w6`) 中不存在这些列。运行时直接 SQL 报错。

- **修复**: 更新 migration, 新增 `digest_date`, `grade`, `digest_json`, `summary`, `used_in_report` 列和索引
- **文件**: `alembic/versions/r1s2t3u4v5w6_add_article_digest_table.py`

**2. Celery 调度与文档严重不一致**

`celery_app.py` 有重复的 `daily-evening-precheck` 和 `sim-pool-daily-update` 条目 (L49-53 与 L127-131, L61-65 与 L183-187)。恐慌指数仍为每小时执行 (24次/天), 时间间隔未按 OOM 优化方案调整。

- **修复**: 重写 `celery_app.py`, 去重并按时间顺序整理; 恐慌指数改为 3次/天 (08:00/12:00/18:30); 因子->指标间隔拉到 60min; 健康报告改到 21:30
- **文件**: `api/tasks/celery_app.py`, `docs/celery_schedule_consolidated.md`

**3. Celery 任务模块未注册**

`api/tasks/__init__.py` 缺少 `briefing_tasks` 和 `data_pipeline_tasks` 的导入, 导致这两个模块中的 17 个 Celery 任务不会被 `autodiscover_tasks` 发现。Beat 调度会报 `NotRegistered`。

- **修复**: 在 `__init__.py` 中补充导入
- **文件**: `api/tasks/__init__.py`

#### P1 -- 安全/可靠性

**4. 硬编码凭证泄露**

`feishu_doc_publisher.py:282` 硬编码了飞书用户 Open ID 到 git 仓库。

- **修复**: 改为从 `settings.FEISHU_OWNER_OPEN_ID` 读取, 保留默认值兼容
- **文件**: `api/services/feishu_doc_publisher.py`, `api/config.py`

**5. 硬编码服务器 IP 和脚本路径**

`daily_health_report.py:308` 硬编码 `http://123.56.3.1/data-health`; `data_pipeline_tasks.py:150` 硬编码 `/root/app/scripts/export_wechat_articles.py`。

- **修复**: 改为从 `settings.DATA_HEALTH_URL` / `settings.ARTICLE_EXPORT_SCRIPT` 读取, 保留默认值兼容
- **文件**: `api/services/daily_health_report.py`, `api/tasks/data_pipeline_tasks.py`, `api/config.py`

**6. akshare_fetcher 线程不安全**

`_eastmoney_failures` 全局变量在 `ThreadPoolExecutor` 多线程并发修改, 无锁保护。

- **修复**: 添加 `threading.Lock`, 修改计数时加锁
- **文件**: `data_analyst/fetchers/akshare_fetcher.py`

**7. akshare_fetcher 失败检测永远为 true**

`download_and_save` 返回 `(code, count, err)`, count 是 `len(rows)` 始终 >= 0。`count >= 0` 永远为 True, fail_list 永远为空。

- **修复**: 改为 `err is not None` 判断失败
- **文件**: `data_analyst/fetchers/akshare_fetcher.py`

**8. DB 连接泄漏**

`download_and_save` 中 `executemany` 异常时 `cursor.close()` 和 `conn.close()` 不会执行。

- **修复**: 用 `try/finally` 包裹
- **文件**: `data_analyst/fetchers/akshare_fetcher.py`

**9. API 端点缺少认证**

`/publish-briefing`, `/data-health`, `/data-health/push` 可向飞书推送内容, 但无 `get_current_user` 认证。

- **修复**: 三个端点均添加 `Depends(get_current_user)`
- **文件**: `api/routers/market.py`

#### P2 -- 代码质量

**10. `_extract_verdict` 过度 strip**

`line.strip('* ')` 会去掉所有首尾 `*` 和空格, 对 `*** text ***` 等内容会过度删除。

- **修复**: 先检查 `startswith('**') and endswith('**')`, 再用 `line[2:-2].strip()`
- **文件**: `api/services/feishu_doc_publisher.py`

**11. subprocess 输出未捕获**

`data_pipeline_tasks.py` 的 `subprocess.run()` 未设置 `capture_output=True`, 失败时丢失错误信息。

- **修复**: 添加 `capture_output=True, text=True`, 记录 stdout
- **文件**: `api/tasks/data_pipeline_tasks.py`

**12. 未使用的 import**

`daily_health_report.py` 导入了 `timedelta` 但未使用。

- **修复**: 移除未使用 import
- **文件**: `api/services/daily_health_report.py`

#### 修改文件汇总

| 文件 | 改动类型 |
|------|---------|
| `alembic/versions/r1s2t3u4v5w6_add_article_digest_table.py` | 新增 4 列 + 1 索引 |
| `api/tasks/celery_app.py` | 重写, 去重 + 时间修正 |
| `api/tasks/__init__.py` | 补充 2 个模块导入 |
| `api/config.py` | 新增 3 个环境变量 |
| `api/services/feishu_doc_publisher.py` | Open ID 改环境变量 + strip 修复 |
| `api/services/daily_health_report.py` | IP 改环境变量 + 移除未用 import |
| `api/tasks/data_pipeline_tasks.py` | 路径改环境变量 + capture_output |
| `api/routers/market.py` | 3 端点添加认证 |
| `data_analyst/fetchers/akshare_fetcher.py` | 线程锁 + 失败检测 + DB 泄漏修复 |
| `docs/celery_schedule_consolidated.md` | 同步更新时间表 |

---

## 2026-04-15 收盘复盘行情回顾 -- 数据质量与幻觉问题排查

### 问题背景

用户使用系统生成的收盘复盘（Evening Briefing）与实际行情对比，发现多处严重数据错误和 LLM 幻觉。
**核心原则：投资是严肃的事情，宁愿说"数据缺失/不确定"也不许瞎说。**

### 错误清单

#### 严重错误（数据失真，直接影响投资判断）

| # | 指标 | 系统输出 | 实际值 | 偏差 | 根因分析 |
|---|------|---------|--------|------|---------|
| 1 | 成交额 | 2.15万亿 | 2.43万亿 | -13% | macro_data.market_volume 数据未更新到当日，LLM 使用了过期数据或自行编造 |
| 2 | 涨跌家数 | 2312涨/2719跌 | 1702涨/3387跌 | 涨多报610只，跌少报668只 | advance_count/decline_count 缺失或过期，LLM 自行"脑补"了看似合理的数值 |
| 3 | 跌停家数 | 4家 | 15家 | 少报11只（4倍偏差） | limit_down_count 缺失，LLM 编造了"仅4家" |
| 4 | AH溢价 | 11.51 | 118.94 | 格式完全错误 | AH溢价指数基准为100，实际值约118.94；macro_data中存储的是原始指数值，但 LLM 可能将其误解为百分比溢价率(18.94%->11.51) |
| 5 | 沪深300涨幅 | +0.21% | 当日上证仅+0.01%，300大概率微跌或持平 | LLM 编造了具体涨幅数值 |
| 6 | 中证1000涨幅 | +0.34% | 深成指-0.97%、创业板-1.22%，小盘大概率也下跌 | LLM 编造了具体涨幅数值 |

#### 定性错误（LLM 解读偏差）

| # | 描述 | 系统输出 | 应有判断 |
|---|------|---------|---------|
| 7 | 市场格局判断 | "个股分化明显" | 1700涨/3400跌是明显普跌，不是"分化" |
| 8 | 情绪判断 | "情绪中性" | 普跌+15只跌停，应为偏弱 |
| 9 | 走势描述 | "震荡整理" | 创业板盘中创2015年来新高后跳水-1.22%，应为"冲高回落" |
| 10 | 创业板重大事件 | 完全未提及 | 创业板指盘中创2015年6月19日以来新高后跳水，止步5连阳，是当日最重要技术信号 |
| 11 | 热点板块 | 完全未提及 | 医药板块（国办政策利好）是当日核心主线，GPU/钠电池/折叠屏等活跃 |

#### 不可验证但存疑

| # | 指标 | 系统输出 | 存疑原因 |
|---|------|---------|---------|
| 12 | 北向资金 | "净流出" | 港交所已调整披露机制，不再实时展示净买额，来源可疑 |
| 13 | 10Y国债收益率 | 1.783% | 近期区间1.81%-1.84%，偏低约3bp |
| 14 | 封板率 | 50% | 涨停基数就不对(59 vs 实际68)，封板率无法验证 |

### 根因总结

1. **数据管道断裂**：macro_data 表的 4月9日-15日数据未入库（fetcher 未执行），LLM 拿到的是过期数据或空值
2. **LLM 无数据校验约束**：当数据缺失时，LLM 不说"数据缺失"，而是自行编造看似合理的数值（幻觉）
3. **Prompt 无数据完备性声明**：EVENING_PROMPT 未要求 LLM 标注哪些数据是实际值、哪些是缺失的
4. **数据快照无日期标注**：`_collect_dashboard_snapshot()` 输出的数据没有标注每个指标的实际日期，LLM 无法判断数据是否过期
5. **AH溢价单位歧义**：macro_data 存储的是原始指数值(118.94)，但 Prompt 中未标注单位，LLM 可能误解
6. **缺少板块/行业/个股层面数据**：Dashboard 仅提供宽基指数级别信号，缺少板块轮动和个股亮点数据，LLM 无法生成板块分析
7. **缺少涨跌停个股明细**：仅有涨停/跌停数量统计，无个股名单和原因分类，无法做风格解读

### 数据库现状

- `trade_stock_daily` 最新数据：2026-04-08（缺失 04-09 ~ 04-15 共5个交易日）
- `macro_data` 部分指标：同样滞后
- 涨跌家数(advance_count/decline_count)：依赖 `stock_market_activity_legu()` 或 `stock_zh_a_spot_em()`，需当日盘后执行

---

## 2026-04-15 收盘复盘改进方案

### 改进原则

**投资是严肃的事情，宁愿说"不知道"也不许瞎说。** 所有改进围绕三条铁律：

1. **数据先验证，再解读** -- 任何指标在进入 LLM Prompt 之前必须通过完备性校验
2. **缺失即标注** -- 数据缺失/过期时，Prompt 中明确标注 `[数据缺失]` 或 `[数据过期: 实际日期 vs 目标日期]`
3. **LLM 禁止编造数值** -- Prompt 硬约束：对于标注为缺失/过期的数据，必须回答"数据暂缺"，不得自行推测

### 改进任务清单

#### P0 -- 消除幻觉（必须立即修复）

**T1: 数据完备性校验层** (`global_asset_briefing.py`)

在 `_collect_data_snapshot()` 和 `_collect_dashboard_snapshot()` 中增加数据新鲜度校验：

```python
def _validate_data_freshness(indicator: str, latest_date: str, target_date: str) -> str:
    """
    校验数据新鲜度，返回状态标注。
    - 当日数据 -> "[OK]"
    - 滞后1天 -> "[WARN: 数据为{latest_date}，非当日]"
    - 滞后>1天 -> "[STALE: 数据停留在{latest_date}，已过期{N}天]"
    - 无数据 -> "[MISSING: 无数据]"
    """
```

修改数据快照输出格式，为每行指标追加新鲜度标注：
```
| 指标 | 最新值 | 日期 | 状态 |
| 成交额 | 21522亿 | 2026-04-08 | [STALE: 过期7天] |
| 涨跌家数 | -- | -- | [MISSING: 无数据] |
```

**T2: Prompt 硬约束** (`global_asset_briefing.py`)

在 SYSTEM_PROMPT 中增加不可违反的规则：

```python
SYSTEM_PROMPT += """
## 铁律（不可违反）
1. 你收到的数据表格中，标注为 [MISSING] 或 [STALE] 的指标，必须在输出中注明"数据暂缺"或"数据过期(截止XX日)"，不得自行推测或编造数值
2. 不得编造任何未在数据表中出现的具体数值（涨跌幅、成交额、资金流向等）
3. 如果某个维度的核心指标全部缺失，该维度输出"[数据不足，无法判断]"，不做空泛推测
4. 涨跌家数、涨停/跌停等市场微观结构数据如缺失，不得用"个股分化"等模糊措辞替代
5. AH溢价指数基准为100（>100表示A股溢价），不要将其误读为百分比
"""
```

**T3: Dashboard 数据快照增加日期标注** (`calculator.py`)

`compute_dashboard()` 返回的每个板块增加 `data_date` 字段：

```python
{
    "temperature": {
        "available": True,
        "data_date": "2026-04-08",  # 新增：数据实际日期
        "target_date": "2026-04-15",  # 新增：目标日期
        "is_fresh": False,  # 新增：是否为最新交易日数据
        "level": "常温",
        ...
    }
}
```

`_collect_dashboard_snapshot()` 利用 `is_fresh` 标注：
```
**市场温度** (信号: 常温) [STALE: 数据为04-08，非当日]
```

**T4: AH溢价单位显式标注**

在 INDICATOR_NAMES 中明确单位：
```python
'ah_premium': 'AH溢价指数(基准100，>100表示A股溢价)',
```

#### P1 -- 丰富数据维度（短期优化）

**T5: 增加板块/行业层面数据**

在 `_collect_dashboard_snapshot()` 中追加申万一级行业当日涨跌幅 Top5/Bottom5：
- 数据来源：`sw_industry_valuation` 表 或 AKShare `stock_board_industry_name_em()`
- 输出格式：`领涨行业: 综合+3.24% 电子+2.67% | 领跌行业: 石油石化-1.18% 煤炭-1.02%`

**T6: 增加涨跌停个股明细**

新增函数 `_collect_limit_stocks(trade_date)`:
- 数据来源：`stock_zt_pool_em()` / `stock_zt_pool_dtgc_em()`
- 输出涨停/跌停个股名单 + 所属概念板块
- 格式：`涨停73只，主要集中在: CPO/光模块(沪电股份/协创数据)、新能源(正邦科技/腾远钴业)、...`

**T7: 增加创新高/新低个股明细**

从 `macro_data.new_high_60d` / `new_low_60d` 扩展为具体个股名单（至少 Top10），便于 LLM 解读市场风格特征。

**T8: 增加指数分时特征**

当日指数的高点/低点/收盘位置关系（如"盘中创新高后回落收阴"），目前仅有收盘价，缺少分时信息。

#### P2 -- 数据管道健壮性（中期优化）

**T9: 数据管道断裂告警**

在 `generate_briefing()` 中增加前置检查：
```python
async def generate_briefing(session: str = 'morning') -> dict:
    # 前置检查：数据新鲜度
    freshness = _check_overall_freshness(target_date=today_str)
    if freshness['stale_count'] > 3:
        logger.error('[briefing] %d/%d indicators are stale, aborting generation',
                     freshness['stale_count'], freshness['total_count'])
        return {
            'session': session,
            'date': today_str,
            'content': '## 数据不足，暂无法生成行情回顾\n\n'
                       f"以下 {freshness['stale_count']} 项核心指标数据过期或缺失：\n"
                       + freshness['detail'],
            'cached': False,
            'data_quality': 'insufficient',
        }
```

当核心指标（成交额、涨跌家数、指数收盘价）缺失时，直接拒绝生成，返回数据不足提示，而不是让 LLM 编造。

**T10: 数据管道自动补拉**

在 Celery Beat 中增加数据完备性检查任务（每日 17:00），如果发现当日数据缺失自动触发补拉：
```python
'data-freshness-check': {
    'task': 'api.tasks.macro_fetch.check_and_backfill',
    'schedule': crontab(hour=17, minute=0, day_of_week='1-5'),
}
```

**T11: Briefing 输出增加数据质量评分**

在返回的 briefing 中附加元数据：
```python
{
    'content': '...',
    'data_quality': {
        'score': 0.72,  # 0-1, 数据覆盖率
        'fresh_indicators': 18,
        'stale_indicators': 4,
        'missing_indicators': 3,
        'stale_list': ['advance_count', 'decline_count', 'margin_balance', ...],
    }
}
```

前端据此在 AIBriefingCard 中展示数据质量提示：
- score >= 0.9: 正常展示
- 0.7 <= score < 0.9: 展示黄色提示"部分指标数据过期，仅供参考"
- score < 0.7: 展示红色警告"数据严重不足，解读可信度低"

#### P3 -- LLM 输出后校验（长期优化）

**T12: LLM 输出后置校验**

LLM 生成 briefing 后，用规则引擎做一轮后置校验：
- 提取 briefing 中提到的所有数值（正则匹配"XX万亿"、"XX只涨停"等）
- 与 `_collect_data_snapshot()` 中的实际值对比
- 偏差超过阈值的标记为 `[数据存疑]`
- 出现在 [MISSING] 列表中的指标如果 LLM 仍给出了数值，强制替换为"数据暂缺"

**T13: 历史 Briefing 回测验证**

建立回测机制：用历史数据生成 briefing，与实际行情对比，计算准确率指标：
- 方向准确率（涨/跌/震荡判断）
- 数值偏差率（成交额/涨跌家数等）
- 板块命中率（提到的热点板块是否实际领涨）

### 实施优先级

| 优先级 | 任务 | 预计工时 | 效果 |
|--------|------|---------|------|
| P0 | T1 数据完备性校验层 | 2h | 消除90%的数值幻觉 |
| P0 | T2 Prompt 硬约束 | 0.5h | 强制 LLM 不编造 |
| P0 | T3 Dashboard 日期标注 | 1h | LLM 能判断数据时效性 |
| P0 | T4 AH溢价单位标注 | 0.5h | 消除单位歧义 |
| P1 | T5 行业涨跌数据 | 2h | 解读能覆盖板块轮动 |
| P1 | T6 涨跌停明细 | 2h | 支持风格和情绪深度解读 |
| P1 | T7 创新高/低明细 | 1h | 捕捉市场结构变化 |
| P1 | T8 指数分时特征 | 1h | 识别冲高回落等日内模式 |
| P2 | T9 管道断裂告警 | 1h | 数据不足时拒绝生成 |
| P2 | T10 自动补拉 | 2h | 减少人工干预 |
| P2 | T11 质量评分 | 1.5h | 前端展示可信度 |
| P3 | T12 后置校验 | 3h | 兜底拦截漏网幻觉 |
| P3 | T13 回测验证 | 4h | 持续评估质量 |

### 改进后的数据流

```
AKShare / yfinance / 交易所
       |
macro_fetcher (Celery 每小时/每日)
       |
macro_data 表
       |
[新增] _check_overall_freshness()  <-- 前置校验
       |
       +-- 核心指标缺失 --> 拒绝生成，返回"数据不足"
       |
       +-- 数据充足 -->
            |
    _collect_data_snapshot()  (每行带 [OK]/[STALE]/[MISSING] 标注)
    _collect_dashboard_snapshot()  (每板块带 data_date/is_fresh)
    [新增] _collect_industry_snapshot()  (行业涨跌 Top5)
    [新增] _collect_limit_stocks()  (涨跌停明细)
            |
    EVENING_PROMPT + SYSTEM_PROMPT(含铁律约束)
            |
    LLM 生成 briefing
            |
    [新增] _post_validate(briefing, raw_data)  <-- 后置校验
            |
    trade_briefing 表 + data_quality 元数据
            |
    API 返回 (content + data_quality)
            |
    前端 AIBriefingCard (根据 data_quality.score 展示可信度提示)
```

---

## 2026-04-15（补充）RAG 知识库 Bug 修复 + 文档异步向量化

### 今日工作内容（补充）

#### 9. RAG 知识库页面汉化 + 部署修复

- `web/src/app/rag/page.tsx` — 全页面汉化（Knowledge Base -> 知识库，+ Upload -> + 上传等）
- 根因：本地改动未 commit 就 push，服务器拿不到更新；加之旧镜像未重建
- 修复流程：commit -> push -> 服务器 `git pull` -> `docker build --no-cache` -> 重启容器

---

#### 10. 收盘复盘 Markdown 渲染优化

- `web/src/app/sentiment/page.tsx` — 引入 `react-markdown`，替换手写 mini-renderer
- 自定义 `mdComponents` 适配深色主题变量（h1/h2/h3/p/ul/ol/li/hr/blockquote/code）
- 安装依赖：`react-markdown`（79 个包）

---

#### 11. RAG 错误处理 Code Review + 修复

**问题根因：** 后端超时或异常时返回 HTML，前端直接 `res.json()` 导致 `SyntaxError: Unexpected token '<'`

| 文件 | 问题 | 修复 |
|------|------|------|
| `DocumentUploadDialog.tsx` | `res.json()` 在 `res.ok` 检查之前 | 先检查 `res.ok`，再解析 JSON |
| `DocumentUploadDialog.tsx` | 无文件大小前端校验 | 加 100 MB 上限，本地报错不走网络 |
| `DocumentCard.tsx` | 保存/删除失败静默无提示 | 展示错误信息，删除失败用 `alert` |
| `rag/page.tsx` | `loadDocuments`/`handleSearch` 直接 `.json()` | 先检查 `res.ok` |
| `api/main.py` | 未捕获异常返回 Uvicorn HTML | 加全局 `@app.exception_handler(Exception)` 返回 JSON |

---

#### 12. 文档向量化改为 Celery 异步处理

**问题根因：** 向量化（解析 + Embedding API + ChromaDB 写入）耗时长，Nginx 300s 超时后返回 504 HTML，前端再次触发 `SyntaxError`。

**方案：上传接口立即返回，向量化交给 Celery worker 后台处理，前端轮询状态。**

| 文件 | 改动 |
|------|------|
| `api/services/document_service.py` | `upload_document()` 拆为两步：存文件+建DB记录（同步）；`process_document()` 做解析+向量化（供 Celery 调用）|
| `api/tasks/document_tasks.py` | 新增 `ingest_document_task` Celery task，`time_limit=600` |
| `api/routers/documents.py` | 上传后 `.delay(doc_id)` 触发异步任务；新增 `GET /{doc_id}/status` 状态轮询接口 |
| `DocumentUploadDialog.tsx` | 上传成功后每 3s 轮询一次状态，展示"上传中..."/"向量化中..."两阶段进度，最长等待 5 分钟 |

**效果：** 上传接口 < 1s 返回，不再受 Nginx 超时影响；用户可见实时进度。

---

## 2026-04-15 LLM Agent 体系 + 埋点系统 + Code Review 修复

### 今日工作内容

#### 1. LLM Agent 体系（M1–M3）

**M1：AI 驱动的主题创建 (theme-create)**

新增 `ThemeCreateSkill`，SSE 流式输出，流程：
1. LLM 将主题名映射为概念板块关键词
2. 从东方财富批量拉取概念板块成分股
3. LLM 二次过滤，输出带 relevance/reason 的候选股列表

**M2：多模型工厂 + Redis 缓存 + 统一流路由**

| 文件 | 说明 |
|------|------|
| `api/services/llm_client_factory.py` | 多模型别名路由（qwen/deepseek/doubao），async + thread executor |
| `api/services/akshare_cache.py` | Redis 缓存 AKShare 数据，TTL 可配置 |
| `api/routers/theme_pool.py` `POST /llm/stream` | 统一 SSE 路由，按 skill_id 分发 |
| `api/services/llm_usage_logger.py` | 异步 fire-and-forget 用量记录 |
| `api/services/llm_feedback.py` | helpful/unhelpful 反馈收集 |
| `alembic/versions/j1k2l3m4n5o6` | `llm_usage_logs` 表迁移 |
| `alembic/versions/k1l2m3n4o5p6` | `llm_feedback` 表迁移 |

**M3：Skill 体系（portfolio-doctor / signal-interpreter / theme-review）**

新增 `api/services/llm_skills/` 包：

| Skill | skill_id | 功能 |
|-------|----------|------|
| PortfolioDoctorSkill | `portfolio-doctor` | 持仓集中度/行业分布/调仓建议 |
| SignalInterpreterSkill | `signal-interpreter` | 策略信号列表解读 |
| ThemeReviewSkill | `theme-review` | 主题池内股票评分解读 |

前端新增：
- `LLMCreateDialog.tsx` — AI 创建主题 SSE 流展示
- `ThemeReviewDialog.tsx` — 主题评审 SSE 流展示
- `useSSEFetch.ts` — POST SSE 通用 hook

---

#### 2. 股票新闻动态 + 舆情增强

**后端：**
- `api/services/stock_news_service.py` — 东方财富新闻抓取（绕过 pyarrow bug）、LLM 情感分析、事件检测、存储
- `api/tasks/stock_news.py` — Celery 定时任务，每日 18:30 批量拉取所有已分析股票的新闻
- `alembic/versions/` — `stock_news` 表迁移

**前端：**
- `web/src/app/stock/page.tsx` — 新增"个股动态" tab，展示新闻列表 + LLM 情感分析结果

---

#### 3. 全球资产大盘 + 宏观 LLM 简报

**新增 `api/services/global_asset_briefing.py`：**
- 从 `macro_data` 表读取商品/利率/汇率/加密/美股 8 个标的
- 用 `yfinance` 批量下载（单次 HTTP 请求，添加指数退避重试）
- LLM 生成中文大盘简报

**前端：**
- `web/src/app/sentiment/page.tsx` — 新增"全球资产"tab（GlobalAssetsPanel）、DataHealthPanel 迁移进来
- 大盘总览 tab 顶部显示 LLM 市场简报

**Celery：**
- `api/tasks/macro_fetch.py` — 每小时 :15 分增量拉取（替代之前每日 17:30）

---

#### 4. 概念板块每日同步

- `data_analyst/fetchers/concept_board_fetcher.py` — 多数据源（Tushare > 东财 > 同花顺）拉取概念成分股，写入 `stock_concept_map` 表
- `alembic/versions/l1m2n3o4p5q6` — `stock_concept_map` 表迁移
- `tasks/08_theme_pool.yaml` — 每日同步任务

---

#### 5. 文档上传 + RAG 知识库 UI 重构

- `api/routers/documents.py` + `api/services/document_service.py` — PDF/MD/DOCX 上传、解析、向量写入 ChromaDB
- `alembic/versions/n1o2p3q4r5s6` — `research_document` 表迁移
- `investment_rag/ingest/parsers/docx_parser.py` — 新增 Word 解析器
- 前端 RAG 页面重构为"知识库"模式，新增 `DocumentCard.tsx`、`DocumentUploadDialog.tsx`

---

#### 6. 估值数据增强 M3（前端）

- `web/src/app/industry/page.tsx` — 新增行业估值热力图，从 `/analysis` 迁移过来
- `web/src/app/analysis/page.tsx` — 新增"估值分析" tab，行业 PE/PB 历史走势 + 分位带

---

#### 7. Code Review 修复（P0/P1）

| 文件 | 问题 | 修复 |
|------|------|------|
| `api/routers/documents.py` | 文件上传无大小限制 | 加 100 MB 上限，413 响应 |
| `api/routers/documents.py` | filename 路径遍历 | 上传前用 `PurePath(...).name` 净化 |
| `api/services/document_service.py` | 服务层同样未净化路径 | `Path(filename).name` 二次防护 |
| `api/routers/theme_pool.py` | `_get_user_or_dev` 无 token 可冒充任意用户 | 非 dev 环境强制返回 401 |
| `api/routers/theme_pool.py` | skills 每次请求重复 import | 改为模块级 import 一次 |
| `api/routers/theme_pool.py` | `trigger_score` 线程失败无堆栈 | 加 `exc_info=True` |
| `api/services/llm_client_factory.py` | HTTP 超时 60s 硬编码 | 改为 `LLM_HTTP_TIMEOUT` 环境变量（默认 90s） |
| `api/services/llm_client_factory.py` | 重试只覆盖 JSON 错误 | 扩展至 `OSError/ConnectionError` |
| `api/services/llm_usage_logger.py` | `utcnow()` 与系统时区不一致 | 改为 `datetime.now()` |
| `api/services/llm_skills/registry.py` | `list_skills` 每次创建 N 个实例 | 注册时缓存 meta，`list_skills` 不再实例化 |
| `api/tasks/stock_news.py` | Celery beat 重复触发无去重 | 加 Redis 同步锁（TTL=1h） |
| `api/tasks/macro_fetch.py` | 同上 | 加 Redis 同步锁（TTL=55min） |
| `web/src/hooks/useSSEFetch.ts` | SSE 无超时，连接可能永久挂起 | 默认 5 分钟 `AbortSignal.timeout()` |

---

#### 8. PostHog 埋点系统

**自托管部署：**
- `docker-compose.yml` 新增 `posthog`、`posthog-db`（PostgreSQL）、`posthog-redis` 三个服务
- `nginx.conf` 新增 `/analytics/` 反代到 PostHog 容器
- `.env.example` 新增 `POSTHOG_DB_PASSWORD` / `POSTHOG_SECRET_KEY` / `POSTHOG_SITE_URL`

**前端 SDK 接入：**

| 文件 | 说明 |
|------|------|
| `web/src/lib/posthog.ts` | Key/Host/Enabled 常量 |
| `web/src/components/PostHogProvider.tsx` | 初始化 + 路由变化自动 `$pageview` |
| `web/src/hooks/useTrack.ts` | 统一埋点 hook，自动带 `page` 字段 |
| `web/src/components/TrackingDelegate.tsx` | 全局点击委托，`data-track` 属性自动上报 |
| `web/src/app/layout.tsx` | 注入 PostHogProvider + TrackingDelegate |

**埋点覆盖：**

| 事件 | 触发位置 |
|------|---------|
| `$pageview` | 每次路由跳转（自动） |
| `nav_click` | 侧边栏所有导航项（AppShell） |
| `logout_click` | 退出登录按钮 |
| `tab_switch` | analysis/stock/sentiment 页 tab 切换 |
| `generate_briefing` | 分析页生成一页纸 |
| `generate_comprehensive_report` | 生成综合研报 |
| `generate_tech_report` | 生成技术面报告 |
| `stock_search_submit` | 个股搜索提交 |
| `add_to_watchlist` | 加入关注 |
| `reanalyze_stock_news` | 重新分析新闻 |
| `knowledge_search` | 知识库搜索 |
| `upload_document_open` | 打开文档上传弹窗 |
| `theme_llm_create_open` | 打开 AI 创建主题 |
| `theme_create_open` | 打开手动创建主题 |
| `strategy_trigger` | 触发策略执行 |
| `strategy_force_trigger` | 强制重新触发策略 |

IP 来源分析由 PostHog 自动从请求头提取，在 People/Sessions 页面直接查看。

**PostHog 启动步骤：**
```bash
# 1. 在 .env 填写 POSTHOG_DB_PASSWORD / POSTHOG_SECRET_KEY / POSTHOG_SITE_URL
# 2. 启动服务
docker compose up -d posthog-db posthog-redis posthog
# 3. 首次初始化
docker compose exec posthog python manage.py migrate
# 4. 重载 Nginx
docker compose restart nginx
# 5. 访问 http://<server>/analytics 完成注册，获取 Project API Key
# 6. 填入 web/.env.local: NEXT_PUBLIC_POSTHOG_KEY=phc_xxx
```

---

### 新增文件清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `api/services/theme_llm_service.py` | 新增 | ThemeCreateSkill + LLM 概念映射 |
| `api/services/stock_news_service.py` | 新增 | 股票新闻抓取 + 情感分析 |
| `api/services/global_asset_briefing.py` | 新增 | 全球资产数据 + LLM 简报 |
| `api/services/llm_client_factory.py` | 新增 | 多模型工厂 + 重试包装 |
| `api/services/llm_usage_logger.py` | 新增 | LLM 调用用量异步记录 |
| `api/services/llm_feedback.py` | 新增 | 用户反馈收集 |
| `api/services/document_service.py` | 新增 | 文档上传/解析/向量化 |
| `api/services/llm_skills/` (4 文件) | 新增 | Skill 基类 + 注册表 + 3 个 Skill |
| `api/routers/documents.py` | 新增 | 文档 CRUD 路由 |
| `api/routers/theme_pool.py` | 新增 | 主题池路由 + LLM 流路由 |
| `api/tasks/stock_news.py` | 新增 | 每日股票新闻 Celery 任务 |
| `api/tasks/macro_fetch.py` | 新增 | 每小时宏观数据 Celery 任务 |
| `data_analyst/fetchers/concept_board_fetcher.py` | 新增 | 概念板块多源拉取 |
| `data_analyst/fetchers/sw_industry_valuation_fetcher.py` | 新增 | 申万行业估值分位 |
| `investment_rag/ingest/parsers/docx_parser.py` | 新增 | Word 文档解析器 |
| `web/src/lib/posthog.ts` | 新增 | PostHog 配置 |
| `web/src/hooks/useTrack.ts` | 新增 | 统一埋点 hook |
| `web/src/components/PostHogProvider.tsx` | 新增 | PostHog Provider + 页面浏览追踪 |
| `web/src/components/TrackingDelegate.tsx` | 新增 | 全局点击委托 |
| `web/src/components/theme-pool/LLMCreateDialog.tsx` | 新增 | AI 创建主题弹窗 |
| `web/src/components/theme-pool/ThemeReviewDialog.tsx` | 新增 | 主题评审弹窗 |
| `web/src/hooks/useSSEFetch.ts` | 新增 | POST SSE 通用 hook |
| `web/src/app/rag/components/DocumentCard.tsx` | 新增 | 文档卡片 |
| `web/src/app/rag/components/DocumentUploadDialog.tsx` | 新增 | 文档上传弹窗 |
| `web/src/app/industry/page.tsx` | 新增 | 行业页（含估值热力图） |
| `alembic/versions/*` (5 个) | 新增 | llm_usage_logs / llm_feedback / stock_concept_map / trade_briefing / research_document |
| `tests/unit/` (10 个) | 新增 | LLM 相关模块单元测试 |
| `docs/plans/2026-04-15-llm-agent-plan.md` | 新增 | LLM Agent 设计方案 |
| `docs/plans/2026-04-15-valuation-enhancement.md` | 新增 | 估值增强设计方案 |

---

### 待完成

- [ ] PostHog 获取 Project API Key，填入 GitHub Secrets（POSTHOG_KEY / POSTHOG_HOST）
- [ ] push 触发前端重建，激活埋点
- [ ] `portfolio-doctor` skill 补充 user_id 权限校验
- [ ] `document_service.delete_document` 三步删除改软删除
- [ ] 概念板块 `concept_board_fetcher` 分页加 max_pages 保护

---

## 2026-04-15（补充 2）PostHog 服务器端部署 + 磁盘清理

### 问题排查与修复

#### 1. PostHog 镜像下载失败：磁盘满

- **根因：** `/dev/vda1` (40G 系统盘) 被 Docker build cache 占满（22GB），无空间下载 posthog/posthog (~1.5GB）
- **修复：** `docker builder prune -af` 清理全部 build cache，释放 22GB，磁盘占用从 100% 降至 40%
- **根因 2：** 今日频繁构建 `mytrader-web` 镜像（10+ 次），每次都留下悬空层
- **预防：** 服务器已有 crontab 每日凌晨 3 点自动 prune（`docker image prune -af --filter "until=24h"` + `docker builder prune -af --keep-storage=2g`），今后不会再积累

#### 2. Docker build cache 清理策略升级

- crontab 由每日 3 点清理改为**每 8 小时清理一次**（00:00 / 08:00 / 16:00）
- `--filter "until=8h"` 只清超过 8 小时的旧层，不影响近期构建
- `--keep-storage=2g` 保留 2GB build cache，加速增量构建

#### 3. PostHog 启动成功

```bash
# 磁盘清理后重新拉取镜像
docker pull posthog/posthog:latest  # ~1.5GB，约 5 分钟

# 启动主容器（PostgreSQL + Redis 已提前启动）
docker run -d \
  --name mytrader-posthog \
  --network app_mytrader-network \
  -p 127.0.0.1:8080:8000 \
  -e DATABASE_URL=postgres://posthog:posthog_secret@mytrader-posthog-db:5432/posthog \
  -e REDIS_URL=redis://mytrader-posthog-redis:6379/ \
  -e SECRET_KEY=<secret> \
  -e SITE_URL=http://123.56.3.1/analytics \
  -e DISABLE_SECURE_SSL_REDIRECT=true \
  -e IS_BEHIND_PROXY=true \
  --restart unless-stopped \
  posthog/posthog:latest

# 数据库迁移（首次）
docker exec mytrader-posthog python manage.py migrate
```

### 下一步

1. 访问 `http://123.56.3.1/analytics`，注册账号
2. Settings -> Project Settings -> Project API Key，复制 `phc_` 开头的 key
3. 在 GitHub 添加 Secret：`POSTHOG_KEY=phc_xxx`，`POSTHOG_HOST=http://123.56.3.1/analytics`
4. push 任意 `web/` 改动，触发前端镜像重建，埋点自动生效

---

## 2026-04-15 估值数据增强 M1/M2 实施

### 今日工作内容

#### 1. 理杏仁竞品调研 + 技术方案

对标 https://www.lixinger.com/ 完成产品功能调研，制定 M1-M3 估值增强方案。
产出文档：`docs/lixinger_research.md`、`docs/plans/2026-04-15-valuation-enhancement.md`

#### 2. 申万行业数据验证与修复

- `trade_stock_basic` 新增 `sw_level1` / `sw_level2` 字段（用户已完成）
- 覆盖率分析：sw_level1 73.2% → **94.5%**（5194/5497）
  - 根因：未覆盖股票的 `industry` 字段本来就是 NULL（北交所）或已有值
  - 修复：用 `industry` 字段回填 `sw_level1`，一条 UPDATE 补充 1169 只股票
  - 剩余 303 只是北交所股票（无申万行业分类，属正常）

#### 3. 宏观数据补全（macro_fetcher.py）

新增 5 个月度宏观指标写入 `macro_data` 表：

| 指标 | indicator | 数据量 |
|------|-----------|--------|
| CPI同比 | cpi_yoy | 20 条（2024.01~2025.08） |
| PPI同比 | ppi_yoy | 20 条（2024.01~2025.08） |
| M0货币同比 | m0_yoy | 27 条（2024.01~2026.03） |
| M1货币同比 | m1_yoy | 27 条（2024.01~2026.03） |
| M2货币供应同比 | m2_supply_yoy | 27 条（2024.01~2026.03） |

新增函数：`fetch_cpi_yoy`、`fetch_ppi_yoy`、`fetch_money_supply_indicators`（联合函数）
注册到 `FETCH_FUNCTIONS` 和 `fetch_all_indicators` 的 `skip_set` / 联合调用中。

#### 4. 申万行业估值分位系统

**新建表 `sw_industry_valuation`（17 字段）：**
- trade_date / sw_name / sw_level
- pe_ttm（市值加权）/ pe_ttm_eq（等权）/ pe_ttm_med（中位数）
- pb（市值加权）/ pb_med（中位数）
- pe_pct_5y / pb_pct_5y / pe_pct_10y / pb_pct_10y（历史分位）
- valuation_score（0-100 估值温度）/ valuation_label（低估/合理/高估）

**新建 `sw_industry_valuation_fetcher.py`：**
- `calc_daily_industry_valuation(date)` -- JOIN trade_stock_daily_basic + trade_stock_basic，按申万一级行业聚合 PE/PB（三口径）
- `calc_percentile(series, window)` -- 滚动历史分位（5年/10年窗口）
- `_batch_update_percentiles()` -- 一次性加载全量历史批量计算所有分位并 UPDATE
- `run_daily()` / `run_backfill()` -- 日常增量 + 历史回填

**数据质量验证（2026-04-08）：**
- 31 个行业全覆盖（含银行 PE=6.8、国防军工 PE=56.4 等合理值）
- PE 三口径均正常（市值加权 < 等权 < 中位数，符合分布特征）

**历史回填：** 2024-01-01 起回填，后台运行中

#### 5. 估值 API（M2 完成）

**`api/services/analysis_service.py` 新增 3 个函数：**
- `get_industry_valuation_temperature(trade_date)` -- 行业估值温度列表
- `get_industry_valuation_history(industry, metric, years)` -- 行业历史走势 + 分位带
- `get_stock_valuation_history(stock_code, years)` -- 个股历史 PE/PB + 分位带

**`api/routers/analysis.py` 新增 3 个端点：**
```
GET /api/analysis/valuation/temperature               # 行业估值温度（低估排前）
GET /api/analysis/valuation/industry/{name}/history   # 行业历史走势
GET /api/analysis/valuation/stock/{code}/history      # 个股历史 PE/PB
```

**`tasks/04_indicators.yaml` 新增：**
```yaml
calc_sw_industry_valuation:  # 每日 after_gate 自动运行
```

### 回填完成验证（2026-04-15）

- 总记录: **20739 条** = 669 交易日 x 31 行业，数据完整
- 有分位记录: 16895 条（81.5%，前 ~120 天无分位属正常，窗口未满）
- Bug 修复：唯一键 `(trade_date, sw_code)` 改为 `(trade_date, sw_name)` 后重新回填
- API 全部验证通过：食品饮料 score=12.1（低估）、通信 score=99.9（高估），符合市场认知
- 五粮液个股：PE分位=8.2%，PB分位=4.7%，历史极低位

### 待完成

- [ ] M3：前端行业估值热力表 + 个股估值历史走势图

产出文档：`docs/plans/2026-04-15-valuation-enhancement.md`

---

## 2026-04-14 策略模拟池系统 (SimPool) 完整实现

### 今日工作内容

#### 1. SimPool 系统设计与任务拆分

编写完整系统设计文档和任务拆分文档：

- `docs/sim_pool_design.md` -- 系统概念、5 张表 DDL、模块结构、数据流、API 设计
- `docs/sim_pool_tasks.md` -- 24 个任务，分 M1-M5 五个里程碑

**核心设计原则：**
- 无人工干预：创建后自动执行，不允许手动买卖
- 交易成本：佣金 0.03% + 滑点 0.1% + 印花税 0.1%（仅卖出）
- 整数手：持股数必须是 100 的整数倍，余额作为现金保留
- 等权分配：`weight = 1 / N`，不超过 max_positions

#### 2. 核心引擎实现 (M1)

| 模块 | 文件 | 功能 |
|------|------|------|
| 建表 | `strategist/sim_pool/schemas.py` | 5 张表 DDL + `ensure_tables()` |
| 配置 | `strategist/sim_pool/config.py` | `SimPoolConfig` dataclass |
| 池子管理 | `strategist/sim_pool/pool_manager.py` | 创建/查询/关闭池子 |
| 持仓跟踪 | `strategist/sim_pool/position_tracker.py` | T+1买入/价格更新/止盈止损/停牌处理 |
| 净值计算 | `strategist/sim_pool/nav_calculator.py` | 日净值/回撤/基准净值 |

**退出条件（按优先级）：**
1. `stop_loss`: 净收益率 <= -10%
2. `take_profit`: 净收益率 >= +20%
3. `max_hold`: 持有天数 >= 60
4. `suspended`: 连续停牌 >= 5 个交易日

#### 3. 策略适配器 (M2)

| 适配器 | 文件 | 封装模块 |
|--------|------|---------|
| 动量反转 | `strategies/momentum.py` | `doctor_tao.SignalScreener` |
| 行业轮动 | `strategies/industry.py` | `universe_scanner.ScoringEngine` |
| 微盘股 | `strategies/micro_cap.py` | `trade_stock_daily_basic` + `trade_stock_daily` |

微盘股筛选条件：流通市值 < 50 亿，60日均成交额 >= 1000 万，价格 > MA20，排除 ST。

#### 4. Celery 定时任务 (M2)

| 任务 | 时间 | 功能 |
|------|------|------|
| `fill_entry_prices` | 工作日 09:35 | T+1 填充买入价 |
| `daily_sim_pool_update` | 工作日 16:30 | 价格更新 -> 退出检查 -> 净值计算 -> 报告生成 -> 周报(周五) -> 关闭(全部退出) |

`create_sim_pool_task` 由 API 端点异步触发，不在 Beat 调度中。

#### 5. 报告生成 (M3)

`ReportGenerator` 复用 `strategist.backtest.metrics.MetricsCalculator`，生成三种报告：
- **日报**: 每日生成，包含累计收益/年化/回撤/Sharpe 等指标
- **周报**: 周五生成，统计本周一到周五的绩效
- **终报**: 池子关闭后生成，额外包含每只股贡献度排名和退出原因分布

#### 6. REST API (M3)

9 个端点，注册在 `/api/sim-pool`：

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/` | 池子列表（支持 strategy_type/status 过滤） |
| POST | `/` | 创建模拟池（异步，返回 task_id） |
| GET | `/tasks/{task_id}` | 轮询任务状态 |
| GET | `/{id}` | 池子详情 |
| GET | `/{id}/positions` | 持仓列表（支持 status 过滤） |
| GET | `/{id}/nav` | 净值序列 |
| GET | `/{id}/reports` | 报告列表 |
| GET | `/{id}/reports/{date}/{type}` | 报告详情 |
| GET | `/{id}/trades` | 交易日志 |
| POST | `/{id}/close` | 强制关闭 |

#### 7. 前端页面 (M4)

**页面：** `web/src/app/sim-pool/page.tsx`

**功能：**
- 池子列表：卡片式展示，支持策略类型/状态过滤，"创建模拟池"按钮
- 创建弹窗：策略类型选择、交易参数配置、异步任务轮询
- 池子详情 4-Tab：
  - 概览：8 个指标卡片（总收益/年化/超额收益/最大回撤/Sharpe/胜率/盈亏比/均持天数）+ SVG 净值曲线
  - 持仓：表格含退出原因中文标签和颜色，支持 open/exited/all 过滤
  - 报告：日报/周报/终报列表，点击展开 metrics JSON
  - 交易记录：买卖明细表格（价格/数量/手续费/印花税/净金额）
- 强制关闭按钮：仅非 closed 状态显示
- 侧边栏新增"模拟池"导航项

#### 8. 测试 (M5)

41 个测试全部通过（25 单元 + 16 集成）：

| 测试文件 | 数量 | 覆盖 |
|---------|------|------|
| `test_pool_manager.py` | 5 | 创建/等权/max_positions/过滤/关闭 |
| `test_position_tracker.py` | 7 | 买入成本/止损/止盈/到期/不触发/印花税/停牌 |
| `test_nav_calculator.py` | 4 | NAV=1/价格上涨/回撤计算/基准净值 |
| `test_report_generator.py` | 4 | 日报字段/终报退出分布/终报贡献度/周报区间 |
| `test_strategy_adapters.py` | 5 | 抽象类/动量DataFrame/meta序列化/行业过滤/市值过滤 |
| `test_full_lifecycle.py` | 4 | 完整生命周期/止损/止盈/到期 |
| `test_api_endpoints.py` | 12 | 列表/详情/持仓/净值/交易/关闭/报告/无效策略 |

---

### 修改的文件

| 文件 | 类型 | 说明 |
|------|------|------|
| `strategist/sim_pool/` (12 文件) | 新增 | 核心引擎 + 策略适配器 |
| `api/tasks/sim_pool_tasks.py` | 新增 | 3 个 Celery 任务 |
| `api/services/sim_pool_service.py` | 新增 | 服务层 |
| `api/routers/sim_pool.py` | 新增 | 9 个 REST 端点 |
| `api/main.py` | 修改 | 注册 sim_pool router |
| `api/tasks/__init__.py` | 修改 | 注册 sim_pool_tasks |
| `api/tasks/celery_app.py` | 修改 | 添加 2 个 Beat 调度 |
| `web/src/app/sim-pool/page.tsx` | 新增 | 前端页面 |
| `web/src/components/layout/AppShell.tsx` | 修改 | 添加导航项 |
| `tests/unit/sim_pool/` (5 文件) | 新增 | 单元测试 |
| `tests/integration/sim_pool/` (2 文件) | 新增 | 集成测试 |
| `docs/sim_pool_design.md` | 新增 | 系统设计文档 |
| `docs/sim_pool_tasks.md` | 新增 | 任务拆分文档 |

### 相关 Git 提交

```
13c3ec9 feat: implement Strategy Simulation Pool (SimPool) system
612a1b1 docs: add sim_pool system design and task breakdown
```

---

### 待解决问题

1. **线上建表**：需在 API 容器内执行 `ensure_tables(env='online')` 创建 5 张 sim_pool 相关表
2. **端到端验证**：实际创建一个动量策略模拟池，观察 T+1 买入和后续每日更新流程
3. **Celery Beat 更新**：重启 Celery worker 以加载新的 Beat 调度配置

---

*文档维护：每次开发后更新此文件，新日期追加在上方*

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
- [x] 下载财务数据（一页纸研报需要）
- [x] 更新 daily_basic 数据
- [x] 更新 RPS 数据
- [x] 更新 extended_factor 数据

---

## 2026-04-14 数据完备度页面 + 因子补算 + OOM 修复

### 今日工作内容

#### 1. 数据完备度检查页面 `/data-health`

新增数据完备度可视化页面，展示各数据维度的最新更新时间、距今天数和记录数。

**后端 (`GET /api/admin/data-health`)：**
- 查询 16 个数据维度，按分组展示（行情/因子/财务/资金/情绪/宏观/策略）
- 不暴露表名，使用友好描述
- 状态判断：正常(绿点)/偏旧(黄点)/异常(红点)
- 无需登录即可访问（方便快速检查）

**前端 (`/data-health`)：**
- 紧凑表格布局，分组标题行
- 状态圆点 + 等宽字体日期 + 距今标签
- 每2分钟自动刷新

#### 2. 数据补算

发现多个数据表严重滞后，逐一补算：

| 数据 | 补算前 | 补算后 | 方式 |
|------|--------|--------|------|
| A股每日指标 | 4月10日 (1586只) | 4月13日 (5199只) | AKShare `daily_basic_history_fetcher` |
| 基础量价因子 | 3月22日 | 4月13日 (5171只) | `basic_factor_calculator --backfill` |
| 扩展因子 | 3月23日 | 4月13日 (4707只) | `extended_factor_calculator --start` |

#### 3. 因子回填 OOM 修复

**问题：** `basic_factor_calculator.backfill_factors()` 一次性加载全量K线数据（5000只 x 3年），导致 ECS 3.6G RAM + 4G Swap OOM 崩溃。

**修复：** 改为分批模式，每批500只股票，加载该批数据 -> 计算因子 -> 保存 -> 释放内存 -> 下一批。内存峰值从 4GB+ 降至约 200MB。

同步为 `extended_factor_calculator` 添加 `--start`/`--end` 命令行参数，支持指定回填范围。

#### 4. 各数据维度使用情况梳理

| 数据 | 使用方 |
|------|--------|
| 基础量价因子 | strategist 本地回测（doctor_tao/multi_factor），API 未直接使用 |
| 扩展因子 | `analysis_service` 个股基本面分析、`theme_pool_score` 主题评分（ROE/利润增长） |
| A股每日指标 | doctor_tao/multi_factor/microcap 策略（市值过滤/PE筛选）、research_pipeline |

---

*文档维护：每次开发后更新此文件，新日期追加在上方*
