#!/usr/bin/env python3
"""주간 리밸런싱 백테스트 엔진 (AI Berkshire 퀀트 Phase 2).

설계 원칙
  - point-in-time: 각 리밸런싱 시점 D에서, 공시시차(reporting_lag) 지난 최신 회계연도
    재무만 사용 → 룩어헤드 차단.
  - 과거 재구성 가능한 팩터만: 퀄리티(ROE·영업이익률·순이익률·부채비율역) +
    가치(이익수익률·순자산수익률). 컨센 상승여력·배당은 과거시점 확보 불가 → 백테스트 제외.
  - 비용: 매수·매도 회전율에 수수료·슬리피지, 매도엔 거래세 추가.
  - 벤치마크: (1) 동일가중 유니버스 (팩터선별의 순수 알파) (2) KODEX200 (시장).
"""

from __future__ import annotations

import calendar
import datetime as dt
import json
import os

import pandas as pd

import re

import factors
import rank_select
import history
import dart

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def parse_korean_mcap(s) -> float | None:
    """'1,938조 5,504억' / '8,256억' / '2조 8,742억' → KRW(float)."""
    if not s:
        return None
    t = str(s).replace(",", "").replace(" ", "")
    val = 0.0
    mjo = re.search(r"([\d.]+)조", t)
    meok = re.search(r"([\d.]+)억", t)
    if mjo:
        val += float(mjo.group(1)) * 1e12
    if meok:
        val += float(meok.group(1)) * 1e8
    if not mjo and not meok:
        n = re.search(r"[\d.]+", t)
        return float(n.group()) if n else None
    return val or None


def _load_shares(cfg: dict) -> dict:
    """{code: 주식수} = 시가총액 / 현재가 (최근 snapshot에서). 가치팩터 환산용."""
    snaps = [f for f in os.listdir(DATA_DIR) if f.startswith("snapshot-")] if os.path.isdir(DATA_DIR) else []
    if not snaps:
        return {}
    with open(os.path.join(DATA_DIR, sorted(snaps)[-1]), encoding="utf-8") as f:
        recs = json.load(f)
    out = {}
    for r in recs:
        mc = parse_korean_mcap(r.get("market_value_raw"))
        px = r.get("price")
        if mc and px:
            out[r["code"]] = mc / px
    return out


def build_panels_dart(cfg: dict, use_cache: bool = True) -> dict:
    """장기 패널: DART 다년 재무 + 연장 가격(2019~). 가치팩터용 eps/bps는 주식수로 환산."""
    blt = cfg["backtest"]
    codes = [u["code"] for u in cfg["universe"]]
    bench = blt.get("benchmarks", {})
    px_path = os.path.join(DATA_DIR, "prices_long.csv")
    fu_path = os.path.join(DATA_DIR, "fundamentals_dart.json")
    os.makedirs(DATA_DIR, exist_ok=True)

    if use_cache and os.path.exists(px_path) and os.path.exists(fu_path):
        prices = pd.read_csv(px_path, index_col=0, parse_dates=True)
        with open(fu_path, encoding="utf-8") as f:
            fund = {k: {int(fy): v for fy, v in d.items()} for k, d in json.load(f).items()}
        print(f"캐시 사용: {px_path} ({prices.shape[1]}종), {fu_path}")
        return {"prices": prices, "fund": fund, "bench": list(bench.keys())}

    s = blt.get("price_history_start", "2019-06-01").replace("-", "")
    e = blt["end"].replace("-", "")
    series = {}
    for n, c in enumerate(codes + list(bench.keys()), 1):
        try:
            ser = history.fetch_price_history(c, s, e)
            if len(ser):
                series[c] = ser
            print(f"  가격 [{n}/{len(codes)+len(bench)}] {c} … {len(ser)}일")
        except Exception as ex:  # noqa: BLE001
            print(f"  가격 [{n}] {c} … ERROR:{ex}")
    prices = pd.DataFrame(series).sort_index()

    shares = _load_shares(cfg)
    cmap = dart.corp_code_map()
    fund = {}
    for n, c in enumerate(codes, 1):
        cc = cmap.get(c)
        if not cc:
            fund[c] = {}
            print(f"  재무 [{n}/{len(codes)}] {c} … corp_code 없음")
            continue
        try:
            hist = dart.fetch_history(cc)
        except Exception as ex:  # noqa: BLE001
            hist = {}
            print(f"  재무 [{n}/{len(codes)}] {c} … ERROR:{ex}")
            continue
        sh = shares.get(c)
        for fy, rec in hist.items():
            ni, eq = rec.get("net_income"), rec.get("equity")
            rec["eps"] = (ni / sh) if (sh and ni is not None) else None
            rec["bps"] = (eq / sh) if (sh and eq is not None) else None
        fund[c] = hist
        print(f"  재무 [{n}/{len(codes)}] {c} … FY{sorted(hist.keys())}")

    prices.to_csv(px_path)
    with open(fu_path, "w", encoding="utf-8") as f:
        json.dump({k: {str(fy): v for fy, v in d.items()} for k, d in fund.items()},
                  f, ensure_ascii=False)
    print(f"저장: {px_path}, {fu_path}")
    return {"prices": prices, "fund": fund, "bench": list(bench.keys())}


