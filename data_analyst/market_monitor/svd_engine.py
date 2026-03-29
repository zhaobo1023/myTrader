# -*- coding: utf-8 -*-
"""
Randomized SVD 引擎 - 仅提取前 k 个奇异值
"""
import numpy as np
from sklearn.utils.extmath import randomized_svd
from typing import Tuple


def compute_svd(matrix: np.ndarray, n_components: int = 10,
                random_state: int = 42) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Randomized SVD，提取前 n_components 个成分

    Args:
        matrix: 输入矩阵 (stocks x days)，已去均值
        n_components: 提取成分数
        random_state: 随机种子

    Returns:
        U, sigma, Vt
    """
    # 确保没有 NaN/inf
    if np.any(~np.isfinite(matrix)):
        matrix = np.nan_to_num(matrix, nan=0.0, posinf=0.0, neginf=0.0)

    # n_components 不能超过矩阵最小维度
    k = min(n_components, min(matrix.shape) - 1)
    if k < 1:
        k = 1

    U, sigma, Vt = randomized_svd(
        matrix, n_components=k, random_state=random_state
    )
    return U, sigma, Vt


def compute_variance_ratios(sigma: np.ndarray) -> dict:
    """
    从奇异值计算方差占比和重构误差

    Args:
        sigma: 奇异值数组

    Returns:
        dict: top1_var_ratio, top3_var_ratio, top5_var_ratio, reconstruction_error
    """
    sigma_sq = sigma ** 2
    total_var = np.sum(sigma_sq)

    if total_var == 0:
        return {
            'top1_var_ratio': 0.0,
            'top3_var_ratio': 0.0,
            'top5_var_ratio': 0.0,
            'reconstruction_error': 1.0,
        }

    top5_var = np.sum(sigma_sq[:min(5, len(sigma_sq))])
    return {
        'top1_var_ratio': float(sigma_sq[0] / total_var),
        'top3_var_ratio': float(np.sum(sigma_sq[:min(3, len(sigma_sq))]) / total_var),
        'top5_var_ratio': float(top5_var / total_var),
        'reconstruction_error': float(1.0 - top5_var / total_var),
    }
