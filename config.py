"""레거시 호환 shim.

새 위치는 ``src/mybot/core/config.py``. 직접 import 하지 마세요.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from mybot.core.config import (  # noqa: E402,F401
    DEFAULT_BEFORE_OPTIONS,
    DEFAULT_OPTIONS,
    FFmpegOptions,
    Settings,
    load_settings,
)


def load_env_config() -> dict[str, str]:
    return dict(load_settings().extra)


def get_ffmpeg_options() -> dict[str, str]:
    return load_settings().ffmpeg_options.as_kwargs()


def get_node_path() -> str:
    return load_settings().node_path


FFMPEG_OPTIONS = get_ffmpeg_options()
