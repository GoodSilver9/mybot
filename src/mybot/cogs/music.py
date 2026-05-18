"""핵심 음악 명령: play / pause / resume / skip / stop / queue / clear / forceplay."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import discord
from discord.ext import commands

from ..core.state import GuildState, Track
from ..services.audio import build_source
from ..services.youtube import YoutubeService, YoutubeTrack, extract_video_id_from_url
from ..ui.player import MusicControlView, build_player_embed

log = logging.getLogger(__name__)


def safe_channel_name(channel: Optional[discord.abc.GuildChannel]) -> str:
    if channel is None:
        return "Unknown Channel"
    name = getattr(channel, "name", None)
    if not name:
        return "Unknown Channel"
    return name.encode("utf-8", errors="ignore").decode("utf-8")


async def ensure_voice(ctx: commands.Context) -> Optional[discord.VoiceClient]:
    voice = ctx.voice_client
    if voice and voice.is_connected():
        return voice

    if not ctx.author.voice:
        await ctx.send("```먼저 음성 채널에 접속해주세요.```")
        return None

    channel = ctx.author.voice.channel
    name = safe_channel_name(channel)
    log.info("음성 채널 연결 시도: %s (id=%s)", name, getattr(channel, "id", "?"))

    if ctx.voice_client:
        try:
            await ctx.voice_client.disconnect()
            await asyncio.sleep(1)
        except Exception as exc:  # noqa: BLE001
            log.debug("기존 음성 연결 정리 오류(무시): %s", exc)

    last_error: Optional[BaseException] = None
    for attempt in range(3):
        try:
            return await channel.connect()
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            log.warning("음성 연결 실패 %s/3: %s", attempt + 1, exc)
            await asyncio.sleep(5 if "4006" in str(exc) else 2)

    if last_error and ("4006" in str(last_error) or "ConnectionClosed" in str(last_error)):
        await ctx.send(
            "```❌ 음성 채널 연결에 실패했습니다.\n\n"
            "가능한 원인:\n• 네트워크 연결 문제\n• Discord 서버 과부하\n• 봇 권한 부족\n\n"
            "잠시 후 다시 시도해주세요.```"
        )
    else:
        await ctx.send(
            f"```❌ 음성 채널 연결 중 오류가 발생했습니다.\n오류: {str(last_error)[:100]}...```"
        )
    return None


async def send_player_message(
    ctx: commands.Context,
    state: GuildState,
    *,
    title: str,
    thumbnail_url: Optional[str],
) -> None:
    embed = build_player_embed(
        title=title,
        thumbnail_url=thumbnail_url,
        queue_count=len(state.queue) + len(state.playlist_queue),
    )
    view = MusicControlView(ctx, state)

    if state.current_message is not None:
        try:
            await state.current_message.delete()
        except Exception:  # noqa: BLE001
            pass
    state.current_message = await ctx.send(embed=embed, view=view)


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @property
    def yt(self) -> YoutubeService:
        return self.bot.youtube  # type: ignore[attr-defined]

    def _state_for(self, ctx: commands.Context) -> GuildState:
        return self.bot.state.for_guild(ctx.guild.id)  # type: ignore[attr-defined]

    async def _start_playback(
        self,
        ctx: commands.Context,
        voice: discord.VoiceClient,
        track: YoutubeTrack,
    ) -> None:
        state = self._state_for(ctx)
        try:
            source = build_source(track.url, self.bot.settings.ffmpeg_options)  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001
            log.warning("FFmpeg 소스 생성 실패: %s", exc)
            await ctx.send(f"```음악 재생 중 오류가 발생했습니다.\n오류: {str(exc)[:100]}...```")
            return

        state.current_track = track.title
        state.current_thumbnail = track.thumbnail
        state.is_playing = True

        def _after(error: Optional[BaseException]) -> None:
            if error:
                log.warning("재생 후 콜백 오류: %s", error)
            asyncio.run_coroutine_threadsafe(self.play_next(ctx), self.bot.loop)

        voice.play(source, after=_after)
        await send_player_message(
            ctx, state, title=track.title, thumbnail_url=track.thumbnail
        )

    @commands.command(aliases=["p"])
    async def play(self, ctx: commands.Context, *, search_or_url: Optional[str] = None) -> None:
        state = self._state_for(ctx)

        if state.auto_similar_mode:
            await ctx.send(
                "```⚠️ 자동 비슷한 곡 재생 모드가 활성화되어 있습니다.\n"
                "다른 곡을 추가하면 자동 재생이 중단될 수 있습니다.\n\n사용법:\n"
                ".autostop - 자동 모드 중단 후 곡 추가\n.forceplay - 자동 모드 무시하고 곡 추가\n"
                ".stop - 모든 재생 중단```"
            )
            return

        if state.disconnect_task and not state.disconnect_task.done():
            state.disconnect_task.cancel()
        state.disconnect_task = None

        voice = await ensure_voice(ctx)
        if voice is None:
            return

        if voice.is_paused():
            voice.resume()
            await ctx.send(f"```{ctx.author.mention} 일시정지된 음악을 다시 재생합니다.```")
            return

        if not search_or_url:
            await ctx.send("```URL 또는 검색어를 입력해주세요.```")
            return

        await self._enqueue_or_play(ctx, voice, search_or_url)

    async def _enqueue_or_play(
        self,
        ctx: commands.Context,
        voice: discord.VoiceClient,
        search_or_url: str,
    ) -> None:
        state = self._state_for(ctx)

        if search_or_url.startswith("http"):
            await ctx.send("```🔄 URL 정보를 가져오는 중...```", delete_after=10)
            try:
                meta = await self.yt.extract_playlist_meta(search_or_url)
            except Exception as exc:  # noqa: BLE001
                log.debug("플레이리스트 메타 조회 실패: %s", exc)
                meta = {}

            if meta and "entries" in meta:
                entries = [e for e in meta["entries"] if e]
                if len(entries) > 10:
                    await ctx.send(
                        "```플레이리스트는 최대 10개의 곡까지만 지원합니다. 더 적은 수의 곡을 선택해주세요.```",
                        delete_after=10,
                    )
                    return
                if len(entries) > 1:
                    await ctx.send(
                        f"```플레이리스트에서 {len(entries)}개의 곡을 추가합니다...```",
                        delete_after=10,
                    )

            try:
                info = await self.yt.extract_info(search_or_url)
            except Exception as exc:  # noqa: BLE001
                await ctx.send(f"```음악을 재생할 수 없습니다. 오류: {exc}```")
                return

            if "entries" in info:
                await self._handle_playlist_entries(ctx, voice, info["entries"])
                return

            url = info.get("url")
            if not url:
                await ctx.send("```검색 결과가 없습니다.```")
                return
            track = YoutubeTrack(
                url=url,
                title=info.get("title") or "알 수 없는 제목",
                thumbnail=info.get("thumbnail"),
                video_id=info.get("id"),
            )
        else:
            yt = await self.yt.search(search_or_url)
            if yt is None:
                await ctx.send("```검색 결과가 없습니다.```")
                return
            video_id = yt.video_id or extract_video_id_from_url(yt.url)
            track = YoutubeTrack(
                url=yt.url, title=yt.title, thumbnail=yt.thumbnail, video_id=video_id
            )

        if voice.is_playing():
            state.queue.append(
                Track(
                    url=track.url,
                    title=track.title,
                    thumbnail=track.thumbnail,
                    video_id=track.video_id,
                )
            )
            await ctx.send(
                f"```✅ '{track.title}'가 대기열에 추가되었습니다! (대기열: {len(state.queue)}개)```",
                delete_after=3,
            )
            if state.current_track:
                await send_player_message(
                    ctx,
                    state,
                    title=state.current_track,
                    thumbnail_url=state.current_thumbnail,
                )
            return

        await self._start_playback(ctx, voice, track)

    async def _handle_playlist_entries(
        self,
        ctx: commands.Context,
        voice: discord.VoiceClient,
        entries: list[dict],
    ) -> None:
        state = self._state_for(ctx)
        added = 0
        for entry in entries:
            if not entry:
                continue
            url = entry.get("url")
            if not url:
                continue
            title = entry.get("title", "알 수 없는 제목")
            thumbnail = entry.get("thumbnail")
            video_id = entry.get("id")
            if voice.is_playing():
                state.queue.append(
                    Track(url=url, title=title, thumbnail=thumbnail, video_id=video_id)
                )
                added += 1
            else:
                track = YoutubeTrack(
                    url=url, title=title, thumbnail=thumbnail, video_id=video_id
                )
                await self._start_playback(ctx, voice, track)
                added += 1
        if added:
            await ctx.send(
                f"```플레이리스트에서 {added}개의 곡을 추가했습니다!```", delete_after=5
            )
        else:
            await ctx.send("```플레이리스트에서 곡을 추가할 수 없습니다.```", delete_after=5)

    async def play_next(self, ctx: commands.Context) -> None:
        state = self._state_for(ctx)
        voice = ctx.voice_client

        if not state.queue:
            if state.playlist_queue:
                state.queue.append(state.playlist_queue.pop(0))
            elif state.auto_similar_queue:
                auto = state.auto_similar_queue.pop(0)
                state.queue.append(
                    Track(
                        url=auto.url,
                        title=auto.title,
                        thumbnail=auto.thumbnail,
                        video_id=None,
                    )
                )
                state.current_info = auto.info
            else:
                state.is_playing = False
                state.current_track = None
                await ctx.send("```재생할 곡이 더 이상 없습니다.```")
                return

        if voice is None or not voice.is_connected():
            await ctx.send("```음성 연결이 끊어졌습니다. 다시 연결해주세요.```")
            return

        if voice.is_playing():
            log.debug("이미 재생 중 — play_next 스킵")
            return

        item = state.queue.pop(0)
        track = await self._refresh_url(item)
        if track is None:
            await ctx.send(f"```⚠️ '{item.title}' 재생 실패\n다음 곡으로 넘어갑니다.```")
            await asyncio.sleep(0.5)
            await self.play_next(ctx)
            return

        await self._start_playback(ctx, voice, track)

    async def _refresh_url(self, item: Track) -> Optional[YoutubeTrack]:
        cache = self.yt.cache
        cached = cache.get(item.video_id) if item.video_id else None
        if cached:
            return YoutubeTrack(
                url=cached.url,
                title=cached.title or item.title,
                thumbnail=cached.thumbnail or item.thumbnail,
                video_id=item.video_id,
            )

        if item.video_id:
            fresh = await self.yt.fresh_url(item.video_id)
            if fresh:
                cache.put(item.video_id, fresh.url, fresh.title or item.title, fresh.thumbnail)
                return fresh

        if item.title:
            yt = await self.yt.search(item.title)
            if yt:
                return yt

        return None

    @commands.command()
    async def q(self, ctx: commands.Context) -> None:
        state = self._state_for(ctx)
        embed = discord.Embed(title="📋 재생 목록", color=0x5DADE2)

        embed.add_field(
            name="🎵 현재 재생 중",
            value=f"`{state.current_track}`" if state.current_track else "없음",
            inline=False,
        )

        if state.queue:
            head = state.queue[:10]
            lines = [f"`{i + 1}. {t.title}`" for i, t in enumerate(head)]
            if len(state.queue) > 10:
                lines.append(f"... 그리고 {len(state.queue) - 10}개 더")
            embed.add_field(name="📋 대기 중인 곡들", value="\n".join(lines), inline=False)
        else:
            embed.add_field(name="📋 대기 중인 곡들", value="없음", inline=False)

        if state.auto_similar_queue:
            head = state.auto_similar_queue[:5]
            lines = [f"`{i + 1}. {t.title}`" for i, t in enumerate(head)]
            if len(state.auto_similar_queue) > 5:
                lines.append(f"... 그리고 {len(state.auto_similar_queue) - 5}개 더")
            embed.add_field(name="🔄 자동 비슷한 곡 대기열", value="\n".join(lines), inline=False)
        else:
            embed.add_field(
                name="🔄 자동 비슷한 곡 대기열",
                value="없음 (`.auto` 명령어로 활성화)",
                inline=False,
            )

        embed.set_footer(text="🎶 Discord Music Bot")
        await ctx.send(embed=embed)

    @commands.command()
    async def clear(self, ctx: commands.Context) -> None:
        state = self._state_for(ctx)
        if state.queue:
            state.queue.clear()
            await ctx.send("```재생 목록이 비워졌습니다.```")
        else:
            await ctx.send("```재생 목록이 이미 비어 있습니다.```")

    @commands.command()
    async def stop(self, ctx: commands.Context) -> None:
        state = self._state_for(ctx)
        state.reset()
        voice = ctx.voice_client
        if voice and voice.is_connected():
            await voice.disconnect()
            await ctx.send(
                "```재생이 중단되었습니다. 음성 채널에서 나갑니다.\n"
                "자동 비슷한 곡 재생 모드도 비활성화되었습니다.```"
            )
        else:
            await ctx.send("```봇이 음성 채널에 연결되어 있지 않습니다.```")

    @commands.command()
    async def pause(self, ctx: commands.Context) -> None:
        voice = ctx.voice_client
        if voice and voice.is_playing():
            voice.pause()
            await ctx.send(f"```{ctx.author.mention} 플레이어를 일시정지했습니다.```")
        else:
            await ctx.send(f"```{ctx.author.mention} 현재 재생 중인 곡이 없습니다.```")

    @commands.command()
    async def resume(self, ctx: commands.Context) -> None:
        voice = ctx.voice_client
        if voice and voice.is_paused():
            voice.resume()
            await ctx.send(f"```{ctx.author.mention} 음악을 계속 재생합니다.```")
        else:
            await ctx.send(f"```{ctx.author.mention} 현재 일시정지된 곡이 없습니다.```")

    @commands.command()
    async def skip(self, ctx: commands.Context) -> None:
        voice = ctx.voice_client
        if voice and voice.is_playing():
            voice.stop()
            await ctx.send("```다음 곡으로 넘어갑니다.```")
        else:
            await ctx.send("```현재 재생 중인 곡이 없습니다.```")

    @commands.command(name="forceplay")
    async def force_play(
        self, ctx: commands.Context, *, search_or_url: Optional[str] = None
    ) -> None:
        if not search_or_url:
            await ctx.send(
                "```사용법: .forceplay <URL 또는 검색어>\n예시: .forceplay BTS Dynamite```"
            )
            return
        state = self._state_for(ctx)
        state.auto_similar_mode = False
        state.auto_similar_queue.clear()
        await ctx.send(
            "```⚠️ 자동 비슷한 곡 재생 모드가 비활성화되었습니다.\n일반 재생 모드로 전환합니다.```"
        )
        await self.play(ctx, search_or_url=search_or_url)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Music(bot))
