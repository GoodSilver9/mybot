"""번역 & AI 검색 명령: jp / kr / en / search."""

from __future__ import annotations

import logging

from discord.ext import commands

from ..services.deepseek import DeepSeekService

log = logging.getLogger(__name__)


class Language(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @property
    def deepseek(self) -> DeepSeekService:
        return self.bot.deepseek  # type: ignore[attr-defined]

    @commands.command(name="jp")
    async def jp(self, ctx: commands.Context, *, text: str = "") -> None:
        if not text:
            await ctx.send("```사용법: .jp <번역할 텍스트>\n예시: .jp 안녕하세요```")
            return
        await ctx.send("```번역 중...```")
        translated = await self.deepseek.translate(text, "Japanese")
        await ctx.send(f"```🇯🇵 일본어 번역:\n{translated}```")

    @commands.command(name="kr")
    async def kr(self, ctx: commands.Context, *, text: str = "") -> None:
        if not text:
            await ctx.send("```사용법: .kr <번역할 텍스트>\n예시: .kr こんにちは```")
            return
        await ctx.send("```번역 중...```")
        translated = await self.deepseek.translate(text, "Korean")
        await ctx.send(f"```🇰🇷 한국어 번역:\n{translated}```")

    @commands.command(name="en")
    async def en(self, ctx: commands.Context, *, text: str = "") -> None:
        if not text:
            await ctx.send("```사용법: .en <번역할 텍스트>\n예시: .en 안녕하세요```")
            return
        await ctx.send("```번역 중...```")
        translated = await self.deepseek.translate(text, "English")
        await ctx.send(f"```🇺🇸 영어 번역:\n{translated}```")

    @commands.command(name="search")
    async def search(self, ctx: commands.Context, *, query: str = "") -> None:
        if not query:
            await ctx.send("```사용법: .search <질문>```")
            return
        await ctx.send("```🔍 검색 중... 잠시만 기다려주세요.```")
        try:
            result = await self.deepseek.search_and_summarize(query)
        except Exception as exc:  # noqa: BLE001
            log.warning("search 오류: %s", exc)
            await ctx.send(f"```❌ 검색 중 오류가 발생했습니다: {exc}```")
            return
        if len(result) > 3000:
            result = result[:3000] + "..."
        await ctx.send(f"```📚 검색 결과:\n{result}```")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Language(bot))
