"""크로스플랫폼 봇 런처.

사용 예::

    python run.py            # 포그라운드 실행 (Ctrl+C 로 종료)
    python run.py start      # 백그라운드 실행 (PID 파일에 기록)
    python run.py stop       # PID 파일을 읽어 안전 종료
    python run.py status     # 실행 여부 확인
    python run.py run        # 데몬 자신이 호출하는 내부용 (직접 사용 X)

- macOS / Linux: 표준 detach(setsid + 새 세션) 사용.
- Windows: ``DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP`` 로 분리.
- 기존 ``gui.py`` (Windows tray) 는 그대로 사용 가능.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

PID_FILE = HERE / ".bot.pid"
LOG_DIR = HERE / "logs"
DAEMON_LOG = LOG_DIR / "daemon.out"


def _read_pid() -> int | None:
    if not PID_FILE.exists():
        return None
    try:
        return int(PID_FILE.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _process_alive(pid: int) -> bool:
    if os.name == "nt":
        try:
            import ctypes

            handle = ctypes.windll.kernel32.OpenProcess(0x0400 | 0x0010, False, pid)
            if handle == 0:
                return False
            exit_code = ctypes.c_ulong()
            ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            ctypes.windll.kernel32.CloseHandle(handle)
            return exit_code.value == 259  # STILL_ACTIVE
        except Exception:  # noqa: BLE001
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _foreground() -> int:
    from mybot.bot import run

    run(HERE)
    return 0


def _spawn_detached() -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    existing = _read_pid()
    if existing and _process_alive(existing):
        print(f"이미 실행 중입니다 (PID {existing}).", file=sys.stderr)
        return 1

    cmd = [sys.executable, str(Path(__file__).resolve()), "run"]
    out = open(DAEMON_LOG, "ab", buffering=0)

    kwargs: dict = {
        "stdin": subprocess.DEVNULL,
        "stdout": out,
        "stderr": out,
        "cwd": str(HERE),
    }
    if os.name == "nt":
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        kwargs["creationflags"] = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        kwargs["close_fds"] = True
    else:
        kwargs["start_new_session"] = True
        kwargs["close_fds"] = True

    proc = subprocess.Popen(cmd, **kwargs)  # noqa: S603
    PID_FILE.write_text(f"{proc.pid}\n", encoding="utf-8")
    time.sleep(0.5)
    if proc.poll() is not None:
        print(f"봇이 즉시 종료되었습니다 (exit={proc.returncode}). {DAEMON_LOG} 확인.")
        return 2
    print(f"백그라운드 실행 시작: PID {proc.pid}\n로그: {DAEMON_LOG}")
    return 0


def _stop() -> int:
    pid = _read_pid()
    if pid is None:
        print("PID 파일이 없습니다.")
        return 1
    if not _process_alive(pid):
        print(f"PID {pid} 프로세스가 이미 종료되어 있습니다. PID 파일 정리.")
        try:
            PID_FILE.unlink()
        except OSError:
            pass
        return 0

    sig = signal.SIGTERM if os.name != "nt" else signal.SIGBREAK
    try:
        os.kill(pid, sig)
    except OSError as exc:
        print(f"종료 신호 전송 실패: {exc}", file=sys.stderr)
        return 2

    for _ in range(20):
        if not _process_alive(pid):
            break
        time.sleep(0.5)

    if _process_alive(pid):
        print("정상 종료 실패 — 강제 종료 시도", file=sys.stderr)
        try:
            os.kill(pid, signal.SIGKILL if os.name != "nt" else signal.SIGTERM)
        except OSError:
            pass

    try:
        PID_FILE.unlink()
    except OSError:
        pass
    print(f"PID {pid} 종료 완료.")
    return 0


def _status() -> int:
    pid = _read_pid()
    if pid is None:
        print("실행 중 아님.")
        return 1
    if _process_alive(pid):
        print(f"실행 중 (PID {pid}).")
        return 0
    print(f"PID 파일은 있지만 프로세스(PID {pid})는 죽어 있음.")
    return 2


COMMANDS = {
    "start": _spawn_detached,
    "stop": _stop,
    "status": _status,
    "run": _foreground,
}


def main(argv: list[str]) -> int:
    if not argv:
        return _foreground()
    cmd = argv[0]
    fn = COMMANDS.get(cmd)
    if fn is None:
        print(__doc__)
        return 2
    return fn()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
