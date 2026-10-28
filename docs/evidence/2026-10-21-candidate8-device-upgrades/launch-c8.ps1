$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$env:ELECTRON_RUN_AS_NODE='1'
$env:HETEROES_GPU_ACCEPTANCE='1'
$task=Join-Path $env:LOCALAPPDATA 'Temp\heteroes-system-finish'
$app=Join-Path $env:LOCALAPPDATA 'Programs\@heteroesworker\HeteroES Worker.exe'
$args=@(('"'+(Join-Path $task 'driver.cjs')+'"'),'launch')
if(Test-Path (Join-Path $task 'launch-args.json')) { $args+=('"'+(Join-Path $task 'launch-args.json')+'"') }

$p=Start-Process -FilePath $app -ArgumentList $args -PassThru -RedirectStandardOutput (Join-Path $task 'launch-stdout.log') -RedirectStandardError (Join-Path $task 'launch-stderr.log')
$p.WaitForExit()
Write-Output ('launch driver exit: '+$p.ExitCode)
if($p.ExitCode -ne 0) { throw 'launch failed; private diagnostic log retained' }
