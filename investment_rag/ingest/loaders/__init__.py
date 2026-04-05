# -*- coding: utf-8 -*-
"""
Data loaders for investment_rag ingest pipeline.

AKShareLoader: financial summary data from AKShare (ROE/gross margin/growth rates).
"""
from .akshare_loader import AKShareLoader

__all__ = ["AKShareLoader"]
