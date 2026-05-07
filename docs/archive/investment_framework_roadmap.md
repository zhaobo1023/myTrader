# myTrader 投资框架建设路线图

> 基于唐君框架的差异分析与渐进式搭建方案
> 创建日期：2026-04-23

---

## 一、现状分析

### 1.1 myTrader 现有能力

| 模块 | 位置 | 功能 |
|------|------|------|
| **数据采集** | `data_analyst/fetchers/` | QMT/Tushare/AKShare/yfinance 多数据源 |
| **宏观因子** | `data_analyst/factors/macro_factor_calculator.py` | 油价、金价、VIX、北向资金动量 |
| **牛熊判断** | `data_analyst/bull_bear_monitor/` | 债券+汇率+股息率三因子综合判断 |
| **市场状态** | `data_analyst/market_monitor/` | SVD多尺度状态分类（齐涨齐跌/板块分化/个股行情） |
| **组合配置** | `strategist/portfolio_allocator/` | 权重引擎、信号收集、持仓调和 |
| **任务调度** | `scheduler/` + `tasks/` | YAML DAG 定义，每日自动执行 |
| **技术指标** | `data_analyst/indicators/` | MA/MACD/RSI/KDJ/BOLL/ATR |
| **因子计算** | `data_analyst/factors/` | 基础因子、估值因子、质量因子 |

### 1.2 唐君框架 vs myTrader 差距分析

| 唐君框架模块 | myTrader 现状 | 差距评估 | 优先级 |
|-------------|--------------|----------|--------|
| **货币-信用状态判断** | bull_bear_monitor（债券+汇率+股息率） | 缺少信用扩张核心指标（社融、房贷、企业信贷） | **P0** |
| **宏观指标体系** | macro_factor_calculator（4个因子） | 缺少M2、社融、利率曲线等货币政策指标 | **P0** |
| **预期差框架** | 无 | 需新建：行业价格监控 + 一致预期 + 拥挤度 | **P1** |
| **风险预算** | portfolio_allocator（基础版） | 需增强：波动率/相关性计算、边际风险贡献 | **P1** |
| **资金面监控** | north_flow（北向资金） | 缺少融资余额、公募发行、ETF份额 | **P2** |
| **市场状态分类** | regime_classifier（SVD） | 已有，可复用 | 已完成 |

---

## 二、渐进式搭建路径

### Phase 1: 货币-信用状态机（核心引擎）

**目标**：实现唐君框架的核心——货币信用四象限状态判断

**新建模块**：`data_analyst/macro_regime/`

```
data_analyst/macro_regime/
├── __init__.py
├── config.py           # 状态定义、阈值配置
├── data_loader.py      # 加载货币/信用指标
├── state_machine.py    # 四象限状态判断
├── storage.py          # 存储状态历史
└── run_regime.py       # CLI入口
```

#### 1.1 需要的数据源

| 指标 | 数据源 | 频率 | 说明 |
|------|--------|------|------|
| M2同比 | AKShare/Tushare | 月度 | 货币端 |
| 社融同比 | AKShare | 月度 | 信用端核心 |
| 10年期国债收益率 | 已有 | 日度 | 货币端 |
| 居民房贷余额 | 央行/Wind | 月度 | 信用端-居民 |
| 企业中长期贷款 | 央行/Wind | 月度 | 信用端-企业 |
| 政府债务净增 | 财政部/Wind | 月度 | 信用端-政府 |

#### 1.2 状态定义

```python
class MonetaryCreditState(Enum):
    LOOSE_WEAK = "宽货币+弱信用"    # 利好：债券、黄金、题材
    LOOSE_STRONG = "宽货币+强信用"  # 利好：商品、顺周期、蓝筹
    TIGHT_STRONG = "紧货币+强信用"  # 类滞胀，持有现金
    TIGHT_WEAK = "紧货币+弱信用"    # 衰退，债券最优
```

#### 1.3 判断逻辑

```python
def judge_state(monetary_score: float, credit_score: float) -> MonetaryCreditState:
    """
    monetary_score: 货币宽松程度 (-1 to 1, 正数为宽松)
    credit_score: 信用扩张程度 (-1 to 1, 正数为扩张)
    """
    is_loose = monetary_score > 0
    is_expanding = credit_score > 0
    
    if is_loose and not is_expanding:
        return MonetaryCreditState.LOOSE_WEAK
    elif is_loose and is_expanding:
        return MonetaryCreditState.LOOSE_STRONG
    elif not is_loose and is_expanding:
        return MonetaryCreditState.TIGHT_STRONG
    else:
        return MonetaryCreditState.TIGHT_WEAK
```

