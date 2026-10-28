# Operator failure injection on Thao native Windows: hard-stop every process of the installed Worker app and of its
# candidate7 runtime (no graceful quit, no ledger/assignment edits). Prints the identities it stopped.
$ErrorActionPreference='Stop'
$app=Join-Path $env:LOCALAPPDATA 'Programs\@heteroesworker'
$runtime='D:\HeteroES-Worker-data\runtimes\81663cebe7eb'
$targets=@(Get-Process | Where-Object { $_.Path -and ($_.Path.StartsWith($app) -or $_.Path.StartsWith($runtime)) })
if(-not ($targets | Where-Object { $_.Path.StartsWith($runtime) })) { throw 'No compute process of the candidate7 runtime is running' }
$stopped=@($targets | ForEach-Object { [ordered]@{ pid=$_.Id; name=$_.ProcessName; started=$_.StartTime.ToUniversalTime().ToString('o'); path=$_.Path } })
$targets | Stop-Process -Force
Start-Sleep -Seconds 2
$left=@(Get-Process | Where-Object { $_.Path -and ($_.Path.StartsWith($app) -or $_.Path.StartsWith($runtime)) }).Count
[ordered]@{ event='hard_stop'; t=[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()/1000; stopped=$stopped; remaining=$left } | ConvertTo-Json -Depth 4 -Compress
