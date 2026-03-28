import discord
from discord.ext import commands
import os

def load_env_config():
    """.env 파일에서 설정을 로드합니다."""
    config = {}
    try:
        with open('.env', 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    config[key.strip()] = value.strip()
    except FileNotFoundError:
        print("[경고] .env 파일을 찾을 수 없습니다. 기본값을 사용합니다.")
    return config

def create_intents():
    """Discord 봇의 intents를 생성합니다."""
    intents = discord.Intents.default()
    intents.message_content = True
    return intents

def create_bot_client():
    """Discord 봇 클라이언트를 생성합니다."""
    config = load_env_config()
    
    # 설정값 가져오기 (기본값 포함)
    command_prefix = config.get('COMMAND_PREFIX', '.')
    case_insensitive = config.get('CASE_INSENSITIVE', 'true').lower() == 'true'
    voice_timeout = float(config.get('VOICE_TIMEOUT', '30.0'))
    
    intents = create_intents()
    client = commands.Bot(command_prefix=command_prefix, intents=intents, case_insensitive=case_insensitive)
    
    # 음성 연결 타임아웃 설정
    discord.voice_client.VoiceClient.timeout = voice_timeout
    
    return client

def get_ffmpeg_options():
    """FFmpeg 옵션을 환경변수에서 로드합니다."""
    config = load_env_config()
    ffmpeg_path = config.get('FFMPEG_PATH', 'ffmpeg')
    
    return {
        'executable': ffmpeg_path,
        # 버퍼링 최소화 및 안정적인 스트리밍을 위한 옵션
        'before_options': (
            '-reconnect 1 '              # 연결 끊김 시 재연결
            '-reconnect_streamed 1 '     # 스트림 재연결
            '-reconnect_delay_max 5 '    # 최대 재연결 딜레이 5초
            '-reconnect_at_eof 1 '       # EOF 시 재연결
            '-timeout 30000000 '         # 30초 타임아웃
            '-nostdin '                  # stdin 비활성화
            '-analyzeduration 0 '        # 분석 시간 최소화 (버퍼링 감소)
            '-probesize 32768 '          # 프로브 크기 최적화
            '-fflags +nobuffer+fastseek' # 버퍼링 최소화
        ),
        'options': (
            '-vn '                       # 비디오 비활성화
            '-b:a 256k '                 # 오디오 비트레이트 (고품질)
            '-bufsize 128k '             # 버퍼 사이즈
            '-loglevel error '           # 에러만 로깅
            '-avoid_negative_ts make_zero '  # 타임스탬프 정규화
            '-fflags +discardcorrupt '   # 손상된 패킷 무시
            '-ac 2 '                     # 스테레오
            '-ar 48000 '                 # 샘플레이트 48kHz
            '-af "aresample=resampler=soxr" ' # 고품질 리샘플러
            '-compression_level 10'      # 최대 압축 품질 (Opus)
        )
    }

def get_node_path():
    """Node.js 경로를 환경변수에서 로드합니다."""
    config = load_env_config()
    return config.get('NODE_PATH', 'node')

# 기존 호환성을 위한 FFMPEG_OPTIONS
FFMPEG_OPTIONS = get_ffmpeg_options()
