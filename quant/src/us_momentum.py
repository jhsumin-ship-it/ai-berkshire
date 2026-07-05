#!/usr/bin/env python3
"""미국 성장주 모멘텀 퀀트 — 나스닥100 12-1 모멘텀 상위 10 동일가중.

데이터: yfinance 일별 → W-FRI 주간 리샘플(정렬 보장). 통화: USD.
선택: 12-1 모멘텀(lookback~skip주) 상위 n_hold, 순위버퍼(기존 보유가 buffer 밖일 때만 교체).
리밸런싱 트레이드는 portfolio.build_trades 재사용(USD 기준).
"""

from __future__ import annotations

import pandas as pd


def weekly_prices(tickers: list[str], period: str = "2y") -> pd.DataFrame:
    """yfinance 일별 종가 → W-FRI 주간. period는 모멘텀 룩백보다 충분히 길게(기본 2년)."""
    import yfinance as yf
    tickers = [str(t) for t in tickers]  # 방어: YAML 불리언(ON/OFF 등) → 문자열 강제
    d = yf.download(tickers, period=period, interval="1d",
                    progress=False, auto_adjust=True)["Close"]
    if isinstance(d, pd.Series):
        d = d.to_frame()
    return d.resample("W-FRI").last()


def usdkrw() -> float:
    """현재 USD/KRW 환율(원). 실패 시 예외."""
    import yfinance as yf
    fx = yf.download("KRW=X", period="5d", interval="1d",
                     progress=False, auto_adjust=True)["Close"]
    if isinstance(fx, pd.DataFrame):
        fx = fx.iloc[:, 0]
    v = float(fx.dropna().iloc[-1])
    if not (500 < v < 3000):  # 내부정합: 환율 상식 범위
        raise ValueError(f"USDKRW 이상치: {v}")
    return v


def momentum_series(px: pd.DataFrame, lookback: int, skip: int) -> pd.Series:
    """최신 시점 12-1 모멘텀 = (skip주 전) / (lookback주 전) - 1. 유효종목만."""
    need = lookback + 1
    if len(px) < need:
        raise ValueError(f"가격 데이터 부족: {len(px)}주 < 필요 {need}주")
    p_now = px.iloc[-1]
    p_skip = px.iloc[-1 - skip]
    p_back = px.iloc[-1 - lookback]
    mom = p_skip / p_back - 1
    ok = p_now.notna() & p_skip.notna() & p_back.notna() & (p_back > 0) & (p_now > 0)
    return mom[ok].dropna().sort_values(ascending=False)


def select(ranked: pd.Series, prices_now: pd.Series, holdings: list[str],
           n_hold: int, buffer: int) -> pd.DataFrame:
    """모멘텀 순위 + 순위버퍼로 보유 n_hold종목 선택 → picks(code·weight·price·mom·name)."""
    rank_of = {tk: r for r, tk in enumerate(ranked.index, 1)}
    keep = [h for h in holdings if rank_of.get(h, 10 ** 9) <= buffer]
    target: list[str] = list(keep)
    for tk in ranked.index:
        if len(target) >= n_hold:
            break
        if tk not in target:
            target.append(tk)
    target = target[:n_hold]
    if not target:
        return pd.DataFrame(columns=["code", "name", "sector", "weight", "price", "mom"])
    w = 100.0 / len(target)  # 동일가중(합 정확히 100). 표시 시에만 반올림.
    rows = [{
        "code": tk, "name": tk, "sector": "US",
        "weight": w, "price": float(prices_now.get(tk, 0.0)),
        "mom": float(ranked.get(tk, float("nan"))),
    } for tk in target]
    return pd.DataFrame(rows)


def build_picks(cfg: dict, holdings: list[str],
                px: pd.DataFrame | None = None) -> tuple[pd.DataFrame, pd.Series]:
    """설정+보유 → (picks, 현재가Series). px 미지정 시 yfinance 수집."""
    s = cfg["strategy"]
    if px is None:
        px = weekly_prices(cfg["universe"])
    ranked = momentum_series(px, s["lookback_weeks"], s["skip_weeks"])
    picks = select(ranked, px.iloc[-1], holdings, s["n_hold"], s["buffer"])
    return picks, px.iloc[-1]


def render_report(picks: pd.DataFrame, trades: dict, port: dict,
                  fx: float, asof: str) -> str:
    """미국 리밸런싱 매매지시 리포트(md). USD·KRW 병기."""
    s = trades["summary"]
    total_usd = s["total"]
    lines = [
        f"# AI Berkshire 미국 성장주 모멘텀 — 매매지시",
        "",
        f"> **기준일** {asof} · **전략** 나스닥100 12-1 모멘텀 상위{len(picks)}·동일가중 · 순위버퍼20",
        f"> **총자산** ${total_usd:,.0f} (≈ {total_usd * fx:,.0f}원, 환율 {fx:,.1f}) · 기존보유 {len(port['positions'])}종",
        f"> ⚠️ 시세=yfinance(지연가능). 미국장 시간대 유의. 양도세 22%·환리스크 별도. **투자권유 아님.**",
        "",
        "## 1. 매매 지시 (USD)",
        "",
        "| 종목 | 액션 | 현재→목표 | 주수 | 금액($) | 현재가($) | 모멘텀 |",
        "|---|---|--:|--:|--:|--:|--:|",
    ]
    order = {"신규매수": 0, "추가매수": 1, "일부매도": 2, "전량매도": 3, "유지(밴드내)": 4}
    tdf = trades["trades"].sort_values(by="action", key=lambda x: x.map(order))
    mom_of = {r["code"]: r.get("mom") for _, r in picks.iterrows()}
    for _, r in tdf.iterrows():
        sh = "—" if r["shares"] == 0 else f"{int(r['shares']):+,d}"
        m = mom_of.get(r["code"])
        mtag = f"{m*100:+.0f}%" if m is not None and pd.notna(m) else "—"
        lines.append(
            f"| {r['name']} | {r['action']} | {r['cur_w']*100:.1f}%→{r['tgt_w']*100:.1f}% | "
            f"{sh} | {r['trade_val']:+,.0f} | {r['price']:,.2f} | {mtag} |")
    lines += [
        "",
        "## 2. 거래 요약",
        f"- 거래 종목수: **{s['n_trades']}종** · 회전율 {s['turnover']*100:.1f}%",
        f"- 매수 ${s['buys']:,.0f} · 매도 ${s['sells']:,.0f} · 예상비용 ${s['est_cost']:,.0f}",
        f"- 거래후 현금(추정): ${s['new_cash']:,.0f}",
        "",
        "## 3. 주의",
        "- **실행은 수동**: 현 자동매매(키움)는 한국 전용. 미국 실주문은 별도 브로커에서 직접 체결.",
        "- 체결 후 `quant/us_portfolio.yaml`(cash·positions) 갱신 필수(다음 신호 정확화).",
        "- 모멘텀은 급반전(2022 -23%)에 취약. 백테스트는 생존편향으로 낙관 → forward 보수적.",
        "",
        "---",
        "*AI Berkshire 미국 모멘텀 퀀트 — `python quant/run.py us-rebalance`. 투자권유 아님.*",
    ]
    return "\n".join(lines)
