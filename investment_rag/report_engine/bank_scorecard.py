# -*- coding: utf-8 -*-
"""
银行评分卡 v2.0

用途：
1. 对单只银行股进行结构化打分（7大维度，100分制）
2. 输出文本供 LLM 引用（注入研报上下文）
3. 输出结构化 dict 供逆向工程使用（拟合 f大 评分权重）

评分维度（v2.1, 基于 f大 17 家银行年报点评逆向工程 + 边际变化维度）：
  D1 资产质量        25%  (NPL2变化趋势权重最高，f大核心)
  D2 盈利能力        10%  (f大几乎不看利润惊喜，大幅降权)
  D3 利润质量        15%  (新增拨备比变化趋势, f大 OLS coeff=+0.576)
  D4 净资产质量      20%  (f大第一驱动力，OCI+净资产增速)
  D5 资本充足率      10%  (微降)
  D6 估值安全边际    10%  (PB分位)
  D7 股息回报        10%  (独立维度，含股息率+分红增长趋势)

逆向工程依据 (OLS R^2=0.794, n=17):
  权益惊喜 coeff=+0.925 > 拨备趋势 +0.576 > 不良率趋势 +0.464
  > 分红趋势 +0.436 > 不良率2趋势 +0.367 > 充足率 +0.127
  > 利润惊喜 -0.046 (接近零)
"""
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ============================================================
# 评分配置（权重 + 阈值）
# 逆向工程后，用 fit_weights() 替换 weights 字段
# ============================================================

@dataclass
class ThresholdScore:
    """单个子维度的分档阈值（降序，第一个匹配即采用）"""
    # [(上限 or None, 下限 or None, 得分)]
    # 规则：value 满足 lower <= value < upper 则得分
    # upper=None 表示无上限；lower=None 表示无下限
    brackets: List[Tuple]  # (lower, upper, score)
    missing_score: float = 2.5  # 数据缺失时给中性分

    def score(self, value: Optional[float]) -> float:
        if value is None:
            return self.missing_score
        for lower, upper, s in self.brackets:
            ok_lower = (lower is None) or (value >= lower)
            ok_upper = (upper is None) or (value < upper)
            if ok_lower and ok_upper:
                return float(s)
        return self.missing_score


@dataclass
class SubDimConfig:
    name: str
    weight: float          # 在父维度内的权重（归一化前）
    threshold: ThresholdScore
    extract_key: str = ""  # 从 raw_data dict 中取值的 key（供 score_from_data 使用）


@dataclass
class DimConfig:
    name: str
    weight: float          # 在总分中的权重（0-1）
    subs: List[SubDimConfig]


@dataclass
class ScorecardConfig:
    dimensions: List[DimConfig]
    rating_map: List[Tuple[float, str]]  # [(下限, 评级)] 降序排列

    def rating(self, total: float) -> str:
        for lower, label in self.rating_map:
            if total >= lower:
                return label
        return "强烈回避"


