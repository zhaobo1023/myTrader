# 舆情监控与感知集成方案

> 基于课程代码 `/Users/zhaobo/data0/person/quant/课程代码-20260408` 和 `舆情感知与事件驱动.md` 的技术方案，集成到 myTrader 项目。

## 一、技术方案概述

### 1.1 课程代码核心能力

| 层次 | 功能 | 数据源 | 脚本 |
|------|------|--------|------|
| **微观舆情** | 个股/行业新闻情感分析 | 东方财富(akshare) | `news_fetcher.py`, `sentiment_scorer.py`, `event_detector.py` |
| **宏观风险** | VIX/OVX/GVZ + 10年期国债 | Yahoo Finance / akshare | `market_fear_index.py` |
| **预测市场** | Polymarket 地缘政治概率 | Gamma API | `polymarket_monitor.py` |

### 1.2 myTrader 现有架构

- **后端**: FastAPI + MySQL + Redis + Celery
- **前端**: Next.js 16 (App Router) + TypeScript + TailwindCSS
- **数据层**: MySQL (双环境) + ChromaDB (RAG)
- **任务调度**: scheduler/ (YAML DAG)

### 1.3 集成目标

1. 新增 `data_analyst/sentiment/` 模块 - 舆情数据采集与分析
2. 新增 `api/routers/sentiment.py` - 舆情监控 API
3. 新增 `web/src/app/sentiment/` - 舆情监控前端页面
4. 集成到 scheduler 定时任务 - 每日自动更新

---

## 二、整体架构

```
+-------------------------------------------------------------------+
|                      舆情监控看板 (前端)                            |
+---------------+---------------+---------------+-------------------+
|  宏观恐慌指数  |  预测市场      |  个股舆情      |  事件驱动信号      |
|  (VIX/国债)   | (Polymarket)  |  (新闻分析)    |  (资产重组等)      |
+-------+-------+-------+-------+-------+-------+---------+---------+
        |               |               |                 |
        v               v               v                 v
+-------------------------------------------------------------------+
|                      FastAPI 后端 API                              |
|  /api/sentiment/fear-index     - 恐慌/贪婪指数                      |
|  /api/sentiment/polymarket     - 预测市场数据                       |
|  /api/sentiment/news           - 新闻获取与情感分析                  |
|  /api/sentiment/events         - 事件检测与信号                     |
+-------+-----------------------------------------------------------+
        |
        v
+-------------------------------------------------------------------+
|                      数据层                                        |
|  - akshare (东财新闻/VIX/国债)                                      |
|  - yfinance (VIX/OVX/GVZ)                                          |
|  - Polymarket Gamma API (免费无需认证)                              |
|  - MySQL (缓存 + 历史数据)                                          |
|  - LLM (DashScope/DeepSeek 情感分析)                                |
+-------------------------------------------------------------------+
```

---

## 三、后端模块设计

### 3.1 目录结构

```
myTrader/
+-- data_analyst/
|   +-- sentiment/                    # [新增] 舆情分析模块
|       +-- __init__.py
|       +-- config.py                 # 配置参数
|       +-- schemas.py                # Pydantic 数据模型
|       +-- fear_index.py             # 恐慌指数服务
|       +-- polymarket.py             # 预测市场服务
|       +-- news_fetcher.py           # 新闻获取服务
|       +-- sentiment_analyzer.py     # LLM 情感分析
|       +-- event_detector.py         # 事件检测
|       +-- storage.py                # 数据库读写
|       +-- run_monitor.py            # CLI 入口
|
+-- api/
|   +-- routers/
|       +-- sentiment.py              # [新增] 舆情监控 API 路由
|   +-- schemas/
|       +-- sentiment.py              # [新增] API 请求/响应模型
|
+-- tasks/
|   +-- 07_sentiment.yaml             # [新增] 舆情任务定义
|
+-- web/
    +-- src/app/
        +-- sentiment/                # [新增] 舆情监控页面
            +-- page.tsx
            +-- components/
                +-- FearIndexCard.tsx
                +-- PolymarketPanel.tsx
                +-- NewsSentimentPanel.tsx
                +-- EventSignalPanel.tsx
```

### 3.2 数据库表设计

```sql
-- 恐慌指数历史记录
CREATE TABLE IF NOT EXISTS trade_fear_index (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    trade_date DATE NOT NULL COMMENT '交易日期',
    vix DECIMAL(10,4) COMMENT 'VIX 恐慌指数',
    ovx DECIMAL(10,4) COMMENT 'OVX 原油波动率',
    gvz DECIMAL(10,4) COMMENT 'GVZ 黄金波动率',
    us10y DECIMAL(10,4) COMMENT '美国10年期国债收益率',
    fear_greed_score INT COMMENT '综合恐慌/贪婪评分 0-100',
    market_regime VARCHAR(20) COMMENT '市场状态: extreme_fear/fear/neutral/greed/extreme_greed',
    risk_alert TEXT COMMENT '风险提示',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_trade_date (trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='恐慌指数历史';

-- 新闻情感分析结果
CREATE TABLE IF NOT EXISTS trade_news_sentiment (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    stock_code VARCHAR(10) COMMENT '股票代码(可为空表示全市场)',
    news_title VARCHAR(500) NOT NULL COMMENT '新闻标题',
    news_content TEXT COMMENT '新闻内容',
    news_source VARCHAR(100) COMMENT '来源',
    news_url VARCHAR(500) COMMENT '链接',
    publish_time DATETIME COMMENT '发布时间',
    sentiment VARCHAR(10) COMMENT '情感: positive/negative/neutral',
    sentiment_strength INT COMMENT '强度 1-5',
    entities JSON COMMENT '相关实体',
    keywords JSON COMMENT '关键词',
    summary VARCHAR(500) COMMENT '一句话摘要',
    market_impact VARCHAR(500) COMMENT '市场影响',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_stock_code (stock_code),
    INDEX idx_publish_time (publish_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='新闻情感分析';

-- 事件驱动信号
CREATE TABLE IF NOT EXISTS trade_event_signal (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    trade_date DATE NOT NULL COMMENT '交易日期',
    stock_code VARCHAR(10) COMMENT '股票代码',
    stock_name VARCHAR(50) COMMENT '股票名称',
    event_type VARCHAR(20) NOT NULL COMMENT '事件类型: bullish/bearish/policy',
    event_category VARCHAR(50) NOT NULL COMMENT '事件分类: 资产重组/回购增持/业绩预增等',
    signal VARCHAR(20) COMMENT '交易信号: strong_buy/buy/hold/sell/strong_sell',
    signal_reason VARCHAR(200) COMMENT '信号理由',
    news_title VARCHAR(500) COMMENT '相关新闻标题',
    matched_keywords JSON COMMENT '匹配的关键词',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_trade_date (trade_date),
    INDEX idx_stock_code (stock_code),
    INDEX idx_event_type (event_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='事件驱动信号';

-- Polymarket 预测市场快照
CREATE TABLE IF NOT EXISTS trade_polymarket_snapshot (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    snapshot_time DATETIME NOT NULL COMMENT '快照时间',
    event_id VARCHAR(100) NOT NULL COMMENT '事件ID',
    event_title VARCHAR(500) NOT NULL COMMENT '事件标题',
    market_question VARCHAR(500) COMMENT '市场问题',
    yes_probability DECIMAL(5,2) COMMENT 'Yes 概率 %',
    volume DECIMAL(20,2) COMMENT '交易量 USD',
    is_smart_money_signal BOOLEAN DEFAULT FALSE COMMENT '是否聪明钱信号',
    category VARCHAR(50) COMMENT '分类: geopolitics/tariff/election等',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_snapshot_time (snapshot_time),
    INDEX idx_category (category)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Polymarket 预测市场快照';
```

