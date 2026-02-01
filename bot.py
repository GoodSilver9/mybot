import discord
import sys
import os
import yt_dlp
import asyncio
import requests
import json
import subprocess
import base64
import aiohttp
import random
from concurrent.futures import ProcessPoolExecutor
from discord import File, FFmpegPCMAudio
from io import BytesIO
from PIL import Image, ImageDraw
from discord.ext import commands
from discord import ui, ButtonStyle
from config import create_bot_client, FFMPEG_OPTIONS

# 별도 프로세스 풀 (CPU 집약적 작업용 - yt-dlp)
# 메인 봇 스레드를 블로킹하지 않음
yt_executor = ProcessPoolExecutor(max_workers=2)

# 패키지 업데이트 함수
def update_package(package_name):
    """지정된 패키지를 업데이트합니다."""
    try:
        print(f"[시스템] {package_name} 업데이트를 확인하는 중...")
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'install', '-U', package_name], 
            capture_output=True, text=True, timeout=60
        )
        
        if result.returncode == 0:
            if "already satisfied" in result.stdout.lower() or "already up-to-date" in result.stdout.lower():
                print(f"[시스템] {package_name}이(가) 이미 최신 버전입니다.")
            else:
                print(f"[시스템] {package_name} 업데이트 완료!")
            return True
        else:
            print(f"[경고] {package_name} 업데이트 실패: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        print(f"[경고] {package_name} 업데이트 시간 초과 (60초)")
        return False
    except Exception as e:
        print(f"[경고] {package_name} 업데이트 중 오류: {str(e)}")
        return False

def update_all_packages():
    """모든 필수 패키지를 업데이트합니다."""
    packages = ['yt-dlp', 'discord.py']
    for package in packages:
        update_package(package)

# 봇 시작 시 패키지 업데이트 실행
print("[시스템] 봇 시작 중...")
update_all_packages()

# Token 파일 경로 설정
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

# .env 파일에서 토큰 읽기 (같은 폴더에서)
def load_tokens_from_file():
    tokens = {}
    env_file_path = os.path.join(current_dir, '.env')
    
    try:
        with open(env_file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    tokens[key] = value
        return tokens
    except FileNotFoundError:
        print(f"[오류] .env 파일을 찾을 수 없습니다: {env_file_path}")
        return {}
    except Exception as e:
        print(f"[오류] .env 파일 읽기 실패: {str(e)}")
        return {}

# 토큰 로드
tokens = load_tokens_from_file()
TOKEN = tokens.get('DISCORD_BOT_TOKEN')  # .env에서 DISCORD_BOT_TOKEN 사용

# 환경 변수에서 토큰을 먼저 확인
if not TOKEN:
    TOKEN = os.getenv('DISCORD_BOT_TOKEN')

# 환경 변수와 파일에서 모두 토큰을 찾을 수 없는 경우
if not TOKEN:
    try:
        from disco_token import Token
        TOKEN = Token
        print("[디버그] disco_token.py에서 토큰 임포트 성공")
    except Exception as e:
        try:
            print(f"[디버그] 모든 토큰 소스에서 실패: {str(e)}")
        except UnicodeEncodeError:
            print("[디버그] 토큰 로딩 실패 - 인코딩 문제")
        print(f"[디버그] 현재 디렉토리: {os.getcwd()}")
        print(f"[디버그] sys.path: {sys.path}")
        print("[경고] 토큰을 찾을 수 없습니다. .env 파일을 확인하세요.")
        sys.exit(1)
else:
    print("[디버그] .env에서 토큰을 로드했습니다.")

# 딥시크 API
DEEPSEEK_API_KEY = tokens.get('DEEPSEEK_API_KEY', "sk-27dae9be93c648bb8805a793438f6eb5")
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"

# Spotify API 설정
SPOTIFY_CLIENT_ID = tokens.get('SPOTIFY_CLIENT_ID', '')
SPOTIFY_CLIENT_SECRET = tokens.get('SPOTIFY_CLIENT_SECRET', '')

# 환경변수로도 설정 (spotify_integration 모듈이 os.getenv() 사용)
os.environ['SPOTIFY_CLIENT_ID'] = SPOTIFY_CLIENT_ID
os.environ['SPOTIFY_CLIENT_SECRET'] = SPOTIFY_CLIENT_SECRET

# Spotify 통합 모듈 임포트
try:
    from spotify_integration import spotify_api, analyze_emotion_and_recommend
    SPOTIFY_AVAILABLE = True
    print("[시스템] Spotify API 통합 모듈 로드 완료")
    try:
        print(f"[디버그] Spotify Client ID: {SPOTIFY_CLIENT_ID[:10]}..." if SPOTIFY_CLIENT_ID else "[경고] Spotify Client ID 없음")
    except UnicodeEncodeError:
        print("[디버그] Spotify 설정 로딩 완료")
except ImportError as e:
    SPOTIFY_AVAILABLE = False
    print(f"[경고] Spotify API 통합 모듈 로드 실패: {e}")

# 봇 클라이언트 생성
client = create_bot_client()

# 봇 실행 상태 플래그
is_bot_running = False

queue = []  # 재생 대기열 (일반 곡들)
playlist_queue = []  # 플레이리스트 전용 대기열
current_track = None  # 현재 재생 중인 곡
current_track_thumbnail = None  # 현재 재생 중인 곡의 썸네일
current_track_info = None  # 현재 재생 중인 곡의 상세 정보 (Spotify용)
is_playing = False  # 현재 재생 중인지 여부
current_voice_client = None 
disconnect_task = None  # 자동 퇴장 타이머를 위한 변수
auto_similar_mode = False  # 자동 비슷한 곡 재생 모드
auto_similar_queue = []  # 자동 비슷한 곡 대기열
current_music_message = None  # 현재 음악 플레이어 메시지

# URL 캐싱 시스템 (video_id -> {url, title, thumbnail, timestamp})
import time
url_cache = {}
URL_CACHE_EXPIRY = 3600  # URL 캐시 만료 시간 (1시간)

# 음악 플레이어 컨트롤 버튼 클래스
# 셔플 모드 전역 변수
shuffle_mode = False

class MusicControlView(ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=None)
        self.ctx = ctx

    # 커스텀 이모지 ID
    EMOJI_PLAY = discord.PartialEmoji(name="1_play", id=1467459287642144841)
    EMOJI_PAUSE = discord.PartialEmoji(name="2_pause", id=1467459302410289327)
    EMOJI_STOP = discord.PartialEmoji(name="3_stop", id=1467459315722883158)
    EMOJI_SKIP = discord.PartialEmoji(name="4_skip_forward", id=1467459327408210064)

    # 1. 정지
    @ui.button(emoji=EMOJI_STOP, style=ButtonStyle.secondary, custom_id="stop")
    async def stop_button(self, interaction: discord.Interaction, button: ui.Button):
        global is_playing, current_track, auto_similar_mode
        voice = self.ctx.voice_client
        
        if voice:
            queue.clear()
            playlist_queue.clear()
            auto_similar_queue.clear()
            auto_similar_mode = False
            is_playing = False
            current_track = None
            
            if voice.is_playing() or voice.is_paused():
                voice.stop()
            
            await voice.disconnect()
            await interaction.response.defer()
        else:
            await interaction.response.defer()

    # 2. 재생/일시정지
    @ui.button(emoji=EMOJI_PAUSE, style=ButtonStyle.secondary, custom_id="pause_resume")
    async def pause_resume_button(self, interaction: discord.Interaction, button: ui.Button):
        voice = self.ctx.voice_client
        if voice and voice.is_playing():
            voice.pause()
            button.emoji = discord.PartialEmoji(name="1_play", id=1467459287642144841)
            await interaction.response.edit_message(view=self)
        elif voice and voice.is_paused():
            voice.resume()
            button.emoji = discord.PartialEmoji(name="2_pause", id=1467459302410289327)
            await interaction.response.edit_message(view=self)
        else:
            await interaction.response.defer()

    # 3. 다음곡
    @ui.button(emoji=EMOJI_SKIP, style=ButtonStyle.secondary, custom_id="skip")
    async def skip_button(self, interaction: discord.Interaction, button: ui.Button):
        voice = self.ctx.voice_client
        if voice and (voice.is_playing() or voice.is_paused()):
            voice.stop()
            await interaction.response.defer()
        else:
            await interaction.response.defer()

    # 4. 대기열
    @ui.button(emoji="📋", style=ButtonStyle.secondary, custom_id="queue")
    async def queue_button(self, interaction: discord.Interaction, button: ui.Button):
        global current_track, playlist_queue, auto_similar_queue, auto_similar_mode
        
        embed = discord.Embed(
            title="📋 대기열",
            color=0x2B2D31
        )
        
        # 현재 재생 중
        if current_track:
            embed.add_field(
                name="🎵 현재 재생 중",
                value=f"**{current_track}**",
                inline=False
            )
        
        # 모든 대기열 합치기 (queue + playlist_queue)
        all_queue = list(queue) + list(playlist_queue)
        
        if all_queue:
            queue_lines = []
            for idx, item in enumerate(all_queue[:8]):
                title = item[1] if len(item) > 1 else str(item)
                if len(title) > 40:
                    title = title[:37] + "..."
                queue_lines.append(f"`{idx + 1}` {title}")
            
            if len(all_queue) > 8:
                queue_lines.append(f"*... +{len(all_queue) - 8}곡 더*")
            
            embed.add_field(
                name=f"다음 곡 ({len(all_queue)})",
                value="\n".join(queue_lines),
                inline=False
            )
        else:
            embed.add_field(name="다음 곡", value="*비어 있음*", inline=False)
        
        # 자동 재생 대기열
        if auto_similar_mode and auto_similar_queue:
            embed.add_field(
                name=f"🔄 자동 재생 ({len(auto_similar_queue)})",
                value="비슷한 곡이 자동으로 추가됩니다",
                inline=False
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

def format_duration(seconds):
    """초를 MM:SS 형식으로 변환"""
    if not seconds:
        return "??:??"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}:{secs:02d}"

# 음악 플레이어 임베드 생성 함수
async def create_music_player_embed(title, artist="알 수 없는 아티스트", thumbnail_url=None, duration=None, requester=None):
    # Discord 다크 테마에 어울리는 색상
    embed = discord.Embed(color=0x2B2D31)  # Discord 다크 배경과 어울리는 색
    
    # 심플한 제목
    embed.set_author(
        name="♪ Now Playing",
        icon_url="https://i.imgur.com/DfBTLnS.png"  # 심플한 음표 아이콘
    )
    
    # 곡 제목 (깔끔하게)
    embed.title = title
    
    # 썸네일 (큰 이미지로)
    if thumbnail_url:
        embed.set_image(url=thumbnail_url)
    
    # 푸터 (미니멀하게)
    queue_count = len(queue) + len(playlist_queue)
    footer_text = f"📋 대기: {queue_count}곡"
    
    embed.set_footer(
        text=footer_text,
        icon_url="https://www.youtube.com/s/desktop/d743f786/img/favicon_96x96.png"
    )
    
    return embed


# Youtube-dl 옵션 (403 오류 해결을 위한 개선)
ydl_opts = {
    'quiet': True,  # 로그 출력 줄이기
    'format': 'bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    'youtube_include_dash_manifest': False,
    'no_warnings': True,  # 경고 메시지 숨기기
    'socket_timeout': 30,  # 소켓 타임아웃 30초
    'retries': 5,  # 재시도 횟수 증가
    'fragment_retries': 5,  # 프래그먼트 재시도 증가
    'extractor_retries': 5,  # 추출기 재시도 증가
    'http_chunk_size': 10485760,  # HTTP 청크 크기 (10MB)
    # 403 오류 해결을 위한 추가 옵션
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'referer': 'https://www.youtube.com/',
    'cookies': None,  # 쿠키 사용 안함
    'extractor_args': {
        'youtube': {
            'skip': ['dash', 'hls'],
            'player_skip': ['configs'],
            'player_client': ['android', 'web']
        }
    }
}

# 봇 준비 이벤트
@client.event
async def on_ready():
    print(f'Logged in as {client.user}')
    # 주기적으로 만료된 캐시 정리하는 태스크 시작
    client.loop.create_task(periodic_cache_cleanup())

async def periodic_cache_cleanup():
    """10분마다 만료된 캐시를 정리합니다."""
    while True:
        await asyncio.sleep(600)  # 10분 대기
        clear_expired_cache()
        print(f"[시스템] 만료된 URL 캐시 정리 완료 (현재 캐시: {len(url_cache)}개)")

# 안전한 채널명 처리 함수
def safe_channel_name(channel):
    """채널명을 안전하게 처리하여 인코딩 문제를 방지합니다."""
    try:
        if channel and hasattr(channel, 'name'):
            # 채널명을 안전하게 인코딩
            return channel.name.encode('utf-8', errors='ignore').decode('utf-8')
        return "Unknown Channel"
    except Exception as e:
        print(f"[경고] 채널명 처리 중 오류: {e}")
        return "Unknown Channel"

# 음성 연결 상태 모니터링
@client.event
async def on_voice_state_update(member, before, after):
    # 봇이 음성 채널에서 혼자 남겨진 경우 자동 퇴장
    if member == client.user:
        return
    
    try:
        voice_client = client.voice_clients
        for vc in voice_client:
            if vc.channel and len(vc.channel.members) == 1:  # 봇만 남은 경우
                channel_name = safe_channel_name(vc.channel)
                print(f"[디버그] 음성 채널 '{channel_name}'에서 혼자 남음 확인")
                await asyncio.sleep(5)  # 5초 대기 후 확인
                if len(vc.channel.members) == 1:  # 여전히 혼자면 퇴장
                    await vc.disconnect()
                    print(f"[시스템] 음성 채널 '{channel_name}'에서 혼자 남아 자동 퇴장했습니다.")
    except Exception as e:
        print(f"[오류] 음성 상태 업데이트 처리 중 오류: {str(e)}")

# 음성 채널 연결 함수
async def join(ctx):
    if ctx.voice_client is None:  
        if ctx.author.voice:  
            channel = ctx.author.voice.channel
            await channel.connect()  # 음성 채널에 연결``
            await ctx.send(f"음성 채널에 연결되었습니다.")
        else:
            await ctx.send("```먼저 음성 채널에 접속해주세요.```")
            return None
    else:
        await ctx.send(f" 봇은 이미 음성 채널에 연결되어 있습니다.")
    return ctx.voice_client  

# Node 스크립트 호출
def generate_song_card(data):
    try:
        # Node.js 스크립트 실행
        result = subprocess.run(
            ['node', 'generateCard.js', json.dumps(data)],
            capture_output=True, text=True
        )
        # 오류 메시지 출력
        if result.stderr:
            print("STDERR:", result.stderr)
            return None

        # Base64로 인코딩된 이미지 데이터 디코딩
        card_image = base64.b64decode(result.stdout.strip())
        return BytesIO(card_image)
    except Exception as e:
        print(f"Error generating song card: {e}")
        # 기본 이미지 반환
        with open("default_card.png", "rb") as f:
            return BytesIO(f.read())

# URL 캐시 관련 함수
def get_cached_url(video_id):
    """캐시에서 URL을 가져옵니다."""
    if video_id in url_cache:
        cached = url_cache[video_id]
        # 만료 여부 확인
        if time.time() - cached['timestamp'] < URL_CACHE_EXPIRY:
            return cached['url'], cached['title'], cached['thumbnail']
        else:
            # 만료된 캐시 삭제
            del url_cache[video_id]
    return None, None, None

def cache_url(video_id, url, title, thumbnail):
    """URL을 캐시에 저장합니다."""
    if video_id:
        url_cache[video_id] = {
            'url': url,
            'title': title,
            'thumbnail': thumbnail,
            'timestamp': time.time()
        }

def clear_expired_cache():
    """만료된 캐시를 정리합니다."""
    current_time = time.time()
    expired_keys = [k for k, v in url_cache.items() if current_time - v['timestamp'] >= URL_CACHE_EXPIRY]
    for key in expired_keys:
        del url_cache[key]

async def prefetch_urls_parallel(tracks, max_concurrent=3):
    """여러 트랙의 URL을 병렬로 미리 가져옵니다."""
    semaphore = asyncio.Semaphore(max_concurrent)  # 동시 요청 수 제한
    results = []
    
    async def fetch_single(track, index):
        async with semaphore:
            # 이벤트 루프에 제어권을 넘겨줌 (heartbeat 유지)
            await asyncio.sleep(0)
            
            search_query = f"{track['name']} {track['artist']}"
            try:
                url, title, thumbnail = await search_youtube(search_query)
                
                # 결과 처리 전에 이벤트 루프에 제어권 넘김
                await asyncio.sleep(0)
                
                if url:
                    video_id = None
                    try:
                        video_id = extract_video_id_from_url(url)
                    except:
                        pass
                    # 캐시에 저장
                    if video_id:
                        cache_url(video_id, url, title, thumbnail)
                    return (index, url, title, thumbnail, video_id, True)
                return (index, None, None, None, None, False)
            except Exception as e:
                print(f"[병렬 URL 추출] 트랙 {index+1} 실패: {e}")
                return (index, None, None, None, None, False)
    
    # 모든 트랙에 대해 병렬로 URL 추출
    # 이벤트 루프에 제어권을 넘겨줌
    await asyncio.sleep(0)
    tasks = [fetch_single(track, i) for i, track in enumerate(tracks)]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # 결과 정리
    success_results = []
    for result in results:
        # 루프 중간에 이벤트 루프에 제어권 넘김 (heartbeat 유지)
        # 0.1초 대기로 Discord heartbeat가 확실히 작동하도록 함
        await asyncio.sleep(0.1)
        
        if isinstance(result, Exception):
            continue
        if result[5]:  # success flag
            success_results.append(result)
    
    return success_results

def extract_video_id_from_url(url):
    """URL에서 video_id를 추출합니다 (간단한 파싱)."""
    if 'youtube.com/watch?v=' in url:
        try:
            return url.split('v=')[1].split('&')[0]
        except:
            pass
    elif 'youtu.be/' in url:
        try:
            return url.split('youtu.be/')[1].split('?')[0]
        except:
            pass
    return None

def extract_video_id(url):
    ydl_opts = {'quiet': True, 'no_warnings': True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info.get('id') if info else None
    except Exception as e:
        print(f"video_id 추출 중 오류: {e}")
        return None

async def get_fresh_url(video_id_or_url, max_retries=3):
    """video_id 또는 URL로부터 새로운 재생 URL을 가져옵니다 (만료 방지)"""
    ydl_opts_fresh = {
        'quiet': True,
        'format': 'bestaudio[acodec=opus]/bestaudio/best',  # Opus 코덱 우선 (최고 품질)
        'noplaylist': True,
        'no_warnings': True,
        'socket_timeout': 30,
        'retries': 3,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'referer': 'https://www.youtube.com/',
        'extractor_args': {
            'youtube': {
                'skip': ['dash', 'hls'],
                'player_skip': ['configs'],
                'player_client': ['android', 'web']
            }
        }
    }
    
    # video_id인 경우 YouTube URL로 변환
    if video_id_or_url and not video_id_or_url.startswith('http'):
        video_id_or_url = f"https://www.youtube.com/watch?v={video_id_or_url}"
    
    for attempt in range(max_retries):
        try:
            loop = asyncio.get_event_loop()
            with yt_dlp.YoutubeDL(ydl_opts_fresh) as ydl:
                # 30초 타임아웃으로 실행
                info = await asyncio.wait_for(
                    loop.run_in_executor(None, ydl.extract_info, video_id_or_url, False),
                    timeout=30.0
                )
                if info and 'url' in info:
                    return info['url'], info.get('title'), info.get('thumbnail')
        except asyncio.TimeoutError:
            print(f"URL 재추출 타임아웃 (시도 {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)  # 지수 백오프: 1초, 2초, 4초
                continue
        except Exception as e:
            print(f"URL 재추출 오류 (시도 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
                continue
    
    return None, None, None

@client.command(aliases=['p'])
async def play(ctx, *, search_or_url: str = None):  
    global current_track, current_track_thumbnail, disconnect_task, auto_similar_mode, current_music_message

    # 자동 재생 모드가 활성화된 경우 경고 메시지
    if auto_similar_mode:
        await ctx.send("```⚠️ 자동 비슷한 곡 재생 모드가 활성화되어 있습니다.\n다른 곡을 추가하면 자동 재생이 중단될 수 있습니다.\n\n사용법:\n.autostop - 자동 모드 중단 후 곡 추가\n.forceplay - 자동 모드 무시하고 곡 추가\n.stop - 모든 재생 중단```")
        return

    # 만약 자동 퇴장 타이머가 실행 중이라면 취소
    if disconnect_task:
        disconnect_task.cancel()
        disconnect_task = None
    
    voice = ctx.voice_client

    # 봇이 음성 채널에 연결되지 않은 경우 연결
    if not voice or not voice.is_connected():
        if ctx.author.voice:  
            try:
                channel = ctx.author.voice.channel
                channel_name = safe_channel_name(channel)
                try:
                    print(f"[디버그] 음성 채널 연결 시도: {channel_name} (ID: {channel.id})")
                except UnicodeEncodeError:
                    print(f"[디버그] 음성 채널 연결 시도: {channel.id}")
                
                # 기존 음성 연결이 있다면 정리
                if ctx.voice_client:
                    try:
                        await ctx.voice_client.disconnect()
                        print(f"[디버그] 기존 음성 연결 정리 완료")
                        await asyncio.sleep(1)  # 1초 대기
                    except:
                        pass
                
                # 재시도 로직 추가
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        voice = await channel.connect()
                        try:
                            print(f"[디버그] 음성 채널 연결 성공: {channel_name}")
                        except UnicodeEncodeError:
                            print(f"[디버그] 음성 채널 연결 성공: {channel.id}")
                        break
                    except Exception as connect_error:
                        print(f"[오류] 음성 채널 연결 시도 {attempt + 1}/{max_retries} 실패: {str(connect_error)}")
                        if attempt < max_retries - 1:
                            # 4006 오류의 경우 더 긴 대기 시간
                            wait_time = 5 if "4006" in str(connect_error) else 2
                            print(f"[디버그] {wait_time}초 대기 후 재시도...")
                            await asyncio.sleep(wait_time)
                        else:
                            raise connect_error
                            
            except Exception as e:
                print(f"[오류] 음성 채널 연결 최종 실패: {str(e)}")
                print(f"[오류] 채널명: {channel.name if 'channel' in locals() else 'Unknown'}")
                
                # 사용자에게 더 친화적인 오류 메시지
                if "4006" in str(e) or "ConnectionClosed" in str(e):
                    await ctx.send(f"```❌ 음성 채널 연결에 실패했습니다.\n\n가능한 원인:\n• 네트워크 연결 문제\n• Discord 서버 과부하\n• 봇 권한 부족\n\n잠시 후 다시 시도해주세요.```")
                else:
                    await ctx.send(f"```❌ 음성 채널 연결 중 오류가 발생했습니다.\n오류: {str(e)[:100]}...```")
                return
        else:
            await ctx.send("```먼저 음성 채널에 접속해주세요.```")
            return

    # 음성 연결 상태 재확인
    if not voice or not voice.is_connected():
        await ctx.send("```음성 채널에 연결할 수 없습니다. 다시 시도해주세요.```")
        return

    # 일시정지된 상태라면 다시 재생
    if voice and voice.is_paused():
        voice.resume()
        await ctx.send(f"```{ctx.author.mention} 일시정지된 음악을 다시 재생합니다.```")
        return

    if search_or_url:
        try:
            # URL로 입력된 경우
            if search_or_url.startswith("http"):
                # 로딩 메시지 표시 (10초 후 자동 삭제)
                loading_msg = await ctx.send("```🔄 URL 정보를 가져오는 중...```", delete_after=10)
                # 플레이리스트 항목 수 확인을 위한 옵션
                playlist_opts = {
                    'quiet': True,
                    'extract_flat': True,  # 플레이리스트 항목만 추출
                    'noplaylist': False
                }
                
                # 먼저 플레이리스트 정보만 확인
                with yt_dlp.YoutubeDL(playlist_opts) as ydl:
                    try:
                        info = ydl.extract_info(search_or_url, download=False)
                        if 'entries' in info:
                            playlist_count = len(info['entries'])
                            if playlist_count > 10:
                                await ctx.send("```플레이리스트는 최대 10개의 곡까지만 지원합니다. 더 적은 수의 곡을 선택해주세요.```", delete_after=10)
                                return
                            elif playlist_count > 1:
                                await ctx.send(f"```플레이리스트에서 {playlist_count}개의 곡을 추가합니다...```", delete_after=10)
                    except Exception as e:
                        print(f"플레이리스트 확인 중 오류: {e}")
                        pass  # 플레이리스트가 아닌 경우 무시

                # 실제 음악 정보 추출
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(search_or_url, download=False)
                    
                    # 플레이리스트인 경우
                    if 'entries' in info:
                        added_count = 0
                        for entry in info['entries']:
                            if entry:  # None이 아닌 경우만 처리
                                try:
                                    url2 = entry['url']
                                    title = entry.get('title', '알 수 없는 제목')
                                    entry_thumbnail = entry.get('thumbnail')
                                    entry_video_id = entry.get('id')  # video_id 추출
                                    
                                    # 음성 연결 상태 재확인
                                    if not voice or not voice.is_connected():
                                        await ctx.send("```음성 연결이 끊어졌습니다. 다시 연결해주세요.```")
                                        return
                                    
                                    # 현재 곡이 재생 중이라면 큐에 추가 (video_id 포함)
                                    if voice.is_playing():
                                        queue.append((url2, title, entry_thumbnail, entry_video_id))
                                        added_count += 1
                                    else:
                                        # 첫 번째 곡은 바로 재생
                                        data = {
                                            "imageText": title,
                                            "songArtist": "아티스트 이름",
                                            "trackDuration": 0,
                                            "trackTotalDuration": 0,
                                            "trackStream": False,
                                        }

                                        # 음악 재생 로직
                                        try:
                                            source = FFmpegPCMAudio(url2, **FFMPEG_OPTIONS)
                                            current_track = title
                                            voice.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), client.loop))
                                            # 음악 플레이어 임베드가 표시되므로 추가 메시지 불필요
                                            added_count += 1
                                            break  # 첫 번째 곡만 재생하고 나머지는 큐에 추가
                                        except Exception as play_error:
                                            print(f"음악 재생 중 오류: {play_error}")
                                            await ctx.send(f"```음악 재생 중 오류가 발생했습니다: {str(play_error)}```")
                                            continue
                                        
                                except Exception as e:
                                    print(f"곡 처리 중 오류: {e}")
                                    continue
                        
                        if added_count > 0:
                            await ctx.send(f"```플레이리스트에서 {added_count}개의 곡을 추가했습니다!```", delete_after=5)
                        else:
                            await ctx.send("```플레이리스트에서 곡을 추가할 수 없습니다.```", delete_after=5)
                        return
                    else:
                        # 단일 곡인 경우
                        url2 = info['url']
                        title = info.get('title', '알 수 없는 제목')
                        thumbnail_url = info.get('thumbnail')  # YouTube 썸네일 URL
                        video_id = info.get('id')  # video_id 추출
            else:  # 검색어로 입력된 경우
                url2, title, thumbnail_url = await search_youtube(search_or_url)
                video_id = None
                if url2:
                    try:
                        video_id = extract_video_id(url2)  # video_id 추출
                    except Exception as e:
                        print(f"video_id 추출 실패: {e}")
                        # video_id 없이도 계속 진행

            if not url2:
                await ctx.send("```검색 결과가 없습니다.```")
                return

            # 음성 연결 상태 재확인
            if not voice or not voice.is_connected():
                await ctx.send("```음성 연결이 끊어졌습니다. 다시 연결해주세요.```")
                return

            # 현재 곡이 재생 중이라면 큐에 추가 (video_id 포함)
            if voice.is_playing():
                queue.append((url2, title, thumbnail_url, video_id))  
                
                # 큐 추가 알림 (3초 후 자동 삭제)
                await ctx.send(f"```✅ '{title}'가 대기열에 추가되었습니다! (대기열: {len(queue)}개)```", delete_after=3)
                
                # 기존 음악 플레이어를 삭제하고 새로 아래에 표시
                if current_music_message:
                    try:
                        await current_music_message.delete()
                    except:
                        pass
                
                # 현재 재생 중인 곡으로 새 음악 플레이어 생성
                if current_track:
                    embed = await create_music_player_embed(current_track, thumbnail_url=current_track_thumbnail)
                    view = MusicControlView(ctx)
                    current_music_message = await ctx.send(embed=embed, view=view)
            else:
                data = {
                    "imageText": title,
                    "songArtist": "아티스트 이름",
                    "trackDuration": 0,
                    "trackTotalDuration": 0,
                    "trackStream": False,
                }

                # 음악 재생 로직
                try:
                    # 음성 연결 상태 최종 확인
                    if not voice or not voice.is_connected():
                        await ctx.send("```음성 연결이 끊어졌습니다. 다시 연결해주세요.```")
                        return
                    
                    source = FFmpegPCMAudio(url2, **FFMPEG_OPTIONS)
                    current_track = title
                    current_track_thumbnail = thumbnail_url
                    
                    def after_play(error):
                        if error:
                            print(f"재생 완료 후 오류: {error}")
                        asyncio.run_coroutine_threadsafe(play_next(ctx), client.loop)
                    
                    voice.play(source, after=after_play)
                    
                    # 음악 플레이어 임베드와 컨트롤 버튼 생성
                    embed = await create_music_player_embed(title, thumbnail_url=thumbnail_url)
                    view = MusicControlView(ctx)
                    
                    # 기존 음악 메시지가 있다면 삭제
                    if current_music_message:
                        try:
                            await current_music_message.delete()
                        except:
                            pass
                    
                    # 새로운 음악 플레이어 메시지 전송
                    current_music_message = await ctx.send(embed=embed, view=view)
                except Exception as play_error:
                    print(f"음악 재생 중 오류: {play_error}")
                    await ctx.send(f"```음악 재생 중 오류가 발생했습니다.\n오류: {str(play_error)[:100]}...```")
                    # 큐에 다음 곡이 있으면 시도
                    if queue:
                        await play_next(ctx)
                    return

        except Exception as e:
            await ctx.send(f"```음악을 재생할 수 없습니다. 오류: {str(e)}```")
            print(f"음악 재생 중 오류: {e}")
            return
    else:
        await ctx.send("```URL 또는 검색어를 입력해주세요.```")

@client.command()
async def q(ctx):
    global current_track, auto_similar_mode, auto_similar_queue
    
    embed = discord.Embed(
        title="📋 재생 목록",
        color=0x5DADE2  # 연한 하늘색
    )
    
    # 현재 재생 중인 곡
    if current_track:
        embed.add_field(
            name="🎵 현재 재생 중",
            value=f"`{current_track}`",
            inline=False
        )
    else:
        embed.add_field(
            name="🎵 현재 재생 중",
            value="없음",
            inline=False
        )
    
    # 일반 재생 목록
    if queue:
        if len(queue) > 10:
            queue_list = "\n".join([f"`{idx + 1}. {item[1]}`" for idx, item in enumerate(queue[:10])])
            queue_list += f"\n... 그리고 {len(queue) - 10}개 더"
        else:
            queue_list = "\n".join([f"`{idx + 1}. {item[1]}`" for idx, item in enumerate(queue)])
        
        embed.add_field(
            name="📋 대기 중인 곡들",
            value=queue_list if queue_list else "없음",
            inline=False
        )
    else:
        embed.add_field(
            name="📋 대기 중인 곡들",
            value="없음",
            inline=False
        )
    
    # 자동 비슷한 곡 대기열
    if auto_similar_queue:
        if len(auto_similar_queue) > 5:
            auto_queue_list = "\n".join([f"`{idx + 1}. {item['title']}`" for idx, item in enumerate(auto_similar_queue[:5])])
            auto_queue_list += f"\n... 그리고 {len(auto_similar_queue) - 5}개 더"
        else:
            auto_queue_list = "\n".join([f"`{idx + 1}. {item['title']}`" for idx, item in enumerate(auto_similar_queue)])
        
        embed.add_field(
            name="🔄 자동 비슷한 곡 대기열",
            value=auto_queue_list,
            inline=False
        )
    else:
        embed.add_field(
            name="🔄 자동 비슷한 곡 대기열",
            value="없음 (`.auto` 명령어로 활성화)",
            inline=False
        )
    
    embed.set_footer(text="🎶 Discord Music Bot")
    await ctx.send(embed=embed)

@client.command()
async def clear(ctx):
    global queue
    if queue:
        queue.clear()
        await ctx.send("```재생 목록이 비워졌습니다.```")
    else:
        await ctx.send("```재생 목록이 이미 비어 있습니다.```")

@client.command()
async def stop(ctx):
    global is_playing, queue, current_track, auto_similar_mode, current_track_info, auto_similar_queue

    queue.clear()  # 큐를 비움
    auto_similar_queue.clear()  # 자동 대기열도 비움
    is_playing = False  # 재생 상태 초기화
    current_track = None  # 현재 재생 중인 곡 초기화
    current_track_info = None  # 현재 곡 정보 초기화
    auto_similar_mode = False  # 자동 모드 비활성화

    voice = ctx.voice_client  # 현재 서버의 음성 클라이언트 가져오기

    if voice and voice.is_connected():
        await voice.disconnect()  # 음성 채널에서 나가기
        await ctx.send("```재생이 중단되었습니다. 음성 채널에서 나갑니다.\n자동 비슷한 곡 재생 모드도 비활성화되었습니다.```")
    else:
        await ctx.send("```봇이 음성 채널에 연결되어 있지 않습니다.```")

@client.command()
async def pause(ctx):
    voice = ctx.voice_client  

    if voice and voice.is_playing():  
        voice.pause()  
        await ctx.send(f"```{ctx.author.mention} 플레이어를 일시정지했습니다.```")
    else:
        await ctx.send(f"```{ctx.author.mention} 현재 재생 중인 곡이 없습니다.```")

@client.command()
async def resume(ctx):
    voice = ctx.voice_client  

    if voice and voice.is_paused():  
        voice.resume() 
        await ctx.send(f"```{ctx.author.mention} 음악을 계속 재생합니다.```")
    else:
        await ctx.send(f"```{ctx.author.mention} 현재 일시정지된 곡이 없습니다.```")

@client.command()
async def skip(ctx):
    voice = ctx.voice_client  # 현재 서버의 음성 클라이언트 참조

    if voice and voice.is_playing():
        voice.stop() 
        await ctx.send("```다음 곡으로 넘어갑니다.```")
        # voice.stop()의 after 콜백이 자동으로 play_next()를 호출하므로 여기서는 호출하지 않음
    else:
        await ctx.send("```현재 재생 중인 곡이 없습니다.```")

async def play_next(ctx):
    global is_playing, current_track, current_track_thumbnail, disconnect_task, auto_similar_mode, auto_similar_queue, current_track_info, playlist_queue, current_music_message

    if len(queue) == 0:  # 일반 큐가 비어있는 경우
        # 플레이리스트 큐에 곡이 있는 경우
        if playlist_queue:
            next_track = playlist_queue.pop(0)
            queue.append(next_track)
        # 자동 대기열에 곡이 있는 경우
        elif auto_similar_queue:
            next_track = auto_similar_queue.pop(0)
            thumbnail = next_track.get('thumbnail')
            # 자동 큐에서는 기존 방식 유지 (URL 포함)
            queue.append((next_track['url'], next_track['title'], thumbnail, None))
            current_track_info = next_track['info']
        else:
            is_playing = False
            current_track = None
            await ctx.send("```재생할 곡이 더 이상 없습니다.```")
            return

    # 음성 연결 상태 확인
    if ctx.voice_client is None or not ctx.voice_client.is_connected():
        await ctx.send("```음성 연결이 끊어졌습니다. 다시 연결해주세요.```")
        return

    try:
        is_playing = True
        # 큐에서 곡 정보 가져오기 (video_id 포함)
        queue_item = queue.pop(0)
        
        # 큐 아이템 파싱 (하위 호환성 유지)
        if len(queue_item) >= 4:
            url, title, thumbnail_url, video_id = queue_item[0], queue_item[1], queue_item[2], queue_item[3]
        elif len(queue_item) == 3:
            url, title, thumbnail_url = queue_item
            video_id = None
        else:
            url, title = queue_item
            thumbnail_url = None
            video_id = None
        
        current_track = title
        current_track_thumbnail = thumbnail_url

        # 다음 곡 재생
        try:
            # 이미 재생 중인지 확인
            if ctx.voice_client.is_playing():
                print("이미 재생 중이므로 건너뜀")
                return
            
            # video_id가 있으면 먼저 캐시 확인, 없으면 새로운 URL 가져오기
            if video_id:
                # 1. 먼저 캐시에서 확인
                cached_url, cached_title, cached_thumbnail = get_cached_url(video_id)
                if cached_url:
                    url = cached_url
                    print(f"[재생] 캐시에서 URL 로드 성공: {title}")
                    if cached_title:
                        title = cached_title
                        current_track = title
                    if cached_thumbnail:
                        thumbnail_url = cached_thumbnail
                        current_track_thumbnail = thumbnail_url
                else:
                    # 2. 캐시에 없으면 새 URL 가져오기 (최대 3번 재시도)
                    print(f"[재생] video_id로 새 URL 가져오는 중: {video_id}")
                    fresh_url, fresh_title, fresh_thumbnail = await get_fresh_url(video_id, max_retries=3)
                    
                    if fresh_url:
                        url = fresh_url
                        # 캐시에 저장
                        cache_url(video_id, fresh_url, fresh_title or title, fresh_thumbnail or thumbnail_url)
                        print(f"[재생] 새 URL 가져오기 성공: {title}")
                        if fresh_title:
                            title = fresh_title
                            current_track = title
                        if fresh_thumbnail:
                            thumbnail_url = fresh_thumbnail
                            current_track_thumbnail = thumbnail_url
                    else:
                        # URL 재추출 실패 - 제목으로 재검색 시도
                        print(f"[경고] URL 재추출 실패, 제목으로 재검색 시도: {title}")
                        search_url, search_title, search_thumbnail = await search_youtube(title)
                        if search_url:
                            url = search_url
                            print(f"[재생] 제목 검색으로 URL 복구 성공: {title}")
                        else:
                            # 최종 실패 - 곡 스킵
                            print(f"[오류] URL 재추출 최종 실패, 곡 스킵: {title}")
                            await ctx.send(f"```⚠️ '{title}' 재생 실패\n다음 곡으로 넘어갑니다.```")
                            if len(queue) > 0 or playlist_queue or (auto_similar_mode and auto_similar_queue):
                                await asyncio.sleep(0.5)
                                await play_next(ctx)
                            else:
                                is_playing = False
                                current_track = None
                                await ctx.send("```재생할 곡이 더 이상 없습니다.```")
                            return
            
            source = FFmpegPCMAudio(url, **FFMPEG_OPTIONS)
            
            def after_play(error):
                if error:
                    print(f"다음 곡 재생 완료 후 오류: {error}")
                asyncio.run_coroutine_threadsafe(play_next(ctx), client.loop)
            
            ctx.voice_client.play(source, after=after_play)
            
            # 음악 플레이어 임베드와 컨트롤 버튼 생성
            embed = await create_music_player_embed(title, thumbnail_url=thumbnail_url)
            view = MusicControlView(ctx)
            
            # 기존 음악 메시지가 있다면 삭제
            if current_music_message:
                try:
                    await current_music_message.delete()
                except:
                    pass
            
            # 새로운 음악 플레이어 메시지 전송
            current_music_message = await ctx.send(embed=embed, view=view)
        except Exception as play_error:
            print(f"다음 곡 재생 중 오류: {play_error}")
            await ctx.send(f"```⚠️ '{title}' 재생 중 오류 발생\n다음 곡으로 넘어갑니다.```")
            # 오류가 발생한 경우 다음 곡으로 넘어가기
            if len(queue) > 0 or playlist_queue or (auto_similar_mode and auto_similar_queue):
                await asyncio.sleep(1)  # 1초 대기 후 다음 곡
                await play_next(ctx)
            else:
                is_playing = False
                current_track = None
                await ctx.send("```재생할 곡이 더 이상 없습니다.```")
    except Exception as e:
        print(f"다음 곡 재생 중 오류: {e}")
        await ctx.send(f"```다음 곡 재생 중 오류가 발생했습니다: {str(e)[:100]}```")
        # 오류가 발생한 경우 다음 곡으로 넘어가기
        if len(queue) > 0 or playlist_queue or (auto_similar_mode and auto_similar_queue):
            await asyncio.sleep(1)  # 1초 대기 후 다음 곡
            await play_next(ctx)
        else:
            is_playing = False
            current_track = None
            await ctx.send("```재생할 곡이 더 이상 없습니다.```")

def _extract_youtube_info_sync(query: str) -> dict:
    """
    별도 프로세스에서 실행되는 동기 yt-dlp 함수.
    메인 봇 스레드를 블로킹하지 않음.
    """
    ydl_opts = {
        'quiet': True,
        'format': 'bestaudio[acodec=opus]/bestaudio/best',
        'default_search': 'ytsearch',
        'noplaylist': True,
        'youtube_include_dash_manifest': False,
        'no_warnings': True,
        'socket_timeout': 25,
        'retries': 3,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'referer': 'https://www.youtube.com/',
        'extractor_args': {
            'youtube': {
                'skip': ['dash', 'hls'],
                'player_skip': ['configs'],
                'player_client': ['android', 'web']
            }
        },
        'ignoreerrors': True,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch:{query}", download=False)
            if info and 'entries' in info and len(info['entries']) > 0:
                first_result = info['entries'][0]
                if first_result and 'url' in first_result and 'title' in first_result:
                    return {
                        'url': first_result['url'],
                        'title': first_result['title'],
                        'thumbnail': first_result.get('thumbnail'),
                        'id': first_result.get('id'),
                        'duration': first_result.get('duration'),
                        'uploader': first_result.get('uploader', '알 수 없음'),
                    }
        return None
    except Exception as e:
        print(f"[yt-dlp 프로세스] 오류: {e}")
        return None


async def search_youtube(query):
    """
    YouTube 검색 - 별도 프로세스에서 실행하여 메인 봇 블로킹 방지
    """
    # 재시도 로직 (최대 3번)
    for attempt in range(3):
        try:
            # 이벤트 루프에 제어권을 넘겨줌 (heartbeat 유지)
            await asyncio.sleep(0)
            
            # 별도 프로세스에서 실행 (메인 봇 블로킹 없음)
            loop = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(yt_executor, _extract_youtube_info_sync, query),
                timeout=30.0
            )
            
            # 결과 처리 전에 이벤트 루프에 제어권 넘김
            await asyncio.sleep(0)
            
            if result:
                url = result['url']
                title = result['title']
                thumbnail = result.get('thumbnail')
                video_id = result.get('id') or extract_video_id_from_url(url)
                
                # 캐시에 저장
                if video_id:
                    cache_url(video_id, url, title, thumbnail)
                
                return url, title, thumbnail
            
            return None, None, None
            
        except asyncio.TimeoutError:
            print(f"YouTube 검색 타임아웃 (시도 {attempt + 1}/3): {query}")
            if attempt < 2:
                await asyncio.sleep(1)
                continue
            return None, None, None
        except Exception as e:
            print(f"YouTube 검색 중 오류 (시도 {attempt + 1}/3): {e}")
            if attempt < 2:
                await asyncio.sleep(1)
                continue
            return None, None, None
    
    return None, None, None

# 번역 함수 (비동기)
async def translate_text(text, target_lang):
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # 번역할 언어에 따른 시스템 메시지 설정
    if target_lang == "Japanese":
        system_msg = "당신은 한국어를 일본어로 번역하는 전문 번역가입니다. 자연스럽고 정확한 일본어로 번역해주세요."
    elif target_lang == "Korean":
        system_msg = "당신은 일본어나 영어를 한국어로 번역하는 전문 번역가입니다. 자연스럽고 정확한 한국어로 번역해주세요."
    elif target_lang == "English":
        system_msg = "당신은 한국어를 영어로 번역하는 전문 번역가입니다. 자연스럽고 정확한 영어로 번역해주세요."
    else:
        system_msg = f"당신은 {target_lang} 전문 번역가입니다. 자연스럽고 정확한 번역을 제공해주세요."
    
    # 프롬프트 설정
    prompt = f"다음 텍스트를 {target_lang}로 번역해주세요: {text}"
    
    data = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,  # 번역은 정확성을 위해 낮은 temperature 사용
        "max_tokens": 1000
    }
    
    # 재시도 로직 (최대 3번)
    for attempt in range(3):
        try:
            # 비동기 HTTP 클라이언트 사용
            timeout = aiohttp.ClientTimeout(total=120)  # 2분 타임아웃
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(DEEPSEEK_API_URL, headers=headers, json=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result["choices"][0]["message"]["content"]
                    else:
                        return f"번역 실패: 상태 코드 {response.status}, 응답: {await response.text()}"
        except asyncio.TimeoutError:
            if attempt < 2:  # 마지막 시도가 아니면 재시도
                continue
            return "번역 시간이 초과되었습니다. (2분) 잠시 후 다시 시도해주세요."
        except aiohttp.ClientError:
            if attempt < 2:  # 마지막 시도가 아니면 재시도
                continue
            return "네트워크 연결에 문제가 있습니다. 인터넷 연결을 확인해주세요."
        except Exception as e:
            if attempt < 2:  # 마지막 시도가 아니면 재시도
                continue
            return f"API 호출 중 오류 발생: {str(e)}"
    
    return "번역에 실패했습니다. 잠시 후 다시 시도해주세요."

# 검색 함수 (비동기)
async def search_and_summarize(query):
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    # 프롬프트 설정 - 한글로 답변하도록 명시
    prompt = f"""다음 질문에 대해 자세하고 정확한 정보를 한글로 답변해주세요. 
    가능한 한 상세하고 이해하기 쉽게 설명해주세요.
    
    질문: {query}
    
    답변은 반드시 한글로 작성해주세요."""
    
    data = {
        "model": "deepseek-chat",  # 사용할 모델 이름 (문서 참고)
        "messages": [
            {"role": "system", "content": "당신은 한국어로 답변하는 도움이 되는 AI 어시스턴트입니다. 모든 답변은 반드시 한국어로 작성해주세요."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 2000  
    }
    
    # 재시도 로직 (최대 3번)
    for attempt in range(3):
        try:
            # 비동기 HTTP 클라이언트 사용
            timeout = aiohttp.ClientTimeout(total=120)  # 2분 타임아웃
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(DEEPSEEK_API_URL, headers=headers, json=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result["choices"][0]["message"]["content"]
                    else:
                        return f"검색 실패: 상태 코드 {response.status}, 응답: {await response.text()}"
        except asyncio.TimeoutError:
            if attempt < 2:  # 마지막 시도가 아니면 재시도
                continue
            return "검색 시간이 초과되었습니다. (2분) 잠시 후 다시 시도해주세요."
        except aiohttp.ClientError:
            if attempt < 2:  # 마지막 시도가 아니면 재시도
                continue
            return "네트워크 연결에 문제가 있습니다. 인터넷 연결을 확인해주세요."
        except Exception as e:
            if attempt < 2:  # 마지막 시도가 아니면 재시도
                continue
            return f"API 호출 중 오류 발생: {str(e)}"
    
    return "검색에 실패했습니다. 잠시 후 다시 시도해주세요."

# 명령어: 한국어 → 일본어 번역
@client.command(name="jp")
async def translate_to_japanese(ctx, *, text):
    if not text:
        await ctx.send("```사용법: .jp <번역할 텍스트>\n예시: .jp 안녕하세요```")
        return
    
    await ctx.send("```번역 중...```")
    translated_text = await translate_text(text, "Japanese")
    await ctx.send(f"```🇯🇵 일본어 번역:\n{translated_text}```")

# 명령어: 일본어/영어 → 한국어 번역
@client.command(name="kr")
async def translate_to_korean(ctx, *, text):
    if not text:
        await ctx.send("```사용법: .kr <번역할 텍스트>\n예시: .kr こんにちは```")
        return
    
    await ctx.send("```번역 중...```")
    translated_text = await translate_text(text, "Korean")
    await ctx.send(f"```🇰🇷 한국어 번역:\n{translated_text}```")

# 명령어: 한국어 → 영어 번역
@client.command(name="en")
async def translate_to_english(ctx, *, text):
    if not text:
        await ctx.send("```사용법: .en <번역할 텍스트>\n예시: .en 안녕하세요```")
        return
    
    await ctx.send("```번역 중...```")
    translated_text = await translate_text(text, "English")
    await ctx.send(f"```🇺🇸 영어 번역:\n{translated_text}```")

@client.command(name="search")
async def search(ctx, *, query):
    # 검색 시작 메시지
    await ctx.send("```🔍 검색 중... 잠시만 기다려주세요.```")
    
    try:
        # 검색 및 요약 실행
        search_result = await search_and_summarize(query)
        
        # 출력 길이 제한 증가 (더 긴 답변 허용)
        if len(search_result) > 3000:
            search_result = search_result[:3000] + "..."
        
        # 결과 출력
        await ctx.send(f"```📚 검색 결과:\n{search_result}```")
        
    except Exception as e:
        await ctx.send(f"```❌ 검색 중 오류가 발생했습니다: {str(e)}```")





# Spotify 트랙 재생 함수 (이 함수는 유지)
async def play_spotify_track(ctx, recommendations, track_index):
    """Spotify 추천 트랙을 YouTube에서 검색하여 재생"""
    global current_track_info, current_track, current_track_thumbnail, current_music_message
    
    if track_index >= len(recommendations):
        await ctx.send("```❌ 잘못된 번호입니다.```")
        return
    
    selected_track = recommendations[track_index]
    search_query = f"{selected_track['name']} {selected_track['artist']}"
    
    await ctx.send(f"```🎵 '{search_query}' 재생을 시작합니다!```", delete_after=5)
    
    # 기존 play 명령어 로직 사용
    url2, title, thumbnail_url = await search_youtube(search_query)
    if url2:
        # video_id 추출
        video_id = None
        try:
            video_id = extract_video_id(url2)
        except Exception as e:
            print(f"video_id 추출 실패: {e}")
        
        voice = ctx.voice_client
        if not voice or not voice.is_connected():
            if ctx.author.voice:
                try:
                    channel = ctx.author.voice.channel
                    channel_name = safe_channel_name(channel)
                    try:
                        print(f"[디버그] Spotify 재생 - 음성 채널 연결 시도: {channel_name} (ID: {channel.id})")
                    except UnicodeEncodeError:
                        print(f"[디버그] Spotify 재생 - 음성 채널 연결 시도: {channel.id}")
                    
                    # 기존 음성 연결이 있다면 정리
                    if ctx.voice_client:
                        try:
                            await ctx.voice_client.disconnect()
                            print(f"[디버그] Spotify 재생 - 기존 음성 연결 정리 완료")
                            await asyncio.sleep(1)  # 1초 대기
                        except:
                            pass
                    
                    # 재시도 로직 추가
                    max_retries = 3
                    for attempt in range(max_retries):
                        try:
                            voice = await channel.connect()
                            try:
                                print(f"[디버그] Spotify 재생 - 음성 채널 연결 성공: {channel_name}")
                            except UnicodeEncodeError:
                                print(f"[디버그] Spotify 재생 - 음성 채널 연결 성공: {channel.id}")
                            break
                        except Exception as connect_error:
                            print(f"[오류] Spotify 재생 - 음성 채널 연결 시도 {attempt + 1}/{max_retries} 실패: {str(connect_error)}")
                            if attempt < max_retries - 1:
                                # 4006 오류의 경우 더 긴 대기 시간
                                wait_time = 5 if "4006" in str(connect_error) else 2
                                print(f"[디버그] Spotify 재생 - {wait_time}초 대기 후 재시도...")
                                await asyncio.sleep(wait_time)
                            else:
                                raise connect_error
                                
                except Exception as e:
                    print(f"[오류] Spotify 재생 - 음성 채널 연결 최종 실패: {str(e)}")
                    if "4006" in str(e) or "ConnectionClosed" in str(e):
                        await ctx.send(f"```❌ 음성 채널 연결에 실패했습니다.\n네트워크 문제일 수 있습니다. 잠시 후 다시 시도해주세요.```")
                    else:
                        await ctx.send(f"```❌ 음성 채널 연결 중 오류가 발생했습니다: {str(e)[:100]}...```")
                    return
            else:
                await ctx.send("```음성 채널에 먼저 접속해주세요.```")
                return
        
        if voice.is_playing():
            queue.append((url2, title, thumbnail_url, video_id))
            # 큐 추가 알림 (3초 후 자동 삭제)
            if playlist_queue:
                await ctx.send(f"```✅ '{title}'가 대기열에 추가되었습니다! (플레이리스트 재생 중)```", delete_after=3)
            else:
                await ctx.send(f"```✅ '{title}'가 대기열에 추가되었습니다! (대기열: {len(queue)}개)```", delete_after=3)
            
            # 기존 음악 플레이어를 삭제하고 새로 아래에 표시
            if current_music_message:
                try:
                    await current_music_message.delete()
                except:
                    pass
            
            # 현재 재생 중인 곡으로 새 음악 플레이어 생성
            if current_track:
                embed = await create_music_player_embed(current_track, thumbnail_url=current_track_thumbnail)
                view = MusicControlView(ctx)
                current_music_message = await ctx.send(embed=embed, view=view)
        else:
            source = FFmpegPCMAudio(url2, **FFMPEG_OPTIONS)
            voice.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), client.loop))
            current_track = title  # 현재 재생 중인 곡 설정
            current_track_thumbnail = thumbnail_url  # 현재 재생 중인 곡의 썸네일 저장
            
            # 음악 플레이어 임베드와 컨트롤 버튼 생성
            embed = await create_music_player_embed(title, thumbnail_url=thumbnail_url)
            view = MusicControlView(ctx)
            
            # 기존 음악 메시지가 있다면 삭제
            if current_music_message:
                try:
                    await current_music_message.delete()
                except:
                    pass
            
            # 새로운 음악 플레이어 메시지 전송
            current_music_message = await ctx.send(embed=embed, view=view)
            
            # 현재 재생 중인 곡 정보 저장 (비슷한 음악 추천용)
            current_track_info = {
                'name': selected_track['name'],
                'artist': selected_track['artist'],
                'album': selected_track['album'],
                'external_url': selected_track['external_url'],
                'duration_ms': selected_track['duration_ms']
            }
    else:
        await ctx.send("```❌ YouTube에서 해당 곡을 찾을 수 없습니다.```")

# 자동 모드를 무시하고 곡을 추가하는 명령어
@client.command(name="forceplay")
async def force_play(ctx, *, search_or_url: str = None):
    """자동 모드를 무시하고 곡을 추가"""
    global current_track, disconnect_task, auto_similar_mode, auto_similar_queue
    
    if not search_or_url:
        await ctx.send("```사용법: .forceplay <URL 또는 검색어>\n예시: .forceplay BTS Dynamite```")
        return
    
    # 자동 모드 비활성화
    auto_similar_mode = False
    auto_similar_queue.clear()
    
    await ctx.send("```⚠️ 자동 비슷한 곡 재생 모드가 비활성화되었습니다.\n일반 재생 모드로 전환합니다.```")
    
    # 기존 play 명령어 로직 사용
    await play(ctx, search_or_url=search_or_url)

# 감정 기반 음악 추천 명령어 (새로운 .mind)
@client.command(name="mind")
async def mind_recommend(ctx, *, query: str = None):
    if not SPOTIFY_AVAILABLE:
        await ctx.send("```❌ Spotify API가 설정되지 않았습니다.```")
        return
    
    if not query:
        await ctx.send("```사용법: .mind <감정 또는 상황>\n예시: .mind 기분이 좋아\n예시: .mind 슬플 때 듣고 싶어```")
        return
    
    await ctx.send("```�� Spotify에서 음악을 추천받는 중...```")
    
    try:
        # 감정 분석 및 추천
        recommendations = await analyze_emotion_and_recommend(query, spotify_api)
        
        if not recommendations:
            await ctx.send("```❌ 추천 음악을 찾을 수 없습니다.```")
            return
        
        # 추천 결과를 전역 변수에 저장 (번호 선택용)
        ctx.bot.last_spotify_recommendations = recommendations
        
        # 추천 결과 표시
        embed = discord.Embed(
            title="🎵 Spotify 음악 추천",
            description=f"'{query}'에 맞는 음악을 추천해드려요!\n\n**사용법:**\n✅ 자동 재생 (1번 곡)\n1️⃣~5️⃣ 번호 선택 (여러 개 선택 가능)\n.ps <번호> 명령어\n❌ 취소",
            color=0x5DADE2  # 연한 하늘색
        )
        
        for i, track in enumerate(recommendations[:5], 1):
            duration_min = track['duration_ms'] // 60000
            duration_sec = (track['duration_ms'] % 60000) // 1000
            duration_str = f"{duration_min}:{duration_sec:02d}"
            
            embed.add_field(
                name=f"{i}. {track['name']}",
                value=f"�� {track['artist']}\n�� {track['album']}\n⏱️ {duration_str}\n🔗 [Spotify에서 듣기]({track['external_url']})",
                inline=False
            )
        
        # 자동 재생 옵션 제공
        message = await ctx.send(embed=embed)
        
        # 모든 이모티콘을 한 번에 추가 (더 빠른 반응을 위해)
        emojis_to_add = ['✅', '❌', '1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣']
        
        # 이모티콘을 병렬로 추가
        emoji_tasks = []
        for emoji in emojis_to_add:
            emoji_tasks.append(message.add_reaction(emoji))
        
        # 모든 이모티콘 추가 완료 대기
        await asyncio.gather(*emoji_tasks, return_exceptions=True)
        
        # 사용자 반응 대기 (개선된 버전)
        selected_tracks = set()  # 선택된 트랙 번호들
        processing_tracks = set()  # 현재 처리 중인 트랙들
        
        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ['✅', '❌', '1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣']
        
        try:
            # 20초 동안 반응 대기
            while True:
                reaction, user = await client.wait_for('reaction_add', timeout=20.0, check=check)
                
                if str(reaction.emoji) == '✅':
                    # 첫 번째 추천 곡 자동 재생
                    if 0 not in processing_tracks:
                        processing_tracks.add(0)
                        # 비동기로 재생 시작 (블로킹하지 않음)
                        asyncio.create_task(play_spotify_track(ctx, recommendations, 0))
                    break
                elif str(reaction.emoji) == '❌':
                    await ctx.send("```자동 재생을 취소했습니다.```")
                    break
                elif str(reaction.emoji) in ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣']:
                    # 번호 선택 재생
                    track_index = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣'].index(str(reaction.emoji))
                    
                    if track_index not in selected_tracks and track_index not in processing_tracks:
                        selected_tracks.add(track_index)
                        processing_tracks.add(track_index)
                        
                        # 비동기로 재생 시작 (블로킹하지 않음)
                        asyncio.create_task(play_spotify_track(ctx, recommendations, track_index))
                        
                        # 선택된 곡이 5개 이상이면 중단
                        if len(selected_tracks) >= 5:
                            await ctx.send("```5개 곡이 선택되어 재생을 중단합니다.```")
                            break
                    elif track_index in processing_tracks:
                        await ctx.send(f"```{track_index + 1}번 곡은 현재 처리 중입니다. 잠시만 기다려주세요.```")
                    else:
                        await ctx.send(f"```{track_index + 1}번 곡은 이미 선택되었습니다.```")
                
        except asyncio.TimeoutError:
            if selected_tracks:
                await ctx.send(f"```시간 초과! {len(selected_tracks)}개 곡이 재생되었습니다.```")
            else:
                await ctx.send("```시간이 초과되어 자동 재생이 취소되었습니다.```")
            
    except Exception as e:
        await ctx.send(f"```❌ Spotify 추천 중 오류가 발생했습니다: {str(e)}```")

# Spotify 검색 명령어 (새로운 .sp)
@client.command(name="sp")
async def spotify_search(ctx, *, query: str = None):
    if not SPOTIFY_AVAILABLE:
        await ctx.send("```❌ Spotify API가 설정되지 않았습니다.```")
        return
    
    if not query:
        await ctx.send("```사용법: .sp <검색어>\n예시: .sp 대부 ost\n예시: .sp BTS Dynamite\n예시: .sp 클래식 음악```")
        return
    
    await ctx.send("```🔍 Spotify에서 검색 중...```")
    
    try:
        tracks = await spotify_api.search_tracks(query, limit=5)
        
        if not tracks:
            await ctx.send("```❌ 검색 결과가 없습니다.```")
            return
        
        # 검색 결과를 전역 변수에 저장
        ctx.bot.last_spotify_recommendations = tracks
        
        embed = discord.Embed(
            title="🔍 Spotify 검색 결과",
            description=f"'{query}' 검색 결과\n\n**사용법:**\n✅ 자동 재생 (1번 곡)\n1️⃣~5️⃣ 번호 선택 (여러 개 선택 가능)\n.ps <번호> 명령어\n❌ 취소",
            color=0x5DADE2  # 연한 하늘색
        )
        
        for i, track in enumerate(tracks, 1):
            duration_min = track['duration_ms'] // 60000
            duration_sec = (track['duration_ms'] % 60000) // 1000
            duration_str = f"{duration_min}:{duration_sec:02d}"
            
            embed.add_field(
                name=f"{i}. {track['name']}",
                value=f"�� {track['artist']}\n�� {track['album']}\n⏱️ {duration_str}\n🔗 [Spotify에서 듣기]({track['external_url']})",
                inline=False
            )
        
        # 자동 재생 옵션 제공
        message = await ctx.send(embed=embed)
        
        # 모든 이모티콘을 한 번에 추가 (더 빠른 반응을 위해)
        emojis_to_add = ['✅', '❌', '1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣']
        
        # 이모티콘을 병렬로 추가
        emoji_tasks = []
        for emoji in emojis_to_add:
            emoji_tasks.append(message.add_reaction(emoji))
        
        # 모든 이모티콘 추가 완료 대기
        await asyncio.gather(*emoji_tasks, return_exceptions=True)
        
        # 사용자 반응 대기 (개선된 버전)
        selected_tracks = set()  # 선택된 트랙 번호들
        processing_tracks = set()  # 현재 처리 중인 트랙들
        
        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ['✅', '❌', '1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣']
        
        try:
            # 20초 동안 반응 대기
            while True:
                reaction, user = await client.wait_for('reaction_add', timeout=20.0, check=check)
                
                if str(reaction.emoji) == '✅':
                    # 첫 번째 검색 결과 자동 재생
                    if 0 not in processing_tracks:
                        processing_tracks.add(0)
                        # 비동기로 재생 시작 (블로킹하지 않음)
                        asyncio.create_task(play_spotify_track(ctx, tracks, 0))
                    break
                elif str(reaction.emoji) == '❌':
                    await ctx.send("```자동 재생을 취소했습니다.```")
                    break
                elif str(reaction.emoji) in ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣']:
                    # 번호 선택 재생
                    track_index = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣'].index(str(reaction.emoji))
                    
                    if track_index not in selected_tracks and track_index not in processing_tracks:
                        selected_tracks.add(track_index)
                        processing_tracks.add(track_index)
                        
                        # 비동기로 재생 시작 (블로킹하지 않음)
                        asyncio.create_task(play_spotify_track(ctx, tracks, track_index))
                        
                        # 선택된 곡이 5개 이상이면 중단
                        if len(selected_tracks) >= 5:
                            await ctx.send("```5개 곡이 선택되어 재생을 중단합니다.```")
                            break
                    elif track_index in processing_tracks:
                        await ctx.send(f"```{track_index + 1}번 곡은 현재 처리 중입니다. 잠시만 기다려주세요.```")
                    else:
                        await ctx.send(f"```{track_index + 1}번 곡은 이미 선택되었습니다.```")
                
        except asyncio.TimeoutError:
            if selected_tracks:
                await ctx.send(f"```시간 초과! {len(selected_tracks)}개 곡이 재생되었습니다.```")
            else:
                await ctx.send("```시간이 초과되어 자동 재생이 취소되었습니다.```")
        
    except Exception as e:
        await ctx.send(f"```❌ Spotify 검색 중 오류가 발생했습니다: {str(e)}```")

# 번호로 Spotify 추천 곡 재생 명령어 (업데이트)
@client.command(name="ps")
async def play_spotify_by_number(ctx, number: int = None):
    """번호로 Spotify 추천 곡 재생"""
    if not hasattr(ctx.bot, 'last_spotify_recommendations'):
        await ctx.send("```❌ 먼저 .mind 또는 .sp 명령어로 추천을 받아주세요.```")
        return
    
    recommendations = ctx.bot.last_spotify_recommendations
    
    if not number:
        await ctx.send("```사용법: .ps <번호>\n예시: .ps 1 (1번 곡 재생)\n예시: .ps 3 (3번 곡 재생)```")
        return
    
    if number < 1 or number > len(recommendations):
        await ctx.send(f"```❌ 1~{len(recommendations)} 사이의 번호를 입력해주세요.```")
        return
    
    await play_spotify_track(ctx, recommendations, number - 1)

# 현재 재생 중인 곡과 비슷한 음악 추천 명령어
@client.command(name="similar")
async def similar_tracks(ctx):
    """현재 재생 중인 곡과 비슷한 음악 추천"""
    global current_track_info
    
    if not SPOTIFY_AVAILABLE:
        await ctx.send("```❌ Spotify API가 설정되지 않았습니다.```")
        return
    
    if not current_track_info:
        await ctx.send("```❌ 현재 재생 중인 Spotify 곡이 없습니다.\n먼저 .sp 또는 .mind 명령어로 음악을 재생해주세요.```")
        return
    
    await ctx.send("```🔍 현재 곡과 비슷한 음악을 찾는 중...```")
    
    try:
        # 현재 곡과 비슷한 곡들 찾기
        similar_tracks = await spotify_api.get_similar_tracks(
            current_track_info['name'], 
            current_track_info['artist'], 
            limit=5
        )
        
        if not similar_tracks:
            await ctx.send("```❌ 비슷한 음악을 찾을 수 없습니다.```")
            return
        
        # 추천 결과를 전역 변수에 저장
        ctx.bot.last_spotify_recommendations = similar_tracks
        
        embed = discord.Embed(
            title="🎵 비슷한 음악 추천",
            description=f"'{current_track_info['name']}' - {current_track_info['artist']}와 비슷한 음악들\n\n**사용법:**\n✅ 자동 재생 (1번 곡)\n1️⃣~5️⃣ 번호 선택 (여러 개 선택 가능)\n.ps <번호> 명령어\n❌ 취소",
            color=0x5DADE2  # 연한 하늘색
        )
        
        for i, track in enumerate(similar_tracks, 1):
            duration_min = track['duration_ms'] // 60000
            duration_sec = (track['duration_ms'] % 60000) // 1000
            duration_str = f"{duration_min}:{duration_sec:02d}"
            
            embed.add_field(
                name=f"{i}. {track['name']}",
                value=f"🎤 {track['artist']}\n💿 {track['album']}\n⏱️ {duration_str}\n🔗 [Spotify에서 듣기]({track['external_url']})",
                inline=False
            )
        
        # 자동 재생 옵션 제공
        message = await ctx.send(embed=embed)
        
        # 모든 이모티콘을 한 번에 추가
        emojis_to_add = ['✅', '❌', '1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣']
        
        # 이모티콘을 병렬로 추가
        emoji_tasks = []
        for emoji in emojis_to_add:
            emoji_tasks.append(message.add_reaction(emoji))
        
        # 모든 이모티콘 추가 완료 대기
        await asyncio.gather(*emoji_tasks, return_exceptions=True)
        
        # 사용자 반응 대기
        selected_tracks = set()
        processing_tracks = set()
        
        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ['✅', '❌', '1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣']
        
        try:
            # 20초 동안 반응 대기
            while True:
                reaction, user = await client.wait_for('reaction_add', timeout=20.0, check=check)
                
                if str(reaction.emoji) == '✅':
                    # 첫 번째 추천 곡 자동 재생
                    if 0 not in processing_tracks:
                        processing_tracks.add(0)
                        asyncio.create_task(play_spotify_track(ctx, similar_tracks, 0))
                    break
                elif str(reaction.emoji) == '❌':
                    await ctx.send("```자동 재생을 취소했습니다.```")
                    break
                elif str(reaction.emoji) in ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣']:
                    # 번호 선택 재생
                    track_index = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣'].index(str(reaction.emoji))
                    
                    if track_index not in selected_tracks and track_index not in processing_tracks:
                        selected_tracks.add(track_index)
                        processing_tracks.add(track_index)
                        
                        asyncio.create_task(play_spotify_track(ctx, similar_tracks, track_index))
                        
                        if len(selected_tracks) >= 5:
                            await ctx.send("```5개 곡이 선택되어 재생을 중단합니다.```")
                            break
                    elif track_index in processing_tracks:
                        await ctx.send(f"```{track_index + 1}번 곡은 현재 처리 중입니다. 잠시만 기다려주세요.```")
                    else:
                        await ctx.send(f"```{track_index + 1}번 곡은 이미 선택되었습니다.```")
                
        except asyncio.TimeoutError:
            if selected_tracks:
                await ctx.send(f"```시간 초과! {len(selected_tracks)}개 곡이 재생되었습니다.```")
            else:
                await ctx.send("```시간이 초과되어 자동 재생이 취소되었습니다.```")
        
    except Exception as e:
        await ctx.send(f"```❌ 비슷한 음악 찾기 중 오류가 발생했습니다: {str(e)}```")

# 자동 비슷한 곡 재생 모드 토글 명령어
@client.command(name="auto")
async def auto_similar(ctx):
    """현재 재생 중인 곡에서 비슷한 곡 5개를 대기열에 추가"""
    global auto_similar_queue, current_track_info
    
    if not SPOTIFY_AVAILABLE:
        await ctx.send("```❌ Spotify API가 설정되지 않았습니다.```")
        return
    
    if not current_track_info:
        await ctx.send("```❌ 현재 재생 중인 Spotify 곡이 없습니다.\n먼저 .sp 명령어로 Spotify 곡을 재생해주세요.```")
        return
    
    try:
        await ctx.send("```🔄 현재 곡과 비슷한 곡을 찾는 중...```")
        similar_tracks = await spotify_api.get_similar_tracks(
            current_track_info['name'], 
            current_track_info['artist']
        )
        
        if similar_tracks and len(similar_tracks) > 0:
                    # 자동 대기열에 추가
                    added_count = 0
                    failed_count = 0
                    for selected_track in similar_tracks:
                        try:
                            search_query = f"{selected_track['name']} {selected_track['artist']}"
                            url2, title, thumbnail_url = await search_youtube(search_query)
                            
                            if url2:
                                # 자동 대기열에 추가 (일반 대기열이 아닌)
                                auto_similar_queue.append({
                                    'url': url2,
                                    'title': title,
                                    'thumbnail': thumbnail_url,
                                    'info': {
                                        'name': selected_track['name'],
                                        'artist': selected_track['artist'],
                                        'album': selected_track['album'],
                                        'external_url': selected_track['external_url'],
                                        'duration_ms': selected_track['duration_ms']
                                    }
                                })
                                added_count += 1
                            else:
                                failed_count += 1
                                print(f"YouTube에서 곡을 찾을 수 없음: {search_query}")
                        except Exception as e:
                            failed_count += 1
                            print(f"개별 곡 검색 중 오류: {e}")
                            continue
                    
                    if added_count > 0:
                        track_list = "\n".join([f"• {track['name']} - {track['artist']}" for track in similar_tracks[:5]])
                        await ctx.send(f"```✅ {added_count}개의 비슷한 곡이 대기열에 추가되었습니다!\n\n추가된 곡들:\n{track_list}```")
                    else:
                        await ctx.send("```🔄 자동 비슷한 곡 재생 모드가 활성화되었습니다!\n하지만 비슷한 곡을 YouTube에서 찾을 수 없습니다.\n\n특징:\n• 5개씩 미리 준비하여 부드러운 연속 재생\n• Spotify 알고리즘으로 정확한 비슷한 곡 추천\n• 무한 반복 재생 가능\n\n사용법:\n.auto - 모드 토글\n.autostop - 자동 모드만 중단\n.stop - 모든 재생 중단```")
        else:
            await ctx.send("```❌ 비슷한 곡을 찾을 수 없습니다.\n\n이 곡은 Spotify에서 추천을 제공하지 않거나,\n유사한 곡을 찾을 수 없습니다.\n\n다른 곡으로 시도해보세요.```")
    except Exception as e:
        print(f"비슷한 곡 검색 중 오류: {e}")
        await ctx.send("```❌ 비슷한 곡을 찾는 중 오류가 발생했습니다.```")

# 자동 비슷한 곡 재생 모드만 중단하는 명령어
@client.command(name="autostop")
async def auto_similar_mode_stop(ctx):
    """자동 비슷한 곡 재생 모드만 중단"""
    global auto_similar_mode, auto_similar_queue
    
    if not SPOTIFY_AVAILABLE:
        await ctx.send("```❌ Spotify API가 설정되지 않았습니다.```")
        return
    
    if auto_similar_mode:
        auto_similar_mode = False
        auto_similar_queue.clear()  # 자동 대기열도 비움
        await ctx.send("```⏹️ 자동 비슷한 곡 재생 모드가 중단되었습니다.\n현재 재생 중인 곡은 계속 재생됩니다.\n\n자동 대기열도 비워졌습니다.```")
    else:
        await ctx.send("```💡 자동 비슷한 곡 재생 모드가 이미 비활성화되어 있습니다.```")

# Spotify 플레이리스트 재생 명령어
@client.command(name="playlist")
async def spotify_playlist(ctx, *, playlist_url: str = None):
    """Spotify 플레이리스트에서 랜덤 10곡을 재생"""
    if not SPOTIFY_AVAILABLE:
        await ctx.send("```❌ Spotify API가 설정되지 않았습니다.```")
        return
    
    # URL이 없으면 고정 플레이리스트 사용
    if not playlist_url:
        playlist_url = "https://open.spotify.com/playlist/3EFwYCA2ixqyf9n5qIridt?si=a3dee8612ba64320"
    
    await ctx.send("```🎵 Spotify 플레이리스트를 분석하는 중...```")
    

    try:
        # 플레이리스트에서 랜덤 10곡 가져오기
        tracks, playlist_info = await spotify_api.get_playlist_tracks(playlist_url, limit=10)
        
        if not tracks:
            await ctx.send("```❌ 플레이리스트에서 곡을 찾을 수 없습니다.\n\n가능한 원인:\n• 플레이리스트가 비어있음\n• 플레이리스트가 비공개임\n• 잘못된 URL\n\n다른 플레이리스트를 시도해보세요.```")
            return
        
        # 플레이리스트 정보 표시
        embed = discord.Embed(
            title="🎵 Spotify 플레이리스트 재생",
            description=f"**{playlist_info['name']}**\n\n📝 {playlist_info['description'][:100]}{'...' if len(playlist_info['description']) > 100 else ''}\n📊 총 곡 수: {playlist_info['total_tracks']}개\n🎲 랜덤 선택: {len(tracks)}개",
            color=0x5DADE2,  # 연한 하늘색
            url=playlist_info['external_url']
        )
        
        # 선택된 곡들 표시
        track_list = []
        for i, track in enumerate(tracks, 1):
            duration_min = track['duration_ms'] // 60000
            duration_sec = (track['duration_ms'] % 60000) // 1000
            duration_str = f"{duration_min}:{duration_sec:02d}"
            track_list.append(f"{i}. **{track['name']}** - {track['artist']} ({duration_str})")
        
        embed.add_field(
            name="🎲 랜덤 선택된 곡들",
            value="\n".join(track_list),
            inline=False
        )
        
        await ctx.send(embed=embed)
        
        # 음성 채널 연결 확인
        voice = ctx.voice_client
        if not voice or not voice.is_connected():
            if ctx.author.voice:
                try:
                    channel = ctx.author.voice.channel
                    channel_name = safe_channel_name(channel)
                    try:
                        print(f"[디버그] 플레이리스트 재생 - 음성 채널 연결 시도: {channel_name}")
                    except UnicodeEncodeError:
                        print(f"[디버그] 플레이리스트 재생 - 음성 채널 연결 시도: {channel.id}")
                    
                    # 기존 음성 연결이 있다면 정리
                    if ctx.voice_client:
                        try:
                            await ctx.voice_client.disconnect()
                            print(f"[디버그] 플레이리스트 재생 - 기존 음성 연결 정리 완료")
                            await asyncio.sleep(1)
                        except:
                            pass
                    
                    # 재시도 로직
                    max_retries = 3
                    for attempt in range(max_retries):
                        try:
                            voice = await channel.connect()
                            try:
                                print(f"[디버그] 플레이리스트 재생 - 음성 채널 연결 성공: {channel_name}")
                            except UnicodeEncodeError:
                                print(f"[디버그] 플레이리스트 재생 - 음성 채널 연결 성공: {channel.id}")
                            break
                        except Exception as connect_error:
                            print(f"[오류] 플레이리스트 재생 - 음성 채널 연결 시도 {attempt + 1}/{max_retries} 실패: {str(connect_error)}")
                            if attempt < max_retries - 1:
                                wait_time = 5 if "4006" in str(connect_error) else 2
                                print(f"[디버그] 플레이리스트 재생 - {wait_time}초 대기 후 재시도...")
                                await asyncio.sleep(wait_time)
                            else:
                                raise connect_error
                                
                except Exception as e:
                    print(f"[오류] 플레이리스트 재생 - 음성 채널 연결 최종 실패: {str(e)}")
                    await ctx.send(f"```❌ 음성 채널 연결에 실패했습니다.\n네트워크 문제일 수 있습니다. 잠시 후 다시 시도해주세요.```")
                    return
            else:
                await ctx.send("```음성 채널에 먼저 접속해주세요.```")
                return
        
        # 병렬로 모든 트랙의 URL을 미리 가져오기
        await ctx.send("```🔄 YouTube에서 곡들을 병렬로 검색하는 중... (더 빠름!)```")
        
        # 병렬 URL 추출 (최대 3개 동시)
        prefetch_results = await prefetch_urls_parallel(tracks, max_concurrent=3)
        
        added_count = 0
        failed_count = len(tracks) - len(prefetch_results)
        
        # 성공한 결과를 playlist_queue에 추가 (원래 순서대로)
        prefetch_results.sort(key=lambda x: x[0])  # index 기준 정렬
        
        for result in prefetch_results:
            # 루프 중간에 이벤트 루프에 제어권 넘김 (heartbeat 유지)
            # 0.1초 대기로 Discord heartbeat가 확실히 작동하도록 함
            await asyncio.sleep(0.1)
            
            index, url2, title, thumbnail_url, video_id, success = result
            if success and url2:
                playlist_queue.append((url2, title, thumbnail_url, video_id))
                added_count += 1
                try:
                    print(f"[디버그] 플레이리스트 곡 {index+1}/{len(tracks)} 추가 성공: {title}")
                except UnicodeEncodeError:
                    print(f"[디버그] 플레이리스트 곡 {index+1}/{len(tracks)} 추가 성공")
        
        # 결과 요약
        if added_count > 0:
            await ctx.send(f"```✅ 플레이리스트에서 {added_count}개 곡을 큐에 추가했습니다!\n\n📊 결과:\n• 성공: {added_count}개\n• 실패: {failed_count}개\n• 플레이리스트 큐: {len(playlist_queue)}개```")
            
            # 현재 재생 중이 아니라면 첫 번째 곡 재생
            if not voice.is_playing() and playlist_queue:
                await play_next(ctx)
        else:
            await ctx.send("```❌ 플레이리스트에서 재생 가능한 곡을 찾을 수 없습니다.\n\nYouTube에서 해당 곡들을 찾을 수 없었습니다.\n다른 플레이리스트를 시도해보세요.```")
        
    except Exception as e:
        print(f"[디버그] 플레이리스트 재생 중 오류: {e}")
        await ctx.send(f"```❌ 플레이리스트 재생 중 오류가 발생했습니다: {str(e)[:200]}...```")

async def graceful_shutdown():
    """안전한 종료 - 리소스 정리"""
    print("[종료] 안전한 종료를 시작합니다...")
    
    # 1. 음성 연결 정리
    try:
        for vc in client.voice_clients:
            if vc.is_connected():
                if vc.is_playing():
                    vc.stop()
                await vc.disconnect()
                print(f"[종료] 음성 연결 해제: {vc.guild.name if vc.guild else 'Unknown'}")
    except Exception as e:
        print(f"[종료] 음성 연결 정리 중 오류: {e}")
    
    # 2. ProcessPoolExecutor 정리
    try:
        yt_executor.shutdown(wait=False, cancel_futures=True)
        print("[종료] yt_executor 정리 완료")
    except Exception as e:
        print(f"[종료] executor 정리 중 오류: {e}")
    
    # 3. 대기열 비우기
    queue.clear()
    playlist_queue.clear()
    auto_similar_queue.clear()
    print("[종료] 대기열 정리 완료")
    
    # 4. 클라이언트 종료
    try:
        await client.close()
        print("[종료] Discord 클라이언트 종료 완료")
    except Exception as e:
        print(f"[종료] 클라이언트 종료 중 오류: {e}")
    
    print("[종료] 안전한 종료 완료!")


def signal_handler(signum, frame):
    """시그널 핸들러 (SIGTERM, SIGINT)"""
    print(f"\n[종료] 시그널 {signum} 수신, 종료 시작...")
    
    try:
        # 이벤트 루프에서 graceful_shutdown 실행
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(graceful_shutdown())
        else:
            loop.run_until_complete(graceful_shutdown())
    except Exception as e:
        print(f"[종료] 시그널 핸들러 오류: {e}")
    finally:
        sys.exit(0)


if __name__ == "__main__":
    import signal
    
    # 시그널 핸들러 등록 (안전한 종료)
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        print("[시작] 봇을 시작합니다...")
        client.run(TOKEN)
    except KeyboardInterrupt:
        print("\n[종료] 키보드 인터럽트 감지...")
        asyncio.get_event_loop().run_until_complete(graceful_shutdown())
        sys.exit(0)
    except Exception as e:
        print(f"[오류] 예상치 못한 오류: {str(e)}")
        try:
            asyncio.get_event_loop().run_until_complete(graceful_shutdown())
        except:
            pass
        sys.exit(1)
        sys.exit(1)