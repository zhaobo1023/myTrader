# 因子与策略登记表

> **本文件分两层，来源不同、维护方式不同，不要合并**（依据全局规范「脚本做结构，人做语义」）：
>
> - **§1 结构层（generated）**：因子在哪个文件算、写哪张表、被哪个调度任务调用、依赖什么数据。
>   这些脚本能可靠抽取，代码改了就要重新抽，**不要手工编辑**。
> - **§2 语义层（manual）**：这个因子**为什么可能有效**、**什么条件下失效**、容量上限、与其他因子的相关性。
>   脚本猜不出来，只能人写。**空着比编造好**——没想清楚就写「未评估」，不要填看起来合理的话。
>
> 建这张表的理由：myTrader 是单人维护的投研系统，没有同事会替你记住「这个因子的
> min_periods 当时是拍脑袋定的」「这个策略 2024 年就失效过一次」。
>
> **红线**：§2 里的任何结论必须有数据或来源支撑（全局规范「投研分析结论必须有数据或来源支撑」）。
> 没做过 IC 检验就不要写「有效」，写「未验证」。

---

## §1 结构层（generated · 最后更新 2026-08-01）

### 1.1 因子计算模块 → 输出表

| 模块 | 入口函数 | 输出表 | 调度任务 id |
|------|---------|--------|------------|
| `data_analyst/factors/basic_factor_calculator.py` | `calculate_and_save_factors` | `trade_stock_basic_factor` | `calc_basic_factor` |
| `data_analyst/factors/extended_factor_calculator.py` | `main` | `trade_stock_extended_factor` | `calc_extended_factor` |
| `data_analyst/factors/valuation_factor_calculator.py` | `main` | `trade_stock_valuation_factor` | `calc_valuation_factor` |
| `data_analyst/factors/quality_factor_calculator.py` | `main` | `trade_stock_quality_factor` | `calc_quality_factor` |
| `data_analyst/factors/factor_calculator.py` | `calculate_factors_for_date` | `trade_stock_factor` | `calc_technical_factor` |
| `data_analyst/factors/hardtech_factor_calculator.py` | `main` | （待补） | `calc_hardtech_factor` |
| `data_analyst/factors/macro_factor_calculator.py` | - | `macro_factors` | 见 `tasks/02_macro.yaml` |
| `data_analyst/factors/factor_validator.py` | - | `trade_factor_validation` | - |

### 1.2 调度依赖（`tasks/03_factors_basic.yaml`）

```
_gate_daily_price  (17:45, 等日线数据就绪, timeout 60min)
  ├── calc_basic_factor          [alert_on_failure]
  │     └── calc_extended_factor
  │           └── calc_hardtech_factor  (还依赖 calc_basic_factor)
  ├── calc_valuation_factor
  ├── calc_quality_factor
  └── calc_technical_factor
```

### 1.3 因子字段清单（从代码抽取，可能含非因子字段）

- **basic**：`mom_20` `mom_60` `reversal_5` `volatility_20` `turnover_rate` `vol_ratio` `price_vol_diverge`
- **extended**：`mom_5` `mom_10` `reversal_1` `amihud_illiquidity` `high_low_ratio` `roe_ttm`
  `revenue_growth` `net_profit_growth` `gross_margin`
- **quality**：`roe` `roa` `debt_ratio` `current_ratio` `cash_flow_ratio` `accrual` `gross_margin`
- **technical**（`trade_stock_factor`）：`momentum_20d` `momentum_60d` `volatility` `rsi_14`
  `adx_14` `turnover_ratio` `price_position` `macd_signal` `close`

> **[WARN] 结构层发现的问题**（已登记到 `docs/tech-debt.md`）：
> - `factor_storage.save_factors()` 引用未定义的 `cursor`，调用必失败且被 except 吞掉（债务 #3）
> - `gross_margin` 同时出现在 extended 和 quality 两张表，口径是否一致未核实
> - `hardtech_factor_calculator` 的输出表未从代码中抽到，需人工确认

---

## §2 语义层（manual · 需人工填写）

> **当前状态：全部未填。** 这是诚实的起点——下面每一条都需要你基于实测数据填写，
> 不填也比编造强。建议按「实际在用的策略」优先补，不必一次填满。

### 2.1 模板（新增因子/策略时复制这段）

```markdown
### <因子或策略名>

- **赚钱理由**：为什么这个信号会有超额收益？（风险补偿 / 定价错误 / 结构性摩擦 / 未知）
  必须写清是哪一类。如果答案是「回测跑出来好看」，那就写「未知 — 仅回测支持」，
  这本身是重要信息。
- **失效触发条件**：满足什么条件时我认为它死了？**事前写，不是事后补。**
  例：拥挤度指标超过 X / 连续 N 个月 IC 为负 / 某项制度变更落地。
  （对应全局规范「显式宣告不做 + 触发条件」）
- **实证依据**：IC 均值 / IR / 分组单调性 / 检验区间。没做过就写「未验证」。
- **容量上限**：多大资金规模下超额开始衰减？依据是什么？
- **与现有因子相关性**：跟已有因子的相关系数。>0.8 说明不是新 alpha，是老 alpha 的变体。
- **已知失效期**：历史上哪段时间失效过？原因？
- 登记日期 / 最后复核日期
```

### 2.2 待填清单

以下因子已在跑但语义层空白，按重要性排序补：

| 因子/策略 | 赚钱理由 | 失效触发条件 | 实证依据 | 状态 |
|-----------|---------|-------------|---------|------|
| `mom_20` / `mom_60` 动量 | 未填 | 未填 | 未验证 | 待填 |
| `reversal_1` / `reversal_5` 反转 | 未填 | 未填 | 未验证 | 待填 |
| `amihud_illiquidity` 流动性 | 未填 | 未填 | 未验证 | 待填 |
| `roe_ttm` / `roa` 质量 | 未填 | 未填 | 未验证 | 待填 |
| `volatility_20` 波动 | 未填 | 未填 | 未验证 | 待填 |
| XGBoost 截面预测策略 | 未填 | 未填 | 见 `docs/claude/xgboost_strategy.md` | 待填 |
| SVD 市场状态监控 | 未填 | 未填 | 见 `docs/claude/svd_monitor.md` | 待填 |

### 2.3 通用失效触发条件（所有截面选股因子适用）

这几条是 A 股结构性风险，与具体因子无关，任何截面策略都该盯：

- **退市/面值风险**：2024 年新「国九条」后，面值退市（连续 20 日 <1 元）与市值退市（<3 亿）
  同时生效。**票池必须显式剔除**，否则回测里的「便宜票」在实盘会退市归零。
- **拥挤度**：小盘成交占比是常用观测量。注意——拥挤度**应接到容量上限和仓位帽**上，
  不要接到「清仓信号」上；等拥挤度报警时流动性已在消失，撤不掉，这正是踩踏的定义。
- **风格切换**：历史上量化策略的大幅回撤多由大小盘风格切换引发。
  单一风格暴露 = 把 beta 当 alpha 卖，2024 年 2 月已验证过一次。

---

## 维护约定

- **改因子代码后**：重新核对 §1，确保表名/任务 id/字段清单跟代码一致
- **新增因子**：§1 加行 + §2 复制模板填写，**两层都填才算完成**
- **§2 的结论**：必须有数据或来源支撑；没验证就写「未验证」，不要写看起来合理的话
- **淘汰因子前问一句**：是因为它收益变差了，还是因为搞清楚了它为什么赚钱、并确认那个理由已不成立？
  前者是看后视镜开车，后者才是研究。
