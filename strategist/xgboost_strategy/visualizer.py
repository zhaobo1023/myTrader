# -*- coding: utf-8 -*-
"""
可视化模块

绘制 IC 时序图、累计 IC 曲线、组合净值等
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
from typing import Dict
import os

matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
matplotlib.rcParams['axes.unicode_minus'] = False


class Visualizer:
    """可视化工具"""
    
    def __init__(self, output_dir='output'):
        """
        初始化可视化工具
        
        参数:
            output_dir: 输出目录
        """
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
    
    def plot_ic_analysis(self, metrics: Dict, save_name='ic_analysis.png'):
        """
        绘制 IC 分析图表
        
        参数:
            metrics: 评估指标字典
            save_name: 保存文件名
        """
        daily_ics = metrics['daily_ics']
        daily_rics = metrics['daily_rics']
        
        fig, axes = plt.subplots(2, 2, figsize=(16, 10))
        fig.suptitle('XGBoost 截面预测 IC 分析', fontsize=16, fontweight='bold')
        
        # 1. 逐日 IC 时序图
        ax = axes[0, 0]
        ax.bar(range(len(daily_ics)), daily_ics, 
               color=['#27ae60' if x > 0 else '#e74c3c' for x in daily_ics],
               alpha=0.6, width=1.0)
        ax.axhline(y=0, color='black', linewidth=0.5)
        ax.axhline(y=metrics['IC'], color='#3498db', linewidth=2, linestyle='--',
                   label=f"IC Mean = {metrics['IC']:.4f}")
        ax.set_title('逐日 IC (Pearson 相关)')
        ax.set_xlabel('交易日')
        ax.set_ylabel('IC')
        ax.legend(loc='upper right')
        ax.grid(True, alpha=0.3)
        
        # 2. 逐日 RankIC 时序图
        ax = axes[0, 1]
        ax.bar(range(len(daily_rics)), daily_rics,
               color=['#27ae60' if x > 0 else '#e74c3c' for x in daily_rics],
               alpha=0.6, width=1.0)
        ax.axhline(y=0, color='black', linewidth=0.5)
        ax.axhline(y=metrics['RankIC'], color='#3498db', linewidth=2, linestyle='--',
                   label=f"RankIC Mean = {metrics['RankIC']:.4f}")
        ax.set_title('逐日 RankIC (Spearman 相关)')
        ax.set_xlabel('交易日')
        ax.set_ylabel('RankIC')
        ax.legend(loc='upper right')
        ax.grid(True, alpha=0.3)
        
        # 3. IC 分布直方图
        ax = axes[1, 0]
        ax.hist(daily_ics, bins=50, color='#3498db', alpha=0.7, edgecolor='white', label='IC')
        ax.hist(daily_rics, bins=50, color='#e67e22', alpha=0.5, edgecolor='white', label='RankIC')
        ax.axvline(x=0, color='black', linewidth=1)
        ax.axvline(x=metrics['IC'], color='#3498db', linewidth=2, linestyle='--')
        ax.axvline(x=metrics['RankIC'], color='#e67e22', linewidth=2, linestyle='--')
        ax.set_title('IC / RankIC 分布')
        ax.set_xlabel('IC 值')
        ax.set_ylabel('频数')
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        # 4. 累计 IC 曲线
        ax = axes[1, 1]
        cumsum_ic = np.cumsum(daily_ics)
        cumsum_ric = np.cumsum(daily_rics)
        ax.plot(cumsum_ic, color='#3498db', linewidth=1.5, label='Cumulative IC')
        ax.plot(cumsum_ric, color='#e67e22', linewidth=1.5, label='Cumulative RankIC')
        ax.set_title('累计 IC 曲线 (向上倾斜=持续有效)')
        ax.set_xlabel('交易日')
        ax.set_ylabel('累计 IC')
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        save_path = os.path.join(self.output_dir, save_name)
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"IC 分析图表已保存: {save_path}")
        plt.close()
    
    def plot_portfolio_performance(self, portfolio_returns: pd.DataFrame, save_name='portfolio_performance.png'):
        """
        绘制组合表现图表
        
        参数:
            portfolio_returns: 组合收益 DataFrame
            save_name: 保存文件名
        """
        if portfolio_returns.empty:
            print("组合收益数据为空，跳过绘图")
            return
        
        fig, axes = plt.subplots(2, 1, figsize=(16, 10))
        fig.suptitle('XGBoost 策略组合表现', fontsize=16, fontweight='bold')
        
        # 1. 累计收益曲线
        ax = axes[0]
        ax.plot(portfolio_returns.index, portfolio_returns['cum_portfolio'], 
                color='#2980b9', linewidth=2, label='策略组合')
        ax.plot(portfolio_returns.index, portfolio_returns['cum_benchmark'],
                color='gray', linewidth=1.5, alpha=0.6, label='基准 (全市场平均)')
        ax.axhline(y=1.0, color='red', linestyle='--', alpha=0.3)
        ax.set_title('累计收益曲线')
        ax.set_ylabel('累计收益 (初始=1.0)')
        ax.legend(loc='upper left')
        ax.grid(True, alpha=0.3)
        
        # 添加统计信息
        total_ret = portfolio_returns['cum_portfolio'].iloc[-1] - 1
        benchmark_ret = portfolio_returns['cum_benchmark'].iloc[-1] - 1
        excess_ret = total_ret - benchmark_ret
        
        info_text = (
            f"策略总收益: {total_ret*100:+.2f}%\n"
            f"基准总收益: {benchmark_ret*100:+.2f}%\n"
            f"超额收益:   {excess_ret*100:+.2f}%"
        )
        ax.text(0.02, 0.98, info_text, transform=ax.transAxes,
                fontsize=10, verticalalignment='top',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='wheat', alpha=0.8),
                family='monospace')
        
        # 2. 超额收益
        ax = axes[1]
        ax.bar(portfolio_returns.index, portfolio_returns['excess_return'] * 100,
               color=['#27ae60' if x > 0 else '#e74c3c' for x in portfolio_returns['excess_return']],
               alpha=0.6, width=1.0)
        ax.axhline(y=0, color='black', linewidth=0.5)
        ax.set_title('每日超额收益 (%)')
        ax.set_xlabel('日期')
        ax.set_ylabel('超额收益 (%)')
        ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        save_path = os.path.join(self.output_dir, save_name)
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"组合表现图表已保存: {save_path}")
        plt.close()
    
    def plot_factor_ic(self, factor_ic_df: pd.DataFrame, top_n=15, save_name='factor_ic.png'):
        """
        绘制因子 IC 排名
        
        参数:
            factor_ic_df: 因子 IC 统计 DataFrame
            top_n: 显示前 N 个因子
            save_name: 保存文件名
        """
        if factor_ic_df.empty:
            print("因子 IC 数据为空，跳过绘图")
            return
        
        top_factors = factor_ic_df.head(top_n)
        
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
        fig.suptitle(f'Top {top_n} 因子 IC 分析', fontsize=16, fontweight='bold')
        
        # 1. ICIR 排名
        ax1.barh(range(len(top_factors)), top_factors['ICIR'].values,
                 color='#3498db', alpha=0.7)
        ax1.set_yticks(range(len(top_factors)))
        ax1.set_yticklabels(top_factors['factor'].values)
        ax1.set_xlabel('ICIR')
        ax1.set_title('因子 ICIR 排名')
        ax1.grid(True, alpha=0.3, axis='x')
        ax1.invert_yaxis()
        
        # 2. IC vs RankIC
        ax2.scatter(top_factors['IC'], top_factors['RankIC'],
                    s=100, alpha=0.6, c=range(len(top_factors)), cmap='viridis')
        for i, row in top_factors.iterrows():
            ax2.annotate(row['factor'], (row['IC'], row['RankIC']),
                        fontsize=8, alpha=0.7)
        ax2.axhline(y=0, color='gray', linestyle='--', alpha=0.3)
        ax2.axvline(x=0, color='gray', linestyle='--', alpha=0.3)
        ax2.set_xlabel('IC')
        ax2.set_ylabel('RankIC')
        ax2.set_title('IC vs RankIC')
        ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        save_path = os.path.join(self.output_dir, save_name)
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"因子 IC 图表已保存: {save_path}")
        plt.close()
