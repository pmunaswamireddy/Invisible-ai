import os
import ctypes
from ctypes import wintypes

class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", ctypes.c_ulong),
        ("scanCode", ctypes.c_ulong),
        ("flags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_void_p)
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

    ctypes.windll.user32.GetForegroundWindow.restype = ctypes.wintypes.HWND
    ctypes.windll.user32.GetForegroundWindow.argtypes = []

    ctypes.windll.user32.WindowFromPoint.restype = ctypes.wintypes.HWND
    ctypes.windll.user32.WindowFromPoint.argtypes = [POINT]

    ctypes.windll.user32.GetAncestor.restype = ctypes.wintypes.HWND
    ctypes.windll.user32.GetAncestor.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]

    ctypes.windll.user32.GetShellWindow.restype = ctypes.wintypes.HWND
    ctypes.windll.user32.GetShellWindow.argtypes = []

    ctypes.windll.user32.GetFocus.restype = ctypes.wintypes.HWND
    ctypes.windll.user32.GetFocus.argtypes = []
except Exception:
    pass

def translate_vk_to_char(vk, shift):
    if 0x30 <= vk <= 0x39: # 0-9
        chars = ")!@#$%^&*(" if shift else "0123456789"
        return chars[vk - 0x30]
    elif 0x41 <= vk <= 0x5A: # A-Z
        char = chr(vk)
        return char if shift else char.lower()
    elif vk == 0x20: # Space
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

def get_app_dir():
    app_dir = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'InvisibleAI')
    if not os.path.exists(app_dir):
        os.makedirs(app_dir)
    return app_dir

# --- Ctypes Structures for Hardware Keyboard Injection (SendInput) ---
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
