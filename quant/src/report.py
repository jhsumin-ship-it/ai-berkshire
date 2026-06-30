#!/usr/bin/env python3
"""랭킹·포트폴리오 마크다운 리포트 생성 (AI Berkshire 퀀트)."""

from __future__ import annotations

import os

import pandas as pd


def _fmt(v, nd=0, pct=False, plus=False):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    s = f"{f:+,.{nd}f}" if plus else f"{f:,.{nd}f}"
    return s + ("%" if pct else "")


def render(ranked: pd.DataFrame, picks: pd.DataFrame, screened: pd.DataFrame,
           cfg: dict, asof: str) -> str:
    L = []
    L.append("# AI Berkshire 주간 리밸런싱 — 유니버스 랭킹 (Phase 1)\n")
    L.append(f"> **기준일** {asof} · **통화** KRW · **프레임워크** 가치·퀄리티 점수가중"
             f"(가치 {int(cfg['weights']['value']*100)} : 퀄리티 {int(cfg['weights']['quality']*100)})\n")
    L.append("> **데이터** 네이버페이 증권 모바일 API(시세·밸류·컨센서스·재무) · "
             "내부정합(PER≈주가/EPS) 자동검증 · 재무는 최근 회계연도 실적\n")
    L.append("> ⚠️ 투자권유 아님. 백테스트(Phase 2) 전 단계의 횡단면 스냅샷입니다.\n")

    # ── 이번 주 후보 포트폴리오 ──────────────────────────────
    L.append("\n## 1. 이번 주 후보 포트폴리오 (섹터별 상위 + 점수가중)\n")
    if picks.empty:
        L.append("_선별 종목 없음_\n")
    else:
        L.append("| # | 종목(코드) | 섹터 | 비중 | 현재가 | 등락 | PER | ROE | 영업이익률 | 부채비율 | 컨센목표가 | 상승여력 | 종합점수 |")
        L.append("|--:|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|")
        for i, r in picks.iterrows():
            L.append("| {n} | {nm}({cd}) | {sec} | **{w}%** | {px} | {chg} | {per} | {roe} | {opm} | {dr} | {tp} | {up} | {sc:+.2f} |".format(
                n=i + 1, nm=r["name"], cd=r["code"], sec=r["sector"],
                w=_fmt(r["weight"], 2), px=_fmt(r["price"]),
                chg=_fmt(r["change_pct"], 1, pct=True, plus=True),
                per=_fmt(r.get("per"), 1), roe=_fmt(r.get("roe"), 1, pct=True),
                opm=_fmt(r.get("op_margin"), 1, pct=True), dr=_fmt(r.get("debt_ratio"), 1, pct=True),
                tp=_fmt(r.get("target_price")), up=_fmt(r.get("upside"), 1, pct=True, plus=True),
                sc=r["score"]))
        # 섹터 비중 요약
        sw = picks.groupby("sector")["weight"].sum().sort_values(ascending=False)
        L.append("\n**섹터 비중**: " + " · ".join(f"{s} {w:.1f}%" for s, w in sw.items()))

    # ── 전체 통과 종목 랭킹 ──────────────────────────────────
    L.append("\n## 2. 전체 통과 종목 랭킹\n")
    L.append("| 순위 | 종목(코드) | 섹터 | 현재가 | PER | PBR | ROE | 영업이익률 | 순이익률 | 부채비율 | 상승여력 | 퀄리티z | 가치z | 종합 |")
    L.append("|--:|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|")
    for _, r in ranked.iterrows():
        L.append("| {rk} | {nm}({cd}) | {sec} | {px} | {per} | {pbr} | {roe} | {opm} | {npm} | {dr} | {up} | {qz:+.2f} | {vz:+.2f} | **{sc:+.2f}** |".format(
            rk=r["rank"], nm=r["name"], cd=r["code"], sec=r["sector"], px=_fmt(r["price"]),
            per=_fmt(r.get("per"), 1), pbr=_fmt(r.get("pbr"), 2), roe=_fmt(r.get("roe"), 1, pct=True),
            opm=_fmt(r.get("op_margin"), 1, pct=True), npm=_fmt(r.get("net_margin"), 1, pct=True),
            dr=_fmt(r.get("debt_ratio"), 1, pct=True), up=_fmt(r.get("upside"), 1, pct=True, plus=True),
            qz=r["quality_z"], vz=r["value_z"], sc=r["score"]))

    # ── 스크린 탈락 ──────────────────────────────────────────
    out = screened[screened["screen_out"] != ""]
    L.append(f"\n## 3. 스크린 탈락 ({len(out)}종)\n")
    if out.empty:
        L.append("_없음_\n")
    else:
        L.append("| 종목(코드) | 섹터 | 사유 |")
        L.append("|---|---|---|")
        for _, r in out.sort_values("sector").iterrows():
            L.append(f"| {r['name']}({r['code']}) | {r['sector']} | {r['screen_out']} |")

    # ── 정합 경고 ────────────────────────────────────────────
    flagged = screened[screened["flags"].apply(lambda x: bool(x))]
    if not flagged.empty:
        L.append("\n## 4. 데이터 정합 경고 (피드 오류 의심)\n")
        for _, r in flagged.iterrows():
            L.append(f"- {r['name']}({r['code']}): {'; '.join(r['flags'])}")

    L.append("\n---\n*AI Berkshire quant Phase 1 — `python quant/run.py rank`. "
             "데이터=네이버 모바일 API, 정밀계산=pandas. 투자권유 아님.*")
    return "\n".join(L)


