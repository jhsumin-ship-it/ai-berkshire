#!/usr/bin/env python3
"""DART 전자공시 다년 재무 수집 — 장기·다레짐 백테스트용 (AI Berkshire Phase 2.1).

네이버 연간재무는 4개년뿐이라 2020~2022(약세장 포함) 검증 불가 → DART 정본 사용.
OpenDART `fnlttSinglAcntAll`는 한 호출에 3개년(당기·전기·전전기) 반환 →
FY2025·2022·2019 리포트 3회로 2017~2025 전부 커버.

API 키는 env DART_API_KEY 우선, 없으면 ~/.claude.json mcpServers.dart 에서 읽음(본인 키).
키는 절대 출력·커밋하지 않는다.
"""

from __future__ import annotations

import io
import json
import os
import time
import zipfile

import requests
import xml.etree.ElementTree as ET

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
_BASE = "https://opendart.fss.or.kr/api"


def api_key() -> str:
    k = os.environ.get("DART_API_KEY")
    if k:
        return k
    cfgp = os.path.join(os.path.expanduser("~"), ".claude.json")
    try:
        with open(cfgp, encoding="utf-8") as f:
            cfg = json.load(f)
        return cfg["mcpServers"]["dart"]["env"]["DART_API_KEY"]
    except Exception as e:  # noqa: BLE001
        raise RuntimeError("DART_API_KEY를 env 또는 ~/.claude.json에서 찾지 못함") from e


def corp_code_map() -> dict:
    """{6자리 종목코드: 8자리 corp_code}. corpCode.xml(zip) 다운로드 후 캐시."""
    cache = os.path.join(DATA_DIR, "dart_corpmap.json")
    if os.path.exists(cache):
        with open(cache, encoding="utf-8") as f:
            return json.load(f)
    os.makedirs(DATA_DIR, exist_ok=True)
    r = requests.get(f"{_BASE}/corpCode.xml", params={"crtfc_key": api_key()}, timeout=30)
    r.raise_for_status()
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    xml = zf.read(zf.namelist()[0])
    root = ET.fromstring(xml)
    m = {}
    for it in root.iter("list"):
        sc = (it.findtext("stock_code") or "").strip()
        cc = (it.findtext("corp_code") or "").strip()
        if sc and sc != " " and cc:
            m[sc.zfill(6)] = cc
    with open(cache, "w", encoding="utf-8") as f:
        json.dump(m, f)
    return m


def _num(s):
    if s in (None, "", "-"):
        return None
    try:
        return float(str(s).replace(",", ""))
    except ValueError:
        return None


# 계정 식별: account_id 우선, 없으면 account_nm
_ACC = {
    "revenue": ("ifrs-full_Revenue", ("매출액", "수익(매출액)", "영업수익")),
    "op_income": ("dart_OperatingIncomeLoss", ("영업이익", "영업이익(손실)")),
    "net_income": ("ifrs-full_ProfitLoss", ("당기순이익", "당기순이익(손실)")),
    "equity": ("ifrs-full_Equity", ("자본총계",)),
    "liabilities": ("ifrs-full_Liabilities", ("부채총계",)),
}


def _pick(rows, key):
    aid, names = _ACC[key]
    for r in rows:
        if r.get("account_id") == aid:
            return r
    for r in rows:
        if (r.get("account_nm") or "").strip() in names:
            return r
    return None


def _fetch_year(corp_code, year, fs_div, key):
    p = {"crtfc_key": key, "corp_code": corp_code, "bsns_year": str(year),
         "reprt_code": "11011", "fs_div": fs_div}
    try:
        j = requests.get(f"{_BASE}/fnlttSinglAcntAll.json", params=p, timeout=20).json()
    except Exception:  # noqa: BLE001
        return {}
    if j.get("status") != "000":
        return {}
    rows = j.get("list", [])
    out = {}  # fy_int(YYYYMM) -> {raw accounts}
    cols = [(year, "thstrm_amount"), (year - 1, "frmtrm_amount"), (year - 2, "bfefrmtrm_amount")]
    for fld, key_name in _ACC.items():
        r = _pick(rows, fld)
        if not r:
            continue
        for y, col in cols:
            out.setdefault(y, {})[fld] = _num(r.get(col))
    return out


def fetch_history(corp_code: str, report_years=(2025, 2022, 2019)) -> dict:
    """{fy_int(YYYYMM) -> 비율dict}. CFS 우선, 비면 OFS 폴백."""
    key = api_key()
    merged = {}  # year -> accounts
    for ry in report_years:
        d = _fetch_year(corp_code, ry, "CFS", key)
        if not d:
            d = _fetch_year(corp_code, ry, "OFS", key)
        for y, acc in d.items():
            if y not in merged:
                merged[y] = acc
        time.sleep(0.1)

    out = {}
    for y, a in merged.items():
        rev, opi, ni = a.get("revenue"), a.get("op_income"), a.get("net_income")
        eq, li = a.get("equity"), a.get("liabilities")
        rec = {
            "revenue": rev, "op_income": opi, "net_income": ni,
            "equity": eq, "liabilities": li,
            "op_margin": (opi / rev * 100) if (rev and opi is not None) else None,
            "net_margin": (ni / rev * 100) if (rev and ni is not None) else None,
            "roe": (ni / eq * 100) if (eq and ni is not None and eq != 0) else None,
            "debt_ratio": (li / eq * 100) if (eq and li is not None and eq != 0) else None,
        }
        out[int(f"{y}12")] = rec  # 12월 결산 가정 (대다수 KR)
    return out


if __name__ == "__main__":
    import sys
    code = sys.argv[1] if len(sys.argv) > 1 else "000660"
    m = corp_code_map()
    cc = m.get(code)
    print(f"종목 {code} → corp_code {cc} (총 {len(m)}개 매핑)")
    h = fetch_history(cc)
    for fy in sorted(h):
        d = h[fy]
        print(f"  FY{fy}: 매출={d['revenue']} 영업이익={d['op_income']} 순익={d['net_income']} "
              f"ROE={d['roe'] and round(d['roe'],1)} 영업이익률={d['op_margin'] and round(d['op_margin'],1)} "
              f"부채비율={d['debt_ratio'] and round(d['debt_ratio'],1)}")