#### 1.4 输出

- 每日/每周一个状态标签
- 状态置信度（基于指标一致性）
- 状态变化预警

#### 1.5 验收标准

- [ ] 数据源接入完成
- [ ] 状态判断逻辑实现
- [ ] 历史回测验证（2015-2025）
- [ ] 与 bull_bear_monitor 整合
- [ ] 任务调度集成（tasks/02_macro.yaml）

---

### Phase 2: 预期差捕捉系统（战术层）

**目标**：实现中观层面的预期差框架

**新建模块**：`data_analyst/expectation_gap/`

```
data_analyst/expectation_gap/
├── __init__.py
├── config.py
├── price_monitor.py      # 行业主营产品价格监控
├── consensus_tracker.py  # 一致预期跟踪（可选）
├── crowding_calc.py      # 拥挤度计算
├── gap_scorer.py         # 预期差评分
└── run_scanner.py        # CLI入口
```

#### 2.1 核心逻辑

```
预期差得分 = 基本面信号（价格变化） - 市场预期（拥挤度）
```

#### 2.2 基本面信号

| 行业 | 监控价格 | 数据源 |
|------|----------|--------|
| 电解铝 | 铝价、煤炭价、价差 | AKShare |
| 钢铁 | 螺纹钢、铁矿石、价差 | AKShare |
| 化工 | 主要化工品价格 | AKShare |
| 养殖 | 猪价、鸡价 | AKShare |
| ... | ... | ... |

#### 2.3 拥挤度指标

| 指标 | 计算方法 | 说明 |
|------|----------|------|
| 成交额占比 | 行业成交额 / 全市场成交额 | 历史分位数 |
| 融资余额占比 | 行业融资余额 / 全市场融资余额 | 历史分位数 |
| 换手率 | 行业平均换手率 | 历史分位数 |

#### 2.4 输出

- 行业预期差排序表
- 正向预期差（基本面改善 + 低拥挤）行业列表
- 负向预期差（基本面走弱 + 高拥挤）行业列表

#### 2.5 验收标准

- [ ] 行业价格数据采集
- [ ] 拥挤度计算实现
- [ ] 预期差评分逻辑
- [ ] 历史回测验证
- [ ] 与 sw_rotation 模块整合

---

### Phase 3: 增强风险预算

**目标**：在现有 portfolio_allocator 基础上增加风险预算能力

**增强模块**：`strategist/portfolio_allocator/`

#### 3.1 新增功能

| 功能 | 说明 |
|------|------|
| 波动率计算 | 历史波动率 + 修正系数（近期涨幅大则上浮） |
| 相关性矩阵 | 动态窗口 + 宏观环境修正 |
| 边际风险贡献 | 每类资产对组合波动的边际贡献 |
| 最大回撤约束 | 目标回撤5%，常规3% |

#### 3.2 风险预算公式

```python
def calc_risk_budget(weights: np.array, cov_matrix: np.array) -> np.array:
    """
    计算每类资产的风险贡献
    
    风险贡献 = w_i * (Σw)_i / σ_p
    其中 σ_p = sqrt(w' Σ w)
    """
    portfolio_vol = np.sqrt(weights @ cov_matrix @ weights)
    marginal_contrib = cov_matrix @ weights
    risk_contrib = weights * marginal_contrib / portfolio_vol
    return risk_contrib
```

#### 3.3 验收标准

- [ ] 波动率计算模块
- [ ] 相关性矩阵计算
- [ ] 风险预算优化器
- [ ] 回撤约束实现
- [ ] 与现有 weight_engine 整合

---

### Phase 4: 配置建议生成

**目标**：整合前三个模块，生成配置建议

**新建模块**：`strategist/allocation_advisor/`

```
strategist/allocation_advisor/
├── __init__.py
├── config.py
├── strategic_advisor.py   # 战略配置建议
├── tactical_advisor.py    # 战术偏离建议
├── risk_advisor.py        # 风险预算建议
├── report_generator.py    # 报告生成
└── run_advisor.py         # CLI入口
```

#### 4.1 输出内容

| 类型 | 内容 |
|------|------|
| 战略配置 | 股/债/商品/黄金比例建议 |
| 战术偏离 | 行业/风格超配/低配建议 |
| 风险预算 | 各资产风险贡献分配 |
| 置信度 | 各建议的置信度评估 |

#### 4.2 验收标准

- [ ] 战略配置建议生成
- [ ] 战术偏离建议生成
- [ ] 风险预算分配
- [ ] 报告输出（Markdown/HTML）
- [ ] Web API 集成

