import discord
import sys
import os
import yt_dlp as youtube_dl
import asyncio

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from discord.ext import commands
from disco_token import Token
from discord import FFmpegPCMAudio

intents = discord.Intents.default()
intents.message_content = True  

client = commands.Bot(command_prefix='./', intents=intents)

queue = []  # 재생 대기열
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
    if ctx.voice_client is None:  # 봇이 음성 채널에 연결되어 있지 않은 경우
        if ctx.author.voice:  # 사용자가 음성 채널에 있는지 확인
            channel = ctx.author.voice.channel
            await channel.connect()  # 음성 채널에 연결
            await ctx.send(f"{ctx.author.mention} 음성 채널에 연결되었습니다.")
        else:
            await ctx.send("먼저 음성 채널에 접속해주세요.")
            return None
    else:
        await ctx.send(f"{ctx.author.mention} 봇은 이미 음성 채널에 연결되어 있습니다.")
    return ctx.voice_client  # 이미 연결된 경우 현재 음성 클라이언트를 반환



@client.command(aliases=['p'])
async def play(ctx, url: str = None):
    voice = ctx.voice_client

    # 봇이 음성 채널에 연결되지 않은 경우 연결
    if not voice:
        if ctx.author.voice:  # 사용자가 음성 채널에 있는지 확인
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

    # 새로운 URL이 입력된 경우
    if url:
        # Use youtube_dl to extract the information and the URL for the audio
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            url2 = info['url']
            title = info['title']  # Get the title of the song

            if voice.is_playing():
                queue.append((url2, title))  
                await ctx.send(f"'{title}'가 목록에 추가되었습니다! 현재 목록: {len(queue)}개")
            else:
                # 재생 중인 곡이 없으면 바로 재생
                source = FFmpegPCMAudio(url2, **FFMPEG_OPTIONS)
                voice.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), client.loop))
                await ctx.send(f"지금 재생 중: {title}")
    else:
        await ctx.send("URL을 입력해주세요.")

@client.command()
async def skip(ctx):
    voice = ctx.voice_client  # 현재 서버의 음성 클라이언트 참조

    if voice and voice.is_playing():
        voice.stop() 
        await ctx.send("다음 곡으로 넘어갑니다.")
    else:
        await ctx.send("현재 재생 중인 곡이 없습니다.")

async def play_next(ctx):
    global is_playing

    if len(queue) == 0:  # 재생할 곡이 없는 경우
        is_playing = False
        await ctx.send("재생할 곡이 더 이상 없습니다.")
        return

    if ctx.voice_client is None:  # 음성 클라이언트가 없는 경우 연결
        await join(ctx)

    is_playing = True
    url, title = queue.pop(0)  # 큐에서 다음 곡을 꺼냄

    # 다음 곡 재생
    source = FFmpegPCMAudio(url, **FFMPEG_OPTIONS)
    ctx.voice_client.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), client.loop))
    await ctx.send(f"지금 재생 중: {title}")

@client.command()
async def q(ctx):
    if queue:
        await ctx.send(f"현재 목록: {len(queue)}개 곡이 대기 중입니다.")
        titles = [f"{idx + 1}. {item[1]}" for idx, item in enumerate(queue)]
        await ctx.send("재생 목록:\n" + "\n".join(titles))
    else:
        await ctx.send("현재 재생 목록이 비어 있습니다.")


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
async def pause(ctx):
    voice = ctx.voice_client  # 현재 음성 클라이언트를 가져옴

    if voice and voice.is_playing():  # 봇이 음성 채널에 연결되어 있고, 재생 중인지 확인
        voice.pause()  # 재생 중인 곡을 일시정지
        await ctx.send(f"{ctx.author.mention} 플레이어를 일시정지했습니다.")
    else:
        await ctx.send(f"{ctx.author.mention} 현재 재생 중인 곡이 없습니다.")
@client.command()
async def resume(ctx):
    voice = ctx.voice_client  # 현재 음성 클라이언트를 가져옴

    if voice and voice.is_paused():  # 봇이 음성 채널에 연결되어 있고, 곡이 일시정지 상태인지 확인
        voice.resume()  # 일시정지된 곡을 다시 재생
        await ctx.send(f"{ctx.author.mention} 음악을 계속 재생합니다.")
    else:
        await ctx.send(f"{ctx.author.mention} 현재 일시정지된 곡이 없습니다.")




client.run(Token)

# ./q 에서 재생목록을 보면현재재생중인것도 뜨게하기