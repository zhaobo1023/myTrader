# 大盘首页设计文档

> 版本: v1.0 | 日期: 2026-04-14

## 一、目标

将 `/sentiment` 页面升级为**大盘首页**（Market Dashboard），一屏呈现市场全貌。用户打开页面后，无需翻页即可回答以下核心问题:

1. 市场整体冷热如何?
2. 大盘趋势向上还是震荡向下?
3. 市场参与者恐惧还是贪婪?
4. 资金偏好什么风格?（大/小盘、成长/价值）
5. 股债之间的相对关系?
6. 哪些信号最近发生了翻转?

设计原则:
- **先看结论再看数据** -- 每个板块顶部一句话综合判断
- **变化比绝对值重要** -- 每个指标显示方向和持续天数
- **颜色即信号** -- 红/绿/灰三色系，一眼扫完即知全貌
- **日频更新** -- 盘后更新一次，感受变化而非追逐盘中波动

---

## 二、页面总体布局

```
+------------------------------------------------------------------+
|  大盘总览                    2026-04-14 周一     数据截止: 15:00   |
+------------------------------------------------------------------+
|                                                                    |
|  [市场温度]          [趋势方向]          [情绪恐贪]               |
|   综合判断条          综合判断条           综合判断条              |
|   5-6项核心指标       5-6项核心指标        5-6项核心指标           |
|   迷你趋势线          迷你趋势线           迷你趋势线             |
|                                                                    |
+------------------------------------------------------------------+
|                                                                    |
|  [风格轮动]          [股债关系]           [宏观背景]              |
|   综合判断条          综合判断条           综合判断条              |
|   风格/大小盘指标     利差/国债指标        PMI/M2/北向等           |
|   迷你趋势线          迷你趋势线           迷你趋势线             |
|                                                                    |
+------------------------------------------------------------------+
|                                                                    |
|  [信号变化日志] -- 最近 7 日重要信号翻转记录                      |
|                                                                    |
+------------------------------------------------------------------+
```

页面路由: `/sentiment` (复用现有路由，标题改为"大盘总览")

响应式: 桌面端 3 列, 平板 2 列, 手机 1 列

---

## 三、6 大板块详细设计

### 板块 1: 市场温度 (Market Temperature)

**核心问题: 市场整体冷热如何?**

#### 综合判断
5 档: `冰点` / `低迷` / `常温` / `活跃` / `过热`

颜色: 冰点=深蓝, 低迷=浅蓝, 常温=灰, 活跃=浅红, 过热=深红

#### 指标列表

| # | 指标 | 计算方式 | 判断标准 | 数据源 |
|---|------|---------|---------|--------|
| 1 | 两市成交额(亿) | 当日沪+深成交额合计 | 展示绝对值 + 与昨日对比 | AKShare `stock_zh_a_hist` 或 `macro_data` 新增 |
| 2 | 成交额/MA20 | 当日成交额 / 20日均值 | <0.7冰点, <0.85低迷, 0.85-1.15常温, >1.15活跃, >1.5过热 | 计算字段 |
| 3 | 全A平均换手率分位 | 当日换手率在近252日的百分位 | <15%冰点, <30%低迷, 30-70%常温, >70%活跃, >85%过热 | **已有** `calc_market_turnover` |
| 4 | 涨跌家数比 | 上涨家数 / 下跌家数 | <0.5极弱, <0.8弱, 0.8-1.2均衡, >1.2强, >2.0极强 | AKShare `stock_zh_a_spot_em` 汇总 |
| 5 | 涨停/跌停家数 | 当日涨停数 vs 跌停数 | 展示绝对值(如 "68/15") | AKShare |
| 6 | 融资余额5日变化率(%) | (今日融资余额 - 5日前) / 5日前 * 100 | >1%活跃, <-1%收缩 | AKShare `stock_margin_sse` + `stock_margin_szse` |

#### 综合评分逻辑

