# XGBoost 截面策略 — 回测修复技术方案

**目标**：消除 Look-ahead Bias，使回测结果可信  
**预计工作量**：4~6 小时  
**修复后预期**：IC 从 0.20 回落至 0.03~0.06，超额收益从 +1000% 回落至合理区间

---

## 核心问题诊断

当前回测存在两处数据泄露，共同导致结果虚高：

```
泄露点 1：future_ret 标签污染截面预处理
  ──► 标准化时用了未来价格计算出的统计量

泄露点 2：信号当天 = 收益当天
  ──► T日生成信号，T日的 actual 收益被直接纳入计算
      正确做法：T日生成信号 → T+1日开盘价买入 → T+6日开盘价卖出
```

---

## 任务清单

### Task 1 — 修复 `data_loader.py`：标签计算与特征严格分离

**问题**：`future_ret` 在全量数据上计算后，`preprocess_cross_section` 可能将其作为统计量来源影响特征标准化；另外 `future_ret` 本身是否被 shift 正确也需要验证。

**修改位置**：`data_loader.py` → `load_and_compute_factors()`

**修改前（伪代码，需对照实际文件）**：
```python
def load_and_compute_factors(self):
    df = load_from_db(...)           # 全量数据
    df = feature_engine.calc_features(df)  # 计算因子
    
    # ❌ 问题：future_ret 和特征在同一个 df 里，
    #    后续预处理可能混用统计量
    df['future_ret'] = df.groupby('stock_code')['close'].transform(
        lambda x: x.shift(-predict_horizon) / x - 1
    )
    
    panel = preprocess_cross_section(df)  # ❌ 此时 df 含 future_ret
    return panel, feature_cols
```

**修改后**：
```python
def load_and_compute_factors(self):
    df = load_from_db(...)
    df = feature_engine.calc_features(df)   # Step1: 只计算技术因子
    
    # Step2: 先做截面预处理（此时 df 里没有 future_ret）
    feature_cols = [c for c in df.columns if c not in
                    ['trade_date', 'stock_code', 'open', 'high', 'low',
                     'close', 'volume', 'amount']]
    panel = self.preprocessor.preprocess_panel(df, feature_cols)
    
    # Step3: 计算标签（在预处理完成后单独挂载，不参与标准化）
    panel = panel.sort_values(['stock_code', 'trade_date'])
    panel['future_ret'] = panel.groupby('stock_code')['close'].transform(
        lambda x: x.shift(-self.config.predict_horizon) / x - 1
    )
    # 注意：最后 predict_horizon 天没有 future_ret，是 NaN，属正常
    
    return panel, feature_cols
```

**验证方法**：
```python
# 检查：future_ret 的日期对应关系
sample = panel[panel['stock_code'] == '600519.SH'][
    ['trade_date', 'close', 'future_ret']
].head(10)
print(sample)
# 确认：2023-01-03 的 future_ret = close[2023-01-10] / close[2023-01-03] - 1
```

---

### Task 2 — 修复 `preprocessor.py`：截面标准化只用当日数据

**问题**：如果 `preprocess_panel` 先把整个 panel（含未来日期）拼在一起再做 MAD，就会用到未来日期的数值来计算当前截面的统计量。

**修改位置**：`preprocessor.py` → `preprocess_panel()` 或 `preprocess_cross_section()`

**正确实现**：
```python
def preprocess_panel(self, df: pd.DataFrame, feature_cols: list) -> pd.DataFrame:
    """
    逐日截面标准化：每一天只用当天的截面数据计算统计量
    绝对不能用全局统计量
    """
    result_parts = []
    
    for date, group in df.groupby('trade_date'):
        group = group.copy()
        for col in feature_cols:
            # 只用当天截面的数据做 MAD 去极值 + Z-Score
            group[col] = self.mad_zscore(group[col])
        result_parts.append(group)
    
    return pd.concat(result_parts, ignore_index=True)

def mad_zscore(self, series: pd.Series) -> pd.Series:
    """MAD 去极值 + Z-Score（截面内计算）"""
    median = series.median()
    mad = (series - median).abs().median()
    # 避免 MAD=0 的边界情况
    if mad < 1e-8:
        return series - median
    upper = median + 5 * 1.4826 * mad
    lower = median - 5 * 1.4826 * mad
    series = series.clip(lower=lower, upper=upper)
    mean, std = series.mean(), series.std()
    if std < 1e-8:
        return series - mean
    return (series - mean) / std
```

