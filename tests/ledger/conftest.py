import os

try:
    from hypothesis import settings
except ImportError:             # Hypothesis is a test extra: without it the tests that need it are skipped
    settings = None

if settings is not None:
    # "default": the same examples at every run (a red test is red for a reason, not for luck), quick.
    # "fuzz": random every time and many more examples, to hunt for bugs:  HETEROES_HYPOTHESIS=fuzz pytest tests/ledger
    settings.register_profile("default", max_examples=150, derandomize=True, deadline=None, print_blob=True)
    settings.register_profile("fuzz", max_examples=3000, derandomize=False, deadline=None, print_blob=True)
    settings.load_profile(os.environ.get("HETEROES_HYPOTHESIS", "default"))
