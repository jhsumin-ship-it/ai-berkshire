# AI Berkshire 퀀트 — 치트시트 (자주 쓰는 명령 요약)

> 이 시스템은 **파이썬 스크립트**입니다. 아래 명령만 알면 됩니다.
> 자동 실행(주말)을 켜면 **매번 손댈 필요 없이** 리포트가 생성됩니다(맨 아래 참조).

## 매주 하는 일
```bash
python quant/run.py rebalance          # 이번 주 매매지시 → reports/quant/리밸런싱-*.md
```
- 보유 현황을 반영하려면 `quant/portfolio.yaml`에 `cash`·`positions` 입력
  (`quant/portfolio.example.yaml` 복사해서 사용). 없으면 1억 전액 현금 가정.

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

## 🔁 자동 실행 (매주 토요일, 손 안 대고)
Windows 작업 스케줄러에 **한 번만** 등록하면, 이후 **매주 자동으로** 매매지시가 생성됩니다.
Claude(나)를 부를 필요 없이 PC가 스스로 실행합니다.

**등록** (PowerShell에서 한 번):
```powershell
schtasks /Create /TN "AI-Berkshire-Weekly-Rebalance" /SC WEEKLY /D SAT /ST 09:00 /F `
  /TR "powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\jhsum\code\ai-berkshire\quant\weekly_rebalance.ps1"
```
- 일요일 원하면 `/D SAT` → `/D SUN`, 시간은 `/ST 09:00` 조정.
- **해제**: `schtasks /Delete /TN "AI-Berkshire-Weekly-Rebalance" /F`
- **확인**: `schtasks /Query /TN "AI-Berkshire-Weekly-Rebalance"`
- 로그: `quant/data/weekly.log` · 생성 후 리포트 자동 열림.

> ⚠️ 조건: 그 시각에 **PC가 켜져 있어야** 합니다(로컬 스크립트라 클라우드가 아님).

### 📲 휴대폰으로 받기 (텔레그램, 설정됨)
주간 스크립트는 `rebalance --notify`로 실행되어 **텔레그램(aifm 봇)** 으로 매매지시를 발송합니다.
- 텔레그램: `AI FACTORY MANAGER\.env`의 aifm 봇 자동 사용(설정 불필요). ✅ 실측 도착 확인.
- 수동 발송: `python quant/run.py rebalance --notify`
- (Gmail 발송은 사용 안 함. 나중에 원하면 `quant/notify.example.yaml` 참고해 `notify.yaml`에 앱 비밀번호 추가.)
