$ProgressPreference='SilentlyContinue'
function Size($p){ [math]::Round(((Get-ChildItem -LiteralPath $p -Recurse -Force -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum)/1GB,3) }
$roots=@($env:APPDATA,$env:LOCALAPPDATA,(Join-Path $env:LOCALAPPDATA 'Temp'),(Join-Path $env:LOCALAPPDATA 'Programs'),$env:USERPROFILE,'D:\','C:\')
foreach($r in $roots){ Get-ChildItem -LiteralPath $r -Force -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -match 'hetero' } | ForEach-Object { Write-Output ('DIR ' + $_.FullName + ' GB=' + (Size $_.FullName) + ' last=' + $_.LastWriteTime.ToString('s')) } }
Get-ChildItem -LiteralPath (Join-Path $env:LOCALAPPDATA 'Temp') -Force -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -match 'hetero' } | ForEach-Object { Write-Output ('FILE ' + $_.FullName + ' MB=' + [math]::Round($_.Length/1MB,1)) }
$hf=Join-Path $env:USERPROFILE '.cache\huggingface'; Write-Output ('hfCache=' + (Test-Path $hf) + $(if(Test-Path $hf){' GB=' + (Size $hf)}))
$py=Join-Path $env:APPDATA 'Python'; if(Test-Path $py){ Get-ChildItem $py -Directory | ForEach-Object { Write-Output ('APPDATA Python\' + $_.Name + ' GB=' + (Size $_.FullName) + ' last=' + $_.LastWriteTime.ToString('s')) } }
Get-ChildItem 'HKCU:\Software' -ErrorAction SilentlyContinue | Where-Object { $_.PSChildName -match 'hetero' } | ForEach-Object { Write-Output ('REG ' + $_.Name) }
$lnk=@([Environment]::GetFolderPath('Desktop'),[Environment]::GetFolderPath('StartMenu'),[Environment]::GetFolderPath('Programs')) | ForEach-Object { Get-ChildItem $_ -Recurse -Filter '*.lnk' -ErrorAction SilentlyContinue } | Where-Object { $_.Name -match 'hetero' }
$lnk | ForEach-Object { Write-Output ('LNK ' + $_.FullName) }
Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object { $_.TaskName -match 'hetero' } | ForEach-Object { Write-Output ('TASK ' + $_.TaskName) }
Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -match 'hetero' } | ForEach-Object { Write-Output ('PROC ' + $_.Id + ' ' + $_.Path) }
Get-PSDrive C,D | ForEach-Object { Write-Output ($_.Name + ' freeGB=' + [math]::Round($_.Free/1GB,1)) }
