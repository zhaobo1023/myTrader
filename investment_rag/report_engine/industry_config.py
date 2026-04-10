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

**数据引用硬规则**：以下每项必须引用上方"行业专项数据"段落中明确出现的数字，
不得引用"财务比率摘要"中的增速/比率替代绝对值，不得凭记忆填充任何数字。

1. 资产质量三重验证
   - 官方NPL率（来自 financial_balance 表的 npl_ratio 字段）
   - NPL率2（来自 bank_overdue_detail 表）vs 官方NPL率
   - 判断方向：若 NPL率2 <= 官方NPL率，说明不良认定严格，不存在隐藏不良；
     若 NPL率2 >> 官方NPL率（差值 > 0.3ppt），才存在隐藏不良敞口——二者含义截然相反，切勿混淆
   - 拨备覆盖率合规性判断（关键：必须先确认适用监管下限再判断）：
     * 政策背景：2018年银保监会《关于调整商业银行贷款损失准备监管要求的通知》
       将固定150%要求调整为120%-150%动态区间，150%不再是所有银行的硬性红线
     * 适用下限规则：不良认定严格（NPL率2 <= 官方NPL率）→ 适用120-130%下限
       不良认定宽松（NPL率2 >> 官方NPL率，差>0.5ppt）→ 适用150%下限
     * 必须先看"行业专项数据"中的[NPL交叉验证]结论，再判断拨备是否合规
     * 严禁将143%-149%范围的拨备覆盖率定性为"跌破监管红线"——须视具体银行适用哪档
   - 拨备覆盖率趋势：须同时呈现绝对值和同比变化方向
     * 下降 = 信用成本收窄或拨备消耗，属双刃剑：短期利润受益，长期缓冲减少
     * 客观呈现两面，不得因绝对值低于150%就单面定性为"监管违规"或"回避信号"

2. 净息差（NIM）趋势
   - 当前NIM绝对值（来自 financial_balance.nim）+ 同比变动bps
   - 若NIM同比收窄超过10bps，须分析驱动因子（存款成本/贷款定价/结构）

3. 一次性损益对净利润的影响（公允价值变动 + OCI）——**必须量化回摆弹性**
   - 公允价值变动损益：当期绝对值 + 同比摆动幅度（来自 financial_income_detail）
     * 若同比摆动 > 50亿，须注明"一次性项目，下一年存在回摆弹性"
     * **必须量化**：假设公允价值变动回归0，增厚利润 = |当期公允价值变动损益|（税前）
       对应归母净利润弹性 = 增厚金额 / 当期归母净利润 x 100%（取自核心财务数据）
       例如：公允价值变动-35亿回归0 = +35亿增厚，272亿基数上 = +12.9%弹性
     * 若公允价值变动损益为正（当期获利），则不构成"回摆弹性"，应关注可持续性
   - 其他综合收益（OCI）对净资产的冲击：
     * OCI大额负值 = 国债/债券浮亏直接侵蚀净资产（不走利润表）
     * 若可推算出"推算净资产 vs 实际净资产"偏差，须点明原因（通常是FVOCI债券浮亏）
     * 这是PB估值被压制的直接原因，投资含义：利率回升时净资产将自动修复

4. 拨备比（贷款拨备率）趋势
   - 拨备比 = 拨备余额 / 总贷款（来自 financial_balance.provision_ratio）
   - 反映贷款整体风险缓冲厚度，与拨备覆盖率互补
   - 趋势下降 = 风险缓冲在削薄，需关注是主动释放利润还是被动消耗

5. 资本充足率 vs 内生资本补充
   - CET1 与监管红线距离；若 ROE < 核心资本充足率要求 + 分红率，则内生补充不足

6. 核心财务绝对值（来自 financial_income 表）
   - 营业收入（亿元）、归母净利润（亿元）、净利润同比增速、ROE、EPS
   - 严禁使用"财务比率摘要"中的同比增速替代绝对金额
   - 所有数据引用必须标注来源表名

**以下三项为Flitter诊断强制输出项（来自"银行诊断预计算"段落，直接引用信号结论）**：

