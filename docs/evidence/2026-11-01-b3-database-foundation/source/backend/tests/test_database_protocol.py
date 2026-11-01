"""Portable named bindings and the row/result contract needed by existing repositories."""

import pytest

from backend.db.bindings import bind_parameters
from backend.db.rows import Row, Result


def test_positional_parameters_become_named_and_booleans_keep_integer_storage():
    sql, parameters = bind_parameters("SELECT ? AS enabled, ? AS name", (True, "fixture"))
    assert sql == "SELECT :p0 AS enabled, :p1 AS name"
    assert parameters == {"p0": 1, "p1": "fixture"}
    assert type(parameters["p0"]) is int


def test_question_marks_in_literals_identifiers_comments_and_dollar_quotes_are_not_parameters():
    sql = "SELECT '?' AS literal, \"odd?name\", $$?$$, $tag$?$tag$, ? /* ? */ -- ?\n"
    converted, parameters = bind_parameters(sql, (7,))
    assert converted == sql.replace(", ? /*", ", :p0 /*")
    assert parameters == {"p0": 7}


def test_named_tuple_bindings_keep_repeated_names_and_postgres_casts():
    sql, parameters = bind_parameters("SELECT :p0::bigint + :p0, :p1", (9, False))
    assert sql == "SELECT :p0::bigint + :p0, :p1"
    assert parameters == {"p0": 9, "p1": 0}


def test_named_mapping_values_are_not_serialized_or_interpolated():
    sql, parameters = bind_parameters(
        "SELECT :value, :empty, :enabled", {"value": "quote'fixture?", "empty": None, "enabled": False}
    )
    assert sql == "SELECT :value, :empty, :enabled"
    assert parameters == {"value": "quote'fixture?", "empty": None, "enabled": 0}


@pytest.mark.parametrize(
    "sql,parameters",
    [("SELECT ?", ()), ("SELECT 1", (7,)), ("SELECT :p1", (7,)), ("SELECT :name", {}), ("SELECT ? + :p0", (7,))],
)
def test_wrong_or_mixed_bindings_are_rejected_without_echoing_values(sql, parameters):
    with pytest.raises(ValueError):
        bind_parameters(sql, parameters)


def test_rows_support_positional_iteration_named_keys_and_dict_conversion():
    row = Row(("id", "VALUE"), (7, "fixture"))
    assert row[0] == row["id"] == 7
    assert row[-1] == row["value"] == "fixture"
    assert tuple(row) == (7, "fixture")
    assert row.keys() == ["id", "VALUE"]
    assert dict(row) == {"id": 7, "VALUE": "fixture"}
    with pytest.raises(IndexError):
        row["missing"]


def test_duplicate_row_names_keep_sqlite_first_column_lookup_behavior():
    row = Row(("value", "VALUE"), (3, 9))
    assert row["VALUE"] == row["value"] == 3
    assert tuple(row) == (3, 9)


def test_result_adapts_real_sqlalchemy_core_results_and_empty_dml():
    from sqlalchemy import create_engine, text

    engine = create_engine("sqlite+pysqlite://")
    try:
        with engine.begin() as connection:
            result = Result(connection.execute(text("SELECT :value AS value"), {"value": 17}))
            assert dict(result.fetchone()) == {"value": 17}
            assert result.fetchone() is None
            assert result.fetchall() == []
            connection.execute(text("CREATE TABLE entries(id INTEGER PRIMARY KEY)"))
            inserted = Result(connection.execute(text("INSERT INTO entries VALUES (:id)"), {"id": 4}))
            assert inserted.rowcount == 1
            assert inserted.fetchone() is None and inserted.fetchall() == []
            assert [tuple(row) for row in Result(connection.execute(text("SELECT id FROM entries")))] == [(4,)]
    finally:
        engine.dispose()
