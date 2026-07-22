# AI Berkshire 긴급 급변동 알람 래퍼
# 작업 스케줄러에서 각 시장 마감 후 호출(하루 2회): 한국 마감후 ~15:40, 미국 마감후 아침 ~07:00.
# 임계(지수±5%·VIX35·보유±10%) 초과 시에만 텔레그램 긴급 알람. 리밸런싱은 자동 안 함.
#
# 2026-07-17 추가: 주5회 도는 이 작업에 주간 리밸런싱 지연감지(healthcheck)를 얹었다.
#   주간 래퍼가 강제종료되면 자기 자신은 알림을 못 보낸다(7/15 사례) → 외부에서 감시.
$ErrorActionPreference = "Continue"
# 한글 깨짐 방지 (2026-07-22, weekly_rebalance.ps1 과 동일 처방): PS 5.1 이 UTF-8
# 파이썬 출력을 CP949 로 잘못 해독 → 로그·텔레그램 한글 깨짐. 콘솔 UTF-8 강제 + BOM 재저장.
try {
  [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
  $OutputEncoding = [System.Text.Encoding]::UTF8
} catch { }
$repo = "C:\Users\jhsum\code\ai-berkshire"
Set-Location $repo
$log = Join-Path $repo "quant\data\emergency.log"
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null

$env:PYTHONUNBUFFERED = "1"
$env:PYTHONIOENCODING = "utf-8"

# PATH의 python.exe는 0바이트 Store 앱 별칭이라 비대화형에서 깨질 수 있다 → 실체 경로 우선.
function Resolve-Python {
  $c = Get-ChildItem "$env:LOCALAPPDATA\Python\pythoncore-*\python.exe" -ErrorAction SilentlyContinue |
       Where-Object { $_.Length -gt 0 } | Sort-Object FullName -Descending | Select-Object -First 1
  if ($c) { return $c.FullName }
  $g = Get-Command python -ErrorAction SilentlyContinue
  if ($g -and (Get-Item $g.Source).Length -gt 0) { return $g.Source }
  return "python"
}
$PY = Resolve-Python

"`n===== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') 급변동 점검 =====" | Tee-Object -FilePath $log -Append

& $PY quant/run.py emergency-check --notify 2>&1 | Tee-Object -FilePath $log -Append
$rc = $LASTEXITCODE
if ($rc -ne 0) {
  "!!! 급변동 점검 실패 (exit=$rc)" | Tee-Object -FilePath $log -Append
  & $PY quant/run.py alert --subject "[AI Berkshire] 🚨 긴급알람 점검 실패" `
      --text "emergency-check 실행 실패 (exit=$rc)`n로그: $log" 2>&1 | Tee-Object -FilePath $log -Append
}

# 주간 리밸런싱이 조용히 실패했는지 외부 감시(4일 이상 성공기록 없으면 알람). 정상이면 조용.
& $PY quant/run.py healthcheck --job weekly --max-age-days 4 --notify 2>&1 | Tee-Object -FilePath $log -Append

"===== 종료 $(Get-Date -Format 'HH:mm:ss') =====" | Tee-Object -FilePath $log -Append