# ── 데이터 패널 구축 ─────────────────────────────────────────
def build_panels(cfg: dict, use_cache: bool = True) -> dict:
    bt = cfg["backtest"]
    start, end = bt["start"], bt["end"]
    codes = [u["code"] for u in cfg["universe"]]
    bench = bt.get("benchmarks", {})
    os.makedirs(DATA_DIR, exist_ok=True)
    px_path = os.path.join(DATA_DIR, "prices.csv")
    fu_path = os.path.join(DATA_DIR, "fundamentals.json")

    if use_cache and os.path.exists(px_path) and os.path.exists(fu_path):
        prices = pd.read_csv(px_path, index_col=0, parse_dates=True)
        with open(fu_path, encoding="utf-8") as f:
            fund = {k: {int(fy): v for fy, v in d.items()} for k, d in json.load(f).items()}
        print(f"캐시 사용: {px_path} ({prices.shape[1]}종), {fu_path}")
        return {"prices": prices, "fund": fund, "bench": list(bench.keys())}

    s, e = start.replace("-", ""), end.replace("-", "")
    series = {}
    all_codes = codes + list(bench.keys())
    for n, c in enumerate(all_codes, 1):
        try:
            ser = history.fetch_price_history(c, s, e)
            if len(ser):
                series[c] = ser
            tag = f"{len(ser)}일" if len(ser) else "빈값"
        except Exception as ex:  # noqa: BLE001
            tag = f"ERROR:{ex}"
        print(f"  가격 [{n:2d}/{len(all_codes)}] {c} … {tag}")
    prices = pd.DataFrame(series).sort_index()

    fund = {}
    for n, c in enumerate(codes, 1):
        try:
            fund[c] = history.fetch_fundamentals_history(c)
            tag = f"FY{sorted(fund[c].keys())}"
        except Exception as ex:  # noqa: BLE001
            fund[c] = {}
            tag = f"ERROR:{ex}"
        print(f"  재무 [{n:2d}/{len(codes)}] {c} … {tag}")

    prices.to_csv(px_path)
    with open(fu_path, "w", encoding="utf-8") as f:
        json.dump({k: {str(fy): v for fy, v in d.items()} for k, d in fund.items()},
                  f, ensure_ascii=False)
    print(f"저장: {px_path}, {fu_path}")
    return {"prices": prices, "fund": fund, "bench": list(bench.keys())}


# ── point-in-time 재무 ───────────────────────────────────────
def _fy_end(fy: int) -> dt.date:
    y, m = fy // 100, fy % 100
    return dt.date(y, m, calendar.monthrange(y, m)[1])


def fundamentals_asof(fmap: dict, date: dt.date, lag_days: int):
    """date 시점에 '공시되어 알 수 있는' 최신 실적연도 재무 반환 (fy, dict) or None."""
    best = None
    for fy, d in fmap.items():
        if d.get("debt_ratio") is None and d.get("roe") is None:
            continue  # 빈 추정연도
        avail = _fy_end(fy) + dt.timedelta(days=lag_days)
        if avail <= date and (best is None or fy > best[0]):
            best = (fy, d)
    return best


# ── 백테스트 ─────────────────────────────────────────────────
def _cost(target: pd.Series, prev: pd.Series, c: dict) -> float:
    idx = target.index.union(prev.index)
    delta = target.reindex(idx).fillna(0) - prev.reindex(idx).fillna(0)
    buys = delta[delta > 0].sum()
    sells = -delta[delta < 0].sum()
    return buys * (c["commission"] + c["slippage"]) + sells * (c["commission"] + c["slippage"] + c["sell_tax"])


