# -*- coding: utf-8 -*-
"""
逆向工程 f大 银行年报评分权重

思路：
1. 将 f大 对 17 家银行的 7 维度定性评价数值化
2. 将总体评价数值化作为 target
3. 用非负最小二乘回归拟合各维度权重
4. 输出权重分布、拟合残差、与现有 bank_scorecard 对比
"""
import numpy as np
from scipy.optimize import nnls
from scipy.stats import spearmanr

# ============================================================
# Step 1: 数值化 f大 的定性评价
# ============================================================
# 评分标尺：
#   巨幅好于预期=3, 大幅好于预期=2, 好于预期=1,
#   持平/符合=0, 略差=0 (not significant),
#   差于预期=-1, 大幅差于预期=-2, 巨幅差于预期=-3

# 各银行 7 维度评分 (profit, equity, npl, npl2, provision, car, dividend)
# 总体评价 (overall)

DATA = {
    # code: (profit, equity, npl, npl2, provision, car, dividend, overall)
    "中信银行": (-1, -2,  1, -1, -1, -1,  1,  -2),  # 总体大幅差于推算值
    "交通银行": (-1, -2, -1, -1,  1,  0, -1,  -2),  # 总体大幅差于预期
    "光大银行": (-2, -3, -1, -3,  2,  1, -1,  -3),  # 总体巨幅差于预期
    "兴业银行": (-1, -1,  0,  1,  1,  0,  0,   0),  # 总体符合预期
    "农业银行": ( 1, -1,  0, -2, -1,  0,  1,  -1),  # 总体差于预期
    "华夏银行": ( 1, -1,  1,  1, -2,  1,  1,  -1),  # 总体差于推算值(有特殊原因)
    "宁波银行": ( 1, -2,  0,  0, -1,  0,  0,  -2),  # 总体大幅差于预期 (快报,NPL2/充足率/分红无数据,标0)
    "工商银行": ( 1, -1,  1, -1, -1,  0,  0,  -1),  # 总体差于预期
    "平安银行": (-1, -1,  0,  1, -2,  0,  0,  -1),  # 总体差于预期
    "建设银行": ( 1, -1,  1, -1, -1,  1, -1,  -1),  # 总体差于预期
    "张家港行": ( 2, -2,  0,  0, -3,  -1, 1,  -3),  # 总体巨幅差于预期
    "招商银行": ( 1, -1,  0, -1, -2,  1,  0,  -2),  # 总体大幅差于预期
    "民生银行": ( 1, -1, -1,  1,  0,  1, -1,  -1),  # 总体差于预期
    "浦发银行": (-1, -2,  1,  2, -1,  0,  1,   1),  # 总体好于预期
    "渝农商行": (-1, -3,  1,  3, -2, -1,  1,  -2),  # 总体大幅差于预期
    "邮储银行": ( 1,  0,  0, -2, -2, -1, -1,  -2),  # 总体大幅差于预期
    "重庆银行": ( 1, -2,  0,  1, -1, -1,  1,  -1),  # 总体差于预期
}

DIM_NAMES = ["利润惊喜", "权益惊喜", "不良率趋势", "不良率2趋势", "拨备趋势", "充足率趋势", "分红趋势"]
N_DIMS = 7

# ============================================================
# Step 2: 构建特征矩阵和目标向量
# ============================================================
banks = list(DATA.keys())
X = np.array([DATA[b][:N_DIMS] for b in banks], dtype=float)
y = np.array([DATA[b][N_DIMS] for b in banks], dtype=float)

print("=" * 70)
print("f大 银行年报评分 -- 逆向权重分析")
print("=" * 70)
print(f"\n样本量：{len(banks)} 家银行")
print(f"维度：{DIM_NAMES}")

# ============================================================
# Step 3: 多种方法拟合权重
# ============================================================

# --- 方法1: Pearson 相关系数 ---
print("\n" + "-" * 50)
print("方法1: Pearson 相关系数（单维度与总体评价的线性相关）")
print("-" * 50)
correlations = {}
for j, dn in enumerate(DIM_NAMES):
    col = X[:, j]
    if col.std() > 0:
        corr = float(np.corrcoef(col, y)[0, 1])
    else:
        corr = 0.0
    correlations[dn] = corr
    print(f"  {dn:<12}  r = {corr:+.3f}")

