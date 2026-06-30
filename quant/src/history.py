#!/usr/bin/env python3
"""과거 시계열 수집 — 백테스트용 (AI Berkshire 퀀트 Phase 2).

- 일별시세: https://api.finance.naver.com/siseJson.naver  (6자리코드 직접, .KS/.KQ 불필요)
- 다년 연간재무: m.stock.naver.com/api/stock/{code}/finance/annual (전체 FY)

가격은 returns(수익률)로만 쓰므로 단위/스케일 무관. 재무는 회계연도별로 보관해
백테스트 시 '공시 시차(reporting lag)'를 적용해 룩어헤드를 방지한다.
"""

from __future__ import annotations

import ast
import time

import pandas as pd
import requests

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://finance.naver.com/",
}
_SISE = ("https://api.finance.naver.com/siseJson.naver"
         "?symbol={code}&requestType=1&startTime={start}&endTime={end}&timeframe=day")
_ANNUAL = "https://m.stock.naver.com/api/stock/{code}/finance/annual"


def _get_text(url, retries=3, pause=0.4):
    last = None
    for i in range(retries):
        try:
            r = requests.get(url, headers=_HEADERS, timeout=20)
            r.raise_for_status()
            return r.text
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(pause * (i + 1))
    raise RuntimeError(f"GET 실패 {url}: {last}")


def _get_json(url, retries=3, pause=0.4):
    last = None
    for i in range(retries):
        try:
            r = requests.get(url, headers=_HEADERS, timeout=20)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(pause * (i + 1))
    raise RuntimeError(f"GET 실패 {url}: {last}")


def fetch_price_history(code: str, start: str, end: str) -> pd.Series:
    """일별 종가 시계열(날짜 인덱스). start/end = 'YYYYMMDD'."""
    txt = _get_text(_SISE.format(code=code, start=start, end=end))
    rows = ast.literal_eval(txt.strip())  # 단일따옴표 파이썬 리터럴
    if not rows or len(rows) < 2:
        return pd.Series(dtype=float)
    header = rows[0]
    di = header.index("날짜")
    ci = header.index("종가")
    dates, closes = [], []
    for row in rows[1:]:
        try:
            dates.append(pd.to_datetime(str(row[di]), format="%Y%m%d"))
            closes.append(float(row[ci]))
        except (ValueError, TypeError, IndexError):
            continue
    s = pd.Series(closes, index=dates, name=code).sort_index()
    return s[~s.index.duplicated(keep="last")]


def _num(s):
    if s is None:
        return None
    t = str(s).strip().replace(",", "")
    for suf in ("원", "%", "배", "조", "억", "백만"):
        t = t.replace(suf, "")
    t = t.strip()
    if t in ("", "-", "N/A", "null", "None"):
        return None
    try:
        return float(t)
    except ValueError:
        return None


def fetch_fundamentals_history(code: str) -> dict:
    """{fy:int -> {roe, op_margin, net_margin, debt_ratio, eps, bps, net_income, revenue}}.

    네이버 annual은 보통 최근 3개 실적연도 + 1개 추정연도 제공.
    """
    j = _get_json(_ANNUAL.format(code=code))
    rows = ((j.get("financeInfo") or {}).get("rowList")) or []
    titles = {
        "매출액": "revenue", "영업이익": "op_income", "당기순이익": "net_income",
        "영업이익률": "op_margin", "순이익률": "net_margin", "ROE": "roe",
        "부채비율": "debt_ratio", "EPS": "eps", "BPS": "bps",
    }
    out: dict[int, dict] = {}
    for row in rows:
        key = titles.get(row.get("title"))
        if not key:
            continue
        for period, cell in (row.get("columns") or {}).items():
            try:
                fy = int(period)
            except (ValueError, TypeError):
                continue
            out.setdefault(fy, {})[key] = _num((cell or {}).get("value"))
    return out


def recent_momentum(code: str, lookback_weeks: int = 26) -> float | None:
    """오늘 기준 lookback_weeks(주) 수익률 — 라이브 모멘텀 팩터."""
    import datetime as dt
    end = dt.date.today()
    start = end - dt.timedelta(weeks=lookback_weeks + 12)
    try:
        px = fetch_price_history(code, start.strftime("%Y%m%d"), end.strftime("%Y%m%d"))
    except Exception:  # noqa: BLE001
        return None
    if len(px) < lookback_weeks:
        return None
    w = px.resample("W-FRI").last().dropna()
    if len(w) <= lookback_weeks:
        return None
    base = w.iloc[-1 - lookback_weeks]
    if base <= 0:
        return None
    return float(w.iloc[-1] / base - 1)


if __name__ == "__main__":
    import sys
    c = sys.argv[1] if len(sys.argv) > 1 else "005930"
    px = fetch_price_history(c, "20230101", "20260630")
    print(f"{c} 가격: {len(px)}거래일  {px.index.min().date()} ~ {px.index.max().date()}  최근종가 {px.iloc[-1]:,.0f}")
    fu = fetch_fundamentals_history(c)
    print(f"{c} 재무 FY: {sorted(fu.keys())}")
    for fy in sorted(fu.keys()):
        d = fu[fy]
        print(f"  FY{fy}: ROE={d.get('roe')} 영업이익률={d.get('op_margin')} 부채비율={d.get('debt_ratio')} EPS={d.get('eps')} BPS={d.get('bps')} 순익={d.get('net_income')}")