```python
score = 0
score += turnover_pct_rank_contribution   # 换手率分位贡献 0-25
score += volume_ratio_contribution         # 成交额/MA20贡献 0-25
score += advance_decline_contribution      # 涨跌比贡献 0-25
score += margin_change_contribution        # 融资变化贡献 0-25
# 总分 0-100 映射到 5 档
```

#### 迷你图
- 20 日成交额柱状图 + MA20 均线
- 当日柱用高亮色

---

### 板块 2: 趋势方向 (Trend & Direction)

**核心问题: 大盘是趋势上行、震荡还是下行?**

#### 综合判断
5 档: `强势上攻` / `温和上行` / `震荡蓄势` / `弱势调整` / `恐慌下跌`

颜色: 强势=深绿, 温和上行=浅绿, 震荡=灰, 弱势=浅红, 恐慌=深红

#### 指标列表

| # | 指标 | 计算方式 | 判断标准 | 数据源 |
|---|------|---------|---------|--------|
| 1 | 主要指数涨跌幅 | 上证/沪深300/创业板/中证1000 当日涨跌幅 | 直接展示, 颜色标记 | AKShare 指数数据 或 `macro_data` |
| 2 | 指数均线位置 | 收盘价 vs MA5/MA20/MA60/MA250 | 在哪些均线之上/之下 | 计算字段 |
| 3 | 均线排列状态 | MA5 vs MA20 vs MA60 关系 | 多头排列 / 缠绕(方向选择) / 空头排列 | 计算字段 |
| 4 | MACD 周线状态 | 沪深300周线MACD(DIF/DEA/柱) | 金叉/死叉 + 红柱/绿柱 扩张or收缩 | 计算字段 |
| 5 | 趋势强度(ADX 14) | 沪深300日线ADX | <20震荡, 20-25弱趋势, >25趋势明确 | 计算字段 |
| 6 | SVD市场结构 | F1方差占比 + 突变信号 | 齐涨齐跌/板块分化/个股行情 + 是否突变 | **已有** `market_monitor` |

#### 综合评分逻辑

```python
# 方向分: 正=上行, 负=下行, 0=震荡
direction_score = 0
direction_score += ma_position_score       # 均线位置 -20 ~ +20
direction_score += ma_alignment_score      # 均线排列 -15 ~ +15
direction_score += macd_weekly_score       # MACD周线 -15 ~ +15
# 幅度: ADX决定趋势置信度
confidence = adx_to_confidence(adx)        # 0.3 ~ 1.0
# 综合: 方向 * 置信度 映射到 5 档
```

#### 迷你图
- 沪深300 近 60 日K线 + MA20/MA60 叠加
- ADX曲线(底部小图)

---

### 板块 3: 情绪恐贪 (Sentiment & Fear-Greed)

**核心问题: 市场参与者是恐惧还是贪婪?**

#### 综合判断
5 档: `极度恐惧` / `恐惧` / `中性` / `贪婪` / `极度贪婪`

颜色: 极度恐惧=深绿(反向!机会), 恐惧=浅绿, 中性=灰, 贪婪=浅红, 极度贪婪=深红(风险)

> 注意: 情绪板块颜色逻辑是**逆向**的 -- 极度恐惧是潜在机会(绿), 极度贪婪是风险(红)

#### 指标列表

| # | 指标 | 计算方式 | 判断标准 | 数据源 |
|---|------|---------|---------|--------|
| 1 | A股恐贪指数 | 综合评分(0-100) | 0-20极恐, 20-40恐惧, 40-60中性, 60-80贪婪, 80-100极贪 | 综合计算(见下) |
| 2 | QVIX(中国波指) | iVX/QVIX值 | <15平静, 15-25正常, 25-35焦虑, >35恐慌 | **已有** `macro_pulse` |
| 3 | 北向资金(亿) | 当日净买入 + 5日累计 | 持续流入=偏贪, 持续流出=偏恐 | **已有** `macro_pulse` |
| 4 | 融资净买入(亿) | 当日融资买入-偿还 | >0做多情绪, <0谨慎 | AKShare |
| 5 | 新高/新低家数 | 创60日新高 vs 创60日新低 | 新高>新低=乐观, 反之=悲观 | AKShare |
| 6 | 封板率(%) | 涨停封住家数 / 曾触及涨停家数 | >70%追高意愿强, <50%犹豫 | AKShare |

