"""페이퍼 트레이딩(로컬 모의투자) — 가상 계좌로 리밸런싱 집행 시뮬레이션.

실제 주문/실제 돈 없음. 키움 모의투자 appkey가 없어도 즉시 안전하게 전략을 검증한다.
상태는 quant/paper_portfolio.json(gitignore)에 누적: {cash, positions, history}.
집행은 현재가 체결 가정 + 설정 비용(수수료·슬리피지·매도세) 반영.
"""
from __future__ import annotations

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_FILE = os.path.join(ROOT, "paper_portfolio.json")


def load_state(default_cash: float) -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            s = json.load(f)
        s.setdefault("cash", default_cash)
        s.setdefault("positions", {})
        s.setdefault("history", [])
        s.setdefault("initial", s.get("initial", default_cash))
        return s
    return {"cash": float(default_cash), "positions": {}, "history": [],
            "initial": float(default_cash)}


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def portfolio_value(state: dict, prices: dict) -> dict:
    holdings = 0.0
    for c, sh in state["positions"].items():
        holdings += sh * prices.get(c, 0)
    total = state["cash"] + holdings
    pnl = total - state["initial"]
    return {"cash": state["cash"], "holdings": holdings, "total": total,
            "pnl": pnl, "pnl_pct": (pnl / state["initial"] * 100) if state["initial"] else 0.0}


def apply_trades(state: dict, trades_df, prices: dict, cost_cfg: dict, asof: str) -> dict:
    """매매지시 DataFrame을 가상계좌에 체결(현재가). 비용 차감. 상태 갱신 후 요약 반환."""
    executed, buy_val, sell_val, cost = [], 0.0, 0.0, 0.0
    c_rate = cost_cfg["commission"] + cost_cfg["slippage"]
    for _, r in trades_df.iterrows():
        sh = int(r["shares"])
        if sh == 0:
            continue
        code = r["code"]
        px = prices.get(code, r.get("price", 0)) or 0
        val = sh * px
        cur = state["positions"].get(code, 0)
        state["positions"][code] = cur + sh
        if state["positions"][code] <= 0:
            state["positions"].pop(code, None)
        if sh > 0:  # 매수
            fee = val * c_rate
            state["cash"] -= (val + fee)
            buy_val += val
        else:       # 매도
            fee = (-val) * (c_rate + cost_cfg["sell_tax"])
            state["cash"] += (-val) - fee
            sell_val += -val
        cost += fee
        executed.append({"action": r["action"], "name": r["name"], "code": code,
                         "shares": sh, "price": px})
    val_now = portfolio_value(state, prices)
    rec = {"asof": asof, "trades": len(executed), "buy": buy_val, "sell": sell_val,
           "cost": round(cost), "total_after": round(val_now["total"]),
           "pnl_pct": round(val_now["pnl_pct"], 2)}
    state["history"].append(rec)
    return {"executed": executed, "cost": cost, "buy": buy_val, "sell": sell_val, "value": val_now}
