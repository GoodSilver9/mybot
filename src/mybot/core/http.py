"""봇 전체에서 공유하는 aiohttp 세션.

기존 코드는 매 요청마다 ``aiohttp.ClientSession()`` 을 새로 만들었음 → 커넥션 재사용 못 함.
``Bot`` 인스턴스 lifetime 에 묶인 단일 세션을 노출.
"""

from __future__ import annotations

import aiohttp


class HttpSessionManager:
    def __init__(self, total_timeout: float = 120.0) -> None:
        self._timeout = aiohttp.ClientTimeout(total=total_timeout)
        self._session: aiohttp.ClientSession | None = None

    async def get(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
        return self._session

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None
