# -*- coding: utf-8 -*-
"""
持仓股票池 SVD 分析

读取当前持仓，以持仓股票为 universe 做 SVD 市场状态分析。
回答核心问题: 我的持仓是"集体共振"还是"内部分化"？

用法:
    DB_ENV=online python data_analyst/market_monitor/portfolio_svd.py
"""
import sys
import os
import types
import importlib
import logging
from datetime import date, datetime, timedelta
from time import time

import numpy as np
import pandas as pd

# 路径设置
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def _register_dummy_parent_package():
    if 'data_analyst' not in sys.modules:
        dummy = types.ModuleType('data_analyst')
        dummy.__path__ = [os.path.join(_PROJECT_ROOT, 'data_analyst')]
        dummy.__package__ = 'data_analyst'
        sys.modules['data_analyst'] = dummy
    if 'data_analyst.market_monitor' not in sys.modules:
        dummy_sub = types.ModuleType('data_analyst.market_monitor')
        dummy_sub.__path__ = [_THIS_DIR]
        dummy_sub.__package__ = 'data_analyst.market_monitor'
        sys.modules['data_analyst.market_monitor'] = dummy_sub


def _load_sibling(name):
    import importlib.util
    full_name = f"data_analyst.market_monitor.{name}"
    filepath = os.path.join(_THIS_DIR, f"{name}.py")
    spec = importlib.util.spec_from_file_location(full_name, filepath)
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "data_analyst.market_monitor"
    sys.modules[full_name] = mod
    spec.loader.exec_module(mod)
    return mod


_register_dummy_parent_package()

_config_mod = _load_sibling("config")
_schemas_mod = _load_sibling("schemas")
_svd_engine_mod = _load_sibling("svd_engine")
_regime_classifier_mod = _load_sibling("regime_classifier")
_data_builder_mod = _load_sibling("data_builder")
_visualizer_mod = _load_sibling("visualizer")

SVDMonitorConfig = _config_mod.SVDMonitorConfig
SVDRecord = _schemas_mod.SVDRecord
MarketRegime = _schemas_mod.MarketRegime
DataBuilder = _data_builder_mod.DataBuilder
compute_svd = _svd_engine_mod.compute_svd
compute_variance_ratios = _svd_engine_mod.compute_variance_ratios
RegimeClassifier = _regime_classifier_mod.RegimeClassifier

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================
# 持仓股票池 (从 00-Current-Portfolio-Audit.md 提取)
# 仅 A 股个股，排除 ETF / 港股 / 美股
# ============================================================
PORTFOLIO_STOCKS = [
    "000408.SZ",  # 藏格矿业
    "000725.SZ",  # 京东方A (多账户合并)
    "000786.SZ",  # 北新建材
    "000792.SZ",  # 盐湖股份
    "000858.SZ",  # 五粮液
    "000983.SZ",  # 山西焦煤
    "002241.SZ",  # 歌尔股份
    "002318.SZ",  # 久立特材
    "002738.SZ",  # 中矿资源
    "300124.SZ",  # 汇川技术
    "300274.SZ",  # 阳光电源
    "300775.SZ",  # 三角防务
    "300782.SZ",  # 卓胜微
    "600011.SH",  # 华能国际
    "600015.SH",  # 华夏银行
    "600029.SH",  # 南方航空
    "600096.SH",  # 云天化
    "600188.SH",  # 兖矿能源
    "600309.SH",  # 万华化学
    "600348.SH",  # 华阳股份
    "600406.SH",  # 国电南瑞
    "600547.SH",  # 山东黄金
    "600863.SH",  # 华能水电
    "600989.SH",  # 宝丰能源
    "601155.SH",  # 新城控股
    "601225.SH",  # 陕西煤业
    "601318.SH",  # 中国平安
    "601600.SH",  # 中国铝业
    "601717.SH",  # 中创智远
    "601857.SH",  # 中国石油
    "601899.SH",  # 紫金矿业
    "603893.SH",  # 瑞芯微
    "605090.SH",  # 九丰能源
    "605499.SH",  # 东鹏饮料
]

# 持仓行业映射 (手动标注)
PORTFOLIO_INDUSTRY_MAP = {
    "000408.SZ": "有色金属", "000725.SZ": "电子", "000786.SZ": "建筑材料",
    "000792.SZ": "有色金属", "000858.SZ": "食品饮料", "000983.SZ": "煤炭",
    "002241.SZ": "电子", "002318.SZ": "钢铁", "002738.SZ": "有色金属",
    "300124.SZ": "机械设备", "300274.SZ": "电力设备", "300775.SZ": "国防军工",
    "300782.SZ": "电子", "600011.SH": "公用事业", "600015.SH": "银行",
    "600029.SH": "交通运输", "600096.SH": "化工", "600188.SH": "煤炭",
    "600309.SH": "化工", "600348.SH": "煤炭", "600406.SH": "电力设备",
    "600547.SH": "有色金属", "600863.SH": "公用事业", "600989.SH": "化工",
    "601155.SH": "房地产", "601225.SH": "煤炭", "601318.SH": "非银金融",
    "601600.SH": "有色金属", "601717.SH": "通信", "601857.SH": "石油石化",
    "601899.SH": "有色金属", "603893.SH": "电子", "605090.SH": "公用事业",
    "605499.SH": "食品饮料",
}


