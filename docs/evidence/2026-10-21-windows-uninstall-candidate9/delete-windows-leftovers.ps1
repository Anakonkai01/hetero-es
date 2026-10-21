$ProgressPreference='SilentlyContinue'
if(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -match 'hetero' }){ throw 'a HeteroES process is running' }
$targets=@('D:\HeteroES-r11-long-data-20261020','D:\HeteroES-v3-20261019','D:\HeteroES-session4-20261020','D:\HeteroES-r11-cpu-guard-probe-20261021',
  (Join-Path $env:LOCALAPPDATA '@heteroesworker-updater'),(Join-Path $env:LOCALAPPDATA 'HeteroES-v3-20261019'))
foreach($t in $targets){
  if(-not (Test-Path -LiteralPath $t)){ Write-Output ('absent ' + $t); continue }
  $m=Get-ChildItem -LiteralPath $t -Recurse -Force -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum
  Remove-Item -LiteralPath $t -Recurse -Force -ErrorAction Continue
  Write-Output ('deleted=' + (-not (Test-Path -LiteralPath $t)) + ' ' + $t + ' files=' + $m.Count + ' GB=' + [math]::Round($m.Sum/1GB,3))
}
Get-PSDrive C,D | ForEach-Object { Write-Output ($_.Name + ' freeGB=' + [math]::Round($_.Free/1GB,1)) }
Write-Output ('now=' + (Get-Date).ToString('s'))
