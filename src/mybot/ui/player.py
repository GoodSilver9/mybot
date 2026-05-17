"""음악 플레이어 임베드 + 컨트롤 버튼."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

import discord
from discord import ButtonStyle, ui

if TYPE_CHECKING:
    from ..core.state import GuildState

log = logging.getLogger(__name__)


# 원본 bot.py 에서 쓰던 커스텀 이모지 ID — 동작 보존을 위해 그대로 사용
EMOJI_PLAY = discord.PartialEmoji(name="1_play", id=1467459287642144841)
EMOJI_PAUSE = discord.PartialEmoji(name="2_pause", id=1467459302410289327)
EMOJI_STOP = discord.PartialEmoji(name="3_stop", id=1467459315722883158)
EMOJI_SKIP = discord.PartialEmoji(name="4_skip_forward", id=1467459327408210064)


def format_duration(seconds: Optional[int]) -> str:
    if not seconds:
        return "??:??"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}:{secs:02d}"


def build_player_embed(
    *,
    title: str,
    thumbnail_url: Optional[str],
    queue_count: int,
) -> discord.Embed:
    embed = discord.Embed(color=0x2B2D31)
    embed.set_author(name="♪ Now Playing", icon_url="https://i.imgur.com/DfBTLnS.png")
    embed.title = title
    if thumbnail_url:
        embed.set_image(url=thumbnail_url)
    embed.set_footer(
        text=f"📋 대기: {queue_count}곡",
        icon_url="https://www.youtube.com/s/desktop/d743f786/img/favicon_96x96.png",
    )
    return embed


class MusicControlView(ui.View):
    def __init__(self, ctx, state: "GuildState") -> None:
        super().__init__(timeout=None)
        self.ctx = ctx
        self._state = state

    @ui.button(emoji=EMOJI_STOP, style=ButtonStyle.secondary, custom_id="stop")
    async def stop_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        voice = self.ctx.voice_client
        if voice:
            self._state.reset()
            if voice.is_playing() or voice.is_paused():
                voice.stop()
            await voice.disconnect()
        await interaction.response.defer()

    @ui.button(emoji=EMOJI_PAUSE, style=ButtonStyle.secondary, custom_id="pause_resume")
    async def pause_resume_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        voice = self.ctx.voice_client
        if voice and voice.is_playing():
            voice.pause()
            button.emoji = EMOJI_PLAY
            await interaction.response.edit_message(view=self)
        elif voice and voice.is_paused():
            voice.resume()
            button.emoji = EMOJI_PAUSE
            await interaction.response.edit_message(view=self)
        else:
            await interaction.response.defer()

    @ui.button(emoji=EMOJI_SKIP, style=ButtonStyle.secondary, custom_id="skip")
    async def skip_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        voice = self.ctx.voice_client
        if voice and (voice.is_playing() or voice.is_paused()):
            voice.stop()
        await interaction.response.defer()

    @ui.button(emoji="📋", style=ButtonStyle.secondary, custom_id="queue")
    async def queue_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        state = self._state
        embed = discord.Embed(title="📋 대기열", color=0x2B2D31)
        if state.current_track:
            embed.add_field(
                name="🎵 현재 재생 중", value=f"**{state.current_track}**", inline=False
            )

        combined = list(state.queue) + list(state.playlist_queue)
        if combined:
            lines = []
            for idx, item in enumerate(combined[:8]):
                title = item.title if hasattr(item, "title") else str(item)
                if len(title) > 40:
                    title = title[:37] + "..."
                lines.append(f"`{idx + 1}` {title}")
            if len(combined) > 8:
                lines.append(f"*... +{len(combined) - 8}곡 더*")
            embed.add_field(name=f"다음 곡 ({len(combined)})", value="\n".join(lines), inline=False)
        else:
            embed.add_field(name="다음 곡", value="*비어 있음*", inline=False)

        if state.auto_similar_mode and state.auto_similar_queue:
            embed.add_field(
                name=f"🔄 자동 재생 ({len(state.auto_similar_queue)})",
                value="비슷한 곡이 자동으로 추가됩니다",
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)
