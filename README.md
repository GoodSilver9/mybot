# 🎵 Discord Music Bot

> **다기능 음악 봇** - YouTube 음악 재생, Spotify 연동, AI 번역 및 검색 기능을 제공하는 올인원 디스코드 봇

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![Discord.py](https://img.shields.io/badge/Discord.py-2.5.2-blue.svg)
![Spotify](https://img.shields.io/badge/Spotify-API-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

---

## ✨ **주요 기능**

### 🎶 **음악 재생**
- **YouTube 음악 재생** - URL 또는 검색어로 음악 재생
- **고품질 오디오** - FFmpeg 기반 192kbps 스트리밍
- **재생 목록 관리** - 큐 추가, 건너뛰기, 일시정지/재개
- **자동 재연결** - 네트워크 끊김 시 자동 복구

### 🎵 **Spotify 연동**
- **감정 기반 추천** - 사용자의 감정/상황에 맞는 음악 추천
- **Spotify 검색** - Spotify 데이터베이스에서 음악 검색
- **비슷한 곡 추천** - 현재 재생 중인 곡과 비슷한 음악 자동 추천
- **자동 연속 재생** - 비슷한 곡을 자동으로 추가하여 무한 재생

### 🤖 **AI 기능** (준비중)
- **AI 번역** - 한국어, 일본어, 영어 간 번역
- **AI 검색** - 지능형 정보 검색 및 요약

---

## 🎮 **명령어**

### 기본 음악 명령어
| 명령어 | 설명 | 사용법 |
|--------|------|--------|
| `.play` / `.p` | 음악 재생 | `.play [URL 또는 검색어]` |
| `.pause` | 일시정지 | `.pause` |
| `.resume` | 재생 재개 | `.resume` |
| `.skip` | 다음 곡으로 건너뛰기 | `.skip` |
| `.stop` | 재생 중단 및 퇴장 | `.stop` |
| `.q` | 재생 목록 확인 | `.q` |
| `.clear` | 재생 목록 비우기 | `.clear` |

### 🎵 Spotify 연동 명령어
| 명령어 | 설명 | 사용법 |
|--------|------|--------|
| `.mind` | 감정 기반 음악 추천 | `.mind 기분이 좋아` |
| `.sp` | Spotify 검색 | `.sp BTS Dynamite` |
| `.ps` | 번호로 추천 곡 재생 | `.ps 3` |
| `.similar` | 비슷한 곡 추천 | `.similar` |
| `.auto` | 자동 연속 재생 모드 | `.auto` |
| `.autostop` | 자동 모드 중단 | `.autostop` |

### 🤖 AI 명령어 (준비중)
| 명령어 | 설명 | 사용법 |
|--------|------|--------|
| `.jp` | 한국어 → 일본어 번역 | `.jp 안녕하세요` |
| `.kr` | 일본어/영어 → 한국어 번역 | `.kr こんにちは` |
| `.en` | 한국어 → 영어 번역 | `.en 안녕하세요` |
| `.search` | AI 기반 정보 검색 | `.search 파이썬이란?` |

---

## 🚀 **설치 및 설정**

### 1. **필요 조건**
- Python 3.8 이상
- Windows 10/11

### 2. **빠른 설치 (권장)**

```bash
# 저장소 클론
git clone https://github.com/GoodSilver9/smbot.git
cd smbot/mybot

# 설치 스크립트 실행 (Python 패키지 + FFmpeg 자동 설치)
setup.bat
```

`setup.bat`이 자동으로 처리합니다:
- Python 패키지 설치 (`requirements.txt`)
- FFmpeg 설치 (winget 사용)
- `.env` 파일 생성

### 3. **환경 설정**

`setup.bat` 실행 시 `.env` 파일이 자동 생성됩니다. 아래 값을 입력하세요:

```env
DISCORD_BOT_TOKEN=your_discord_bot_token_here

# Spotify 연동 사용 시 (선택사항)
SPOTIFY_CLIENT_ID=your_spotify_client_id_here
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret_here
```

- Discord 토큰: [Discord Developer Portal](https://discord.com/developers/applications)
- Spotify 키: [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)

### 4. **실행**

```bash
python bot.py
```

또는 트레이 아이콘으로 실행:

```bash
python gui.py
```

---

## 🏗️ **프로젝트 구조**
