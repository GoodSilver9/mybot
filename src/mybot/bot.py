"""봇 클래스 + 부팅 로직."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

import discord
from discord.ext import commands

from .core.cache import UrlCache
from .core.config import Settings, inject_tool_paths, load_settings
from .core.http import HttpSessionManager
from .core.logger import setup_logging
from .core.state import GuildStateRegistry
from .services.deepseek import DeepSeekService
from .services.spotify import SpotifyService
from .services.youtube import YoutubeService

log = logging.getLogger(__name__)


class MusicBot(commands.Bot):
    """전역 상태/서비스를 봇 인스턴스에 부착해 Cog 에서 접근."""

    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(
            command_prefix=settings.command_prefix,
            intents=intents,
            case_insensitive=settings.case_insensitive,
        )
        # discord.py 의 voice timeout 호환 유지
        discord.voice_client.VoiceClient.timeout = settings.voice_timeout  # type: ignore[attr-defined]

        self.settings: Settings = settings
        self.state: GuildStateRegistry = GuildStateRegistry()
        self.http_session: HttpSessionManager = HttpSessionManager()
        self.url_cache: UrlCache = UrlCache(ttl_seconds=settings.url_cache_ttl_seconds)
        self.youtube: YoutubeService = YoutubeService(settings, self.url_cache)
        self.spotify: SpotifyService = SpotifyService(settings, self.http_session)
        self.deepseek: DeepSeekService = DeepSeekService(settings, self.http_session)
        self._cleanup_task: Optional[asyncio.Task[None]] = None

    async def setup_hook(self) -> None:
        await self.load_extension("mybot.cogs.music")
        await self.load_extension("mybot.cogs.spotify_cog")
        await self.load_extension("mybot.cogs.language")
        self._cleanup_task = self.loop.create_task(self._periodic_cache_cleanup())
        log.info("Cog 로드 완료. 캐시 정리 태스크 시작.")

    async def _periodic_cache_cleanup(self) -> None:
        try:
            while not self.is_closed():
                await asyncio.sleep(600)
                removed = self.url_cache.cleanup()
                log.info(
                    "URL 캐시 정리: %s 항목 제거, 현재 %s 개", removed, len(self.url_cache)
                )
        except asyncio.CancelledError:
            pass

    async def on_ready(self) -> None:
        log.info("Logged in as %s", self.user)

    async def on_command_error(
        self, ctx: commands.Context, error: commands.CommandError
    ) -> None:
        if isinstance(error, commands.CommandNotFound):
            return
        log.exception("명령 실행 오류 (%s)", ctx.command, exc_info=error)

    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if member == self.user:
            return
        for vc in list(self.voice_clients):
            channel = vc.channel
            if channel is None:
                continue
            if len(channel.members) > 1:
                continue
            await asyncio.sleep(5)
            if vc.channel and len(vc.channel.members) == 1:
                try:
                    await vc.disconnect()
                except Exception as exc:  # noqa: BLE001
                    log.warning("자동 퇴장 실패: %s", exc)

    async def close(self) -> None:
        log.info("봇 종료 시작")
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
        for vc in list(self.voice_clients):
            try:
                if vc.is_playing():
                    vc.stop()
                await vc.disconnect()
            except Exception as exc:  # noqa: BLE001
                log.warning("음성 연결 정리 오류: %s", exc)
        self.youtube.shutdown()
        await self.http_session.close()
        await super().close()
        log.info("봇 종료 완료")


def create_bot(project_dir: Path | None = None) -> MusicBot:
    settings = load_settings(project_dir)
    inject_tool_paths(settings)
    setup_logging(settings.log_dir)
    return MusicBot(settings)


def run(project_dir: Path | None = None) -> None:
    bot = create_bot(project_dir)
    try:
        bot.run(bot.settings.discord_token, log_handler=None)
    except KeyboardInterrupt:
        log.info("키보드 인터럽트 - 종료")


__all__ = ["MusicBot", "create_bot", "run"]