def _pc(v):
    return "—" if v is None else f"{v*100:+.1f}%"


def render_backtest(res: dict, cfg: dict, asof: str, plot_path: str | None = None) -> str:
    bt = cfg["backtest"]
    L = []
    L.append("# AI Berkshire 주간 리밸런싱 — 백테스트 (Phase 2)\n")
    L.append(f"> **기간** {bt['start']} ~ {bt['end']} · 주간({bt['rebalance']}) · "
             f"{res['n_weeks']}주 · 평균보유 {res['avg_holdings']:.1f}종\n")
    L.append(f"> **팩터** 퀄리티(ROE·영업이익률·순이익률·부채비율역) + 가치"
             f"({'·'.join(bt['value_factors'])}) · 가치:퀄리티 50:50\n")
    L.append(f"> **비용** 수수료 {bt['cost']['commission']*100:.3f}% + 슬리피지 "
             f"{bt['cost']['slippage']*100:.2f}% (편도) + 매도세 {bt['cost']['sell_tax']*100:.2f}%\n")
    L.append("> ⚠️ **point-in-time**: 회계연도말+공시시차 90일 후 재무만 사용(룩어헤드 차단). "
             "컨센 상승여력·배당은 과거시점 확보 불가로 백테스트 제외. **투자권유 아님.**\n")

    # 성과 요약
    L.append("\n## 1. 성과 요약\n")
    L.append("| 전략/벤치 | 누적수익 | CAGR | 변동성 | Sharpe | MDD | 주간승률 |")
    L.append("|---|--:|--:|--:|--:|--:|--:|")
    for nm, m in res["metrics"].items():
        if not m:
            continue
        bold = "**" if nm == "전략" else ""
        L.append(f"| {bold}{nm}{bold} | {_pc(m['total'])} | {_pc(m['cagr'])} | "
                 f"{m['vol']*100:.1f}% | {m['sharpe']:.2f} | {_pc(m['mdd'])} | {m['win']*100:.0f}% |")

    if plot_path:
        rel = os.path.relpath(plot_path, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        L.append(f"\n![자산곡선]({os.path.basename(plot_path)})\n")

    # 연도별 수익
    L.append("\n## 2. 연도별 수익률\n")
    yr = _yearly(res)
    cols = list(yr.columns)
    L.append("| 연도 | " + " | ".join(cols) + " |")
    L.append("|---|" + "|".join(["--:"] * len(cols)) + "|")
    for y, row in yr.iterrows():
        L.append(f"| {y} | " + " | ".join(_pc(row[c]) for c in cols) + " |")

    # 보유 빈도 상위
    L.append("\n## 3. 보유 빈도 상위 (선별 단골)\n")
    hc = sorted(res["holdings_count"].items(), key=lambda x: -x[1])[:15]
    L.append("| 종목 | 선택 주수 | 비율 |")
    L.append("|---|--:|--:|")
    for code, cnt in hc:
        L.append(f"| {res['name_of'].get(code, code)}({code}) | {cnt} | {cnt/res['n_weeks']*100:.0f}% |")

    L.append("\n## 4. 한계\n")
    L.append("- **데이터 구간 짧음(~2.25년)**: 네이버 연간재무 4개년 한계 → FY2023 공시 이후만 "
             "point-in-time 가능. 더 긴 백테스트는 DART 시점데이터 필요(Phase 2.1).")
    L.append("- **컨센·배당 팩터 제외**: 과거시점 확보 불가. 즉 본 백테스트는 '재구성 가능한 "
             "가치·퀄리티'만 검증(= Phase 1 발견 #1의 '컨센 노이즈 제거' 버전).")
    L.append("- **유동성 스크린 해제**(과거 거래대금 미수집), 생존편향(현 유니버스 기준) 잔존.")
    L.append("- 비용·슬리피지는 가정치. 세금·체결지연 실제와 다를 수 있음. **백테스트 ≠ 실전.**")
    L.append("\n---\n*AI Berkshire quant Phase 2 — `python quant/run.py backtest`. 투자권유 아님.*")
    return "\n".join(L)


def _yearly(res: dict) -> pd.DataFrame:
    series = {"전략": res["strategy"], "동일가중유니버스": res["eqw"], **res["benches"]}
    out = {}
    for nm, s in series.items():
        g = (1 + s).groupby(s.index.year).prod() - 1
        out[nm] = g
    return pd.DataFrame(out)


def render_rebalance(picks, trades_res: dict, port: dict, cfg: dict, asof: str) -> str:
    s = trades_res["summary"]
    df = trades_res["trades"]
    w = cfg["weights"]
    L = []
    L.append("# AI Berkshire 주간 리밸런싱 — 매매지시 (Phase 3)\n")
    L.append(f"> **기준일** {asof} · **전략** 퀄{int(w['quality']*100)}·가치{int(w['value']*100)}·"
             f"모멘{int(w['momentum']*100)} 블렌드 · 회전율밴드 ±{cfg['rebalance']['band']*100:.0f}%p\n")
    L.append(f"> **총자산** {s['total']:,.0f}원 (현금 {s['cash']:,.0f} + 보유 {s['holdings_val']:,.0f}) · "
             f"기존보유 {len(port['positions'])}종\n")
    L.append("> ⚠️ 시세=네이버 실시간. 체결 전 호가·수량 재확인. **투자권유 아님.**\n")

    # 매매지시
    L.append("\n## 1. 매매 지시\n")
    L.append("| 종목(코드) | 섹터 | 액션 | 현재→목표 비중 | 주수 | 금액(원) | 현재가 |")
    L.append("|---|---|---|--:|--:|--:|--:|")
    order = {"신규매수": 0, "추가매수": 1, "일부매도": 2, "전량매도": 3, "유지(밴드내)": 4}
    for _, r in df.sort_values(by="action", key=lambda s: s.map(order)).iterrows():
        sh = r["shares"]
        sh_s = "—" if sh == 0 else f"{sh:+,d}"
        val_s = "—" if r["trade_val"] == 0 else f"{r['trade_val']:+,.0f}"
        L.append(f"| {r['name']}({r['code']}) | {r['sector']} | {r['action']} | "
                 f"{r['cur_w']*100:.1f}% → {r['tgt_w']*100:.1f}% | {sh_s} | {val_s} | {r['price']:,.0f} |")

    # 요약
    L.append("\n## 2. 거래 요약\n")
    L.append(f"- 거래 종목수: **{s['n_trades']}종** (밴드내 유지는 거래 없음)")
    L.append(f"- 매수 {s['buys']:,.0f}원 · 매도 {s['sells']:,.0f}원 · 회전율 {s['turnover']*100:.1f}%")
    L.append(f"- 예상 거래비용: {s['est_cost']:,.0f}원 ({s['est_cost']/s['total']*100:.2f}%)")
    L.append(f"- 거래후 현금(추정): {s['new_cash']:,.0f}원")

    # 거래 후 보유(예상)
    L.append("\n## 3. 거래 후 목표 포트폴리오\n")
    L.append("| 종목(코드) | 섹터 | 목표비중 | 보유주수(예상) | 평가액 |")
    L.append("|---|---|--:|--:|--:|")
    for _, r in picks.iterrows():
        c = r["code"]
        tw = r["weight"] / 100.0
        px = r.get("price") or 0
        sh = int(tw * s["total"] / px) if px else 0
        L.append(f"| {r['name']}({c}) | {r['sector']} | {tw*100:.1f}% | {sh:,} | {sh*px:,.0f} |")

    L.append("\n## 4. 주의\n")
    L.append("- 블렌드는 **2.25년 단일레짐** 백테스트 기반. 모멘텀은 급반전에 취약 — 분할체결·손절원칙 병행.")
    L.append("- 밴드 ±3%p 안은 유지(거래비용 절감). 매주 실행 권장.")
    L.append("- 보유현황은 `quant/portfolio.yaml`(cash·positions)로 갱신.")
    L.append("\n---\n*AI Berkshire quant Phase 3 — `python quant/run.py rebalance`. 투자권유 아님.*")
    return "\n".join(L)


def render_variants(comp: dict, cfg: dict, asof: str, plot_path: str | None = None,
                    long_mode: bool = False) -> str:
    bt = cfg["backtest"]
    base = comp["base"]
    variants = comp["variants"]
    L = []
    phase = "Phase 2.1 — 장기 다레짐(DART 재무)" if long_mode else "Phase 2.5"
    L.append(f"# AI Berkshire 주간 리밸런싱 — 팩터 A/B 비교 ({phase})\n")
    L.append(f"> **기간** {bt['start']} ~ {bt['end']} · 주간 · {base['n_weeks']}주 · "
             f"동일 데이터/비용/캡으로 팩터 조합만 변경\n")
    src = ("재무 = **DART 정본 다년(FY2017~2025)** + 주식수환산 eps/bps. "
           "2022 둔화·2023 반도체적자·2024~26 호황을 모두 포함." if long_mode
           else "모멘텀 = 26주(6개월) 수익률(point-in-time). 컨센·배당 제외(과거 확보불가).")
    L.append(f"> {src} **투자권유 아님.**\n")

    # 변형 + 벤치 통합 성과표 (CAGR 내림차순)
    rows = []
    for nm, res in variants.items():
        rows.append((nm, res["metrics"]["전략"], "variant"))
    rows.append(("동일가중유니버스", base["metrics"]["동일가중유니버스"], "bench"))
    for bnm, bs in base["benches"].items():
        rows.append((bnm, base["metrics"][bnm], "bench"))
    rows = [r for r in rows if r[1]]
    rows.sort(key=lambda x: -x[1]["cagr"])

    L.append("\n## 1. 성과 비교 (CAGR 순)\n")
    L.append("| 순 | 전략/벤치 | 누적 | CAGR | 변동성 | Sharpe | MDD | 승률 |")
    L.append("|--:|---|--:|--:|--:|--:|--:|--:|")
    for i, (nm, m, kind) in enumerate(rows, 1):
        mark = "" if kind == "variant" else " _(벤치)_"
        bold = "**" if (kind == "variant" and nm.endswith("(기준)")) else ""
        L.append(f"| {i} | {bold}{nm}{bold}{mark} | {_pc(m['total'])} | {_pc(m['cagr'])} | "
                 f"{m['vol']*100:.1f}% | {m['sharpe']:.2f} | {_pc(m['mdd'])} | {m['win']*100:.0f}% |")

    if plot_path:
        L.append(f"\n![자산곡선 비교]({os.path.basename(plot_path)})\n")

    # 연도별(변형만)
    L.append("\n## 2. 변형별 연도 수익률\n")
    yrs = sorted({y for res in variants.values() for y in (1 + res["strategy"]).groupby(res["strategy"].index.year).prod().index})
    L.append("| 전략 | " + " | ".join(str(y) for y in yrs) + " | 종합CAGR |")
    L.append("|---|" + "|".join(["--:"] * (len(yrs) + 1)) + "|")
    for nm, res in variants.items():
        g = (1 + res["strategy"]).groupby(res["strategy"].index.year).prod() - 1
        cells = [_pc(g.get(y)) for y in yrs]
        L.append(f"| {nm} | " + " | ".join(cells) + f" | {_pc(res['metrics']['전략']['cagr'])} |")
    # 벤치 연도
    bg = (1 + base["benches"].get("KODEX200", base["eqw"])).groupby(base["eqw"].index.year).prod() - 1 if base["benches"] else None
    eg = (1 + base["eqw"]).groupby(base["eqw"].index.year).prod() - 1
    L.append(f"| _동일가중(벤치)_ | " + " | ".join(_pc(eg.get(y)) for y in yrs) + f" | {_pc(base['metrics']['동일가중유니버스']['cagr'])} |")
    for bnm, bm in base["benches"].items():
        g = (1 + bm).groupby(bm.index.year).prod() - 1
        L.append(f"| _{bnm}(벤치)_ | " + " | ".join(_pc(g.get(y)) for y in yrs) + f" | {_pc(base['metrics'][bnm]['cagr'])} |")

    # 해석
    L.append("\n## 3. 한계\n")
    if long_mode:
        L.append("- DART 12월결산 가정·연결(CFS) 우선. 일부 종목 corp_code/연결 결측 시 해당주 제외.")
        L.append("- 가치팩터 eps/bps는 **현재 주식수 고정 환산**(과거 증자·분할 미반영, 근사).")
        L.append("- 생존편향(현 유니버스)·신규상장종목은 상장 전 자동 제외.")
    else:
        L.append("- 단일 레짐(2024~26 AI 불장) 2.25년 — 모멘텀 우위는 이 구간 특성일 수 있음(레짐 의존).")
        L.append("- 모멘텀 추가는 회전율·비용↑. 본 비용가정(편도 0.115%+매도세) 하 순수익 기준.")
    L.append("- **백테스트 ≠ 실전.** 비용·슬리피지는 가정치.")
    cmd = "backtest-long" if long_mode else "compare"
    L.append(f"\n---\n*AI Berkshire quant — `python quant/run.py {cmd}`. 투자권유 아님.*")
    return "\n".join(L)

