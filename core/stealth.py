import time
import ctypes
from core.constants import Input, Input_I, MouseInput

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
    
    ctypes.windll.user32.SendInput(1, ctypes.pointer(x_down), ctypes.sizeof(x_down))
    time.sleep(0.01)
    ctypes.windll.user32.SendInput(1, ctypes.pointer(x_up), ctypes.sizeof(x_up))

def set_win32_clipboard(text):
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    
    # Configure argtypes/restypes for 64-bit safety
    user32.OpenClipboard.argtypes = [ctypes.c_void_p]
    user32.OpenClipboard.restype = ctypes.c_bool
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = ctypes.c_bool
    user32.EmptyClipboard.argtypes = []
    user32.EmptyClipboard.restype = ctypes.c_bool
    user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    user32.SetClipboardData.restype = ctypes.c_void_p
    user32.GetClipboardData.argtypes = [ctypes.c_uint]
    user32.GetClipboardData.restype = ctypes.c_void_p
    
    kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.restype = ctypes.c_bool
    kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
    kernel32.GlobalFree.restype = ctypes.c_void_p

    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002
    
    for _ in range(10):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.05)
    else:
        return False
        
    try:
        user32.EmptyClipboard()
        data = text.encode('utf-16le') + b'\x00\x00'
        h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not h_mem:
            return False
        p_mem = kernel32.GlobalLock(h_mem)
        if not p_mem:
            kernel32.GlobalFree(h_mem)
            return False
        ctypes.memmove(p_mem, data, len(data))
        kernel32.GlobalUnlock(h_mem)
        res = user32.SetClipboardData(CF_UNICODETEXT, h_mem)
        return bool(res)
    finally:
        user32.CloseClipboard()

def get_win32_clipboard():
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    # Set restype so GlobalLock returns a proper c_void_p pointer, not a bare integer.
    kernel32.GlobalLock.restype = ctypes.c_void_p
    CF_UNICODETEXT = 13
    for _ in range(10):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.05)
    else:
        return ""
    try:
        h_mem = user32.GetClipboardData(CF_UNICODETEXT)
        if not h_mem:
            return ""
        p_mem = kernel32.GlobalLock(h_mem)
        if not p_mem:
            return ""
        try:
            try:
                return ctypes.wstring_at(p_mem)
            except OSError:
                # Another process released the clipboard memory between lock and read
                return ""
        finally:
            kernel32.GlobalUnlock(h_mem)
    finally:
        user32.CloseClipboard()