**性能提示**：如果股票数量很多，逐日 groupby 可能慢，可以用向量化：
```python
# 更快的向量化写法（等价）
def preprocess_panel_fast(self, df, feature_cols):
    df = df.copy()
    for col in feature_cols:
        df[col] = df.groupby('trade_date')[col].transform(self.mad_zscore)
    return df
```

---

### Task 3 — 修复 `model_trainer.py`：训练集绝对不包含预测日

**问题**：训练窗口的边界如果切错一天，就会包含 pred_date 当天的数据。

**修改位置**：`model_trainer.py` → `rolling_train_predict()`

**修改后**：
```python
def rolling_train_predict(self, panel, feature_cols, dates):
    results = []
    
    for pred_idx in range(self.config.train_window, len(dates), self.config.roll_step):
        pred_date = dates[pred_idx]
        
        # ✅ 训练数据：[pred_idx - train_window, pred_idx - 1]，严格不含 pred_date
        train_dates = dates[pred_idx - self.config.train_window : pred_idx]
        train_data = panel[panel['trade_date'].isin(train_dates)].copy()
        
        # ✅ 去掉训练集中 future_ret 为 NaN 的行（最后几天没有标签）
        train_data = train_data.dropna(subset=['future_ret'])
        
        if len(train_data) < 100:  # 样本过少跳过
            continue
        
        X_train = train_data[feature_cols].fillna(0)
        y_train = train_data['future_ret']
        
        # ✅ 预测数据：只用 pred_date 当天的截面
        test_data = panel[panel['trade_date'] == pred_date].copy()
        X_test = test_data[feature_cols].fillna(0)
        
        model = XGBRegressor(**self.config.get_xgboost_params())
        model.fit(X_train, y_train)
        
        y_pred = model.predict(X_test)
        
        results.append({
            'pred_date': pred_date,          # 信号生成日（T日）
            'stock_code': test_data['stock_code'].values,
            'prediction': y_pred,
            # ✅ 不在这里记录 actual，actual 在 backtest 里按 T+1 买入价计算
        })
    
    return results
```

---

### Task 4 — 修复 `backtest.py`：收益计算改为 T+1 买入

**这是最关键的一步**，决定回测逻辑是否符合实际。

**时间轴示意**：
```
T日（周五收盘后）   T+1日（下周一）    T+1+5日（下周五）
  ├── 因子计算          ├── 开盘买入         └── 开盘卖出
  ├── 模型预测          │   按 T日收盘价       按 T+6日开盘价
  └── 生成 Top N        └── 作为成本价         计算实际收益
```

**修改位置**：`backtest.py` → `calc_portfolio_returns()`

