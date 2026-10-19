"""Shared backend policies preserve strict input and durable settings behavior."""
import pytest
from backend.policies import backup_policy, dispatch_held, set_disabled_workers, read_setting


@pytest.mark.parametrize('policy', [{'interval':True,'retain':3},{'interval':0,'retain':3},
    {'interval':1,'retain':1001},{'interval':1,'retain':3,'extra':1},None])
def test_backup_policy_rejects_invalid_values(policy):
    with pytest.raises(ValueError):backup_policy(policy)


def test_backup_policy_accepts_boundaries_and_copies_input():
    value={'interval':1,'retain':1000}
    result=backup_policy(value)
    assert result==value and result is not value


def test_shared_settings_preserve_hold_and_sorted_disabled_workers(lab):
    _,store,_,_=lab
    with store.db() as db:
        assert dispatch_held(db) is False
        db.execute('UPDATE settings SET value=? WHERE key="dispatchHold"',('true',))
        assert dispatch_held(db) is True
        set_disabled_workers(db,{'z','a'})
        assert read_setting(db,'disabledWorkers')==['a','z']


def test_unknown_process_state_and_physical_alias_keep_device_busy(lab):
    from backend.policies import has_device_reservation, processes_drained
    _,store,_,_=lab
    assert processes_drained([])
    assert processes_drained([{'coordinatorAlive':False,'workerAlive':False}])
    assert not processes_drained([{'workerAlive':False}])
    with store.db() as db:
        assert not has_device_reservation(db,'new','gpu')
        db.execute('INSERT INTO physical_reservations VALUES (?,?)',('gpu','assignment'))
        assert has_device_reservation(db,'new','gpu')
        assert not has_device_reservation(db,'new','different')
        db.execute('INSERT INTO device_reservations VALUES (?,?)',('old','assignment'))
        assert has_device_reservation(db,'old')
