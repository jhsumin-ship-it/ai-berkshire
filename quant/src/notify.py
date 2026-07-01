#!/usr/bin/env python3
"""알림 발송 — 텔레그램(aifm 봇) + Gmail (AI Berkshire 퀀트 Phase 4 배송).

자격증명은 코드/커밋에 넣지 않고 런타임에 아래 우선순위로 읽는다(값 미출력):
  텔레그램: quant/notify.yaml → 환경변수 → AIFM .env(TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID)
  Gmail:    quant/notify.yaml → 환경변수 (GMAIL_USER/GMAIL_APP_PASSWORD/GMAIL_TO)
채널별 자격증명이 없으면 조용히 건너뛴다.
"""

from __future__ import annotations

import os
import smtplib
import ssl
from email.mime.text import MIMEText

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_NOTIFY_YAML = os.path.join(ROOT, "notify.yaml")
# aifm 봇 자격증명이 있는 AI FACTORY MANAGER 프로젝트 .env (기본 경로)
_AIFM_ENV_DEFAULT = r"C:\Users\jhsum\code\AI FACTORY MANAGER\.env"


def _load_yaml() -> dict:
    if not os.path.exists(_NOTIFY_YAML):
        return {}
    try:
        import yaml
        with open(_NOTIFY_YAML, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:  # noqa: BLE001
        return {}


def _parse_env_file(path: str) -> dict:
    out = {}
    if not path or not os.path.exists(path):
        return out
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    except Exception:  # noqa: BLE001
        pass
    return out


def _telegram_creds(cfg: dict):
    y = _load_yaml().get("telegram", {}) or {}
    token = y.get("bot_token") or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = y.get("chat_id") or os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        env_path = y.get("env_file") or (cfg.get("notify", {}) or {}).get("telegram_env_file") or _AIFM_ENV_DEFAULT
        e = _parse_env_file(env_path)
        token = token or e.get("TELEGRAM_BOT_TOKEN")
        chat = chat or e.get("TELEGRAM_CHAT_ID") or (e.get("TELEGRAM_CHAT_IDS", "").split(",")[0].strip() or None)
    return token, str(chat) if chat else None


def _gmail_creds():
    y = _load_yaml().get("gmail", {}) or {}
    user = y.get("user") or os.environ.get("GMAIL_USER")
    pw = y.get("app_password") or os.environ.get("GMAIL_APP_PASSWORD")
    to = y.get("to") or os.environ.get("GMAIL_TO") or user
    return user, pw, to


def send_telegram(text: str, cfg: dict) -> str:
    token, chat = _telegram_creds(cfg)
    if not token or not chat:
        return "skip(자격증명 없음)"
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": text, "parse_mode": "HTML",
                  "disable_web_page_preview": True},
            timeout=15)
        return "ok" if r.ok and r.json().get("ok") else f"fail({r.status_code}:{r.text[:80]})"
    except Exception as e:  # noqa: BLE001
        return f"fail({e})"


def send_gmail(subject: str, body: str) -> str:
    user, pw, to = _gmail_creds()
    if not user or not pw:
        return "skip(자격증명 없음)"
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = user
        msg["To"] = to
        ctx = ssl.create_default_context()
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as s:
            s.starttls(context=ctx)
            s.login(user, pw)
            s.sendmail(user, [x.strip() for x in to.split(",")], msg.as_string())
        return "ok"
    except Exception as e:  # noqa: BLE001
        return f"fail({e})"


def notify(subject: str, text: str, cfg: dict) -> dict:
    """텔레그램 발송(+Gmail은 자격증명이 설정된 경우에만)."""
    out = {"telegram": send_telegram(f"<b>{subject}</b>\n{text}", cfg)}
    user, pw, _ = _gmail_creds()
    if user and pw:  # Gmail은 앱 비밀번호가 설정됐을 때만 시도
        out["gmail"] = send_gmail(subject, text)
    return out


if __name__ == "__main__":
    # 발송 테스트: python quant/src/notify.py "테스트 메시지"
    import sys
    txt = sys.argv[1] if len(sys.argv) > 1 else "AI Berkshire 알림 테스트"
    print(notify("[테스트] AI Berkshire 퀀트", txt, {}))
