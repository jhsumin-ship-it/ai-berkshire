#!/usr/bin/env python3
"""긴급 급변동 감지 — 지수·VIX·보유종목 일간 급변동 → 텔레그램 알람.

설계: evaluate()는 순수로직(관측치→트리거), fetch_*()는 네트워크. 각 시장 마감 후 실행.
리밸런싱은 자동 안 함. 알람은 인지용이며 매매지시가 아니다(급락 반응매매는 대개 손해).
"""

from __future__ import annotations


def evaluate(observations: dict, cfg: dict) -> list[dict]:
    """관측치 → 임계 초과 트리거 리스트. 순수함수(네트워크 無).

    observations = {
      "indices": {name: 일간%},
      "vix": {"level": float, "change_pct": float},
      "holdings": {name: 일간%},
    }
    반환: [{kind, name, value, threshold, direction}]
    """
    e = cfg["emergency"]
    out: list[dict] = []

    for name, pct in (observations.get("indices") or {}).items():
        if pct is None:
            continue
        if abs(pct) >= e["index_pct"]:
            out.append({"kind": "지수", "name": name, "value": pct,
                        "threshold": e["index_pct"],
                        "direction": "급락" if pct < 0 else "급등"})

    vix = observations.get("vix") or {}
    lvl, chg = vix.get("level"), vix.get("change_pct")
    if lvl is not None and lvl >= e["vix_level"]:
        out.append({"kind": "VIX", "name": "VIX", "value": lvl,
                    "threshold": e["vix_level"], "direction": "고공(공포)"})
    elif chg is not None and chg >= e["vix_jump_pct"]:
        out.append({"kind": "VIX", "name": "VIX", "value": chg,
                    "threshold": e["vix_jump_pct"], "direction": "급등"})

    for name, pct in (observations.get("holdings") or {}).items():
        if pct is None:
            continue
        if abs(pct) >= e["holding_pct"]:
            out.append({"kind": "보유종목", "name": name, "value": pct,
                        "threshold": e["holding_pct"],
                        "direction": "급락" if pct < 0 else "급등"})
    return out


def _yf_daily_change(ticker: str):
    """yfinance 최근 2영업일 종가로 일간 등락률(%). (등락률, 최신값) 반환. 실패 시 (None, None)."""
    import yfinance as yf
    d = yf.download(ticker, period="7d", interval="1d",
                    progress=False, auto_adjust=True)["Close"]
    if hasattr(d, "columns"):
        d = d.iloc[:, 0]
    d = d.dropna()
    if len(d) < 2:
        return None, None
    last, prev = float(d.iloc[-1]), float(d.iloc[-2])
    if prev <= 0:
        return None, last
    return (last / prev - 1) * 100, last


def fetch_index_moves(cfg: dict) -> dict:
    """지수·VIX 일간 등락 수집(yfinance)."""
    indices = {}
    for tk, name in (cfg.get("indices") or {}).items():
        pct, _ = _yf_daily_change(tk)
        indices[name] = pct
    vpct, vlevel = _yf_daily_change(cfg.get("vix_ticker", "^VIX"))
    return {"indices": indices, "vix": {"level": vlevel, "change_pct": vpct}}


def fetch_holding_moves(kr_codes: list[str], us_tickers: list[str],
                        kr_names: dict | None = None) -> dict:
    """보유종목 일간 등락 수집. KR=naver change_pct, US=yfinance."""
    kr_names = kr_names or {}
    holdings = {}
    if kr_codes:
        import naver
        for code in kr_codes:
            try:
                rec = naver.fetch_stock(code)
                nm = rec.get("name") or kr_names.get(code) or code
                holdings[nm] = rec.get("change_pct")
            except Exception:  # noqa: BLE001
                pass
    for tk in us_tickers or []:
        pct, _ = _yf_daily_change(tk)
        holdings[tk] = pct
    return {"holdings": holdings}


def check_shocks(cfg: dict, kr_codes: list[str] | None = None,
                 us_tickers: list[str] | None = None,
                 kr_names: dict | None = None) -> list[dict]:
    """지수·VIX·보유종목 수집 → evaluate. 트리거 리스트 반환."""
    obs = fetch_index_moves(cfg)
    obs.update(fetch_holding_moves(kr_codes or [], us_tickers or [], kr_names))
    return evaluate(obs, cfg)


def format_alarm(triggered: list[dict]) -> str:
    """텔레그램 긴급 알람 메시지."""
    lines = ["🚨 <b>긴급 급변동 감지</b>"]
    for t in triggered:
        if t["kind"] == "VIX":
            v = f"{t['value']:.1f}" if t["direction"] != "급등" else f"+{t['value']:.0f}%"
            lines.append(f"· VIX {t['direction']} {v} (임계 {t['threshold']})")
        else:
            lines.append(f"· [{t['kind']}] {t['name']} {t['value']:+.1f}% "
                         f"{t['direction']} (임계 ±{t['threshold']:.0f}%)")
    lines.append("")
    lines.append("⚠️ 인지용 알람(매매지시 아님). 급락 반응매매는 대개 손해 — 관망이 기본.")
    lines.append("긴급 리밸런싱을 원하면 Claude에게 \"긴급 리밸런싱 돌려줘\"라고 하세요.")
    return "\n".join(lines)
