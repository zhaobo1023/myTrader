# -*- coding: utf-8 -*-
"""
技术分析图表生成器

生成专业的K线图，包含：
- 日K蜡烛图 + MA均线系统
- 关键点位标注（止损位/压力位/支撑位/成本价）
- 信号标记（金叉/死叉/背离等）
- 副图：成交量 + MACD
- 信息面板
"""
import os
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)

# 尝试导入绘图库
try:
    import matplotlib
    matplotlib.use('Agg')  # 非交互式后端
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import matplotlib.dates as mdates
    from matplotlib.lines import Line2D
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    logger.warning("matplotlib 未安装，图表功能不可用")

try:
    import mplfinance as mpf
    HAS_MPLFINANCE = True
except ImportError:
    HAS_MPLFINANCE = False
    logger.warning("mplfinance 未安装，将使用 matplotlib 绘制K线")


class ChartGenerator:
    """技术分析图表生成器"""

    # 颜色配置
    COLORS = {
        'up': '#e74c3c',        # 上涨红色
        'down': '#27ae60',      # 下跌绿色
        'ma5': '#f39c12',       # MA5 橙色
        'ma20': '#3498db',      # MA20 蓝色
        'ma60': '#9b59b6',      # MA60 紫色
        'ma250': '#1abc9c',     # MA250 青色
        'stop_loss': '#c0392b', # 止损位 深红
        'resistance': '#e67e22',# 压力位 橙色
        'support': '#27ae60',   # 支撑位 绿色
        'cost': '#2980b9',      # 成本价 蓝色
        'volume_up': '#e74c3c', # 成交量上涨
        'volume_down': '#27ae60',# 成交量下跌
        'macd_positive': '#e74c3c',
        'macd_negative': '#27ae60',
        'dif': '#3498db',
        'dea': '#e67e22',
        'signal_buy': '#e74c3c',
        'signal_sell': '#27ae60',
        'boll_upper': '#95a5a6',
        'boll_middle': '#bdc3c7',
        'boll_lower': '#95a5a6',
    }

    def __init__(self, output_dir: str = "output/charts"):
        """
        初始化图表生成器

        Args:
            output_dir: 图表输出目录
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 设置中文字体
        if HAS_MATPLOTLIB:
            plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'DejaVu Sans']
            plt.rcParams['axes.unicode_minus'] = False

    def generate_chart(
        self,
        df: pd.DataFrame,
        stock_code: str,
        stock_name: str,
        analysis_result: Dict[str, Any],
        scan_date: datetime = None,
        lookback_days: int = 60
    ) -> Optional[str]:
        """
        生成单只股票的技术分析图表

        Args:
            df: 包含OHLCV和技术指标的DataFrame
            stock_code: 股票代码
            stock_name: 股票名称
            analysis_result: 分析结果字典（包含signals, trend, stop_loss等）
            scan_date: 扫描日期
            lookback_days: 显示的K线天数

        Returns:
            图表文件路径，失败返回None
        """
        if not HAS_MATPLOTLIB:
            logger.error("matplotlib 未安装，无法生成图表")
            return None

        if df.empty:
            logger.warning(f"{stock_code} 数据为空，跳过图表生成")
            return None

        if scan_date is None:
            scan_date = datetime.now()

        # 筛选该股票的数据
        stock_df = df[df['stock_code'] == stock_code].copy()
        if stock_df.empty:
            logger.warning(f"{stock_code} 无数据")
            return None

        # 取最近N天数据
        stock_df = stock_df.sort_values('trade_date').tail(lookback_days)
        stock_df = stock_df.set_index('trade_date')

        try:
            if HAS_MPLFINANCE:
                filepath = self._generate_with_mplfinance(
                    stock_df, stock_code, stock_name, analysis_result, scan_date
                )
            else:
                filepath = self._generate_with_matplotlib(
                    stock_df, stock_code, stock_name, analysis_result, scan_date
                )
            return filepath
        except Exception as e:
            logger.error(f"生成 {stock_code} 图表失败: {e}")
            return None

    def _generate_with_mplfinance(
        self,
        df: pd.DataFrame,
        stock_code: str,
        stock_name: str,
        analysis_result: Dict[str, Any],
        scan_date: datetime
    ) -> str:
        """使用 mplfinance 生成图表"""

        # 准备数据（mplfinance 需要特定列名）
        plot_df = df.rename(columns={
            'open': 'Open',
            'high': 'High',
            'low': 'Low',
            'close': 'Close',
            'volume': 'Volume'
        })

        # 确保索引是 DatetimeIndex
        if not isinstance(plot_df.index, pd.DatetimeIndex):
            plot_df.index = pd.to_datetime(plot_df.index)

        # 构建均线叠加
        add_plots = []

        # MA均线
        ma_colors = {
            'ma5': self.COLORS['ma5'],
            'ma20': self.COLORS['ma20'],
            'ma60': self.COLORS['ma60'],
            'ma250': self.COLORS['ma250'],
        }
        for ma_col, color in ma_colors.items():
            if ma_col in df.columns and not df[ma_col].isna().all():
                add_plots.append(mpf.make_addplot(
                    df[ma_col], color=color, width=1.0, label=ma_col.upper()
                ))

        # BOLL bands
        if 'boll_upper' in df.columns and not df['boll_upper'].isna().all():
            add_plots.append(mpf.make_addplot(
                df['boll_upper'], color=self.COLORS['boll_upper'],
                width=0.8, linestyle='--', alpha=0.7
            ))
        if 'boll_middle' in df.columns and not df['boll_middle'].isna().all():
            add_plots.append(mpf.make_addplot(
                df['boll_middle'], color=self.COLORS['boll_middle'],
                width=0.8, linestyle=':', alpha=0.5
            ))
        if 'boll_lower' in df.columns and not df['boll_lower'].isna().all():
            add_plots.append(mpf.make_addplot(
                df['boll_lower'], color=self.COLORS['boll_lower'],
                width=0.8, linestyle='--', alpha=0.7
            ))

        # 关键价位水平线
        hlines_dict = self._build_hlines(df, analysis_result)

        # MACD 副图
        macd_plots = self._build_macd_addplot(df)
        add_plots.extend(macd_plots)

        # 自定义样式
        mc = mpf.make_marketcolors(
            up=self.COLORS['up'],
            down=self.COLORS['down'],
            edge='inherit',
            wick='inherit',
            volume={'up': self.COLORS['volume_up'], 'down': self.COLORS['volume_down']}
        )
        style = mpf.make_mpf_style(
            marketcolors=mc,
            gridstyle='-',
            gridcolor='#e0e0e0',
            figcolor='white',
            facecolor='white'
        )

        # 标题
        title = f"{stock_code} {stock_name} - {scan_date.strftime('%Y-%m-%d')}"
        trend = analysis_result.get('trend', '')
        if trend:
            title += f" [{trend}]"

        # 生成图表
        filename = f"{stock_code.replace('.', '_')}_{scan_date.strftime('%Y%m%d')}.png"
        filepath = self.output_dir / filename

        fig, axes = mpf.plot(
            plot_df,
            type='candle',
            style=style,
            title=title,
            ylabel='价格',
            ylabel_lower='成交量',
            volume=True,
            addplot=add_plots if add_plots else None,
            hlines=hlines_dict if hlines_dict else None,
            figsize=(14, 10),
            returnfig=True,
            panel_ratios=(4, 1, 1) if macd_plots else (4, 1),
        )

        # 添加图例和信息面板
        self._add_legend_and_info(fig, axes[0], df, analysis_result)

        # 保存
        fig.savefig(filepath, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close(fig)

        logger.info(f"图表已生成: {filepath}")
        return str(filepath)

    def _generate_with_matplotlib(
        self,
        df: pd.DataFrame,
        stock_code: str,
        stock_name: str,
        analysis_result: Dict[str, Any],
        scan_date: datetime
    ) -> str:
        """使用纯 matplotlib 生成图表（备用方案）"""

        fig, axes = plt.subplots(
            3, 1, figsize=(14, 10),
            gridspec_kw={'height_ratios': [4, 1, 1]},
            sharex=True
        )
        ax_price, ax_volume, ax_macd = axes

        n = len(df)
        x = np.arange(n)

        # 绘制K线
        self._draw_candlestick(ax_price, df, x)

        # 绘制均线
        ma_configs = [
            ('ma5', self.COLORS['ma5'], 'MA5'),
            ('ma20', self.COLORS['ma20'], 'MA20'),
            ('ma60', self.COLORS['ma60'], 'MA60'),
            ('ma250', self.COLORS['ma250'], 'MA250'),
        ]
        for col, color, label in ma_configs:
            if col in df.columns and not df[col].isna().all():
                ax_price.plot(x, df[col].values, color=color, linewidth=1.0, label=label)

        # BOLL bands
        if 'boll_upper' in df.columns:
            ax_price.plot(x, df['boll_upper'].values,
                          color=self.COLORS['boll_upper'], linewidth=0.8,
                          linestyle='--', alpha=0.7, label='BOLL')
            ax_price.plot(x, df['boll_middle'].values,
                          color=self.COLORS['boll_middle'], linewidth=0.8,
                          linestyle=':', alpha=0.5)
            ax_price.plot(x, df['boll_lower'].values,
                          color=self.COLORS['boll_lower'], linewidth=0.8,
                          linestyle='--', alpha=0.7)

        # 绘制关键价位
        self._draw_key_levels(ax_price, df, analysis_result, n)

        # 绘制信号标记
        self._draw_signals(ax_price, df, analysis_result, x)

        # 绘制成交量
        self._draw_volume(ax_volume, df, x)

        # 绘制MACD
        self._draw_macd(ax_macd, df, x)

        # 设置X轴标签
        self._set_xaxis_labels(ax_macd, df)

        # 标题和图例
        title = f"{stock_code} {stock_name} - {scan_date.strftime('%Y-%m-%d')}"
        trend = analysis_result.get('trend', '')
        if trend:
            title += f" [{trend}]"
        ax_price.set_title(title, fontsize=14, fontweight='bold')
        ax_price.legend(loc='upper left', fontsize=8)
        ax_price.set_ylabel('价格')
        ax_volume.set_ylabel('成交量')
        ax_macd.set_ylabel('MACD')

        # 网格
        for ax in axes:
            ax.grid(True, alpha=0.3)

        # 添加信息面板
        self._add_info_panel(fig, df, analysis_result)

        plt.tight_layout()

        # 保存
        filename = f"{stock_code.replace('.', '_')}_{scan_date.strftime('%Y%m%d')}.png"
        filepath = self.output_dir / filename
        fig.savefig(filepath, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close(fig)

        logger.info(f"图表已生成: {filepath}")
        return str(filepath)

    def _draw_candlestick(self, ax, df: pd.DataFrame, x: np.ndarray):
        """绘制K线蜡烛图"""
        opens = df['open'].values
        highs = df['high'].values
        lows = df['low'].values
        closes = df['close'].values

        width = 0.6
        width2 = 0.1

        for i in range(len(df)):
            if closes[i] >= opens[i]:
                color = self.COLORS['up']
                body_low = opens[i]
                body_high = closes[i]
            else:
                color = self.COLORS['down']
                body_low = closes[i]
                body_high = opens[i]

            # 影线
            ax.plot([x[i], x[i]], [lows[i], highs[i]], color=color, linewidth=0.8)
            # 实体
            ax.bar(x[i], body_high - body_low, bottom=body_low, width=width,
                   color=color, edgecolor=color)

    def _draw_key_levels(self, ax, df: pd.DataFrame, analysis_result: Dict, n: int):
        """绘制关键价位水平线"""
        latest = df.iloc[-1]

        # 止损位
        stop_loss = analysis_result.get('stop_loss')
        if stop_loss and stop_loss.get('stop_price'):
            price = stop_loss['stop_price']
            ax.axhline(y=price, color=self.COLORS['stop_loss'], linestyle='--',
                      linewidth=1.5, alpha=0.8, label=f"止损 {price:.2f}")
            ax.text(n - 1, price, f" 止损 {price:.2f}", fontsize=8,
                   color=self.COLORS['stop_loss'], va='center')

        # 成本价
        cost = analysis_result.get('cost')
        if cost:
            ax.axhline(y=cost, color=self.COLORS['cost'], linestyle='-.',
                      linewidth=1.5, alpha=0.8, label=f"成本 {cost:.2f}")
            ax.text(n - 1, cost, f" 成本 {cost:.2f}", fontsize=8,
                   color=self.COLORS['cost'], va='center')

        # MA压力/支撑位
        close = latest['close']
        for ma_col, label in [('ma20', 'MA20'), ('ma60', 'MA60')]:
            if ma_col in df.columns:
                ma_val = latest[ma_col]
                if pd.notna(ma_val):
                    if ma_val > close * 1.02:  # 压力位
                        ax.axhline(y=ma_val, color=self.COLORS['resistance'],
                                  linestyle=':', linewidth=1.0, alpha=0.6)
                    elif ma_val < close * 0.98:  # 支撑位
                        ax.axhline(y=ma_val, color=self.COLORS['support'],
                                  linestyle=':', linewidth=1.0, alpha=0.6)

        # 20日高低点
        if 'high_20' in df.columns:
            high_20 = latest.get('high_20')
            if pd.notna(high_20) and high_20 > close:
                ax.axhline(y=high_20, color=self.COLORS['resistance'],
                          linestyle='--', linewidth=1.0, alpha=0.5)
                ax.text(0, high_20, f"20日高 {high_20:.2f} ", fontsize=7,
                       color=self.COLORS['resistance'], va='center', ha='right')

        if 'low_20' in df.columns:
            low_20 = latest.get('low_20')
            if pd.notna(low_20) and low_20 < close:
                ax.axhline(y=low_20, color=self.COLORS['support'],
                          linestyle='--', linewidth=1.0, alpha=0.5)
                ax.text(0, low_20, f"20日低 {low_20:.2f} ", fontsize=7,
                       color=self.COLORS['support'], va='center', ha='right')

    def _draw_signals(self, ax, df: pd.DataFrame, analysis_result: Dict, x: np.ndarray):
        """绘制信号标记"""
        signals = analysis_result.get('signals', [])
        if not signals:
            return

        latest_x = x[-1]
        latest = df.iloc[-1]

        for sig in signals:
            sig_name = sig.name if hasattr(sig, 'name') else str(sig)
            sig_level = sig.level.value if hasattr(sig, 'level') else ''

            # 根据信号类型选择标记
            if '金叉' in sig_name:
                marker = '^'
                color = self.COLORS['signal_buy']
                y_pos = latest['low'] * 0.98
            elif '死叉' in sig_name:
                marker = 'v'
                color = self.COLORS['signal_sell']
                y_pos = latest['high'] * 1.02
            elif '突破' in sig_name or '新高' in sig_name:
                marker = '*'
                color = self.COLORS['signal_buy']
                y_pos = latest['high'] * 1.02
            elif '跌破' in sig_name:
                marker = 'x'
                color = self.COLORS['signal_sell']
                y_pos = latest['low'] * 0.98
            else:
                continue

            ax.scatter(latest_x, y_pos, marker=marker, s=150, color=color,
                      edgecolors='black', linewidths=0.5, zorder=10)
            ax.annotate(sig_name, (latest_x, y_pos),
                       textcoords="offset points", xytext=(5, 5),
                       fontsize=8, color=color,
                       bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.7))

    def _draw_volume(self, ax, df: pd.DataFrame, x: np.ndarray):
        """绘制成交量柱状图"""
        volumes = df['volume'].values
        colors = [self.COLORS['volume_up'] if df['close'].iloc[i] >= df['open'].iloc[i]
                  else self.COLORS['volume_down'] for i in range(len(df))]

        ax.bar(x, volumes, color=colors, alpha=0.7, width=0.6)

        # 5日均量线
        if 'vol_ma5' in df.columns:
            ax.plot(x, df['vol_ma5'].values, color='#f39c12', linewidth=1.0, label='VOL MA5')

    def _draw_macd(self, ax, df: pd.DataFrame, x: np.ndarray):
        """绘制MACD"""
        if 'macd_hist' not in df.columns:
            return

        hist = df['macd_hist'].values
        colors = [self.COLORS['macd_positive'] if h >= 0 else self.COLORS['macd_negative']
                  for h in hist]

        ax.bar(x, hist, color=colors, alpha=0.7, width=0.6)

        if 'macd_dif' in df.columns:
            ax.plot(x, df['macd_dif'].values, color=self.COLORS['dif'],
                   linewidth=1.0, label='DIF')
        if 'macd_dea' in df.columns:
            ax.plot(x, df['macd_dea'].values, color=self.COLORS['dea'],
                   linewidth=1.0, label='DEA')

        ax.axhline(y=0, color='gray', linewidth=0.5)
        ax.legend(loc='upper left', fontsize=7)

    def _set_xaxis_labels(self, ax, df: pd.DataFrame):
        """设置X轴日期标签"""
        n = len(df)
        step = max(1, n // 10)
        tick_positions = list(range(0, n, step))
        if (n - 1) not in tick_positions:
            tick_positions.append(n - 1)

        tick_labels = [df.index[i].strftime('%m-%d') for i in tick_positions]
        ax.set_xticks(tick_positions)
        ax.set_xticklabels(tick_labels, rotation=45, ha='right', fontsize=8)

    def _build_hlines(self, df: pd.DataFrame, analysis_result: Dict) -> Optional[Dict]:
        """构建 mplfinance 的水平线配置"""
        hlines = {'hlines': [], 'colors': [], 'linestyle': [], 'linewidths': []}

        # 止损位
        stop_loss = analysis_result.get('stop_loss')
        if stop_loss and stop_loss.get('stop_price'):
            hlines['hlines'].append(stop_loss['stop_price'])
            hlines['colors'].append(self.COLORS['stop_loss'])
            hlines['linestyle'].append('--')
            hlines['linewidths'].append(1.5)

        # 成本价
        cost = analysis_result.get('cost')
        if cost:
            hlines['hlines'].append(cost)
            hlines['colors'].append(self.COLORS['cost'])
            hlines['linestyle'].append('-.')
            hlines['linewidths'].append(1.5)

        return hlines if hlines['hlines'] else None

    def _build_macd_addplot(self, df: pd.DataFrame) -> List:
        """构建 MACD 副图"""
        plots = []

        if 'macd_hist' not in df.columns:
            return plots

        # MACD 柱状图
        hist = df['macd_hist']
        hist_colors = [self.COLORS['macd_positive'] if h >= 0 else self.COLORS['macd_negative']
                       for h in hist]

        plots.append(mpf.make_addplot(
            hist, type='bar', panel=2, color=hist_colors, alpha=0.7
        ))

        # DIF/DEA 线
        if 'macd_dif' in df.columns:
            plots.append(mpf.make_addplot(
                df['macd_dif'], panel=2, color=self.COLORS['dif'], width=1.0
            ))
        if 'macd_dea' in df.columns:
            plots.append(mpf.make_addplot(
                df['macd_dea'], panel=2, color=self.COLORS['dea'], width=1.0
            ))

        return plots

    def _add_legend_and_info(self, fig, ax, df: pd.DataFrame, analysis_result: Dict):
        """添加图例和信息面板"""
        # 构建图例
        legend_elements = [
            Line2D([0], [0], color=self.COLORS['ma5'], linewidth=1, label='MA5'),
            Line2D([0], [0], color=self.COLORS['ma20'], linewidth=1, label='MA20'),
            Line2D([0], [0], color=self.COLORS['ma60'], linewidth=1, label='MA60'),
            Line2D([0], [0], color=self.COLORS['ma250'], linewidth=1, label='MA250'),
            Line2D([0], [0], color=self.COLORS['boll_upper'], linewidth=0.8,
                   linestyle='--', label='BOLL'),
        ]

        stop_loss = analysis_result.get('stop_loss')
        if stop_loss:
            legend_elements.append(
                Line2D([0], [0], color=self.COLORS['stop_loss'], linestyle='--',
                      linewidth=1.5, label=f"止损 {stop_loss.get('stop_price', 0):.2f}")
            )

        ax.legend(handles=legend_elements, loc='upper left', fontsize=8)

    def _add_info_panel(self, fig, df: pd.DataFrame, analysis_result: Dict):
        """添加信息面板（右侧）"""
        latest = df.iloc[-1]

        info_lines = []

        # 趋势
        trend = analysis_result.get('trend', '')
        if trend:
            info_lines.append(f"趋势: {trend}")

        # 盈亏
        pnl = analysis_result.get('pnl_pct')
        if pnl is not None:
            info_lines.append(f"盈亏: {pnl:+.2f}%")

        # RSI
        rsi = latest.get('rsi')
        if pd.notna(rsi):
            info_lines.append(f"RSI: {rsi:.1f}")

        # RPS
        rps = analysis_result.get('rps')
        if rps is not None and pd.notna(rps):
            info_lines.append(f"RPS: {rps:.0f}")

        if info_lines:
            info_text = "\n".join(info_lines)
            fig.text(0.98, 0.5, info_text, fontsize=9, va='center', ha='right',
                    bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))


def generate_stock_chart(
    df: pd.DataFrame,
    stock_code: str,
    stock_name: str,
    analysis_result: Dict[str, Any],
    output_dir: str = "output/charts",
    scan_date: datetime = None
) -> Optional[str]:
    """
    便捷函数：生成单只股票的技术分析图表

    Args:
        df: 包含OHLCV和技术指标的DataFrame
        stock_code: 股票代码
        stock_name: 股票名称
        analysis_result: 分析结果字典
        output_dir: 输出目录
        scan_date: 扫描日期

    Returns:
        图表文件路径
    """
    generator = ChartGenerator(output_dir)
    return generator.generate_chart(
        df, stock_code, stock_name, analysis_result, scan_date
    )
