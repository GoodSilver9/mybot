import discord
from discord.ext import commands

def create_intents():
    """Discord 봇의 intents를 생성합니다."""
    intents = discord.Intents.default()
    intents.message_content = True
    return intents

def create_bot_client(command_prefix='.', case_insensitive=True):
    """Discord 봇 클라이언트를 생성합니다."""
    intents = create_intents()
    client = commands.Bot(command_prefix=command_prefix, intents=intents, case_insensitive=case_insensitive)
    return client

# FFmpeg 옵션 (안정성 개선)
FFMPEG_OPTIONS = {
    'executable': 'C:\\Program Files (x86)\\ffmpeg-2024-10-13-git-e347b4ff31-essentials_build\\bin\\ffmpeg.exe',
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -timeout 30000000 -nostdin',
    'options': '-vn -b:a 128k -bufsize 4096k -maxrate 256k -loglevel error -avoid_negative_ts make_zero -fflags +discardcorrupt'
}
