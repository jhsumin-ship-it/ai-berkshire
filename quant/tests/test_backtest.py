#!/usr/bin/env python3
"""백테스트 핵심 로직 테스트 (point-in-time·비용·성과). 실행: python quant/tests/test_backtest.py"""

import datetime as dt
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import pandas as pd
import backtest as bt


def test_fundamentals_asof_lag():
    fmap = {202312: {"roe": 10.0, "debt_ratio": 5.0},
            202412: {"roe": 12.0, "debt_ratio": 6.0}}
    # FY2023은 2024-03-31부터 사용 가능 → 2024-01은 아직 없음(룩어헤드 차단)
    assert bt.fundamentals_asof(fmap, dt.date(2024, 1, 15), 90) is None
    # 2024-06 → FY2023
    fy, _ = bt.fundamentals_asof(fmap, dt.date(2024, 6, 30), 90)
    assert fy == 202312
    # 2025-06 → FY2024
    fy2, _ = bt.fundamentals_asof(fmap, dt.date(2025, 6, 30), 90)
    assert fy2 == 202412


def test_fundamentals_asof_skips_empty_estimate():
    fmap = {202512: {"roe": 20.0, "debt_ratio": 10.0},
            202612: {"roe": None, "debt_ratio": None}}  # 빈 추정연도
    fy, _ = bt.fundamentals_asof(fmap, dt.date(2026, 6, 30), 90)
    assert fy == 202512, "추정(빈)연도는 건너뛰고 실적연도 사용"


def test_cost_model():
    cost_cfg = {"commission": 0.00015, "slippage": 0.001, "sell_tax": 0.0018}
    target = pd.Series({"A": 0.5, "B": 0.5})
    prev = pd.Series({"A": 1.0})
    c = bt._cost(target, prev, cost_cfg)
    # buys=0.5(B), sells=0.5(A)
    expect = 0.5 * (0.00015 + 0.001) + 0.5 * (0.00015 + 0.001 + 0.0018)
    assert abs(c - expect) < 1e-12, f"비용 {c} != {expect}"


def test_cost_zero_when_no_change():
    cost_cfg = {"commission": 0.001, "slippage": 0.001, "sell_tax": 0.001}
    w = pd.Series({"A": 0.6, "B": 0.4})
    assert abs(bt._cost(w, w, cost_cfg)) < 1e-12, "동일 포지션이면 비용 0"


def test_perf_metrics():
    flat = pd.Series([0.0, 0.0, 0.0])
    m = bt.perf(flat)
    assert abs(m["total"]) < 1e-12 and abs(m["mdd"]) < 1e-12
    up = pd.Series([0.1, 0.1, 0.1, 0.1])  # 단조 상승 → MDD 0, 승률 1
    mu = bt.perf(up)
    assert mu["total"] > 0 and abs(mu["mdd"]) < 1e-12 and mu["win"] == 1.0


def test_perf_mdd_negative():
    rets = pd.Series([0.2, -0.5, 0.1])  # 중간에 -50% → MDD 음수
    m = bt.perf(rets)
    assert m["mdd"] < -0.4, f"MDD가 큰 낙폭 반영해야 (got {m['mdd']})"


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
