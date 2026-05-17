"""yt-dlp 비동기 래퍼.

기존 ``bot.py`` 의 검색/URL 재추출/병렬 prefetch 로직을 응집도 있게 옮김.
중복된 ydl_opts 도 한 곳에서 빌드.
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from typing import Any, Iterable, Optional

import yt_dlp

from ..core.cache import UrlCache
from ..core.config import Settings

log = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _base_opts(settings: Settings) -> dict[str, Any]:
    return {
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
        "retries": 3,
        "user_agent": _USER_AGENT,
        "referer": "https://www.youtube.com/",
        "extractor_args": {
            "youtube": {
                "skip": ["dash", "hls"],
                "player_skip": ["configs"],
                "player_client": ["android", "web"],
            }
        },
        "js_runtimes": {"node": {"path": settings.node_path}},
        "remote_components": ["ejs:github"],
        "ffmpeg_location": settings.ffmpeg_path,
    }


def _search_opts(settings: Settings) -> dict[str, Any]:
    opts = _base_opts(settings)
    opts.update(
        {
            "format": "bestaudio[acodec=opus]/bestaudio/best",
            "default_search": "ytsearch",
            "noplaylist": True,
            "ignoreerrors": True,
            "youtube_include_dash_manifest": False,
        }
    )
    return opts


def _fresh_opts(settings: Settings) -> dict[str, Any]:
    opts = _base_opts(settings)
    opts.update(
        {
            "format": "bestaudio[acodec=opus]/bestaudio/best",
            "noplaylist": True,
        }
    )
    return opts


def _generic_opts(settings: Settings) -> dict[str, Any]:
    opts = _base_opts(settings)
    opts.update(
        {
            "format": "bestaudio/best",
            "postprocessors": [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
            ],
            "youtube_include_dash_manifest": False,
            "fragment_retries": 5,
            "extractor_retries": 5,
            "http_chunk_size": 10 * 1024 * 1024,
        }
    )
    return opts


def _playlist_flat_opts(settings: Settings) -> dict[str, Any]:
    opts = _base_opts(settings)
    opts.update({"extract_flat": True, "noplaylist": False})
    return opts


@dataclass(frozen=True)
class YoutubeTrack:
    url: str
    title: str
    thumbnail: Optional[str]
    video_id: Optional[str]


def extract_video_id_from_url(url: str) -> Optional[str]:
    if not url:
        return None
    if "youtube.com/watch?v=" in url:
        try:
            return url.split("v=", 1)[1].split("&", 1)[0]
        except IndexError:
            return None
    if "youtu.be/" in url:
        try:
            return url.split("youtu.be/", 1)[1].split("?", 1)[0]
        except IndexError:
            return None
    return None


def _extract_search_sync(opts: dict[str, Any], query: str) -> Optional[dict[str, Any]]:
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"ytsearch:{query}", download=False)
        if not info or "entries" not in info or not info["entries"]:
            return None
        first = info["entries"][0]
        if not first or "url" not in first or "title" not in first:
            return None
        return {
            "url": first["url"],
            "title": first["title"],
            "thumbnail": first.get("thumbnail"),
            "id": first.get("id"),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("yt-dlp 검색 오류: %s", exc)
        return None


def _extract_fresh_sync(opts: dict[str, Any], target: str) -> Optional[dict[str, Any]]:
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(target, download=False)
        if not info or "url" not in info:
            return None
        return {
            "url": info["url"],
            "title": info.get("title"),
            "thumbnail": info.get("thumbnail"),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("yt-dlp 추출 오류: %s", exc)
        return None


def _extract_video_id_sync(opts: dict[str, Any], url: str) -> Optional[str]:
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        return info.get("id") if info else None
    except Exception as exc:  # noqa: BLE001
        log.warning("video_id 추출 실패: %s", exc)
        return None


def _extract_generic_sync(opts: dict[str, Any], url: str) -> dict[str, Any]:
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return info or {}


def _extract_playlist_meta_sync(opts: dict[str, Any], url: str) -> dict[str, Any]:
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        return info or {}
    except Exception as exc:  # noqa: BLE001
        log.debug("플레이리스트 메타 추출 실패(무시): %s", exc)
        return {}


class YoutubeService:
    """주 봇 스레드를 막지 않도록 yt-dlp 작업을 프로세스 풀에서 실행."""

    def __init__(self, settings: Settings, cache: UrlCache, max_workers: int = 2) -> None:
        self._settings = settings
        self._cache = cache
        self._executor = ProcessPoolExecutor(max_workers=max_workers)

    @property
    def cache(self) -> UrlCache:
        return self._cache

    def shutdown(self) -> None:
        try:
            self._executor.shutdown(wait=False, cancel_futures=True)
        except Exception as exc:  # noqa: BLE001
            log.warning("yt-dlp executor 종료 오류: %s", exc)

    async def search(self, query: str, retries: int = 3) -> Optional[YoutubeTrack]:
        opts = _search_opts(self._settings)
        loop = asyncio.get_running_loop()
        for attempt in range(retries):
            try:
                result = await asyncio.wait_for(
                    loop.run_in_executor(self._executor, _extract_search_sync, opts, query),
                    timeout=30.0,
                )
            except asyncio.TimeoutError:
                log.warning("YouTube 검색 타임아웃 (%s/%s): %s", attempt + 1, retries, query)
                continue
            if not result:
                continue
            video_id = result.get("id") or extract_video_id_from_url(result["url"])
            if video_id:
                self._cache.put(
                    video_id, result["url"], result["title"], result.get("thumbnail")
                )
            return YoutubeTrack(
                url=result["url"],
                title=result["title"],
                thumbnail=result.get("thumbnail"),
                video_id=video_id,
            )
        return None

    async def fresh_url(self, video_id_or_url: str, retries: int = 3) -> Optional[YoutubeTrack]:
        opts = _fresh_opts(self._settings)
        target = (
            video_id_or_url
            if video_id_or_url.startswith("http")
            else f"https://www.youtube.com/watch?v={video_id_or_url}"
        )
        loop = asyncio.get_running_loop()
        for attempt in range(retries):
            try:
                result = await asyncio.wait_for(
                    loop.run_in_executor(self._executor, _extract_fresh_sync, opts, target),
                    timeout=30.0,
                )
            except asyncio.TimeoutError:
                log.warning("URL 재추출 타임아웃 (%s/%s)", attempt + 1, retries)
                if attempt < retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                return None
            if not result:
                if attempt < retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                return None
            video_id = extract_video_id_from_url(target) or extract_video_id_from_url(result["url"])
            return YoutubeTrack(
                url=result["url"],
                title=result.get("title") or "",
                thumbnail=result.get("thumbnail"),
                video_id=video_id,
            )
        return None

    async def extract_video_id(self, url: str) -> Optional[str]:
        opts = _base_opts(self._settings)
        loop = asyncio.get_running_loop()
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(self._executor, _extract_video_id_sync, opts, url),
                timeout=20.0,
            )
        except asyncio.TimeoutError:
            log.warning("video_id 추출 타임아웃: %s", url)
            return None

    async def extract_info(self, url: str) -> dict[str, Any]:
        """단일 URL/플레이리스트 정보 추출 (.play 의 URL 입력 분기용)."""

        loop = asyncio.get_running_loop()
        opts = _generic_opts(self._settings)
        return await asyncio.wait_for(
            loop.run_in_executor(self._executor, _extract_generic_sync, opts, url),
            timeout=60.0,
        )

    async def extract_playlist_meta(self, url: str) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        opts = _playlist_flat_opts(self._settings)
        return await asyncio.wait_for(
            loop.run_in_executor(self._executor, _extract_playlist_meta_sync, opts, url),
            timeout=30.0,
        )

    async def prefetch_many(
        self, tracks: Iterable[dict[str, Any]], max_concurrent: int = 3
    ) -> list[tuple[int, YoutubeTrack]]:
        sem = asyncio.Semaphore(max_concurrent)
        track_list = list(tracks)

        async def _one(idx: int, track: dict[str, Any]) -> Optional[tuple[int, YoutubeTrack]]:
            async with sem:
                await asyncio.sleep(0)
                yt = await self.search(f"{track['name']} {track['artist']}")
                if yt is None:
                    return None
                return idx, yt

        results = await asyncio.gather(
            *[_one(i, t) for i, t in enumerate(track_list)], return_exceptions=True
        )
        success: list[tuple[int, YoutubeTrack]] = []
        for item in results:
            if isinstance(item, Exception) or item is None:
                continue
            success.append(item)
        success.sort(key=lambda pair: pair[0])
        return success
