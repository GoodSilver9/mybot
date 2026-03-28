@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
echo ========================================
echo   Discord Music Bot - 설치 스크립트
echo ========================================
echo.

REM Python 확인
python --version >nul 2>&1
if errorlevel 1 (
    echo [오류] Python이 설치되어 있지 않습니다.
    echo https://www.python.org/downloads/ 에서 Python 3.8 이상을 설치하세요.
    pause
    exit /b 1
)
echo [OK] Python 확인 완료
python --version

REM pip 패키지 설치
echo.
echo [1/4] Python 패키지 설치 중...
pip install -r requirements.txt
if errorlevel 1 (
    echo [오류] 패키지 설치 실패
    pause
    exit /b 1
)
echo [OK] 패키지 설치 완료

REM FFmpeg 확인 및 설치
echo.
echo [2/4] FFmpeg 확인 중...
set "FFMPEG_EXE="
where ffmpeg >nul 2>&1
if not errorlevel 1 (
    for /f "tokens=*" %%i in ('where ffmpeg 2^>nul') do (
        if "!FFMPEG_EXE!"=="" set "FFMPEG_EXE=%%i"
    )
    echo [OK] FFmpeg 이미 설치됨: !FFMPEG_EXE!
) else (
    echo FFmpeg가 없습니다. winget으로 설치합니다...
    winget install --id Gyan.FFmpeg -e --silent
    if errorlevel 1 (
        echo [경고] winget 설치 실패. .env 파일에 FFMPEG_PATH를 직접 입력하세요.
    ) else (
        echo [OK] FFmpeg 설치 완료
        REM winget 설치 후 경로 탐색
        for /f "tokens=*" %%i in ('where ffmpeg 2^>nul') do (
            if "!FFMPEG_EXE!"=="" set "FFMPEG_EXE=%%i"
        )
        if "!FFMPEG_EXE!"=="" (
            REM PATH 미반영 시 winget 패키지 폴더에서 직접 탐색
            for /r "%LOCALAPPDATA%\Microsoft\WinGet\Packages" %%i in (ffmpeg.exe) do (
                if "!FFMPEG_EXE!"=="" set "FFMPEG_EXE=%%i"
            )
        )
    )
)

REM Node.js 확인 및 설치
echo.
echo [3/4] Node.js 확인 중...
set "NODE_EXE="
where node >nul 2>&1
if not errorlevel 1 (
    for /f "tokens=*" %%i in ('where node 2^>nul') do (
        if "!NODE_EXE!"=="" set "NODE_EXE=%%i"
    )
    echo [OK] Node.js 이미 설치됨: !NODE_EXE!
) else (
    echo Node.js가 없습니다. winget으로 설치합니다...
    winget install --id OpenJS.NodeJS -e --silent
    if errorlevel 1 (
        echo [경고] Node.js winget 설치 실패. https://nodejs.org 에서 수동 설치하세요.
    ) else (
        echo [OK] Node.js 설치 완료
        for /f "tokens=*" %%i in ('where node 2^>nul') do (
            if "!NODE_EXE!"=="" set "NODE_EXE=%%i"
        )
        if "!NODE_EXE!"=="" (
            if exist "C:\Program Files\nodejs\node.exe" set "NODE_EXE=C:\Program Files\nodejs\node.exe"
        )
    )
)

REM .env 파일 설정
echo.
echo [4/4] 환경 설정 중...
if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo [OK] .env 파일 생성됨
)

REM ffmpeg 경로를 .env에 자동 기록
if not "!FFMPEG_EXE!"=="" (
    REM 이미 FFMPEG_PATH가 있으면 교체, 없으면 추가
    python -c "
import re, sys
path = sys.argv[1]
with open('.env', 'r', encoding='utf-8') as f:
    content = f.read()
if 'FFMPEG_PATH=' in content:
    content = re.sub(r'#?\s*FFMPEG_PATH=.*', 'FFMPEG_PATH=' + path, content)
else:
    content += '\nFFMPEG_PATH=' + path + '\n'
with open('.env', 'w', encoding='utf-8') as f:
    f.write(content)
print('[OK] FFMPEG_PATH .env에 저장:', path)
" "!FFMPEG_EXE!"
)

REM node 경로를 .env에 자동 기록
if not "!NODE_EXE!"=="" (
    python -c "
import re, sys
path = sys.argv[1]
with open('.env', 'r', encoding='utf-8') as f:
    content = f.read()
if 'NODE_PATH=' in content:
    content = re.sub(r'#?\s*NODE_PATH=.*', 'NODE_PATH=' + path, content)
else:
    content += 'NODE_PATH=' + path + '\n'
with open('.env', 'w', encoding='utf-8') as f:
    f.write(content)
print('[OK] NODE_PATH .env에 저장:', path)
" "!NODE_EXE!"
)

echo.
echo !! 중요: .env 파일을 열어 Discord 봇 토큰을 입력하세요 !!
echo    DISCORD_BOT_TOKEN = Discord Developer Portal에서 발급
echo.
echo .env 파일을 메모장으로 열겠습니까? (Y/N)
set /p OPEN_ENV=
if /i "!OPEN_ENV!"=="Y" notepad .env

echo.
echo ========================================
echo   설치 완료!
echo ========================================
echo.
echo 봇 실행 방법:
echo   python bot.py       (콘솔 창)
echo   python gui.py       (트레이 아이콘)
echo.
pause
