# AI Berkshire 주간 리밸런싱 자동 실행 래퍼
# Windows 작업 스케줄러에서 매주 호출. 로그는 quant/data/weekly.log.
$ErrorActionPreference = "Continue"
$repo = "C:\Users\jhsum\code\ai-berkshire"
Set-Location $repo
$log = Join-Path $repo "quant\data\weekly.log"
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null
$ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
"`n===== $ts 주간 리밸런싱 시작 =====" | Tee-Object -FilePath $log -Append
# 최신 시세·재무로 매매지시 생성 (가치·퀄리티 전략)
python quant/run.py rebalance 2>&1 | Tee-Object -FilePath $log -Append
$rc = $LASTEXITCODE
"===== 종료(exit=$rc) $(Get-Date -Format 'HH:mm:ss') =====" | Tee-Object -FilePath $log -Append
exit $rc
