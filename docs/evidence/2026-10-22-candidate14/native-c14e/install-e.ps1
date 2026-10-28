$ErrorActionPreference='Stop'
for($i=0;$i -lt 60;$i++){ if(-not (Get-Process -Name 'HeteroES Worker' -ErrorAction SilentlyContinue)){break}; Start-Sleep -Seconds 1 }
if(Get-Process -Name 'HeteroES Worker' -ErrorAction SilentlyContinue) {throw 'Worker must exit safely before install'}
Write-Output 'Worker exited after RPC quit'
$installer='F:\HeteroES-Worker-data\candidate14e-setup.exe'
if((Get-FileHash -Algorithm SHA256 -LiteralPath $installer).Hash.ToLower() -ne '94a07104d7d66a59ebe006396af204b885b614eb99da5998fabd64fcfde442ef') {throw 'Installer hash differs'}
Write-Output 'Installer SHA-256 matches prepared receipt'
$p=Start-Process -FilePath $installer -ArgumentList '/S' -Wait -PassThru
Write-Output ('Installer exit='+$p.ExitCode)
if($p.ExitCode -ne 0) {throw 'Installer failed'}
$app=Join-Path $env:LOCALAPPDATA 'Programs\@heteroesworker\resources\worker'
Write-Output (Get-Content -LiteralPath ($app+'\defaults.json') -Raw)
