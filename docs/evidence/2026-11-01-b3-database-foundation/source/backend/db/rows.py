"""Repository rows preserve sqlite3.Row lookup/iteration while wrapping SQLAlchemy Core results."""


class Row:
    __slots__ = ("_keys", "_positions", "_values")

    def __init__(self, keys, values):
        self._keys, self._values = tuple(keys), tuple(values)
        if len(self._keys) != len(self._values):
            raise ValueError("Database row metadata does not match its values")
        self._positions = {}
        for index, key in enumerate(self._keys):
            self._positions.setdefault(key.lower() if key.isascii() else key, index)

    def __getitem__(self, key):
        if isinstance(key, str):
            try:
                index = self._positions[key.lower() if key.isascii() else key]
            except KeyError:
                raise IndexError("No item with that key") from None
            return self._values[index]
        return self._values[key]

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)

    def keys(self):
        return list(self._keys)


class Result:
    def __init__(self, cursor_result):
        self._result = cursor_result
        self._keys = tuple(cursor_result.keys()) if cursor_result.returns_rows else ()
        self._returns_rows = cursor_result.returns_rows

    @property
    def rowcount(self):
        return self._result.rowcount

    @property
    def lastrowid(self):
        return self._result.lastrowid

    def keys(self):
        return list(self._keys)

    def fetchone(self):
        if not self._returns_rows:
            return None
        values = self._result.fetchone()
        return None if values is None else Row(self._keys, values)

    def fetchall(self):
        if not self._returns_rows:
            return []
        return [Row(self._keys, values) for values in self._result.fetchall()]

    def __iter__(self):
        while (row := self.fetchone()) is not None:
            yield row

    def close(self):
        self._result.close()
