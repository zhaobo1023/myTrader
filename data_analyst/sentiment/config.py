"""
Sentiment Analysis Configuration

配置参数：
- VIX/US10Y 阈值
- 事件关键词库
- 信号映射
- 数据源配置
"""

# VIX 恐慌指数阈值
VIX_THRESHOLDS = {
    'extreme_calm': 15,
    'normal': 20,
    'anxiety': 25,
    'fear': 35,
}

# US10Y 国债收益率阈值
US10Y_THRESHOLDS = {
    'low': 3.8,
    'watershed': 4.3,
    'high': 4.4,
}

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

# 数据源配置
DATA_SOURCE_CONFIG = {
    'yfinance': {
        'vix_ticker': '^VIX',
        'ovx_ticker': '^OVX',
        'gvz_ticker': '^GVZ',
        'us10y_ticker': '^TNX',
        'timeout': 10,
    },
    'polymarket': {
        'base_url': 'https://gamma-api.polymarket.com',
        'timeout': 10,
    },
}
