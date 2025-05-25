import discord
import sys
import os
import yt_dlp as youtube_dl
import asyncio
import requests
import json
import subprocess
import base64
from discord import File, FFmpegPCMAudio
from io import BytesIO
from PIL import Image, ImageDraw
from discord.ext import commands

# Token 파일 경로 설정
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

try:
    from disco_token import Token
    print("[디버그] Token 임포트 성공")
except Exception as e:
    print(f"[디버그] Token 임포트 실패: {str(e)}")
    print(f"[디버그] 현재 디렉토리: {os.getcwd()}")
    print(f"[디버그] sys.path: {sys.path}")
    sys.exit(1)

# 딥시크 API
DEEPSEEK_API_KEY = "sk-27dae9be93c648bb8805a793438f6eb5"
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"

intents = discord.Intents.default()
intents.message_content = True  

client = commands.Bot(command_prefix='.', intents=intents, case_insensitive=True)

# 봇 실행 상태 플래그
is_bot_running = False

queue = []  # 재생 대기열
current_track = None  # 현재 재생 중인 곡
is_playing = False  # 현재 재생 중인지 여부
current_voice_client = None 

# FFmpeg 옵션
FFMPEG_OPTIONS = {
    'executable': 'C:\\Program Files (x86)\\ffmpeg-2024-10-13-git-e347b4ff31-essentials_build\\bin\\ffmpeg.exe',
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

# Youtube-dl 옵션
ydl_opts = {
    'quiet': False,
    'format': 'bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    'youtube_include_dash_manifest': False,
}

# 봇 준비 이벤트
@client.event
async def on_ready():
    print(f'Logged in as {client.user}')

# 음성 채널 연결 함수
async def join(ctx):
    if ctx.voice_client is None:  
        if ctx.author.voice:  
            channel = ctx.author.voice.channel
            await channel.connect()  # 음성 채널에 연결``
            await ctx.send(f"{ctx.author.mention} 음성 채널에 연결되었습니다.")
        else:
            await ctx.send("먼저 음성 채널에 접속해주세요.")
            return None
    else:
        await ctx.send(f"{ctx.author.mention} 봇은 이미 음성 채널에 연결되어 있습니다.")
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
    ydl_opts = {}
    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        return info.get('id')  # video_id 반환

@client.command(aliases=['p'])
async def play(ctx, *, search_or_url: str = None):  
    global current_track
    voice = ctx.voice_client

    # 봇이 음성 채널에 연결되지 않은 경우 연결
    if not voice:
        if ctx.author.voice:  
            channel = ctx.author.voice.channel
            voice = await channel.connect()
        else:
            await ctx.send("먼저 음성 채널에 접속해주세요.")
            return

    # 일시정지된 상태라면 다시 재생
    if voice and voice.is_paused():
        voice.resume()
        await ctx.send(f"{ctx.author.mention} 일시정지된 음악을 다시 재생합니다.")
        return

    if search_or_url:
        # URL로 입력된 경우``
        if search_or_url.startswith("http"):
            # youtube_dl을 사용해 URL에서 정보를 추출
            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(search_or_url, download=False)
                url2 = info['url']
                title = info.get('title', '알 수 없는 제목')
                thumbnail_url = info.get('thumbnail')  # YouTube 썸네일 URL
                video_id = info.get('id')  # video_id 추출
        else:  # 검색어로 입력된 경우
            url2, title = await search_youtube(search_or_url)
            video_id = extract_video_id(url2)  # video_id 추출

        if not url2:
            await ctx.send("검색 결과가 없습니다.")
            return

        # 현재 곡이 재생 중이라면 큐에 추가
        if voice.is_playing():
            queue.append((url2, title))  
            await ctx.send(f"'{title}'가 목록에 추가되었습니다! 현재 목록: {len(queue)}개")
        else:
            
            data = {
            # "imageBg": heal_song, 
            "imageText": title,
            "songArtist": "아티스트 이름",
            "trackDuration": 0,
            "trackTotalDuration": 0,
            "trackStream": False,
        }

        # # song card 생성
        #     card_image = generate_song_card(data)
        #     await ctx.send(file=File(card_image, "card.png"))

            # 음악 재생 로직
            source = FFmpegPCMAudio(url2, **FFMPEG_OPTIONS)
            current_track = title
            voice.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), client.loop))
            await ctx.send(f"지금 재생 중: {title}")
                    
            # source = FFmpegPCMAudio(url2, **FFMPEG_OPTIONS)
            # current_track = title
            # voice.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), client.loop))
            # await ctx.send(f"지금 재생 중: {title}")
    else:
        await ctx.send("URL 또는 검색어를 입력해주세요.")

@client.command()
async def q(ctx):
    global current_track
    voice = ctx.voice_client

    if current_track:
        await ctx.send(f"현재 재생 중인 곡: {current_track}")
    else:
        await ctx.send("현재 재생 중인 곡이 없습니다.")

    
    if queue:
        titles = [f"{idx + 1}. {item[1]}" for idx, item in enumerate(queue)]
        await ctx.send("재생 목록:\n" + "\n".join(titles))
    else:
        await ctx.send("현재 재생 목록이 비어 있습니다.")

@client.command()
async def stop(ctx):
    global is_playing, queue, current_track

    queue.clear()  # 큐를 비움
    is_playing = False  # 재생 상태 초기화
    current_track = None  # 현재 재생 중인 곡 초기화

    voice = ctx.voice_client  # 현재 서버의 음성 클라이언트 가져오기

    if voice and voice.is_connected():
        await voice.disconnect()  # 음성 채널에서 나가기
        await ctx.send("재생이 중단되었습니다. 음성 채널에서 나갑니다.")
    else:
        await ctx.send("봇이 음성 채널에 연결되어 있지 않습니다.")

