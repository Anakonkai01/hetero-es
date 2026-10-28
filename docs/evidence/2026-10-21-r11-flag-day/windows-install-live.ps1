$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$task=Join-Path $env:LOCALAPPDATA 'Temp\heteroes-live'
New-Item -ItemType Directory -Force -Path $task | Out-Null
if(Get-Process -Name 'HeteroES Worker' -ErrorAction SilentlyContinue) { throw 'Worker must stop before install' }
Get-PSDrive C,D | ForEach-Object { Write-Output ('before ' + $_.Name + ' freeGB=' + [math]::Round($_.Free/1GB,1)) }
$name='HeteroES Worker-0.1.0-lf1-20261021-r11-candidate9-Windows.exe'
$file=Join-Path $task 'worker-setup-live.exe'
Invoke-WebRequest -UseBasicParsing -Uri ('https://lab.heteroes.site/downloads/' + [uri]::EscapeDataString($name)) -OutFile $file
$hash=(Get-FileHash -Algorithm SHA256 $file).Hash.ToLower()
if($hash -ne 'e9f1f4c79997a2c52eb807950c8e85c27ba7baa47eacb1e6b184cac6f376b7ec') { throw 'Installer hash differs' }
Write-Output 'public installer hash matches the published receipt'
$process=Start-Process -FilePath $file -ArgumentList '/S' -Wait -PassThru
Write-Output ('installer exit: ' + $process.ExitCode)
if($process.ExitCode -ne 0) { throw 'Installer failed' }
Write-Output ('defaults=' + (Get-Content -LiteralPath (Join-Path $env:LOCALAPPDATA 'Programs\@heteroesworker\resources\worker\defaults.json') -Raw))
Get-PSDrive C,D | ForEach-Object { Write-Output ('after ' + $_.Name + ' freeGB=' + [math]::Round($_.Free/1GB,1)) }
