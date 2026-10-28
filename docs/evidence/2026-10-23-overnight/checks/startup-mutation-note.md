`first generation not held for the validation` survives: without the `join` the first generation could open before the
base validation finishes, but the CPU fixture validates in well under a second, before the test touches `start.flag`, so
the race never shows. The join in `finally` is the guarantee; the other three mutants (ordering, error hand-over, waiting)
are killed. `runtime-cpu-full-startup.log` is the first full run: 3 failures from the new ordering assertion applied to a
resumed run and a missing `import pytest`, both fixed in the test before commit (targeted reruns: 36 passed).
