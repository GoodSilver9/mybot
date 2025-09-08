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
from discord import File, FFmpegPCMAudio
from io import BytesIO
from PIL import Image, ImageDraw
from discord.ext import commands

# yt-dlp 자동 업데이트 함수
def update_yt_dlp():
    try:
        print("[시스템] yt-dlp 업데이트를 확인하는 중...")
        result = subprocess.run([sys.executable, '-m', 'pip', 'install', '-U', 'yt-dlp'], 
                              capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0:
            print("[시스템] yt-dlp 업데이트 완료!")
            return True
        else:
            print(f"[경고] yt-dlp 업데이트 실패: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        print("[경고] yt-dlp 업데이트 시간 초과 (60초)")
        return False
    except Exception as e:
        print(f"[경고] yt-dlp 업데이트 중 오류: {str(e)}")
        return False

# 봇 시작 시 yt-dlp 업데이트 실행
print("[시스템] 봇 시작 중...")
update_yt_dlp()

# Token 파일 경로 설정
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

# env_tokens.txt 파일에서 토큰 읽기
def load_tokens_from_file():
    tokens = {}
    env_file_path = os.path.join(parent_dir, 'env_tokens.txt')
    
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
        print(f"[오류] env_tokens.txt 파일을 찾을 수 없습니다: {env_file_path}")
        return {}
    except Exception as e:
        print(f"[오류] env_tokens.txt 파일 읽기 실패: {str(e)}")
        return {}

# 토큰 로드
tokens = load_tokens_from_file()
TOKEN = tokens.get('DISCORD_BOT_TOKEN')

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
        print(f"[디버그] 모든 토큰 소스에서 실패: {str(e)}")
        print(f"[디버그] 현재 디렉토리: {os.getcwd()}")
        print(f"[디버그] sys.path: {sys.path}")
        print("[경고] 토큰을 찾을 수 없습니다. env_tokens.txt 파일을 확인하세요.")
        sys.exit(1)
else:
    print("[디버그] env_tokens.txt에서 토큰을 로드했습니다.")

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
    print(f"[디버그] Spotify Client ID: {SPOTIFY_CLIENT_ID[:10]}..." if SPOTIFY_CLIENT_ID else "[경고] Spotify Client ID 없음")
except ImportError as e:
    SPOTIFY_AVAILABLE = False
    print(f"[경고] Spotify API 통합 모듈 로드 실패: {e}")

intents = discord.Intents.default()
intents.message_content = True  

client = commands.Bot(command_prefix='.', intents=intents, case_insensitive=True)

# 봇 실행 상태 플래그
is_bot_running = False

queue = []  # 재생 대기열
current_track = None  # 현재 재생 중인 곡
is_playing = False  # 현재 재생 중인지 여부
current_voice_client = None 
disconnect_task = None  # 자동 퇴장 타이머를 위한 변수

# FFmpeg 옵션 (안정성 개선)
FFMPEG_OPTIONS = {
    'executable': 'C:\\Program Files (x86)\\ffmpeg-2024-10-13-git-e347b4ff31-essentials_build\\bin\\ffmpeg.exe',
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -timeout 30000000 -nostdin',
    'options': '-vn -b:a 128k -bufsize 4096k -maxrate 256k -loglevel error -avoid_negative_ts make_zero -fflags +discardcorrupt'
}

# Youtube-dl 옵션
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
}

# 봇 준비 이벤트
@client.event
async def on_ready():
    print(f'Logged in as {client.user}')

# 음성 연결 상태 모니터링
@client.event
async def on_voice_state_update(member, before, after):
    # 봇이 음성 채널에서 혼자 남겨진 경우 자동 퇴장
    if member == client.user:
        return
    
    voice_client = client.voice_clients
    for vc in voice_client:
        if vc.channel and len(vc.channel.members) == 1:  # 봇만 남은 경우
            await asyncio.sleep(5)  # 5초 대기 후 확인
            if len(vc.channel.members) == 1:  # 여전히 혼자면 퇴장
                await vc.disconnect()
                print("음성 채널에 혼자 남아 자동 퇴장했습니다.")

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

def extract_video_id(url):
    ydl_opts = {'quiet': True, 'no_warnings': True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info.get('id') if info else None
    except Exception as e:
        print(f"video_id 추출 중 오류: {e}")
        return None

@client.command(aliases=['p'])
async def play(ctx, *, search_or_url: str = None):  
    global current_track, disconnect_task

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
                voice = await channel.connect()
                await ctx.send(f"``` 음성 채널에 연결되었습니다.```")
            except Exception as e:
                await ctx.send(f"```음성 채널 연결 중 오류가 발생했습니다: {str(e)}```")
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
                                await ctx.send("```플레이리스트는 최대 10개의 곡까지만 지원합니다. 더 적은 수의 곡을 선택해주세요.```")
                                return
                            elif playlist_count > 1:
                                await ctx.send(f"```플레이리스트에서 {playlist_count}개의 곡을 추가합니다...```")
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
                                    
                                    # 음성 연결 상태 재확인
                                    if not voice or not voice.is_connected():
                                        await ctx.send("```음성 연결이 끊어졌습니다. 다시 연결해주세요.```")
                                        return
                                    
                                    # 현재 곡이 재생 중이라면 큐에 추가
                                    if voice.is_playing():
                                        queue.append((url2, title))
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
                                            await ctx.send(f"```지금 재생 중: {title}```")
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
                            await ctx.send(f"```플레이리스트에서 {added_count}개의 곡을 추가했습니다!```")
                        else:
                            await ctx.send("```플레이리스트에서 곡을 추가할 수 없습니다.```")
                        return
                    else:
                        # 단일 곡인 경우
                        url2 = info['url']
                        title = info.get('title', '알 수 없는 제목')
                        thumbnail_url = info.get('thumbnail')  # YouTube 썸네일 URL
                        video_id = info.get('id')  # video_id 추출
            else:  # 검색어로 입력된 경우
                url2, title = await search_youtube(search_or_url)
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

            # 현재 곡이 재생 중이라면 큐에 추가
            if voice.is_playing():
                queue.append((url2, title))  
                await ctx.send(f"```'{title}'가 목록에 추가되었습니다! 현재 목록: {len(queue)}개```")
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
                    
                    def after_play(error):
                        if error:
                            print(f"재생 완료 후 오류: {error}")
                        asyncio.run_coroutine_threadsafe(play_next(ctx), client.loop)
                    
                    voice.play(source, after=after_play)
                    await ctx.send(f"```지금 재생 중: {title}```")
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
    global current_track
    voice = ctx.voice_client

    if current_track:
        await ctx.send(f"```현재 재생 중인 곡: {current_track}```")
    else:
        await ctx.send("```현재 재생 중인 곡이 없습니다.```")

    
    if queue:
        # 큐가 너무 길면 나누어서 표시
        if len(queue) > 10:
            titles = [f"{idx + 1}. {item[1]}" for idx, item in enumerate(queue[:10])]
            await ctx.send("```재생 목록 (처음 10개):\n" + "\n".join(titles) + f"\n... 그리고 {len(queue) - 10}개 더```")
        else:
            titles = [f"{idx + 1}. {item[1]}" for idx, item in enumerate(queue)]
            await ctx.send("```재생 목록:\n" + "\n".join(titles) + "```")
    else:
        await ctx.send("```현재 재생 목록이 비어 있습니다.```")

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
    global is_playing, queue, current_track

    queue.clear()  # 큐를 비움
    is_playing = False  # 재생 상태 초기화
    current_track = None  # 현재 재생 중인 곡 초기화

    voice = ctx.voice_client  # 현재 서버의 음성 클라이언트 가져오기

    if voice and voice.is_connected():
        await voice.disconnect()  # 음성 채널에서 나가기
        await ctx.send("```재생이 중단되었습니다. 음성 채널에서 나갑니다.```")
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
    else:
        await ctx.send("```현재 재생 중인 곡이 없습니다.```")

async def play_next(ctx):
    global is_playing, current_track, disconnect_task

    if len(queue) == 0:  # 재생할 곡이 없는 경우
        is_playing = False
        current_track = None
        await ctx.send("```재생할 곡이 더 이상 없습니다.```")
        
        # 5분 후 자동 퇴장 타이머 설정
        # async def disconnect_after_timeout():
        #     try:
        #         await asyncio.sleep(300)  # 5분 대기
        #         if ctx.voice_client and ctx.voice_client.is_connected() and not is_playing:
        #             await ctx.voice_client.disconnect()
        #             await ctx.send("```5분 동안 아무 곡도 재생되지 않아 음성 채널에서 나갑니다.```")
        #     except asyncio.CancelledError:
        #         pass  # 타이머가 취소된 경우
        #     except Exception as e:
        #         print(f"자동 퇴장 중 오류: {e}")
        
        # # 이전 타이머가 있다면 취소
        # if disconnect_task:
        #     disconnect_task.cancel()
        
        # # 새로운 타이머 시작
        # disconnect_task = asyncio.create_task(disconnect_after_timeout())
        return

    # 음성 연결 상태 확인
    if ctx.voice_client is None or not ctx.voice_client.is_connected():
        await ctx.send("```음성 연결이 끊어졌습니다. 다시 연결해주세요.```")
        return

    try:
        is_playing = True
        url, title = queue.pop(0)  
        current_track = title

        # 다음 곡 재생
        try:
            source = FFmpegPCMAudio(url, **FFMPEG_OPTIONS)
            
            def after_play(error):
                if error:
                    print(f"다음 곡 재생 완료 후 오류: {error}")
                asyncio.run_coroutine_threadsafe(play_next(ctx), client.loop)
            
            ctx.voice_client.play(source, after=after_play)
            await ctx.send(f"```지금 재생 중: {title}```")
        except Exception as play_error:
            print(f"다음 곡 재생 중 오류: {play_error}")
            await ctx.send(f"```다음 곡 재생 중 오류가 발생했습니다.\n'{title}' 건너뛰고 다음 곡을 재생합니다.```")
            # 오류가 발생한 경우 다음 곡으로 넘어가기
            await play_next(ctx)
    except Exception as e:
        print(f"다음 곡 재생 중 오류: {e}")
        await ctx.send(f"```다음 곡 재생 중 오류가 발생했습니다: {str(e)}```")
        # 오류가 발생한 경우 다음 곡으로 넘어가기
        await play_next(ctx)

async def search_youtube(query):
    ydl_opts_search = {
        'quiet': True,
        'format': 'bestaudio/best',
        'default_search': 'ytsearch',  
        'noplaylist': True,  
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'youtube_include_dash_manifest': False,
        'no_warnings': True,
    }

    # 재시도 로직 (최대 3번)
    for attempt in range(3):
        try:
            with yt_dlp.YoutubeDL(ydl_opts_search) as ydl:
                info = ydl.extract_info(f"ytsearch:{query}", download=False)
                if 'entries' in info and len(info['entries']) > 0:
                    first_result = info['entries'][0]
                    if first_result and 'url' in first_result and 'title' in first_result:
                        return first_result['url'], first_result['title']
                return None, None
        except Exception as e:
            print(f"YouTube 검색 중 오류 (시도 {attempt + 1}/3): {e}")
            if attempt < 2:  # 마지막 시도가 아니면 1초 대기 후 재시도
                await asyncio.sleep(1)
                continue
            return None, None
        
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
    if track_index >= len(recommendations):
        await ctx.send("```❌ 잘못된 번호입니다.```")
        return
    
    selected_track = recommendations[track_index]
    search_query = f"{selected_track['name']} {selected_track['artist']}"
    
    await ctx.send(f"```�� '{search_query}' 재생을 시작합니다!```")
    
    # 기존 play 명령어 로직 사용
    url2, title = await search_youtube(search_query)
    if url2:
        voice = ctx.voice_client
        if not voice or not voice.is_connected():
            if ctx.author.voice:
                channel = ctx.author.voice.channel
                voice = await channel.connect()
            else:
                await ctx.send("```음성 채널에 먼저 접속해주세요.```")
                return
        
        if voice.is_playing():
            queue.append((url2, title))
            await ctx.send(f"```'{title}'가 목록에 추가되었습니다!```")
        else:
            source = FFmpegPCMAudio(url2, **FFMPEG_OPTIONS)
            voice.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), client.loop))
            await ctx.send(f"```지금 재생 중: {title}```")
    else:
        await ctx.send("```❌ YouTube에서 해당 곡을 찾을 수 없습니다.```")

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
            color=0x1DB954  # Spotify 그린
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
            color=0x1DB954
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

if __name__ == "__main__":
    try:
        client.run(TOKEN)
    except KeyboardInterrupt:
        print("봇을 종료합니다...")
        # 음성 연결 정리
        try:
            for vc in client.voice_clients:
                if vc.is_connected():
                    client.loop.run_until_complete(vc.disconnect())
        except Exception as e:
            print(f"음성 연결 정리 중 오류: {e}")
        
        # 클라이언트 정리
        try:
            client.loop.run_until_complete(client.close())
        except Exception as e:
            print(f"클라이언트 정리 중 오류: {e}")
        
        sys.exit(0)
    except Exception as e:
        print(f"오류 발생: {str(e)}")
        # 에러 발생 시에도 정리
        try:
            for vc in client.voice_clients:
                if vc.is_connected():
                    client.loop.run_until_complete(vc.disconnect())
        except:
            pass
        try:
            client.loop.run_until_complete(client.close())
        except:
            pass
        sys.exit(1)