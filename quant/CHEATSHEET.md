# AI Berkshire 퀀트 — 치트시트 (자주 쓰는 명령 요약)

> 이 시스템은 **파이썬 스크립트**입니다. 아래 명령만 알면 됩니다.
> 자동 실행(주말)을 켜면 **매번 손댈 필요 없이** 리포트가 생성됩니다(맨 아래 참조).

## 매주 하는 일
```bash
python quant/run.py rebalance          # 이번 주 매매지시 → reports/quant/리밸런싱-*.md
```
- 보유 현황을 반영하려면 `quant/portfolio.yaml`에 `cash`·`positions` 입력
  (`quant/portfolio.example.yaml` 복사해서 사용). 없으면 1억 전액 현금 가정.

## 미국 성장주 모멘텀 (나스닥100, 별도 계좌)
```bash
python quant/run.py us-rebalance          # 미국 매매지시(신호) → reports/quant/미국리밸런싱-*.md
python quant/run.py us-rebalance --notify # 텔레그램으로도
```
- 나스닥100 중 12-1 모멘텀 상위 **10종목 동일가중**, 순위버퍼 20. 초기 5천만원(환산).
- 보유는 `quant/us_portfolio.yaml`(cash·positions, USD). 실행은 **수동**(미국 브로커, 키움 아님).
- ⚠️ 모멘텀은 섹터 쏠림·급반전 위험. 백테스트 CAGR 35.9%는 생존편향 → forward 보수적.

## 모의투자 (페이퍼 트레이딩 — 실제 돈 없음)
```bash
python quant/run.py paper               # 가상계좌로 리밸런싱 집행 → paper_portfolio.json 누적
python quant/run.py paper --notify      # 결과를 텔레그램으로도
```
- 초기 1억(가상) → 매주 실행하면 손익 누적. 키움 모의 appkey 없이 즉시 안전 검증.
- **키움 실계좌 자동주문**은 `quant/src/broker.py`에 준비돼 있으나 **기본 비활성**(실수 방지).
  키움 정식 모의투자는 별도 '모의 appkey' 발급 필요(실전 appkey는 모의 불가).

## 전략 점검 / 확장
```bash
python quant/run.py rank                # 현재 유니버스 랭킹·후보포트
python quant/run.py backtest            # 2.25년 백테스트
python quant/run.py backtest-long       # 6.5년 다레짐 백테스트(2022 약세장 포함)
python quant/run.py compare             # 팩터 A/B 비교
python quant/run.py screen-market --top 60   # 전체시장(코스피·코스닥) 가치·퀄리티 스크린
```

## 코드 백업 (내 GitHub fork로)
```bash
git add quant reports/quant
git commit -m "설명"
git push                                # → 내 fork(jhsumin-ship-it/ai-berkshire)로 자동 전송
```

## 산출물 위치
- 매매지시: `reports/quant/리밸런싱-YYYYMMDD.md`
- 백테스트: `reports/quant/백테스트-*.md` (+ 자산곡선 PNG)
- 전체시장: `reports/quant/전체시장스크린-*.md`

## 현재 전략 (다레짐 백테스트로 확정)
- **가치 50 : 퀄리티 50** (모멘텀 미반영)
- 퀄리티 = ROE·영업이익률·순이익률·부채비율(역)
- 가치 = 이익수익률(1/PER)·순자산수익률(1/PBR)
- 종목 ≤15%·섹터 ≤30% 상한, 회전율밴드 ±3%p

---

## 🔁 자동 실행 (매주 수요일·토요일 2회, 손 안 대고)
Windows 작업 스케줄러에 **한 번만** 등록하면, 이후 **매주 수·토 자동으로** 리밸런싱 지시가 생성됩니다.
Claude(나)를 부를 필요 없이 PC가 스스로 실행합니다. 매매는 **밴드(±3%p) 이탈 시에만** 발생.

**등록** (PowerShell에서 한 번) — 수·토 15:00 (수요일=마감 전 종가 정렬, 토요일=주말 점검):
```powershell
schtasks /Create /TN "AI-Berkshire-Weekly-Rebalance" /SC WEEKLY /D WED,SAT /ST 15:00 /F `
  /TR "powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\jhsum\code\ai-berkshire\quant\weekly_rebalance.ps1"
```
- 요일 조정: `/D WED,SAT`(콤마로 여러 요일; 월 MON·화 TUE·목 THU·금 FRI·일 SUN), 시간 `/ST`.
- 수·토 시간을 다르게 주고 싶으면 작업을 2개로 분리(이름 다르게).
- **해제**: `schtasks /Delete /TN "AI-Berkshire-Weekly-Rebalance" /F`
- **확인**: `schtasks /Query /TN "AI-Berkshire-Weekly-Rebalance"`
- 로그: `quant/data/weekly.log` · 생성 후 리포트 자동 열림.

> ⚠️ 조건: 그 시각에 **PC가 켜져 있어야** 합니다(로컬 스크립트라 클라우드가 아님).
> 💡 수요일 15:00은 **종가 집행**(마감 단일가) 정렬용. 토요일은 장 마감(금요일 종가) 기준 점검.
> 실주문은 별도 `trade --live`(기본 dry-run) — 토요일은 장이 닫혀 매매지시·모의만.

### 📲 휴대폰으로 받기 (텔레그램, 설정됨)
주간 스크립트는 **매주 (1) 매매지시 `rebalance` (2) 모의투자 `paper`** 를 실행해
**텔레그램(aifm 봇)** 으로 둘 다 발송하고 리포트를 엽니다.
- 텔레그램: `AI FACTORY MANAGER\.env`의 aifm 봇 자동 사용(설정 불필요). ✅ 실측 도착 확인.
- 수동 발송: `python quant/run.py rebalance --notify`
- (Gmail 발송은 사용 안 함. 나중에 원하면 `quant/notify.example.yaml` 참고해 `notify.yaml`에 앱 비밀번호 추가.)
