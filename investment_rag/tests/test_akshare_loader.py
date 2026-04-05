# -*- coding: utf-8 -*-
import pytest
import pandas as pd
from unittest.mock import patch, MagicMock
from investment_rag.ingest.loaders.akshare_loader import AKShareLoader


def test_format_summary_returns_string():
    loader = AKShareLoader()
    data = {"records": [{"report_period": "2024Q3", "ROE": 25.3}], "columns": ["report_period", "ROE"]}
    result = loader._format_summary(data, stock_code="000858", years=1)
    assert isinstance(result, str)
    assert "000858" in result
    assert "ROE" in result


def test_get_financial_data_returns_expected_keys():
    loader = AKShareLoader()
    with patch.object(loader, "_fetch_financial_abstract") as mock_fetch:
        mock_fetch.return_value = {
            "records": [{"report_period": "2024Q3", "ROE": 25.3}],
            "columns": ["report_period", "ROE"],
        }
        result = loader.get_financial_data("000858", years=1)
    assert "raw" in result
    assert "summary" in result
    assert "error" in result
    assert result["error"] is None
    assert "000858" in result["summary"]


def test_get_financial_data_handles_network_error():
    loader = AKShareLoader()
    with patch.object(loader, "_fetch_financial_abstract", side_effect=Exception("timeout")):
        result = loader.get_financial_data("000858", years=1)
    assert result["summary"] == ""
    assert result["error"] is not None


def test_format_summary_empty_data():
    loader = AKShareLoader()
    result = loader._format_summary({}, stock_code="000858")
    assert isinstance(result, str)
    assert len(result) > 0