### 3.3 核心 API 设计

| 端点 | 方法 | 功能 | 参数 |
|------|------|------|------|
| `/api/sentiment/fear-index` | GET | 获取综合恐慌/贪婪指数 | `include_ashare`: 是否包含A股指标 |
| `/api/sentiment/fear-index/history` | GET | 恐慌指数历史 | `days`: 天数 |
| `/api/sentiment/polymarket` | GET | 查询预测市场 | `keyword`, `min_volume` |
| `/api/sentiment/news` | GET | 获取个股新闻 | `stock_code`, `keywords`, `days` |
| `/api/sentiment/news/analyze` | POST | 分析新闻情感 | `news_ids[]` |
| `/api/sentiment/events` | GET | 检测重大事件 | `keywords`, `days` |
| `/api/sentiment/overview` | GET | 看板概览数据 | - |

### 3.4 核心服务实现

#### 3.4.1 恐慌指数计算 (`fear_index.py`)

```python
"""
恐慌指数服务 - 基于课程代码 market_fear_index.py
"""
import akshare as ak
import yfinance as yf
from dataclasses import dataclass
from typing import Optional
from datetime import datetime

@dataclass
class FearIndexResult:
    vix: float
    ovx: float
    gvz: float
    us10y: float
    fear_greed_score: int  # 0-100
    market_regime: str     # extreme_fear/fear/neutral/greed/extreme_greed
    vix_level: str         # 极度平静/正常/焦虑/恐慌/极度恐慌
    us10y_strategy: str    # 利率策略建议
    risk_alert: Optional[str]  # 风险传导提示
    timestamp: datetime

class FearIndexService:
    """恐慌指数服务"""
    
    # VIX 阈值
    VIX_THRESHOLDS = {
        'extreme_calm': 15,
        'normal': 20,
        'anxiety': 25,
        'fear': 35,
    }
    
    # US10Y 阈值
    US10Y_THRESHOLDS = {
        'low': 3.8,
        'watershed': 4.3,
        'high': 4.4,
    }
    
    def fetch_vix(self) -> float:
        """获取 VIX 指数"""
        ticker = yf.Ticker('^VIX')
        data = ticker.history(period='1d')
        return float(data['Close'].iloc[-1]) if not data.empty else 0.0
    
    def fetch_ovx(self) -> float:
        """获取 OVX 原油波动率"""
        ticker = yf.Ticker('^OVX')
        data = ticker.history(period='1d')
        return float(data['Close'].iloc[-1]) if not data.empty else 0.0
    
    def fetch_gvz(self) -> float:
        """获取 GVZ 黄金波动率"""
        ticker = yf.Ticker('^GVZ')
        data = ticker.history(period='1d')
        return float(data['Close'].iloc[-1]) if not data.empty else 0.0
    
    def fetch_us10y(self) -> float:
        """获取美国10年期国债收益率"""
        ticker = yf.Ticker('^TNX')
        data = ticker.history(period='1d')
        return float(data['Close'].iloc[-1]) if not data.empty else 0.0
    
    def calculate_fear_greed_score(self, vix: float, us10y: float) -> int:
        """
        计算综合恐慌/贪婪评分 (0-100)
        0 = 极度恐慌, 100 = 极度贪婪
        """
        score = 50  # 基准分
        
        # VIX 维度
        if vix < 15:
            score += 30      # 极度贪婪
        elif vix < 20:
            score += 15      # 偏贪婪
        elif vix < 25:
            score += 0       # 中性
        elif vix < 35:
            score -= 15      # 恐慌
        else:
            score -= 30      # 极度恐慌
        
        # 10年期国债维度
        if us10y < 3.8:
            score += 10      # 宽松利好
        elif us10y > 4.8:
            score -= 10      # 紧缩利空
        
        return max(0, min(100, score))
    
    def get_market_regime(self, score: int) -> str:
        """根据评分判断市场状态"""
        if score <= 20:
            return 'extreme_fear'
        elif score <= 40:
            return 'fear'
        elif score <= 60:
            return 'neutral'
        elif score <= 80:
            return 'greed'
        else:
            return 'extreme_greed'
    
    def check_risk_contagion(self, vix: float, ovx: float) -> Optional[str]:
        """
        风险传导检测
        - OVX飙升但VIX滞后 -> 风险集中在能源端
        - OVX与VIX同步共振向上 -> 地缘风险已触发流动性危机
        """
        if ovx > 50 and vix > 25:
            return 'OVX与VIX同步共振向上: 地缘风险已触发流动性危机或全球经济衰退预期，需立即风控'
        elif ovx > 50 and vix < 20:
            return 'OVX飙升但VIX滞后: 风险仍集中在能源端，尚未传导至全球宏观信用风险'
        return None
    
    def get_fear_index(self) -> FearIndexResult:
        """获取完整恐慌指数"""
        vix = self.fetch_vix()
        ovx = self.fetch_ovx()
        gvz = self.fetch_gvz()
        us10y = self.fetch_us10y()
        
        score = self.calculate_fear_greed_score(vix, us10y)
        regime = self.get_market_regime(score)
        risk_alert = self.check_risk_contagion(vix, ovx)
        
        # VIX 级别描述
        if vix < 15:
            vix_level = '极度平静(警惕自满)'
        elif vix < 20:
            vix_level = '正常'
        elif vix < 25:
            vix_level = '焦虑'
        elif vix < 35:
            vix_level = '恐慌'
        else:
            vix_level = '极度恐慌'
        
        # US10Y 策略
        if us10y > 4.4:
            us10y_strategy = '利率偏高，看好价值股和防御板块'
        elif us10y > 4.3:
            us10y_strategy = '利率处于分水岭，密切关注方向选择'
        else:
            us10y_strategy = '宽松预期，资金回流成长股'
        
        return FearIndexResult(
            vix=vix,
            ovx=ovx,
            gvz=gvz,
            us10y=us10y,
            fear_greed_score=score,
            market_regime=regime,
            vix_level=vix_level,
            us10y_strategy=us10y_strategy,
            risk_alert=risk_alert,
            timestamp=datetime.now(),
        )
```

