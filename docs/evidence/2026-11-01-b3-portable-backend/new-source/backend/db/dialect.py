"""Small deliberate SQL fragments for JSON text and dynamic named parameter lists."""

import re

_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)?\Z")
_KEY = re.compile(r"[A-Za-z_][A-Za-z_0-9]*\Z")


def bind_list(values, *, start=0):
    if type(start) is not int or start < 0:
        raise ValueError("Invalid parameter offset")
    # Used only by positive IN predicates. PostgreSQL rejects IN (); IN (NULL) matches no rows on both dialects.
    return ",".join(":p" + str(number) for number in range(start, start + len(values))) or "NULL"


def json_text(db, column, key):
    if not _IDENTIFIER.fullmatch(column) or not _KEY.fullmatch(key):
        raise ValueError("Invalid JSON projection identifier")
    if getattr(db, "dialect", "sqlite") == "postgresql":
        return "(CAST(" + column + " AS JSONB)->>'" + key + "')"
    return "json_extract(" + column + ",'$." + key + "')"
