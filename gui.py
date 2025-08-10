import tkinter as tk
import subprocess
import sys
import os
from infi.systray import SysTrayIcon
import psutil
import signal
from PIL import Image, ImageDraw
import logging
from datetime import datetime
import threading
import time

class BotController:
    def __init__(self):
        self.bot_process = None
        self.error_count = 0
        self.last_error_time = time.time()
        self.setup_logging()
        self.setup_tray()
        # 프로그램 시작 시 자동으로 봇 시작
        self.start_bot(None)
    
    def setup_logging(self):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        log_dir = os.path.join(current_dir, 'logs')
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        log_file = os.path.join(log_dir, f'bot_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        self.logger.info("로깅 시스템 초기화 완료")

    def start_bot(self, systray):
        if self.bot_process is None or self.bot_process.poll() is not None:
            try:
                current_dir = os.path.dirname(os.path.abspath(__file__))
                bot_path = os.path.join(current_dir, "bot.py")
                python_exe = os.path.join(os.path.dirname(sys.executable), "python.exe")
                
                self.logger.info(f"현재 디렉토리: {current_dir}")
                self.logger.info(f"봇 파일 경로: {bot_path}")
                self.logger.info(f"Python 실행 파일: {python_exe}")
                
                if not os.path.exists(bot_path):
                    self.logger.error(f"오류: {bot_path} 파일을 찾을 수 없습니다.")
                    return
                
                if not os.path.exists(python_exe):
                    self.logger.error(f"오류: Python 실행 파일을 찾을 수 없습니다: {python_exe}")
                    # 대체 경로 시도
                    python_exe = "python.exe"
                    self.logger.info(f"대체 Python 경로 사용: {python_exe}")
                
                # 봇 프로세스 시작 (숨겨진 창으로 실행)
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                
                self.logger.info("봇 프로세스 시작 시도...")
                
                self.bot_process = subprocess.Popen(
                    [python_exe, bot_path],
                    startupinfo=startupinfo,
                    cwd=current_dir,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                
                # 프로세스 상태 확인
                self.logger.info(f"프로세스 ID: {self.bot_process.pid}")
                self.logger.info(f"프로세스 상태: {self.bot_process.poll()}")
                
                # 에러 출력 확인
                stderr_thread = threading.Thread(target=self._monitor_stderr)
                stderr_thread.daemon = True
                stderr_thread.start()
                
                self.logger.info("봇이 시작되었습니다.")
            except Exception as e:
                self.logger.error(f"봇 시작 중 오류 발생: {str(e)}")
                import traceback
                self.logger.error(traceback.format_exc())
        else:
            self.logger.info("봇이 이미 실행 중입니다.")
    
    def _monitor_stderr(self):
        while self.bot_process and self.bot_process.poll() is None:
            line = self.bot_process.stderr.readline()
            if line:
                self.logger.error(f"봇 에러 출력: {line.strip()}")
                current_time = time.time()
                
                # 에러가 발생한 경우
                if "error" in line.lower() or "exception" in line.lower():
                    # 마지막 에러로부터 10초 이내에 발생한 에러인 경우
                    if current_time - self.last_error_time <= 10:
                        self.error_count += 1
                        # 10초 이내에 3번 이상의 에러가 발생한 경우
                        if self.error_count >= 3:
                            self.logger.warning("10초 이내에 3번 이상의 에러가 발생하여 봇을 재시작합니다.")
                            self.restart_bot()
                            return
                    else:
                        # 10초가 지난 경우 에러 카운트 초기화
                        self.error_count = 1
                    
                    self.last_error_time = current_time

    def restart_bot(self):
        self.logger.info("봇 재시작 시도...")
        self.stop_bot(None)
        time.sleep(2)  # 프로세스가 완전히 종료될 때까지 대기
        self.start_bot(None)
        self.error_count = 0
        self.last_error_time = time.time()

    def stop_bot(self, systray):
        if self.bot_process and self.bot_process.poll() is None:
            try:
                self.logger.info(f"종료할 프로세스 ID: {self.bot_process.pid}")
                
                # Windows에서 프로세스 트리 종료
                parent = psutil.Process(self.bot_process.pid)
                children = parent.children(recursive=True)
                
                # 자식 프로세스 먼저 종료
                for child in children:
                    try:
                        self.logger.info(f"자식 프로세스 종료: {child.pid}")
                        child.terminate()
                        child.wait(timeout=3)  # 3초 대기
                    except psutil.TimeoutExpired:
                        self.logger.warning(f"자식 프로세스 {child.pid} 강제 종료")
                        child.kill()
                    except psutil.NoSuchProcess:
                        pass
                
                # 부모 프로세스 종료
                self.logger.info(f"부모 프로세스 종료: {parent.pid}")
                parent.terminate()
                
                try:
                    # 부모 프로세스가 종료될 때까지 최대 5초 대기
                    self.bot_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.logger.warning("봇 프로세스 강제 종료")
                    parent.kill()  # 강제 종료
                
                self.logger.info("봇이 종료되었습니다.")
                
            except Exception as e:
                self.logger.error(f"봇 종료 중 오류 발생: {str(e)}")
                import traceback
                self.logger.error(traceback.format_exc())
                # 마지막 수단으로 강제 종료
                try:
                    if self.bot_process:
                        self.bot_process.kill()
                except:
                    pass
            finally:
                self.bot_process = None
        else:
            self.logger.info("실행 중인 봇이 없습니다.")
    
    def create_icon(self):
        # PNG 파일을 ICO로 변환
        current_dir = os.path.dirname(os.path.abspath(__file__))
        png_path = os.path.join(current_dir, "default_card.png")
        icon_path = os.path.join(current_dir, "temp_icon.ico")
        
        if os.path.exists(png_path):
            # PNG 파일 로드 및 크기 조정
            img = Image.open(png_path)
            img = img.resize((64, 64), Image.LANCZOS)
            
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