#### A股恐贪指数计算

```python
# 独立于VIX的A股本土恐贪指数
score = 50  # 基准
score += qvix_contribution          # QVIX: -15 ~ +15
score += north_flow_contribution    # 北向5日: -10 ~ +10
score += margin_contribution        # 融资变化: -10 ~ +10
score += new_high_low_contribution  # 新高/新低比: -10 ~ +10
score += seal_rate_contribution     # 封板率: -5 ~ +5
score = max(0, min(100, score))
```

#### 迷你图
- 恐贪指数近 20 日折线图
- 20/80 阈值区域标记

---

### 板块 4: 风格轮动 (Style Rotation)

**核心问题: 资金偏好什么风格?**

#### 综合判断
展示两个维度:
- 大小盘: `大盘主导` / `均衡` / `小盘主导` (各分 confirmed/weak)
- 风格: `价值主导` / `均衡` / `成长主导` (各分 confirmed/weak)

#### 指标列表

| # | 指标 | 计算方式 | 判断标准 | 数据源 |
|---|------|---------|---------|--------|
| 1 | 大盘/小盘三棱镜 | 沪深300 vs 中证1000 (Boll+MA5Y+Mom40d) | confirmed/weak/neutral | **已有** `calc_scale_rotation` |
| 2 | 成长/价值三棱镜 | Growth300 vs Value300 (同上) | confirmed/weak/neutral | **已有** `calc_style_rotation` |
| 3 | 中证500相对强弱 | 中证500 / 沪深300 的 20日动量 | 中盘是否独立走强 | 新增计算 |
| 4 | 5年锚偏离度 | 全A vs 5年均线偏离% | 估值高低参考 | **已有** `calc_anchor_5y` |

#### 展示方式

**风格指南针** (核心视觉):
```
              成长
               |
               |
    小盘 ------+------ 大盘
               |
               |
              价值

    [x] = 当前位置(根据两个三棱镜信号定位)
    箭头 = 近 20 日漂移方向
```

+ 5年锚偏离度作为底部估值标尺

---

### 板块 5: 股债关系 (Stock-Bond Dynamics)

**核心问题: 股票相对债券是贵还是便宜?**

#### 综合判断
3 档: `股票吸引力强` / `中性` / `债券更优`

#### 指标列表

| # | 指标 | 计算方式 | 判断标准 | 数据源 |
|---|------|---------|---------|--------|
| 1 | 股债利差(EP-CN10Y) | 沪深300盈利收益率 - 中国10年国债 | >3%股票极其便宜, 1-3%中性, <1%债券更优 | **已有** `calc_stock_bond_spread` |
| 2 | 10年国债收益率 | CN10Y当前值 + 趋势方向 | 展示值 + 近期方向(上行/下行/横盘) | **已有** |
| 3 | 股息率利差 | 沪深300股息率 - CN10Y | >0红利价值突出, <0债券收益更高 | **已有** `calc_dividend_tracking` |
| 4 | 基金3年滚动收益 | 偏股基金指数3年年化 | <-10%底部区, >30%泡沫区 | **已有** `calc_equity_fund_rolling` |

#### 迷你图
- 股债利差近 250 日走势 + 均值线 + 1标准差带

---

### 板块 6: 宏观背景 (Macro Backdrop)

**核心问题: 宏观环境对市场是顺风还是逆风?**

#### 综合判断
3 档: `顺风` / `中性` / `逆风`

#### 指标列表

