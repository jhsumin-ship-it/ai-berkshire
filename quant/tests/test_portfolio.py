#!/usr/bin/env python3
"""주간 리밸런싱 매매리스트 로직 테스트. 실행: python quant/tests/test_portfolio.py"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import pandas as pd
import portfolio as pf

COST = {"commission": 0.00015, "slippage": 0.001, "sell_tax": 0.0018}


def _picks(rows):
    return pd.DataFrame(rows)


def test_first_rebalance_all_new_buys():
    picks = _picks([{"code": "A", "weight": 60.0}, {"code": "B", "weight": 40.0}])
    port = {"cash": 1_000_000, "positions": {}}
    prices = {"A": 1000, "B": 2000}
    res = pf.build_trades(picks, port, prices, {"A": "s", "B": "s"}, {"A": "A", "B": "B"}, 0.03, COST)
    df = res["trades"]
    assert set(df["action"]) == {"신규매수"}, "보유0이면 전부 신규매수"
    a = df[df["code"] == "A"].iloc[0]
    assert a["shares"] == 600, f"A 60%×100만/1000 = 600주 (got {a['shares']})"
    assert res["summary"]["sells"] == 0


def test_band_holds_small_drift():
    # 현재 A 50%, 목표 A 52% → 드리프트 2%p < 밴드3%p → 유지
    picks = _picks([{"code": "A", "weight": 52.0}, {"code": "B", "weight": 48.0}])
    total = 1_000_000
    # A 500주×1000=50만(50%), B 250주×2000=50만(50%), cash 0
    port = {"cash": 0, "positions": {"A": 500, "B": 250}}
    prices = {"A": 1000, "B": 2000}
    res = pf.build_trades(picks, port, prices, {}, {}, 0.03, COST)
    df = res["trades"]
    a = df[df["code"] == "A"].iloc[0]
    assert a["action"] == "유지(밴드내)" and a["shares"] == 0, "밴드내는 거래 없음"


def test_exit_when_dropped():
    picks = _picks([{"code": "A", "weight": 100.0}])
    port = {"cash": 0, "positions": {"A": 500, "B": 250}}
    prices = {"A": 1000, "B": 2000}
    res = pf.build_trades(picks, port, prices, {}, {}, 0.03, COST)
    b = res["trades"][res["trades"]["code"] == "B"].iloc[0]
    assert b["action"] == "전량매도" and b["shares"] < 0, "목표서 빠지면 전량매도"


def test_load_portfolio_default(tmpname="__no_such_file__.yaml"):
    p = pf.load_portfolio(tmpname, 5_000_000)
    assert p["cash"] == 5_000_000 and p["positions"] == {}, "파일 없으면 현금만"


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
