# Rebuild the Windows Worker's Python exactly as setup.cjs does (pinned Python + pinned wheels, --require-hashes),
# then run the strict Qwen parity probe with the app's environment (agent-env.cjs) and WITHOUT native_python.py.
# Usage: powershell -ExecutionPolicy Bypass -File check-packaged-env.ps1 -Root D:\heteroes-winapp-check-20261127 -Models <dir>
param([string]$Root, [string]$Models)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
# Keep everything on this drive: the owner's C: is nearly full (temp files and the pip cache would land there).
$tmp = Join-Path $Root "tmp"; New-Item -ItemType Directory -Force $tmp | Out-Null
$env:TEMP = $tmp; $env:TMP = $tmp; $env:PIP_NO_CACHE_DIR = "1"
$res = Join-Path $Root "resources"
$prof = Get-Content (Join-Path $res "profile.json") -Raw | ConvertFrom-Json
$win = $prof.platforms.windows
$dl = Join-Path $Root "downloads"; $wh = Join-Path $dl "windows"
New-Item -ItemType Directory -Force $dl, $wh | Out-Null
function Get-Verified($item, $dir) {
  $file = Join-Path $dir $item.name
  if (-not (Test-Path $file) -or (Get-FileHash $file -Algorithm SHA256).Hash.ToLower() -ne $item.sha256) {
    Invoke-WebRequest -Uri $item.url -OutFile "$file.part" -UseBasicParsing
    if ((Get-FileHash "$file.part" -Algorithm SHA256).Hash.ToLower() -ne $item.sha256) { throw "checksum $($item.name)" }
    Move-Item -Force "$file.part" $file
  }
  return $file
}
$rt = Join-Path $Root "runtime"
if (-not (Test-Path (Join-Path $rt "python\python.exe"))) {
  New-Item -ItemType Directory -Force $rt | Out-Null
  $archive = Get-Verified $win.python $dl
  tar -xzf $archive -C $rt
}
if ((Get-FileHash (Join-Path $res "runtime.tar.gz") -Algorithm SHA256).Hash.ToLower() -ne $prof.runtimeSha256) { throw "runtime.tar.gz differs from profile" }
tar -xzf (Join-Path $res "runtime.tar.gz") -C $rt
foreach ($w in $win.wheels) { Get-Verified $w $wh | Out-Null }
$py = Join-Path $rt "python\python.exe"
$env:PYTHONNOUSERSITE = "1"; $env:PYTHONUTF8 = "1"
& $py -m pip install --no-index --find-links $wh --require-hashes -r (Join-Path $res $win.lockFile)
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
# agent-env.cjs: <python dir>\Lib\site-packages\nvidia\cu13\bin first on Path
$env:Path = (Join-Path $rt "python\Lib\site-packages\nvidia\cu13\bin") + ";" + $env:Path
$env:PYTHONPATH = (Join-Path $rt "src") + ";" + (Join-Path $Root "repo\runtime\scripts")
$env:HETEROES_GPU_ACCEPTANCE = "1"
& $py -c "import cuda.bindings, shutil; from heteroes.strict.strict_cuda import _find_nvdisasm; print('cuda.bindings', cuda.bindings.__version__, 'nvdisasm', _find_nvdisasm())"
Set-Location (Join-Path $Root "repo")
& $py acceptance\probes\strict_parity.py --gpu --model qwen --models $Models --out (Join-Path $Root "parity-qwen.json")
exit $LASTEXITCODE
