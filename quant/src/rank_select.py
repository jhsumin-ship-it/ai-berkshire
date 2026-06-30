#!/usr/bin/env python3
"""스크리닝 · 랭킹 · 섹터 선별 · 비중배분 (AI Berkshire 퀀트)."""

from __future__ import annotations

import pandas as pd


def apply_screen(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """하드 스크린. 탈락 사유를 'screen_out' 컬럼에 기록(빈 문자열=통과)."""
    sc = cfg["screen"]
    df = df.copy()
    reasons = []
    for _, r in df.iterrows():
        why = []
        if r.get("flags"):
            why.append("정합오류:" + ";".join(r["flags"]))
        if sc.get("require_positive_net_income") and not (pd.notna(r.get("net_income")) and r.get("net_income", 0) > 0):
            why.append("적자/순익결측")
        if sc.get("require_positive_per") and not (pd.notna(r.get("eps")) and r.get("eps", 0) > 0):
            why.append("EPS<=0")
        tv = r.get("trading_value_eok")
        if pd.notna(tv) and tv < sc.get("min_trading_value_eok", 0):
            why.append(f"유동성<{sc['min_trading_value_eok']}억")
        reasons.append(" / ".join(why))
    df["screen_out"] = reasons
    return df


def rank_universe(df: pd.DataFrame) -> pd.DataFrame:
    """통과 종목만 점수 내림차순 정렬 + 전체·섹터내 순위."""
    passed = df[df["screen_out"] == ""].copy() if "screen_out" in df.columns else df.iloc[0:0].copy()
    passed = passed.sort_values("score", ascending=False).reset_index(drop=True) if len(passed) else passed
    passed["rank"] = passed.index + 1 if len(passed) else []
    if len(passed):
        passed["sector_rank"] = passed.groupby("sector")["score"].rank(ascending=False, method="first").astype(int)
    else:
        passed["sector_rank"] = []
    return passed


def select_portfolio(ranked: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """섹터별 상위 N → 최대 종목수 → 점수가중 비중(상한 적용)."""
    sel = cfg["selection"]
    picks = ranked[ranked["sector_rank"] <= sel["top_per_sector"]].copy()
    picks = picks.sort_values("score", ascending=False).head(sel["max_names"]).reset_index(drop=True)
    if picks.empty:
        picks["weight"] = []
        return picks
    picks["weight"] = _score_weights(
        picks, sel["max_weight"], sel["max_sector_weight"]
    )
    return picks


def _score_weights(picks: pd.DataFrame, max_w: float, max_sector_w: float) -> pd.Series:
    """점수가중(양수 시프트) → 종목·섹터 상한 → 반복 정규화."""
    s = picks["score"].astype(float)
    base = s - s.min() + 0.1  # 모두 양수로
    w = base / base.sum()

    for _ in range(50):
        w = w.clip(upper=max_w)
        # 섹터 상한
        for sec, idx in picks.groupby("sector").groups.items():
            tot = w.loc[idx].sum()
            if tot > max_sector_w:
                w.loc[idx] *= max_sector_w / tot
        total = w.sum()
        if total <= 0:
            break
        w = w / total
        if (w <= max_w + 1e-9).all():
            # 섹터 상한도 만족하는지 확인
            ok = all(w.loc[idx].sum() <= max_sector_w + 1e-9
                     for idx in picks.groupby("sector").groups.values())
            if ok:
                break
    return (w * 100).round(2)
