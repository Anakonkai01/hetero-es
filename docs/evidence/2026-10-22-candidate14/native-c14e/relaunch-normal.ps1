$ErrorActionPreference='Stop'
for($i=0;$i -lt 60;$i++){ if(-not (Get-Process -Name 'HeteroES Worker' -ErrorAction SilentlyContinue)){break}; Start-Sleep -Seconds 1 }
if(Get-Process -Name 'HeteroES Worker' -ErrorAction SilentlyContinue) {throw 'Worker did not exit'}
Write-Output 'Worker exited after RPC quit'
$exe=Join-Path $env:LOCALAPPDATA 'Programs\@heteroesworker\HeteroES Worker.exe'
$action=New-ScheduledTaskAction -Execute $exe
$principal=New-ScheduledTaskPrincipal -UserId ($env:USERDOMAIN+'\'+$env:USERNAME) -LogonType Interactive
Register-ScheduledTask -TaskName 'HeteroES-candidate14e-relaunch' -Action $action -Principal $principal -Force | Out-Null
Start-ScheduledTask -TaskName 'HeteroES-candidate14e-relaunch'
Start-Sleep -Seconds 8
Unregister-ScheduledTask -TaskName 'HeteroES-candidate14e-relaunch' -Confirm:$false
Get-CimInstance Win32_Process -Filter "Name='HeteroES Worker.exe'" | ForEach-Object { [pscustomobject]@{Id=$_.ProcessId; Session=$_.SessionId; Debug=($_.CommandLine -match 'remote-debugging|inspect')} } | Format-Table | Out-String
