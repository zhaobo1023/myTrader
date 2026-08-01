# 技术债登记

> 目的：让技术债可见、可回顾，避免「发现过又忘掉」。myTrader 是单人维护的投研系统，
> 没有同事和 MR review 兜底，本表就是唯一的记忆载体。
> 回顾机制：每次跑完 `bash scripts/preflight.sh` 后过一遍本表；改动触碰了登记项涉及的文件就顺手清偿。
> 登记格式：现状（带实测证据）+ 影响 + 方向 + 登记日期。已清偿条目移到底部，附日期。
>
> **分级**：[CRITICAL] 已确认影响数据正确性或链路可用 · [HIGH] 会导致静默失败 · [MED] 工程质量 · [LOW] 风格存量

---

## 待清偿

### 4. [HIGH] 其余 F821 未定义名（4 处）

- **现状**（2026-08-01 清偿 #1-#3 后复查剩余）：`ruff check . --select F821` 还有 6 处：
  - `api/routers/agent.py:177` `MCPServerConfig`（在字符串类型标注里，运行时不报错，但类型检查无效）
  - `data_analyst/fetchers/data_fetch_manager.py:138` `DATA_START`
  - `data_analyst/fetchers/macro_fetcher.py:1172` `cn_key`、`:1173` `us_key`
  - `data_analyst/research_pipeline/batch_runner.py:227` `ReportData`
  - `strategist/doctor_tao/run_optimized_pipeline.py:130` `_save_new_signals`
  - `tests/integration/conftest.py:115` `User`、`:132` `InviteCode`
- **影响**：会在执行到该分支时抛 NameError。macro_fetcher 两处在同一段落，疑似重构时漏改。
- **方向**：逐个确认分支是否可达；可达的补定义，不可达的删除。agent.py 那处补 import 或改用 TYPE_CHECKING。
- 登记：2026-08-01

### 5. [HIGH] 测试收集有 2 个 error，测试绿不可判定

- **现状**：`python -m pytest tests/ --collect-only -q` 实测 1150 collected / **2 errors**：
  - `tests/test_risk_manager.py`：`ImportError: cannot import name 'RiskEngine' from 'risk_manager'`
  - `tests/test_scanner.py`：`ModuleNotFoundError: No module named 'risk_manager.scanner'`
  收集阶段中断（Interrupted），意味着 CI 无法把 collect-only 当门禁用。
- **影响**：这两个测试对应的模块要么被删了要么被改名了，测试没跟着更新——
  等于 risk_manager 这块**当前没有任何测试覆盖**，而这是涉资金逻辑的模块。
- **方向**：确认 `RiskEngine` / `risk_manager.scanner` 是重命名还是已废弃。
  重命名则更新测试 import；已废弃则删除对应测试文件并补新模块的测试。
  修完把 `pytest tests/ --collect-only -q` 零错误加进 preflight.sh 作为门禁。
- 登记：2026-08-01

### 6. [MED] pytest 自定义 marker 未注册

- **现状**：`tests/unit/sentiment/` 下多个文件用 `@pytest.mark.integration`，
  但没在 pytest 配置里注册，每次跑测试刷一堆 `PytestUnknownMarkWarning`。
- **影响**：噪声掩盖真实警告；且无法用 `-m "not integration"` 可靠地隔离出不依赖外部服务的子集。
- **方向**：建 `pytest.ini` 或在现有配置里加 `markers = integration: 依赖外部服务的集成测试`。
  注册后即可用 `-m "not integration"` 划出 hermetic 子集做 CI 门禁（参考 flow 项目同类做法）。
- 登记：2026-08-01

### 7. [MED] strategist/doctor_tao/test_indicators.py 语法错误

- **现状**：`:9` `'(' was never closed`，文件无法解析。
- **影响**：该测试从未被执行过（收集阶段就跳过了，因为不在 tests/ 目录下所以没进 collect 统计）。
- **方向**：确认这个文件是不是遗留的临时脚本。是则删除，不是则修好并移到 `tests/` 下。
- 登记：2026-08-01

