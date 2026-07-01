# AI Berkshire 주간 리밸런싱 자동 실행 래퍼
# Windows 작업 스케줄러에서 매주 수·토 15:00 호출(수=종가정렬, 토=주말점검). 로그는 quant/data/weekly.log.
# 매매는 밴드(±3%p) 이탈 시에만. 실주문은 별도 trade --live(기본 dry-run).
$ErrorActionPreference = "Continue"
$repo = "C:\Users\jhsum\code\ai-berkshire"
Set-Location $repo
$log = Join-Path $repo "quant\data\weekly.log"
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null
$ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
"`n===== $ts 주간 리밸런싱 시작 =====" | Tee-Object -FilePath $log -Append
# 최신 시세·재무로 매매지시 생성 (가치·퀄리티 전략)
python quant/run.py rebalance --notify 2>&1 | Tee-Object -FilePath $log -Append
$rc = $LASTEXITCODE
# 페이퍼 트레이딩(모의투자)도 같은 데이터로 집행 (--no-fetch로 방금 받은 시세 재사용)
"--- 페이퍼 트레이딩 ---" | Tee-Object -FilePath $log -Append
python quant/run.py paper --no-fetch --notify 2>&1 | Tee-Object -FilePath $log -Append
# 최신 리포트 자동 열기(리밸런싱 + 모의투자)
foreach ($pat in @('리밸런싱-*.md','모의투자-*.md')) {
  $r = Get-ChildItem "$repo\reports\quant\$pat" -ErrorAction SilentlyContinue |
       Sort-Object LastWriteTime -Descending | Select-Object -First 1
  if ($r) {
    "리포트: $($r.Name)" | Tee-Object -FilePath $log -Append
    try { Invoke-Item $r.FullName } catch { "열기 실패(무인세션?): $_" | Tee-Object -FilePath $log -Append }
  }
}
"===== 종료(exit=$rc) $(Get-Date -Format 'HH:mm:ss') =====" | Tee-Object -FilePath $log -Append
exit $rc
