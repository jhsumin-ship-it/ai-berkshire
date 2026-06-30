#!/usr/bin/env python3
"""팩터·비중 순수로직 테스트 (의존성: pandas만). 실행: python quant/tests/test_factors.py"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import pandas as pd
import factors
import rank_select

CFG = {
    "weights": {"quality": 0.5, "value": 0.5},
    "quality_factors": ["roe", "op_margin", "net_margin", "debt_ratio"],
    "value_factors": ["earnings_yield", "book_yield", "upside", "dividend_yield"],
    "screen": {"require_positive_net_income": True, "require_positive_per": True, "min_trading_value_eok": 30},
    "selection": {"top_per_sector": 2, "max_names": 12, "max_weight": 0.15, "max_sector_weight": 0.30},
}


def test_zscore_basic():
    z = factors.zscore(pd.Series([1.0, 2.0, 3.0]))
    assert abs(z.mean()) < 1e-9, "z-score 평균은 0"
    assert z.iloc[2] > z.iloc[0], "큰 값이 더 높은 z"
    # 상수 시리즈 → 모두 0 (std=0)
    z2 = factors.zscore(pd.Series([5.0, 5.0, 5.0]))
    assert (z2 == 0).all(), "상수 시리즈 z=0"


def test_debt_ratio_inverted():
    df = pd.DataFrame({
        "roe": [10, 10], "op_margin": [10, 10], "net_margin": [10, 10],
        "debt_ratio": [10.0, 200.0],  # 낮은 쪽이 좋아야 함
        "earnings_yield": [5, 5], "book_yield": [5, 5], "upside": [10, 10], "dividend_yield": [1, 1],
    })
    out = factors.compute_scores(df, CFG)
    assert out["quality_z"].iloc[0] > out["quality_z"].iloc[1], "부채비율 낮은 종목 퀄리티 우위"


def test_missing_value_factor_skipped():
    df = pd.DataFrame({
        "roe": [10, 20], "op_margin": [10, 20], "net_margin": [10, 20], "debt_ratio": [50, 50],
        "earnings_yield": [5, 6], "book_yield": [5, 6],
        "upside": [None, None],  # 결측이어도 죽지 않아야
        "dividend_yield": [1, 2],
    })
    out = factors.compute_scores(df, CFG)
    assert out["score"].notna().all(), "결측 팩터가 있어도 종합점수 산출"
    assert out["score"].iloc[1] > out["score"].iloc[0]


def test_weights_respect_caps():
    # 실현가능 구성: 2종×4섹터 (섹터당 2×15=30=상한, 4섹터로 100% 달성 가능)
    df = pd.DataFrame({
        "name": list("ABCDEFGH"), "code": [str(i) for i in range(8)],
        "sector": ["조선", "조선", "바이오", "바이오", "전력", "전력", "AI", "AI"],
        "score": [5.0, 4.0, 1.2, 1.0, 0.8, 0.6, 0.5, 0.3],
    })
    w = rank_select._score_weights(df, max_w=0.15, max_sector_w=0.30)
    assert abs(w.sum() - 100.0) < 0.6, f"비중 합 ~100 (got {w.sum()})"
    assert (w <= 15.0 + 0.01).all(), f"종목 상한 15% 준수 (max {w.max()})"
    for sec in df["sector"].unique():
        tot = w[df["sector"] == sec].sum()
        assert tot <= 30.0 + 0.01, f"섹터 상한 30% 준수 ({sec} {tot})"


def test_screen_excludes_loss_maker():
    df = pd.DataFrame({
        "name": ["흑자", "적자"], "code": ["1", "2"], "sector": ["AI", "AI"],
        "flags": [[], []], "net_income": [100.0, -50.0], "eps": [1000.0, -500.0],
        "trading_value_eok": [100.0, 100.0],
    })
    out = rank_select.apply_screen(df, CFG)
    assert out.loc[0, "screen_out"] == "", "흑자 통과"
    assert "적자" in out.loc[1, "screen_out"], "적자 탈락"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {fn.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR {fn.__name__}: {e}")
    print(f"\n{passed}/{len(fns)} passed")
    sys.exit(0 if passed == len(fns) else 1)
