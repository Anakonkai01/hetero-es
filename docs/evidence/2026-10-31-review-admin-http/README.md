# Review A-023: administrative HTTP clients

2026-10-31. Four administrative scripts also used default urllib redirects: lab-login, verify-public-lab,
check-public-replay and recovery. They now reuse http_safety with system proxies retained for researcher tools;
recovery prints only the sanitized RedirectError diagnostic or the type of other errors. Signed object downloads
and uploads reject redirects as well. No administrative script was run against the live lab.

Six loopback integration cases fail before the change; script/recovery regression after the change: 17 passed.
Four mutations replacing each script's safe opener with a default opener are all killed. The recovery compatibility
fixture now patches the safe transport boundary. The first targeted attempt from repository root failed two old
subprocess tests because those require runtime as cwd; the attached final log uses the documented runtime cwd.

The attached interim CPU acceptance receipt belongs to 2fabe28a / src-1ab5a488..., BEFORE this follow-up fix:
2/2 checks passed, including complete check-all (596 seconds), runtime 3315 passed / 1045 skipped, backend SQLite
464 passed. This was completed before changing source. Final-source acceptance is repeated after the A-023 commit.
The earlier CUDA-engine note in the contract was also corrected to say the optional Recipe v1 engine is implemented.

## What this does NOT show

This does not establish final-source A6, remote GPU acceptance or live public verification. Recovery HTTP APIs are
stubbed only to isolate signed object transfer; object redirect responses themselves use real loopback HTTP servers.
All test credentials are synthetic. External dependency downloads without credentials (PyPI/GitHub build scripts)
retain their separate behavior. No live lab data, password or token is included.