@client.command()
async def pause(ctx):
    voice = ctx.voice_client  

    if voice and voice.is_playing():  
        voice.pause()  
        await ctx.send(f"{ctx.author.mention} 플레이어를 일시정지했습니다.")
    else:
        await ctx.send(f"{ctx.author.mention} 현재 재생 중인 곡이 없습니다.")
@client.command()
async def resume(ctx):
    voice = ctx.voice_client  

    if voice and voice.is_paused():  
        voice.resume() 
        await ctx.send(f"{ctx.author.mention} 음악을 계속 재생합니다.")
    else:
        await ctx.send(f"{ctx.author.mention} 현재 일시정지된 곡이 없습니다.")

@client.command()
async def skip(ctx):
    voice = ctx.voice_client  # 현재 서버의 음성 클라이언트 참조

    if voice and voice.is_playing():
        voice.stop() 
        await ctx.send("다음 곡으로 넘어갑니다.")
    else:
        await ctx.send("현재 재생 중인 곡이 없습니다.")

async def play_next(ctx):
    global is_playing, current_track

    if  len(queue) == 0:  # 재생할 곡이 없는 경우
        is_playing = False
        current_track = None
        await ctx.send("재생할 곡이 더 이상 없습니다.")

        # # 3분 후 음성 채널 나가기
        # await asyncio.sleep(180)
        # if not is_playing and ctx.voice_client:  # 여전히 재생 중이 아니라면
        #     await ctx.voice_client.disconnect()
        #     await ctx.send("3분 동안 아무 곡도 재생되지않으니 나간다잉")

        return

    if ctx.voice_client is None:  
        await join(ctx)

    is_playing = True
    url, title = queue.pop(0)  
    current_track = title

    # 다음 곡 재생
    source = FFmpegPCMAudio(url, **FFMPEG_OPTIONS)
    ctx.voice_client.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), client.loop))
    await ctx.send(f"지금 재생 중: {title}")

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
    }

    with youtube_dl.YoutubeDL(ydl_opts_search) as ydl:
        info = ydl.extract_info(f"ytsearch:{query}", download=False)
        if 'entries' in info and len(info['entries']) > 0:
            first_result = info['entries'][0]
            return first_result['url'], first_result['title']
        else:
            return None, None
        
# 번역 함수
def translate_text(text, target_lang):
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    # 프롬프트 설정 (예: "Translate the following text into Japanese: Hello")
    prompt = f"Translate the following text into {target_lang}: {text}"
    data = {
        "model": "deepseek-chat",  # 사용할 모델 이름 (문서 참고)
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,  # 창의성 조절 (0 ~ 1)
        "max_tokens": 1000  # 최대 토큰 수
    }
    try:
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=data)
        if response.status_code == 200:
            # 응답에서 번역된 텍스트 추출
            translated_text = response.json()["choices"][0]["message"]["content"]
            return translated_text
        else:
            return f"번역 실패: 상태 코드 {response.status_code}, 응답: {response.text}"
    except Exception as e:
        return f"API 호출 중 오류 발생: {str(e)}"
# 검색 함수
def search_and_summarize(query):
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    # 프롬프트 설정 (예: "Search and summarize the following query: What is AI?")
    prompt = f"Search and summarize the following query in a concise way: {query}"
    data = {
        "model": "deepseek-chat",  # 사용할 모델 이름 (문서 참고)
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,  # 창의성 조절 (0 ~ 1)
        "max_tokens": 500  # 최대 토큰 수 (요약 결과 길이 제한)
    }
    try:
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=data)
        if response.status_code == 200:
            # 응답에서 검색 결과 및 요약 추출
            result = response.json()["choices"][0]["message"]["content"]
            return result
        else:
            return f"검색 실패: 상태 코드 {response.status_code}, 응답: {response.text}"
    except Exception as e:
        return f"API 호출 중 오류 발생: {str(e)}"
    return summary

# 명령어: 한국어, 영어, 일본어 → 일본어로 번역
@client.command(name="jp")
async def translate_to_japanese(ctx, *, text):
    translated_text = translate_text(text, "Japanese")  # 타겟 언어를 일본어로 설정
    await ctx.send(f" {translated_text}")

# 명령어: 일본어 → 한국어 번역
@client.command(name="kr")
async def translate_to_korean(ctx, *, text):
    translated_text = translate_text(text, "Korean")  # 타겟 언어를 한국어로 설정
    await ctx.send(f" {translated_text}")

# 명령어: 한국어 → 영어 번역
@client.command(name="en")
async def translate_to_english(ctx, *, text):
    translated_text = translate_text(text, "English")  # 타겟 언어를 영어로 설정
    await ctx.send(f" {translated_text}")

@client.command(name="search")
async def search(ctx, *, query):
    # 검색 및 요약 실행
    search_result = search_and_summarize(query)
    # 출력 길이 제한 (예: 200자)
    if len(search_result) > 200:
        search_result = search_result[:200] + "..."
    # 결과 출력
    await ctx.send(f"검색 결과: {search_result}")

if __name__ == "__main__":
    try:
        client.run(Token)
    except KeyboardInterrupt:
        print("봇을 종료합니다...")
        sys.exit(0)
    except Exception as e:
        print(f"오류 발생: {str(e)}")
        sys.exit(1)