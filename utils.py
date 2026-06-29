import sys
import os
import ctypes
import time
import socket
import uuid
from ctypes import wintypes

# --- App Directories and Device Identifiers ---
def get_app_dir():
    app_dir = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'InvisibleAI')
    if not os.path.exists(app_dir):
        os.makedirs(app_dir)
    return app_dir

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def get_device_id():
    return uuid.UUID(int=uuid.getnode()).hex[-12:].upper()

def get_device_name():
    return socket.gethostname()

# --- Windows Acrylic DWM Blur ---
def apply_acrylic_blur(widget, is_dark=True):
    from ctypes import windll, Structure, c_int, byref, c_void_p, sizeof
    
    class ACCENT_POLICY(Structure):
        _fields_ = [
            ("AccentState", c_int),
            ("AccentFlags", c_int),
            ("GradientColor", c_int),
            ("AnimationId", c_int)
        ]
        
    class WINDOWCOMPOSITIONATTRIBDATA(Structure):
        _fields_ = [
            ("Attribute", c_int),
            ("Data", c_void_p),
            ("SizeOfData", c_int)
        ]
        
    try:
        accent = ACCENT_POLICY()
        accent.AccentState = 4 
        accent.AccentFlags = 2 
        if is_dark:
            accent.GradientColor = 0xCC161414 
        else:
            accent.GradientColor = 0xCCF6F4F3 
            
        data = WINDOWCOMPOSITIONATTRIBDATA()
        data.Attribute = 19 
        data.Data = ctypes.cast(byref(accent), c_void_p)
        data.SizeOfData = sizeof(accent)
        
        hwnd = int(widget.winId())
        windll.user32.SetWindowCompositionAttribute(hwnd, byref(data))
    except Exception as e:
        print("Acrylic blur is unsupported or failed:", e)

# --- Windows Registry Startup ---
def toggle_registry_autostart(enabled):
    import winreg
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    app_name = "InvisibleAI_Manager"
    exe_path = sys.executable
    if not getattr(sys, 'frozen', False):
        script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "manager.py"))
        exe_path = f'"{sys.executable}" "{script_path}"'
    else:
        exe_path = f'"{exe_path}"'
        
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
        if enabled:
            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, exe_path)
        else:
            try:
                winreg.DeleteValue(key, app_name)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception as e:
        print("Failed to toggle registry autostart:", e)

# --- Ctypes Structures for Hooks and Keyboard/Mouse Simulation ---
class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", ctypes.c_ulong),
        ("scanCode", ctypes.c_ulong),
        ("flags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_ulong)
    ]

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long)
    ]

class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", POINT),
        ("mouseData", ctypes.c_ulong),
        ("flags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_void_p)
    ]

HOOKPROC = ctypes.WINFUNCTYPE(ctypes.wintypes.LPARAM, ctypes.c_int, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM)

# Declare argtypes and restypes for 64-bit Win32 safety
try:
    ctypes.windll.user32.SetWindowsHookExW.restype = ctypes.wintypes.HHOOK
    ctypes.windll.user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, ctypes.wintypes.HINSTANCE, ctypes.wintypes.DWORD]
    
    ctypes.windll.user32.CallNextHookEx.restype = ctypes.wintypes.LPARAM
    ctypes.windll.user32.CallNextHookEx.argtypes = [ctypes.wintypes.HHOOK, ctypes.c_int, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM]
    
    ctypes.windll.user32.UnhookWindowsHookEx.restype = ctypes.wintypes.BOOL
    ctypes.windll.user32.UnhookWindowsHookEx.argtypes = [ctypes.wintypes.HHOOK]
except AttributeError:
    pass

def translate_vk_to_char(vk, shift):
    if 0x30 <= vk <= 0x39: 
        chars = ")!@#$%^&*(" if shift else "0123456789"
        return chars[vk - 0x30]
    elif 0x41 <= vk <= 0x5A: 
        char = chr(vk)
        return char if shift else char.lower()
    elif vk == 0x20: 
        return " "
    elif vk == 0xBA: return ":" if shift else ";"
    elif vk == 0xBB: return "+" if shift else "="
    elif vk == 0xBC: return "<" if shift else ","
    elif vk == 0xBD: return "_" if shift else "-"
    elif vk == 0xBE: return ">" if shift else "."
    elif vk == 0xBF: return "?" if shift else "/"
    elif vk == 0xC0: return "~" if shift else "`"
    elif vk == 0xDB: return "{" if shift else "["
    elif vk == 0xDC: return "|" if shift else "\\"
    elif vk == 0xDD: return "}" if shift else "]"
    elif vk == 0xDE: return '"' if shift else "'"
    return None

PUL = ctypes.POINTER(ctypes.c_ulong)
class KeyBdInput(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort),
                ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", PUL)]

class HardwareInput(ctypes.Structure):
    _fields_ = [("uMsg", ctypes.c_ulong),
                ("wParamL", ctypes.c_short),
                ("wParamH", ctypes.c_ushort)]

