# -*- coding: utf-8 -*-
"""
Unit tests for position schemas and DB portfolio adapter.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)


class TestPositionSchemas(unittest.TestCase):
    """Test position Pydantic schemas."""

    def test_create_minimal(self):
        from api.schemas.positions import PositionCreate
        req = PositionCreate(stock_code='600519')
        self.assertEqual(req.stock_code, '600519')
        self.assertIsNone(req.shares)
        self.assertIsNone(req.level)

    def test_create_full(self):
        from api.schemas.positions import PositionCreate
        req = PositionCreate(
            stock_code='600519',
            stock_name='Moutai',
            level='L1',
            shares=100,
            cost_price=1800.0,
            account='broker_a',
            note='test',
        )
        self.assertEqual(req.level, 'L1')
        self.assertEqual(req.shares, 100)

    def test_create_empty_code_rejected(self):
        from api.schemas.positions import PositionCreate
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            PositionCreate(stock_code='')

    def test_update_partial(self):
        from api.schemas.positions import PositionUpdate
        req = PositionUpdate(shares=200)
        data = req.model_dump(exclude_unset=True)
        self.assertEqual(data, {'shares': 200})
        self.assertNotIn('level', data)

    def test_import_request(self):
        from api.schemas.positions import PositionImportRequest, PositionImportItem
        req = PositionImportRequest(items=[
            PositionImportItem(stock_code='000001', stock_name='PA Bank'),
            PositionImportItem(stock_code='600519', level='L1', shares=50),
        ])
        self.assertEqual(len(req.items), 2)

    def test_response_model(self):
        from api.schemas.positions import PositionResponse
        resp = PositionResponse(
            id=1,
            stock_code='000001',
            stock_name='PA Bank',
            level='L2',
            shares=100,
            cost_price=12.5,
            account=None,
            note=None,
            is_active=True,
            created_at='2026-04-17T00:00:00',
            updated_at='2026-04-17T00:00:00',
        )
        self.assertEqual(resp.stock_code, '000001')
        self.assertTrue(resp.is_active)


class TestDbPortfolioAdapter(unittest.TestCase):
    """Test DB portfolio adapter market suffix logic."""

    def test_add_sh_suffix(self):
        from strategist.tech_scan.db_portfolio_adapter import DbPortfolioAdapter
        self.assertEqual(DbPortfolioAdapter._add_market_suffix('600519'), '600519.SH')
        self.assertEqual(DbPortfolioAdapter._add_market_suffix('510300'), '510300.SH')

    def test_add_sz_suffix(self):
        from strategist.tech_scan.db_portfolio_adapter import DbPortfolioAdapter
        self.assertEqual(DbPortfolioAdapter._add_market_suffix('000001'), '000001.SZ')
        self.assertEqual(DbPortfolioAdapter._add_market_suffix('300750'), '300750.SZ')
        self.assertEqual(DbPortfolioAdapter._add_market_suffix('159915'), '159915.SZ')


if __name__ == '__main__':
    unittest.main()
