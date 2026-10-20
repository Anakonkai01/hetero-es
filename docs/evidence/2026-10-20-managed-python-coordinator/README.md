# Managed Python rewards reach the coordinator agent (2026-10-20, session 5)

Found by the first real managed `serve --lab` run on r11 candidate3 (isolated lab, Quang CPU coordinator, 5070 Ti worker):
the experiment stayed STARTING because the coordinator agent refused every COORDINATE command with
`ValueError: this lab accepts only declarative scorers` (7 retries in the agent's command_failures table, no run directory).
`heteroes.product.run_supervisor.validate` called `validate_options(config)` without `allow_python`, so every managed
experiment with a Python scorer or coefficient rule (owner decision since efe8e33) could never start on any coordinator,
desktop or CLI. The efe8e33 tests exercised `prepare_run` directly and skipped this agent check.

The check now admits Python exactly as `prepare_run` does and still requires the frozen `pythonCode` that pins it.
`before.log` (red for the stated reason), `after.log` (52 product/agent/large-data tests), mutation 3/3.

## What this does NOT show

This receipt is the CPU test of the check. The real managed rerun is recorded separately.
