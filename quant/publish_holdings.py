#!/usr/bin/env python3
"""보유(선정) 종목목록을 quant/holdings.json으로 발행.

용도: 모닝뉴스 텔레그램(Railway)이 raw GitHub로 이 파일을 읽어
'퀀트 선정종목 종가·등락률' 섹션을 만든다. weekly_rebalance.ps1이
리밸런싱 후 이 스크립트를 호출하고, 변동이 있으면 git push로 fork에 반영한다.

- 보유코드: paper_portfolio.json 의 positions
- 한글명:   config.yaml 의 universe(code→name)
- 코드 목록이 이전 holdings.json 과 동일하면 파일을 건드리지 않는다
  (asof 날짜만 바뀌어 매주 불필요한 커밋이 생기는 것을 방지).

종료코드: 변동 있어 새로 씀=0 / 변동 없음=0 / 입력 없음=1
"""
from __future__ import annotations

import datetime
import json
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = os.path.join(ROOT, "paper_portfolio.json")
CFG = os.path.join(ROOT, "config.yaml")
OUT = os.path.join(ROOT, "holdings.json")


def _names() -> dict:
    """config.yaml universe 에서 code→한글명."""
    try:
        import yaml
        with open(CFG, encoding="utf-8") as f:
            d = yaml.safe_load(f) or {}
        return {str(e["code"]).zfill(6): e.get("name")
                for e in (d.get("universe") or []) if e.get("code")}
    except Exception as e:  # noqa: BLE001
        print(f"[publish] config 이름맵 실패(무시): {e}")
        return {}


def _held_codes() -> list[str]:
    with open(PORT, encoding="utf-8") as f:
        port = json.load(f)
    return [str(c).zfill(6) for c in (port.get("positions") or {})]


def main() -> int:
    try:
        codes = _held_codes()
    except Exception as e:  # noqa: BLE001
        print(f"[publish] paper_portfolio 읽기 실패: {e}")
        return 1
    if not codes:
        print("[publish] 보유 종목 없음 — 발행 생략")
        return 1

    # 코드 목록이 그대로면 파일 유지(커밋 노이즈 방지)
    if os.path.exists(OUT):
        try:
            with open(OUT, encoding="utf-8") as f:
                prev = json.load(f)
            prev_codes = [str(h.get("code")).zfill(6) for h in prev.get("holdings", [])]
            if prev_codes == codes:
                print(f"[publish] 보유목록 변동 없음({len(codes)}종) — 파일 유지")
                return 0
        except Exception:  # noqa: BLE001
            pass

    names = _names()
    holdings = [{"code": c, "name": names.get(c)} for c in codes]
    out = {
        "asof": datetime.datetime.now().strftime("%Y%m%d"),
        "holdings": holdings,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"[publish] holdings.json 갱신: {len(holdings)}종 (asof {out['asof']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