7. 净资产质量 - OCI差值（推算净资产 vs 实际净资产）
   - 直接引用"银行诊断预计算"[诊断2]的OCI差值（亿元）和信号标记
   - [RISK]/[WARN]信号须在"数据局限"中单独列出，说明PB估值安全边际被压缩程度
   - [OK/+]信号须说明FVOCI浮盈的可持续性风险（利率上行时会反转）

8. 营业利润 vs 归母净利 剪刀差
   - 直接引用"银行诊断预计算"[诊断3]的剪刀差（ppt）和信号标记
   - [WARN]信号须说明免税收入/少数股东驱动不可持续，利润增速预期应向营业利润靠拢
   - 若[数据不足]，须在"数据局限"注明无法验证盈利质量

9. 资本消耗速率
   - 直接引用"银行诊断预计算"[诊断4]的贷款增速、内生资本补充速度、资本压力值
   - [RISK]/[WARN]信号须说明对未来贷款扩张节奏和利润增速的压制路径
   - 须同时引用tier1资本充足率趋势（绝对值 + 同比变动ppt）
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
- 辅助估值1：股息率 vs 10年期国债收益率利差（> 200bps = 有安全边际）
  * 分红数据已注入估值上下文（来自 financial_dividend 表），包含历史每股分红、派息率
  * 当前股价下的股息率 = 年度合计每股分红 / 当前股价
- 辅助估值2：一致预期 EPS（来自同花顺数据），对比市场隐含盈利假设
- 切忌使用 PE/EV-EBITDA，银行资产负债表与非金融企业差异过大

**PB数据来源约束（防止前后矛盾）**：
- 全篇只能使用一个PB数值，来源必须统一：优先使用"估值历史分位"段落中的PB数值
- 执行摘要中的PB必须与第三步估值中的PB完全一致，若两者来源不同须在执行摘要注明"以Step3数据为准"
- PB数值若为数据库历史数据，须注明查询日期；若感觉明显偏离常识（如<0.3x或>3x），标注"(待核实，数据来自历史库)"
""",

    risk_dimensions="""
**银行专项风险**：
- 信用风险：不良生成率（Credit Cost）突增、城投/房地产贷款集中度
- 利率风险：NIM下行斜率 vs 再定价缺口（若未披露，标注为信息盲区）
- 资本充足率：核心一级资本充足率（CET1）与监管红线距离
  * 须引用[诊断4]的资本压力值和tier1趋势，不得自行估算
- 流动性风险：LCR（流动性覆盖率）+ 对同业负债依赖度
- 拨备充足性：基于动态监管下限（120-150%区间）评估，不得以150%作统一红线
  * 若拨备覆盖率低于银行适用下限（已通过NPL交叉验证确定），才构成合规风险
  * 拨备覆盖率在适用下限以上的下降趋势 = 风险偏好变化，不等于监管违规
- OCI/净资产风险：引用[诊断2]OCI差值信号；[RISK]标记须作为独立风险项列出
- 盈利质量风险：引用[诊断1]拨备贡献比和[诊断3]剪刀差；利润增速虚高须在风险项中说明

**综合评级约束**：
- 单一指标（如拨备覆盖率低于150%）不得成为"回避"评级的唯一或主要理由
- 评级须综合考虑：资产质量趋势 + 一次性损益回摆弹性 + 估值分位 + 股息安全边际
- 若存在重大正面催化剂（如百亿级公允价值回摆），必须在评级中给予对等权重

**预期回报量化特别说明（银行业）**：
- 估值贡献必须使用PB框架（目标PB/当前PB - 1），不得使用系统提供的PE回归测算
  * 系统"预期回报测算"中的PE回归结果仅供参考，银行PE波动大且不稳定，不适合做回归目标
  * 目标PB参考：ROE/(Ke-g) 理论值打折，或同业PB中位数，或历史PB合理区间
- 股息贡献不得为0（除非确实无分红记录）：
  * 股息率 = 年度合计每股分红 / 当前股价
  * 当前股价可由 PB x 每股净资产 推算（两个数据均在估值上下文中）
  * 2年股息贡献 = 股息率 x 2
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