| # | 指标 | 计算方式 | 判断标准 | 数据源 |
|---|------|---------|---------|--------|
| 1 | 制造业PMI | 最新值 | >=50扩张(顺风), <50收缩(逆风) | **已有** `macro_pulse` |
| 2 | M2同比增速(%) | 最新值 + 环比变化 | 上升=宽松(偏顺风) | **已有** `macro_pulse` |
| 3 | AH溢价指数 | 最新值 | <120低(A便宜), >140高(A贵) | **已有** `macro_pulse` |
| 4 | VIX(美股波动率) | 最新值 + 等级 | 外围风险参考 | **已有** `fear_index` |
| 5 | 社融增速(%) | 最新同比 | 上行=信用扩张 | AKShare 新增 |

#### 迷你图
- PMI 近 12 月柱状图 + 50 分水岭线

---

## 四、底部: 信号变化日志 (Signal Change Log)

展示最近 7 天内发生的**信号级别翻转**，按时间倒序排列。

### 记录规则

当以下任一板块的综合判断等级发生变化时，自动记录:

| 板块 | 示例翻转 |
|------|---------|
| 市场温度 | "低迷 -> 常温" |
| 趋势方向 | "震荡蓄势 -> 温和上行" |
| 情绪恐贪 | "中性 -> 贪婪" |
| 风格轮动 | "大盘主导(confirmed) -> 均衡" |
| 股债关系 | "中性 -> 股票吸引力强" |
| 宏观背景 | "中性 -> 顺风" |

也记录关键**单项指标**翻转:
- MACD 周线金叉/死叉
- 均线多空排列切换
- SVD突变信号触发
- 北向资金连续3日同向
- 成交额突破/跌破 MA20

### 展示格式

```
04-14  [市场温度]  低迷 -> 常温    成交额突破 MA20, 换手率分位升至 55%
04-12  [趋势方向]  震荡 -> 偏多    沪深300 MACD 周线金叉
04-10  [情绪恐贪]  中性 -> 偏贪    北向资金连续 3 日净流入累计 +82 亿
04-08  [风格轮动]  均衡 -> 小盘    中证1000三棱镜翻多, 动量信号确认
```

### 存储

新增数据库表 `trade_dashboard_signal_log`:

```sql
CREATE TABLE trade_dashboard_signal_log (
    id INT PRIMARY KEY AUTO_INCREMENT,
    trade_date DATE NOT NULL,
    section VARCHAR(50) NOT NULL COMMENT '板块: temperature/trend/sentiment/style/bond/macro',
    signal_from VARCHAR(100) NOT NULL COMMENT '前值',
    signal_to VARCHAR(100) NOT NULL COMMENT '后值',
    trigger_detail TEXT COMMENT '触发原因描述',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_date (trade_date),
    INDEX idx_section (section)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COMMENT='大盘信号翻转日志';
```

---

## 五、数据架构

### 5.1 新增数据需求

以下指标需要新增采集（现有系统未覆盖）:

| 指标 | 推荐数据源 | 采集频率 | 存储方式 |
|------|-----------|---------|---------|
| 两市成交额 | AKShare `stock_zh_a_hist` 指数数据 | 日频 | `macro_data` 表, indicator='market_volume' |
| 涨跌家数 | AKShare `stock_zh_a_spot_em` 汇总 | 日频 | `macro_data` 表, indicator='advance_count' / 'decline_count' |
| 涨停/跌停家数 | AKShare `stock_zt_pool_em` / `stock_dt_pool_em` | 日频 | `macro_data` 表, indicator='limit_up_count' / 'limit_down_count' |
| 融资余额 | AKShare `stock_margin_sse` + `stock_margin_szse` | 日频 | `macro_data` 表, indicator='margin_balance' |
| 融资净买入 | AKShare 同上 | 日频 | `macro_data` 表, indicator='margin_net_buy' |
| 新高/新低家数 | 从 `trade_stock_daily` 计算(60日新高/新低) | 日频 | `macro_data` 表, indicator='new_high_60d' / 'new_low_60d' |
| 封板率 | AKShare `stock_zt_pool_em` 字段 | 日频 | `macro_data` 表, indicator='seal_rate' |
| 指数日线(上证/300/创业板/1000) | AKShare 指数接口 | 日频 | `macro_data` 表, indicator='idx_sh' / 'idx_csi300' 等 (部分已有) |
| 社融增速 | AKShare `macro_china_shrzgm` | 月频 | `macro_data` 表, indicator='social_finance_yoy' |

