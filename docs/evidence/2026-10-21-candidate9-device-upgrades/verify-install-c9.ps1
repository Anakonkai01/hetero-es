$ErrorActionPreference='Stop'
$root=Join-Path $env:LOCALAPPDATA 'Programs\@heteroesworker\resources\worker'
$d=Get-Content -LiteralPath (Join-Path $root 'defaults.json') -Raw | ConvertFrom-Json
if($d.build -ne 'lf1-20261021-r11-candidate9') { throw 'Wrong installed build' }
$h=(Get-FileHash -Algorithm SHA256 (Join-Path $root 'runtime.tar.gz')).Hash.ToLower()
if($h -ne '9a553d2dfae92859b4a41a12a8bb946bed8743ceb531745ffef689e4e7e9ae41') { throw 'Wrong installed runtime bundle' }
Write-Output ('installed build=' + $d.build + ' runtimeSha256=' + $h)
Write-Output ('worker app processes=' + @(Get-Process -Name 'HeteroES Worker' -ErrorAction SilentlyContinue).Count)
Get-PSDrive C,D | ForEach-Object { Write-Output ('after ' + $_.Name + ' freeBytes=' + $_.Free) }
