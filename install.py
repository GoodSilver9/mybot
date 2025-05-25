import os
import sys
import winreg
import win32com.client
from pathlib import Path
from PIL import Image

def create_icon():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    png_path = os.path.join(current_dir, "default_card.png")
    icon_path = os.path.join(current_dir, "temp_icon.ico")
    
    if os.path.exists(png_path):
        # PNG 파일 로드 및 크기 조정
        img = Image.open(png_path)
        img = img.resize((64, 64), Image.Resampling.LANCZOS)
        
        # RGBA 모드로 변환
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        
        # ICO 파일로 저장
        img.save(icon_path, format='ICO', sizes=[(64, 64)])
        return icon_path
    return None

def create_shortcut():
    # 현재 스크립트의 절대 경로
    current_dir = os.path.dirname(os.path.abspath(__file__))
    gui_path = os.path.join(current_dir, "gui.py")
    pythonw_path = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    
    # 시작 프로그램 폴더 경로
    startup_folder = str(Path.home() / "AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Startup")
    
    # 아이콘 생성
    icon_path = create_icon() or os.path.join(current_dir, "default_card.png")
    
    # 바로가기 생성
    shell = win32com.client.Dispatch("WScript.Shell")
    shortcut = shell.CreateShortCut(os.path.join(startup_folder, "DiscordBot.lnk"))
    shortcut.Targetpath = pythonw_path  # pythonw.exe 사용
    shortcut.Arguments = f'"{gui_path}"'
    shortcut.WorkingDirectory = current_dir
    shortcut.IconLocation = icon_path
    shortcut.WindowStyle = 7  # 최소화된 상태로 실행
    shortcut.save()
    
    print("자동 시작 설정이 완료되었습니다.")
    print(f"바로가기가 생성된 경로: {startup_folder}")

if __name__ == "__main__":
    try:
        create_shortcut()
    except Exception as e:
        print(f"설치 중 오류가 발생했습니다: {str(e)}")
        import traceback
        traceback.print_exc()
        input("계속하려면 아무 키나 누르세요...") 