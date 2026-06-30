# AI Berkshire — 주간 리밸런싱 가치퀀트

8개 섹터(AI·반도체소부장·전력·ESS2차전지·로봇·조선·바이오·우주항공방산)의 한국주식을
**가치·퀄리티 팩터로 점수화 → 섹터별 선별 → 점수가중**하는 주간 리밸런싱 시스템.
4대 거장(버핏·멍거·돤융핑·리루) 프레임을 정량 팩터로 번역한다.

## 빠른 시작
```bash
python quant/run.py update-data      # 네이버 유니버스 전종목 수집(+모멘텀) → data/ 캐시
python quant/run.py rank             # 점수화·랭킹·후보포트 → reports/quant/주간랭킹-*.md
python quant/run.py backtest --fetch # 주간 리밸런싱 백테스트(2.25년) → 백테스트-*.md
python quant/run.py compare          # 팩터 변형 A/B 비교 → 백테스트-팩터비교-*.md
python quant/run.py rebalance        # 주간 매매지시(보유 대비) → 리밸런싱-*.md
python quant/run.py backtest-long    # DART 다레짐 6.5년 백테스트 → 백테스트-장기다레짐-*.md
python quant/run.py screen-market --top 60   # 전체시장 가치·퀄리티 스크린 → 전체시장스크린-*.md
for t in factors backtest portfolio; do python quant/tests/test_$t.py; done
```

## 주간 자동화 (Windows 작업 스케줄러)
래퍼 `quant/weekly_rebalance.ps1` 준비됨. 아래 한 줄로 **매주 월 08:00 자동 실행** 등록:
```powershell
schtasks /Create /TN "AI-Berkshire-Weekly-Rebalance" /SC WEEKLY /D MON /ST 08:00 /F `
  /TR "powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\jhsum\code\ai-berkshire\quant\weekly_rebalance.ps1"
```
해제: `schtasks /Delete /TN "AI-Berkshire-Weekly-Rebalance" /F` · 로그: `quant/data/weekly.log`

보유현황은 `quant/portfolio.yaml`(`portfolio.example.yaml` 복사)에 `cash`·`positions`로 입력.
없으면 `default_cash` 전액 현금 가정(첫 리밸런싱 = 전량 신규매수).

## 구조
```
quant/
  config.yaml        # 유니버스(55종)·팩터가중·스크린·선별 규칙
  run.py             # CLI (update-data / rank)
  src/
    naver.py         # 네이버 모바일 API 수집 + 내부정합 검증
    factors.py       # 가치·퀄리티 z-score 합성
    rank_select.py   # 스크린·랭킹·섹터선별·점수가중 비중
    report.py        # 마크다운 리포트 렌더
  tests/test_factors.py
  data/              # 시세·재무 캐시 (gitignore)
```

## 팩터 (가치 50 : 퀄리티 50 — 다레짐 백테스트로 확정)
| 그룹 | 팩터 |
|---|---|
| 퀄리티(버핏·돤융핑) | ROE, 영업이익률, 순이익률, 부채비율(역) |
| 가치(버핏·돤) | 이익수익률(1/PER), 순자산수익률(1/PBR) |

종합점수 `S = 0.5·z_퀄 + 0.5·z_가치` (유니버스 내 z-score).
컨센 상승여력·배당은 표시만 하고 점수 미반영(과거 검증 불가·노이즈). `config.yaml`로 조정.

**왜 가치·퀄리티?** Phase 2.5(2.25년)에선 모멘텀이 좋아 보였으나, Phase 2.1
**6.5년 다레짐(2020~26, 코로나·2022약세장·2023반도체적자 포함)** 검증에서 반전 —
가치·퀄리티 틸트가 수익·Sharpe(1.81)·하락방어(2022 −7% vs 모멘텀블렌드 −20%) 모두
우월. 모멘텀 우위는 단기 불장 과적합이었음. `momentum_factors`는 비워 점수 미반영.

## 스크린(통과 조건)
- 최근 회계연도 당기순이익 > 0 (적자 제외)
- EPS > 0 (PER 산출 가능)
- 최근 거래대금 ≥ 30억원 (유동성)
- 내부정합 통과 (PER ≈ 주가/EPS — 피드 10배 오류 등 자동 탐지)

## 데이터
네이버페이 증권 모바일 JSON API(시세·밸류·컨센서스·연간재무). WebFetch는 차단되나
직접 HTTP는 가능. 재무 정본 교차검증(DART)·시세 3소스 교차검증은 Phase 2에서 강화.

**교훈**: SK하이닉스가 3소스(Yahoo·Naver·Google) 동일하게 ~2,730,000원/시총 1,938조로
일치 → 내부정합(주가=EPS×PER) 검증을 코드에 내장해 피드 오류를 자동으로 잡는다.

## 로드맵
- **Phase 1 (완료)**: 유니버스·데이터 파이프라인·팩터 점수화 → 현재 랭킹
- **Phase 2 (완료)**: 백테스트 엔진(point-in-time, KR 비용모델) + 자산곡선
- **Phase 2.5 (완료)**: 팩터 A/B 비교 → 퀄50·가25·모25 블렌드 채택
- **Phase 3 (완료)**: 주간 리밸런싱 매매지시(회전율 밴드 ±3%p) 생성
- **Phase 2.1 (완료)**: DART 다년 재무로 6.5년 다레짐 백테스트 → 가치·퀄리티 확정
- **Phase 4 (완료)**: 주간 자동화 래퍼 + 작업 스케줄러 등록(위 참조)
- **Phase 5 (완료)**: 전체시장(KOSPI·KOSDAQ) 자동 스크린(`screen-market`)
- 향후(선택): 섹터중립 전체시장 포트, 실거래 연동, 알림

## 면책
가치투자 방법론 기반 연구 도구이며 **투자권유가 아님**. 실투자는 2개 이상 독립소스
재확인 후 본인 책임. 백테스트 ≠ 실전(생존편향·룩어헤드 주의).