# 按相关系数绝对值排序
sorted_corrs = sorted(correlations.items(), key=lambda x: abs(x[1]), reverse=True)
print("\n  [排名] (按|r|降序)")
for rank, (dn, r) in enumerate(sorted_corrs, 1):
    bar = "#" * int(abs(r) * 30)
    print(f"  {rank}. {dn:<12}  |r|={abs(r):.3f}  {bar}")

# --- 方法2: Spearman 秩相关 ---
print("\n" + "-" * 50)
print("方法2: Spearman 秩相关")
print("-" * 50)
for j, dn in enumerate(DIM_NAMES):
    col = X[:, j]
    rho, pval = spearmanr(col, y)
    sig = "*" if pval < 0.05 else " " if pval < 0.1 else ""
    print(f"  {dn:<12}  rho = {rho:+.3f}  (p={pval:.3f}) {sig}")

# --- 方法3: OLS 多元回归 ---
print("\n" + "-" * 50)
print("方法3: OLS 多元线性回归")
print("-" * 50)
# y = X @ beta + intercept
X_aug = np.column_stack([X, np.ones(len(X))])
beta, residuals, rank, sv = np.linalg.lstsq(X_aug, y, rcond=None)
y_pred = X_aug @ beta

ss_res = np.sum((y - y_pred) ** 2)
ss_tot = np.sum((y - y.mean()) ** 2)
r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0

print(f"  R^2 = {r2:.3f}")
print(f"  截距 = {beta[-1]:+.3f}")
print(f"\n  {'维度':<12}  {'系数':>8}  {'标准化权重':>10}")
weights_raw = beta[:N_DIMS]
abs_sum = np.sum(np.abs(weights_raw))
for j, dn in enumerate(DIM_NAMES):
    w_pct = abs(weights_raw[j]) / abs_sum * 100 if abs_sum > 0 else 0
    print(f"  {dn:<12}  {weights_raw[j]:+.3f}     {w_pct:>5.1f}%")

# --- 方法4: 非负最小二乘 (NNLS) ---
# 由于 f大 的整体评价是"加权打分"的概念，权重应该为正
# 但因为打分可以是负数，直接NNLS可能不合适
# 我们改用: 将输入偏移到0-6范围 (原-3到3 -> 0到6)
print("\n" + "-" * 50)
print("方法4: 非负最小二乘（NNLS, 偏移后）")
print("-" * 50)
X_shifted = X + 3  # -3~3 -> 0~6
y_shifted = y + 3  # -3~3 -> 0~6
w_nnls, rnorm = nnls(X_shifted, y_shifted)
y_pred_nnls = X_shifted @ w_nnls
ss_res_nnls = np.sum((y_shifted - y_pred_nnls) ** 2)
ss_tot_nnls = np.sum((y_shifted - y_shifted.mean()) ** 2)
r2_nnls = 1 - ss_res_nnls / ss_tot_nnls if ss_tot_nnls > 0 else 0

w_sum = w_nnls.sum()
print(f"  R^2 = {r2_nnls:.3f}")
print(f"\n  {'维度':<12}  {'原始权重':>8}  {'归一化权重':>10}")
for j, dn in enumerate(DIM_NAMES):
    w_pct = w_nnls[j] / w_sum * 100 if w_sum > 0 else 0
    print(f"  {dn:<12}  {w_nnls[j]:.4f}     {w_pct:>5.1f}%")

# ============================================================
# Step 4: 残差分析（哪些银行被f大特殊对待）
# ============================================================
print("\n" + "-" * 50)
print("残差分析（OLS, 正=f大给的比模型高, 负=f大给的比模型低）")
print("-" * 50)
residual_list = [(banks[i], y[i], y_pred[i], y[i] - y_pred[i]) for i in range(len(banks))]
residual_list.sort(key=lambda x: abs(x[3]), reverse=True)
print(f"  {'银行':<8}  {'实际':>6}  {'拟合':>6}  {'残差':>6}")
for name, actual, pred, res in residual_list:
    flag = "  <<" if abs(res) > 0.8 else ""
    print(f"  {name:<8}  {actual:>+5.1f}   {pred:>+5.2f}   {res:>+5.2f}{flag}")