class MouseInput(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long),
                ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", PUL)]

class Input_I(ctypes.Union):
    _fields_ = [("ki", KeyBdInput),
                ("mi", MouseInput),
                ("hi", HardwareInput)]

class Input(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong),
                ("ii", Input_I)]

def stealth_click():
    INPUT_MOUSE = 0
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004
    
    extra = ctypes.c_ulong(0)
    
    ii_down = Input_I()
    ii_down.mi = MouseInput(0, 0, 0, MOUSEEVENTF_LEFTDOWN, 0, ctypes.pointer(extra))
    x_down = Input(ctypes.c_ulong(INPUT_MOUSE), ii_down)
    
    ii_up = Input_I()
    ii_up.mi = MouseInput(0, 0, 0, MOUSEEVENTF_LEFTUP, 0, ctypes.pointer(extra))
    x_up = Input(ctypes.c_ulong(INPUT_MOUSE), ii_up)
    
    try:
        ctypes.windll.user32.SendInput(1, ctypes.pointer(x_down), ctypes.sizeof(x_down))
        time.sleep(0.01)
        ctypes.windll.user32.SendInput(1, ctypes.pointer(x_up), ctypes.sizeof(x_up))
    except AttributeError:
        pass

def stealth_type_text(text, switch_focus=True):
    KEYEVENTF_UNICODE = 0x0004
    KEYEVENTF_KEYUP = 0x0002
    INPUT_KEYBOARD = 1
    
    try:
        user32 = ctypes.windll.user32
        target_hwnd = user32.GetForegroundWindow()
    except AttributeError:
        return
    
    def press_key(vk, is_down):
        extra = ctypes.c_ulong(0)
        ii = Input_I()
        flags = 0 if is_down else KEYEVENTF_KEYUP
        ii.ki = KeyBdInput(vk, 0, flags, 0, ctypes.pointer(extra))
        x = Input(ctypes.c_ulong(INPUT_KEYBOARD), ii)
        user32.SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))
        time.sleep(0.002)

    if switch_focus:
        VK_MENU = 0x12 
        VK_TAB = 0x09  
        press_key(VK_MENU, True)
        press_key(VK_TAB, True)
        press_key(VK_TAB, False)
        press_key(VK_MENU, False)
        time.sleep(0.15)
        target_hwnd = user32.GetForegroundWindow()
    
    for char in text:
        if target_hwnd and user32.GetForegroundWindow() != target_hwnd:
            user32.SetForegroundWindow(target_hwnd)
            time.sleep(0.02)
            
        if char == '\n':
            VK_RETURN = 0x0D
            press_key(VK_RETURN, True)
            press_key(VK_RETURN, False)
            time.sleep(0.01)
            
            unicode_val = ord(' ')
            extra = ctypes.c_ulong(0)
            ii_ = Input_I()
            ii_.ki = KeyBdInput(0, unicode_val, KEYEVENTF_UNICODE, 0, ctypes.pointer(extra))
            x_down = Input(ctypes.c_ulong(INPUT_KEYBOARD), ii_)
            ctypes.windll.user32.SendInput(1, ctypes.pointer(x_down), ctypes.sizeof(x_down))
            
            ii_.ki = KeyBdInput(0, unicode_val, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, ctypes.pointer(extra))
            x_up = Input(ctypes.c_ulong(INPUT_KEYBOARD), ii_)
            ctypes.windll.user32.SendInput(1, ctypes.pointer(x_up), ctypes.sizeof(x_up))
            time.sleep(0.002)
            
            VK_SHIFT = 0x10
            VK_HOME = 0x24
            VK_BACK = 0x08
            
            press_key(VK_SHIFT, True)
            press_key(VK_HOME, True)
            press_key(VK_HOME, False)
            press_key(VK_HOME, True)
            press_key(VK_HOME, False)
            press_key(VK_SHIFT, False)
            time.sleep(0.002)
            
            press_key(VK_BACK, True)
            press_key(VK_BACK, False)
            time.sleep(0.005)
        else:
            unicode_val = ord(char)
            extra = ctypes.c_ulong(0)
            ii_ = Input_I()
            ii_.ki = KeyBdInput(0, unicode_val, KEYEVENTF_UNICODE, 0, ctypes.pointer(extra))
            x_down = Input(ctypes.c_ulong(INPUT_KEYBOARD), ii_)
            ctypes.windll.user32.SendInput(1, ctypes.pointer(x_down), ctypes.sizeof(x_down))
            
            time.sleep(0.001)
            
            ii_.ki = KeyBdInput(0, unicode_val, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, ctypes.pointer(extra))
            x_up = Input(ctypes.c_ulong(INPUT_KEYBOARD), ii_)
            ctypes.windll.user32.SendInput(1, ctypes.pointer(x_up), ctypes.sizeof(x_up))
            time.sleep(0.003)
