# Windows packaged Worker launch failure (2026-10-20)

The native Windows packaged GPU self-test passed. The first isolated two-machine GSM8K attempt then failed to start
the Windows worker. A CPU diagnostic reproduced `PermissionError` while `worker_environment` inspected
`\usr\lib\wsl\drivers`: a Windows process launched from a WSL UNC working directory can see those paths, but must not
select Linux driver libraries. This happened before creating a subprocess.

The old agent had already written `launch-intent.json`, leaving ownership unknown despite the failed preparation.
Tests cover native environment isolation, known failures before creation, failed OS creation, ownership uncertainty
after creation and adopting an already recorded process.

## What this does NOT show

- The failed attempt is not two-machine acceptance. It is cancelled through the isolated lab API.
- CPU diagnostics and tests do not establish successful GPU training on Windows.
- A failed process-identity query after creation must still retain ownership; connectivity or elapsed time never
  proves that a worker stopped.