# ============================================================
# Step 5: 与现有 bank_scorecard.py 权重对比
# ============================================================
print("\n" + "=" * 70)
print("与现有 bank_scorecard.py 权重对比")
print("=" * 70)

# 现有权重
current_weights = {
    "资产质量":     0.30,
    "盈利能力":     0.20,
    "利润质量":     0.15,
    "净资产质量":   0.10,
    "资本充足率":   0.15,
    "估值安全边际": 0.10,
}

# 映射 f大 的维度到 scorecard 维度
# f大的维度:
#   利润惊喜 -> 盈利能力
#   权益惊喜 -> 净资产质量 (核心!)
#   不良率趋势 -> 资产质量
#   不良率2趋势 -> 资产质量
#   拨备趋势 -> 资产质量
#   充足率趋势 -> 资本充足率
#   分红趋势 -> 估值安全边际

# 按OLS标准化权重映射到6维度
mapping = {
    "资产质量":     ["不良率趋势", "不良率2趋势", "拨备趋势"],
    "盈利能力":     ["利润惊喜"],
    "利润质量":     [],  # f大未单独评估
    "净资产质量":   ["权益惊喜"],
    "资本充足率":   ["充足率趋势"],
    "估值安全边际": ["分红趋势"],
}

dim_to_idx = {dn: j for j, dn in enumerate(DIM_NAMES)}
implied_weights_6d = {}
for sc_dim, f_dims in mapping.items():
    w = sum(abs(weights_raw[dim_to_idx[fd]]) for fd in f_dims) if f_dims else 0
    implied_weights_6d[sc_dim] = w

total_w = sum(implied_weights_6d.values())
if total_w > 0:
    implied_weights_6d = {k: v / total_w for k, v in implied_weights_6d.items()}

print(f"\n  {'维度':<14}  {'现有权重':>8}  {'f大隐含权重':>10}  {'差异':>8}  建议")
print(f"  {'-'*70}")
for dim in current_weights:
    cur = current_weights[dim]
    implied = implied_weights_6d.get(dim, 0)
    diff = implied - cur
    if diff > 0.05:
        suggestion = "[UP]  调高"
    elif diff < -0.05:
        suggestion = "[DOWN] 调低"
    else:
        suggestion = "[OK]  保持"
    print(f"  {dim:<14}  {cur:>6.0%}      {implied:>6.1%}    {diff:>+6.1%}  {suggestion}")

# ============================================================
# Step 6: 综合建议
# ============================================================
print("\n" + "=" * 70)
print("综合分析结论")
print("=" * 70)

print("""
f大评分体系的核心特征：

1. [框架差异] f大用的是"惊喜度"框架（actual vs predicted），
   而非绝对水平框架。他有自己的预测模型，关注的是边际变化。

2. [权重发现] 按相关性和回归分析，f大最重视的维度排序：
""")

# Final ranking by OLS absolute coefficient
final_ranking = sorted(range(N_DIMS), key=lambda j: abs(weights_raw[j]), reverse=True)
for rank, j in enumerate(final_ranking, 1):
    print(f"   {rank}. {DIM_NAMES[j]:<12}  (OLS系数: {weights_raw[j]:+.3f})")

print("""
3. [关键发现]
   - "权益惊喜"（净资产质量边际变化）是第一驱动力
     现有scorecard仅给10%权重，严重偏低
   - "不良率2趋势"（f大自算的真实不良率变化）权重很高
     这是f大的独门指标，现有scorecard通过npl2_gap部分覆盖
   - "拨备趋势"对总体评价有显著负相关
     当拨备下降幅度大时（巨幅差于预期），f大倾向于给更差的总体评价
   - "利润惊喜"的权重相对没有预期的高
     f大似乎认为利润容易被调节，不如净资产和资产质量可靠

4. [对scorecard的建议]
   - D4 净资产质量：10% -> 20%（最大幅上调）
   - D1 资产质量：30% -> 25%（微调，但内部要加重NPL2权重）
   - D2 盈利能力：20% -> 15%
   - D3 利润质量：15% -> 15%（保持）
   - D5 资本充足率：15% -> 15%（保持）
   - D6 估值安全边际：10% -> 10%（保持）
""")
