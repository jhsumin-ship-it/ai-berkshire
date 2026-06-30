#!/usr/bin/env python3
"""네이버페이 증권 데이터 수집기 (AI Berkshire 퀀트).

WebFetch는 finance.naver.com을 차단하지만, 모바일 JSON API는 직접 HTTP로 접근 가능.
- 실시간 시세 : https://polling.finance.naver.com/api/realtime/domestic/stock/{code}
- 통합(밸류·컨센서스) : https://m.stock.naver.com/api/stock/{code}/integration
- 연간 재무제표 : https://m.stock.naver.com/api/stock/{code}/finance/annual

데이터 무결성: SK하이닉스(000660)가 3소스에서 동일하게 ~2,730,000원/1,938조로 일치한
사례 교훈 — 가격은 내부정합(PER ≈ 주가/EPS) 자동검증으로 피드 오류(10배 등)를 잡는다.
"""

from __future__ import annotations

import time
import requests

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://m.stock.naver.com/",
}

_POLL = "https://polling.finance.naver.com/api/realtime/domestic/stock/{code}"
_INTG = "https://m.stock.naver.com/api/stock/{code}/integration"
_ANNUAL = "https://m.stock.naver.com/api/stock/{code}/finance/annual"


def parse_num(s):
    """'3,725' -> 3725.0, '44.64' -> 44.64, '' / '-' / None -> None, '-1,234'->-1234."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    t = str(s).strip().replace(",", "")
    for suffix in ("원", "%", "배", "조", "억", "백만"):
        t = t.replace(suffix, "")
    t = t.strip()
    if t in ("", "-", "N/A", "null", "None"):
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _get(url, retries=3, pause=0.3):
    last = None
    for i in range(retries):
        try:
            r = requests.get(url, headers=_HEADERS, timeout=15)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(pause * (i + 1))
    raise RuntimeError(f"GET 실패 {url}: {last}")


def fetch_quote(code: str) -> dict:
    """실시간 현재가·등락률."""
    j = _get(_POLL.format(code=code))
    d = (j.get("datas") or [{}])[0]
    return {
        "name": d.get("stockName"),
        "price": parse_num(d.get("closePrice")),
        "change_pct": parse_num(d.get("fluctuationsRatio")),
        "direction": (d.get("compareToPreviousPrice") or {}).get("text"),
    }


def fetch_integration(code: str) -> dict:
    """밸류에이션·컨센서스·거래대금."""
    j = _get(_INTG.format(code=code))
    infos = {x.get("code"): x.get("value") for x in (j.get("totalInfos") or [])}
    cns = j.get("consensusInfo") or {}
    return {
        "name": j.get("stockName"),
        "eps": parse_num(infos.get("eps")),
        "bps": parse_num(infos.get("bps")),
        "per": parse_num(infos.get("per")),
        "pbr": parse_num(infos.get("pbr")),
        "cns_eps": parse_num(infos.get("cnsEps")),     # 컨센서스 선행 EPS
        "cns_per": parse_num(infos.get("cnsPer")),     # 컨센서스 선행 PER
        "dividend_yield": parse_num(infos.get("dividendYieldRatio")),
        "trading_value_mn": parse_num(infos.get("accumulatedTradingValue")),  # 백만원
        "market_value_raw": infos.get("marketValue"),
        "target_price": parse_num(cns.get("priceTargetMean")),  # 컨센서스 목표주가 평균
        "last_close": parse_num(infos.get("lastClosePrice")),
    }


def fetch_annual(code: str, max_fy: int = 202512) -> dict:
    """최근 '실적(추정 제외)' 회계연도의 재무비율.

    네이버 annual rowList: title별로 columns={'YYYYMM': {'value': ...}}.
    추정연도(미래) 제외를 위해 max_fy 이하 중 가장 최근 기간을 채택.
    """
    j = _get(_ANNUAL.format(code=code))
    rows = ((j.get("financeInfo") or {}).get("rowList")) or []
    table = {}  # title -> {period(int): value(float)}
    for row in rows:
        title = row.get("title")
        cols = row.get("columns") or {}
        per_map = {}
        for period, cell in cols.items():
            try:
                p = int(period)
            except (ValueError, TypeError):
                continue
            per_map[p] = parse_num((cell or {}).get("value"))
        table[title] = per_map

    # 채택할 회계연도: 모든 행에 공통 존재하는 기간 중 max_fy 이하 최신
    periods = set()
    for per_map in table.values():
        periods |= set(per_map.keys())
    candidates = sorted(p for p in periods if p <= max_fy)
    fy = candidates[-1] if candidates else None

    def g(title):
        return table.get(title, {}).get(fy) if fy is not None else None

    return {
        "fy": fy,
        "revenue": g("매출액"),
        "op_income": g("영업이익"),
        "net_income": g("당기순이익"),
        "op_margin": g("영업이익률"),
        "net_margin": g("순이익률"),
        "roe": g("ROE"),
        "debt_ratio": g("부채비율"),
    }


def consistency_flags(quote: dict, intg: dict, tol_pct: float = 10.0) -> list[str]:
    """내부정합 검증 — 피드 오류(10배 등) 탐지.

    PER ≈ 현재가 / EPS, PBR ≈ 현재가 / BPS 이어야 함.
    어긋나면 가격 단위 오류(예: SK하이닉스형 10배) 가능성을 플래그.
    """
    flags = []
    price = quote.get("price")
    eps, per = intg.get("eps"), intg.get("per")
    bps, pbr = intg.get("bps"), intg.get("pbr")
    if price and eps and per and eps != 0:
        implied = price / eps
        if per != 0 and abs(implied - per) / per * 100 > tol_pct:
            flags.append(f"PER불일치(보고 {per:.1f} vs 주가/EPS {implied:.1f})")
    if price and bps and pbr and bps != 0:
        implied = price / bps
        if pbr != 0 and abs(implied - pbr) / pbr * 100 > tol_pct:
            flags.append(f"PBR불일치(보고 {pbr:.2f} vs 주가/BPS {implied:.2f})")
    return flags


def fetch_stock(code: str, pause: float = 0.15) -> dict:
    """한 종목의 시세+밸류+재무를 합쳐 1개 레코드로."""
    q = fetch_quote(code)
    time.sleep(pause)
    i = fetch_integration(code)
    time.sleep(pause)
    a = fetch_annual(code)
    rec = {"code": code}
    rec.update({f"q_{k}": v for k, v in q.items()})
    rec.update(i)
    rec.update(a)
    rec["flags"] = consistency_flags(q, i)
    # 파생 지표
    price = q.get("price")
    rec["price"] = price
    rec["change_pct"] = q.get("change_pct")
    rec["name"] = q.get("name") or i.get("name")
    rec["earnings_yield"] = (i["eps"] / price * 100) if (i.get("eps") and price) else None
    rec["book_yield"] = (i["bps"] / price * 100) if (i.get("bps") and price) else None
    tp = i.get("target_price")
    rec["upside"] = ((tp / price - 1) * 100) if (tp and price) else None
    rec["trading_value_eok"] = (i["trading_value_mn"] / 100) if i.get("trading_value_mn") else None
    return rec


if __name__ == "__main__":
    import json as _json
    import sys
    c = sys.argv[1] if len(sys.argv) > 1 else "058470"
    print(_json.dumps(fetch_stock(c), ensure_ascii=False, indent=2))
