# -*- coding: utf-8 -*-
"""log_bias config"""

from dataclasses import dataclass
from dataclasses import field
from typing import Dict

# -- CSI thematic indices (中证行业主题指数) --
# Data source: ak.stock_zh_index_hist_csindex (中证指数官网)
# Fallback:    ak.stock_zh_index_daily_em     (东财 app 接口, 399xxx only)
DEFAULT_CSI_INDICES: Dict[str, str] = {
    # tech / growth
    '931840': '卫星产业',
    '930713': '人工智能',
    '931719': 'CS电池',
    '930997': 'CS新能源车',
    '931865': '半导体',
    '930851': '云计算',
    '930843': '机器人产业',
    '931160': '电网设备主题',
    '931862': '中证半导',
    '930782': '半导体材料设备',
    '931151': '光伏产业',
    '930766': '软件指数',
    '931587': '金融科技',
    '930899': '动漫游戏',
    # consumer / pharma
    '399997': '中证白酒',
    '930697': '家用电器',
    '930901': '中证影视',
    '931508': '科创新药',
    '930633': '中证旅游',
    # cyclical / resources
    '399967': '中证军工',
    '930598': '稀土产业',
    '930708': '有色金属',
    '399998': '中证煤炭',
    '000813': '细分化工',
    '930707': '中证畜牧',
    '930706': '建筑材料',
    # finance / real estate
    '399986': '中证银行',
    '399975': '证券公司',
    '931775': '房地产',
}


DEFAULT_ETFS: Dict[str, str] = {
    # tech growth
    '159995.SZ': '芯片ETF',
    '515050.SH': '5G ETF',
    '516160.SH': '新能源车ETF',
    '515790.SH': '光伏ETF',
    '159941.SZ': '纳指ETF',
    # consumer & pharma
    '512690.SH': '白酒ETF',
    '512010.SH': '医药ETF',
    # cyclical & finance
    '512880.SH': '券商ETF',
    '515220.SH': '煤炭ETF',
    '518880.SH': '黄金ETF',
    # broad base
    '510300.SH': '沪深300ETF',
    '588000.SH': '科创50ETF',
}

OVERHEAT_THRESHOLD = 15.0
BREAKOUT_THRESHOLD = 5.0
STALL_THRESHOLD = -5.0
COOLDOWN_DAYS = 10
EMA_WINDOW = 20


@dataclass
class LogBiasConfig:
    """config for log bias module"""
    etfs: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_ETFS))
    csi_indices: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_CSI_INDICES))
    ema_window: int = EMA_WINDOW
    overheat_threshold: float = OVERHEAT_THRESHOLD
    breakout_threshold: float = BREAKOUT_THRESHOLD
    stall_threshold: float = STALL_THRESHOLD
    cooldown_days: int = COOLDOWN_DAYS
    lookback_days: int = 400
    multi_day_window: int = 10
    output_dir: str = '/Users/zhaobo/Documents/notes/Finance/Output'
    log_dir: str = 'output/log_bias'
    db_env: str = 'online'
