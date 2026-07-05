# AI Berkshire 긴급 급변동 알람 래퍼
# 작업 스케줄러에서 각 시장 마감 후 호출(하루 2회): 한국 마감후 ~15:40, 미국 마감후 아침 ~07:00.
# 임계(지수±5%·VIX35·보유±10%) 초과 시에만 텔레그램 긴급 알람. 리밸런싱은 자동 안 함.
$ErrorActionPreference = "Continue"
$repo = "C:\Users\jhsum\code\ai-berkshire"
Set-Location $repo
$log = Join-Path $repo "quant\data\emergency.log"
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null
$ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
"`n===== $ts 급변동 점검 =====" | Tee-Object -FilePath $log -Append
python quant/run.py emergency-check --notify 2>&1 | Tee-Object -FilePath $log -Append
"===== 종료 $(Get-Date -Format 'HH:mm:ss') =====" | Tee-Object -FilePath $log -Append
