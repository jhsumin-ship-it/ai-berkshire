#!/usr/bin/env python3
"""주간 리밸런싱 — 보유포지션 대비 매매리스트 생성 (AI Berkshire 퀀트 Phase 3).

목표비중(블렌드 점수가중) vs 현재비중(보유주식×현재가)을 비교해,
회전율 밴드(±band) 밖 종목만 거래하는 매매지시를 만든다.
"""

from __future__ import annotations

import os

import pandas as pd
import yaml


def load_portfolio(path: str, default_cash: float) -> dict:
    """portfolio.yaml → {cash, positions:{code:shares}}. 없으면 현금만(첫 리밸런싱)."""
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            d = yaml.safe_load(f) or {}
        return {
            "cash": float(d.get("cash", default_cash)),
            "positions": {str(k): float(v) for k, v in (d.get("positions") or {}).items()},
        }
    return {"cash": float(default_cash), "positions": {}}


def build_trades(picks: pd.DataFrame, port: dict, prices: dict, sectors: dict,
                 names: dict, band: float, cost_cfg: dict) -> dict:
    """매매리스트 + 요약 산출.

    picks: target 종목/비중(weight %) DataFrame (code, weight, ...).
    port:  {cash, positions}.  prices: {code: 현재가}.
    """
    positions = port["positions"]
    cash = port["cash"]

    # 총자산
    holdings_val = sum(sh * prices.get(c, 0) for c, sh in positions.items())
    total = cash + holdings_val
    if total <= 0:
        total = 1.0

    target_w = {r["code"]: r["weight"] / 100.0 for _, r in picks.iterrows()}
    cur_w = {c: (sh * prices.get(c, 0)) / total for c, sh in positions.items()}

    universe = sorted(set(target_w) | set(cur_w), key=lambda c: -target_w.get(c, 0))
    trades = []
    for c in universe:
        tw = target_w.get(c, 0.0)
        cw = cur_w.get(c, 0.0)
        px = prices.get(c, 0)
        drift = tw - cw
        if cw == 0 and tw > 0:
            action = "신규매수"
        elif tw == 0 and cw > 0:
            action = "전량매도"
        elif abs(drift) <= band:
            action = "유지(밴드내)"
        elif drift > 0:
            action = "추가매수"
        else:
            action = "일부매도"

        # 밴드내 유지면 거래 0, 그 외엔 목표까지 거래
        trade_val = 0.0 if action == "유지(밴드내)" else drift * total
        shares = int(trade_val / px) if px else 0  # 0방향 절사 → 매수 자본초과 방지
        trades.append({
            "code": c, "name": names.get(c, c), "sector": sectors.get(c, ""),
            "action": action, "cur_w": cw, "tgt_w": tw, "drift": drift,
            "price": px, "trade_val": shares * px, "shares": shares,
        })

    df = pd.DataFrame(trades)
    traded = df[df["shares"] != 0]
    buys = traded[traded["shares"] > 0]["trade_val"].sum()
    sells = -traded[traded["shares"] < 0]["trade_val"].sum()
    turnover = (buys + sells) / total
    cost = (buys * (cost_cfg["commission"] + cost_cfg["slippage"])
            + sells * (cost_cfg["commission"] + cost_cfg["slippage"] + cost_cfg["sell_tax"]))
    new_cash = cash - buys + sells
    summary = {
        "total": total, "cash": cash, "holdings_val": holdings_val,
        "n_trades": int((df["shares"] != 0).sum()), "buys": buys, "sells": sells,
        "turnover": turnover, "est_cost": cost, "new_cash": new_cash,
    }
    return {"trades": df, "summary": summary}