#### 3.4.2 事件检测关键词体系

```python
# 事件关键词库 (来自课程代码)
EVENT_KEYWORDS = {
    'bullish': {
        '资产重组': ['资产重组', '重大资产', '借壳上市', '资产注入'],
        '回购增持': ['回购', '增持', '股份回购', '大股东增持'],
        '业绩预增': ['业绩预增', '业绩大增', '净利润增长', '扭亏为盈'],
        '股权激励': ['股权激励', '员工持股', '限制性股票'],
        '大额订单': ['大额订单', '重大合同', '中标'],
        '战略合作': ['战略合作', '战略协议', '合资公司'],
    },
    'bearish': {
        '股东减持': ['减持', '股东减持', '高管减持', '清仓'],
        '业绩预减': ['业绩预减', '业绩下滑', '亏损', '营收下降'],
        '违规处罚': ['违规', '处罚', '立案调查', '行政处罚'],
        '商誉减值': ['商誉减值', '资产减值'],
        '退市风险': ['退市', '*ST', '暂停上市'],
    },
    'policy': {
        '货币政策': ['降准', '降息', 'MLF', 'LPR'],
        '产业政策': ['产业政策', '扶持政策', '补贴'],
        '监管新规': ['监管', '新规', '征求意见'],
    },
}

# 事件 -> 交易信号映射
SIGNAL_MAP = {
    'bullish': {
        '资产重组': {'signal': 'strong_buy', 'reason': '资产重组可能带来基本面质变'},
        '回购增持': {'signal': 'buy', 'reason': '大股东用真金白银表达信心'},
        '业绩预增': {'signal': 'buy', 'reason': '业绩超预期增长'},
        '股权激励': {'signal': 'buy', 'reason': '管理层利益绑定'},
        '大额订单': {'signal': 'buy', 'reason': '订单驱动业绩增长'},
        '战略合作': {'signal': 'hold', 'reason': '需观察合作落地情况'},
    },
    'bearish': {
        '股东减持': {'signal': 'sell', 'reason': '内部人士减持可能释放负面信号'},
        '业绩预减': {'signal': 'sell', 'reason': '基本面恶化'},
        '违规处罚': {'signal': 'strong_sell', 'reason': '合规风险'},
        '商誉减值': {'signal': 'sell', 'reason': '资产质量下降'},
        '退市风险': {'signal': 'strong_sell', 'reason': '退市风险极高'},
    },
    'policy': {
        '货币政策': {'signal': 'hold', 'reason': '关注政策方向'},
        '产业政策': {'signal': 'hold', 'reason': '关注受益板块'},
        '监管新规': {'signal': 'hold', 'reason': '评估影响'},
    },
}
```

---

## 四、前端页面设计

### 4.1 页面布局

```
+-------------------------------------------------------------------+
|  舆情监控看板                                    [刷新] [配置]      |
+-------------------------------------------------------------------+
|  +---------------+ +---------------+ +---------------+ +---------+ |
|  | 恐慌指数 25   | | VIX 25.63    | | US10Y 4.33%  | | 事件 8  | |
|  | 极度恐慌 [!]  | | 恐慌 [!]     | | 分水岭 [~]   | | 利好 8  | |
|  +---------------+ +---------------+ +---------------+ +---------+ |
+-------------------------------------------------------------------+
|  [宏观指数] [预测市场] [个股舆情] [事件信号]                        |
+-------------------------------------------------------------------+
|                                                                    |
|  +-- 宏观恐慌指数 -----------------------------------------------+ |
|  |  综合评分: 25/100 (极度恐慌)                                   | |
|  |  建议: 市场极度恐慌，历史上往往是中长期买入良机                 | |
|  |                                                                | |
|  |  +----------+ +----------+ +----------+ +----------+           | |
|  |  | VIX      | | OVX      | | GVZ      | | US10Y    |           | |
|  |  | 25.63    | | 96.14    | | 37.04    | | 4.337%   |           | |
|  |  | 恐慌 [!] | | 高波动[!]| | 避险 [~] | | 分水岭   |           | |
|  |  +----------+ +----------+ +----------+ +----------+           | |
|  |                                                                | |
|  |  [!] 风险传导: OVX与VIX同步共振向上 -> 需立即风控              | |
|  +----------------------------------------------------------------+ |
|                                                                    |
|  +-- 预测市场 (Polymarket) --------------------------------------+ |
|  |  关键词: [tariff] [China] [Iran] [+添加]                       | |
|  |                                                                | |
|  |  [i] Will tariffs increase? - Yes: 72% | $1.2M                | |
|  |  [i] China invades Taiwan? - Yes: 52.5% | $1.8M               | |
|  |  ...                                                           | |
|  |                                                                | |
|  |  [!] 聪明钱信号: 检测到 41 个高置信度信号                      | |
|  +----------------------------------------------------------------+ |
|                                                                    |
|  +-- 个股舆情 ---------------------------------------------------+ |
|  |  股票代码: [002594] 比亚迪  [搜索]  最近 [7] 天                | |
|  |                                                                | |
|  |  情绪指数: 50/100 (中性)                                       | |
|  |  正面: 2 | 负面: 2 | 中性: 1                                   | |
|  |                                                                | |
|  |  [+] 比亚迪2025年报亮眼，营收8040亿 [正面 5]                   | |
|  |  [-] 汽车行业资金流出榜 [负面 3]                               | |
|  |  ...                                                           | |
|  +----------------------------------------------------------------+ |
|                                                                    |
|  +-- 事件驱动信号 -----------------------------------------------+ |
|  |  关键词: [资产重组] [回购] [业绩预增] [+添加]                  | |
|  |                                                                | |
|  |  [>>] [利好] 资产重组 -> 强烈关注                              | |
|  |       亿纬锂能(300067) 50GWh储能电池基地                       | |
|  |                                                                | |
|  |  [>>] [利好] 资产重组 -> 强烈关注                              | |
|  |       长源东谷(603950) 重大资产重组                            | |
|  |                                                                | |
|  |  统计: 利好 8 | 利空 0 | 政策 0                                | |
|  +----------------------------------------------------------------+ |
+-------------------------------------------------------------------+
```

