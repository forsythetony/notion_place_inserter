"""Run-scoped shared cache for pipeline step communication."""

from __future__ import annotations

from typing import Any


class RunScopedCache:
    """
    Shared cache for a single run. Pipelines can write and read.
    Isolated to the run; never shared across jobs or users.
    """

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def __contains__(self, key: str) -> bool:
        return key in self._data