def _make_default_config() -> ScorecardConfig:
    """
    v2.0 配置（基于 f大 17家银行年报点评逆向工程）。
    """

    # ---------- D1: 资产质量 (25%) ----------
    # f大核心看 NPL2 变化趋势（边际改善/恶化）+ 绝对水平
    d1 = DimConfig(
        name="资产质量",
        weight=0.25,
        subs=[
            SubDimConfig(
                name="NPL率",
                weight=0.15,        # 降权：官方NPL可调节，f大几乎不看
                extract_key="npl_ratio",
                threshold=ThresholdScore(brackets=[
                    (None, 0.8,  5),
                    (0.8,  1.2,  4),
                    (1.2,  1.8,  3),
                    (1.8,  2.5,  2),
                    (2.5,  None, 1),
                ]),
            ),
            SubDimConfig(
                name="拨备覆盖率",
                weight=0.20,
                extract_key="provision_coverage",
                threshold=ThresholdScore(brackets=[
                    (None, 0,    1),   # 负值异常
                    (300,  None, 5),
                    (200,  300,  4),
                    (150,  200,  3),
                    (120,  150,  2),
                    (0,    120,  1),
                ], missing_score=2.0),
            ),
            SubDimConfig(
                name="NPL2-官方差值",
                weight=0.25,        # NPL2绝对水平可信度
                extract_key="npl2_gap",   # npl_ratio2 - official_npl_ratio，负=更严格
                threshold=ThresholdScore(brackets=[
                    (None, 0.0,  5),   # NPL2 <= 官方，认定严格
                    (0.0,  0.3,  4),
                    (0.3,  0.5,  3),
                    (0.5,  1.0,  2),
                    (1.0,  None, 1),
                ]),
            ),
            SubDimConfig(
                name="NPL2变化趋势(ppt)",
                weight=0.40,        # 新增：f大核心--不良率2是在改善还是恶化
                extract_key="npl2_trend_ppt",   # 正=恶化，负=改善
                threshold=ThresholdScore(brackets=[
                    (None, -0.10, 5),   # 大幅改善
                    (-0.10, -0.02, 4),  # 改善
                    (-0.02,  0.02, 3),  # 持平
                    (0.02,   0.08, 2),  # 恶化
                    (0.08,   None, 1),  # 大幅恶化
                ]),
            ),
        ],
    )

    # ---------- D2: 盈利能力 (10%, was 20%) ----------
    # f大的逆向工程显示利润惊喜系数接近0，大幅降权
    d2 = DimConfig(
        name="盈利能力",
        weight=0.10,
        subs=[
            SubDimConfig(
                name="ROE",
                weight=0.50,
                extract_key="roe",
                threshold=ThresholdScore(brackets=[
                    (15,   None, 5),
                    (13,   15,   4),
                    (11,   13,   3),
                    (9,    11,   2),
                    (None, 9,    1),
                ]),
            ),
            SubDimConfig(
                name="NIM水平",
                weight=0.30,
                extract_key="nim",
                threshold=ThresholdScore(brackets=[
                    (2.0,  None, 5),
                    (1.7,  2.0,  4),
                    (1.4,  1.7,  3),
                    (1.1,  1.4,  2),
                    (None, 1.1,  1),
                ]),
            ),
            SubDimConfig(
                name="归母净利同比增速",
                weight=0.20,
                extract_key="net_profit_yoy",
                threshold=ThresholdScore(brackets=[
                    (12,   None, 5),
                    (8,    12,   4),
                    (4,    8,    3),
                    (0,    4,    2),
                    (None, 0,    1),
                ]),
            ),
        ],
    )

    # ---------- D3: 利润质量 (15%) ----------
    # f大 拨备趋势 OLS coeff=+0.576，加入拨备比变化趋势
    d3 = DimConfig(
        name="利润质量",
        weight=0.15,
        subs=[
            SubDimConfig(
                name="拨备释放贡献比",
                weight=0.30,
                extract_key="prov_release_contrib_pct",  # 拨备贡献/利润增量（%）
                threshold=ThresholdScore(brackets=[
                    (None, 10,   5),
                    (10,   30,   4),
                    (30,   50,   3),
                    (50,   70,   2),
                    (70,   None, 1),
                ], missing_score=3.0),
            ),
            SubDimConfig(
                name="拨备比变化趋势(ppt)",
                weight=0.40,        # 新增：f大核心--拨备比是在增厚还是消耗
                extract_key="prov_ratio_trend_ppt",  # 正=拨备增厚(好)，负=消耗(差)
                threshold=ThresholdScore(brackets=[
                    (0.10,  None, 5),   # 拨备大幅增厚
                    (0.02,  0.10, 4),   # 略增厚
                    (-0.05, 0.02, 3),   # 持平
                    (-0.15, -0.05, 2),  # 消耗
                    (None,  -0.15, 1),  # 大幅消耗
                ], missing_score=3.0),
            ),
            SubDimConfig(
                name="剪刀差（归母-营收增速差）",
                weight=0.30,
                extract_key="scissors_gap_ppt",   # 归母yoy - 营收yoy（ppt），越大越差
                threshold=ThresholdScore(brackets=[
                    (None, 2,    5),
                    (2,    5,    4),
                    (5,    8,    3),
                    (8,    12,   2),
                    (12,   None, 1),
                ], missing_score=3.0),
            ),
        ],
    )

    # ---------- D4: 净资产质量 (20%, was 10%) ----------
    # f大第一驱动力（OLS coeff=+0.925），从10%翻倍到20%
    # 新增"净资产增速"子维度：f大核心看权益是否达到预期
    d4 = DimConfig(
        name="净资产质量",
        weight=0.20,
        subs=[
            SubDimConfig(
                name="OCI差值（占期初净资产%）",
                weight=0.40,        # was 1.0
                extract_key="oci_gap_pct",   # 负=OCI侵蚀净资产（%），正=增厚
                threshold=ThresholdScore(brackets=[
                    (0,    None, 5),    # OCI正贡献
                    (-1,   0,    4),
                    (-2,   -1,   3),
                    (-4,   -2,   2),
                    (None, -4,   1),
                ], missing_score=3.0),
            ),
            SubDimConfig(
                name="净资产增速（%）",
                weight=0.60,        # 新增：f大最关注权益增长是否符合预期
                extract_key="equity_growth_pct",  # 股东权益同比增速
                threshold=ThresholdScore(brackets=[
                    (10,   None, 5),   # 高增长
                    (7,    10,   4),
                    (4,    7,    3),
                    (1,    4,    2),
                    (None, 1,    1),   # 几乎不增长或缩水
                ], missing_score=3.0),
            ),
        ],
    )

    # ---------- D5: 资本充足率 (10%, was 15%) ----------
    # f大逆向工程显示充足率系数仅+0.127，降权
    d5 = DimConfig(
        name="资本充足率",
        weight=0.10,
        subs=[
            SubDimConfig(
                name="一级资本充足率水平",
                weight=0.40,
                extract_key="tier1_ratio",
                threshold=ThresholdScore(brackets=[
                    (12,   None, 5),
                    (11,   12,   4),
                    (10,   11,   3),
                    (9.5,  10,   2),
                    (None, 9.5,  1),
                ]),
            ),
            SubDimConfig(
                name="资本压力（贷款增速-内生补充，ppt）",
                weight=0.60,
                extract_key="cap_pressure_ppt",   # 越大越差
                threshold=ThresholdScore(brackets=[
                    (None, 0,    5),
                    (0,    3,    4),
                    (3,    7,    3),
                    (7,    12,   2),
                    (12,   None, 1),
                ], missing_score=3.0),
            ),
        ],
    )

    # ---------- D6: 估值安全边际 (10%) ----------
    d6 = DimConfig(
        name="估值安全边际",
        weight=0.10,
        subs=[
            SubDimConfig(
                name="PB历史分位数",
                weight=1.0,
                extract_key="pb_percentile",   # 历史百分位，越低越便宜
                threshold=ThresholdScore(brackets=[
                    (None, 20,   5),
                    (20,   40,   4),
                    (40,   60,   3),
                    (60,   80,   2),
                    (80,   None, 1),
                ], missing_score=3.0),
            ),
        ],
    )

    # ---------- D7: 股息回报 (10%, 新增独立维度) ----------
    # f大分红趋势 OLS coeff=+0.436，独立成维度
    d7 = DimConfig(
        name="股息回报",
        weight=0.10,
        subs=[
            SubDimConfig(
                name="股息率（%）",
                weight=0.60,
                extract_key="dividend_yield_pct",
                threshold=ThresholdScore(brackets=[
                    (6,    None, 5),
                    (4.5,  6,    4),
                    (3,    4.5,  3),
                    (1.5,  3,    2),
                    (None, 1.5,  1),
                ], missing_score=3.0),
            ),
            SubDimConfig(
                name="分红增长趋势",
                weight=0.40,
                extract_key="div_growth_pct",  # 每股分红同比增速(%)
                threshold=ThresholdScore(brackets=[
                    (10,   None, 5),   # 分红大幅增长
                    (3,    10,   4),   # 分红温和增长
                    (-2,   3,    3),   # 基本持平
                    (-10,  -2,   2),   # 分红下降
                    (None, -10,  1),   # 分红大幅下降
                ], missing_score=3.0),
            ),
        ],
    )

    return ScorecardConfig(
        dimensions=[d1, d2, d3, d4, d5, d6, d7],
        rating_map=[
            (85, "强烈推荐"),
            (70, "推荐"),
            (55, "中性偏推荐"),
            (40, "中性"),
            (25, "回避"),
            (0,  "强烈回避"),
        ],
    )


