"""FFmpeg 오디오 소스 팩토리."""

from __future__ import annotations

from discord import FFmpegPCMAudio

from ..core.config import FFmpegOptions


def build_source(url: str, options: FFmpegOptions) -> FFmpegPCMAudio:
    return FFmpegPCMAudio(url, **options.as_kwargs())
