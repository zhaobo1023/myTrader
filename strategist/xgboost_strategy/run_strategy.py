# -*- coding: utf-8 -*-
"""
XGBoost 截面预测策略 - 主入口

运行完整的策略流程：
1. 加载数据并计算因子
2. 滚动训练 XGBoost 模型
3. 截面预测
4. IC 评估
5. 回测
6. 可视化

运行: python -m strategist.xgboost_strategy.run_strategy
"""
import sys
import os
import logging
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from strategist.xgboost_strategy.config import StrategyConfig
from strategist.xgboost_strategy.data_loader import DataLoader
from strategist.xgboost_strategy.backtest import XGBoostBacktest
from strategist.xgboost_strategy.visualizer import Visualizer
from strategist.xgboost_strategy.feature_engine import get_all_feature_cols, FACTOR_TAXONOMY

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def print_factor_taxonomy():
    """打印因子分类体系"""
    print("\n" + "=" * 60)
    print("因子分类体系 (52 维)")
    print("=" * 60)
    
    total = 0
    for cat_key, cat_info in FACTOR_TAXONOMY.items():
        print(f"\n{cat_info['name']} ({len(cat_info['features'])} 个)")
        print(f"  描述: {cat_info['desc']}")
        print(f"  因子: {', '.join(cat_info['features'][:5])}...")
        total += len(cat_info['features'])
    
    print(f"\n总计: {total} 个因子")
    print("=" * 60)


def main():
    """主函数"""
    print("\n" + "=" * 80)
    print("XGBoost 截面预测策略")
    print("基于 MASTER 论文思想，使用 XGBoost 进行股票截面预测")
    print("=" * 80)
    
    # 打印因子体系
    print_factor_taxonomy()
    
    # 1. 配置
    config = StrategyConfig()
    
    print("\n策略配置:")
    print(f"  股票池: {len(config.stock_pool)} 只")
    print(f"  日期范围: {config.start_date} ~ {config.end_date}")
    print(f"  训练窗口: {config.train_window} 交易日")
    print(f"  预测目标: 未来 {config.predict_horizon} 日收益率")
    print(f"  滚动步长: {config.roll_step} 天")
    print(f"  预处理方法: {config.preprocess_method}")
    print(f"  XGBoost 参数: n_estimators={config.n_estimators}, max_depth={config.max_depth}, lr={config.learning_rate}")
    
    # 2. 加载数据并计算因子
    logger.info("\n开始加载数据...")
    data_loader = DataLoader(config)
    
    try:
        panel, feature_cols = data_loader.load_and_compute_factors()
    except Exception as e:
        logger.error(f"数据加载失败: {e}")
        return
    
    # 3. 运行回测
    logger.info("\n开始回测...")
    backtest = XGBoostBacktest(config)
    
    try:
        result = backtest.run_backtest(panel, feature_cols)
    except Exception as e:
        logger.error(f"回测失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    if not result:
        logger.error("回测结果为空")
        return
    
    # 4. 单因子 IC 分析
    logger.info("\n单因子 IC 分析...")
    factor_ic_df = backtest.analyze_factor_ic(panel, feature_cols)
    
    if not factor_ic_df.empty:
        print("\n" + "=" * 60)
        print("因子 IC 排名 (Top 15, 按 |ICIR| 排序)")
        print("=" * 60)
        print(f"{'因子':<28} {'IC':>8} {'ICIR':>8} {'RankIC':>8} {'RICIR':>8} {'IC>0':>6}")
        print("-" * 75)
        for _, row in factor_ic_df.head(15).iterrows():
            print(f"{row['factor']:<28} {row['IC']:>8.4f} {row['ICIR']:>8.4f} "
                  f"{row['RankIC']:>8.4f} {row['RankICIR']:>8.4f} {row['IC_positive']:>5.1%}")
        
        # 按类别汇总
        print("\n各因子类别平均 |ICIR|:")
        for cat_key, cat_info in FACTOR_TAXONOMY.items():
            cat_factors = factor_ic_df[factor_ic_df['factor'].isin(cat_info['features'])]
            if not cat_factors.empty:
                avg_icir = cat_factors['ICIR'].abs().mean()
                best = cat_factors.loc[cat_factors['ICIR'].abs().idxmax()]
                print(f"  {cat_info['name']:<14} 平均|ICIR|={avg_icir:.3f}  "
                      f"最佳: {best['factor']} (ICIR={best['ICIR']:.3f})")
    
    # 5. 与 MASTER 对比
    backtest.evaluator.compare_with_master(result['metrics'])
    
    # 6. 可视化
    logger.info("\n生成可视化图表...")
    output_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        'output'
    )
    visualizer = Visualizer(output_dir)
    
    # IC 分析图
    visualizer.plot_ic_analysis(result['metrics'])
    
    # 组合表现图
    if not result['portfolio_returns'].empty:
        visualizer.plot_portfolio_performance(result['portfolio_returns'])
    
    # 因子 IC 图
    if not factor_ic_df.empty:
        visualizer.plot_factor_ic(factor_ic_df)
    
    # 7. 保存结果
    logger.info("\n保存结果...")
    
    # 保存信号
    signals_file = os.path.join(output_dir, 'signals.csv')
    result['signals'].to_csv(signals_file, index=False, encoding='utf-8-sig')
    logger.info(f"信号已保存: {signals_file}")
    
    # 保存组合收益
    if not result['portfolio_returns'].empty:
        returns_file = os.path.join(output_dir, 'portfolio_returns.csv')
        result['portfolio_returns'].to_csv(returns_file, index=False, encoding='utf-8-sig')
        logger.info(f"组合收益已保存: {returns_file}")
    
    # 保存因子 IC
    if not factor_ic_df.empty:
        factor_ic_file = os.path.join(output_dir, 'factor_ic.csv')
        factor_ic_df.to_csv(factor_ic_file, index=False, encoding='utf-8-sig')
        logger.info(f"因子 IC 已保存: {factor_ic_file}")
    
    # 8. 生成报告
    generate_report(result, factor_ic_df, output_dir)
    
    print("\n" + "=" * 80)
    print("✅ XGBoost 截面预测策略运行完成!")
    print(f"输出目录: {output_dir}")
    print("=" * 80)


