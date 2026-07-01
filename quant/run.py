#!/usr/bin/env python3
"""AI Berkshire 주간 리밸런싱 퀀트 — CLI (Phase 1).

사용법:
    python quant/run.py update-data        # 네이버에서 유니버스 전종목 수집 → 캐시
    python quant/run.py rank                # 점수화·랭킹·후보포트 → reports/quant/ 리포트
    python quant/run.py rank --no-fetch     # 캐시만 사용(재수집 안 함)

Phase 2(백테스트)·Phase 3(주간 리밸런싱 매매리스트)는 후속.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
try:
    sys.stdout.reconfigure(encoding="utf-8")  # 윈도우 콘솔 한글 깨짐 방지
except Exception:  # noqa: BLE001
    pass

import pandas as pd  # noqa: E402
import yaml  # noqa: E402

import naver  # noqa: E402
import factors  # noqa: E402
import rank_select  # noqa: E402
import report as report_mod  # noqa: E402
import backtest as bt_mod  # noqa: E402
import history  # noqa: E402
import portfolio as pf_mod  # noqa: E402
import market as market_mod  # noqa: E402
import notify as notify_mod  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")
REPORT_DIR = os.path.join(os.path.dirname(ROOT), "reports", "quant")


def load_cfg() -> dict:
    with open(os.path.join(ROOT, "config.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def _snapshot_path(asof: str) -> str:
    return os.path.join(DATA_DIR, f"snapshot-{asof}.json")


def update_data(cfg: dict, asof: str) -> list[dict]:
    os.makedirs(DATA_DIR, exist_ok=True)
    uni = cfg["universe"]
    lookback = int(cfg.get("mom_lookback_weeks", 26))
    recs = []
    for n, u in enumerate(uni, 1):
        code, name, sector = u["code"], u["name"], u["sector"]
        try:
            rec = naver.fetch_stock(code)
            rec["sector"] = sector
            rec["name"] = rec.get("name") or name
            rec["mom"] = history.recent_momentum(code, lookback)  # 라이브 모멘텀
            mtag = f" mom={rec['mom']*100:+.0f}%" if rec["mom"] is not None else " mom=NA"
            status = ("OK" if not rec["flags"] else "FLAG:" + ";".join(rec["flags"])) + mtag
        except Exception as e:  # noqa: BLE001
            rec = {"code": code, "name": name, "sector": sector, "flags": [], "error": str(e)}
            status = f"ERROR:{e}"
        recs.append(rec)
        print(f"  [{n:2d}/{len(uni)}] {name}({code}) … {status}")
    with open(_snapshot_path(asof), "w", encoding="utf-8") as f:
        json.dump(recs, f, ensure_ascii=False, indent=2)
    print(f"\n저장: {_snapshot_path(asof)}  ({len(recs)}종)")
    return recs


def load_snapshot(asof: str) -> list[dict] | None:
    p = _snapshot_path(asof)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _resolve_recs(cfg: dict, asof: str, fetch: bool) -> list[dict]:
    recs = None if fetch else load_snapshot(asof)
    if recs is None:
        if not fetch:
            print("캐시 없음 → 수집 실행")
        print("네이버에서 유니버스 수집 중…")
        recs = update_data(cfg, asof)
    return recs


def _rank_frame(cfg: dict, recs: list[dict]):
    df = pd.DataFrame([r for r in recs if "error" not in r])
    df = factors.compute_scores(df, cfg)
    screened = rank_select.apply_screen(df, cfg)
    ranked = rank_select.rank_universe(screened)
    picks = rank_select.select_portfolio(ranked, cfg)
    return df, screened, ranked, picks


def rank(cfg: dict, asof: str, fetch: bool = True) -> None:
    recs = _resolve_recs(cfg, asof, fetch)
    errs = [r for r in recs if "error" in r]
    if errs:
        print(f"\n수집 실패 {len(errs)}종: " + ", ".join(f"{r['name']}({r['code']})" for r in errs))

    df, screened, ranked, picks = _rank_frame(cfg, recs)

    md = report_mod.render(ranked, picks, screened, cfg, asof)
    os.makedirs(REPORT_DIR, exist_ok=True)
    out_path = os.path.join(REPORT_DIR, f"주간랭킹-{asof}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md)

    # 콘솔 요약
    print("\n" + "=" * 72)
    print(f"통과 {len(ranked)}종 / 전체 {len(df)}종 · 후보포트 {len(picks)}종")
    print("=" * 72)
    print(f"{'순위':>3} {'종목':<14} {'섹터':<12} {'종합':>7} {'ROE':>6} {'PER':>6} {'상승여력':>8}")
    for _, r in ranked.head(15).iterrows():
        print(f"{r['rank']:>3} {str(r['name'])[:13]:<14} {str(r['sector'])[:11]:<12} "
              f"{r['score']:>+7.2f} {(r.get('roe') or 0):>5.1f}% {(r.get('per') or 0):>6.1f} "
              f"{(r.get('upside') or 0):>+7.1f}%")
    print("\n── 이번 주 후보 포트폴리오 ──")
    for i, r in picks.iterrows():
        print(f"  {r['weight']:>5.1f}%  {str(r['name'])[:13]:<14} {str(r['sector'])[:11]:<12} "
              f"(점수 {r['score']:+.2f}, 상승여력 {(r.get('upside') or 0):+.1f}%)")
    print(f"\n리포트: {out_path}")


def backtest(cfg: dict, asof: str, fetch: bool = False) -> None:
    print("백테스트 데이터 패널 구축 중…")
    panels = bt_mod.build_panels(cfg, use_cache=not fetch)
    print("백테스트 실행 중…")
    res = bt_mod.run(cfg, panels)

    plot_path = _plot_equity(res, asof)
    md = report_mod.render_backtest(res, cfg, asof, plot_path)
    os.makedirs(REPORT_DIR, exist_ok=True)
    out_path = os.path.join(REPORT_DIR, f"백테스트-{asof}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md)
    eq = bt_mod.equity_frame(res)
    eq.to_csv(os.path.join(DATA_DIR, f"equity-{asof}.csv"))

    print("\n" + "=" * 72)
    print(f"백테스트 {cfg['backtest']['start']} ~ {cfg['backtest']['end']} · {res['n_weeks']}주")
    print("=" * 72)
    print(f"{'전략/벤치':<18}{'누적':>9}{'CAGR':>8}{'변동성':>8}{'Sharpe':>8}{'MDD':>9}")
    for nm, m in res["metrics"].items():
        if not m:
            continue
        print(f"{nm:<18}{m['total']*100:>+8.1f}%{m['cagr']*100:>+7.1f}%"
              f"{m['vol']*100:>7.1f}%{m['sharpe']:>8.2f}{m['mdd']*100:>+8.1f}%")
    print(f"\n리포트: {out_path}")


def rebalance(cfg: dict, asof: str, fetch: bool = True, send: bool = False) -> None:
    recs = _resolve_recs(cfg, asof, fetch)
    df, screened, ranked, picks = _rank_frame(cfg, recs)
    if picks.empty:
        print("선별 종목 없음 — 매매지시 생략")
        return

    prices = {r["code"]: r.get("price") for r in recs if r.get("price")}
    sectors = {u["code"]: u["sector"] for u in cfg["universe"]}
    names = {u["code"]: u["name"] for u in cfg["universe"]}
    pf_path = os.path.join(ROOT, "portfolio.yaml")
    port = pf_mod.load_portfolio(pf_path, cfg["rebalance"]["default_cash"])

    trades = pf_mod.build_trades(
        picks, port, prices, sectors, names,
        cfg["rebalance"]["band"], cfg["backtest"]["cost"])

    md = report_mod.render_rebalance(picks, trades, port, cfg, asof)
    os.makedirs(REPORT_DIR, exist_ok=True)
    out_path = os.path.join(REPORT_DIR, f"리밸런싱-{asof}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md)

    s = trades["summary"]
    print("\n" + "=" * 72)
    print(f"주간 리밸런싱 · 총자산 {s['total']:,.0f}원 · 거래 {s['n_trades']}종 · "
          f"회전율 {s['turnover']*100:.1f}% · 예상비용 {s['est_cost']:,.0f}원")
    print("=" * 72)
    od = {"신규매수": 0, "추가매수": 1, "일부매도": 2, "전량매도": 3, "유지(밴드내)": 4}
    tdf = trades["trades"].sort_values(by="action", key=lambda x: x.map(od))
    for _, r in tdf.iterrows():
        sh = "—" if r["shares"] == 0 else f"{r['shares']:+,d}주"
        print(f"  {r['action']:<10} {str(r['name'])[:12]:<13} {r['cur_w']*100:>5.1f}%→{r['tgt_w']*100:>5.1f}%  {sh}")
    if port["positions"]:
        print(f"\n(보유현황 {pf_path} 사용)")
    else:
        print(f"\n(보유 없음 → 전량 신규매수 가정. {pf_path}로 현황 입력 가능)")
    print(f"리포트: {out_path}")

    if send:
        lines = [f"총자산 {s['total']:,.0f}원 · 거래 {s['n_trades']}종 · 회전율 {s['turnover']*100:.0f}%"]
        for _, r in tdf.iterrows():
            if r["shares"] == 0:
                continue
            lines.append(f"· {r['action']} {r['name']} → {r['tgt_w']*100:.0f}% ({r['shares']:+,d}주)")
        lines.append(f"예상비용 {s['est_cost']:,.0f}원")
        subject = f"[AI Berkshire] 주간 리밸런싱 {asof}"
        status = notify_mod.notify(subject, "\n".join(lines), cfg)
        print(f"발송: 텔레그램={status['telegram']} · Gmail={status['gmail']}")


def screen_market(cfg: dict, asof: str, fetch: bool = True, top_per_market: int | None = None) -> None:
    ms = cfg.get("market_screen", {})
    tpm = top_per_market or ms.get("top_per_market", 60)
    markets = ms.get("markets", ["KOSPI", "KOSDAQ"])
    min_tv = ms.get("min_trading_eok", 50)
    cache = os.path.join(DATA_DIR, f"market-snapshot-{asof}.json")

    if fetch or not os.path.exists(cache):
        print(f"전체시장 후보 발굴: {markets} 시총상위 {tpm}/시장, 거래대금≥{min_tv}억 …")
        cand = market_mod.build_candidates(markets, tpm, min_tv)
        print(f"후보 {len(cand)}종 → 심층 스크리닝(종목별 시세·재무)…")
        recs = []
        for i, c in enumerate(cand, 1):
            try:
                rec = naver.fetch_stock(c["code"])
                rec["sector"] = c["market"]
                rec["name"] = rec.get("name") or c["name"]
                recs.append(rec)
            except Exception:  # noqa: BLE001
                pass
            if i % 25 == 0:
                print(f"  … {i}/{len(cand)}")
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(cache, "w", encoding="utf-8") as f:
            json.dump(recs, f, ensure_ascii=False)
        print(f"저장: {cache} ({len(recs)}종)")
    else:
        with open(cache, encoding="utf-8") as f:
            recs = json.load(f)
        print(f"캐시 사용: {cache} ({len(recs)}종)")

    df = pd.DataFrame([r for r in recs if "error" not in r and r.get("price")])
    df = factors.compute_scores(df, cfg)
    screened = rank_select.apply_screen(df, cfg)
    ranked = rank_select.rank_universe(screened)

    params = {"n_cand": len(df), "top_per_market": tpm, "min_trading_eok": min_tv,
              "show_top": ms.get("show_top", 40)}
    md = report_mod.render_market(ranked, screened, asof, params)
    os.makedirs(REPORT_DIR, exist_ok=True)
    out_path = os.path.join(REPORT_DIR, f"전체시장스크린-{asof}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md)

    print("\n" + "=" * 72)
    print(f"전체시장 스크린 · 후보 {len(df)}종 · 통과 {len(ranked)}종")
    print("=" * 72)
    print(f"{'순위':>3} {'종목':<14} {'시장':<7} {'종합':>7} {'ROE':>6} {'PER':>7}")
    for _, r in ranked.head(20).iterrows():
        print(f"{r['rank']:>3} {str(r['name'])[:13]:<14} {str(r['sector'])[:6]:<7} "
              f"{r['score']:>+7.2f} {(r.get('roe') or 0):>5.1f}% {(r.get('per') or 0):>7.1f}")
    print(f"\n리포트: {out_path}")


def backtest_long(cfg: dict, asof: str, fetch: bool = False) -> None:
    print("장기 다레짐 패널 구축 중(DART 재무 + 2019~ 가격)…")
    panels = bt_mod.build_panels_dart(cfg, use_cache=not fetch)
    # 장기 윈도우로 백테스트 기간 override
    cfg = dict(cfg)
    cfg["backtest"] = dict(cfg["backtest"])
    cfg["backtest"]["start"] = cfg["backtest"].get("long_start", "2020-01-03")
    specs = bt_mod.variant_specs(cfg)
    print(f"장기 팩터 변형 {len(specs)}종 비교({cfg['backtest']['start']}~{cfg['backtest']['end']})…")
    comp = bt_mod.run_variants(cfg, panels, specs)

    plot_path = _plot_variants(comp, f"장기-{asof}")
    md = report_mod.render_variants(comp, cfg, asof, plot_path, long_mode=True)
    os.makedirs(REPORT_DIR, exist_ok=True)
    out_path = os.path.join(REPORT_DIR, f"백테스트-장기다레짐-{asof}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md)

    print("\n" + "=" * 78)
    print(f"장기 다레짐 백테스트 · {comp['base']['n_weeks']}주 · {cfg['backtest']['start']}~{cfg['backtest']['end']}")
    print("=" * 78)
    rows = [(nm, r["metrics"]["전략"]) for nm, r in comp["variants"].items()]
    rows.append(("동일가중유니버스", comp["base"]["metrics"]["동일가중유니버스"]))
    for bnm in comp["base"]["benches"]:
        rows.append((bnm, comp["base"]["metrics"][bnm]))
    rows = [r for r in rows if r[1]]
    rows.sort(key=lambda x: -x[1]["cagr"])
    print(f"{'전략/벤치':<22}{'누적':>9}{'CAGR':>8}{'Sharpe':>8}{'MDD':>9}")
    for nm, m in rows:
        print(f"{nm:<22}{m['total']*100:>+8.1f}%{m['cagr']*100:>+7.1f}%{m['sharpe']:>8.2f}{m['mdd']*100:>+8.1f}%")
    print(f"\n리포트: {out_path}")


def compare(cfg: dict, asof: str, fetch: bool = False) -> None:
    print("백테스트 데이터 패널 구축 중…")
    panels = bt_mod.build_panels(cfg, use_cache=not fetch)
    specs = bt_mod.variant_specs(cfg)
    print(f"팩터 변형 {len(specs)}종 비교 실행 중…")
    comp = bt_mod.run_variants(cfg, panels, specs)

    plot_path = _plot_variants(comp, asof)
    md = report_mod.render_variants(comp, cfg, asof, plot_path)
    os.makedirs(REPORT_DIR, exist_ok=True)
    out_path = os.path.join(REPORT_DIR, f"백테스트-팩터비교-{asof}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md)

    print("\n" + "=" * 78)
    print(f"팩터 A/B 비교 · {comp['base']['n_weeks']}주 · {cfg['backtest']['start']}~{cfg['backtest']['end']}")
    print("=" * 78)
    rows = [(nm, r["metrics"]["전략"]) for nm, r in comp["variants"].items()]
    rows.append(("동일가중유니버스", comp["base"]["metrics"]["동일가중유니버스"]))
    for bnm in comp["base"]["benches"]:
        rows.append((bnm, comp["base"]["metrics"][bnm]))
    rows = [r for r in rows if r[1]]
    rows.sort(key=lambda x: -x[1]["cagr"])
    print(f"{'전략/벤치':<22}{'누적':>9}{'CAGR':>8}{'Sharpe':>8}{'MDD':>9}")
    for nm, m in rows:
        print(f"{nm:<22}{m['total']*100:>+8.1f}%{m['cagr']*100:>+7.1f}%{m['sharpe']:>8.2f}{m['mdd']*100:>+8.1f}%")
    print(f"\n리포트: {out_path}")


def _plot_variants(comp: dict, asof: str):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        try:
            plt.rcParams["font.family"] = "Malgun Gothic"
            plt.rcParams["axes.unicode_minus"] = False
        except Exception:  # noqa: BLE001
            pass
    except Exception:  # noqa: BLE001
        print("(matplotlib 없음 → 그래프 생략)")
        return None
    fig, ax = plt.subplots(figsize=(10, 5.5))
    for nm, res in comp["variants"].items():
        eq = (1 + res["strategy"]).cumprod()
        ax.plot(eq.index, eq.values, label=nm, linewidth=1.6)
    base = comp["base"]
    eqw = (1 + base["eqw"]).cumprod()
    ax.plot(eqw.index, eqw.values, label="동일가중(벤치)", linewidth=1.2, linestyle="--", color="gray")
    for bnm, bs in base["benches"].items():
        eb = (1 + bs).cumprod()
        ax.plot(eb.index, eb.values, label=f"{bnm}(벤치)", linewidth=1.2, linestyle=":")
    ax.set_title("Factor Variants — Equity Curve")
    ax.set_ylabel("Growth of 1")
    ax.legend(fontsize=8); ax.grid(alpha=0.3)
    path = os.path.join(REPORT_DIR, f"백테스트-팩터비교-{asof}.png")
    os.makedirs(REPORT_DIR, exist_ok=True)
    fig.tight_layout(); fig.savefig(path, dpi=110); plt.close(fig)
    return path


def _plot_equity(res: dict, asof: str):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:  # noqa: BLE001
        print("(matplotlib 없음 → 그래프 생략, CSV만 저장)")
        return None
    eq = bt_mod.equity_frame(res)
    fig, ax = plt.subplots(figsize=(9, 5))
    for col in eq.columns:
        lw = 2.4 if col == "전략" else 1.2
        ax.plot(eq.index, eq[col], label=col, linewidth=lw)
    try:
        plt.rcParams["font.family"] = "Malgun Gothic"
        plt.rcParams["axes.unicode_minus"] = False
    except Exception:  # noqa: BLE001
        pass
    ax.set_title("Weekly Rebalancing Backtest — Equity Curve")
    ax.set_ylabel("Growth of 1")
    ax.legend(); ax.grid(alpha=0.3)
    path = os.path.join(REPORT_DIR, f"백테스트-equity-{asof}.png")
    os.makedirs(REPORT_DIR, exist_ok=True)
    fig.tight_layout(); fig.savefig(path, dpi=110); plt.close(fig)
    return path


def main():
    ap = argparse.ArgumentParser(description="AI Berkshire 주간 리밸런싱 퀀트")
    sub = ap.add_subparsers(dest="cmd")
    p_up = sub.add_parser("update-data", help="네이버 유니버스 전종목 수집 → 캐시")
    p_up.add_argument("--asof", default=None, help="기준일 YYYYMMDD")
    p_rk = sub.add_parser("rank", help="점수화·랭킹·후보포트 리포트")
    p_rk.add_argument("--asof", default=None, help="기준일 YYYYMMDD")
    p_rk.add_argument("--no-fetch", action="store_true", help="캐시만 사용")
    p_bt = sub.add_parser("backtest", help="주간 리밸런싱 백테스트")
    p_bt.add_argument("--asof", default=None, help="기준일 YYYYMMDD")
    p_bt.add_argument("--fetch", action="store_true", help="시계열 재수집(기본: 캐시)")
    p_cmp = sub.add_parser("compare", help="팩터 변형 A/B 비교(horse race)")
    p_cmp.add_argument("--asof", default=None, help="기준일 YYYYMMDD")
    p_cmp.add_argument("--fetch", action="store_true", help="시계열 재수집(기본: 캐시)")
    p_rb = sub.add_parser("rebalance", help="주간 리밸런싱 매매지시 생성")
    p_rb.add_argument("--asof", default=None, help="기준일 YYYYMMDD")
    p_rb.add_argument("--no-fetch", action="store_true", help="캐시만 사용")
    p_rb.add_argument("--notify", action="store_true", help="텔레그램·Gmail 발송")
    p_bl = sub.add_parser("backtest-long", help="DART 다레짐 장기 백테스트(2020~, 2022 약세장 포함)")
    p_bl.add_argument("--asof", default=None, help="기준일 YYYYMMDD")
    p_bl.add_argument("--fetch", action="store_true", help="DART·시계열 재수집(기본: 캐시)")
    p_sm = sub.add_parser("screen-market", help="전체시장(KOSPI·KOSDAQ) 가치·퀄리티 스크린")
    p_sm.add_argument("--asof", default=None, help="기준일 YYYYMMDD")
    p_sm.add_argument("--no-fetch", action="store_true", help="캐시만 사용")
    p_sm.add_argument("--top", type=int, default=None, help="시장별 시총상위 N 사전필터")
    args = ap.parse_args()

    cfg = load_cfg()
    asof = getattr(args, "asof", None) or dt.date.today().strftime("%Y%m%d")

    if args.cmd == "update-data":
        update_data(cfg, asof)
    elif args.cmd == "rank":
        rank(cfg, asof, fetch=not args.no_fetch)
    elif args.cmd == "backtest":
        backtest(cfg, asof, fetch=args.fetch)
    elif args.cmd == "compare":
        compare(cfg, asof, fetch=args.fetch)
    elif args.cmd == "rebalance":
        rebalance(cfg, asof, fetch=not args.no_fetch, send=args.notify)
    elif args.cmd == "backtest-long":
        backtest_long(cfg, asof, fetch=args.fetch)
    elif args.cmd == "screen-market":
        screen_market(cfg, asof, fetch=not args.no_fetch, top_per_market=args.top)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
