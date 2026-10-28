$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$task=Join-Path $env:LOCALAPPDATA 'Temp\heteroes-system-finish'
if(Get-Process -Name 'HeteroES Worker' -ErrorAction SilentlyContinue) { throw 'Worker must stop before install' }
Get-PSDrive C,D | ForEach-Object { Write-Output ('before ' + $_.Name + ' freeGB=' + [math]::Round($_.Free/1GB,1)) }
Invoke-WebRequest -UseBasicParsing -Uri 'http://100.110.165.40:8802/worker/HeteroES%20Worker%20Setup%200.1.0.exe' -OutFile (Join-Path $task 'worker-setup-c8.exe')
Write-Output ('before: app=' + (Test-Path (Join-Path $env:LOCALAPPDATA 'Programs\@heteroesworker\HeteroES Worker.exe')) + ' appdata=' + (Test-Path (Join-Path $env:APPDATA '@heteroes\worker')))
$hash=(Get-FileHash -Algorithm SHA256 (Join-Path $task 'worker-setup-c8.exe')).Hash.ToLower()
if($hash -ne 'dbc239137d6c1a11d52b915af9c183a022fd3eb92a5f8a4ef499b7a694a7509b') { throw 'Installer hash differs' }
Write-Output 'installer hash matches the prepared receipt'
$process=Start-Process -FilePath (Join-Path $task 'worker-setup-c8.exe') -ArgumentList '/S' -Wait -PassThru
Write-Output ('Candidate8 installer exit: '+$process.ExitCode)
if($process.ExitCode -ne 0) { throw 'Installer failed' }
Write-Output ('defaults=' + (Get-Content -LiteralPath (Join-Path $env:LOCALAPPDATA 'Programs\@heteroesworker\resources\worker\defaults.json') -Raw))
Get-PSDrive C,D | ForEach-Object { Write-Output ('after ' + $_.Name + ' freeGB=' + [math]::Round($_.Free/1GB,1)) }
