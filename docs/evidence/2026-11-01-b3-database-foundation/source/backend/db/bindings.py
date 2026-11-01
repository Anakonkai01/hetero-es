"""Named bindings and positional-call compatibility, independent of database SQL dialect."""

from collections.abc import Mapping
import re

_DOLLAR_QUOTE = re.compile(r"\$(?:[A-Za-z_][A-Za-z_0-9]*)?\$")
_PARAMETER = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")


def _named_statement(statement):
    parts, names = [], set()
    position, positional = 0, 0
    while position < len(statement):
        char = statement[position]
        if statement.startswith("--", position):
            end = statement.find("\n", position)
            end = len(statement) if end < 0 else end
            parts.append(statement[position:end])
            position = end
            continue
        if statement.startswith("/*", position):
            end = statement.find("*/", position + 2)
            end = len(statement) if end < 0 else end + 2
            parts.append(statement[position:end])
            position = end
            continue
        if char in {"'", '"'}:
            start, quote = position, char
            position += 1
            while position < len(statement):
                if statement[position] == quote:
                    position += 1
                    if position < len(statement) and statement[position] == quote:
                        position += 1
                        continue
                    break
                position += 1
            parts.append(statement[start:position])
            continue
        if char == "$" and (match := _DOLLAR_QUOTE.match(statement, position)):
            delimiter = match.group()
            end = statement.find(delimiter, match.end())
            end = len(statement) if end < 0 else end + len(delimiter)
            parts.append(statement[position:end])
            position = end
            continue
        if char == "?":
            parts.append(":p" + str(positional))
            positional += 1
            position += 1
            continue
        if char == ":" and (position == 0 or statement[position - 1] not in {":", "\\"}):
            if match := _PARAMETER.match(statement, position + 1):
                names.add(match.group())
                parts.append(":" + match.group())
                position = match.end()
                continue
        parts.append(char)
        position += 1
    if positional and names:
        raise ValueError("Mixed SQL parameter styles")
    return "".join(parts), positional, names


def bind_parameters(statement, parameters=()):
    """Return named SQL and bindings without interpolating values or translating dialect-specific SQL.

    Repositories use named SQL. Positional compatibility also supports existing direct database callers during the
    migration. Python bools retain the original SQLite integer-column representation on PostgreSQL.
    """
    sql, positional, names = _named_statement(statement)
    if isinstance(parameters, Mapping):
        if positional or names != set(parameters):
            raise ValueError("SQL parameters do not match placeholders")
        values = parameters
    else:
        if parameters is None:
            parameters = ()
        if isinstance(parameters, (str, bytes, bytearray)):
            raise ValueError("SQL parameters must be a mapping or value sequence")
        values = {"p" + str(index): value for index, value in enumerate(parameters)}
        expected = {"p" + str(index) for index in range(positional)} if positional else names
        if set(values) != expected:
            raise ValueError("SQL parameters do not match placeholders")
    return sql, {name: int(value) if isinstance(value, bool) else value for name, value in values.items()}
