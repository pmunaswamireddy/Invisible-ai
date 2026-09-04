import time
import random
import ctypes
from PyQt5.QtWidgets import QApplication
from core.constants import POINT, KeyBdInput, Input_I, Input
from core.stealth import set_win32_clipboard

def stealth_paste_text(text, target_hwnd=None):
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    KEYEVENTF_KEYUP = 0x0002
    
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    
    # 1. Set text into Win32 unicode clipboard
    set_win32_clipboard(text)
    time.sleep(0.05)
    
    # 2. Ensure target window is in foreground
    target_hwnd_val = int(target_hwnd) if target_hwnd is not None else 0
    if target_hwnd_val:
        fore_hwnd = user32.GetForegroundWindow()
        fore_hwnd_val = int(fore_hwnd) if fore_hwnd is not None else 0
        if fore_hwnd_val != target_hwnd_val:
            curr_thread = kernel32.GetCurrentThreadId()
            target_thread, _ = user32.GetWindowThreadProcessId(target_hwnd_val, None)
            if curr_thread and target_thread and curr_thread != target_thread:
                user32.AttachThreadInput(curr_thread, target_thread, True)
            user32.SetForegroundWindow(target_hwnd_val)
            user32.BringWindowToTop(target_hwnd_val)
            if curr_thread and target_thread and curr_thread != target_thread:
                user32.AttachThreadInput(curr_thread, target_thread, False)
            time.sleep(0.08)
            
    # 3. Send Ctrl+V paste keys with hardware scan codes
    VK_SHIFT = 0x10
    VK_CONTROL = 0x11
    VK_MENU = 0x12
    VK_V = 0x56
    
    scan_ctrl = user32.MapVirtualKeyW(VK_CONTROL, 0)
    scan_v = user32.MapVirtualKeyW(VK_V, 0)
    
    def send_key_event(vk, scan, is_down):
        ii = Input_I()
        flags = 0 if is_down else KEYEVENTF_KEYUP
        ii.ki = KeyBdInput(vk, scan, flags, 0, None)
        inp = Input(ctypes.c_ulong(1), ii)
        user32.SendInput(1, ctypes.pointer(inp), ctypes.sizeof(Input))

    # Release any stuck modifiers
    send_key_event(VK_SHIFT, 0, False)
    send_key_event(VK_MENU, 0, False)
    time.sleep(0.02)
    
    # Send Ctrl Down -> V Down -> V Up -> Ctrl Up
    send_key_event(VK_CONTROL, scan_ctrl, True)
    time.sleep(0.02)
    send_key_event(VK_V, scan_v, True)
    time.sleep(0.03)
    send_key_event(VK_V, scan_v, False)
    time.sleep(0.02)
    send_key_event(VK_CONTROL, scan_ctrl, False)
    time.sleep(0.05)
    
    # Dual Fallback: Post WM_PASTE (0x0302) directly to target control
    try:
        WM_PASTE = 0x0302
        focus_hwnd = user32.GetFocus()
        focus_hwnd_val = int(focus_hwnd) if focus_hwnd is not None else 0
        overlay_hwnd = int(QApplication.instance()._overlay_instance.winId() if hasattr(QApplication.instance(), '_overlay_instance') and QApplication.instance()._overlay_instance else 0)
        if focus_hwnd_val and focus_hwnd_val != overlay_hwnd:
            user32.PostMessageW(focus_hwnd_val, WM_PASTE, 0, 0)
        elif target_hwnd_val:
            user32.PostMessageW(target_hwnd_val, WM_PASTE, 0, 0)
    except Exception:
        pass