### 8. [LOW] ruff 存量 1310 条（棘轮管控）

- **现状**：`ruff check . --statistics` 实测 1310 errors，822 可自动修。分布：
  ```
  591 F401 unused-import          269 F541 f-string 无占位符
  242 E402 import 不在文件顶部     92 F841 unused-variable
   38 E701 一行多语句              19 invalid-syntax（见 #1/#2/#7）
   16 E712 == True 比较            11 E741 歧义变量名
   11 F821 undefined-name（见 #3/#4）  9 E722 bare-except
  ```
- **影响**：`ruff check .` 永远红，无法做门禁；真问题（F821、invalid-syntax）淹没在风格噪声里。
- **方向**：**只减不增，棘轮式管控**。preflight.sh 已只查本次改动，保持该口径。
  优先清 F821 / invalid-syntax / E722（真问题），F401/F541 可批量 `--fix` 但要分批提交避免大 diff。
  **注意**：E402 有 242 条，其中一部分可能是 sys.path 操作后再 import 的合理写法，不可无脑修。
- 登记：2026-08-01

### 9. [MED] 9 处 bare-except 吞异常

- **现状**：`ruff check . --select E722` 报 9 处裸 `except:`。另有大量 `except Exception` + print/warning
  的模式（#1 #3 均因此把致命错误降级成一行日志）。
- **影响**：这是 myTrader 最危险的模式——**投研系统里静默失败比崩溃更糟**，
  因为你会拿到一个「看起来正常」的空结果去做决策。#3 的 save_factors 就是活例子。
- **方向**：结合全局规范「不要为了让代码跑起来注释掉报错或加绕过标记，找根本原因」。
  逐个评估：数据写入/因子计算链路上的 except 必须改为抛出或 logger.error + 明确返回失败标志。
- 登记：2026-08-01

---

## 已清偿

### [CRITICAL] alert_service.py 语法错误，报警链路整体失效

- **原现状**：`data_analyst/services/alert_service.py` 无法被 Python 解析
  （`SyntaxError: closing parenthesis ']' does not match '{' on line 119`，ruff 报 15 处 invalid-syntax）。
- **原影响**：`run_monitor.py:527` 的 import 包在 `try/except Exception` 里，SyntaxError 被吞成
  一行 `logger.warning`，**SVD 突变警报静默失效**；`scheduler_service.py:124` 裸 import 则会硬崩，
  数据完整性检查 + 因子计算触发链路直接断掉。
- **实际修复**（共 5 处缺陷，比登记时发现的多）：
  1. `send_data_alert` 签名有游离的 `str,` 参数（`data: Dict, str,`）→ 删除
  2. `send_data_alert` 的 elements 列表首个 dict 少两层闭合括号 → 补全
  3. `send_success_alert` 的 content 列表结构错乱：首个 dict 未闭合、第二个 dict 游离在列表外 → 重组为合法的 3 元素列表
  4. `send_factor_calc_trigger` 里字符串 `"数据检查通过，                f"数据完整性..."` 拼接损坏 → 拆成两个参数
  5. **额外发现**：`import sys` 缺失但 line 16 就在用 `sys.path.insert`；`json`/`Optional` 未使用 → 一并修正
  6. **额外发现**：line 144/157 含 emoji（叉号 / 警告三角），违反项目硬规则 → 替换为 `[BAD]`/`[WARN]`
- **验证**：`AlertService` 可 import 并实例化；5 个方法（send_text / send_data_alert /
  send_success_alert / send_factor_calc_trigger 的 True/False 两分支）全部实测返回 True；
  复现 `run_monitor.py:527` 的报警链路确认可用。
- 登记 2026-08-01 · 清偿 2026-08-01

### [CRITICAL] tushare_fetcher.py 语法错误，日线拉取入口不可用

