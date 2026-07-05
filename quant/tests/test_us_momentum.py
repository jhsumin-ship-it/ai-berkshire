#!/usr/bin/env python3
"""미국 모멘텀 퀀트 순수로직 테스트(합성 데이터, 네트워크 無). 실행: python quant/tests/test_us_momentum.py"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import numpy as np
import pandas as pd
import us_momentum as um


def _panel():
    """60주 합성 가격 패널: A는 강한 상승(모멘텀 최고), E는 하락(최저)."""
    idx = pd.date_range("2025-01-03", periods=60, freq="W-FRI")
    data = {
        "A": np.linspace(100, 300, 60),   # +200% 강모멘텀
        "B": np.linspace(100, 180, 60),   # +80%
        "C": np.linspace(100, 140, 60),   # +40%
        "D": np.linspace(100, 110, 60),   # +10%
        "E": np.linspace(100, 60, 60),    # -40% 하락
    }
    return pd.DataFrame(data, index=idx)


def test_momentum_ranks_high_to_low():
    px = _panel()
    ranked = um.momentum_series(px, lookback=52, skip=4)
    # A가 1위, E가 꼴찌
    assert ranked.index[0] == "A", f"기대 A 1위, 실제 {ranked.index[0]}"
    assert ranked.index[-1] == "E"
    # 모멘텀은 skip 반영: 최근 4주 제외한 구간 수익
    assert ranked["A"] > ranked["B"] > ranked["C"]


def test_momentum_insufficient_data_raises():
    px = _panel().iloc[:30]  # 30주 < 53주 필요
    try:
        um.momentum_series(px, lookback=52, skip=4)
        assert False, "데이터 부족 시 예외 필요"
    except ValueError:
        pass


def test_select_top_n_equal_weight():
    px = _panel()
    ranked = um.momentum_series(px, lookback=52, skip=4)
    picks = um.select(ranked, px.iloc[-1], holdings=[], n_hold=3, buffer=20)
    assert len(picks) == 3
    assert list(picks["code"]) == ["A", "B", "C"]  # 상위 3
    assert abs(picks["weight"].sum() - 100.0) < 1e-6  # 동일가중 합 100%
    assert abs(picks.loc[0, "weight"] - 100 / 3) < 1e-6


def test_buffer_keeps_existing_holding():
    """버퍼: 기존 보유가 순위버퍼 안이면 유지(교체 억제)."""
    px = _panel()
    ranked = um.momentum_series(px, lookback=52, skip=4)
    # D는 4위(순위 4). buffer=20이면 유지, n_hold=3
    picks = um.select(ranked, px.iloc[-1], holdings=["D"], n_hold=3, buffer=20)
    assert "D" in set(picks["code"]), "버퍼 안 보유종목 유지"
    assert len(picks) == 3


def test_buffer_drops_when_out_of_buffer():
    """버퍼 밖(순위>buffer)이면 교체."""
    px = _panel()
    ranked = um.momentum_series(px, lookback=52, skip=4)
    # E는 5위(꼴찌). buffer=3이면 3위 밖 → 교체됨
    picks = um.select(ranked, px.iloc[-1], holdings=["E"], n_hold=3, buffer=3)
    assert "E" not in set(picks["code"]), "버퍼 밖 보유종목 교체"
    assert list(picks["code"]) == ["A", "B", "C"]


def test_select_empty_when_no_valid():
    empty = pd.Series(dtype=float)
    picks = um.select(empty, pd.Series(dtype=float), holdings=[], n_hold=10, buffer=20)
    assert picks.empty


def _sector_panel():
    """5종목: A~D는 반도체(모멘텀 순), E는 소프트웨어."""
    idx = pd.date_range("2025-01-03", periods=60, freq="W-FRI")
    data = {
        "A": np.linspace(100, 300, 60),
        "B": np.linspace(100, 250, 60),
        "C": np.linspace(100, 200, 60),
        "D": np.linspace(100, 160, 60),
        "E": np.linspace(100, 130, 60),  # 소프트웨어, 모멘텀 최하
    }
    smap = {"A": "반도체", "B": "반도체", "C": "반도체", "D": "반도체", "E": "소프트웨어"}
    return pd.DataFrame(data, index=idx), smap


def test_sector_cap_limits_concentration():
    """섹터당 최대 2면, 반도체 4종목(A~D) 중 상위 2개만 담고 나머지는 다른 섹터로."""
    px, smap = _sector_panel()
    ranked = um.momentum_series(px, lookback=52, skip=4)
    picks = um.select(ranked, px.iloc[-1], holdings=[], n_hold=3, buffer=20,
                      sector_map=smap, max_per_sector=2)
    semis = [c for c in picks["code"] if smap[c] == "반도체"]
    assert len(semis) == 2, f"반도체 최대 2 기대, 실제 {len(semis)}"
    assert "E" in set(picks["code"]), "상한으로 밀려 다른 섹터(E) 편입"
    assert list(picks["code"]) == ["A", "B", "E"]  # 반도체 상위 2 + 소프트웨어


def test_sector_cap_zero_means_no_limit():
    """max_per_sector=0이면 상한 없음(전부 반도체 가능)."""
    px, smap = _sector_panel()
    ranked = um.momentum_series(px, lookback=52, skip=4)
    picks = um.select(ranked, px.iloc[-1], holdings=[], n_hold=3, buffer=20,
                      sector_map=smap, max_per_sector=0)
    assert list(picks["code"]) == ["A", "B", "C"]  # 상한 없으면 반도체 상위 3


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
