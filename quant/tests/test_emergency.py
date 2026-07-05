#!/usr/bin/env python3
"""긴급 급변동 evaluate() 순수로직 테스트(합성, 네트워크 無). 실행: python quant/tests/test_emergency.py"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import emergency as emg

CFG = {"emergency": {"index_pct": 5.0, "vix_level": 35.0,
                     "vix_jump_pct": 30.0, "holding_pct": 10.0}}


def test_index_crash_triggers():
    obs = {"indices": {"KOSPI": -6.2, "S&P500": +1.1}}
    out = emg.evaluate(obs, CFG)
    assert len(out) == 1
    assert out[0]["name"] == "KOSPI" and out[0]["direction"] == "급락"


def test_index_within_threshold_no_trigger():
    obs = {"indices": {"KOSPI": -4.9, "QQQ": +4.9}}
    assert emg.evaluate(obs, CFG) == []


def test_index_surge_triggers_up():
    obs = {"indices": {"나스닥100": +5.5}}
    out = emg.evaluate(obs, CFG)
    assert out[0]["direction"] == "급등"


def test_vix_high_level_triggers():
    obs = {"vix": {"level": 38.0, "change_pct": 5.0}}
    out = emg.evaluate(obs, CFG)
    assert len(out) == 1 and out[0]["kind"] == "VIX"


def test_vix_jump_triggers_even_if_level_low():
    obs = {"vix": {"level": 22.0, "change_pct": 33.0}}
    out = emg.evaluate(obs, CFG)
    assert len(out) == 1 and out[0]["direction"] == "급등"


def test_vix_calm_no_trigger():
    obs = {"vix": {"level": 18.0, "change_pct": 5.0}}
    assert emg.evaluate(obs, CFG) == []


def test_holding_crash_triggers():
    obs = {"holdings": {"삼성전자": -12.3, "AMD": +3.0}}
    out = emg.evaluate(obs, CFG)
    assert len(out) == 1 and out[0]["name"] == "삼성전자"


def test_none_values_ignored():
    obs = {"indices": {"KOSPI": None}, "vix": {"level": None, "change_pct": None},
           "holdings": {"AMD": None}}
    assert emg.evaluate(obs, CFG) == []


def test_multiple_triggers_combined():
    obs = {"indices": {"KOSPI": -7.0, "S&P500": -6.0},
           "vix": {"level": 42.0, "change_pct": 50.0},
           "holdings": {"NVDA": -15.0}}
    out = emg.evaluate(obs, CFG)
    assert len(out) == 4  # 2지수 + VIX + 1보유


def test_format_alarm_contains_guidance():
    out = emg.evaluate({"indices": {"KOSPI": -6.0}}, CFG)
    msg = emg.format_alarm(out)
    assert "긴급" in msg and "관망" in msg  # 인지용·관망 안내 포함


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
