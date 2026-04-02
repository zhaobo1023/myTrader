# -*- coding: utf-8 -*-
"""financial fetcher config"""

from dataclasses import dataclass, field
from typing import Dict

DEFAULT_WATCH_LIST: Dict[str, str] = {
    "600015": "华夏银行",
    "600036": "招商银行",
    "601288": "农业银行",
    "600016": "民生银行",
    "601166": "兴业银行",
    "601169": "北京银行",
    "600919": "江苏银行",
    "002142": "宁波银行",
    "601088": "中国神华",
    "600188": "兖矿能源",
}

REQUEST_INTERVAL = 1.5


@dataclass
class FinancialFetcherConfig:
    """config for financial fetcher"""
    watch_list: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_WATCH_LIST))
    db_env: str = "online"
    request_interval: float = REQUEST_INTERVAL
    output_dir: str = "/Users/zhaobo/Documents/notes/Finance/Output/financials"
    pdf_output_dir: str = "output/annual_reports"
    rag_collection: str = "financials"