### 5.2 现有数据复用

以下指标直接复用，无需新增采集:

| 指标 | 来源模块 | 接口/函数 |
|------|---------|----------|
| 全A平均换手率 | `market_overview/calculator.py` | `calc_market_turnover()` |
| 股债利差 | `market_overview/calculator.py` | `calc_stock_bond_spread()` |
| 大小盘三棱镜 | `market_overview/calculator.py` | `calc_scale_rotation()` |
| 成长价值三棱镜 | `market_overview/calculator.py` | `calc_style_rotation()` |
| 5年锚偏离度 | `market_overview/calculator.py` | `calc_anchor_5y()` |
| 红利追踪 | `market_overview/calculator.py` | `calc_dividend_tracking()` |
| 基金3年滚动 | `market_overview/calculator.py` | `calc_equity_fund_rolling()` |
| QVIX/北向/M2/PMI/AH溢价 | `market_overview/calculator.py` | `calc_macro_pulse()` |
| VIX/恐贪指数 | `sentiment/fear_index.py` | `FearIndexService` |
| SVD市场结构 | `market_monitor/` | `trade_svd_market_state` 表 |

### 5.3 新增计算需求

以下指标需基于已有数据新增计算逻辑:

| 指标 | 输入数据 | 计算逻辑 |
|------|---------|---------|
| 成交额/MA20 | 两市成交额近20日 | `today_vol / ma(vol, 20)` |
| 涨跌家数比 | 涨/跌家数 | `advance / decline` |
| 指数均线位置 | 指数日线 | 收盘vs MA5/20/60/250, 输出"在X均线之上" |
| 均线排列状态 | 指数日线 | MA5>MA20>MA60=多头, 反之=空头, 其余=缠绕 |
| MACD周线 | 指数日线转周线 | 标准MACD(12,26,9), 输出金叉/死叉+柱方向 |
| ADX(14) | 指数日线 | 标准ADX计算 |
| A股恐贪指数 | 综合6项 | 见板块3详细公式 |
| 中证500相对强弱 | idx_csi500 / idx_csi300 | 20日动量差 |

---

## 六、后端实现方案

### 6.1 模块结构

```
data_analyst/
└── market_dashboard/
    ├── __init__.py
    ├── config.py              # 阈值配置、信号档位定义
    ├── fetcher.py             # 新增指标数据采集(AKShare)
    ├── calculator.py          # 6大板块计算器(整合已有模块)
    ├── signal_tracker.py      # 信号翻转检测与记录
    └── schemas.py             # 数据模型 + DDL
```

### 6.2 calculator.py 核心设计

