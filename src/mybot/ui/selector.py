"""Spotify 추천 결과 reaction 선택 UI.

원본 ``bot.py`` 의 ``.mind / .sp / .similar`` 3 곳에 거의 동일하게 복붙되어 있던
60줄짜리 reaction 선택 루프를 단일 함수로 정리.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

import discord

log = logging.getLogger(__name__)

EMOJI_AUTO = "✅"
EMOJI_CANCEL = "❌"
NUMBER_EMOJIS = ("1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣")
_VALID_EMOJIS = {EMOJI_AUTO, EMOJI_CANCEL, *NUMBER_EMOJIS}


PlayCallback = Callable[[int], Awaitable[None]]


async def run_track_selector(
    *,
    ctx,
    message: discord.Message,
    play_track: PlayCallback,
    timeout: float = 20.0,
) -> None:
    await asyncio.gather(
        *(message.add_reaction(emoji) for emoji in (EMOJI_AUTO, EMOJI_CANCEL, *NUMBER_EMOJIS)),
        return_exceptions=True,
    )

    selected: set[int] = set()
    processing: set[int] = set()

    def _check(reaction: discord.Reaction, user: Any) -> bool:
        return user == ctx.author and str(reaction.emoji) in _VALID_EMOJIS

    try:
        while True:
            reaction, _user = await ctx.bot.wait_for(
                "reaction_add", timeout=timeout, check=_check
            )
            emoji = str(reaction.emoji)

            if emoji == EMOJI_AUTO:
                if 0 not in processing:
                    processing.add(0)
                    asyncio.create_task(play_track(0))
                return
            if emoji == EMOJI_CANCEL:
                await ctx.send("```자동 재생을 취소했습니다.```")
                return

            if emoji in NUMBER_EMOJIS:
                idx = NUMBER_EMOJIS.index(emoji)
                if idx in selected or idx in processing:
                    if idx in processing:
                        await ctx.send(
                            f"```{idx + 1}번 곡은 현재 처리 중입니다. 잠시만 기다려주세요.```"
                        )
                    else:
                        await ctx.send(f"```{idx + 1}번 곡은 이미 선택되었습니다.```")
                    continue
                selected.add(idx)
                processing.add(idx)
                asyncio.create_task(play_track(idx))
                if len(selected) >= 5:
                    await ctx.send("```5개 곡이 선택되어 재생을 중단합니다.```")
                    return
    except asyncio.TimeoutError:
        if selected:
            await ctx.send(f"```시간 초과! {len(selected)}개 곡이 재생되었습니다.```")
        else:
            await ctx.send("```시간이 초과되어 자동 재생이 취소되었습니다.```")