def default_spec(cfg: dict) -> dict:
    """기준 변형: 가치50·퀄50 (모멘텀 없음)."""
    return {
        "name": "가치50·퀄50",
        "quality_factors": cfg["quality_factors"],
        "value_factors": cfg["backtest"]["value_factors"],
        "momentum_factors": [],
        "weights": {"quality": 0.5, "value": 0.5, "momentum": 0.0},
        "mom_lookback": 26,
    }


def _bt_cfg(cfg: dict, spec: dict) -> dict:
    """백테스트용 cfg: spec의 팩터·가중 주입, 유동성 스크린 해제(과거 거래대금 미수집)."""
    c = json.loads(json.dumps(cfg))  # deep copy
    c["quality_factors"] = spec["quality_factors"]
    c["value_factors"] = spec["value_factors"]
    c["momentum_factors"] = spec.get("momentum_factors", [])
    c["weights"] = spec["weights"]
    c["screen"]["min_trading_value_eok"] = 0
    return c


def run(cfg: dict, panels: dict, spec: dict | None = None) -> dict:
    bt = cfg["backtest"]
    spec = spec or default_spec(cfg)
    cbt = _bt_cfg(cfg, spec)
    use_mom = bool(spec.get("momentum_factors"))
    lookback = int(spec.get("mom_lookback", 26))
    prices = panels["prices"]
    fund = panels["fund"]
    bench_codes = panels["bench"]
    name_of = {u["code"]: u["name"] for u in cfg["universe"]}
    sector_of = {u["code"]: u["sector"] for u in cfg["universe"]}
    uni = [u["code"] for u in cfg["universe"]]

    weekly = prices.resample(bt["rebalance"]).last()
    weekly = weekly.loc[(weekly.index >= bt["start"]) & (weekly.index <= bt["end"])]
    dates = list(weekly.index)
    lag = bt["reporting_lag_days"]

    port_rets, eqw_rets = [], []
    bench_rets = {b: [] for b in bench_codes}
    ret_dates = []
    prev_w = pd.Series(dtype=float)
    holdings_count: dict[str, int] = {}
    n_holdings = []

    for i in range(len(dates) - 1):
        d0, d1 = dates[i], dates[i + 1]
        d0d = d0.date()
        # 모멘텀: d0 기준 lookback주 수익률 (point-in-time, 룩어헤드 없음)
        mom_s = None
        if use_mom and i >= lookback:
            mom_s = weekly.iloc[i] / weekly.iloc[i - lookback] - 1
        rows = []
        for c in uni:
            if c not in weekly.columns:
                continue
            px = weekly.at[d0, c]
            if pd.isna(px) or px <= 0:
                continue
            f = fundamentals_asof(fund.get(c, {}), d0d, lag)
            if f is None:
                continue
            fy, fd = f
            eps, bps = fd.get("eps"), fd.get("bps")
            mom = float(mom_s[c]) if (mom_s is not None and c in mom_s and pd.notna(mom_s[c])) else None
            rows.append({
                "code": c, "name": name_of.get(c, c), "sector": sector_of.get(c, ""),
                "flags": [], "price": px,
                "roe": fd.get("roe"), "op_margin": fd.get("op_margin"),
                "net_margin": fd.get("net_margin"), "debt_ratio": fd.get("debt_ratio"),
                "net_income": fd.get("net_income"), "eps": eps,
                "earnings_yield": (eps / px * 100) if eps else None,
                "book_yield": (bps / px * 100) if bps else None,
                "mom": mom,
            })
        if not rows:
            continue
        df = pd.DataFrame(rows)
        df = factors.compute_scores(df, cbt)
        screened = rank_select.apply_screen(df, cbt)
        ranked = rank_select.rank_universe(screened)
        picks = rank_select.select_portfolio(ranked, cfg)

        # 다음주 수익률
        r = (weekly.loc[d1] / weekly.loc[d0] - 1)

        if picks.empty:
            target = pd.Series(dtype=float)
        else:
            target = pd.Series((picks["weight"] / 100).values, index=picks["code"].values)
        port_gross = float((target * r.reindex(target.index).fillna(0)).sum()) if len(target) else 0.0
        cost = _cost(target, prev_w, bt["cost"]) if len(target) or len(prev_w) else 0.0
        port_rets.append(port_gross - cost)

        # 동일가중 유니버스 벤치(스크린 통과 종목)
        elig = ranked["code"].tolist()
        er = r.reindex(elig).dropna()
        eqw_rets.append(float(er.mean()) if len(er) else 0.0)

        # 지수 벤치
        for b in bench_codes:
            if b in weekly.columns and pd.notna(weekly.at[d0, b]) and pd.notna(weekly.at[d1, b]):
                bench_rets[b].append(float(weekly.at[d1, b] / weekly.at[d0, b] - 1))
            else:
                bench_rets[b].append(0.0)

        ret_dates.append(d1)
        n_holdings.append(len(target))
        for c in target.index:
            holdings_count[c] = holdings_count.get(c, 0) + 1

        # 다음 비교용: 타깃을 수익률로 드리프트
        if len(target):
            grown = target * (1 + r.reindex(target.index).fillna(0))
            prev_w = grown / grown.sum() if grown.sum() else target
        else:
            prev_w = pd.Series(dtype=float)

    strat = pd.Series(port_rets, index=ret_dates, name="strategy")
    eqw = pd.Series(eqw_rets, index=ret_dates, name="eqw")
    benches = {panels_name(cfg, b): pd.Series(v, index=ret_dates, name=b)
               for b, v in bench_rets.items()}

    return {
        "strategy": strat, "eqw": eqw, "benches": benches,
        "holdings_count": holdings_count, "name_of": name_of,
        "avg_holdings": float(pd.Series(n_holdings).mean()) if n_holdings else 0,
        "n_weeks": len(strat),
        "metrics": {
            "전략": perf(strat),
            "동일가중유니버스": perf(eqw),
            **{nm: perf(s) for nm, s in benches.items()},
        },
        "weeks_index": ret_dates,
    }


