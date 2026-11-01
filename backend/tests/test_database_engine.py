"""The same transaction contract runs on SQLite files and a real PostgreSQL test schema."""

import threading

import pytest


def test_database_commit_row_protocol_and_integer_parity(database):
    owner, _ = database
    with owner.transaction() as connection:
        connection.execute(
            "INSERT INTO entries(id,value,enabled,large) VALUES (:p0,:p1,:p2,:p3)", (1, "fixture", True, 2**34)
        )
    with owner.transaction(write=False) as connection:
        row = connection.execute("SELECT id,value,enabled,large FROM entries").fetchone()
        assert dict(row) == {"id": 1, "value": "fixture", "enabled": 1, "large": 2**34}
        assert type(row["enabled"]) is int and tuple(row) == (1, "fixture", 1, 2**34)
    assert owner.dialect in {"sqlite", "postgresql"}


def test_failure_rolls_back_and_nested_calls_reuse_the_outer_connection(database):
    owner, _ = database
    with pytest.raises(RuntimeError, match="rollback fixture"):
        with owner.transaction() as first:
            first.execute("INSERT INTO entries(id,value) VALUES (?,?)", (1, "pending"))
            with owner.transaction() as nested:
                assert nested is first
                assert nested.execute("SELECT value FROM entries WHERE id=?", (1,)).fetchone()[0] == "pending"
            raise RuntimeError("rollback fixture")
    with owner.transaction() as connection:
        assert connection.execute("SELECT count(*) FROM entries").fetchone()[0] == 0


def test_caught_nested_scope_failure_prevents_partial_commit(database):
    owner, _ = database
    with pytest.raises(RuntimeError, match="rollback"):
        with owner.transaction() as first:
            try:
                with owner.transaction() as nested:
                    nested.execute("INSERT INTO entries(id) VALUES (?)", (1,))
                    raise ValueError("nested fixture")
            except ValueError:
                pass
            first.execute("INSERT INTO entries(id) VALUES (?)", (2,))
    with owner.transaction() as connection:
        assert connection.execute("SELECT count(*) FROM entries").fetchone()[0] == 0


def test_failed_statement_can_be_handled_without_poisoning_the_write_transaction(database):
    from sqlalchemy.exc import IntegrityError

    owner, _ = database
    with owner.transaction() as connection:
        connection.execute("INSERT INTO entries(id) VALUES (?)", (1,))
        with pytest.raises(IntegrityError):
            connection.execute("INSERT INTO entries(id) VALUES (?)", (1,))
        connection.execute("INSERT INTO entries(id) VALUES (?)", (2,))
    with owner.transaction() as connection:
        assert [row[0] for row in connection.execute("SELECT id FROM entries ORDER BY id")] == [1, 2]


def test_readonly_and_closed_contexts_reject_writes_or_reuse(database):
    owner, _ = database
    with owner.transaction(write=False) as connection:
        assert connection.execute("SELECT count(*) FROM entries").fetchone()[0] == 0
        with pytest.raises(RuntimeError, match="read"):
            connection.execute("INSERT INTO entries(id) VALUES (?)", (1,))
    with pytest.raises(RuntimeError, match="closed"):
        connection.execute("SELECT 1")


def test_write_scope_claims_the_database_before_any_business_read(database):
    owner, another_owner = database
    attempted, entered, release = threading.Event(), threading.Event(), threading.Event()
    errors = []

    def contender():
        other = another_owner()
        try:
            attempted.set()
            with other.transaction():
                entered.set()
                release.wait(3)
        except BaseException as error:
            errors.append(type(error).__name__)
        finally:
            other.close()

    with owner.transaction():
        thread = threading.Thread(target=contender)
        thread.start()
        assert attempted.wait(3)
        assert not entered.wait(0.2), "A competing writer entered before the outer transaction released"
    assert entered.wait(3)
    release.set()
    thread.join(3)
    assert not thread.is_alive() and not errors
