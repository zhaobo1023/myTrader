# -*- coding: utf-8 -*-
"""
回测报告生成模块
"""
import os
from datetime import datetime
from typing import Optional
import pandas as pd

from .metrics import BacktestResult


class ReportGenerator:
    """回测报告生成器"""
    
    @staticmethod
    def generate_markdown_report(
        result: BacktestResult,
        output_path: str,
        strategy_name: str = "策略回测"
    ):
        """
        生成Markdown格式的回测报告
        
        Args:
            result: 回测结果
            output_path: 输出文件路径
            strategy_name: 策略名称
        """
        lines = []
        
        # 标题
        lines.append(f"# {strategy_name} - 回测报告")
        lines.append("")
        lines.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"**回测区间**: {result.start_date} ~ {result.end_date}")
        lines.append(f"**交易天数**: {result.trading_days}")
        lines.append("")
        lines.append("---")
        lines.append("")
        
        # 收益指标
        lines.append("## 一、收益指标")
        lines.append("")
        lines.append("| 指标 | 数值 |")
        lines.append("|------|------|")
        lines.append(f"| 初始资金 | {result.initial_cash:,.0f} |")
        lines.append(f"| 最终净值 | {result.final_value:,.0f} |")
        lines.append(f"| 总收益率 | {result.total_return*100:.2f}% |")
        lines.append(f"| 年化收益率 | {result.annual_return*100:.2f}% |")
        
        if result.benchmark_return != 0:
            lines.append(f"| 基准收益率 | {result.benchmark_return*100:.2f}% |")
            lines.append(f"| 基准年化 | {result.benchmark_annual*100:.2f}% |")
            lines.append(f"| 超额收益 | {result.excess_return*100:.2f}% |")
        
        lines.append("")
        
        # 风险指标
        lines.append("## 二、风险指标")
        lines.append("")
        lines.append("| 指标 | 数值 |")
        lines.append("|------|------|")
        lines.append(f"| 最大回撤 | {result.max_drawdown*100:.2f}% |")
        lines.append(f"| 波动率 | {result.volatility*100:.2f}% |")
        lines.append(f"| 夏普比率 | {result.sharpe_ratio:.2f} |")
        lines.append(f"| 索提诺比率 | {result.sortino_ratio:.2f} |")
        lines.append(f"| 卡玛比率 | {result.calmar_ratio:.2f} |")
        lines.append("")
        
        # 交易统计
        lines.append("## 三、交易统计")
        lines.append("")
        lines.append("| 指标 | 数值 |")
        lines.append("|------|------|")
        lines.append(f"| 总交易数 | {result.total_trades} |")
        lines.append(f"| 盈利次数 | {result.win_trades} |")
        lines.append(f"| 亏损次数 | {result.lose_trades} |")
        lines.append(f"| 胜率 | {result.win_rate*100:.2f}% |")
        lines.append(f"| 平均收益/笔 | {result.avg_return_per_trade*100:.2f}% |")
        lines.append(f"| 平均盈利 | {result.avg_win*100:.2f}% |")
        lines.append(f"| 平均亏损 | {result.avg_loss*100:.2f}% |")
        lines.append(f"| 盈亏比 | {result.profit_loss_ratio:.2f} |")
        lines.append(f"| 平均持仓天数 | {result.avg_hold_days:.1f} |")
        lines.append("")
        
        # 分类统计
        if result.momentum_stats or result.reversal_stats:
            lines.append("## 四、信号分类统计")
            lines.append("")
            
            if result.momentum_stats:
                lines.append("### 动量信号")
                lines.append("")
                lines.append("| 指标 | 数值 |")
                lines.append("|------|------|")
                lines.append(f"| 交易数 | {result.momentum_stats.get('count', 0)} |")
                lines.append(f"| 胜率 | {result.momentum_stats.get('win_rate', 0)*100:.2f}% |")
                lines.append(f"| 平均收益 | {result.momentum_stats.get('avg_return', 0)*100:.2f}% |")
                lines.append(f"| 最大收益 | {result.momentum_stats.get('max_return', 0)*100:.2f}% |")
                lines.append(f"| 最大亏损 | {result.momentum_stats.get('min_return', 0)*100:.2f}% |")
                lines.append("")
            
            if result.reversal_stats:
                lines.append("### 反转信号")
                lines.append("")
                lines.append("| 指标 | 数值 |")
                lines.append("|------|------|")
                lines.append(f"| 交易数 | {result.reversal_stats.get('count', 0)} |")
                lines.append(f"| 胜率 | {result.reversal_stats.get('win_rate', 0)*100:.2f}% |")
                lines.append(f"| 平均收益 | {result.reversal_stats.get('avg_return', 0)*100:.2f}% |")
                lines.append(f"| 最大收益 | {result.reversal_stats.get('max_return', 0)*100:.2f}% |")
                lines.append(f"| 最大亏损 | {result.reversal_stats.get('min_return', 0)*100:.2f}% |")
                lines.append("")
        
        # 基准对比
        if result.gdp_cumulative_return or result.cpi_cumulative_return:
            lines.append("## 五、基准对比 (Benchmark Comparison)")
            lines.append("")
            lines.append("| 基准 | 累计收益 | 年化收益 | 说明 |")
            lines.append("|------|---------|---------|------|")
            lines.append(f"| 策略 | {result.total_return*100:.2f}% | {result.annual_return*100:.2f}% | - |")
            if result.benchmark_return != 0:
                lines.append(f"| 沪深300 | {result.benchmark_return*100:.2f}% | {result.benchmark_annual*100:.2f}% | 市场基准 |")
            lines.append(f"| GDP 增长 | {result.gdp_cumulative_return*100:.2f}% | 5.00% | 经济增长上限参考 |")
            lines.append(f"| CPI 增长 | {result.cpi_cumulative_return*100:.2f}% | 2.00% | 现金保值下限参考 |")
            lines.append("")

            # Reasonability assessment
            lines.append("### 合理性评估")
            lines.append("")
            if result.reasonability == 'overfit_warning':
                lines.append("[WARN] **过拟合警告**: 年化收益超过 GDP 增速 3 倍 (>{:.0f}%)，策略可能过拟合历史数据。".format(5 * 3))
                lines.append("建议: 检查样本外表现、增加交易成本、缩短回测窗口验证稳健性。")
            elif result.reasonability == 'underperform_cash':
                lines.append("[WARN] **跑输现金**: 年化收益低于 CPI (2%)，策略未能跑赢通胀。")
                lines.append("建议: 审视策略逻辑、检查选股范围、优化参数。")
            else:
                lines.append("[OK] **合理区间**: 年化收益在 CPI~3xGDP 区间内，收益水平合理。")
            lines.append("")

        # 策略评价
        section_num = "六" if (result.gdp_cumulative_return or result.cpi_cumulative_return) else "五"
        lines.append(f"## {section_num}、策略评价")
        lines.append("")

        if result.annual_return > 0.15 and result.max_drawdown > -0.2 and result.sharpe_ratio > 1.5:
            lines.append("[OK] **优秀策略**: 高收益 + 低回撤 + 高夏普")
        elif result.annual_return > 0.10 and result.max_drawdown > -0.3 and result.sharpe_ratio > 1.0:
            lines.append("[OK] **良好策略**: 正收益 + 可控回撤 + 正夏普")
        elif result.annual_return > 0.05 and result.sharpe_ratio > 0.5:
            lines.append("[NOTE] **一般策略**: 收益一般或回撤较大")
        else:
            lines.append("[WARN] **需改进**: 收益不足或风险过高")

        lines.append("")
        
        # 写入文件
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        
        print(f"\n报告已保存: {output_path}")
    
    @staticmethod
    def save_trades(
        result: BacktestResult,
        output_path: str
    ):
        """
        保存交易记录到CSV
        
        Args:
            result: 回测结果
            output_path: 输出文件路径
        """
        if len(result.trades_df) == 0:
            print("无交易记录")
            return
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        result.trades_df.to_csv(output_path, index=False, encoding='utf-8-sig')
        print(f"交易记录已保存: {output_path}")
    
    @staticmethod
    def save_daily_values(
        result: BacktestResult,
        output_path: str
    ):
        """
        保存每日净值到CSV
        
        Args:
            result: 回测结果
            output_path: 输出文件路径
        """
        if len(result.daily_df) == 0:
            print("无每日净值数据")
            return
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        result.daily_df.to_csv(output_path, encoding='utf-8-sig')
        print(f"每日净值已保存: {output_path}")
    
    @staticmethod
    def generate_full_report(
        result: BacktestResult,
        output_dir: str,
        strategy_name: str = "策略回测"
    ):
        """
        生成完整报告（Markdown + CSV）
        
        Args:
            result: 回测结果
            output_dir: 输出目录
            strategy_name: 策略名称
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Markdown报告
        report_path = os.path.join(output_dir, f'backtest_report_{timestamp}.md')
        ReportGenerator.generate_markdown_report(result, report_path, strategy_name)
        
        # 交易记录
        trades_path = os.path.join(output_dir, f'backtest_trades_{timestamp}.csv')
        ReportGenerator.save_trades(result, trades_path)
        
        # 每日净值
        daily_path = os.path.join(output_dir, f'backtest_daily_{timestamp}.csv')
        ReportGenerator.save_daily_values(result, daily_path)
        
        print(f"\n完整报告已生成到目录: {output_dir}")
