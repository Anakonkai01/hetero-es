"""Run one driver-e action on native Windows through the packaged Worker (ELECTRON_RUN_AS_NODE) and print its result."""
import subprocess, sys
action = sys.argv[1]
extra = sys.argv[2] if len(sys.argv) > 2 else ''
ps = r"""$ErrorActionPreference='Stop'
$env:ELECTRON_RUN_AS_NODE='1'
$env:HETEROES_GPU_ACCEPTANCE='1'
$task='F:\HeteroES-Worker-data\candidate14-control'
$app=Join-Path $env:LOCALAPPDATA 'Programs\@heteroesworker\HeteroES Worker.exe'
$info=New-Object System.Diagnostics.ProcessStartInfo
$info.FileName=$app
$info.Arguments='"'+$task+'\driver-e.cjs" ACTION EXTRA'
$info.UseShellExecute=$false
$info.RedirectStandardOutput=$true
$info.RedirectStandardError=$true
$p=New-Object System.Diagnostics.Process
$p.StartInfo=$info
$p.Start() | Out-Null
$stdout=$p.StandardOutput.ReadToEndAsync()
$stderr=$p.StandardError.ReadToEndAsync()
$p.WaitForExit()
Write-Output $stdout.Result
Write-Output ('stderr: '+$stderr.Result)
Write-Output ('ACTION exit='+$p.ExitCode)
""".replace('ACTION', action).replace('EXTRA', extra)
path = f'/home/pc5070ti/projects/heteroes/.scratch/candidate14e/ps-{action}.ps1'
open(path, 'w').write(ps)
r = subprocess.run([sys.executable, '/home/pc5070ti/projects/heteroes/.scratch/candidate14/run-windows-ps.py', path], timeout=300)
sys.exit(r.returncode)
