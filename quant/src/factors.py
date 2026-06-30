#!/usr/bin/env python3
"""팩터 계산 — 가치·퀄리티를 z-score로 합성 (AI Berkshire 퀀트).

4대 거장 → 정량 번역
  퀄리티(버핏·돤융핑): ROE, 영업이익률, 순이익률, 부채비율(역)
  가치(버핏·돤):       이익수익률(1/PER), 순자산수익률(1/PBR), 컨센 상승여력, 배당수익률
종합점수 S = wq·mean(z_quality) + wv·mean(z_value)
"""

from __future__ import annotations

import pandas as pd

# 낮을수록 좋은(=부호 반전) 팩터
_LOWER_IS_BETTER = {"debt_ratio"}


def zscore(s: pd.Series) -> pd.Series:
    """결측 무시 z-score. std=0이면 모두 0."""
    s = pd.to_numeric(s, errors="coerce")
    mu = s.mean(skipna=True)
    sd = s.std(skipna=True, ddof=0)
    if not sd or pd.isna(sd):
        return pd.Series(0.0, index=s.index)
    return (s - mu) / sd


def _row_mean(df: pd.DataFrame, cols: list[str]) -> pd.Series:
    """행별로 결측 아닌 z 컬럼들의 평균."""
    present = [c for c in cols if c in df.columns]
    if not present:
        return pd.Series(0.0, index=df.index)
    return df[present].mean(axis=1, skipna=True).fillna(0.0)


_GROUPS = ("quality", "value", "momentum")


def compute_scores(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """df(종목별 팩터 원값) → 그룹별 z(퀄리티·가치·모멘텀) + 종합점수.

    score = Σ_group weights[group] · mean(z of that group's factors).
    모멘텀 그룹은 선택적(momentum_factors / weights.momentum 없으면 0).
    """
    df = df.copy()
    factor_lists = {
        "quality": cfg.get("quality_factors", []),
        "value": cfg.get("value_factors", []),
        "momentum": cfg.get("momentum_factors", []),
    }
    weights = cfg.get("weights", {})
    df["score"] = 0.0
    for g in _GROUPS:
        zcols = []
        for f in factor_lists[g]:
            if f not in df.columns:
                continue
            raw = df[f]
            if f in _LOWER_IS_BETTER:
                raw = -pd.to_numeric(raw, errors="coerce")
            zc = f"z_{f}"
            df[zc] = zscore(raw)
            zcols.append(zc)
        df[f"{g}_z"] = _row_mean(df, zcols)
        df["score"] = df["score"] + float(weights.get(g, 0.0)) * df[f"{g}_z"]
    return df
