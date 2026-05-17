"""레거시 호환 shim. 실제 구현은 ``src/mybot/services/spotify.py``."""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from mybot.services.emotion_map import EMOTION_QUERY, SIMILAR_WORDS  # noqa: E402,F401
from mybot.services.spotify import SpotifyService  # noqa: E402

# 과거 API 호환. 새 코드는 MusicBot.spotify 를 직접 사용할 것.
SpotifyAPI = SpotifyService
spotify_api = None


async def analyze_emotion_and_recommend(text: str, spotify_service: SpotifyService):
    return await spotify_service.emotion_recommend(text, limit=5)
