from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Iterable, Optional

@dataclass
class CacheEntry:
    value: Any
    expires_at: float

class TTLCache:
    def __init__(self, max_size: int = 2048, default_ttl: int = 60):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._data: OrderedDict[str, CacheEntry] = OrderedDict()

    def get(self, key: str) -> Any | None:
        entry = self._data.get(key)
        if entry is None:
            return None
        if entry.expires_at < time.time():
            self._data.pop(key, None)
            return None
        self._data.move_to_end(key)
        return entry.value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> Any:
        self._data[key] = CacheEntry(value=value, expires_at=time.time() + (self.default_ttl if ttl is None else ttl))
        self._data.move_to_end(key)
        while len(self._data) > self.max_size:
            self._data.popitem(last=False)
        return value

    def clear(self) -> None:
        self._data.clear()

    def invalidate_prefixes(self, prefixes: Iterable[str]) -> None:
        prefixes = tuple(prefixes)
        for key in list(self._data.keys()):
            if key.startswith(prefixes):
                self._data.pop(key, None)
