import codecs
path = 'd:/invisibleai/overlay.py'
with codecs.open(path, 'r', 'utf-8') as f:
    text = f.read()

mouse_hook_code = '''
# --- Global Mouse Scroll Hook for Ghost Mode ---
WH_MOUSE_LL = 14
WM_MOUSEWHEEL = 0x020A
_mouse_hook_handle = None

class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", POINT),
        ("mouseData", ctypes.c_ulong),
        ("flags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))
    ]

MOUSE_HOOKPROC = ctypes.WINFUNCTYPE(ctypes.wintypes.LPARAM, ctypes.c_int, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM)

def _global_mouse_callback(nCode, wParam, lParam):
    if nCode >= 0 and wParam == WM_MOUSEWHEEL:
        try:
            app = QApplication.instance()
            if app and hasattr(app, '_overlay_instance'):
                overlay = app._overlay_instance
                if getattr(overlay, 'is_hidden', False):
                    # In Ghost Mode, check if mouse is over the overlay geometry
                    m_struct = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                    x, y = m_struct.pt.x, m_struct.pt.y
                    
                    # Convert mouseData (high word) to delta
                    delta = (m_struct.mouseData >> 16) & 0xFFFF
                    if delta > 32767: delta -= 65536 # two's complement for negative delta
                    
                    geo = overlay.geometry()
                    if geo.contains(QPoint(x, y)):
                        # It is over the overlay. Route it to Qt and swallow the OS event!
                        overlay.global_scroll_signal.emit(x, y, delta)
                        return 1 # Swallow event
        except Exception:
            pass
    return ctypes.windll.user32.CallNextHookEx(_mouse_hook_handle, nCode, wParam, lParam)

_mouse_hook_c_callback = MOUSE_HOOKPROC(_global_mouse_callback)

def install_mouse_hook():
    global _mouse_hook_handle
    if not _mouse_hook_handle:
        _mouse_hook_handle = ctypes.windll.user32.SetWindowsHookExW(
            WH_MOUSE_LL,
            _mouse_hook_c_callback,
            ctypes.windll.kernel32.GetModuleHandleW(None),
            0
        )

def uninstall_mouse_hook():
    global _mouse_hook_handle
    if _mouse_hook_handle:
        ctypes.windll.user32.UnhookWindowsHookEx(_mouse_hook_handle)
        _mouse_hook_handle = None
'''

if 'WH_MOUSE_LL = 14' not in text:
    # Inject mouse hook definitions near the keyboard hook definitions
    text = text.replace('class KeyBdInput(ctypes.Structure):', mouse_hook_code + '\nclass KeyBdInput(ctypes.Structure):')
    
    with codecs.open(path, 'w', 'utf-8') as f:
        f.write(text)
    print("Mouse hook definitions injected.")
else:
    print("Mouse hook already present.")
