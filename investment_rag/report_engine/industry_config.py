# -*- coding: utf-8 -*-
"""
行业差异化分析配置 v1.0

每个行业有独立的分析焦点、数据需求、RAG查询和估值方法。
当前支持：银行（BANK）、通用（DEFAULT）。
"""
from dataclasses import dataclass, field
from typing import List, Optional

# IndustryType 复用 research/industry_classifier.py 的枚举
# 但此处单独定义字符串常量，避免强依赖
INDUSTRY_BANK = "bank"
INDUSTRY_NON_FERROUS = "non_ferrous"
INDUSTRY_DEFAULT = "default"


@dataclass
class IndustryAnalysisConfig:
    """
    行业差异化分析配置。

    每个字段对应五步法中某一步的额外注入内容。
    字段为空时，使用通用模板默认值。
    """
    industry_type: str = INDUSTRY_DEFAULT
    industry_name: str = "通用"

    # Step1 额外关注领域（注入 STEP1_PROMPT 的 {step1_focus_areas}）
    step1_focus_areas: str = ""

    # Step2 护城河评估维度（注入 STEP2_PROMPT 的 {moat_dimensions}）
    moat_dimensions: str = ""

    # Step3 估值方法说明（注入 STEP3_PROMPT 的 {valuation_note}）
    valuation_note: str = ""

    # Step5 风险维度补充（注入 STEP5_PROMPT 的 {risk_dimensions}）
    risk_dimensions: str = ""

    # 行业专属数据标志（由 FiveStepAnalyzer 判断并调用对应 data_tools 方法）
    needs_bank_indicators: bool = False

    # 行业专属 RAG 查询（追加到每步通用查询之后）
    extra_rag_queries: List[str] = field(default_factory=list)


# ============================================================
# 银行行业配置
# ============================================================

BANK_CONFIG = IndustryAnalysisConfig(
    industry_type=INDUSTRY_BANK,
    industry_name="银行",
    needs_bank_indicators=True,

    step1_focus_areas="""
**银行行业专项关注（必须覆盖以下指标，替代通用筛选方向）**：
1. 资产质量三重验证
   - NPL率2（逾期90天以上+关注类重组贷款/总贷款）vs 官方不良率，测算"隐藏不良"空间
   - 拨备覆盖率充足性：若NPL率2 >> 官方NPL率，拨备覆盖率存在虚高
   - 逾期贷款/不良贷款比值：>1 说明不良认定保守，存在未来上调压力
2. 净息差（NIM）趋势
   - 当前NIM绝对值 + 同比变动bps + 行业均值对比
   - 若NIM同比收窄超过10bps，须分析驱动因子（存款成本/贷款定价/结构）
3. 真实股权增长
   - 税后RORWA（风险资产回报率）- 股息率 = 内生资本补充能力
   - 若内生补充率 < 0，须依赖再融资，摊薄风险高
4. 债券投资三分类
   - 以公允价值计量且变动计入其他综合收益（FVOCI）占比
   - 利率下行时FVOCI浮盈进净资产 vs OCI重分类风险
""",

    moat_dimensions="""
**银行护城河评估维度**（替代通用护城河框架）：
- 低成本负债来源：活期存款占比（Demand Deposit Ratio）+ 存款成本率绝对值
- 客群粘性：对公大客户集中度 + 零售AUM增速
- 风险定价能力：风险调整后净息差（NIM - 信用成本）趋势
- 量化证据必须包含：核心负债成本、不良生成率（Credit Cost）
""",

    valuation_note="""
**银行估值方法**（替代 PE 分析）：
- 主估值法：PB-ROE 框架
  - 合理PB = ROE / (Ke - g)，其中 Ke 约10-11%，g 约3-5%
  - 当前PB vs 历史均值 vs 同业中位数（三重对比）
- 辅助估值：股息率 vs 10年期国债收益率利差（> 200bps = 有安全边际）
- 切忌使用 PE/EV-EBITDA，银行资产负债表与非金融企业差异过大
""",

    risk_dimensions="""
**银行专项风险**：
- 信用风险：不良生成率（Credit Cost）突增、城投/房地产贷款集中度
- 利率风险：NIM下行斜率 vs 再定价缺口（若未披露，标注为信息盲区）
- 资本充足率：核心一级资本充足率（CET1）与监管红线距离
- 流动性风险：LCR（流动性覆盖率）+ 对同业负债依赖度
""",

    extra_rag_queries=[
        "{stock_name} 不良贷款 不良率 逾期贷款 拨备覆盖率 资产质量",
        "{stock_name} 净息差 NIM 存款成本 贷款利率 利差",
        "{stock_name} 城投 房地产贷款 集中度 风险敞口",
        "{stock_name} 资本充足率 CET1 再融资 配股 定增",
    ],
)


# ============================================================
# 有色金属行业配置（占位，后续补充）
# ============================================================