def generate_report(result, factor_ic_df, output_dir):
    """生成 Markdown 报告"""
    report_file = os.path.join(output_dir, 'strategy_report.md')
    
    metrics = result['metrics']
    portfolio_returns = result['portfolio_returns']
    
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write("# XGBoost 截面预测策略报告\n\n")
        f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        f.write("## 一、策略概述\n\n")
        f.write("基于 MASTER 论文思想，使用 XGBoost 进行股票截面预测。\n\n")
        f.write("- **因子维度**: 52 维技术因子\n")
        f.write("- **预处理**: MAD 去极值 + Z-Score 标准化\n")
        f.write("- **模型**: XGBoost 回归\n")
        f.write("- **评估**: IC/ICIR/RankIC/RankICIR\n\n")
        
        f.write("## 二、IC 评估结果\n\n")
        f.write("| 指标 | 值 |\n")
        f.write("|------|----|\n")
        f.write(f"| IC | {metrics['IC']:.4f} |\n")
        f.write(f"| ICIR | {metrics['ICIR']:.4f} |\n")
        f.write(f"| RankIC | {metrics['RankIC']:.4f} |\n")
        f.write(f"| RankICIR | {metrics['RankICIR']:.4f} |\n")
        f.write(f"| IC>0 占比 | {metrics['IC_positive_rate']:.1%} |\n")
        f.write(f"| IC 最大值 | {metrics['IC_max']:.4f} |\n")
        f.write(f"| IC 最小值 | {metrics['IC_min']:.4f} |\n")
        f.write(f"| 有效天数 | {metrics['n_days']} |\n\n")
        
        if not portfolio_returns.empty:
            f.write("## 三、组合表现\n\n")
            total_ret = portfolio_returns['cum_portfolio'].iloc[-1] - 1
            benchmark_ret = portfolio_returns['cum_benchmark'].iloc[-1] - 1
            excess_ret = total_ret - benchmark_ret
            
            f.write("| 指标 | 值 |\n")
            f.write("|------|----|\n")
            f.write(f"| 策略总收益 | {total_ret*100:+.2f}% |\n")
            f.write(f"| 基准总收益 | {benchmark_ret*100:+.2f}% |\n")
            f.write(f"| 超额收益 | {excess_ret*100:+.2f}% |\n")
            f.write(f"| 平均持仓 | {portfolio_returns['n_stocks'].mean():.1f} 只 |\n\n")
        
        if not factor_ic_df.empty:
            f.write("## 四、Top 10 因子\n\n")
            f.write("| 因子 | IC | ICIR | RankIC | RankICIR |\n")
            f.write("|------|----:|-----:|-------:|---------:|\n")
            for _, row in factor_ic_df.head(10).iterrows():
                f.write(f"| {row['factor']} | {row['IC']:.4f} | {row['ICIR']:.4f} | "
                       f"{row['RankIC']:.4f} | {row['RankICIR']:.4f} |\n")
            f.write("\n")
        
        f.write("## 五、可视化图表\n\n")
        f.write("- [IC 分析图](ic_analysis.png)\n")
        f.write("- [组合表现图](portfolio_performance.png)\n")
        f.write("- [因子 IC 图](factor_ic.png)\n\n")
    
    logger.info(f"报告已保存: {report_file}")


if __name__ == "__main__":
    main()