```python
class MarketDashboardCalculator:
    """整合已有计算模块 + 新增指标, 输出6大板块结构化数据."""

    def compute_all(self) -> dict:
        """主入口, 返回完整 dashboard 数据."""
        return {
            'updated_at': '2026-04-14',
            'temperature': self._calc_temperature(),
            'trend': self._calc_trend(),
            'sentiment': self._calc_sentiment(),
            'style': self._calc_style(),
            'stock_bond': self._calc_stock_bond(),
            'macro': self._calc_macro(),
            'signal_log': self._get_recent_signals(days=7),
        }

    def _calc_temperature(self) -> dict:
        """板块1: 市场温度."""
        # 复用 calc_market_turnover() + 新增指标
        return {
            'level': 'normal',           # 5档之一
            'score': 52,                 # 0-100
            'indicators': {
                'volume': {'value': 8932, 'unit': '亿', 'change': '+5.2%'},
                'volume_ratio_ma20': {'value': 1.05, 'signal': 'normal'},
                'turnover_pct_rank': {'value': 55.0, 'signal': 'normal'},
                'advance_decline': {'advance': 2847, 'decline': 1923, 'ratio': 1.48},
                'limit_up_down': {'up': 68, 'down': 15},
                'margin_change_5d': {'value': 0.3, 'unit': '%', 'signal': 'normal'},
            },
            'series': [...],             # 20日成交额 + MA20
        }

    def _calc_trend(self) -> dict:
        """板块2: 趋势方向."""
        # 复用 SVD + 新增均线/MACD/ADX
        return {
            'level': 'consolidating',    # 5档之一
            'indices': {
                'sh': {'name': '上证', 'close': 3245.12, 'change_pct': 0.82},
                'csi300': {'name': '沪深300', 'close': 3801.55, 'change_pct': 0.95},
                'gem': {'name': '创业板', 'close': 2156.78, 'change_pct': 1.23},
                'csi1000': {'name': '中证1000', 'close': 6234.56, 'change_pct': 0.45},
            },
            'indicators': {
                'ma_position': {'above': ['MA5', 'MA20'], 'below': ['MA60', 'MA250']},
                'ma_alignment': 'tangled',    # bullish/bearish/tangled
                'macd_weekly': {'status': 'golden_cross', 'histogram': 'expanding'},
                'adx': {'value': 18, 'signal': 'weak_trend'},
                'svd': {'state': 'sector_rotation', 'is_mutation': False},
            },
            'series': [...],             # 60日K线
        }

    # ... 其余4个板块类似结构
```

### 6.3 fetcher.py 数据采集

```python
class MarketDashboardFetcher:
    """采集大盘首页所需的新增指标数据, 写入 macro_data 表."""

    def fetch_all(self, trade_date: str = None):
        """日频采集入口, 在盘后调度中调用."""
        self.fetch_market_volume(trade_date)
        self.fetch_advance_decline(trade_date)
        self.fetch_limit_up_down(trade_date)
        self.fetch_margin_data(trade_date)
        self.fetch_new_high_low(trade_date)
        self.fetch_seal_rate(trade_date)

    def fetch_market_volume(self, trade_date):
        """两市总成交额."""
        # AKShare: stock_zh_a_hist(symbol="sh000001") 上证指数含成交额
        ...

    def fetch_advance_decline(self, trade_date):
        """涨跌家数."""
        # AKShare: stock_zh_a_spot_em() 全量快照, 统计涨/跌/平
        ...
```

### 6.4 signal_tracker.py 信号翻转追踪

```python
class SignalTracker:
    """对比昨日与今日各板块信号, 检测翻转并写入 trade_dashboard_signal_log."""

    def check_and_log(self, today_data: dict, yesterday_data: dict):
        """对比两日数据, 记录翻转."""
        sections = [
            ('temperature', 'level'),
            ('trend', 'level'),
            ('sentiment', 'level'),
            ('style.scale', 'direction'),
            ('style.growth_value', 'direction'),
            ('stock_bond', 'signal'),
            ('macro', 'level'),
        ]
        for section, key in sections:
            old_val = self._get_nested(yesterday_data, section, key)
            new_val = self._get_nested(today_data, section, key)
            if old_val and new_val and old_val != new_val:
                self._write_log(section, old_val, new_val, ...)
```

### 6.5 API 路由

复用并扩展现有 `/api/market-overview/summary`:

```python
# api/routers/market_overview.py 扩展

@router.get('/dashboard')
async def get_market_dashboard(redis=Depends(get_redis)) -> dict:
    """返回大盘首页完整数据, 6h Redis缓存."""
    ...

@router.get('/signal-log')
async def get_signal_log(days: int = 7) -> list:
    """返回最近N天信号翻转日志."""
    ...
```

---

## 七、前端实现方案

### 7.1 页面改造

将 `/sentiment` 页面改造为大盘首页，保留原有舆情功能作为子 Tab:

