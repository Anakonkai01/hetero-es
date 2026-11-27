$ErrorActionPreference = "Stop"
$root = Join-Path $env:APPDATA "HeteroES Worker"
$data = "D:\HeteroES-Worker-data"
New-Item -ItemType Directory -Force $root, $data | Out-Null
# Same content as Setup.chooseDataFolder("D:\") writes (the page's folder picker), so nothing large lands on C:.
$storage = [ordered]@{ runtimes = "$data\runtimes"; models = "$data\models"; downloads = "$data\downloads"; artifacts = "$data\artifacts" }
Set-Content -Encoding ascii -Path (Join-Path $root "storage.json") -Value ($storage | ConvertTo-Json)
Set-Content -Encoding ascii -NoNewline -Path (Join-Path $root "data-folder.txt") -Value $data
$p = Start-Process -FilePath "D:\heteroes-exe-test-20261127\HeteroES-Worker-20261127-fdf359a3.exe" -ArgumentList "/S" -Wait -PassThru
"installer exit $($p.ExitCode)"
$app = Join-Path $env:LOCALAPPDATA "Programs\HeteroES Worker"
Get-ChildItem $app | Select-Object -ExpandProperty Name
"{0:N0} MB" -f ((Get-ChildItem $app -Recurse | Measure-Object Length -Sum).Sum / 1MB)
Get-Content (Join-Path $root "storage.json")
Get-Process | Where-Object { $_.ProcessName -like "HeteroES*" } | Select-Object Id, ProcessName
