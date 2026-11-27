const path = require('node:path');
// The pinned Windows CUDA wheels (nvidia-cuda-nvdisasm, nvidia-cuda-nvrtc) install here. cuda.pathfinder finds the
// NVRTC DLLs by itself; the strict kernels' SASS audit finds nvdisasm.exe only through PATH (shutil.which).
const WINDOWS_CUDA_BIN = ['Lib', 'site-packages', 'nvidia', 'cu13', 'bin'];
/** The environment of a packaged Python child (agent bridge or self-test), independent of the user's Python. */
function agentEnv(python, source, base = process.env, platform = process.platform) {
  const env = { ...base, PYTHONPATH: source, PYTHONNOUSERSITE: '1', PYTHONUTF8: '1' };
  if (platform === 'win32') {
    const bin = path.win32.join(path.win32.dirname(python), ...WINDOWS_CUDA_BIN);
    // Windows environment names are case-insensitive; Node keeps the spelling it inherited (usually "Path").
    const key = Object.keys(env).find((name) => name.toUpperCase() === 'PATH') ?? 'Path';
    env[key] = env[key] ? bin + path.win32.delimiter + env[key] : bin;
  }
  return env;
}
module.exports = { agentEnv, WINDOWS_CUDA_BIN };
