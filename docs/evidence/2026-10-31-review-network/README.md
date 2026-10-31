# Review A1: credential-safe HTTP clients

2026-10-31. Baseline `f27c3d6a`; implementation is on `review/fixes-2026-11`.

- Red test reproduces default urllib redirects on compute JSON and POST clients.
- Integration covers 16 call paths, 301/302/303/307/308, additional 3xx, safe origin diagnostics,
  private clients bypassing proxies, and researcher clients retaining system proxies.
- Target server request count must remain zero after each redirect rejection. Test credentials are synthetic.
- Targeted regression: 1,354 passed, 1 skipped (CPU, ledger + notebook SDK + study).
- Final integration suite: 105 passed. Mutation control: 105 passed; 18/18 mutants killed on disposable copies.
  The mutation receipt contains the final integration result, after fixing the fixture to consume streamed request
  bodies before replying (avoids a connection-close race masking the redirect response).

Commands:

```bash
# runtime working directory
CUDA_VISIBLE_DEVICES='' PYTHONPATH=src ~/miniforge3/envs/heteroes-match/bin/python -m pytest -q tests/ledger tests/v3/test_sdk_lab.py tests/study
# repository root
python3 scripts/mutation-check.py --repo runtime --copy src --copy tests/ledger/test_http_redirects.py --env PYTHONPATH=src --env CUDA_VISIBLE_DEVICES= --test '/home/pc5070ti/miniforge3/envs/heteroes-match/bin/python -m pytest -q tests/ledger/test_http_redirects.py' --mutants .scratch/review-2026-11/A1-mutants.json
```

## What this does NOT show

This is CPU HTTP security evidence, not full product acceptance, cross-GPU numerical proof, or cloud deployment.
The full project goal and A2–C remain open. HTTPS uses the same response handler; loopback probes use HTTP.
Existing live lab state and credentials are not included or modified.
