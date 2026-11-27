$ErrorActionPreference = "Stop"; $ProgressPreference = "SilentlyContinue"
$d = "D:\heteroes-exe-test-20261127"
$app = Join-Path $env:LOCALAPPDATA "Programs\@heteroesworker\HeteroES Worker.exe"
$env:ELECTRON_RUN_AS_NODE = "1"
Start-Process -FilePath $app -ArgumentList @((Join-Path $d drive-steps.cjs), 9339, (Join-Path $d quit.jsonl), (Join-Path $d quit-steps.json)) -Wait -NoNewWindow
Remove-Item Env:ELECTRON_RUN_AS_NODE
for ($i = 0; $i -lt 30 -and (Get-Process | Where-Object { $_.Path -eq $app }); $i++) { Start-Sleep 2 }
"app stopped: " + -not (Get-Process | Where-Object { $_.Path -eq $app })
$f = Join-Path $d "HeteroES-Worker-20261127-472ef70f.exe"
Invoke-WebRequest -UseBasicParsing -Uri "https://lab.heteroes.site/downloads/HeteroES%20Worker-0.1.0-20261127-472ef70f-Windows.exe" -OutFile $f
(Get-FileHash $f -Algorithm SHA256).Hash.ToLower()
$p = Start-Process -FilePath $f -ArgumentList "/S" -Wait -PassThru; "installer exit $($p.ExitCode)"
Get-ChildItem "$env:APPDATA\@heteroes\worker" | Select-Object -ExpandProperty Name
Start-Process -FilePath $app -ArgumentList "--remote-debugging-port=9339"
