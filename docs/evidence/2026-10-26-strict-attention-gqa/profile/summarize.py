"""Group profile-02.json kernel time into whole-path categories; prints a table and writes summary.json."""
import json, sys
from pathlib import Path
here = Path(sys.argv[1])
report = json.loads((here / 'profile-02.json').read_text())
def group(name):
    if name == 'integer_linear' or 'gemm' in name: return 'projection GEMM'
    if name in ('integer_finish', 'integer_input', 'integer_weights'): return 'projection prep/finish'
    if name.startswith('strict_attention'): return 'attention'
    if name in ('strict_rms_norm', 'strict_silu_mul', 'strict_rope', 'strict_add'): return 'norm/act/rope/residual'
    if 'copy' in name or 'Copy' in name or 'Fill' in name: return 'copies/fills'
    return 'other'
out = []
for case in report['cases']:
    totals = {}
    for k in case['kernels']:
        totals[group(k['name'])] = totals.get(group(k['name']), 0.0) + k['ms']
    gap = case['gpuSpanMs'] - case['gpuBusyMs']
    row = {'engine': case['engine'], 'case': case['case'], 'tokPerS': round(case['plainTokensPerSecond'], 1),
           'spanMs': round(case['gpuSpanMs'], 1), 'gpuIdleMs': round(gap, 1),
           'ms': {k: round(v, 1) for k, v in sorted(totals.items(), key=lambda kv: -kv[1])},
           'share': {k: round(100 * v / case['gpuSpanMs'], 1) for k, v in totals.items()}}
    out.append(row)
    print(f"{row['engine']:5s} {row['case']:8s} {row['tokPerS']:7.1f} tok/s span {row['spanMs']:7.1f} ms idle {gap:5.1f} ms")
    for k, v in row['ms'].items():
        print(f"      {k:24s} {v:7.1f} ms {row['share'][k]:5.1f}%")
(here / 'summary.json').write_text(json.dumps(out, indent=2) + '\n')
