from __future__ import annotations

from typing import Any, Dict, List, Optional


class FakeQuery:
    """In-memory mimic of supabase-py's query builder for tests."""

    def __init__(self, table: "FakeTable") -> None:
        self._table = table
        self._filters: list[tuple[str, Any]] = []
        self._limit: Optional[int] = None
        self._op: Optional[str] = None
        self._payload: Any = None

    def insert(self, records: Any) -> "FakeQuery":
        self._op = "insert"
        self._payload = records
        return self

    def update(self, payload: Dict[str, Any]) -> "FakeQuery":
        self._op = "update"
        self._payload = payload
        return self

    def select(self, *_: Any, **__: Any) -> "FakeQuery":
        self._op = "select"
        return self

    def eq(self, column: str, value: Any) -> "FakeQuery":
        self._filters.append((column, value))
        return self

    def limit(self, n: int) -> "FakeQuery":
        self._limit = n
        return self

    def execute(self) -> Any:
        class _Resp:
            def __init__(self, data: Any) -> None:
                self.data = data

        if self._op == "insert":
            records = (
                self._payload if isinstance(self._payload, list) else [self._payload]
            )
            for record in records:
                self._table.rows.append(dict(record))
            return _Resp(records)

        if self._op == "update":
            matched = self._apply_filters(self._table.rows)
            for row in matched:
                for k, v in self._payload.items():
                    if v == "now()":
                        continue
                    row[k] = v
            return _Resp(matched)

        # select
        matched = self._apply_filters(self._table.rows)
        if self._limit is not None:
            matched = matched[: self._limit]
        return _Resp([dict(r) for r in matched])

    def _apply_filters(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        result = rows
        for col, val in self._filters:
            result = [r for r in result if r.get(col) == val]
        return result


class FakeTable:
    def __init__(self) -> None:
        self.rows: List[Dict[str, Any]] = []

    def __call__(self) -> FakeQuery:
        return FakeQuery(self)


class FakeRpc:
    def __init__(self, handler) -> None:
        self._handler = handler
        self._params: Dict[str, Any] = {}

    def __call__(self, name: str, params: Dict[str, Any]) -> "FakeRpc":
        self._params = params
        self._name = name
        return self

    def execute(self) -> Any:
        class _Resp:
            def __init__(self, data: Any) -> None:
                self.data = data

        return _Resp(self._handler(self._params))


class FakeSupabaseClient:
    def __init__(self) -> None:
        self._tables: Dict[str, FakeTable] = {}
        self._rpc_handlers: Dict[str, Any] = {}

    def table(self, name: str) -> FakeQuery:
        if name not in self._tables:
            self._tables[name] = FakeTable()
        return FakeQuery(self._tables[name])

    def rows(self, name: str) -> List[Dict[str, Any]]:
        return self._tables.setdefault(name, FakeTable()).rows

    def register_rpc(self, name: str, handler) -> None:
        self._rpc_handlers[name] = handler

    def rpc(self, name: str, params: Dict[str, Any]):
        handler = self._rpc_handlers.get(name, lambda p: [])
        rpc = FakeRpc(handler)
        return rpc(name, params)


class FakeEmbeddings:
    def __init__(self, dim: int = 1536) -> None:
        self.dim = dim
        self.calls: list[list[str]] = []

    async def create(self, *, model: str, input: List[str]) -> Any:
        self.calls.append(list(input))

        class _Item:
            def __init__(self, v: list[float]) -> None:
                self.embedding = v

        class _Resp:
            def __init__(self, items: list[_Item]) -> None:
                self.data = items

        return _Resp([_Item([float((i + 1) % 100) / 100] * self.dim) for i in range(len(input))])


class FakeOpenAIClient:
    def __init__(self) -> None:
        self.embeddings = FakeEmbeddings()