---

## 三、数据源规划

### 3.1 现有数据源

| 数据源 | 用途 | 状态 |
|--------|------|------|
| QMT | A股日K、分钟K | 已接入 |
| Tushare | A股基础数据、财务数据 | 已接入 |
| AKShare | 宏观数据、商品价格 | 已接入 |
| yfinance | 全球资产、指数 | 已接入（本机抓取） |

### 3.2 需要新增的数据（已验证可用性）

| 数据 | 数据源 | 接口 | 状态 | 说明 |
|------|--------|------|------|------|
| M2同比 | AKShare | `macro_china_money_supply` | **可用** | 货币端，月度，含同比环比 |
| M2年率 | AKShare | `macro_china_m2_yearly` | **可用** | 货币端，含预测值 |
| 新增人民币贷款 | AKShare | `macro_rmb_loan` | **可用** | 信用端核心，月度 |
| 新增信贷 | AKShare | `macro_china_new_financial_credit` | **可用** | 信用端，月度 |
| 社融增量 | AKShare | `macro_china_shrzgm` | **不可用** | SSL错误，需替代方案 |
| 居民房贷余额 | 无 | - | **需替代** | 可用新增贷款中居民部分代替 |
| 国债收益率 | AKShare | `bond_china_yield` | **可用** | 货币端，日度 |
| LPR利率 | AKShare | `macro_china_lpr` | **可用** | 货币端，月度 |
| 融资余额 | AKShare | `macro_china_market_margin_sh/sz` | **可用** | 拥挤度，日度 |
| 行业产品价格 | AKShare | 商品频道 | 待验证 | 预期差 |
| ETF份额 | Tushare | `fund_etf_daily` | 待验证 | 拥挤度 |

**注意**：没有 Wind 数据源，社融数据接口 SSL 错误，需要寻找替代方案或手动录入。

---

## 四、技术实现要点

### 4.1 架构原则

1. **模块化**：每个功能独立模块，可单独测试
2. **可配置**：阈值、权重等参数化，支持调优
3. **可回测**：所有策略支持历史回测验证
4. **可监控**：关键指标入库，支持可视化

### 4.2 代码规范

遵循 `CLAUDE.md` 中的规范：
- 输出统一到 `output/<module_name>/`
- 使用 `config.db` 的双环境连接
- 任务通过 `tasks/*.yaml` 定义

### 4.3 测试策略

| 阶段 | 测试内容 |
|------|----------|
| 单元测试 | 各计算函数正确性 |
| 集成测试 | 模块间数据流 |
| 回测验证 | 历史表现评估 |
| 实盘验证 | 小仓位实盘跟踪 |

---

## 五、里程碑计划

| 阶段 | 目标 | 预计周期 | 交付物 |
|------|------|----------|--------|
| Phase 1 | 货币-信用状态机 | 2周 | macro_regime 模块 |
| Phase 2 | 预期差捕捉 | 3周 | expectation_gap 模块 |
| Phase 3 | 风险预算增强 | 2周 | portfolio_allocator 增强 |
| Phase 4 | 配置建议生成 | 2周 | allocation_advisor 模块 |
| 整合 | 全流程打通 | 1周 | 完整工作流 |

**总计**：约10周

---

## 六、风险与挑战

| 风险 | 影响 | 应对 |
|------|------|------|
| 数据源不稳定 | 指标计算中断 | 多数据源备份、缓存机制 |
| 信用数据难获取 | 状态判断不准 | 定性判断补充、代理指标 |
| 回测过拟合 | 实盘表现差 | 样本外验证、参数稳健性测试 |
| 宏观样本少 | 统计意义弱 | 逻辑优先、概率思维 |

---

## 七、下一步行动

### 立即可做

1. **数据源调研**：确认 M2、社融、房贷数据的获取方式
2. **创建模块骨架**：`data_analyst/macro_regime/` 目录结构
3. **设计数据库表**：`macro_regime_state` 表结构

### 已确认

1. **没有 Wind 数据源**，使用 AKShare + Tushare + 手动录入
2. 预期差框架的行业范围：待定（建议从重点行业开始）
3. **目标回撤：5%**（常规不超过3%）

---

## 八、参考文档

- [唐君投资框架总结](./tangjun_investment_framework.md)
- [CLAUDE.md](../CLAUDE.md) - 项目规范
- [bull_bear_monitor](./claude/bull_bear_monitor.md) - 现有牛熊监控
- [market_dashboard_design](./market_dashboard_design.md) - 市场仪表盘设计

---

*文档版本：v1.0*
*最后更新：2026-04-23*
