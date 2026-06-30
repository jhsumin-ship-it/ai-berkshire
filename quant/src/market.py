#!/usr/bin/env python3
"""전체시장(KOSPI·KOSDAQ) 후보 발굴 — 유니버스 자동확장 (AI Berkshire Phase 5).

네이버 시총순위 API는 전체시장(KOSPI 약 2,500 + KOSDAQ 약 1,800)을 코드·시총·거래대금과
함께 페이지로 제공 → 'cheap 사전필터(시총·유동성) → 상위 후보만 심층 스크리닝'의 정통 펀넬.
PER/ROE 등 팩터는 후보로 좁힌 뒤 종목별 심층호출(naver.fetch_stock)로 채운다.
"""

from __future__ import annotations

import time

import requests

_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://m.stock.naver.com/"}
_LIST = "https://m.stock.naver.com/api/stocks/marketValue/{market}?page={page}&pageSize={size}"


def _num(v):
    if v in (None, "", "-"):
        return None
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return None


def fetch_market_list(market: str, max_n: int, page_size: int = 100, pause: float = 0.1) -> list[dict]:
    """시총 내림차순 상위 max_n 종목 {code, name, market, mcap, trading_value_eok}."""
    out = []
    page = 1
    while len(out) < max_n:
        url = _LIST.format(market=market, page=page, size=page_size)
        try:
            j = requests.get(url, headers=_HEADERS, timeout=15).json()
        except Exception:  # noqa: BLE001
            break
        stocks = j.get("stocks") or []
        if not stocks:
            break
        for s in stocks:
            tv = _num(s.get("accumulatedTradingValueRaw")) or _num(s.get("accumulatedTradingValue"))
            out.append({
                "code": s.get("itemCode"),
                "name": s.get("stockName"),
                "market": market,
                "mcap": _num(s.get("marketValueRaw")) or _num(s.get("marketValue")),
                "trading_value_eok": (tv / 1e8) if tv else None,
            })
            if len(out) >= max_n:
                break
        if len(stocks) < page_size:
            break
        page += 1
        time.sleep(pause)
    return out


def build_candidates(markets, top_per_market: int, min_trading_eok: float) -> list[dict]:
    """시장별 시총 상위 top_per_market 후보. 유동성은 심층 스크린에서 재확인.

    (시총순위 API의 거래대금은 장 마감시간대 결측일 수 있어, 사전필터는 시총만으로 하고
     유동성 컷은 심층 단계 apply_screen의 거래대금으로 적용한다.)
    """
    cand = []
    for m in markets:
        lst = fetch_market_list(m, top_per_market)
        for r in lst:
            tv = r.get("trading_value_eok")
            if tv is None or tv >= min_trading_eok:
                cand.append(r)
    # 중복 코드 제거(우선 먼저 나온 것)
    seen, uniq = set(), []
    for r in cand:
        if r["code"] not in seen:
            seen.add(r["code"])
            uniq.append(r)
    return uniq