**修改后**：
```python
def calc_portfolio_returns(self, signals_list, panel):
    """
    signals_list: rolling_train_predict 的输出
    panel: 含 trade_date, stock_code, open, close 的完整数据（含未来价格，用于计算实际收益）
    """
    portfolio_records = []
    
    # 建立价格查询表：(stock_code, trade_date) -> open/close
    price_table = panel.set_index(['stock_code', 'trade_date'])
    all_dates = sorted(panel['trade_date'].unique())
    date_to_idx = {d: i for i, d in enumerate(all_dates)}
    
    for signal in signals_list:
        pred_date = signal['pred_date']       # T日：信号生成日
        stocks = signal['stock_code']
        preds = signal['prediction']
        
        # 按预测值排名，取 Top N
        ranked = sorted(zip(stocks, preds), key=lambda x: -x[1])
        top_stocks = [s for s, _ in ranked[:self.config.top_n]]
        
        # ✅ 买入日：T+1 日（下一个交易日）
        t_idx = date_to_idx.get(pred_date)
        if t_idx is None or t_idx + 1 >= len(all_dates):
            continue
        buy_date = all_dates[t_idx + 1]
        
        # ✅ 卖出日：T+1+hold_period 日
        hold = self.config.predict_horizon  # 默认5天
        sell_idx = t_idx + 1 + hold
        if sell_idx >= len(all_dates):
            continue
        sell_date = all_dates[sell_idx]
        
        # 计算每只股票的实际收益（用收盘价，更稳定；或用开盘价模拟更严格）
        stock_rets = []
        for stk in top_stocks:
            try:
                buy_price = price_table.loc[(stk, buy_date), 'close']   # T+1 收盘
                sell_price = price_table.loc[(stk, sell_date), 'close'] # T+6 收盘
                # 或更严格用开盘价：
                # buy_price = price_table.loc[(stk, buy_date), 'open']
                # sell_price = price_table.loc[(stk, sell_date), 'open']
                ret = sell_price / buy_price - 1
                stock_rets.append(ret)
            except KeyError:
                continue  # 停牌或数据缺失
        
        if not stock_rets:
            continue
        
        portfolio_ret = np.mean(stock_rets)
        
        # 基准收益：同期全市场等权
        benchmark_stocks = panel[panel['trade_date'] == buy_date]['stock_code'].tolist()
        bm_rets = []
        for stk in benchmark_stocks:
            try:
                bp = price_table.loc[(stk, buy_date), 'close']
                sp = price_table.loc[(stk, sell_date), 'close']
                bm_rets.append(sp / bp - 1)
            except KeyError:
                continue
        benchmark_ret = np.mean(bm_rets) if bm_rets else 0.0
        
        # ✅ 扣除交易成本（双边，A股约 0.15%~0.25%）
        cost = 0.002  # 0.2% 双边（可调）
        net_portfolio_ret = portfolio_ret - cost
        
        portfolio_records.append({
            'signal_date': pred_date,
            'buy_date': buy_date,
            'sell_date': sell_date,
            'portfolio_ret': net_portfolio_ret,
            'benchmark_ret': benchmark_ret,
            'excess_ret': net_portfolio_ret - benchmark_ret,
            'top_stocks': ','.join(top_stocks),
        })
    
    return pd.DataFrame(portfolio_records)
```

---

### Task 5 — 修复 `evaluator.py`：IC 计算用预测值 vs 实际未来收益

**问题**：IC 的计算需要确认用的是 `pred_date` 的预测值，和 `pred_date` 之后实际的 `future_ret`，而不是 `pred_date` 当天的当日收益。

**验证代码**：
```python
def calc_ic(self, pred_date, predictions, stocks, panel):
    """
    IC = corr(预测的未来5日收益排名, 实际未来5日收益排名)
    两者时间对齐：都是以 pred_date 为基准，往后看 N 天
    """
    # 实际未来收益：从 panel 里取 pred_date 当天的 future_ret（已经是 shift(-5) 的结果）
    actual = panel[panel['trade_date'] == pred_date].set_index('stock_code')['future_ret']
    
    pred_series = pd.Series(predictions, index=stocks)
    
    # 对齐
    common = pred_series.index.intersection(actual.index)
    pred_aligned = pred_series[common].dropna()
    actual_aligned = actual[common].dropna()
    common2 = pred_aligned.index.intersection(actual_aligned.index)
    
    if len(common2) < 10:
        return np.nan, np.nan
    
    ic = pred_aligned[common2].corr(actual_aligned[common2])  # Pearson
    rank_ic, _ = spearmanr(pred_aligned[common2], actual_aligned[common2])
    
    return ic, rank_ic
```