```
/sentiment (重命名为 "大盘总览")
  ├── 默认视图: 6 大板块 + 信号日志 (新)
  └── Tab "舆情详情": 原有 FearIndex / News / Events / Polymarket (保留)
```

### 7.2 组件结构

```
web/src/app/sentiment/
├── page.tsx                           # 主页面(Tab切换: 大盘总览 | 舆情详情)
├── components/
│   ├── DashboardView.tsx              # 大盘总览主视图(新)
│   ├── SignalCard.tsx                 # 通用信号卡片组件(新)
│   │   ├── 顶部: 板块名 + 综合判断badge
│   │   ├── 中部: 指标列表(带方向箭头)
│   │   └── 底部: 迷你趋势图(Sparkline)
│   ├── StyleCompass.tsx               # 风格指南针(新)
│   ├── SignalLog.tsx                   # 信号变化日志(新)
│   ├── Sparkline.tsx                  # 迷你趋势线组件(新, SVG)
│   │
│   ├── OverviewCards.tsx              # (保留, 舆情Tab用)
│   ├── FearIndexPanel.tsx             # (保留)
│   ├── NewsSentimentPanel.tsx         # (保留)
│   ├── EventSignalPanel.tsx           # (保留)
│   └── PolymarketPanel.tsx            # (保留)
```

### 7.3 SignalCard 通用组件

每个板块用同一个 `SignalCard` 组件渲染:

```typescript
interface SignalCardProps {
    title: string;           // "市场温度"
    level: string;           // "normal"
    levelLabel: string;      // "常温"
    levelColor: string;      // 根据level映射
    indicators: Indicator[]; // 指标列表
    sparklineData?: number[];// 迷你图数据
    sparklineLabel?: string; // 迷你图标题
}

interface Indicator {
    label: string;           // "成交额"
    value: string;           // "8932亿"
    signal?: 'positive' | 'negative' | 'neutral';
    change?: string;         // "+5.2%" 或 "3日"
    changeDir?: 'up' | 'down' | 'flat';
}
```

### 7.4 Sparkline 迷你图

纯 SVG 实现, 无需引入图表库:

```typescript
// 简单折线 sparkline, 约 50 行代码
function Sparkline({ data, width = 120, height = 32, color = 'var(--accent)' })
```

### 7.5 数据获取

```typescript
// 单一 API 调用获取全部数据
const { data } = useQuery({
    queryKey: ['market-dashboard'],
    queryFn: () => fetch('/api/market-overview/dashboard').then(r => r.json()),
    refetchInterval: 300_000,   // 5分钟刷新(日频数据, 不用太频繁)
    staleTime: 60_000,
});
```

---

## 八、调度集成

### 8.1 新增 YAML 任务

在 `tasks/` 下新增或修改任务定义:

```yaml
# tasks/08_dashboard.yaml

fetch_dashboard_data:
    callable: scheduler.adapters.run_dashboard_fetch
    schedule: "16:30"
    tags: [daily, dashboard]
    timeout: 300
    retry: 2
    retry_delay: 60
    depends_on:
        - fetch_daily_data    # 确保日线数据已拉取
    env:
        DB_ENV: online

compute_dashboard_signals:
    callable: scheduler.adapters.run_dashboard_compute
    schedule: "17:00"
    tags: [daily, dashboard]
    timeout: 180
    retry: 2
    retry_delay: 30
    depends_on:
        - fetch_dashboard_data
        - compute_technical_indicators    # 确保技术指标已算
    env:
        DB_ENV: online
```

### 8.2 执行流程

```
16:00  A股收盘
16:30  fetch_dashboard_data  -- 采集新增指标(成交额/涨跌停/融资等)
17:00  compute_dashboard_signals -- 计算6板块 + 信号翻转检测
17:05  Redis缓存更新, 前端下次刷新自动获取最新数据
```

---

## 九、实施分期

### Phase 1: 核心框架 (后端计算 + API + 前端骨架)