def run_portfolio_svd():
    """对持仓股票池做 SVD 分析"""
    # 配置: 持仓只有 34 只票，用更小的窗口
    config = SVDMonitorConfig()
    config.windows = {20: 5, 60: 5}
    config.min_stock_count = 15  # 持仓 34 只，至少 15 只有效

    data_builder = DataBuilder(config)
    classifier = RegimeClassifier(config)

    end_date = date.today().strftime('%Y-%m-%d')
    start_date = (date.today() - timedelta(days=400)).strftime('%Y-%m-%d')

    logger.info("=" * 60)
    logger.info(f"持仓 SVD 分析: {len(PORTFOLIO_STOCKS)} 只股票")
    logger.info(f"日期范围: {start_date} ~ {end_date}")
    logger.info(f"窗口配置: {config.windows}")
    logger.info("=" * 60)

    t0 = time()

    # 1. 加载数据
    logger.info("[1/3] 加载收益率数据...")
    returns_df = data_builder.load_returns(start_date, end_date, PORTFOLIO_STOCKS)
    if returns_df.empty:
        logger.error("数据加载失败")
        return

    # 检查实际匹配到的股票
    matched = [s for s in PORTFOLIO_STOCKS if s in returns_df.columns]
    logger.info(f"匹配到 {len(matched)}/{len(PORTFOLIO_STOCKS)} 只股票")

    # 2. 滚动窗口 SVD
    logger.info("[2/3] 滚动窗口 SVD 计算...")
    all_records = []
    T = len(returns_df)

    for window_size, step in config.windows.items():
        for start_idx in range(0, T - window_size, step):
            mid_idx = start_idx + window_size // 2
            mid_date = returns_df.index[mid_idx]
            calc_date = mid_date.date() if hasattr(mid_date, 'date') else mid_date

            matrix, stock_count, valid_stocks = data_builder.build_window_matrix(
                returns_df, start_idx, window_size, matched
            )

            if matrix is None:
                continue

            _, sigma, _ = compute_svd(matrix, config.n_components)
            ratios = compute_variance_ratios(sigma)

            record = SVDRecord(
                calc_date=calc_date,
                window_size=window_size,
                universe_type="PORTFOLIO",
                universe_id="当前持仓",
                top1_var_ratio=ratios['top1_var_ratio'],
                top3_var_ratio=ratios['top3_var_ratio'],
                top5_var_ratio=ratios['top5_var_ratio'],
                reconstruction_error=ratios['reconstruction_error'],
                stock_count=stock_count,
                market_state="",
                is_mutation=0,
            )
            all_records.append(record)

        logger.info(f"  窗口 {window_size}日: {len([r for r in all_records if r.window_size == window_size])} 个计算点")

    if not all_records:
        logger.error("无有效 SVD 结果")
        return

    # 3. 市场状态分类 (使用分位数阈值，因为只有 34 只票)
    logger.info("[3/3] 市场状态分类...")
    results_df = pd.DataFrame([r.model_dump() for r in all_records])
    unique_dates = sorted(results_df['calc_date'].unique())
    regimes = []

    for calc_date in unique_dates:
        regime = classifier.classify(results_df, calc_date, use_percentile=True)
        regimes.append(regime)
        for r in all_records:
            if r.calc_date == calc_date:
                r.market_state = regime.market_state
                r.is_mutation = 1 if regime.is_mutation else 0

    latest = regimes[-1]
    logger.info(f"  最新状态: {latest.market_state} (score={latest.final_score:.1%})")

    elapsed = time() - t0
    logger.info(f"计算完成，耗时 {elapsed:.1f}s")

    # 4. 生成报告
    return generate_portfolio_report(
        all_records, regimes, results_df, latest, returns_df, matched
    )


