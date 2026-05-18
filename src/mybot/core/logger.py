"""표준 로깅 설정.

전 모듈이 ``logging.getLogger(__name__)`` 만 호출하면 됨.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(log_dir: Path, level: int = logging.INFO) -> Path:
    """루트 로거를 설정하고 사용 중인 로그 파일 경로를 반환."""

    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "bot.log"

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    file_handler = RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    stream_handler = logging.StreamHandler(stream=sys.stdout)
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)

    for noisy in ("discord", "discord.client", "discord.gateway", "discord.voice_client"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)

    return log_file
