"""The long-run criterion of a strict soak (gate M5.long-run): coordinator bookkeeping must not grow over the run."""


def growth_failure(bookkeeping, limit):
    """None when the late third's mean seconds per generation is at most `limit` times the early third's, else why."""
    if not {"early", "late"} <= set(bookkeeping):
        return "the run is too short to compare early and late generations"
    early, late = bookkeeping["early"]["total_seconds"], bookkeeping["late"]["total_seconds"]
    if late > limit * early:
        return f"bookkeeping grew from {early} s to {late} s per generation (limit {limit}x)"
    return None