### 4.2 前端组件结构

```
web/src/app/sentiment/
+-- page.tsx                      # 主页面
+-- layout.tsx                    # 布局
+-- components/
    +-- OverviewCards.tsx         # 概览卡片组
    +-- FearIndexPanel.tsx        # 恐慌指数面板
    +-- PolymarketPanel.tsx       # 预测市场面板
    +-- NewsSentimentPanel.tsx    # 新闻舆情面板
    +-- EventSignalPanel.tsx      # 事件信号面板
    +-- FearGauge.tsx             # 恐慌仪表盘组件
    +-- SentimentBadge.tsx        # 情感标签组件
```

---

## 五、任务调度集成

### 5.1 新增任务定义 (`tasks/07_sentiment.yaml`)

```yaml
# 舆情监控任务
# 每日收盘后自动执行

tasks:
  # 恐慌指数更新 (每日 16:30)
  update_fear_index:
    name: "更新恐慌指数"
    module: data_analyst.sentiment.run_monitor
    function: update_fear_index
    schedule: "30 16 * * 1-5"  # 周一到周五 16:30
    tags: [daily, sentiment]
    timeout: 300
    retry: 2
    
  # 新闻舆情扫描 (每日 17:00)
  scan_news_sentiment:
    name: "新闻舆情扫描"
    module: data_analyst.sentiment.run_monitor
    function: scan_news_sentiment
    schedule: "0 17 * * 1-5"
    tags: [daily, sentiment]
    timeout: 600
    retry: 2
    depends_on: [update_fear_index]
    
  # 事件信号检测 (每日 17:30)
  detect_event_signals:
    name: "事件信号检测"
    module: data_analyst.sentiment.run_monitor
    function: detect_event_signals
    schedule: "30 17 * * 1-5"
    tags: [daily, sentiment]
    timeout: 300
    retry: 2
    depends_on: [scan_news_sentiment]
    
  # Polymarket 快照 (每4小时)
  snapshot_polymarket:
    name: "Polymarket 快照"
    module: data_analyst.sentiment.run_monitor
    function: snapshot_polymarket
    schedule: "0 */4 * * *"  # 每4小时
    tags: [hourly, sentiment]
    timeout: 300
    retry: 2
```

### 5.2 CLI 命令

```bash
# 手动执行恐慌指数更新
python -m data_analyst.sentiment.run_monitor --task fear-index

# 手动执行新闻舆情扫描
python -m data_analyst.sentiment.run_monitor --task news --stock 002594 --days 7

# 手动执行事件检测
python -m data_analyst.sentiment.run_monitor --task events --keywords "资产重组,回购" --days 3

# 手动执行 Polymarket 快照
python -m data_analyst.sentiment.run_monitor --task polymarket --keyword "tariff"

# 查看任务状态
python -m scheduler status update_fear_index
```

---

## 六、依赖管理

### 6.1 新增 Python 依赖

```txt
# requirements.txt 新增
akshare>=1.14.0        # 东方财富数据
yfinance>=0.2.40       # Yahoo Finance 数据
httpx>=0.27.0          # Polymarket API 异步请求
```

### 6.2 环境变量

```bash
# .env 新增 (可选)
# LLM 情感分析使用现有 DASHSCOPE_API_KEY
# Polymarket API 无需认证
```

---

## 七、与现有系统集成点

| 现有模块 | 集成方式 |
|---------|---------|
| `investment_rag/embeddings/` | 复用 LLMClient 进行情感分析 |
| `config/db.py` | 复用数据库连接 |
| `scheduler/` | 添加舆情任务到 DAG |
| `api/middleware/` | 复用认证、限流中间件 |
| `web/src/lib/` | 复用 API client、auth |
| `strategist/tech_scan/` | 可联动生成综合报告 |

---

## 八、实施步骤

### Phase 1: 后端核心模块 (2-3天)

1. 创建 `data_analyst/sentiment/` 目录结构
2. 实现 `fear_index.py` - 恐慌指数服务
3. 实现 `news_fetcher.py` - 新闻获取服务
4. 实现 `sentiment_analyzer.py` - LLM 情感分析
5. 实现 `event_detector.py` - 事件检测
6. 实现 `polymarket.py` - 预测市场服务
7. 实现 `storage.py` - 数据库读写
8. 创建数据库表

### Phase 2: API 路由 (1天)

1. 创建 `api/routers/sentiment.py`
2. 创建 `api/schemas/sentiment.py`
3. 注册路由到 `api/main.py`
4. 添加 Redis 缓存

### Phase 3: 前端页面 (2-3天)

1. 创建 `web/src/app/sentiment/page.tsx`
2. 实现各子组件
3. 添加导航入口
4. 样式调整

### Phase 4: 任务调度 (0.5天)