NON_FERROUS_CONFIG = IndustryAnalysisConfig(
    industry_type=INDUSTRY_NON_FERROUS,
    industry_name="有色金属",

    step1_focus_areas="""
**有色金属行业专项关注**：
1. 产品价格敏感性：主力金属品种（铜/铝/锂/黄金）价格同比变动 vs 营收/毛利弹性
2. 成本结构：吨成本分解（矿山自供率、能源成本占比），判断是否具备成本护城河
3. 资源储量更新：探明储量增减 + 矿山寿命，影响长期可持续性
4. 副产品贡献：多金属矿山副产品收入占比，影响真实毛利率
""",

    moat_dimensions="""
**有色金属护城河评估维度**：
- 资源禀赋：矿山品位 vs 行业均值、自供率（自产矿/冶炼产能比）
- 成本曲线位置：公司 C1 成本在全球成本曲线中的百分位
- 量化证据必须包含：吨成本、自供率、矿山储量年限
""",

    valuation_note="""
**有色金属估值方法**：
- 资源类：EV/资源量（美元/吨等效金属量）+ DCF（需假设长期金属价格）
- 冶炼类：EV/EBITDA（周期顶/底估值区间对比）
- 注意：当前金属价格是顺周期输入，需敏感性分析
""",

    risk_dimensions="""
**有色金属专项风险**：
- 商品价格风险：主力品种价格下跌 10% 对毛利的敏感性测算
- 汇率风险：若海外矿山收入为美元，汇率波动影响
- 资源税/环保政策：国内外矿山监管收紧风险
- 库存周期：下游去库存导致短期需求萎缩
""",

    extra_rag_queries=[
        "{stock_name} 铜价 铝价 锂价 金价 商品价格 价格走势",
        "{stock_name} 矿山 产量 储量 品位 采矿成本",
        "{stock_name} 海外矿山 并购 资源整合 扩产计划",
    ],
)


# ============================================================
# 默认（通用）配置
# ============================================================

DEFAULT_CONFIG = IndustryAnalysisConfig(
    industry_type=INDUSTRY_DEFAULT,
    industry_name="通用",
    # 所有字段为空，使用 prompts.py 的通用模板
)


# ============================================================
# 配置获取函数
# ============================================================

# SW 行业名称 -> IndustryAnalysisConfig 的映射
_SW_NAME_TO_CONFIG = {
    "银行": BANK_CONFIG,
    "铜": NON_FERROUS_CONFIG,
    "铝": NON_FERROUS_CONFIG,
    "黄金": NON_FERROUS_CONFIG,
    "工业金属": NON_FERROUS_CONFIG,
    "贵金属": NON_FERROUS_CONFIG,
    "有色金属": NON_FERROUS_CONFIG,
}

# IndustryType 枚举值 -> 配置（与 research/industry_classifier.py 对接）
_INDUSTRY_TYPE_TO_CONFIG = {
    "FINANCIAL": BANK_CONFIG,
    "bank": BANK_CONFIG,
    "non_ferrous": NON_FERROUS_CONFIG,
    "default": DEFAULT_CONFIG,
}


def get_industry_config_by_sw_name(sw_name: str) -> IndustryAnalysisConfig:
    """
    根据申万行业名称获取行业配置。
    部分匹配：检查 sw_name 是否包含关键词。
    """
    for keyword, config in _SW_NAME_TO_CONFIG.items():
        if keyword in sw_name:
            return config
    return DEFAULT_CONFIG


def get_industry_config(stock_code: str, db_env: str = "online") -> IndustryAnalysisConfig:
    """
    根据股票代码查询申万行业，返回对应行业配置。
    查询失败时回退到 DEFAULT_CONFIG，不抛异常。

    Args:
        stock_code: 股票代码（纯数字如 "600036" 或带后缀如 "600036.SH"）
        db_env: 数据库环境

    Returns:
        IndustryAnalysisConfig
    """
    sw_name = _get_sw_name(stock_code, db_env)
    if sw_name:
        config = get_industry_config_by_sw_name(sw_name)
        import logging
        logging.getLogger(__name__).info(
            "[IndustryConfig] %s -> SW行业: %s -> %s",
            stock_code, sw_name, config.industry_name,
        )
        return config
    import logging
    logging.getLogger(__name__).warning(
        "[IndustryConfig] 无法获取 %s 的行业信息，使用默认配置", stock_code
    )
    return DEFAULT_CONFIG


def _get_sw_name(stock_code: str, db_env: str = "online") -> Optional[str]:
    """查询 SW 一级行业名称（来自 trade_stock_basic.industry），失败返回 None。"""
    try:
        from config.db import execute_query
        clean_code = stock_code.split(".")[0]
        rows = execute_query(
            "SELECT industry FROM trade_stock_basic WHERE stock_code LIKE %s LIMIT 1",
            params=(f"{clean_code}%",),
            env=db_env,
        )
        if rows:
            return rows[0].get("industry", "") or ""
    except Exception:
        pass
    return None
