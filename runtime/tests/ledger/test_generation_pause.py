import pytest
from heteroes.coordinator import RunPaused
from test_coordinator import Env


def test_pause_finishes_generation_and_resume_has_identical_weights(tmp_path):
    requested=False
    def completed(summary):
        nonlocal requested
        requested=True
    env=Env(tmp_path,generation_completed=completed,pause_requested=lambda:requested)
    try:
        env.start_workers()
        with pytest.raises(RunPaused):env.coordinator.run(3)
        assert [g.generation for g in env.ledger.list_generations('exp')]==[0]
        update=env.ledger.get_update('exp',0)
        assert update.applied_at is not None
        assert env.job()['state']=='FINISHED'
        # No new candidate leases were created while paused. Resuming preserves
        # the same ledger, model and deterministic candidate identities.
        requested=False
        env.coordinator._generation_completed=None
        env.coordinator.run(3)
        rewards=[list(env.ledger.get_generation_results('exp',g).rewards) for g in range(3)]
        assert env.coordinator.parent_sha256==env.oracle_child(rewards)
        assert env.coordinator.recover()==3
    finally:env.close()


def test_pause_before_first_generation_still_creates_a_completed_barrier(tmp_path):
    env=Env(tmp_path,pause_requested=lambda:True)
    try:
        env.start_workers()
        with pytest.raises(RunPaused):env.coordinator.run(2)
        assert env.ledger.get_update('exp',0).applied_at is not None
        assert len(env.ledger.list_generations('exp'))==1
    finally:env.close()
