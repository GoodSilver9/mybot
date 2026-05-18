"""기존 ``python bot.py`` 호환용 shim.

실제 로직은 ``src/mybot/`` 패키지에 있음. ``gui.py`` 가 이 파일을 띄우므로 경로 유지.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SRC = _HERE / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# 윈도우 콘솔 UTF-8 강제 (한글 print 시 UnicodeEncodeError 방지)
if os.name == "nt":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass

from mybot.bot import run  # noqa: E402

if __name__ == "__main__":
    run(_HERE)
