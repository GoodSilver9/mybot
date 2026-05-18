"""DeepSeek chat completion 클라이언트.

기존 ``bot.py`` 의 번역/검색 함수에서 발생하던:
- 매 요청마다 새로 만든 ``aiohttp.ClientSession`` → 공유 세션으로 교체
- 하드코딩된 API 키 → ``Settings`` 주입
"""

from __future__ import annotations

import asyncio
import logging
from typing import Final

import aiohttp

from ..core.config import Settings
from ..core.http import HttpSessionManager

log = logging.getLogger(__name__)


_TRANSLATION_SYSTEM: Final[dict[str, str]] = {
    "Japanese": "당신은 한국어를 일본어로 번역하는 전문 번역가입니다. 자연스럽고 정확한 일본어로 번역해주세요.",
    "Korean": "당신은 일본어나 영어를 한국어로 번역하는 전문 번역가입니다. 자연스럽고 정확한 한국어로 번역해주세요.",
    "English": "당신은 한국어를 영어로 번역하는 전문 번역가입니다. 자연스럽고 정확한 영어로 번역해주세요.",
}

_SEARCH_SYSTEM: Final[str] = (
    "당신은 한국어로 답변하는 도움이 되는 AI 어시스턴트입니다. 모든 답변은 반드시 한국어로 작성해주세요."
)


class DeepSeekService:
    def __init__(self, settings: Settings, http: HttpSessionManager) -> None:
        self._settings = settings
        self._http = http

    @property
    def available(self) -> bool:
        return self._settings.deepseek_available

    async def _post(self, payload: dict) -> str:
        if not self.available:
            return "DeepSeek API 키가 설정되지 않았습니다. .env 의 DEEPSEEK_API_KEY 를 확인하세요."
        headers = {
            "Authorization": f"Bearer {self._settings.deepseek_api_key}",
            "Content-Type": "application/json",
        }
        session = await self._http.get()
        for attempt in range(3):
            try:
                async with session.post(
                    self._settings.deepseek_api_url, headers=headers, json=payload
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result["choices"][0]["message"]["content"]
                    body = await response.text()
                    log.warning("DeepSeek 응답 %s: %s", response.status, body[:200])
                    if attempt < 2:
                        await asyncio.sleep(1)
                        continue
                    return f"API 호출 실패 (status {response.status})"
            except asyncio.TimeoutError:
                if attempt < 2:
                    continue
                return "요청 시간이 초과되었습니다. 잠시 후 다시 시도해주세요."
            except aiohttp.ClientError as exc:
                log.warning("DeepSeek 네트워크 오류: %s", exc)
                if attempt < 2:
                    await asyncio.sleep(1)
                    continue
                return "네트워크 연결에 문제가 있습니다."
        return "요청에 실패했습니다."

    async def translate(self, text: str, target_lang: str) -> str:
        system_msg = _TRANSLATION_SYSTEM.get(
            target_lang,
            f"당신은 {target_lang} 전문 번역가입니다. 자연스럽고 정확한 번역을 제공해주세요.",
        )
        return await self._post(
            {
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": f"다음 텍스트를 {target_lang}로 번역해주세요: {text}"},
                ],
                "temperature": 0.3,
                "max_tokens": 1000,
            }
        )

    async def search_and_summarize(self, query: str) -> str:
        prompt = (
            "다음 질문에 대해 자세하고 정확한 정보를 한글로 답변해주세요. "
            "가능한 한 상세하고 이해하기 쉽게 설명해주세요.\n\n"
            f"질문: {query}\n\n답변은 반드시 한글로 작성해주세요."
        )
        return await self._post(
            {
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": _SEARCH_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.7,
                "max_tokens": 2000,
            }
        )


__all__ = ["DeepSeekService"]
