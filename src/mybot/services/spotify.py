"""Spotify Web API 클라이언트.

기존 ``spotify_integration.py`` 의 기능을 유지하되:
- 공유 ``aiohttp.ClientSession`` 사용
- ``aiohttp`` 세션을 매 요청마다 생성하던 부분 제거
- 추천 폴백 체인(seed_tracks → seed_artists → 검색)을 한 메서드로 정리
- 감정 키워드 표는 별도 모듈로 분리
"""

from __future__ import annotations

import asyncio
import base64
import logging
import random
import re
from typing import Any, Optional

import aiohttp

from ..core.config import Settings
from ..core.http import HttpSessionManager
from .emotion_map import EMOTION_QUERY, SIMILAR_WORDS

log = logging.getLogger(__name__)

_API = "https://api.spotify.com/v1"
_TOKEN_URL = "https://accounts.spotify.com/api/token"
_DEFAULT_MARKET = "KR"


def _normalize_track(track: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": track["name"],
        "artist": track["artists"][0]["name"],
        "album": track["album"]["name"],
        "external_url": track["external_urls"]["spotify"],
        "preview_url": track.get("preview_url"),
        "duration_ms": track["duration_ms"],
    }


class SpotifyService:
    def __init__(self, settings: Settings, http: HttpSessionManager) -> None:
        self._settings = settings
        self._http = http
        self._access_token: Optional[str] = None
        self._expires_at: float = 0.0
        self._token_lock = asyncio.Lock()

    @property
    def available(self) -> bool:
        return self._settings.spotify_available

    async def _ensure_token(self) -> bool:
        if not self.available:
            return False
        async with self._token_lock:
            loop = asyncio.get_running_loop()
            if self._access_token and loop.time() < self._expires_at:
                return True
            auth = base64.b64encode(
                f"{self._settings.spotify_client_id}:{self._settings.spotify_client_secret}".encode(
                    "ascii"
                )
            ).decode("ascii")
            headers = {
                "Authorization": f"Basic {auth}",
                "Content-Type": "application/x-www-form-urlencoded",
            }
            session = await self._http.get()
            try:
                async with session.post(
                    _TOKEN_URL, headers=headers, data={"grant_type": "client_credentials"}
                ) as resp:
                    if resp.status != 200:
                        log.error("Spotify 토큰 발급 실패: %s", resp.status)
                        return False
                    data = await resp.json()
                    self._access_token = data["access_token"]
                    self._expires_at = loop.time() + data["expires_in"] - 60
                    return True
            except aiohttp.ClientError as exc:
                log.error("Spotify 토큰 요청 오류: %s", exc)
                return False

    async def _auth_headers(self) -> Optional[dict[str, str]]:
        if not await self._ensure_token():
            return None
        return {"Authorization": f"Bearer {self._access_token}"}

    async def _get(self, path: str, params: dict[str, Any]) -> Optional[dict[str, Any]]:
        headers = await self._auth_headers()
        if headers is None:
            return None
        session = await self._http.get()
        try:
            async with session.get(f"{_API}{path}", headers=headers, params=params) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    log.warning("Spotify %s 실패 %s: %s", path, resp.status, body[:200])
                    return None
                return await resp.json()
        except aiohttp.ClientError as exc:
            log.error("Spotify %s 네트워크 오류: %s", path, exc)
            return None

    async def search_tracks(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        data = await self._get(
            "/search",
            {"q": query, "type": "track", "limit": limit, "market": _DEFAULT_MARKET},
        )
        if not data:
            return []
        return [_normalize_track(t) for t in data["tracks"]["items"]]

    async def _search_id(self, query: str, type_: str) -> Optional[str]:
        data = await self._get(
            "/search",
            {"q": query, "type": type_, "limit": 1, "market": _DEFAULT_MARKET},
        )
        if not data:
            return None
        bucket = f"{type_}s"
        items = data.get(bucket, {}).get("items", [])
        return items[0]["id"] if items else None

    async def get_similar_tracks(
        self, track_name: str, artist_name: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        track_id = await self._search_id(f"{track_name} {artist_name}", "track")
        if track_id:
            data = await self._get(
                "/recommendations",
                {"seed_tracks": track_id, "limit": limit, "market": _DEFAULT_MARKET},
            )
            if data:
                return [_normalize_track(t) for t in data["tracks"]]

        artist_id = await self._search_id(artist_name, "artist")
        if artist_id:
            data = await self._get(
                "/recommendations",
                {"seed_artists": artist_id, "limit": limit, "market": _DEFAULT_MARKET},
            )
            if data:
                return [_normalize_track(t) for t in data["tracks"]]

        for fallback_query in (
            f"{artist_name} similar",
            f"{artist_name} hits",
            f"{track_name} similar",
        ):
            result = await self.search_tracks(fallback_query, limit)
            if result:
                return result
        return []

    @staticmethod
    def _extract_playlist_id(url: str) -> Optional[str]:
        if not url:
            return None
        for pattern in (r"playlist/([a-zA-Z0-9]+)", r"playlist:([a-zA-Z0-9]+)"):
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        cleaned = url.replace("-", "").replace("_", "")
        if len(url) == 22 and cleaned.isalnum():
            return url
        return None

    async def get_playlist_tracks(
        self, playlist_url: str, limit: int = 10
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        playlist_id = self._extract_playlist_id(playlist_url)
        if not playlist_id:
            log.warning("플레이리스트 ID 추출 실패: %s", playlist_url)
            return [], {}

        meta = await self._get(f"/playlists/{playlist_id}", {})
        if not meta:
            return [], {}
        playlist_info = {
            "name": meta["name"],
            "description": meta.get("description", ""),
            "total_tracks": meta["tracks"]["total"],
            "external_url": meta["external_urls"]["spotify"],
            "owner": meta["owner"]["display_name"],
        }

        all_tracks: list[dict[str, Any]] = []
        offset = 0
        page_size = 100
        while True:
            page = await self._get(
                f"/playlists/{playlist_id}/tracks",
                {"limit": page_size, "offset": offset, "market": _DEFAULT_MARKET},
            )
            if not page:
                break
            items = page.get("items", [])
            for item in items:
                track = item.get("track")
                if not track or track.get("type") != "track":
                    continue
                all_tracks.append(_normalize_track(track))
            if len(items) < page_size:
                break
            offset += page_size

        if len(all_tracks) <= limit:
            selected = all_tracks
        else:
            selected = random.sample(all_tracks, limit)
        return selected, playlist_info

    async def emotion_recommend(self, text: str, limit: int = 5) -> list[dict[str, Any]]:
        if not await self._ensure_token():
            return []
        text_lower = text.lower()
        for emotion, query in EMOTION_QUERY.items():
            if emotion in text_lower:
                log.debug("정확한 감정 매칭: %s", emotion)
                return await self.search_tracks(query, limit)
        for similar_word, emotions in SIMILAR_WORDS.items():
            if similar_word in text_lower:
                emotion = emotions[0]
                query = EMOTION_QUERY.get(emotion)
                if query:
                    log.debug("유사어 매칭: %s → %s", similar_word, emotion)
                    return await self.search_tracks(query, limit)
        return await self.search_tracks("korean pop", limit)

    async def warm_up(self) -> bool:
        return await self._ensure_token()


__all__ = ["SpotifyService"]
