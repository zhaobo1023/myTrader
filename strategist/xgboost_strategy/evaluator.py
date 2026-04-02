# -*- coding: utf-8 -*-
"""
IC 评估器

计算 IC/ICIR/RankIC/RankICIR 等指标评估预测质量
"""
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from typing import List, Dict
import logging

logger = logging.getLogger(__name__)


class ICEvaluator:
    """IC 评估器"""
    
    def __init__(self):
        pass
    
    def calc_ic(self, pred, label):
        """
        计算单日 IC (Pearson相关) 和 RankIC (Spearman相关)
        
        参数:
            pred: 预测值
            label: 实际值
        
        返回:
            (ic, rank_ic)
        """
        df = pd.DataFrame({'pred': pred, 'label': label})
        df = df.dropna()
        
        if len(df) < 5:
            return np.nan, np.nan
        
        ic = df['pred'].corr(df['label'])
        ric, _ = spearmanr(df['pred'], df['label'])
        
        return ic, ric
    
    def evaluate_predictions(self, results: List[Dict], panel: pd.DataFrame = None) -> Dict:
        """
        评估预测结果

        IC = corr(预测的未来N日收益排名, 实际未来N日收益排名)
        两者时间对齐：都是以 pred_date 为基准，往后看 N 天

        参数:
            results: 预测结果列表，每个元素为 {pred_date, predictions, stock_codes}
            panel: 面板数据，包含 future_ret（用于获取实际标签）

        返回:
            评估指标字典
        """
        daily_ics = []
        daily_rics = []

        for result in results:
            pred_date = result['pred_date']
            predictions = result['predictions']
            stock_codes = result['stock_codes']

            # 从 panel 中获取 pred_date 当天的 future_ret（已经是 shift(-N) 的结果）
            if panel is not None:
                actual_series = panel[panel['trade_date'] == pred_date].set_index('stock_code')['future_ret']
                pred_series = pd.Series(predictions, index=stock_codes)

                # 对齐
                common = pred_series.index.intersection(actual_series.index)
                pred_aligned = pred_series[common].dropna()
                actual_aligned = actual_series[common].dropna()
                common2 = pred_aligned.index.intersection(actual_aligned.index)

                if len(common2) < 10:
                    continue

                ic, ric = self.calc_ic(pred_aligned[common2].values, actual_aligned[common2].values)
            else:
                # 兼容旧接口（无 panel 时跳过）
                continue

            if not np.isnan(ic):
                daily_ics.append(ic)
            if not np.isnan(ric):
                daily_rics.append(ric)
        
        if not daily_ics:
            logger.error("没有有效的 IC 数据")
            return {}
        
        # 计算统计指标
        ic_arr = np.array(daily_ics)
        ric_arr = np.array(daily_rics)
        
        ic_mean = np.mean(ic_arr)
        ic_std = np.std(ic_arr)
        icir = ic_mean / ic_std if ic_std > 0 else 0
        
        ric_mean = np.mean(ric_arr)
        ric_std = np.std(ric_arr)
        ricir = ric_mean / ric_std if ric_std > 0 else 0
        
        ic_positive = sum(1 for x in ic_arr if x > 0) / len(ic_arr)
        
        metrics = {
            'IC': ic_mean,
            'ICIR': icir,
            'RankIC': ric_mean,
            'RankICIR': ricir,
            'IC_std': ic_std,
            'RankIC_std': ric_std,
            'IC_positive_rate': ic_positive,
            'IC_max': np.max(ic_arr),
            'IC_min': np.min(ic_arr),
            'IC_median': np.median(ic_arr),
            'n_days': len(ic_arr),
            'daily_ics': ic_arr,
            'daily_rics': ric_arr,
        }
        
        return metrics
    
    def analyze_factor_ic(self, panel: pd.DataFrame, feature_cols: List[str]) -> pd.DataFrame:
        """
        单因子 IC 分析
        
        参数:
            panel: 面板数据，包含 trade_date, feature_cols, future_ret
            feature_cols: 特征列名列表
        
        返回:
            DataFrame with factor IC statistics
        """
        dates = sorted(panel['trade_date'].unique())
        factor_stats = {col: {'ics': [], 'rics': []} for col in feature_cols}
        
        logger.info(f"开始单因子 IC 分析: {len(feature_cols)} 个因子, {len(dates)} 个交易日")
        
        for dt in dates:
            daily = panel[panel['trade_date'] == dt]
            if len(daily) < 10:
                continue
            
            for col in feature_cols:
                valid = daily[[col, 'future_ret']].dropna()
                if len(valid) < 10:
                    continue
                
                ic = valid[col].corr(valid['future_ret'])
                ric, _ = spearmanr(valid[col], valid['future_ret'])
                
                if not np.isnan(ic):
                    factor_stats[col]['ics'].append(ic)
                if not np.isnan(ric):
                    factor_stats[col]['rics'].append(ric)
        
        # 汇总统计
        results = []
        for col in feature_cols:
            ics = factor_stats[col]['ics']
            rics = factor_stats[col]['rics']
            if len(ics) < 30:
                continue
            
            ic_mean = np.mean(ics)
            ic_std = np.std(ics)
            ric_mean = np.mean(rics)
            ric_std = np.std(rics)
            
            results.append({
                'factor': col,
                'IC': ic_mean,
                'ICIR': ic_mean / ic_std if ic_std > 0 else 0,
                'RankIC': ric_mean,
                'RankICIR': ric_mean / ric_std if ric_std > 0 else 0,
                'IC_positive': sum(1 for x in ics if x > 0) / len(ics),
                'n_days': len(ics),
            })
        
        results_df = pd.DataFrame(results)
        results_df['abs_ICIR'] = results_df['ICIR'].abs()
        results_df = results_df.sort_values('abs_ICIR', ascending=False)

        # RankIC 方向一致性诊断
        if len(results_df) > 5:
            ic_ric_corr = results_df['IC'].corr(results_df['RankIC'])
            if ic_ric_corr < 0.3:
                logger.warning(
                    f"IC 与 RankIC 方向不一致 (corr={ic_ric_corr:.3f})，"
                    f"可能存在异常值影响 Pearson IC。"
                    f"建议检查因子分布是否有极端值。"
                )

        logger.info(f"单因子 IC 分析完成: {len(results_df)} 个有效因子")
        
        return results_df
    
    def print_metrics(self, metrics: Dict):
        """
        打印评估指标
        
        参数:
            metrics: 评估指标字典
        """
        print("\n" + "=" * 60)
        print("XGBoost 截面预测评估结果")
        print("=" * 60)
        print(f"IC:        {metrics['IC']:.4f}")
        print(f"ICIR:      {metrics['ICIR']:.4f}")
        print(f"RankIC:    {metrics['RankIC']:.4f}")
        print(f"RankICIR:  {metrics['RankICIR']:.4f}")
        print(f"IC>0占比:  {metrics['IC_positive_rate']:.1%} ({sum(1 for x in metrics['daily_ics'] if x > 0)}/{metrics['n_days']})")
        print(f"IC最大值:  {metrics['IC_max']:.4f}")
        print(f"IC最小值:  {metrics['IC_min']:.4f}")
        print(f"IC中位数:  {metrics['IC_median']:.4f}")
        print("=" * 60)
    
    def compare_with_master(self, metrics: Dict):
        """
        与 MASTER 论文对比
        
        参数:
            metrics: 评估指标字典
        """
        # MASTER 在 CSI300 上的典型结果
        master_range = {
            'IC':       (0.050, 0.080),
            'ICIR':     (0.400, 0.700),
            'RankIC':   (0.080, 0.120),
            'RankICIR': (0.700, 1.100),
        }
        
        print("\n" + "=" * 60)
        print("与 MASTER 论文 (CSI300) 对比")
        print("=" * 60)
        print(f"{'指标':<12} {'我们':>12} {'MASTER':>15} {'差距':>8} {'评估'}")
        print("-" * 60)
        
        for key in ['IC', 'ICIR', 'RankIC', 'RankICIR']:
            ours = metrics.get(key, 0)
            m_lo, m_hi = master_range[key]
            m_mid = (m_lo + m_hi) / 2
            
            if abs(ours) >= m_lo:
                assessment = '达标'
            elif abs(ours) >= m_lo * 0.6:
                assessment = '接近'
            else:
                assessment = '差距大'
            
            gap = abs(ours) - m_mid
            print(f"{key:<12} {ours:>12.4f} {m_lo:.3f}~{m_hi:.3f}      {gap:>+8.4f} {assessment}")
        
        print("=" * 60)
