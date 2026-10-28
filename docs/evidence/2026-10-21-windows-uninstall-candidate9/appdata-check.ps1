$ProgressPreference='SilentlyContinue'
$root=Join-Path $env:APPDATA '@heteroes'
Write-Output ('appdataParent=' + (Test-Path $root))
if(Test-Path $root){ Get-ChildItem $root -Force | ForEach-Object { $s=(Get-ChildItem $_.FullName -Recurse -Force -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum; Write-Output ('  ' + $_.Name + ' GB=' + [math]::Round($s/1GB,2)) } }
$t=Join-Path $env:LOCALAPPDATA 'Temp\heteroes-system-finish'
Write-Output ('tempBackup=' + (Test-Path $t))
if(Test-Path $t){ Get-ChildItem $t -Force | ForEach-Object { $s=(Get-ChildItem $_.FullName -Recurse -Force -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum; Write-Output ('  ' + $_.Name + ' GB=' + [math]::Round($s/1GB,3)) } }
$bin=(New-Object -ComObject Shell.Application).Namespace(10)
$items=@($bin.Items() | Where-Object { $bin.GetDetailsOf($_,1) -like '*heteroes*' -or $_.Name -like '*heteroes*' })
Write-Output ('recycleBinItems=' + $items.Count)
$items | ForEach-Object { Write-Output ('  ' + $_.Name + ' from=' + $bin.GetDetailsOf($_,1) + ' size=' + $bin.GetDetailsOf($_,3)) }
