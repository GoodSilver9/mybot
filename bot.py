import discord
import sys
import os
import yt_dlp as youtube_dl
import asyncio

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from discord.ext import commands
from disco_token import Token
from discord import FFmpegPCMAudio

# Intents 설정 (필수)
intents = discord.Intents.default()
intents.message_content = True  # 메시지 내용을 읽을 수 있도록 설정

# 봇 생성
client = commands.Bot(command_prefix='./', intents=intents)

# 플레이리스트와 현재 상태 관리
queue = []  # 재생 대기열
is_playing = False  # 현재 재생 중인지 여부
current_voice_client = None  # 현재 연결된 음성 채널

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
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        return await channel.connect()
    else:
        await ctx.send("먼저 음성 채널에 접속해주세요.")
        return None

# 재생 함수 (큐에서 노래를 재생)
async def play_next(ctx):
    global is_playing, current_voice_client

    if queue:  # 큐에 노래가 있으면
        is_playing = True
        url = queue.pop(0)  # 큐에서 첫 번째 곡을 가져옴
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            url2 = info['url']
            source = FFmpegPCMAudio(executable=FFMPEG_OPTIONS['executable'], source=url2, before_options=FFMPEG_OPTIONS['before_options'], options=FFMPEG_OPTIONS['options'])

            if not current_voice_client:
                current_voice_client = await join(ctx)
            current_voice_client.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), client.loop))
            await ctx.send(f"지금 재생 중: {info['title']}")
    else:
        is_playing = False
        if current_voice_client:
            await current_voice_client.disconnect()
            current_voice_client = None

# 노래 추가 및 재생 명령어
@client.command()
async def play(ctx, url: str):
    global is_playing

    queue.append(url)
    await ctx.send(f"노래가 목록에 추가되었습니다! 현재 목록: {len(queue)}개")

    if not is_playing:
        await play_next(ctx)

# 현재 목록 확인 명령어
@client.command()
async def queue_list(ctx):
    if queue:
        await ctx.send(f"현재 목록: {len(queue)}개 곡이 대기 중입니다.")
    else:
        await ctx.send("현재 재생 목록이 비어 있습니다.")

# 정지 명령어
@client.command()
async def stop(ctx):
    global is_playing, queue, current_voice_client

    queue.clear()  # 큐를 비우고
    is_playing = False
    if current_voice_client:
        await current_voice_client.disconnect()  # 음성 채널에서 나가기
        current_voice_client = None
    await ctx.send("재생이 중단되었습니다.")
@client.command()
async def skip(ctx):
    global current_voice_client

    if current_voice_client and current_voice_client.is_playing():
        current_voice_client.stop()  # 현재 재생 중인 곡을 멈추면 play_next 함수가 자동 호출됨
        await ctx.send("다음 곡으로 넘어갑니다.")
    else:
        await ctx.send("현재 재생 중인 곡이 없습니다.")

# 봇 실행
client.run(Token)