def generate_portfolio_report(records, regimes, results_df, latest_regime,
                              returns_df, matched_stocks):
    """生成持仓 SVD 分析报告"""

    output_dir = "/Users/zhaobo/Documents/notes/Finance/Positions"
    output_path = os.path.join(output_dir, "Portfolio-SVD-Analysis.md")

    lines = []
    lines.append("# 持仓 SVD 市场结构分析")
    lines.append("")
    lines.append(f"> **生成日期**: {date.today().strftime('%Y-%m-%d')}")
    lines.append(f"> **股票数量**: {len(matched_stocks)} 只")
    lines.append(f"> **分析方法**: 滚动 SVD (20日/60日窗口)")
    lines.append(f"> **阈值模式**: 历史分位数 (70%/30%)，适配小样本")
    lines.append("")

    # 核心结论
    lines.append("## 核心结论")
    lines.append("")
    state = latest_regime.market_state
    score = latest_regime.final_score
    if state == "齐涨齐跌":
        lines.append(f"**持仓状态: Beta 共振 (F1={score:.1%})**")
        lines.append("")
        lines.append("> 你的持仓高度同步涨跌，Beta 属性强。这意味着:")
        lines.append("> - 个股选择几乎没有 Alpha 贡献")
        lines.append("> - 大盘下跌时，持仓几乎无法分散风险")
        lines.append("> - 建议: 减少同质化持仓，增加低相关性标的")
    elif state == "板块分化":
        lines.append(f"**持仓状态: 板块分化 (F1={score:.1%})**")
        lines.append("")
        lines.append("> 你的持仓存在板块层面的联动，但板块间有一定分化。")
        lines.append("> - 行业配置有一定分散效果")
        lines.append("> - 但仍需警惕系统性风险")
    else:
        lines.append(f"**持仓状态: 个股行情 (F1={score:.1%})**")
        lines.append("")
        lines.append("> 你的持仓内部分化明显，Alpha 空间存在。")
        lines.append("> - 个股选择有差异化收益")
        lines.append("> - 持仓具有一定的风险分散效果")
    lines.append("")

    # F1 历史趋势
    lines.append("## F1 方差占比趋势 (60日窗口)")
    lines.append("")
    hist_60 = results_df[results_df['window_size'] == 60].sort_values('calc_date')
    if not hist_60.empty:
        lines.append("| 日期 | F1 占比 | Top3 占比 | 重构误差 | 状态 |")
        lines.append("|------|---------|----------|---------|------|")
        for _, row in hist_60.iterrows():
            d = row['calc_date']
            date_str = d.strftime('%Y-%m-%d') if hasattr(d, 'strftime') else str(d)
            lines.append(
                f"| {date_str} | {row['top1_var_ratio']:.1%} | "
                f"{row['top3_var_ratio']:.1%} | "
                f"{row['reconstruction_error']:.1%} | {row['market_state']} |"
            )
    lines.append("")

    # 行业分布分析
    lines.append("## 持仓行业分布")
    lines.append("")
    industry_counts = {}
    for code in matched_stocks:
        ind = PORTFOLIO_INDUSTRY_MAP.get(code, "未知")
        industry_counts[ind] = industry_counts.get(ind, 0) + 1

    lines.append("| 行业 | 股票数 | 占比 |")
    lines.append("|------|--------|------|")
    for ind, count in sorted(industry_counts.items(), key=lambda x: -x[1]):
        pct = count / len(matched_stocks) * 100
        lines.append(f"| {ind} | {count} | {pct:.0f}% |")
    lines.append("")

    # 集中度警告
    max_ind = max(industry_counts, key=industry_counts.get)
    max_pct = industry_counts[max_ind] / len(matched_stocks) * 100
    if max_pct > 20:
        lines.append(f"> **注意**: {max_ind} 行业占比 {max_pct:.0f}%，集中度偏高。")
        lines.append("> 这会导致该行业波动对整个持仓产生过大影响。")
        lines.append("")

    # 持仓个股列表
    lines.append("## 持仓股票列表")
    lines.append("")
    lines.append("| 代码 | 行业 |")
    lines.append("|------|------|")
    for code in sorted(matched_stocks):
        ind = PORTFOLIO_INDUSTRY_MAP.get(code, "未知")
        lines.append(f"| {code} | {ind} |")
    lines.append("")

    # 策略建议
    lines.append("## 策略建议")
    lines.append("")
    lines.append("### 当前持仓结构问题")
    lines.append("")

    # 检查行业集中度
    if max_pct > 20:
        lines.append(f"1. **行业过度集中**: {max_ind} 占 {max_pct:.0f}%")
        lines.append(f"   - 有色金属/煤炭/化工等周期性行业合计占比较高")
        lines.append(f"   - 建议降低周期板块权重，增加防御性/成长性标的")
        lines.append("")

    # 检查 F1 趋势
    if len(hist_60) >= 5:
        recent_f1 = hist_60['top1_var_ratio'].tail(3).mean()
        early_f1 = hist_60['top1_var_ratio'].head(3).mean()
        if recent_f1 > early_f1 * 1.2:
            lines.append("2. **持仓共振趋势上升**: F1 近期持续走高")
            lines.append("   - Beta 属性增强，个股差异在消失")
            lines.append("   - 市场可能进入系统性风险阶段")
            lines.append("   - 建议: 考虑降低整体仓位")
        elif recent_f1 < early_f1 * 0.8:
            lines.append("2. **持仓分化趋势增强**: F1 近期持续走低")
            lines.append("   - Alpha 空间在打开，个股选择更重要")
            lines.append("   - 适合做强弱切换和个股精选")
        else:
            lines.append("2. **持仓结构相对稳定**: F1 无明显趋势变化")
    lines.append("")

    report_text = "\n".join(lines)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report_text)

    logger.info(f"报告已保存: {output_path}")
    return output_path


if __name__ == '__main__':
    run_portfolio_svd()