1. 创建 `tasks/07_sentiment.yaml`
2. 实现 `run_monitor.py` CLI
3. 测试定时任务

### Phase 5: 测试与文档 (1天)

1. 单元测试
2. 集成测试
3. 更新 CLAUDE.md

---

## 九、预期效果

1. **宏观风险监控**: 每日自动更新 VIX/OVX/GVZ/US10Y，生成综合恐慌/贪婪评分
2. **预测市场监控**: 实时跟踪 Polymarket 地缘政治事件概率，检测聪明钱信号
3. **个股舆情分析**: 支持按股票代码或关键词搜索新闻，LLM 自动分析情感
4. **事件驱动信号**: 自动检测资产重组、回购增持等重大事件，生成交易信号
5. **多维决策支持**: 宏观 + 微观 + 前瞻三层分析，辅助投资决策

---

## 十、参考资料

- 课程代码: `/Users/zhaobo/data0/person/quant/课程代码-20260408/CASE-AI量化助手（nanobot）/skills/sentiment-analysis/`
- 课程文档: `/Users/zhaobo/data0/person/quant/舆情感知与事件驱动.md`
- Polymarket API: `https://gamma-api.polymarket.com`
- akshare 文档: `https://akshare.akfamily.xyz/`
- yfinance 文档: `https://pypi.org/project/yfinance/`

---

## 十一、详细任务拆解与验证计划

> 每个任务包含：开发内容、单元测试、验证步骤、完成标准

### Phase 1: 后端核心模块 (预计 2-3 天)

#### T1.1 创建模块目录结构

**开发内容**:
```bash
mkdir -p data_analyst/sentiment
touch data_analyst/sentiment/__init__.py
touch data_analyst/sentiment/config.py
touch data_analyst/sentiment/schemas.py
```

**验证步骤**:
```bash
# 验证模块可导入
python -c "from data_analyst.sentiment import config; print('OK')"
```

**完成标准**: 模块目录创建完成，`__init__.py` 存在，可正常 import

---

#### T1.2 实现配置模块 (`config.py`)

**开发内容**:
- VIX/US10Y 阈值配置
- 事件关键词库配置
- 信号映射配置
- 数据源配置（akshare/yfinance/Polymarket）

**单元测试** (`tests/unit/sentiment/test_config.py`):
```python
def test_vix_thresholds_valid():
    """VIX 阈值配置有效"""
    from data_analyst.sentiment.config import VIX_THRESHOLDS
    assert VIX_THRESHOLDS['extreme_calm'] < VIX_THRESHOLDS['normal']
    assert VIX_THRESHOLDS['normal'] < VIX_THRESHOLDS['anxiety']

def test_event_keywords_not_empty():
    """事件关键词库非空"""
    from data_analyst.sentiment.config import EVENT_KEYWORDS
    assert len(EVENT_KEYWORDS['bullish']) > 0
    assert len(EVENT_KEYWORDS['bearish']) > 0
```

**验证步骤**:
```bash
pytest tests/unit/sentiment/test_config.py -v
```

**完成标准**: 配置加载正常，单测通过

---

#### T1.3 实现数据模型 (`schemas.py`)

**开发内容**:
- `FearIndexResult` dataclass
- `NewsItem` dataclass
- `SentimentResult` dataclass
- `EventSignal` dataclass
- `PolymarketEvent` dataclass

**单元测试** (`tests/unit/sentiment/test_schemas.py`):
```python
def test_fear_index_result_creation():
    """FearIndexResult 创建正常"""
    from data_analyst.sentiment.schemas import FearIndexResult
    result = FearIndexResult(
        vix=25.0, ovx=50.0, gvz=20.0, us10y=4.3,
        fear_greed_score=35, market_regime='fear',
        vix_level='恐慌', us10y_strategy='分水岭',
        risk_alert=None, timestamp=datetime.now()
    )
    assert result.fear_greed_score == 35

def test_event_signal_to_dict():
    """EventSignal 可序列化"""
    from data_analyst.sentiment.schemas import EventSignal
    signal = EventSignal(...)
    assert isinstance(signal.to_dict(), dict)
```

**验证步骤**:
```bash
pytest tests/unit/sentiment/test_schemas.py -v
```

**完成标准**: 所有数据模型可正常创建和序列化

---

#### T1.4 实现恐慌指数服务 (`fear_index.py`)

**开发内容**:
- `FearIndexService` 类
- `fetch_vix()` / `fetch_ovx()` / `fetch_gvz()` / `fetch_us10y()`
- `calculate_fear_greed_score()`
- `get_market_regime()`
- `check_risk_contagion()`
- `get_fear_index()` 主入口

**单元测试** (`tests/unit/sentiment/test_fear_index.py`):
```python
def test_calculate_fear_greed_score_extreme_fear():
    """VIX > 35 应返回极度恐慌"""
    service = FearIndexService()
    score = service.calculate_fear_greed_score(vix=40, us10y=4.5)
    assert score <= 20  # extreme_fear

def test_calculate_fear_greed_score_extreme_greed():
    """VIX < 15 应返回极度贪婪"""
    service = FearIndexService()
    score = service.calculate_fear_greed_score(vix=12, us10y=3.5)
    assert score >= 80  # extreme_greed

def test_get_market_regime():
    """市场状态判断正确"""
    service = FearIndexService()
    assert service.get_market_regime(15) == 'extreme_fear'
    assert service.get_market_regime(50) == 'neutral'
    assert service.get_market_regime(85) == 'extreme_greed'

def test_check_risk_contagion_both_high():
    """OVX 和 VIX 同时高应触发警报"""
    service = FearIndexService()
    alert = service.check_risk_contagion(vix=30, ovx=60)
    assert alert is not None
    assert '流动性危机' in alert

@pytest.mark.integration
def test_fetch_vix_real():
    """实际获取 VIX 数据（需网络）"""
    service = FearIndexService()
    vix = service.fetch_vix()
    assert vix > 0
```

**验证步骤**:
```bash
# 单元测试（不含网络请求）
pytest tests/unit/sentiment/test_fear_index.py -v -m "not integration"

# 集成测试（含网络请求）
pytest tests/unit/sentiment/test_fear_index.py -v -m integration
```

**完成标准**: 评分计算逻辑正确，网络请求可获取数据