DEFAULT_SCORECARD_CONFIG = _make_default_config()


# ============================================================
# 评分卡引擎
# ============================================================

@dataclass
class SubScore:
    name: str
    raw_score: float    # 0-5
    weight: float       # 在父维度内的归一化权重
    input_value: Optional[float]
    note: str = ""


@dataclass
class DimScore:
    name: str
    dim_weight: float       # 在总分中的权重
    sub_scores: List[SubScore]
    dim_raw: float          # 子维度加权平均（0-5）
    dim_contribution: float # 对总分贡献（0-100）


@dataclass
class ScorecardResult:
    stock_code: str
    stock_name: str
    report_date: str
    dim_scores: List[DimScore]
    total_score: float      # 0-100
    rating: str
    highlights: List[str]   # 亮点（得分>=4.0的子维度）
    risks: List[str]        # 风险（得分<=2.0的子维度）
    raw_data: Dict          # 打分用原始数据（供逆向工程）

    def to_text(self) -> str:
        lines = [
            f"[银行评分卡] {self.stock_name}（{self.stock_code}）  数据期：{self.report_date}",
            f"总分：{self.total_score:.1f}/100   评级：{self.rating}",
            "",
            f"{'维度':<12} {'原始分':>6} {'权重':>6} {'贡献分':>7}",
            "-" * 38,
        ]
        for d in self.dim_scores:
            lines.append(
                f"{d.name:<12} {d.dim_raw:>5.2f}/5  "
                f"{d.dim_weight*100:>4.0f}%  {d.dim_contribution:>6.1f}"
            )
            for s in d.sub_scores:
                val_str = f"{s.input_value:.2f}" if s.input_value is not None else "N/A"
                lines.append(
                    f"  - {s.name[:18]:<18} {s.raw_score:.1f}/5  (实际值:{val_str})"
                )
        lines += [
            "",
            "[亮点] " + "；".join(self.highlights) if self.highlights else "[亮点] 无",
            "[风险] " + "；".join(self.risks) if self.risks else "[风险] 无",
        ]
        return "\n".join(lines)

    def to_dict(self) -> Dict:
        """结构化输出，用于逆向工程和横向对比"""
        return {
            "stock_code": self.stock_code,
            "stock_name": self.stock_name,
            "report_date": self.report_date,
            "total_score": round(self.total_score, 2),
            "rating": self.rating,
            "dim_scores": {
                d.name: {
                    "raw": round(d.dim_raw, 3),
                    "contribution": round(d.dim_contribution, 2),
                    "subs": {s.name: {"score": s.raw_score, "value": s.input_value}
                             for s in d.sub_scores},
                }
                for d in self.dim_scores
            },
            "raw_data": self.raw_data,
        }


