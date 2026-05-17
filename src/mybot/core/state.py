"""길드별 재생 상태.

기존 ``bot.py`` 의 모든 전역(queue / playlist_queue / current_track …)을 길드 단위로 격리.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Track:
    url: str
    title: str
    thumbnail: Optional[str] = None
    video_id: Optional[str] = None


@dataclass
class AutoTrack:
    url: str
    title: str
    thumbnail: Optional[str]
    info: dict[str, Any]


@dataclass
class GuildState:
    guild_id: int
    queue: list[Track] = field(default_factory=list)
    playlist_queue: list[Track] = field(default_factory=list)
    auto_similar_queue: list[AutoTrack] = field(default_factory=list)
    current_track: Optional[str] = None
    current_thumbnail: Optional[str] = None
    current_info: Optional[dict[str, Any]] = None
    is_playing: bool = False
    auto_similar_mode: bool = False
    shuffle_mode: bool = False
    current_message: Any = None  # discord.Message
    disconnect_task: Optional[asyncio.Task[Any]] = None
    last_spotify_recommendations: list[dict[str, Any]] = field(default_factory=list)

    def reset(self) -> None:
        self.queue.clear()
        self.playlist_queue.clear()
        self.auto_similar_queue.clear()
        self.current_track = None
        self.current_thumbnail = None
        self.current_info = None
        self.is_playing = False
        self.auto_similar_mode = False
        if self.disconnect_task and not self.disconnect_task.done():
            self.disconnect_task.cancel()
        self.disconnect_task = None
        self.current_message = None

    def has_anything_queued(self) -> bool:
        return bool(self.queue or self.playlist_queue or self.auto_similar_queue)


class GuildStateRegistry:
    def __init__(self) -> None:
        self._store: dict[int, GuildState] = {}

    def for_guild(self, guild_id: int) -> GuildState:
        state = self._store.get(guild_id)
        if state is None:
            state = GuildState(guild_id=guild_id)
            self._store[guild_id] = state
        return state

    def drop(self, guild_id: int) -> None:
        self._store.pop(guild_id, None)

    def all_states(self) -> list[GuildState]:
        return list(self._store.values())
