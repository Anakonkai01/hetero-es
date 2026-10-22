$ErrorActionPreference='Stop'
for($i=0;$i -lt 60;$i++){ if(-not (Get-Process -Name 'HeteroES Worker' -ErrorAction SilentlyContinue)){break}; Start-Sleep -Seconds 1 }
if(Get-Process -Name 'HeteroES Worker' -ErrorAction SilentlyContinue) {throw 'Worker must exit safely before install'}
Write-Output 'Worker exited after Quit safely'
$installer='F:\HeteroES-Worker-data\candidate15-setup.exe'
if((Get-FileHash -Algorithm SHA256 -LiteralPath $installer).Hash.ToLower() -ne '63520695a45725dda0734e788d8898700c24ea8bc4e3f4ef526681e5ee9e5727') {throw 'Installer hash differs'}
Write-Output 'Installer SHA-256 matches prepared receipt'
$p=Start-Process -FilePath $installer -ArgumentList '/S' -Wait -PassThru
Write-Output ('Installer exit='+$p.ExitCode)
if($p.ExitCode -ne 0) {throw 'Installer failed'}
$app=Join-Path $env:LOCALAPPDATA 'Programs\@heteroesworker\resources\worker'
Write-Output (Get-Content -LiteralPath ($app+'\defaults.json') -Raw)
