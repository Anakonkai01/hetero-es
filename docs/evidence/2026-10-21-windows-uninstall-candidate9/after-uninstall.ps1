$ProgressPreference='SilentlyContinue'
$app=Join-Path $env:LOCALAPPDATA 'Programs\@heteroesworker\HeteroES Worker.exe'
$appdata=Join-Path $env:APPDATA '@heteroes\worker'
Write-Output ('app=' + (Test-Path $app) + ' appdata=' + (Test-Path $appdata) + ' dataFolder=' + (Test-Path 'D:\HeteroES-Worker-data'))
Write-Output ('appFolder=' + (Test-Path (Join-Path $env:LOCALAPPDATA 'Programs\@heteroesworker')))
Write-Output ('processes=' + @(Get-Process -Name 'HeteroES Worker' -ErrorAction SilentlyContinue).Count)
$keys=Get-ChildItem 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall','HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall' -ErrorAction SilentlyContinue | Get-ItemProperty | Where-Object { $_.DisplayName -like '*HeteroES*' }
Write-Output ('uninstallEntries=' + @($keys).Count + ' ' + (($keys | ForEach-Object { $_.DisplayName + ' ' + $_.DisplayVersion }) -join '; '))
Get-ChildItem 'D:\' -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -like '*eteroES*' } | ForEach-Object { Write-Output ('D:\' + $_.Name + ' lastWrite=' + $_.LastWriteTime.ToString('s')) }
Get-PSDrive C,D | ForEach-Object { Write-Output ($_.Name + ' freeGB=' + [math]::Round($_.Free/1GB,1)) }
Write-Output ('now=' + (Get-Date).ToString('s'))