**注意**：这里的 IC 是"用未来实际收益来验证"——这在事后评估（回测分析）中是合法的，但模型训练时绝不能用这个 actual 当特征。

---

### Task 6 — 新增验证脚本：快速检测泄露

在 `test_strategy.py` 中新增一个专门的泄露检测函数：

```python
def test_no_lookahead(panel, feature_cols):
    """
    泄露检测：用"反向标签"测试
    如果用"过去5日收益"替换"未来5日收益"作为标签，
    模型 IC 应接近 0（随机）。
    如果 IC 仍然很高，说明存在泄露。
    """
    panel_test = panel.copy()
    # 用过去5日收益作为假标签
    panel_test['fake_label'] = panel_test.groupby('stock_code')['close'].transform(
        lambda x: x / x.shift(5) - 1  # 过去5日，非未来
    )
    
    # 跑一次 IC 计算
    from scipy.stats import spearmanr
    ic_list = []
    for date, grp in panel_test.groupby('trade_date'):
        grp = grp.dropna(subset=feature_cols + ['fake_label'])
        if len(grp) < 10:
            continue
        # 随机选一个因子
        ic, _ = spearmanr(grp['momentum_20d'], grp['fake_label'])
        ic_list.append(ic)
    
    mean_ic = np.nanmean(ic_list)
    print(f"[泄露检测] 反向标签 IC = {mean_ic:.4f}（应接近 0，若 >0.05 则存在泄露）")
    return mean_ic
```

另一个快速检测：直接打印训练集最后一天和预测日的时间差：
```python
def test_time_boundary(results):
    for r in results[:3]:
        pred_date = r['pred_date']
        print(f"信号日: {pred_date}")
        # 确认没有用到 pred_date 当天或之后的数据
```

---

## 修改优先级与预期效果

| 任务 | 优先级 | 预期 IC 变化 |
|------|--------|------------|
| Task 4 收益计算改 T+1 买入 | 🔴 最高 | 超额收益从 +1000% 降至合理 |
| Task 3 训练集边界检查 | 🔴 最高 | 确保无泄露 |
| Task 1 标签与特征分离 | 🟡 高 | IC 从 0.20 降至 0.05 以内 |
| Task 2 截面标准化隔离 | 🟡 高 | 保证 IC 计算真实 |
| Task 5 IC 计算对齐确认 | 🟢 中 | 评估指标准确性 |
| Task 6 泄露检测脚本 | 🟢 中 | 持续验证用 |

---

## 修复后的合理预期结果

| 指标 | 修复前（有泄露） | 修复后（合理区间） |
|------|----------------|-----------------|
| IC（上证50） | 0.207 | 0.03 ~ 0.06 |
| ICIR | 0.818 | 0.3 ~ 0.6 |
| IC>0 占比 | 80%+ | 55% ~ 65% |
| 年化超额收益 | +600%+ | +5% ~ +20% |
| 最大回撤 | -10% | -15% ~ -25% |
| 夏普比率 | 6.31 | 0.8 ~ 2.0 |

如果修复后 IC 仍然 > 0.08，说明因子本身质量很好，可以进一步调研是否有其他信息泄露。

---

## 科学回测的标准时间轴（总结）

```
周五（T日）收盘后
  ├── 计算截面因子（只用 T 日及之前的数据）
  ├── 用 [T-120, T-1] 的历史数据训练模型
  ├── 预测 T 日截面上每只股票的未来5日收益
  └── 生成 Top N 持仓列表（信号）

下周一（T+1日）开盘
  └── 按 T 日收盘价或 T+1 开盘价买入 Top N

下周五（T+6日）
  └── 收盘卖出，记录实际收益
  └── 同时生成新一期信号，重复循环

收益计算
  ├── 实际收益 = (卖出价 - 买入价) / 买入价 - 交易成本(0.2%)
  ├── 基准收益 = 同期指数收益（或全市场等权）
  └── 超额收益 = 实际收益 - 基准收益
```

---

*文档版本：1.0 | 生成日期：2026-03-27*
