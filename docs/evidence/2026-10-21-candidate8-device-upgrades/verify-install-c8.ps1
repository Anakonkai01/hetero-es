$ErrorActionPreference='Stop'
$root=Join-Path $env:LOCALAPPDATA 'Programs\@heteroesworker\resources\worker'
$d=Get-Content -LiteralPath (Join-Path $root 'defaults.json') -Raw | ConvertFrom-Json
if($d.build -ne 'lf1-20261021-r11-candidate8') { throw 'Wrong installed build' }
$h=(Get-FileHash -Algorithm SHA256 (Join-Path $root 'runtime.tar.gz')).Hash.ToLower()
if($h -ne 'b377c9c94cea16817978c67d32e72d0dea479c13df42682467842f374c46a62b') { throw 'Wrong installed runtime bundle' }
Write-Output ('installed build=' + $d.build + ' runtimeSha256=' + $h)
Write-Output ('worker app processes=' + @(Get-Process -Name 'HeteroES Worker' -ErrorAction SilentlyContinue).Count)
Get-PSDrive C,D | ForEach-Object { Write-Output ('after ' + $_.Name + ' freeBytes=' + $_.Free) }
