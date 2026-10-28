$ProgressPreference='SilentlyContinue'
$t=Join-Path $env:LOCALAPPDATA 'Temp\heteroes-system-finish'
if(-not (Test-Path $t)){ Write-Output 'absent before'; exit 0 }
if(Get-Process -Name 'HeteroES Worker' -ErrorAction SilentlyContinue){ throw 'HeteroES Worker is running' }
$before=(Get-ChildItem $t -Recurse -Force -File | Measure-Object Length -Sum)
Write-Output ('before files=' + $before.Count + ' GB=' + [math]::Round($before.Sum/1GB,3))
Remove-Item -LiteralPath $t -Recurse -Force
Write-Output ('after exists=' + (Test-Path $t))
Get-PSDrive C | ForEach-Object { Write-Output ('C freeGB=' + [math]::Round($_.Free/1GB,1)) }
Write-Output ('now=' + (Get-Date).ToString('s'))
