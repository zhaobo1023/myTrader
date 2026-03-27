# XGBoost 截面预测策略

基于 MASTER 论文思想，使用 XGBoost 进行股票截面预测的量化策略。

## 概述

本策略实现了以下核心功能：

1. **52 维技术因子计算** - 基于 TA-Lib 计算 6 大类技术因子
2. **截面预处理** - MAD 去极值 + Z-Score 标准化
3. **滚动窗口训练** - XGBoost 模型滚动训练
4. **截面预测** - 预测未来 N 日收益率排名
5. **IC 评估** - IC/ICIR/RankIC/RankICIR 评估体系
6. **策略回测** - 基于预测排名的选股回测

## 因子体系

### 6 大类 52 维因子

| 类别 | 数量 | 说明 |
|------|------|------|
| 价量因子 | 10 | 价格和成交量衍生的基础因子 |
| 动量因子 | 8 | 价格趋势的持续性和强度 |
| 波动率因子 | 6 | 价格波动的剧烈程度 |
| 技术指标因子 | 12 | RSI/MACD/KDJ/ADX 等经典指标 |
| 均线形态因子 | 10 | 均线偏离度和 K 线形态 |
| 交互因子 | 6 | 多因子交叉组合 |

详细因子列表见 `feature_engine.py` 中的 `FACTOR_TAXONOMY`。

## 快速开始

### 1. 安装依赖

```bash
# 安装 Python 依赖
pip install -r requirements.txt

# 安装 TA-Lib (必需)
# macOS
brew install ta-lib
pip install TA-Lib

# Ubuntu/Debian
sudo apt-get install ta-lib
pip install TA-Lib

# Windows
# 下载预编译包: https://www.lfd.uci.edu/~gohlke/pythonlibs/#ta-lib
pip install TA_Lib-0.4.XX-cpXX-cpXX-win_amd64.whl
```

### 2. 配置数据库

确保 `.env` 文件中配置了数据库连接：

```bash
DB_ENV=local
LOCAL_DB_HOST=localhost
LOCAL_DB_NAME=mytrader
LOCAL_DB_USER=root
LOCAL_DB_PASSWORD=your_password
```

### 3. 运行策略

```bash
# 从项目根目录运行
python -m strategist.xgboost_strategy.run_strategy
```

## 配置说明

编辑 `config.py` 中的 `StrategyConfig` 类来调整策略参数：

```python
@dataclass
class StrategyConfig:
    # 数据配置
    start_date: str = '2023-01-01'
    end_date: str = '2025-12-31'
    
    # 训练配置
    train_window: int = 120  # 训练窗口（交易日）
    predict_horizon: int = 5  # 预测未来N日收益率
    roll_step: int = 5  # 滚动步长
    
    # XGBoost 超参数
    n_estimators: int = 50
    max_depth: int = 4
    learning_rate: float = 0.05
    
    # 预处理配置
    preprocess_method: str = 'mad'  # 'mad' 或 'robust_zscore'
    
    # 回测配置
    top_n: int = 10  # 买入预测排名前N的股票
```

## 模块说明

| 模块 | 功能 |
|------|------|
| `config.py` | 策略配置 |
| `feature_engine.py` | 52 维因子计算引擎 |
| `preprocessor.py` | 截面预处理（MAD/Z-Score） |
| `data_loader.py` | 数据加载与因子计算 |
| `model_trainer.py` | XGBoost 滚动窗口训练 |
| `predictor.py` | 截面预测器 |
| `evaluator.py` | IC 评估器 |
| `backtest.py` | 回测框架 |
| `visualizer.py` | 可视化工具 |
| `run_strategy.py` | 主入口脚本 |

## 输出结果

运行后会在 `output/` 目录生成：

1. **CSV 文件**
   - `signals.csv` - 每日预测信号
   - `portfolio_returns.csv` - 组合收益
   - `factor_ic.csv` - 因子 IC 统计

2. **可视化图表**
   - `ic_analysis.png` - IC 时序图和分布
   - `portfolio_performance.png` - 组合表现
   - `factor_ic.png` - 因子 IC 排名

3. **报告**
   - `strategy_report.md` - 策略报告

## 预期效果

根据课程代码的实验结果，使用 XGBoost + 52 维因子在 A 股上可以达到：

| 指标 | XGBoost | MASTER (论文) |
|------|---------|---------------|
| IC | 0.03~0.05 | 0.05~0.08 |
| ICIR | 0.3~0.5 | 0.4~0.7 |
| RankIC | 0.04~0.06 | 0.08~0.12 |

**实践意义**：IC > 0.03 即可产生有效的选股信号。

## 进阶使用

### 单因子 IC 分析

```python
from strategist.xgboost_strategy.data_loader import DataLoader
from strategist.xgboost_strategy.backtest import XGBoostBacktest
from strategist.xgboost_strategy.config import StrategyConfig

config = StrategyConfig()
data_loader = DataLoader(config)
panel, feature_cols = data_loader.load_and_compute_factors()

backtest = XGBoostBacktest(config)
factor_ic_df = backtest.analyze_factor_ic(panel, feature_cols)
print(factor_ic_df.head(10))
```

### 自定义股票池

```python
config = StrategyConfig()
config.stock_pool = ['600519.SH', '000858.SZ', '601318.SH']  # 自定义股票池
```

### 调整预测周期

```python
config = StrategyConfig()
config.predict_horizon = 10  # 预测未来10日收益率
config.train_window = 240  # 增加训练窗口
```

## 参考资料

- **MASTER 论文**: Li et al., "MASTER: Market-Guided Stock Transformer for Stock Price Forecasting" (AAAI 2024)
- **课程代码**: `/Users/zhaobo/data0/person/quant/课程代码-20260325`

## 注意事项

1. **TA-Lib 必需** - 因子计算依赖 TA-Lib，必须安装
2. **数据完整性** - 确保数据库中有足够的历史数据（至少 120 个交易日）
3. **计算时间** - 首次运行需要计算所有因子，可能需要几分钟
4. **内存占用** - 股票池越大，内存占用越高

## 故障排除

### ImportError: TA-Lib

```bash
# 确保安装了 TA-Lib 系统库
brew install ta-lib  # macOS
pip install TA-Lib
```

### 数据不足

```bash
# 检查数据库中的数据
python -c "from config.db import execute_query; print(execute_query('SELECT COUNT(*) FROM trade_stock_daily'))"
```

### XGBoost 未安装

```bash
pip install xgboost
```

## License

MIT