---

#### T1.5 实现新闻获取服务 (`news_fetcher.py`)

**开发内容**:
- `NewsFetcher` 类
- `fetch_stock_news(stock_code, days)` - 获取个股新闻
- `fetch_keyword_news(keywords, days)` - 按关键词获取新闻
- `filter_by_keywords(news_list, keywords)` - 关键词过滤

**单元测试** (`tests/unit/sentiment/test_news_fetcher.py`):
```python
def test_filter_by_keywords():
    """关键词过滤正确"""
    fetcher = NewsFetcher()
    news = [
        {'title': '比亚迪资产重组公告'},
        {'title': '今日大盘走势'},
    ]
    filtered = fetcher.filter_by_keywords(news, ['资产重组'])
    assert len(filtered) == 1
    assert '资产重组' in filtered[0]['title']

@pytest.mark.integration
def test_fetch_stock_news_real():
    """实际获取个股新闻（需网络）"""
    fetcher = NewsFetcher()
    news = fetcher.fetch_stock_news('002594', days=3)
    assert isinstance(news, list)
```

**验证步骤**:
```bash
pytest tests/unit/sentiment/test_news_fetcher.py -v
```

**完成标准**: 新闻获取和过滤逻辑正确

---

#### T1.6 实现 LLM 情感分析 (`sentiment_analyzer.py`)

**开发内容**:
- `SentimentAnalyzer` 类
- `analyze_single(news_item)` - 单条新闻分析
- `analyze_batch(news_list)` - 批量分析
- `build_prompt(news)` - 构建 Prompt
- `parse_response(response)` - 解析 LLM 响应

**单元测试** (`tests/unit/sentiment/test_sentiment_analyzer.py`):
```python
def test_build_prompt():
    """Prompt 构建正确"""
    analyzer = SentimentAnalyzer()
    prompt = analyzer.build_prompt({'title': '比亚迪业绩大增', 'content': '...'})
    assert '情感分析' in prompt or 'sentiment' in prompt.lower()

def test_parse_response_positive():
    """解析正面情感响应"""
    analyzer = SentimentAnalyzer()
    mock_response = '{"sentiment": "positive", "strength": 4, "summary": "业绩利好"}'
    result = analyzer.parse_response(mock_response)
    assert result['sentiment'] == 'positive'
    assert result['strength'] == 4

def test_parse_response_invalid():
    """解析无效响应应返回中性"""
    analyzer = SentimentAnalyzer()
    result = analyzer.parse_response('invalid json')
    assert result['sentiment'] == 'neutral'

@pytest.mark.integration
def test_analyze_single_real():
    """实际调用 LLM 分析（需 API Key）"""
    analyzer = SentimentAnalyzer()
    result = analyzer.analyze_single({
        'title': '比亚迪2025年报亮眼，营收突破8000亿',
        'content': '比亚迪发布年报，营收同比增长30%...'
    })
    assert result['sentiment'] in ['positive', 'negative', 'neutral']
```

**验证步骤**:
```bash
pytest tests/unit/sentiment/test_sentiment_analyzer.py -v -m "not integration"
```

**完成标准**: Prompt 构建正确，响应解析健壮

---

#### T1.7 实现事件检测 (`event_detector.py`)

**开发内容**:
- `EventDetector` 类
- `detect_events(news_list)` - 检测事件
- `match_keywords(text, keywords)` - 关键词匹配
- `generate_signal(event_type, category)` - 生成交易信号

**单元测试** (`tests/unit/sentiment/test_event_detector.py`):
```python
def test_match_keywords_bullish():
    """匹配利好关键词"""
    detector = EventDetector()
    matches = detector.match_keywords('公司发布资产重组公告', 'bullish')
    assert '资产重组' in matches

def test_generate_signal_strong_buy():
    """资产重组应生成强烈买入信号"""
    detector = EventDetector()
    signal = detector.generate_signal('bullish', '资产重组')
    assert signal['signal'] == 'strong_buy'

def test_detect_events():
    """事件检测完整流程"""
    detector = EventDetector()
    news = [
        {'title': '某公司重大资产重组', 'stock_code': '000001'},
        {'title': '今日天气晴朗', 'stock_code': None},
    ]
    events = detector.detect_events(news)
    assert len(events) == 1
    assert events[0]['event_type'] == 'bullish'
```

**验证步骤**:
```bash
pytest tests/unit/sentiment/test_event_detector.py -v
```

**完成标准**: 事件检测和信号生成逻辑正确

---

#### T1.8 实现 Polymarket 服务 (`polymarket.py`)

**开发内容**:
- `PolymarketService` 类
- `search_markets(keyword)` - 搜索市场
- `get_market_details(market_id)` - 获取市场详情
- `detect_smart_money_signals()` - 检测聪明钱信号

**单元测试** (`tests/unit/sentiment/test_polymarket.py`):
```python
def test_parse_market_response():
    """解析市场响应"""
    service = PolymarketService()
    mock_data = {
        'id': '123',
        'question': 'Will tariffs increase?',
        'outcomePrices': '[0.72, 0.28]',
        'volume': '1200000'
    }
    result = service.parse_market(mock_data)
    assert result['yes_probability'] == 72.0
    assert result['volume'] == 1200000

@pytest.mark.integration
def test_search_markets_real():
    """实际搜索市场（需网络）"""
    service = PolymarketService()
    markets = service.search_markets('tariff', min_volume=100000)
    assert isinstance(markets, list)
```

**验证步骤**:
```bash
pytest tests/unit/sentiment/test_polymarket.py -v
```

**完成标准**: API 调用和数据解析正确

---

#### T1.9 实现数据库存储 (`storage.py`)

**开发内容**:
- `SentimentStorage` 类
- `save_fear_index(result)` - 保存恐慌指数
- `get_fear_index_history(days)` - 获取历史
- `save_news_sentiment(items)` - 保存新闻情感
- `save_event_signals(signals)` - 保存事件信号
- `save_polymarket_snapshot(events)` - 保存预测市场快照

