"""키움증권 REST API 연동 (AI Berkshire 퀀트 — korean_momentum에서 이전).

핵심: TR코드는 body가 아니라 **헤더 api-id**로 전달. 공식: https://openapi.kiwoom.com
자격증명은 env(KIWOOM_APPKEY/SECRETKEY) 우선, 없으면 quant/.kiwoom_rest.json(gitignore).
값은 코드/커밋/출력에 넣지 않는다.

⚠️ 실계좌 자동주문은 절대 임의 실행 금지. 모의투자(force_mock=True) + dry-run 우선.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from dataclasses import dataclass

import requests

_SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "..", ".kiwoom_rest.json")

REAL_BASE = "https://api.kiwoom.com"
MOCK_BASE = "https://mockapi.kiwoom.com"

TR_MAP = {
    "ka10032": ("/api/dostk/rkinfo",       "거래대금 상위"),
    "ka10001": ("/api/dostk/stkbasicinfo", "주식 기본정보"),
    "ka10072": ("/api/dostk/acnt",         "계좌 거래내역"),
    "ka10075": ("/api/dostk/acnt",         "미수잔고"),
    "ka10076": ("/api/dostk/acnt",         "오늘 체결내역"),
    "ka10077": ("/api/dostk/acnt",         "미체결 내역"),
    "ka10085": ("/api/dostk/acnt",         "보유주식 현황"),
    "kt10000": ("/api/dostk/ordr",         "주식 매수"),
    "kt10001": ("/api/dostk/ordr",         "주식 매도"),
    "kt10002": ("/api/dostk/ordr",         "주식 정정"),
    "kt10003": ("/api/dostk/ordr",         "주식 취소"),
}


def save_rest_settings(appkey: str, secretkey: str, mock: bool = False, account: str = "") -> None:
    data = {"appkey": appkey, "secretkey": secretkey, "mock": mock, "account": account}
    with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f)


def load_rest_settings() -> dict:
    env_key = os.environ.get("KIWOOM_APPKEY", "")
    env_secret = os.environ.get("KIWOOM_SECRETKEY", "")
    if env_key and env_secret:
        return {"appkey": env_key, "secretkey": env_secret,
                "mock": os.environ.get("KIWOOM_MOCK", "false").lower() == "true",
                "account": os.environ.get("KIWOOM_ACCOUNT", "")}
    if os.path.exists(_SETTINGS_FILE):
        with open(_SETTINGS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"appkey": "", "secretkey": "", "mock": False, "account": ""}


def is_rest_configured() -> bool:
    s = load_rest_settings()
    return bool(s.get("appkey") and s.get("secretkey"))


@dataclass
class RestOrderResult:
    success: bool
    ticker: str = ""
    action: str = ""
    shares: int = 0
    price: float = 0.0
    order_no: str = ""
    message: str = ""


class KiwoomREST:
    """키움 REST 클라이언트. force_mock=True면 설정과 무관하게 모의(mockapi) 강제."""

    def __init__(self, force_mock: bool | None = None) -> None:
        cfg = load_rest_settings()
        self._appkey = cfg.get("appkey", "")
        self._secret = cfg.get("secretkey", "")
        self._mock = cfg.get("mock", False) if force_mock is None else bool(force_mock)
        self._account = cfg.get("account", "")
        self._base = MOCK_BASE if self._mock else REAL_BASE
        self._token: str | None = None
        self._token_expires: datetime = datetime.min

    @property
    def mock(self) -> bool:
        return self._mock

    def connect(self) -> bool:
        if self._token and datetime.now() < self._token_expires:
            return True
        try:
            resp = requests.post(
                f"{self._base}/oauth2/token",
                json={"grant_type": "client_credentials",
                      "appkey": self._appkey, "secretkey": self._secret},
                headers={"Content-Type": "application/json;charset=UTF-8"}, timeout=10)
            data = resp.json()
            if resp.status_code == 200 and "token" in data:
                self._token = data["token"]
                try:
                    self._token_expires = datetime.strptime(data.get("expires_dt", ""), "%Y%m%d%H%M%S")
                except Exception:  # noqa: BLE001
                    self._token_expires = datetime.now() + timedelta(hours=23)
                print(f"[KiwoomREST] {'모의투자' if self._mock else '실계좌'} 연결 성공")
                return True
            print(f"[KiwoomREST] 토큰 발급 실패: {data}")
            return False
        except Exception as e:  # noqa: BLE001
            print(f"[KiwoomREST] 연결 오류: {e}")
            return False

    @property
    def is_connected(self) -> bool:
        return bool(self._token and datetime.now() < self._token_expires)

    def _call(self, tr_code: str, body: dict, cont_yn: str = "N", next_key: str = "") -> dict:
        if not self.is_connected and not self.connect():
            return {"return_code": -1, "return_msg": "연결 안됨"}
        uri = TR_MAP.get(tr_code, (f"/api/dostk/{tr_code.lower()}", ""))[0]
        hdrs = {"Content-Type": "application/json;charset=UTF-8",
                "authorization": f"Bearer {self._token}",
                "cont-yn": cont_yn, "next-key": next_key, "api-id": tr_code}
        try:
            resp = requests.post(f"{self._base}{uri}", headers=hdrs, json=body, timeout=10)
            return resp.json()
        except Exception as e:  # noqa: BLE001
            return {"return_code": -1, "return_msg": str(e)}

    def get_stock_info(self, ticker: str) -> dict:
        data = self._call("ka10001", {"stk_cd": ticker})
        return data if data.get("return_code") == 0 else {}

    def get_holdings(self, account: str = "") -> list[dict]:
        acnt = account or self._account
        data = self._call("ka10085", {"acnt_no": acnt, "stex_tp": "1"})
        if data.get("return_code") != 0:
            return []
        out = []
        for r in data.get("acnt_prft_rt", []):
            cur = abs(int(r.get("cur_prc", "0").replace("+", "").replace("-", "")))
            pur = abs(int(r.get("pur_pric", "0").replace("+", "").replace("-", "")))
            qty = int(r.get("rmnd_qty", "0"))
            out.append({"ticker": r.get("stk_cd", ""), "name": r.get("stk_nm", ""),
                        "cur_price": cur, "buy_price": pur, "quantity": qty,
                        "eval_amount": cur * qty,
                        "pnl_pct": round((cur / pur - 1) * 100, 2) if pur > 0 else 0.0})
        return out

    def buy(self, ticker: str, shares: int, price: float = 0, account: str = "") -> RestOrderResult:
        return self._order("buy", ticker, shares, price, account or self._account)

    def sell(self, ticker: str, shares: int, price: float = 0, account: str = "") -> RestOrderResult:
        return self._order("sell", ticker, shares, price, account or self._account)

    def _order(self, side: str, ticker: str, shares: int, price: float, account: str) -> RestOrderResult:
        tr = "kt10000" if side == "buy" else "kt10001"
        body = {"acnt_no": account, "stk_cd": ticker, "ord_qty": str(shares),
                "ord_prc": "0" if price == 0 else str(int(price)),
                "ord_dvsn": "03" if price == 0 else "00",  # 03=시장가 00=지정가
                "dmst_stex_tp": "KRX", "trde_tp": "3"}
        data = self._call(tr, body)
        if data.get("return_code") == 0:
            return RestOrderResult(success=True, ticker=ticker, action=side, shares=shares,
                                   price=price, order_no=str(data.get("ord_no", "")),
                                   message=f"{'매수' if side == 'buy' else '매도'} 성공")
        return RestOrderResult(success=False, ticker=ticker, action=side,
                               message=data.get("return_msg", ""))


_rest_instance: KiwoomREST | None = None


def get_kiwoom_rest(force_mock: bool | None = None) -> KiwoomREST:
    global _rest_instance
    if _rest_instance is None or force_mock is not None:
        _rest_instance = KiwoomREST(force_mock=force_mock)
    return _rest_instance
