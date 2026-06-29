import os
import sys
import shutil
import subprocess
import ctypes
from utils import get_app_dir

def is_debugger_present():
    try:
        return ctypes.windll.kernel32.IsDebuggerPresent()
    except AttributeError:
        return False

def self_destruct():
    # 1. Wipe AppData folder
    app_dir = get_app_dir()
    try:
        if os.path.exists(app_dir):
            shutil.rmtree(app_dir)
    except Exception:
        pass
        
    # 2. Self-delete the running executable
    try:
        exe_path = sys.executable
        # Detached cmd command that waits 1 second and force-deletes the locked exe
        cmd = f"timeout /T 1 & del /F /Q \"{exe_path}\""
        subprocess.Popen(cmd, shell=True, creationflags=0x08000000) # CREATE_NO_WINDOW
    except Exception:
        pass
        
    # 3. Exit process instantly
    os._exit(1)

def check_security():
    if getattr(sys, 'frozen', False):
        if is_debugger_present():
            self_destruct()
