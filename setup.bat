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
echo [1/3] Python 패키지 설치 중...
pip install -r requirements.txt
if errorlevel 1 (
    echo [오류] 패키지 설치 실패
    pause
    exit /b 1
)
echo [OK] 패키지 설치 완료

REM FFmpeg 확인 및 설치
echo.
echo [2/3] FFmpeg 확인 중...
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo FFmpeg가 없습니다. winget으로 설치합니다...
    winget install --id Gyan.FFmpeg -e --silent
    if errorlevel 1 (
        echo [경고] winget 설치 실패. 수동으로 FFmpeg를 설치하세요.
        echo   1. https://www.gyan.dev/ffmpeg/builds/ 에서 다운로드
        echo   2. 압축 해제 후 bin 폴더를 PATH에 추가
        echo   또는 .env 파일에 FFMPEG_PATH=경로\ffmpeg.exe 를 직접 입력하세요.
    ) else (
        echo [OK] FFmpeg 설치 완료 (터미널 재시작 후 적용됩니다)
    )
) else (
    echo [OK] FFmpeg 이미 설치됨
    ffmpeg -version 2>&1 | findstr "ffmpeg version"
)

REM .env 파일 설정
echo.
echo [3/3] 환경 설정 확인 중...
if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo [필요] .env 파일이 생성되었습니다.
    echo.
    echo !! 중요: .env 파일을 열어 아래 값을 입력하세요 !!
    echo    DISCORD_BOT_TOKEN = Discord 봇 토큰
    echo    SPOTIFY_CLIENT_ID = Spotify Client ID (선택)
    echo    SPOTIFY_CLIENT_SECRET = Spotify Client Secret (선택)
    echo.
    echo .env 파일을 메모장으로 열겠습니까? (Y/N)
    set /p OPEN_ENV=
    if /i "!OPEN_ENV!"=="Y" notepad .env
) else (
    echo [OK] .env 파일 존재 확인
)

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
