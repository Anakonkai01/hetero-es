"""Finding 13: hash libm's float functions numpy's float32 normal sampler uses, over fixed inputs; diff across machines."""
import ctypes, hashlib, json, sys
import numpy as np
libm = ctypes.CDLL("libm.so.6")
x = np.random.default_rng(1).random(2_000_000, dtype=np.float32)
out = {}
for name, arg in (("log1pf", -x), ("expf", -8 * x), ("logf", x)):
    f = getattr(libm, name); f.restype = ctypes.c_float; f.argtypes = [ctypes.c_float]
    y = np.array([f(float(v)) for v in arg[:300_000]], dtype=np.float32)
    out[name] = hashlib.sha256(y.tobytes()).hexdigest()[:16]
    np.save(f"libm-{name}-{sys.argv[1]}.npy", y)
print(json.dumps(out))
