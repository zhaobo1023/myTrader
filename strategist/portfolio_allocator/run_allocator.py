# -*- coding: utf-8 -*-
"""
策略组合权重调度器 - 主入口

Usage:
  python -m strategist.portfolio_allocator.run_allocator --latest
  python -m strategist.portfolio_allocator.run_allocator --regime BULL --crowding HIGH
"""
import sys
import os
import argparse
import logging
from datetime import date

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from strategist.portfolio_allocator.config import AllocatorConfig
from strategist.portfolio_allocator.signal_collector import SignalCollector
from strategist.portfolio_allocator.weight_engine import WeightEngine
from strategist.portfolio_allocator.reconciler import Reconciler
from strategist.portfolio_allocator.storage import WeightStorage
from strategist.portfolio_allocator.reporter import generate_report

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PortfolioAllocator:
    """策略组合权重调度器"""
    
    def __init__(self, config: AllocatorConfig = None, env: str = 'online'):
        self.config = config or AllocatorConfig()
        self.collector = SignalCollector(env=env)
        self.engine = WeightEngine(self.config)
        self.reconciler = Reconciler()
    
    def run(self, regime: str = None, crowding_level: str = None,
            save_db: bool = True, do_report: bool = True) -> dict:
        """
        Run weight allocation.
        
        Args:
            regime: Override regime (BULL/BEAR/NEUTRAL). If None, reads from DB.
            crowding_level: Override crowding level. If None, reads from DB.
            save_db: Save to DB
            do_report: Generate report
        
        Returns:
            dict with keys: weights, suggestions, report_path
        """
        today = date.today()
        
        logger.info("=" * 60)
        logger.info(f"Portfolio Allocator: {today}")
        logger.info("=" * 60)
        
        # 1. Collect signals
        logger.info("[1/4] Collecting signals...")
        if regime is None or crowding_level is None:
            collected_regime, collected_crowding = self.collector.collect()
            regime = regime or collected_regime
            crowding_level = crowding_level or collected_crowding
        
        logger.info(f"  Regime: {regime}, Crowding: {crowding_level}")
        
        # 2. Compute weights
        logger.info("[2/4] Computing target weights...")
        weights = self.engine.compute_weights(today, regime, crowding_level)
        
        for w in weights:
            logger.info(f"  {w.strategy_name}: base={w.base_weight:.0%} -> final={w.final_weight:.1%}")
        
        # Verify sum
        total = sum(w.final_weight for w in weights)
        logger.info(f"  Total weight: {total:.4f}")
        
        # 3. Reconcile with current
        logger.info("[3/4] Reconciling with current allocation...")
        target_dict = {w.strategy_name: w.final_weight for w in weights}
        
        # Try to get previous weights for comparison
        current_dict = None
        try:
            prev = WeightStorage.get_latest_weights()
            if prev:
                current_dict = {r['strategy_name']: float(r['final_weight']) for r in prev}
        except Exception:
            pass
        
        suggestions = self.reconciler.reconcile(target_dict, current_dict)
        
        # 4. Save & report
        if save_db:
            logger.info("[4/4] Saving to DB...")
            try:
                WeightStorage.init_table()
                WeightStorage.save_batch(weights)
            except Exception as e:
                logger.warning(f"DB save failed: {e}")
        
        report_path = None
        if do_report:
            output_dir = os.path.join(_PROJECT_ROOT, self.config.output_dir)
            report_path = generate_report(weights, suggestions, output_dir)
        
        return {
            'weights': weights,
            'suggestions': suggestions,
            'report_path': report_path,
        }


def main():
    parser = argparse.ArgumentParser(description='Strategy Portfolio Allocator')
    parser.add_argument('--regime', type=str, choices=['BULL', 'BEAR', 'NEUTRAL'],
                        help='Override regime')
    parser.add_argument('--crowding', type=str, choices=['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'],
                        help='Override crowding level')
    parser.add_argument('--no-db', action='store_true', help='Skip DB save')
    parser.add_argument('--no-report', action='store_true', help='Skip report')
    parser.add_argument('--env', type=str, default='online', help='DB environment')
    args = parser.parse_args()
    
    allocator = PortfolioAllocator(env=args.env)
    result = allocator.run(
        regime=args.regime,
        crowding_level=args.crowding,
        save_db=not args.no_db,
        do_report=not args.no_report,
    )
    
    print(f"\n[RESULT] Strategy Weights:")
    for w in result['weights']:
        print(f"  {w.strategy_name}: {w.final_weight:.1%} (regime={w.regime}, crowding={w.crowding_level})")
    
    if result['suggestions']:
        print(f"\n[RESULT] Rebalance Suggestions:")
        for s in result['suggestions']:
            print(f"  {s['strategy']}: {s['action']} (delta={s['delta']}pp)" if s['delta'] is not None else f"  {s['strategy']}: {s['action']}")
    
    if result['report_path']:
        print(f"\n[RESULT] Report: {result['report_path']}")


if __name__ == '__main__':
    main()
