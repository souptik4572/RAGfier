from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional


class FakeQuery:
    """In-memory mimic of supabase-py's query builder for tests."""

    def __init__(self, table: "FakeTable") -> None:
        self._table = table
        self._filters: list[tuple[str, str, Any]] = []
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

    def delete(self) -> "FakeQuery":
        self._op = "delete"
        return self

    def select(self, *_: Any, **__: Any) -> "FakeQuery":
        self._op = "select"
        return self

    def eq(self, column: str, value: Any) -> "FakeQuery":
        self._filters.append(("eq", column, value))
        return self

    def is_(self, column: str, value: Any) -> "FakeQuery":
        # Supabase uses is_("col", "null") to match NULL.
        self._filters.append(("is", column, value))
        return self

    def in_(self, column: str, values: Any) -> "FakeQuery":
        self._filters.append(("in", column, list(values)))
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
            stored: List[Dict[str, Any]] = []
            for record in records:
                row = dict(record)
                row.setdefault("id", str(uuid.uuid4()))
                self._table.rows.append(row)
                stored.append(row)
            return _Resp(stored)

        if self._op == "update":
            matched = self._apply_filters(self._table.rows)
            for row in matched:
                for k, v in self._payload.items():
                    if v == "now()":
                        continue
                    row[k] = v
            return _Resp(matched)

        if self._op == "delete":
            matched = self._apply_filters(self._table.rows)
            self._table.rows = [row for row in self._table.rows if row not in matched]
            return _Resp(matched)

        # select
        matched = self._apply_filters(self._table.rows)
        if self._limit is not None:
            matched = matched[: self._limit]
        return _Resp([dict(r) for r in matched])

    def _apply_filters(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        result = rows
        for op, col, val in self._filters:
            if op == "eq":
                result = [r for r in result if r.get(col) == val]
            elif op == "is":
                if val in ("null", None):
                    result = [r for r in result if r.get(col) is None]
                else:
                    result = [r for r in result if r.get(col) == val]
            elif op == "in":
                allowed = set(val)
                result = [r for r in result if r.get(col) in allowed]
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


class _FakeChoiceMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = _FakeChoiceMessage(content)


class _FakeChatCompletion:
    def __init__(self, content: str) -> None:
        self.choices = [_FakeChoice(content)]


class _FakeStreamDelta:
    def __init__(self, content: Optional[str]) -> None:
        self.content = content


class _FakeStreamChoice:
    def __init__(self, content: Optional[str]) -> None:
        self.delta = _FakeStreamDelta(content)


class _FakeStreamChunk:
    def __init__(self, content: Optional[str]) -> None:
        self.choices = [_FakeStreamChoice(content)]


class FakeAsyncStream:
    def __init__(self, tokens: List[str]) -> None:
        self._tokens = list(tokens)

    def __aiter__(self) -> "FakeAsyncStream":
        return self

    async def __anext__(self) -> _FakeStreamChunk:
        if not self._tokens:
            raise StopAsyncIteration
        return _FakeStreamChunk(self._tokens.pop(0))


class FakeChatCompletions:
    def __init__(self, response_text: str = "stub answer [SOURCE_1]") -> None:
        self.response_text = response_text
        self.stream_tokens: List[str] = ["Hello", " ", "world", " [SOURCE_1]"]
        self.calls: list[dict] = []

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if kwargs.get("stream"):
            return FakeAsyncStream(self.stream_tokens)
        return _FakeChatCompletion(self.response_text)


class FakeChat:
    def __init__(self, response_text: str = "stub answer [SOURCE_1]") -> None:
        self.completions = FakeChatCompletions(response_text)


class FakeAsyncOpenAIClient:
    def __init__(self, response_text: str = "stub answer [SOURCE_1]") -> None:
        self.embeddings = FakeEmbeddings()
        self.chat = FakeChat(response_text)