- 新建 `data_analyst/market_dashboard/` 模块
- 实现 `calculator.py`: 整合已有 `market_overview` 8组信号, 映射到新的6板块结构
- 实现 `fetcher.py`: 采集 6 项新增指标
- 扩展 API: `/api/market-overview/dashboard`
- 前端: `DashboardView` + `SignalCard` + `Sparkline`
- 前端: 页面改造, Tab切换(大盘总览 / 舆情详情)

### Phase 2: 趋势板块增强

- 新增指数均线位置、均线排列、MACD周线、ADX 计算
- 接入 SVD 市场结构数据
- 趋势板块完整展示

### Phase 3: 情绪板块 + A股恐贪指数

- 新增采集: 新高/新低、封板率
- 实现A股本土恐贪指数计算
- 情绪板块完整展示

### Phase 4: 信号翻转追踪

- 实现 `signal_tracker.py`
- 新建 `trade_dashboard_signal_log` 表
- 前端 `SignalLog` 组件
- 调度集成

### Phase 5: 视觉优化

- 风格指南针(StyleCompass)交互优化
- Sparkline 增加 hover tooltip
- 响应式布局适配
- 加载骨架屏

---

## 十、指标阈值配置汇总

集中定义在 `config.py`, 便于后续调优:

```python
# data_analyst/market_dashboard/config.py

# -- 板块1: 市场温度 --
VOLUME_RATIO_THRESHOLDS = [0.7, 0.85, 1.15, 1.5]       # 冰点/低迷/常温/活跃/过热
TURNOVER_PCT_THRESHOLDS = [15, 30, 70, 85]               # 同上
ADV_DEC_RATIO_THRESHOLDS = [0.5, 0.8, 1.2, 2.0]         # 极弱/弱/均衡/强/极强

# -- 板块2: 趋势方向 --
ADX_THRESHOLDS = [20, 25]                                 # 震荡/弱趋势/趋势明确

# -- 板块3: 情绪恐贪 --
FEAR_GREED_THRESHOLDS = [20, 40, 60, 80]                  # 极恐/恐惧/中性/贪婪/极贪
QVIX_THRESHOLDS = [15, 25, 35]                            # 平静/正常/焦虑/恐慌
SEAL_RATE_THRESHOLDS = [50, 70]                            # 犹豫/正常/追高

# -- 板块5: 股债 --
STOCK_BOND_SPREAD_THRESHOLDS = [1, 3]                      # 债优/中性/股优

# -- 板块6: 宏观 --
PMI_THRESHOLD = 50                                         # 扩张/收缩分界
AH_PREMIUM_THRESHOLDS = [120, 140]                         # 低/中/高
```

---

## 附录 A: 与现有模块的关系

```
                 market_dashboard (新)
                /       |        \
               /        |         \
    market_overview  sentiment  market_monitor
    (8组信号)      (恐贪/舆情)   (SVD结构)

    market_dashboard 是聚合层, 不重复实现计算逻辑,
    而是调用已有模块的函数, 加上新增指标的采集和计算,
    统一输出为6板块结构化数据.
```

现有 `/api/market-overview/summary` 接口保持不变(向后兼容), 新增 `/api/market-overview/dashboard` 作为大盘首页的专用接口。

## 附录 B: 关键 AKShare 接口

```python
import akshare as ak

# 涨停池 (含封板率)
ak.stock_zt_pool_em(date="20260414")

# 跌停池
ak.stock_dt_pool_em(date="20260414")

# 全A股实时行情快照 (用于统计涨跌家数)
ak.stock_zh_a_spot_em()

# 融资融券 - 沪市
ak.stock_margin_sse(start_date="20260401", end_date="20260414")

# 融资融券 - 深市
ak.stock_margin_szse(start_date="20260401", end_date="20260414")

# 指数行情
ak.stock_zh_index_daily(symbol="sh000001")  # 上证
ak.stock_zh_index_daily(symbol="sh000300")  # 沪深300

# 社会融资规模
ak.macro_china_shrzgm()
```
