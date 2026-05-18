"""TTL 기반 URL 캐시.

원본 ``bot.py`` 의 ``url_cache`` 전역 딕셔너리 + 만료 로직을 클래스로 캡슐화.
"""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass(frozen=True)
class CachedEntry:
    url: str
    title: str | None
    thumbnail: str | None
    timestamp: float


class UrlCache:
    def __init__(self, ttl_seconds: int = 3600) -> None:
        self._ttl = ttl_seconds
        self._store: dict[str, CachedEntry] = {}

    def __len__(self) -> int:
        return len(self._store)

    def get(self, video_id: str) -> CachedEntry | None:
        if not video_id:
            return None
        entry = self._store.get(video_id)
        if entry is None:
            return None
        if time.time() - entry.timestamp >= self._ttl:
            self._store.pop(video_id, None)
            return None
        return entry

    def put(self, video_id: str, url: str, title: str | None, thumbnail: str | None) -> None:
        if not video_id:
            return
        self._store[video_id] = CachedEntry(
            url=url, title=title, thumbnail=thumbnail, timestamp=time.time()
        )

    def cleanup(self) -> int:
        now = time.time()
        expired = [k for k, v in self._store.items() if now - v.timestamp >= self._ttl]
        for key in expired:
            self._store.pop(key, None)
        return len(expired)
