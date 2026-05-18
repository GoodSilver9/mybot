"""Spotify 연동 명령: mind / sp / ps / similar / auto / autostop / playlist."""

from __future__ import annotations

import logging
from typing import Any, Optional

import discord
from discord.ext import commands

from ..core.state import AutoTrack, GuildState, Track
from ..services.spotify import SpotifyService
from ..services.youtube import YoutubeService, YoutubeTrack, extract_video_id_from_url
from ..ui.selector import run_track_selector
from .music import Music, ensure_voice, send_player_message

log = logging.getLogger(__name__)


def _duration_string(duration_ms: int) -> str:
    minutes = duration_ms // 60_000
    seconds = (duration_ms % 60_000) // 1000
    return f"{minutes}:{seconds:02d}"


def _build_track_embed(
    *, title: str, description: str, tracks: list[dict[str, Any]]
) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=0x5DADE2)
    for i, track in enumerate(tracks, 1):
        embed.add_field(
            name=f"{i}. {track['name']}",
            value=(
                f"🎤 {track['artist']}\n"
                f"💿 {track['album']}\n"
                f"⏱️ {_duration_string(track['duration_ms'])}\n"
                f"🔗 [Spotify에서 듣기]({track['external_url']})"
            ),
            inline=False,
        )
    return embed