- **原现状**：`:143-145` 的 `records.append((...))` 里 `float(row['high'])` 和 `float(row['low'])`
  两行末尾漏逗号，文件无法解析。CLAUDE.md 把该文件列为日线拉取标准入口，实际根本跑不起来。
- **实际修复**（共 3 处缺陷）：
  1. 补 143、144 行末尾逗号。核对 `INSERT_SQL` 为 9 字段 9 占位符，tuple 顺序
     （open/high/low/close/vol/amount/turnover）与 SQL 列序一致 —— 漏逗号会让相邻两值被
     条件表达式静默吞并，属于 CLAUDE.md「SQL 占位符数量必须与字段数严格一致」的隐患
  2. **额外发现**：`from config.settings import settings` 但 `config/settings.py` 根本没有
     `settings` 对象（只有模块级常量）→ 改为 `from config.settings import TUSHARE_TOKEN`，
     3 处 `settings.TUSHARE_TOKEN` 同步改。参照 `daily_basic_fetcher.py:30` 的既有正确写法
  3. **额外发现**：TUSHARE_TOKEN 的未配置检查被错误缩进在 `except ImportError` 块内，
     只在 tushare 未安装时才执行 → 提到模块级
  4. `pro = get_pro()` 的 F841 未使用变量 → 改为 `get_pro()`（内部 `ts.set_token()` 是必需副作用，加注释说明）
- **验证**：模块可 import，`TUSHARE_TOKEN` 已配置、`HAS_TUSHARE=True`；ruff 该文件全绿。
- **未做**：没有实际发起 Tushare 网络请求拉数入库（会消耗 API 额度且写生产表），
  建议主人自行跑一次 `python data_analyst/fetchers/tushare_fetcher.py` 确认端到端。
- 登记 2026-08-01 · 清偿 2026-08-01

### [CRITICAL] save_factors() 引用未定义的 cursor

- **原现状**：`factor_storage.py:119/125` 使用 `cursor` 但函数体内从未定义
  （只有 `conn = get_connection()`，缺 `cursor = conn.cursor()`）。
- **原影响**：必抛 NameError，且被 line 121 的 `except Exception + print` 吞掉 →
  循环跑完、一条没写、返回 `success_count=0` 且不报错。
- **实际修复**：
  1. 补 `cursor = conn.cursor()`（对齐同文件 `batch_save_factors` 的正确写法）
  2. 加静默失败防护：整批写入失败（`success_count == 0` 且有失败记录）时抛 `RuntimeError`，
     不再返回 0 让调用方当成正常结果 —— 对应债务 #9 的模式
- **原「待核实」已澄清**：`macro_factor_calculator.py:333` 调的 `save_factors(factor_code, df)`
  是该文件**自己定义的同名函数**（`:295`），与 `factor_storage.save_factors` 无关，不存在跨模块误调用。
  `factor_storage` 的唯一 importer 是 `factor_calculator.py:28`，只导入了 `batch_save_factors`，
  故 `save_factors` 当前**无任何调用方**（保留并修复，未删除）。
- **验证**：ruff 该文件全绿；F821 `cursor` 已消失。
- **未做**：未实际写库验证（需连生产 MySQL）。因该函数当前无调用方，风险为零。
- 登记 2026-08-01 · 清偿 2026-08-01

### [HIGH] scheduler_service.init_scheduler() 缺 AlertService import

- **现状**：清偿 #1 后复查 F821 时发现，`data_analyst/services/scheduler_service.py:214`
  的 `init_scheduler()` 直接用 `AlertService()` 但未 import（同文件
  `check_data_and_trigger_factor():124` 有函数内局部 import，该函数没有）。
- **影响**：`init_scheduler()` 一调用即 NameError，定时任务无法初始化。与 #1 同源。
- **修复**：在 `init_scheduler()` 内加局部 import，与同文件既有写法保持一致。
- **验证**：模块可 import，`init_scheduler` 可解析；ruff 该文件全绿。
- 登记 2026-08-01 · 清偿 2026-08-01