def stealth_type_text(text, switch_focus=True, target_hwnd=None, use_paste=True):
    if use_paste:
        stealth_paste_text(text, target_hwnd=target_hwnd)
        return

    KEYEVENTF_UNICODE = 0x0004
    KEYEVENTF_KEYUP = 0x0002
    INPUT_KEYBOARD = 1
    
    # Normalize carriage returns out of the text to prevent double-newline and carriage cursor jumping bugs
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    
    user32 = ctypes.windll.user32
    
    # Send inputs helper to execute multiple keys in a single atomic transaction
    def send_inputs(events_list):
        n = len(events_list)
        InputArray = Input * n
        inputs = InputArray()
        for idx, (vk, is_down, is_unicode) in enumerate(events_list):
            ii = Input_I()
            if is_unicode:
                flags = KEYEVENTF_UNICODE
                if not is_down:
                    flags |= KEYEVENTF_KEYUP
                ii.ki = KeyBdInput(0, vk, flags, 0, None)
            else:
                flags = 0 if is_down else KEYEVENTF_KEYUP
                ii.ki = KeyBdInput(vk, 0, flags, 0, None)
            inputs[idx] = Input(ctypes.c_ulong(INPUT_KEYBOARD), ii)
        user32.SendInput(n, ctypes.pointer(inputs), ctypes.sizeof(Input))

    # Pre-typing sanitation: ensure any lingering/held modifiers (Shift, Ctrl, Alt) are fully released
    VK_SHIFT = 0x10
    VK_CONTROL = 0x11
    VK_MENU = 0x12
    send_inputs([
        (VK_SHIFT, False, False),
        (VK_CONTROL, False, False),
        (VK_MENU, False, False)
    ])
    time.sleep(0.02)

    # Use pre-captured target window, or fallback to foreground window
    if not target_hwnd:
        for _ in range(10):
            fg = user32.GetForegroundWindow()
            if fg is not None and fg != 0:
                target_hwnd = fg
                break
            time.sleep(0.02)
    
    target_hwnd_val = int(target_hwnd) if target_hwnd is not None else 0
    if not target_hwnd_val:
        return
    
    is_notepad = False
    if target_hwnd_val:
        class_name = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(target_hwnd_val, class_name, 256)
        if "notepad" in class_name.value.lower():
            is_notepad = True

    use_human_delays = getattr(QApplication.instance(), '_human_typing_enabled', True)
    
    if use_human_delays:
        hold_delay = 0.012 if is_notepad else 0.006
    else:
        hold_delay = 0.008 if is_notepad else 0.003
    spacing_delay = 0.010 if is_notepad else 0.004

    if target_hwnd_val:
        user32.SetForegroundWindow(target_hwnd_val)
        time.sleep(0.05)
    
    lines = text.split('\n')
    abort = False
    
    pt = POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    
    for line_idx, line in enumerate(lines):
        if abort:
            break
            
        # Pause Wait Loop
        overlay = getattr(QApplication.instance(), '_overlay_instance', None)
        while overlay and getattr(overlay, 'injection_paused', False):
            if getattr(overlay, 'abort_injection', False):
                abort = True
                break
            time.sleep(0.05)
            
        if abort:
            break

        if not user32.IsWindow(target_hwnd_val):
            abort = True
            break
            
        if line_idx > 0:
            VK_RETURN = 0x0D
            VK_HOME = 0x24
            VK_END = 0x23
            VK_ESCAPE = 0x1B
            VK_SHIFT = 0x10
            VK_DELETE = 0x2E
            
            # Dismiss any auto-complete popups before pressing Enter
            send_inputs([(VK_ESCAPE, True, False), (VK_ESCAPE, False, False)])
            time.sleep(0.005)
            
            # If line consists only of closing brackets/punctuation, send DELETE to pull and absorb IDE auto-closing brackets
            is_bracket_line = bool(line.strip()) and all(c in ")}],; " for c in line.strip())
            if is_bracket_line:
                send_inputs([(VK_DELETE, True, False), (VK_DELETE, False, False)])
                time.sleep(0.005)
            
            send_inputs([(VK_RETURN, True, False), (VK_RETURN, False, False)])
            if use_human_delays:
                time.sleep(random.uniform(0.040, 0.080))
            else:
                time.sleep(0.01)
            
            # Dismiss popups again
            send_inputs([(VK_ESCAPE, True, False), (VK_ESCAPE, False, False)])
            time.sleep(0.005)
            
            # Move to Column 0 of current line, select forward to End, and delete any auto-indented spaces to the right
            send_inputs([
                (VK_HOME, True, False), (VK_HOME, False, False),
                (VK_HOME, True, False), (VK_HOME, False, False),
                (VK_SHIFT, True, False),
                (VK_END, True, False), (VK_END, False, False),
                (VK_SHIFT, False, False),
                (VK_DELETE, True, False), (VK_DELETE, False, False)
            ])
            time.sleep(0.005)
                
        for char in line:
            if not user32.IsWindow(target_hwnd_val):
                abort = True
                break

            overlay = getattr(QApplication.instance(), '_overlay_instance', None)
            if overlay:
                if getattr(overlay, 'abort_injection', False):
                    abort = True
                    break
                while getattr(overlay, 'injection_paused', False):
                    if getattr(overlay, 'abort_injection', False):
                        abort = True
                        break
                    time.sleep(0.05)

            if abort:
                break

            unicode_val = ord(char)
            send_inputs([(unicode_val, True, True)])
            time.sleep(hold_delay)
            send_inputs([(unicode_val, False, True)])
            
            if use_human_delays:
                if char in (';', '{', '}', ':', ',', '(', ')', '='):
                    char_delay = random.uniform(0.050, 0.120)
                else:
                    char_delay = random.uniform(0.015, 0.045)
                time.sleep(char_delay)
            else:
                time.sleep(spacing_delay)
