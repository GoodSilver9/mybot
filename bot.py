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

client = commands.Bot(command_prefix='.', intents=intents, case_insensitive=True)

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
            await channel.connect()  # 음성 채널에 연결
            await ctx.send(f"{ctx.author.mention} 음성 채널에 연결되었습니다.")
        else:
            await ctx.send("먼저 음성 채널에 접속해주세요.")
            return None
    else:
        await ctx.send(f"{ctx.author.mention} 봇은 이미 음성 채널에 연결되어 있습니다.")
    return ctx.voice_client  


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
        # URL로 입력된 경우
        if search_or_url.startswith("http"):
            # youtube_dl을 사용해 URL에서 정보를 추출
            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(search_or_url, download=False)
                url2 = info['url']
                title = info.get('title', '알 수 없는 제목')
        else:  # 검색어로 입력된 경우
            url2, title = await search_youtube(search_or_url)

        if not url2:
            await ctx.send("검색 결과가 없습니다.")
            return

        # 현재 곡이 재생 중이라면 큐에 추가
        if voice.is_playing():
            queue.append((url2, title))  
            await ctx.send(f"'{title}'가 목록에 추가되었습니다! 현재 목록: {len(queue)}개")
        else:
            source = FFmpegPCMAudio(url2, **FFMPEG_OPTIONS)
            current_track = title
            voice.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), client.loop))
            await ctx.send(f"지금 재생 중: {title}")
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




client.run(Token)
