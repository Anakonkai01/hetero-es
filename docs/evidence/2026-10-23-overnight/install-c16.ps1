$ErrorActionPreference='Stop'
for($i=0;$i -lt 60;$i++){ if(-not (Get-Process -Name 'HeteroES Worker' -ErrorAction SilentlyContinue)){break}; Start-Sleep -Seconds 1 }
if(Get-Process -Name 'HeteroES Worker' -ErrorAction SilentlyContinue) {throw 'Worker must exit safely before install'}
Write-Output 'Worker exited after Quit safely'
$installer='F:\HeteroES-Worker-data\candidate16-setup.exe'
if((Get-FileHash -Algorithm SHA256 -LiteralPath $installer).Hash.ToLower() -ne '9c42f55b47cf4e08cc5b6dac78cc2f64b631c0ba261622e2fc5ec799721c4130') {throw 'Installer hash differs'}
Write-Output 'Installer SHA-256 matches prepared receipt'
$p=Start-Process -FilePath $installer -ArgumentList '/S' -Wait -PassThru
Write-Output ('Installer exit='+$p.ExitCode)
if($p.ExitCode -ne 0) {throw 'Installer failed'}
$app=Join-Path $env:LOCALAPPDATA 'Programs\@heteroesworker\resources\worker'
Write-Output (Get-Content -LiteralPath ($app+'\defaults.json') -Raw)
