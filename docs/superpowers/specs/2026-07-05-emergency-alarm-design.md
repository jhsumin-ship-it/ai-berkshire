# 긴급 급변동 알람 시스템 — 설계 스펙

> 작성 2026-07-05 · 상태: 승인됨 · 대상: `quant/` 패키지

## 목적
외부충격에 의한 지수·VIX·보유종목 급변동을 감지해 **긴급 알람(자동)**을 텔레그램 발송. 리밸런싱은 자동 안 함 — 알람이 사용자에게 즉석 리밸런싱 트리거를 안내(옵션 C).

## 감시 대상 & 임계값 (중간 민감도, config 조정 가능)
| 대상 | 티커 | 임계값(일간) | 데이터 |
|---|---|---|---|
| KOSPI | ^KS11 | ±5% | yfinance |
| KOSDAQ | ^KQ11 | ±5% | yfinance |
| S&P500 | ^GSPC | ±5% | yfinance |
| 나스닥100 | QQQ | ±5% | yfinance |
| VIX | ^VIX | 절대 35 이상 or 일간 +30% | yfinance |
| 보유종목(KR) | portfolio.yaml codes | ±10% | naver.py change_pct |
| 보유종목(US) | us_portfolio.yaml tickers | ±10% | yfinance |

## 동작
1. 각 대상 전일 대비 등락 계산 → 임계 초과분 수집
2. 초과분 있으면 **텔레그램 긴급 알람**(무엇이 몇% + VIX 수준). 없으면 조용히 종료(알람 피로 방지)
3. 리밸런싱 자동 안 함 — 알람 말미에 "긴급 리밸런싱 원하면 트리거" 안내

## 구조 (기존 패턴 미러링)
- `quant/emergency_config.yaml`: 임계값(emergency) + 감시지수(indices)·vix_ticker
- `quant/src/emergency.py`:
  - `evaluate(observations, cfg)` — **순수로직**: 관측치→트리거 리스트(테스트 대상)
  - `fetch_index_moves(cfg)` / `fetch_holding_moves(kr_codes, us_tickers)` — 네트워크
  - `check_shocks(cfg, kr_codes, us_tickers)` — 오케스트레이션
  - `format_alarm(triggered)` — 텔레그램 메시지
- `quant/run.py`: `emergency-check` 명령(감지→알람, --notify)
- `quant/tests/test_emergency.py`: evaluate 임계판정 단위테스트(합성, 네트워크 無)
- 스케줄: `emergency_check.ps1` + schtasks 2회/일(한국 마감후 ~15:40, 미국 마감후 아침 ~07:00)

## 관측치 구조 (evaluate 입력)
```
observations = {
  "indices": {"KOSPI": -6.2, "S&P500": +1.1, ...},   # 일간 %
  "vix": {"level": 38.0, "change_pct": +45.0},
  "holdings": {"삼성전자": -12.3, "AMD": +3.0, ...},   # 일간 %
}
```
`evaluate`는 emergency 임계와 비교해 트리거 리스트 반환:
`[{kind, name, value, threshold, direction}]`

## 비적용(YAGNI)
장중 실시간(마감후 1회), 자동 리밸런싱(옵션 C), 텔레그램 외 채널, 이력 저장(무상태).

## 리스크 고지
알람은 인지용, 매매지시 아님. 급락 반응매매는 대개 손해 → 관망 기본. yfinance 지연은 마감후 체크라 무관.