**单元测试** (`tests/unit/sentiment/test_storage.py`):
```python
@pytest.fixture
def test_db():
    """使用测试数据库"""
    # 使用 local 环境或 mock
    pass

def test_save_and_get_fear_index(test_db):
    """保存和读取恐慌指数"""
    storage = SentimentStorage()
    result = FearIndexResult(...)
    storage.save_fear_index(result)
    history = storage.get_fear_index_history(days=1)
    assert len(history) >= 1
```

**验证步骤**:
```bash
# 需要数据库环境
DB_ENV=local pytest tests/unit/sentiment/test_storage.py -v
```

**完成标准**: 数据库 CRUD 正常

---

#### T1.10 创建数据库表

**开发内容**:
- 创建 Alembic 迁移脚本
- 4 张表: `trade_fear_index`, `trade_news_sentiment`, `trade_event_signal`, `trade_polymarket_snapshot`

**验证步骤**:
```bash
# 创建迁移
make migrate-create msg="add sentiment tables"

# 执行迁移
make migrate

# 验证表存在
python -c "
from config.db import execute_query
result = execute_query('SHOW TABLES LIKE \'trade_fear_index\'', env='local')
print('OK' if result else 'FAIL')
"
```

**完成标准**: 4 张表创建成功

---

#### T1.11 实现 CLI 入口 (`run_monitor.py`)

**开发内容**:
- `argparse` 命令行参数
- `--task` 选择任务类型
- `--stock` / `--keywords` / `--days` 参数
- 各任务执行函数

**验证步骤**:
```bash
# 帮助信息
python -m data_analyst.sentiment.run_monitor --help

# dry-run 测试
python -m data_analyst.sentiment.run_monitor --task fear-index --dry-run
```

**完成标准**: CLI 可正常执行各任务

---

### Phase 2: API 路由 (预计 1 天)

#### T2.1 创建 API Schema (`api/schemas/sentiment.py`)

**开发内容**:
- `FearIndexResponse` - 恐慌指数响应
- `NewsListResponse` - 新闻列表响应
- `EventListResponse` - 事件列表响应
- `PolymarketResponse` - 预测市场响应
- `OverviewResponse` - 概览响应

**单元测试**:
```python
def test_fear_index_response_serialization():
    """响应模型可序列化"""
    response = FearIndexResponse(
        vix=25.0, ovx=50.0, gvz=20.0, us10y=4.3,
        fear_greed_score=35, market_regime='fear',
        ...
    )
    assert response.model_dump() is not None
```

**完成标准**: 所有响应模型定义完成

---

#### T2.2 实现 API 路由 (`api/routers/sentiment.py`)

**开发内容**:
- `GET /api/sentiment/fear-index`
- `GET /api/sentiment/fear-index/history`
- `GET /api/sentiment/polymarket`
- `GET /api/sentiment/news`
- `POST /api/sentiment/news/analyze`
- `GET /api/sentiment/events`
- `GET /api/sentiment/overview`

**单元测试** (`tests/unit/api/test_sentiment_router.py`):
```python
from fastapi.testclient import TestClient

def test_get_fear_index(client: TestClient):
    """获取恐慌指数"""
    response = client.get('/api/sentiment/fear-index')
    assert response.status_code == 200
    data = response.json()
    assert 'vix' in data
    assert 'fear_greed_score' in data

def test_get_news_with_stock_code(client: TestClient):
    """按股票代码获取新闻"""
    response = client.get('/api/sentiment/news?stock_code=002594&days=3')
    assert response.status_code == 200

def test_get_events(client: TestClient):
    """获取事件信号"""
    response = client.get('/api/sentiment/events?days=3')
    assert response.status_code == 200
```

**验证步骤**:
```bash
# 启动 API 服务
make api-local &

# 测试端点
curl http://localhost:8000/api/sentiment/fear-index | jq
curl http://localhost:8000/api/sentiment/overview | jq

# 运行 API 测试
pytest tests/unit/api/test_sentiment_router.py -v
```

**完成标准**: 所有 API 端点可正常访问

---

#### T2.3 注册路由到 main.py

**开发内容**:
- 在 `api/main.py` 中 import 并注册 sentiment router

**验证步骤**:
```bash
# 检查路由注册
curl http://localhost:8000/docs | grep sentiment
```

**完成标准**: `/docs` 中可见 sentiment 相关端点

---

#### T2.4 添加 Redis 缓存

**开发内容**:
- 恐慌指数缓存 5 分钟
- 新闻列表缓存 10 分钟

**验证步骤**:
```bash
# 第一次请求
time curl http://localhost:8000/api/sentiment/fear-index

# 第二次请求（应更快）
time curl http://localhost:8000/api/sentiment/fear-index
```

**完成标准**: 缓存生效，重复请求响应更快

---

### Phase 3: 前端页面 (预计 2-3 天)

#### T3.1 创建页面结构

**开发内容**:
```bash
mkdir -p web/src/app/sentiment/components
touch web/src/app/sentiment/page.tsx
touch web/src/app/sentiment/layout.tsx
```

**验证步骤**:
```bash
cd web && npm run build
```

**完成标准**: 页面可正常编译

---

#### T3.2 实现概览卡片组件 (`OverviewCards.tsx`)

**开发内容**:
- 恐慌指数卡片
- VIX 卡片
- US10Y 卡片
- 事件数量卡片

**验证步骤**:
```bash
cd web && npm run dev
# 访问 http://localhost:3000/sentiment
```

**完成标准**: 4 个概览卡片正常显示

---

#### T3.3 实现恐慌指数面板 (`FearIndexPanel.tsx`)

**开发内容**:
- 综合评分展示
- VIX/OVX/GVZ/US10Y 指标卡片
- 风险传导提示
- 操作建议

**完成标准**: 恐慌指数面板数据正确展示

---

#### T3.4 实现预测市场面板 (`PolymarketPanel.tsx`)

**开发内容**:
- 关键词筛选
- 市场列表
- 概率和交易量展示
- 聪明钱信号提示

**完成标准**: Polymarket 数据正确展示

---

#### T3.5 实现新闻舆情面板 (`NewsSentimentPanel.tsx`)

**开发内容**:
- 股票代码搜索
- 新闻列表
- 情感标签
- 情绪指数统计

**完成标准**: 新闻列表和情感分析正确展示

---

#### T3.6 实现事件信号面板 (`EventSignalPanel.tsx`)

