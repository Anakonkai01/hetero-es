$ProgressPreference='SilentlyContinue'
$procs=@(Get-Process -Name 'HeteroES Worker' -ErrorAction SilentlyContinue)
Write-Output ('worker processes before=' + $procs.Count)
$procs | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3
$dir=Join-Path $env:LOCALAPPDATA 'Programs\@heteroesworker'
$un=Join-Path $dir 'Uninstall HeteroES Worker.exe'
if(Test-Path $un){ $p=Start-Process -FilePath $un -ArgumentList '/S' -Wait -PassThru; Write-Output ('uninstaller exit=' + $p.ExitCode) } else { Write-Output 'no uninstaller' }
Start-Sleep -Seconds 5
$task=Join-Path $env:LOCALAPPDATA 'Temp\heteroes-live'
if(Test-Path $task){ Remove-Item -LiteralPath $task -Recurse -Force }
Write-Output ('app=' + (Test-Path $dir) + ' appdata=' + (Test-Path (Join-Path $env:APPDATA '@heteroes')) + ' dataFolder=' + (Test-Path 'D:\HeteroES-Worker-data') + ' task=' + (Test-Path $task) + ' processes=' + @(Get-Process -Name 'HeteroES Worker' -ErrorAction SilentlyContinue).Count)
Get-PSDrive C | ForEach-Object { Write-Output ('C freeGB=' + [math]::Round($_.Free/1GB,1)) }
