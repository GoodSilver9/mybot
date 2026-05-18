"""환경 설정 로더.

원본 ``config.py`` 의 동작을 유지하면서 frozen dataclass 로 노출.
``.env`` → 환경변수 → 기본값 순으로 병합.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping


def _parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class FFmpegOptions:
    executable: str
    before_options: str
    options: str

    def as_kwargs(self) -> dict[str, str]:
        return {
            "executable": self.executable,
            "before_options": self.before_options,
            "options": self.options,
        }


DEFAULT_BEFORE_OPTIONS = (
    "-reconnect 1 "
    "-reconnect_streamed 1 "
    "-reconnect_delay_max 5 "
    "-reconnect_at_eof 1 "
    "-timeout 30000000 "
    "-nostdin "
    "-analyzeduration 0 "
    "-probesize 32768 "
    "-fflags +nobuffer+fastseek"
)

DEFAULT_OPTIONS = (
    "-vn "
    "-b:a 256k "
    "-bufsize 128k "
    "-loglevel error "
    "-avoid_negative_ts make_zero "
    "-fflags +discardcorrupt "
    "-ac 2 "
    "-ar 48000 "
    '-af "aresample=resampler=soxr" '
    "-compression_level 10"
)


@dataclass(frozen=True)
class Settings:
    discord_token: str
    command_prefix: str = "."
    case_insensitive: bool = True
    voice_timeout: float = 30.0
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    spotify_default_playlist_url: str = (
        "https://open.spotify.com/playlist/3EFwYCA2ixqyf9n5qIridt"
    )
    deepseek_api_key: str = ""
    deepseek_api_url: str = "https://api.deepseek.com/chat/completions"
    ffmpeg_path: str = "ffmpeg"
    node_path: str = "node"
    log_dir: Path = field(default_factory=lambda: Path("logs"))
    url_cache_ttl_seconds: int = 3600
    voice_idle_disconnect_seconds: int = 60
    extra: Mapping[str, str] = field(default_factory=dict)

    @property
    def spotify_available(self) -> bool:
        return bool(self.spotify_client_id and self.spotify_client_secret)

    @property
    def deepseek_available(self) -> bool:
        return bool(self.deepseek_api_key)

    @property
    def ffmpeg_options(self) -> FFmpegOptions:
        return FFmpegOptions(
            executable=self.ffmpeg_path,
            before_options=DEFAULT_BEFORE_OPTIONS,
            options=DEFAULT_OPTIONS,
        )


def _resolve(key: str, env_file: Mapping[str, str], default: str = "") -> str:
    return os.environ.get(key) or env_file.get(key) or default


def load_settings(project_dir: Path | None = None) -> Settings:
    """프로젝트 디렉터리의 ``.env`` 와 OS 환경변수를 합쳐 ``Settings`` 를 반환."""

    base = project_dir or Path(__file__).resolve().parents[3]
    env_file = _parse_env_file(base / ".env")

    token = _resolve("DISCORD_BOT_TOKEN", env_file)
    if not token:
        raise RuntimeError(
            "DISCORD_BOT_TOKEN 이 .env 또는 환경변수에 없습니다. "
            ".env.example 를 참고해 .env 를 작성하세요."
        )

    prefix = _resolve("COMMAND_PREFIX", env_file, ".")
    case_insensitive = _truthy(_resolve("CASE_INSENSITIVE", env_file, "true"))
    voice_timeout_raw = _resolve("VOICE_TIMEOUT", env_file, "30.0")
    try:
        voice_timeout = float(voice_timeout_raw)
    except ValueError:
        voice_timeout = 30.0

    log_dir_raw = _resolve("LOG_DIR", env_file, str(base / "logs"))

    return Settings(
        discord_token=token,
        command_prefix=prefix,
        case_insensitive=case_insensitive,
        voice_timeout=voice_timeout,
        spotify_client_id=_resolve("SPOTIFY_CLIENT_ID", env_file),
        spotify_client_secret=_resolve("SPOTIFY_CLIENT_SECRET", env_file),
        spotify_default_playlist_url=_resolve(
            "SPOTIFY_DEFAULT_PLAYLIST_URL",
            env_file,
            "https://open.spotify.com/playlist/3EFwYCA2ixqyf9n5qIridt",
        ),
        deepseek_api_key=_resolve("DEEPSEEK_API_KEY", env_file),
        deepseek_api_url=_resolve(
            "DEEPSEEK_API_URL",
            env_file,
            "https://api.deepseek.com/chat/completions",
        ),
        ffmpeg_path=_resolve("FFMPEG_PATH", env_file, "ffmpeg"),
        node_path=_resolve("NODE_PATH", env_file, "node"),
        log_dir=Path(log_dir_raw),
        extra=dict(env_file),
    )


def inject_tool_paths(settings: Settings) -> None:
    """ffmpeg / node 디렉터리를 PATH 앞에 주입 (yt-dlp 가 찾도록)."""

    for tool in (settings.ffmpeg_path, settings.node_path):
        if not tool:
            continue
        parent = os.path.dirname(tool)
        if not parent or not os.path.isdir(parent):
            continue
        current = os.environ.get("PATH", "")
        if parent in current.split(os.pathsep):
            continue
        os.environ["PATH"] = parent + os.pathsep + current