**开发内容**:
- 关键词筛选
- 事件列表
- 信号标签
- 统计汇总

**完成标准**: 事件信号正确展示

---

#### T3.7 添加导航入口

**开发内容**:
- 在侧边栏添加"舆情监控"入口
- 路由配置

**验证步骤**:
```bash
# 访问 http://localhost:3000
# 点击侧边栏"舆情监控"
```

**完成标准**: 可从侧边栏进入舆情监控页面

---

### Phase 4: 任务调度 (预计 0.5 天)

#### T4.1 创建任务定义 (`tasks/07_sentiment.yaml`)

**开发内容**:
- 4 个定时任务定义
- 依赖关系配置

**验证步骤**:
```bash
python -m scheduler list --tag sentiment
```

**完成标准**: 任务列表中可见 4 个 sentiment 任务

---

#### T4.2 测试定时任务

**验证步骤**:
```bash
# dry-run 测试
python -m scheduler run update_fear_index --dry-run
python -m scheduler run scan_news_sentiment --dry-run

# 实际执行
python -m scheduler run update_fear_index
```

**完成标准**: 任务可正常执行

---

### Phase 5: 测试与文档 (预计 1 天)

#### T5.1 单元测试汇总

**验证步骤**:
```bash
# 运行所有 sentiment 相关单测
pytest tests/unit/sentiment/ -v --cov=data_analyst.sentiment --cov-report=term-missing

# 覆盖率要求 >= 80%
```

**完成标准**: 单测覆盖率 >= 80%

---

#### T5.2 集成测试

**测试场景**:

1. **端到端恐慌指数流程**:
   - 调用 `FearIndexService.get_fear_index()`
   - 保存到数据库
   - 通过 API 获取
   - 前端展示

2. **端到端新闻分析流程**:
   - 获取新闻
   - LLM 情感分析
   - 事件检测
   - 保存到数据库
   - 通过 API 获取

3. **定时任务流程**:
   - 执行 scheduler 任务
   - 验证数据库更新

**验证步骤**:
```bash
# 集成测试
pytest tests/integration/test_sentiment_e2e.py -v

# E2E 测试（需 Playwright）
npx playwright test tests/e2e/sentiment.spec.ts
```

**完成标准**: 所有集成测试通过

---

#### T5.3 更新 CLAUDE.md

**开发内容**:
- 添加 sentiment 模块说明
- 添加 CLI 命令示例
- 添加 API 端点列表

**完成标准**: CLAUDE.md 更新完成

---

## 十二、Code Review Checklist

### 代码质量

- [ ] 遵循项目代码规范（无 emoji、import 规范等）
- [ ] 所有函数有 docstring
- [ ] 类型注解完整
- [ ] 错误处理完善（try-except）
- [ ] 日志记录规范

### 安全性

- [ ] 无硬编码敏感信息
- [ ] API 端点有认证保护
- [ ] 输入参数有校验
- [ ] SQL 使用参数化查询

### 性能

- [ ] 数据库查询有索引
- [ ] 热点数据有缓存
- [ ] 批量操作使用 batch insert
- [ ] 网络请求有超时设置

### 测试

- [ ] 单测覆盖率 >= 80%
- [ ] 关键路径有集成测试
- [ ] 边界条件有测试
- [ ] Mock 外部依赖

### 文档

- [ ] README 更新
- [ ] CLAUDE.md 更新
- [ ] API 文档完整
- [ ] 配置说明完整

---

## 十三、集成测试计划

### 测试环境

- **数据库**: local MySQL
- **Redis**: local Redis
- **LLM**: DashScope API (需 DASHSCOPE_API_KEY)
- **外部 API**: yfinance, akshare, Polymarket

### 测试数据准备

```sql
-- 清理测试数据
DELETE FROM trade_fear_index WHERE trade_date >= '2026-04-01';
DELETE FROM trade_news_sentiment WHERE created_at >= '2026-04-01';
DELETE FROM trade_event_signal WHERE trade_date >= '2026-04-01';
DELETE FROM trade_polymarket_snapshot WHERE snapshot_time >= '2026-04-01';
```

### 测试用例

| ID | 场景 | 步骤 | 预期结果 |
|----|------|------|----------|
| IT-01 | 恐慌指数获取 | 调用 API `/api/sentiment/fear-index` | 返回 VIX/OVX/GVZ/US10Y 数据 |
| IT-02 | 恐慌指数历史 | 调用 API `/api/sentiment/fear-index/history?days=7` | 返回 7 天历史数据 |
| IT-03 | 新闻获取 | 调用 API `/api/sentiment/news?stock_code=002594&days=3` | 返回比亚迪近 3 天新闻 |
| IT-04 | 新闻情感分析 | POST `/api/sentiment/news/analyze` | 返回情感分析结果 |
| IT-05 | 事件检测 | 调用 API `/api/sentiment/events?keywords=资产重组&days=3` | 返回资产重组事件 |
| IT-06 | Polymarket 查询 | 调用 API `/api/sentiment/polymarket?keyword=tariff` | 返回关税相关市场 |
| IT-07 | 概览数据 | 调用 API `/api/sentiment/overview` | 返回汇总数据 |
| IT-08 | 定时任务执行 | 执行 `python -m scheduler run update_fear_index` | 数据库新增记录 |
| IT-09 | 前端页面加载 | 访问 `/sentiment` | 页面正常渲染 |
| IT-10 | 前端数据刷新 | 点击刷新按钮 | 数据更新 |

### 回归测试

- [ ] 现有 API 端点正常
- [ ] 现有前端页面正常
- [ ] 现有定时任务正常
- [ ] 数据库迁移无影响

---

## 十四、上线 Checklist

### 上线前

- [ ] 所有单测通过
- [ ] 所有集成测试通过
- [ ] Code Review 完成
- [ ] 文档更新完成
- [ ] 数据库迁移脚本准备
- [ ] 依赖更新 (requirements.txt)

### 上线步骤

1. 合并 PR 到 main
2. 执行数据库迁移
3. 部署后端服务
4. 部署前端服务
5. 验证功能正常

### 上线后

- [ ] 监控 API 错误率
- [ ] 监控定时任务执行
- [ ] 验证数据正确性
- [ ] 收集用户反馈