class SpotifyCog(commands.Cog, name="Spotify"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @property
    def spotify(self) -> SpotifyService:
        return self.bot.spotify  # type: ignore[attr-defined]

    @property
    def yt(self) -> YoutubeService:
        return self.bot.youtube  # type: ignore[attr-defined]

    @property
    def music(self) -> Music:
        cog = self.bot.get_cog("Music")
        if cog is None:
            raise RuntimeError("Music cog 가 로드되어 있지 않습니다.")
        return cog  # type: ignore[return-value]

    def _state(self, ctx: commands.Context) -> GuildState:
        return self.bot.state.for_guild(ctx.guild.id)  # type: ignore[attr-defined]

    async def _require_spotify(self, ctx: commands.Context) -> bool:
        if not self.spotify.available:
            await ctx.send("```❌ Spotify API가 설정되지 않았습니다.```")
            return False
        return True

    async def _play_spotify_recommendation(
        self,
        ctx: commands.Context,
        recommendations: list[dict[str, Any]],
        track_index: int,
    ) -> None:
        if track_index >= len(recommendations):
            await ctx.send("```❌ 잘못된 번호입니다.```")
            return

        selected = recommendations[track_index]
        search_query = f"{selected['name']} {selected['artist']}"
        await ctx.send(f"```🎵 '{search_query}' 재생을 시작합니다!```", delete_after=5)

        yt = await self.yt.search(search_query)
        if yt is None:
            await ctx.send("```❌ YouTube에서 해당 곡을 찾을 수 없습니다.```")
            return

        voice = await ensure_voice(ctx)
        if voice is None:
            return

        state = self._state(ctx)
        track = YoutubeTrack(
            url=yt.url,
            title=yt.title,
            thumbnail=yt.thumbnail,
            video_id=yt.video_id or extract_video_id_from_url(yt.url),
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
            note = "(플레이리스트 재생 중)" if state.playlist_queue else f"(대기열: {len(state.queue)}개)"
            await ctx.send(
                f"```✅ '{track.title}'가 대기열에 추가되었습니다! {note}```",
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

        await self.music._start_playback(ctx, voice, track)  # type: ignore[attr-defined]
        state.current_info = {
            "name": selected["name"],
            "artist": selected["artist"],
            "album": selected["album"],
            "external_url": selected["external_url"],
            "duration_ms": selected["duration_ms"],
        }

    @commands.command(name="mind")
    async def mind(self, ctx: commands.Context, *, query: Optional[str] = None) -> None:
        if not await self._require_spotify(ctx):
            return
        if not query:
            await ctx.send(
                "```사용법: .mind <감정 또는 상황>\n예시: .mind 기분이 좋아\n예시: .mind 슬플 때 듣고 싶어```"
            )
            return

        await ctx.send("```🎵 Spotify에서 음악을 추천받는 중...```")
        try:
            recommendations = await self.spotify.emotion_recommend(query, limit=5)
        except Exception as exc:  # noqa: BLE001
            log.warning("emotion_recommend 오류: %s", exc)
            await ctx.send(f"```❌ Spotify 추천 중 오류가 발생했습니다: {exc}```")
            return

        if not recommendations:
            await ctx.send("```❌ 추천 음악을 찾을 수 없습니다.```")
            return

        state = self._state(ctx)
        state.last_spotify_recommendations = recommendations

        embed = _build_track_embed(
            title="🎵 Spotify 음악 추천",
            description=(
                f"'{query}'에 맞는 음악을 추천해드려요!\n\n"
                "**사용법:**\n✅ 자동 재생 (1번 곡)\n1️⃣~5️⃣ 번호 선택 (여러 개 선택 가능)\n"
                ".ps <번호> 명령어\n❌ 취소"
            ),
            tracks=recommendations,
        )
        message = await ctx.send(embed=embed)

        async def _play(idx: int) -> None:
            await self._play_spotify_recommendation(ctx, recommendations, idx)

        await run_track_selector(ctx=ctx, message=message, play_track=_play)

    @commands.command(name="sp")
    async def sp(self, ctx: commands.Context, *, query: Optional[str] = None) -> None:
        if not await self._require_spotify(ctx):
            return
        if not query:
            await ctx.send(
                "```사용법: .sp <검색어>\n예시: .sp 대부 ost\n예시: .sp BTS Dynamite```"
            )
            return

        await ctx.send("```🔍 Spotify에서 검색 중...```")
        try:
            tracks = await self.spotify.search_tracks(query, limit=5)
        except Exception as exc:  # noqa: BLE001
            log.warning("spotify search 오류: %s", exc)
            await ctx.send(f"```❌ Spotify 검색 중 오류가 발생했습니다: {exc}```")
            return

        if not tracks:
            await ctx.send("```❌ 검색 결과가 없습니다.```")
            return

        state = self._state(ctx)
        state.last_spotify_recommendations = tracks

        embed = _build_track_embed(
            title="🔍 Spotify 검색 결과",
            description=(
                f"'{query}' 검색 결과\n\n"
                "**사용법:**\n✅ 자동 재생 (1번 곡)\n1️⃣~5️⃣ 번호 선택 (여러 개 선택 가능)\n"
                ".ps <번호> 명령어\n❌ 취소"
            ),
            tracks=tracks,
        )
        message = await ctx.send(embed=embed)

        async def _play(idx: int) -> None:
            await self._play_spotify_recommendation(ctx, tracks, idx)

        await run_track_selector(ctx=ctx, message=message, play_track=_play)

    @commands.command(name="ps")
    async def ps(self, ctx: commands.Context, number: Optional[int] = None) -> None:
        state = self._state(ctx)
        recommendations = state.last_spotify_recommendations
        if not recommendations:
            await ctx.send("```❌ 먼저 .mind 또는 .sp 명령어로 추천을 받아주세요.```")
            return
        if number is None:
            await ctx.send(
                "```사용법: .ps <번호>\n예시: .ps 1 (1번 곡 재생)\n예시: .ps 3 (3번 곡 재생)```"
            )
            return
        if number < 1 or number > len(recommendations):
            await ctx.send(f"```❌ 1~{len(recommendations)} 사이의 번호를 입력해주세요.```")
            return
        await self._play_spotify_recommendation(ctx, recommendations, number - 1)

    @commands.command(name="similar")
    async def similar(self, ctx: commands.Context) -> None:
        if not await self._require_spotify(ctx):
            return
        state = self._state(ctx)
        if not state.current_info:
            await ctx.send(
                "```❌ 현재 재생 중인 Spotify 곡이 없습니다.\n"
                "먼저 .sp 또는 .mind 명령어로 음악을 재생해주세요.```"
            )
            return

        await ctx.send("```🔍 현재 곡과 비슷한 음악을 찾는 중...```")
        try:
            tracks = await self.spotify.get_similar_tracks(
                state.current_info["name"], state.current_info["artist"], limit=5
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("similar 오류: %s", exc)
            await ctx.send(f"```❌ 비슷한 음악 찾기 중 오류가 발생했습니다: {exc}```")
            return

        if not tracks:
            await ctx.send("```❌ 비슷한 음악을 찾을 수 없습니다.```")
            return

        state.last_spotify_recommendations = tracks
        embed = _build_track_embed(
            title="🎵 비슷한 음악 추천",
            description=(
                f"'{state.current_info['name']}' - {state.current_info['artist']}와 비슷한 음악들\n\n"
                "**사용법:**\n✅ 자동 재생 (1번 곡)\n1️⃣~5️⃣ 번호 선택 (여러 개 선택 가능)\n"
                ".ps <번호> 명령어\n❌ 취소"
            ),
            tracks=tracks,
        )
        message = await ctx.send(embed=embed)

        async def _play(idx: int) -> None:
            await self._play_spotify_recommendation(ctx, tracks, idx)

        await run_track_selector(ctx=ctx, message=message, play_track=_play)

    @commands.command(name="auto")
    async def auto(self, ctx: commands.Context) -> None:
        if not await self._require_spotify(ctx):
            return
        state = self._state(ctx)
        if not state.current_info:
            await ctx.send(
                "```❌ 현재 재생 중인 Spotify 곡이 없습니다.\n"
                "먼저 .sp 명령어로 Spotify 곡을 재생해주세요.```"
            )
            return

        await ctx.send("```🔄 현재 곡과 비슷한 곡을 찾는 중...```")
        try:
            similar = await self.spotify.get_similar_tracks(
                state.current_info["name"], state.current_info["artist"]
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("auto 비슷한 곡 검색 오류: %s", exc)
            await ctx.send("```❌ 비슷한 곡을 찾는 중 오류가 발생했습니다.```")
            return

        if not similar:
            await ctx.send(
                "```❌ 비슷한 곡을 찾을 수 없습니다.\n\n"
                "이 곡은 Spotify에서 추천을 제공하지 않거나,\n유사한 곡을 찾을 수 없습니다.\n\n"
                "다른 곡으로 시도해보세요.```"
            )
            return

        added = 0
        for selected in similar:
            yt = await self.yt.search(f"{selected['name']} {selected['artist']}")
            if yt is None:
                continue
            state.auto_similar_queue.append(
                AutoTrack(
                    url=yt.url,
                    title=yt.title,
                    thumbnail=yt.thumbnail,
                    info={
                        "name": selected["name"],
                        "artist": selected["artist"],
                        "album": selected["album"],
                        "external_url": selected["external_url"],
                        "duration_ms": selected["duration_ms"],
                    },
                )
            )
            added += 1

        if added:
            state.auto_similar_mode = True
            preview = "\n".join(
                f"• {track['name']} - {track['artist']}" for track in similar[:5]
            )
            await ctx.send(
                f"```✅ {added}개의 비슷한 곡이 대기열에 추가되었습니다!\n\n추가된 곡들:\n{preview}```"
            )
        else:
            await ctx.send(
                "```🔄 자동 비슷한 곡 재생 모드 — 비슷한 곡을 YouTube 에서 찾을 수 없습니다.\n"
                "다른 곡으로 시도해보세요.```"
            )

    @commands.command(name="autostop")
    async def autostop(self, ctx: commands.Context) -> None:
        if not await self._require_spotify(ctx):
            return
        state = self._state(ctx)
        if state.auto_similar_mode:
            state.auto_similar_mode = False
            state.auto_similar_queue.clear()
            await ctx.send(
                "```⏹️ 자동 비슷한 곡 재생 모드가 중단되었습니다.\n"
                "현재 재생 중인 곡은 계속 재생됩니다.\n\n자동 대기열도 비워졌습니다.```"
            )
        else:
            await ctx.send("```💡 자동 비슷한 곡 재생 모드가 이미 비활성화되어 있습니다.```")

    @commands.command(name="playlist")
    async def playlist(
        self, ctx: commands.Context, *, playlist_url: Optional[str] = None
    ) -> None:
        if not await self._require_spotify(ctx):
            return
        settings = self.bot.settings  # type: ignore[attr-defined]
        url = playlist_url or settings.spotify_default_playlist_url

        await ctx.send("```🎵 Spotify 플레이리스트를 분석하는 중...```")
        try:
            tracks, playlist_info = await self.spotify.get_playlist_tracks(url, limit=10)
        except Exception as exc:  # noqa: BLE001
            log.warning("playlist 조회 오류: %s", exc)
            await ctx.send(f"```❌ 플레이리스트 재생 중 오류가 발생했습니다: {str(exc)[:200]}...```")
            return

        if not tracks:
            await ctx.send(
                "```❌ 플레이리스트에서 곡을 찾을 수 없습니다.\n\n"
                "가능한 원인:\n• 플레이리스트가 비어있음\n• 플레이리스트가 비공개임\n• 잘못된 URL\n\n"
                "다른 플레이리스트를 시도해보세요.```"
            )
            return

        embed = discord.Embed(
            title="🎵 Spotify 플레이리스트 재생",
            description=(
                f"**{playlist_info['name']}**\n\n"
                f"📝 {playlist_info['description'][:100]}"
                f"{'...' if len(playlist_info['description']) > 100 else ''}\n"
                f"📊 총 곡 수: {playlist_info['total_tracks']}개\n"
                f"🎲 랜덤 선택: {len(tracks)}개"
            ),
            color=0x5DADE2,
            url=playlist_info["external_url"],
        )
        listing = "\n".join(
            f"{i}. **{track['name']}** - {track['artist']} ({_duration_string(track['duration_ms'])})"
            for i, track in enumerate(tracks, 1)
        )
        embed.add_field(name="🎲 랜덤 선택된 곡들", value=listing, inline=False)
        await ctx.send(embed=embed)

        voice = await ensure_voice(ctx)
        if voice is None:
            return

        await ctx.send("```🔄 YouTube에서 곡들을 병렬로 검색하는 중... (더 빠름!)```")
        state = self._state(ctx)
        results = await self.yt.prefetch_many(tracks, max_concurrent=3)

        added = 0
        for _, yt in results:
            state.playlist_queue.append(
                Track(
                    url=yt.url,
                    title=yt.title,
                    thumbnail=yt.thumbnail,
                    video_id=yt.video_id,
                )
            )
            added += 1
        failed = len(tracks) - added

        if added:
            await ctx.send(
                f"```✅ 플레이리스트에서 {added}개 곡을 큐에 추가했습니다!\n\n"
                f"📊 결과:\n• 성공: {added}개\n• 실패: {failed}개\n"
                f"• 플레이리스트 큐: {len(state.playlist_queue)}개```"
            )
            if not voice.is_playing() and state.playlist_queue:
                await self.music.play_next(ctx)
        else:
            await ctx.send(
                "```❌ 플레이리스트에서 재생 가능한 곡을 찾을 수 없습니다.\n\n"
                "YouTube에서 해당 곡들을 찾을 수 없었습니다.\n다른 플레이리스트를 시도해보세요.```"
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SpotifyCog(bot))