def panels_name(cfg, code):
    return cfg["backtest"]["benchmarks"].get(code, code)


# ── 성과지표 ─────────────────────────────────────────────────
def perf(rets: pd.Series, periods_per_year: int = 52) -> dict:
    rets = rets.dropna()
    if len(rets) == 0:
        return {}
    eq = (1 + rets).cumprod()
    total = float(eq.iloc[-1] - 1)
    yrs = len(rets) / periods_per_year
    cagr = float(eq.iloc[-1] ** (1 / yrs) - 1) if yrs > 0 else 0.0
    vol = float(rets.std(ddof=0) * (periods_per_year ** 0.5))
    sharpe = cagr / vol if vol else 0.0
    dd = eq / eq.cummax() - 1
    mdd = float(dd.min())
    win = float((rets > 0).mean())
    return {"total": total, "cagr": cagr, "vol": vol, "sharpe": sharpe,
            "mdd": mdd, "win": win, "equity_end": float(eq.iloc[-1])}


def equity_frame(res: dict) -> pd.DataFrame:
    cols = {"전략": res["strategy"], "동일가중유니버스": res["eqw"]}
    cols.update(res["benches"])
    eq = pd.DataFrame({k: (1 + v).cumprod() for k, v in cols.items()})
    return eq


def variant_specs(cfg: dict) -> list[dict]:
    """A/B 비교 변형 정의. 모멘텀(mom)은 6개월(26주) 수익률."""
    qf = cfg["quality_factors"]
    vf = cfg["backtest"]["value_factors"]
    mom = ["mom"]
    def s(name, q, v, m, wq, wv, wm):
        return {"name": name, "quality_factors": q, "value_factors": v, "momentum_factors": m,
                "weights": {"quality": wq, "value": wv, "momentum": wm}, "mom_lookback": 26}
    return [
        s("가치50·퀄50(기준)", qf, vf, [], 0.5, 0.5, 0.0),
        s("퀄70·가치30",       qf, vf, [], 0.7, 0.3, 0.0),
        s("가치70·퀄30",       qf, vf, [], 0.3, 0.7, 0.0),
        s("퀄50·가치25·모멘25", qf, vf, mom, 0.5, 0.25, 0.25),
        s("퀄40·모멘60",       qf, [], mom, 0.4, 0.0, 0.6),
        s("모멘텀100(순수)",    [], [], mom, 0.0, 0.0, 1.0),
    ]


def run_variants(cfg: dict, panels: dict, specs: list[dict]) -> dict:
    """여러 변형을 동일 데이터/기간에 돌려 비교. 벤치마크는 첫 실행 것 공유."""
    out = {"variants": {}, "base": None}
    for n, spec in enumerate(specs, 1):
        print(f"  변형 [{n}/{len(specs)}] {spec['name']} …")
        res = run(cfg, panels, spec)
        out["variants"][spec["name"]] = res
        if out["base"] is None:
            out["base"] = res
    return out
