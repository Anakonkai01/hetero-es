param([string]$Actions = "install selftest")
$app = Join-Path $env:LOCALAPPDATA "Programs\@heteroesworker\HeteroES Worker.exe"
$dir = "D:\heteroes-exe-test-20261127"
if (-not (Get-Process | Where-Object { $_.Path -eq $app })) {
  Start-Process -FilePath $app -ArgumentList "--remote-debugging-port=9339"
}
$env:ELECTRON_RUN_AS_NODE = "1"
& $app (Join-Path $dir "drive-app.cjs") 9339 (Join-Path $dir "drive.jsonl") @($Actions -split " ")
"driver exit $LASTEXITCODE"