class BankScoreCard:
    """
    银行评分卡引擎。

    用法：
        sc = BankScoreCard(db_env="online")
        result = sc.score("002142", "宁波银行")
        print(result.to_text())         # 注入研报
        data = result.to_dict()          # 逆向工程用
    """

    def __init__(
        self,
        db_env: str = "online",
        config: Optional[ScorecardConfig] = None,
    ):
        self._db_env = db_env
        self._config = config or DEFAULT_SCORECARD_CONFIG
        # 延迟导入避免循环依赖
        from investment_rag.report_engine.data_tools import ReportDataTools
        self._tools = ReportDataTools(db_env=db_env)

    # ----------------------------------------------------------
    # Public API
    # ----------------------------------------------------------

    def score(self, stock_code: str, stock_name: str) -> ScorecardResult:
        """对单只银行股进行完整评分。"""
        raw = self._collect_raw_data(stock_code, stock_name)
        report_date = raw.get("report_date", "unknown")

        dim_scores = []
        highlights = []
        risks = []

        for dim_cfg in self._config.dimensions:
            # 归一化子维度权重
            total_sub_w = sum(s.weight for s in dim_cfg.subs)
            sub_scores = []
            dim_raw = 0.0

            for sub_cfg in dim_cfg.subs:
                val = raw.get(sub_cfg.extract_key)
                s = sub_cfg.threshold.score(val)
                norm_w = sub_cfg.weight / total_sub_w if total_sub_w > 0 else 1.0
                sub_scores.append(SubScore(
                    name=sub_cfg.name,
                    raw_score=s,
                    weight=norm_w,
                    input_value=val,
                ))
                dim_raw += s * norm_w

                label = f"{dim_cfg.name}/{sub_cfg.name}（{val:.2f}）" if val is not None else f"{dim_cfg.name}/{sub_cfg.name}"
                if s >= 4.5:
                    highlights.append(label)
                elif s <= 1.5:
                    risks.append(label)

            contrib = dim_raw * dim_cfg.weight * 20  # 0-5 -> 0-100
            dim_scores.append(DimScore(
                name=dim_cfg.name,
                dim_weight=dim_cfg.weight,
                sub_scores=sub_scores,
                dim_raw=dim_raw,
                dim_contribution=contrib,
            ))

        total = sum(d.dim_contribution for d in dim_scores)
        rating = self._config.rating(total)

        return ScorecardResult(
            stock_code=stock_code,
            stock_name=stock_name,
            report_date=report_date,
            dim_scores=dim_scores,
            total_score=total,
            rating=rating,
            highlights=highlights,
            risks=risks,
            raw_data=raw,
        )

    # ----------------------------------------------------------
    # 横向对比（多家银行并排）
    # ----------------------------------------------------------

    def compare(self, banks: List[Tuple[str, str]]) -> str:
        """
        对多家银行评分并横向对比。

        Args:
            banks: [(stock_code, stock_name), ...]

        Returns:
            Formatted comparison table text
        """
        results = []
        for code, name in banks:
            try:
                r = self.score(code, name)
                results.append(r)
            except Exception as e:
                logger.warning("[BankScoreCard] score failed for %s: %s", code, e)

        if not results:
            return "[评分对比] 无有效数据"

        results.sort(key=lambda x: x.total_score, reverse=True)

        lines = [
            "[银行评分对比表]",
            f"{'股票':<10} {'总分':>6} {'评级':<8} {'资产':>5} "
            f"{'盈利':>5} {'利润':>5} {'净资产':>5} {'资本':>5} {'估值':>5} {'股息':>5}",
            "-" * 76,
        ]
        for r in results:
            dim_map = {d.name: d.dim_raw for d in r.dim_scores}
            lines.append(
                f"{r.stock_name[:6]:<6}({r.stock_code})  "
                f"{r.total_score:>5.1f}  {r.rating:<8}  "
                f"{dim_map.get('资产质量', 0):>4.2f}  "
                f"{dim_map.get('盈利能力', 0):>4.2f}  "
                f"{dim_map.get('利润质量', 0):>4.2f}  "
                f"{dim_map.get('净资产质量', 0):>4.2f}  "
                f"{dim_map.get('资本充足率', 0):>4.2f}  "
                f"{dim_map.get('估值安全边际', 0):>4.2f}  "
                f"{dim_map.get('股息回报', 0):>4.2f}"
            )
        return "\n".join(lines)

    # ----------------------------------------------------------
    # 逆向工程入口（拟合 f大 权重）
    # ----------------------------------------------------------

    @staticmethod
    def fit_weights_from_expert(
        expert_data: List[Dict],
        scorecard_results: List[Dict],
        method: str = "linear",
    ) -> Dict:
        """
        从专家评价逆向拟合权重。

        Args:
            expert_data: [{"stock_code": ..., "expert_rating": ...,
                           "expert_score": ...}, ...]  # expert_score: 可选数值化评级
            scorecard_results: [result.to_dict(), ...]  # 对应的评分卡原始数据
            method: "linear" (OLS回归) 或 "rank" (排名相关)

        Returns:
            {"fitted_weights": {...}, "r_squared": ..., "residuals": [...]}
        """
        try:
            import numpy as np
        except ImportError:
            return {"error": "numpy not available"}

        # 构建特征矩阵（每家银行的6个维度原始分）
        dim_names = ["资产质量", "盈利能力", "利润质量", "净资产质量", "资本充足率", "估值安全边际", "股息回报"]

        # 将专家评级数值化（若未提供 expert_score）
        rating_to_score = {
            "强烈推荐": 5, "买入": 5,
            "推荐": 4, "增持": 4,
            "中性偏推荐": 3,
            "中性": 2, "持有": 2,
            "回避": 1, "减持": 1,
            "强烈回避": 0, "卖出": 0,
        }

        # 对齐专家数据和评分卡数据
        code_to_expert = {d["stock_code"]: d for d in expert_data}
        code_to_sc = {d["stock_code"]: d for d in scorecard_results}

        X, y = [], []
        for code, exp in code_to_expert.items():
            if code not in code_to_sc:
                continue
            sc = code_to_sc[code]
            # 特征向量：6个维度的原始分（0-5）
            feats = []
            for dn in dim_names:
                dim_info = sc["dim_scores"].get(dn, {})
                feats.append(dim_info.get("raw", 2.5))
            X.append(feats)

            # 目标：专家评级数值
            expert_score = exp.get("expert_score")
            if expert_score is None:
                expert_score = rating_to_score.get(exp.get("expert_rating", "中性"), 2)
            y.append(float(expert_score))

        if len(X) < 3:
            return {"error": f"样本量不足（{len(X)}家），需至少3家才能拟合"}

        X_arr = np.array(X)
        y_arr = np.array(y)

        if method == "linear":
            # OLS 最小二乘（带非负约束，权重不能为负）
            try:
                from scipy.optimize import nnls
                # 归一化后的特征（0-5 -> 0-1）
                X_norm = X_arr / 5.0
                weights_raw, _ = nnls(X_norm, y_arr)
                weights_sum = weights_raw.sum()
                if weights_sum > 0:
                    weights_norm = weights_raw / weights_sum
                else:
                    weights_norm = np.ones(len(dim_names)) / len(dim_names)

                y_pred = X_norm @ weights_raw
                ss_res = np.sum((y_arr - y_pred) ** 2)
                ss_tot = np.sum((y_arr - y_arr.mean()) ** 2)
                r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0

                result = {
                    "method": "OLS (非负约束)",
                    "n_samples": len(X),
                    "r_squared": round(r2, 3),
                    "fitted_weights": {
                        dn: round(float(w), 4)
                        for dn, w in zip(dim_names, weights_norm)
                    },
                    "raw_weights": {
                        dn: round(float(w), 4)
                        for dn, w in zip(dim_names, weights_raw)
                    },
                    "residuals": [
                        {
                            "stock_code": list(code_to_expert.keys())[i],
                            "expert": round(y_arr[i], 2),
                            "predicted": round(float(y_pred[i]), 2),
                            "error": round(float(y_arr[i] - y_pred[i]), 2),
                        }
                        for i in range(len(y_arr))
                    ],
                }
            except ImportError:
                # scipy 不可用，用简单相关系数代替
                correlations = {}
                for j, dn in enumerate(dim_names):
                    col = X_arr[:, j]
                    if col.std() > 0 and y_arr.std() > 0:
                        corr = float(np.corrcoef(col, y_arr)[0, 1])
                    else:
                        corr = 0.0
                    correlations[dn] = round(corr, 3)
                total_corr = sum(abs(v) for v in correlations.values())
                result = {
                    "method": "相关系数（scipy不可用）",
                    "n_samples": len(X),
                    "correlations": correlations,
                    "implied_weights": {
                        dn: round(abs(v) / total_corr, 4) if total_corr > 0 else round(1/len(dim_names), 4)
                        for dn, v in correlations.items()
                    },
                }
        else:
            # rank correlation
            from scipy.stats import spearmanr
            rank_corrs = {}
            for j, dn in enumerate(dim_names):
                col = X_arr[:, j]
                rho, _ = spearmanr(col, y_arr)
                rank_corrs[dn] = round(float(rho), 3)
            result = {
                "method": "Spearman rank correlation",
                "n_samples": len(X),
                "rank_correlations": rank_corrs,
            }

        return result

    # ----------------------------------------------------------
    # 数据采集（从 DB 提取打分所需的原始值）
    # ----------------------------------------------------------

    def _collect_raw_data(self, stock_code: str, stock_name: str) -> Dict:
        """
        从 DB 采集评分所需的原始指标（v2.0: 含净资产增速、分红增长）。

        Returns dict with keys matching SubDimConfig.extract_key values.
        """
        raw: Dict = {}
        code = stock_code.split(".")[0]

        try:
            raw.update(self._fetch_balance_data(code))
            raw.update(self._fetch_income_data(code))
            raw.update(self._fetch_overdue_data(code))
            raw.update(self._fetch_diagnostic_signals(code))
            raw.update(self._fetch_valuation_data(code))
            raw.update(self._fetch_dividend_data(code))
        except Exception as e:
            logger.warning("[BankScoreCard] data collection partial failure: %s", e)

        return raw

    def _fetch_balance_data(self, code: str) -> Dict:
        from investment_rag.report_engine.data_tools import _execute_query, _safe_float
        if _execute_query is None:
            return {}
        sql = """
            SELECT report_date, npl_ratio, provision_coverage, provision_ratio,
                   tier1_ratio, nim, total_equity
            FROM financial_balance
            WHERE stock_code = %s
            ORDER BY report_date DESC
            LIMIT 8
        """
        rows = _execute_query(sql, params=(code,), env=self._db_env) or []
        annual = [r for r in rows if str(r.get('report_date', '')).endswith('12-31')]
        if not annual:
            return {}
        r = annual[0]
        result = {
            "report_date": str(r.get('report_date', '')),
            "npl_ratio": _safe_float(r.get('npl_ratio')),
            "provision_coverage": _safe_float(r.get('provision_coverage')),
            "tier1_ratio": _safe_float(r.get('tier1_ratio')),
            "nim": _safe_float(r.get('nim')),
        }
        if len(annual) >= 2:
            # 计算净资产增速（D4子维度）
            equity_cur = _safe_float(r.get('total_equity'))
            equity_prev = _safe_float(annual[1].get('total_equity'))
            if equity_cur and equity_prev and equity_prev > 0:
                result["equity_growth_pct"] = (equity_cur - equity_prev) / equity_prev * 100

            # 计算拨备比变化趋势（D3新增子维度）
            prov_cur = _safe_float(r.get('provision_ratio'))
            prov_prev = _safe_float(annual[1].get('provision_ratio'))
            if prov_cur is not None and prov_prev is not None:
                result["prov_ratio_trend_ppt"] = prov_cur - prov_prev  # 正=增厚, 负=消耗
        return result

    def _fetch_income_data(self, code: str) -> Dict:
        from investment_rag.report_engine.data_tools import _execute_query, _safe_float
        if _execute_query is None:
            return {}
        sql = """
            SELECT report_date, net_profit_yoy, roe, net_profit
            FROM financial_income
            WHERE stock_code = %s
            ORDER BY report_date DESC
            LIMIT 8
        """
        rows = _execute_query(sql, params=(code,), env=self._db_env) or []
        annual = [r for r in rows if str(r.get('report_date', '')).endswith('12-31')]
        if not annual:
            return {}
        r = annual[0]
        result = {
            "net_profit_yoy": _safe_float(r.get('net_profit_yoy')),
            "roe": _safe_float(r.get('roe')),
        }
        # 保存当期/上期净利润供后续诊断计算使用
        curr_np = _safe_float(r.get('net_profit'))
        if curr_np is not None:
            result["_curr_net_profit"] = curr_np
        if len(annual) >= 2:
            prev_np = _safe_float(annual[1].get('net_profit'))
            if prev_np is not None:
                result["_prev_net_profit"] = prev_np
        return result

    def _fetch_overdue_data(self, code: str) -> Dict:
        from investment_rag.report_engine.data_tools import _execute_query, _safe_float
        if _execute_query is None:
            return {}
        sql = """
            SELECT report_date, npl_ratio2, official_npl_ratio
            FROM bank_overdue_detail
            WHERE stock_code = %s
            ORDER BY report_date DESC
            LIMIT 2
        """
        rows = _execute_query(sql, params=(code,), env=self._db_env) or []
        if not rows:
            return {}
        r = rows[0]
        npl2 = _safe_float(r.get('npl_ratio2'))
        official = _safe_float(r.get('official_npl_ratio'))

        result = {}
        # NPL2 - 官方 NPL 差值（负=认定更严格）
        if npl2 is not None and official is not None:
            result["npl2_gap"] = npl2 - official

        # NPL2 变化趋势（正=恶化，负=改善）
        if len(rows) >= 2 and npl2 is not None:
            prev_npl2 = _safe_float(rows[1].get('npl_ratio2'))
            if prev_npl2 is not None:
                result["npl2_trend_ppt"] = npl2 - prev_npl2

        return result

    def _fetch_diagnostic_signals(self, code: str) -> Dict:
        """
        直接从 DB 计算4个诊断信号，不再依赖 get_bank_diagnostic() 文本解析。

        诊断1: 拨备释放贡献比 = 拨备比变动释放的利润 / 利润增量
        诊断2: OCI差值占比 = (实际净资产增量 - 利润留存推算值) / 期初净资产
        诊断3: 剪刀差 = 归母净利增速 - 营收增速 (ppt)
        诊断4: 资本压力 = 贷款增速 - ROE*(1-分红率) (ppt)
        """
        from investment_rag.report_engine.data_tools import _execute_query, _safe_float
        if _execute_query is None:
            return {}

        result = {}

        # --- 获取 balance 数据（当期+上期年报）---
        bal_sql = """
            SELECT report_date, provision_ratio, loan_total, total_equity
            FROM financial_balance
            WHERE stock_code = %s
            ORDER BY report_date DESC
            LIMIT 8
        """
        bal_rows = _execute_query(bal_sql, params=(code,), env=self._db_env) or []
        annual_bal = [r for r in bal_rows if str(r.get('report_date', '')).endswith('12-31')]
        if len(annual_bal) < 2:
            return result

        curr_bal = annual_bal[0]
        prev_bal = annual_bal[1]

        curr_prov_ratio = _safe_float(curr_bal.get('provision_ratio'))
        prev_prov_ratio = _safe_float(prev_bal.get('provision_ratio'))
        curr_loan = _safe_float(curr_bal.get('loan_total'))
        prev_loan = _safe_float(prev_bal.get('loan_total'))
        curr_equity = _safe_float(curr_bal.get('total_equity'))
        prev_equity = _safe_float(prev_bal.get('total_equity'))

        # --- 获取 income 数据（当期+上期年报）---
        inc_sql = """
            SELECT report_date, revenue, net_profit, net_profit_yoy, roe
            FROM financial_income
            WHERE stock_code = %s
            ORDER BY report_date DESC
            LIMIT 8
        """
        inc_rows = _execute_query(inc_sql, params=(code,), env=self._db_env) or []
        annual_inc = [r for r in inc_rows if str(r.get('report_date', '')).endswith('12-31')]

        curr_np = None
        prev_np = None
        curr_rev = None
        prev_rev = None
        curr_roe = None
        curr_np_yoy = None
        if len(annual_inc) >= 1:
            curr_np = _safe_float(annual_inc[0].get('net_profit'))
            curr_rev = _safe_float(annual_inc[0].get('revenue'))
            curr_roe = _safe_float(annual_inc[0].get('roe'))
            curr_np_yoy = _safe_float(annual_inc[0].get('net_profit_yoy'))
        if len(annual_inc) >= 2:
            prev_np = _safe_float(annual_inc[1].get('net_profit'))
            prev_rev = _safe_float(annual_inc[1].get('revenue'))

        # --- 诊断1: 拨备释放贡献比 ---
        # 拨备比下降 = 释放利润（正数表示利润被拨备释放贡献）
        # 当利润几乎不变时，用拨备释放金额占当期利润的比例替代
        if all(v is not None for v in [curr_prov_ratio, prev_prov_ratio, curr_loan, curr_np, prev_np]):
            prov_change = curr_prov_ratio - prev_prov_ratio  # 负 = 拨备下降 = 释放利润
            prov_release = -prov_change / 100.0 * curr_loan * 0.75  # 乘0.75扣税
            profit_increment = curr_np - prev_np
            if abs(profit_increment) > curr_np * 0.03:
                # 利润变动足够大，用增量贡献比
                result["prov_release_contrib_pct"] = prov_release / abs(profit_increment) * 100
            elif curr_np > 0:
                # 利润几乎不变，用拨备释放占当期利润的比例
                result["prov_release_contrib_pct"] = abs(prov_release) / curr_np * 100
            else:
                result["prov_release_contrib_pct"] = 0.0

        # --- 诊断2: OCI差值占比 ---
        # 推算净资产 = 上期净资产 + 本期利润 * (1 - 分红率) - 分红
        # OCI差值 = 实际净资产 - 推算净资产（正=OCI增厚净资产）
        # 简化：OCI差值 = 实际权益变动 - 净利润留存
        if all(v is not None for v in [curr_equity, prev_equity, curr_np, prev_equity]):
            equity_change = curr_equity - prev_equity
            # 估算分红率（默认30%）
            payout_ratio = 0.30
            retained = curr_np * (1 - payout_ratio)
            oci_gap = equity_change - retained  # 正=OCI正贡献
            if prev_equity > 0:
                result["oci_gap_pct"] = oci_gap / prev_equity * 100

        # --- 诊断3: 剪刀差 ---
        # 归母净利增速 - 营收增速，正数越大=靠拨备/OCI/非经常性贡献
        if all(v is not None for v in [curr_rev, prev_rev, curr_np_yoy]) and prev_rev and prev_rev > 0:
            rev_yoy = (curr_rev - prev_rev) / prev_rev * 100
            result["scissors_gap_ppt"] = curr_np_yoy - rev_yoy

        # --- 诊断4: 资本压力 ---
        # 贷款增速 - 内生资本补充率（ROE * (1-分红率)）
        if all(v is not None for v in [curr_loan, prev_loan, curr_roe]) and prev_loan and prev_loan > 0:
            loan_growth = (curr_loan - prev_loan) / prev_loan * 100
            internal_cap = curr_roe * 0.70  # 假设30%分红率
            result["cap_pressure_ppt"] = loan_growth - internal_cap

        return result

    def _fetch_valuation_data(self, code: str) -> Dict:
        """直接查 trade_stock_daily_basic 计算 PB 5年历史分位数。"""
        from investment_rag.report_engine.data_tools import _execute_query, _safe_float
        if _execute_query is None:
            return {}

        from datetime import date, timedelta
        start_date = (date.today() - timedelta(days=5 * 365)).isoformat()
        sql = """
            SELECT pb
            FROM trade_stock_daily_basic
            WHERE SUBSTRING_INDEX(stock_code, '.', 1) = %s
              AND trade_date >= %s
              AND pb > 0
            ORDER BY trade_date ASC
        """
        try:
            rows = _execute_query(sql, params=(code, start_date), env=self._db_env) or []
        except Exception:
            return {}

        if len(rows) < 20:
            return {}

        pb_values = [_safe_float(r.get('pb')) for r in rows]
        pb_values = [v for v in pb_values if v is not None and v > 0]
        if not pb_values:
            return {}

        current_pb = pb_values[-1]
        pct = sum(1 for v in pb_values if v < current_pb) / len(pb_values) * 100
        return {"pb_percentile": round(pct, 1)}

    def _fetch_dividend_data(self, code: str) -> Dict:
        """
        获取股息率和分红增长趋势（D7 股息回报维度）。

        股息率 = 最近年度合计每股分红 / 最新收盘价
        分红增长 = (今年合计分红 - 去年合计分红) / 去年合计分红 * 100

        注意：financial_dividend.cash_div 单位是每10股派现金额，需除以10得到每股分红。
        trade_stock_daily.stock_code 格式为 '600015.SH'，需要拼接后缀。
        """
        from investment_rag.report_engine.data_tools import _execute_query, _safe_float
        if _execute_query is None:
            return {}

        result = {}

        # 取最近几次分红记录（按 ex_date 降序）
        div_sql = """
            SELECT ex_date, cash_div
            FROM financial_dividend
            WHERE stock_code = %s AND cash_div > 0
            ORDER BY ex_date DESC
            LIMIT 10
        """
        # 取最新收盘价（stock_code 带 .SH/.SZ 后缀）
        # 用 SUBSTRING_INDEX 匹配纯数字部分
        price_sql = """
            SELECT close_price
            FROM trade_stock_daily
            WHERE SUBSTRING_INDEX(stock_code, '.', 1) = %s
            ORDER BY trade_date DESC
            LIMIT 1
        """
        try:
            div_rows = _execute_query(div_sql, params=(code,), env=self._db_env) or []
            price_rows = _execute_query(price_sql, params=(code,), env=self._db_env) or []
        except Exception:
            return {}

        if not div_rows:
            return {}

        # 按 fiscal year 归属分红（而非按 ex_date 日历年）
        # 规则：ex_date 在1-7月 -> 归属上一年 FY；8-12月 -> 归属当年 FY
        # cash_div 是每10股金额，转换为每股
        from collections import defaultdict
        fy_div = defaultdict(float)
        for row in div_rows:
            ex_date = row.get('ex_date')
            cash = _safe_float(row.get('cash_div'))
            if not ex_date or not cash:
                continue
            if hasattr(ex_date, 'year'):
                ex_year, ex_month = ex_date.year, ex_date.month
            else:
                ex_str = str(ex_date)
                ex_year, ex_month = int(ex_str[:4]), int(ex_str[5:7])
            # 1-7月的除权日对应上一个 fiscal year 的分红
            fy = ex_year - 1 if ex_month <= 7 else ex_year
            fy_div[fy] += cash / 10.0  # 每10股 -> 每股

        sorted_fys = sorted(fy_div.keys(), reverse=True)
        if not sorted_fys:
            return {}

        # 判断最新 FY 是否完整：银行通常一年分两次红（中期+年末）
        # 如果最新 FY 的每股分红远低于次新 FY（不足75%），视为不完整（只有中期分红），跳过
        use_idx = 0
        if len(sorted_fys) >= 2:
            latest_div = fy_div[sorted_fys[0]]
            second_div = fy_div[sorted_fys[1]]
            if second_div > 0 and latest_div < second_div * 0.75:
                use_idx = 1  # 最新 FY 不完整，用次新

        if use_idx >= len(sorted_fys):
            return {}

        latest_annual_div = fy_div[sorted_fys[use_idx]]

        # 股息率 = 最近完整 FY 每股分红 / 最新股价
        if price_rows:
            price = _safe_float(price_rows[0].get('close_price'))
            if price and price > 0:
                result["dividend_yield_pct"] = latest_annual_div / price * 100

        # 分红增长趋势（比较最近两个完整 FY）
        next_idx = use_idx + 1
        if next_idx < len(sorted_fys):
            prev_div = fy_div[sorted_fys[next_idx]]
            if prev_div > 0:
                result["div_growth_pct"] = (latest_annual_div - prev_div) / prev_div * 100

        return result
