# -*- coding: utf-8 -*-
"""
5-dimension sentiment scoring engine.

Dimensions:
  score_fund        - capital flow (manual / defaulted 50)
  score_price_vol   - price/volume technicals (auto-computed)
  score_consensus   - analyst consensus (manual / defaulted 50)
  score_sector      - sector/RPS strength (auto-computed from rps_120)
  score_macro       - macro/geopolitical (manual / defaulted 50)

Weights (individual stock):
  score_fund:       30%
  score_price_vol:  25%
  score_consensus:  20%
  score_sector:     20%
  score_macro:       5%
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

try:
    from config.db import execute_query
except ImportError:
    execute_query = None


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SentimentInput:
    # Auto-computable from technical data
    rsi: Optional[float] = None          # 0..100
    macd_hist: Optional[float] = None    # histogram value (positive = bullish)
    vol_ratio: Optional[float] = None    # current volume / 20d avg volume
    rps_120: Optional[float] = None      # RPS 120-day rank 0..100
    # Manual / defaulted to neutral
    score_fund: int = 50                 # capital flow score 0..100
    score_consensus: int = 50            # analyst consensus 0..100
    score_macro: int = 50                # macro/geopolitical 0..100


@dataclass
class SentimentResult:
    composite_score: int
    score_fund: int
    score_price_vol: int
    score_consensus: int
    score_sector: int
    score_macro: int
    historical_quantile: Optional[float]
    label: str


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------

class SentimentScorer:
    """Compute a 5-dimension composite sentiment score for an individual stock."""

    # Weights must sum to 1.0
    _WEIGHTS = {
        'fund': 0.30,
        'price_vol': 0.25,
        'consensus': 0.20,
        'sector': 0.20,
        'macro': 0.05,
    }

    # Label thresholds (descending order)
    _LABELS = [
        (80, '强多'),
        (65, '中性偏多'),
        (50, '中性'),
        (35, '中性偏空'),
    ]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def score(self, inp: SentimentInput, code: str = '') -> SentimentResult:
        """Compute composite score and return a SentimentResult."""
        s_fund = int(inp.score_fund)
        s_pv = self._price_vol_score(inp)
        s_consensus = int(inp.score_consensus)
        s_sector = self._sector_score(inp)
        s_macro = int(inp.score_macro)

        composite = (
            s_fund * self._WEIGHTS['fund']
            + s_pv * self._WEIGHTS['price_vol']
            + s_consensus * self._WEIGHTS['consensus']
            + s_sector * self._WEIGHTS['sector']
            + s_macro * self._WEIGHTS['macro']
        )
        composite_int = int(round(composite))
        composite_int = max(0, min(100, composite_int))

        label = self._map_label(composite_int)

        historical_quantile = None
        if code:
            historical_quantile = self._compute_historical_quantile(code, composite_int)

        return SentimentResult(
            composite_score=composite_int,
            score_fund=s_fund,
            score_price_vol=s_pv,
            score_consensus=s_consensus,
            score_sector=s_sector,
            score_macro=s_macro,
            historical_quantile=historical_quantile,
            label=label,
        )

    # ------------------------------------------------------------------
    # Sub-scores
    # ------------------------------------------------------------------

    def _price_vol_score(self, inp: SentimentInput) -> int:
        """Compute price/volume sub-score from RSI, MACD histogram, vol_ratio."""
        score = 50

        rsi = inp.rsi
        if rsi is not None:
            if rsi < 30:
                score += 20   # oversold / panic = potential reversal
            elif rsi < 45:
                score += 10
            elif rsi > 70:
                score -= 20   # overbought = frothy
            elif rsi > 60:
                score -= 10

        macd_hist = inp.macd_hist
        if macd_hist is not None:
            if macd_hist > 0:
                score += 10
            else:
                score -= 10

        vol_ratio = inp.vol_ratio
        if vol_ratio is not None:
            if vol_ratio > 2.0:
                score -= 5    # extreme volume = distribution risk
            elif vol_ratio < 0.5:
                score += 5    # quiet = no panic

        return max(0, min(100, score))

    def _sector_score(self, inp: SentimentInput) -> int:
        """Compute sector sub-score from rps_120."""
        if inp.rps_120 is None:
            return 50
        score = int(inp.rps_120 * 0.8 + 10)
        return max(0, min(100, score))

    # ------------------------------------------------------------------
    # Label mapping
    # ------------------------------------------------------------------

    def _map_label(self, composite_score: int) -> str:
        for threshold, label in self._LABELS:
            if composite_score >= threshold:
                return label
        return '强空'

    # ------------------------------------------------------------------
    # Historical quantile
    # ------------------------------------------------------------------

    def _compute_historical_quantile(
        self, code: str, current_score: int
    ) -> Optional[float]:
        """
        Return the percentile rank of current_score in historical distribution.

        Returns None if:
          - execute_query is not available (ImportError at module level)
          - fewer than 60 historical records exist for the given code
        """
        if execute_query is None:
            return None

        try:
            rows = execute_query(
                "SELECT COUNT(*) AS cnt FROM sentiment_scores WHERE code = %s",
                (code,)
            )
            total = rows[0]['cnt'] if rows else 0
            if total < 60:
                return None

            pct_rows = execute_query(
                "SELECT COUNT(*) / %s AS pct "
                "FROM sentiment_scores "
                "WHERE code = %s AND composite_score <= %s",
                (total, code, current_score)
            )
            if not pct_rows:
                return None
            return float(pct_rows[0]['pct'])
        except Exception:
            return None
