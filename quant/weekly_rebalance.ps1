# AI Berkshire 주간 리밸런싱 자동 실행 래퍼
# 작업 스케줄러가 매주 수·토 15:00 호출(-WindowStyle Hidden = 보이는 창 없음). 로그는 quant/data/weekly.log.
# 매매는 밴드(±3%p) 이탈 시에만. 실주문은 별도 trade --live(기본 dry-run).
#
# 2026-07-17 개편: 7/15 실행이 콘솔 창 종료(0xC000013A=STATUS_CONTROL_C_EXIT)로 죽었는데
# 아무 알림도 없었고, Tee-Object 버퍼까지 날아가 로그에 단서조차 안 남았다. 재발방지 4종:
#   - 창을 숨겨(작업 액션의 -WindowStyle Hidden) 실수로 닫을 창 자체를 없앰
#   - 단계별 exit 코드를 잡아 실패하면 텔레그램 발송(성공 때만 알리던 것 → 실패도 알림)
#   - PYTHONUNBUFFERED로 중도 종료 시에도 로그에 흔적이 남게
#   - 전 단계 성공 시 성공도장 → 별도 healthcheck가 무성실패를 외부에서 잡음
$ErrorActionPreference = "Continue"
# 한글 깨짐 방지 (2026-07-22 오너 제보 "한글깨짐"): PS 5.1 이 UTF-8 파이썬 출력을
# 콘솔 코드페이지(CP949)로 잘못 해독해 로그·텔레그램 한글이 전부 깨졌다.
# (파일 자체도 BOM 없는 UTF-8 이라 한글 리터럴부터 깨져 있었음 → BOM 재저장 병행)
try {
  [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
  $OutputEncoding = [System.Text.Encoding]::UTF8
} catch { }
$repo = "C:\Users\jhsum\code\ai-berkshire"
Set-Location $repo
$log = Join-Path $repo "quant\data\weekly.log"
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null

# 파이썬 출력을 줄 단위로 즉시 흘려보낸다. 강제종료돼도 어디까지 갔는지 로그에 남는다.
$env:PYTHONUNBUFFERED = "1"
$env:PYTHONIOENCODING = "utf-8"

# PATH의 python.exe는 0바이트 Store 앱 별칭(App Execution Alias)이라 비대화형 컨텍스트에서
# 깨질 수 있다. 실체 경로를 직접 찾아 쓰고, 못 찾을 때만 PATH로 폴백한다.
function Resolve-Python {
  $c = Get-ChildItem "$env:LOCALAPPDATA\Python\pythoncore-*\python.exe" -ErrorAction SilentlyContinue |
       Where-Object { $_.Length -gt 0 } | Sort-Object FullName -Descending | Select-Object -First 1
  if ($c) { return $c.FullName }
  $g = Get-Command python -ErrorAction SilentlyContinue
  if ($g -and (Get-Item $g.Source).Length -gt 0) { return $g.Source }
  return "python"
}
$PY = Resolve-Python

$failures = [System.Collections.Generic.List[string]]::new()
$completed = $false

function Write-Log([string]$m) { $m | Tee-Object -FilePath $log -Append }

function Invoke-Step([string]$name, [string[]]$argv) {
  Write-Log "--- $name ---"
  & $PY @argv 2>&1 | Tee-Object -FilePath $log -Append
  $rc = $LASTEXITCODE
  if ($rc -ne 0) {
    Write-Log "!!! $name 실패 (exit=$rc)"
    $failures.Add("$name (exit=$rc)")   # 부모 스코프 리스트에 .Add — 대입이 아니라 메서드 호출
  }
}

try {
  Write-Log "`n===== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') 주간 리밸런싱 시작 ====="
  Write-Log "python: $PY"

  # 최신 시세·재무로 매매지시 생성 (가치·퀄리티 전략)
  Invoke-Step "한국 리밸런싱" @('quant/run.py', 'rebalance', '--notify')
  # 페이퍼 트레이딩(모의투자) — --no-fetch로 방금 받은 시세 재사용
  Invoke-Step "페이퍼 트레이딩" @('quant/run.py', 'paper', '--no-fetch', '--notify')
  # 미국 성장주 모멘텀(신호) — yfinance 자체수집. 실행은 수동(미국 브로커).
  Invoke-Step "미국 모멘텀" @('quant/run.py', 'us-rebalance', '--notify')

  # 최신 리포트 자동 열기(창은 숨겨도 로그온 세션이라 열림). 무인 세션이면 조용히 건너뜀.
  foreach ($pat in @('리밸런싱-*.md', '모의투자-*.md', '미국리밸런싱-*.md')) {
    $r = Get-ChildItem "$repo\reports\quant\$pat" -ErrorAction SilentlyContinue |
         Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($r) {
      Write-Log "리포트: $($r.Name)"
      try { Invoke-Item $r.FullName } catch { Write-Log "  (열기 생략: 무인세션)" }
    }
  }
  $completed = $true
}
finally {
  # finally는 Ctrl+C엔 돌지만 창 강제종료엔 못 돈다 → 그 사각은 healthcheck가 담당.
  if (-not $completed) { $failures.Add("스크립트 비정상 종료(중도 강제종료 추정)") }

  if ($failures.Count -gt 0) {
    $body = "주간 리밸런싱 자동실행에 실패했습니다.`n`n" + ($failures -join "`n") + "`n`n로그: $log"
    Write-Log "!!! 실패 알림 발송: $($failures -join ' / ')"
    & $PY quant/run.py alert --subject "[AI Berkshire] 🚨 주간 리밸런싱 실패" --text $body 2>&1 |
      Tee-Object -FilePath $log -Append
  }
  else {
    & $PY quant/run.py mark-success --job weekly 2>&1 | Tee-Object -FilePath $log -Append
  }
  Write-Log "===== 종료(실패 $($failures.Count)건) $(Get-Date -Format 'HH:mm:ss') ====="
}
exit $(if ($failures.Count -gt 0) { 1 } else { 0 })
