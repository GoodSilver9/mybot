import tkinter as tk
import subprocess
import sys
import os
from infi.systray import SysTrayIcon
import psutil
import signal
from PIL import Image, ImageDraw

class BotController:
    def __init__(self):
        self.bot_process = None
        self.setup_tray()
    
    def start_bot(self, systray):
        if self.bot_process is None or self.bot_process.poll() is not None:
            try:
                # 현재 스크립트의 디렉토리 경로
                current_dir = os.path.dirname(os.path.abspath(__file__))
                bot_path = os.path.join(current_dir, "bot.py")
                
                print(f"[디버그] 현재 디렉토리: {current_dir}")
                print(f"[디버그] 봇 파일 경로: {bot_path}")
                print(f"[디버그] Python 실행 파일: {sys.executable}")
                
                if not os.path.exists(bot_path):
                    print(f"오류: {bot_path} 파일을 찾을 수 없습니다.")
                    return
                
                # 봇 프로세스 시작 (현재 터미널에서 실행)
                cmd = f'"{sys.executable}" "{bot_path}"'
                print(f"[디버그] 실행할 명령어: {cmd}")
                
                self.bot_process = subprocess.Popen(
                    cmd,
                    shell=True,
                    cwd=current_dir,
                )
                
                # 프로세스 상태 확인
                print(f"[디버그] 프로세스 ID: {self.bot_process.pid}")
                print(f"[디버그] 프로세스 상태: {self.bot_process.poll()}")
                
                print("봇이 시작되었습니다.")
            except Exception as e:
                print(f"봇 시작 중 오류 발생: {str(e)}")
                import traceback
                traceback.print_exc()
        else:
            print("봇이 이미 실행 중입니다.")
    
    def stop_bot(self, systray):
        if self.bot_process and self.bot_process.poll() is None:
            try:
                print(f"[디버그] 종료할 프로세스 ID: {self.bot_process.pid}")
                
                # Windows에서 프로세스 트리 종료
                parent = psutil.Process(self.bot_process.pid)
                children = parent.children(recursive=True)
                
                for child in children:
                    print(f"[디버그] 자식 프로세스 종료: {child.pid}")
                    child.terminate()
                
                print(f"[디버그] 부모 프로세스 종료: {parent.pid}")
                parent.terminate()
                
                # 프로세스가 완전히 종료될 때까지 대기
                self.bot_process.wait(timeout=5)
                print("봇이 종료되었습니다.")
            except Exception as e:
                print(f"봇 종료 중 오류 발생: {str(e)}")
                import traceback
                traceback.print_exc()
                # 강제 종료
                try:
                    self.bot_process.kill()
                except:
                    pass
            self.bot_process = None
        else:
            print("실행 중인 봇이 없습니다.")
    
    def create_icon(self):
        # PNG 파일을 ICO로 변환
        current_dir = os.path.dirname(os.path.abspath(__file__))
        png_path = os.path.join(current_dir, "default_card.png")
        icon_path = os.path.join(current_dir, "temp_icon.ico")
        
        if os.path.exists(png_path):
            # PNG 파일 로드 및 크기 조정
            img = Image.open(png_path)
            img = img.resize((64, 64), Image.Resampling.LANCZOS)
            
            # RGBA 모드로 변환 (투명도 지원)
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            
            # ICO 파일로 저장
            img.save(icon_path, format='ICO', sizes=[(64, 64)])
            return icon_path
        else:
            # 기본 아이콘 생성 (PNG 파일이 없을 경우)
            img = Image.new('RGBA', (64, 64), color=(0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.ellipse([4, 4, 60, 60], fill='white', outline='black')
            img.save(icon_path, format='ICO', sizes=[(64, 64)])
            return icon_path
    
    def setup_tray(self):
        menu_options = (
            ("봇 시작", None, self.start_bot),
            ("봇 종료", None, self.stop_bot),
        )
        
        # 아이콘 생성
        icon_path = self.create_icon()
        
        self.systray = SysTrayIcon(
            icon_path,
            "디스코드 봇 컨트롤러",
            menu_options,
            on_quit=self.on_quit
        )
        self.systray.start()
    
    def on_quit(self, systray):
        print("[디버그] 프로그램 종료 시작")
        # 봇 프로세스가 실행 중이면 종료
        self.stop_bot(systray)
        
        # 임시 아이콘 파일 삭제
        try:
            icon_path = os.path.join(os.path.dirname(__file__), "temp_icon.ico")
            if os.path.exists(icon_path):
                os.remove(icon_path)
        except Exception as e:
            print(f"[디버그] 아이콘 파일 삭제 중 오류: {str(e)}")
            
        print("[디버그] 프로그램 종료 완료")
        os._exit(0)

if __name__ == "__main__":
    try:
        print("[디버그] 프로그램 시작")
        controller = BotController()
        print("[디버그] 컨트롤러 초기화 완료")
        
        # 메인 스레드 유지
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        print("[디버그] 키보드 인터럽트 감지")
        controller.on_quit(controller.systray)
    except Exception as e:
        print(f"[디버그] 예상치 못한 오류 발생: {str(e)}")
        import traceback
        traceback.print_exc() 