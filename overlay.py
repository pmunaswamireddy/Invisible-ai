import sys
import os
import ctypes
import json
import time
import threading
import urllib.request
import urllib.parse
import re
import queue
import uuid
from ctypes.wintypes import POINT
from ctypes import wintypes
import signal
from PyQt5.QtWidgets import QApplication, QMenu, QWidget, QVBoxLayout, QTextEdit, QTextBrowser, QPushButton, QSlider, QLabel, QHBoxLayout, QFrame, QLineEdit, QComboBox, QSizePolicy, QListWidget, QListWidgetItem, QScrollArea, QGridLayout, QMessageBox, QStackedWidget
from PyQt5.QtCore import Qt, QPoint, QEvent, QObject, QTimer, pyqtSignal, QAbstractNativeEventFilter, QThread, QRect, QSize, QEventLoop
from PyQt5.QtGui import QColor, QPainter, QPen, QCursor, QMouseEvent, QPixmap, QPainterPath, QTextCursor, QFont

class SafeTextBrowser(QTextBrowser):
    def keyPressEvent(self, event):
        # Ignore raw modifier key presses to prevent native QTextBrowser crashes
        if event.key() in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta):
            event.accept()
            return
            
        if event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_C:
            text = self.textCursor().selectedText()
            if text:
                # Replace Unicode paragraph separator (U+2029) with normal newline
                text = text.replace('\u2029', '\n')
                QApplication.clipboard().setText(text)
            event.accept()
            return
        super().keyPressEvent(event)

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
ctypes.windll.user32.SetWindowsHookExW.restype = ctypes.wintypes.HHOOK
ctypes.windll.user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, ctypes.wintypes.HINSTANCE, ctypes.wintypes.DWORD]

ctypes.windll.user32.CallNextHookEx.restype = ctypes.wintypes.LPARAM
ctypes.windll.user32.CallNextHookEx.argtypes = [ctypes.wintypes.HHOOK, ctypes.c_int, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM]

ctypes.windll.user32.UnhookWindowsHookEx.restype = ctypes.wintypes.BOOL
ctypes.windll.user32.UnhookWindowsHookEx.argtypes = [ctypes.wintypes.HHOOK]

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

HAS_MSS = True


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

def stealth_type_text(text, switch_focus=True, target_hwnd=None):
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

    # Safe sequence player with debounce delay to let the OS process key state changes
    def play_sequence(events_list, delay=0.003):
        for vk, is_down, is_unicode in events_list:
            send_inputs([(vk, is_down, is_unicode)])
            time.sleep(delay)

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
        target_hwnd = user32.GetForegroundWindow()
    
    # Determine if target process is notepad.exe
    is_notepad = False
    if target_hwnd:
        class_name = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(target_hwnd, class_name, 256)
        if "notepad" in class_name.value.lower():
            is_notepad = True
        else:
            pid = ctypes.c_ulong(0)
            user32.GetWindowThreadProcessId(target_hwnd, ctypes.byref(pid))
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            h_proc = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if h_proc:
                buf = ctypes.create_unicode_buffer(512)
                size = ctypes.c_ulong(512)
                if ctypes.windll.kernel32.QueryFullProcessImageNameW(h_proc, 0, buf, ctypes.byref(size)):
                    if "notepad.exe" in buf.value.lower():
                        is_notepad = True
                ctypes.windll.kernel32.CloseHandle(h_proc)

    # Enforce safe typing rates for slower legacy applications (Notepad)
    hold_delay = 0.010 if is_notepad else 0.005
    spacing_delay = 0.015 if is_notepad else 0.008

    # Ensure target window has focus before we start typing
    if target_hwnd:
        user32.SetForegroundWindow(target_hwnd)
        time.sleep(0.05)
    
    def press_key(vk, is_down):
        send_inputs([(vk, is_down, False)])
        time.sleep(0.005) # Safe key-up/down debounce delay
    
    if switch_focus:
        VK_TAB = 0x09  
        send_inputs([
            (VK_MENU, True, False),
            (VK_TAB, True, False),
            (VK_TAB, False, False),
            (VK_MENU, False, False)
        ])
        time.sleep(0.15)
        # Update target_hwnd after focus switch
        target_hwnd = user32.GetForegroundWindow()
    
    for idx, char in enumerate(text):
        # Enforce focus on the target window
        if target_hwnd and user32.GetForegroundWindow() != target_hwnd:
            user32.SetForegroundWindow(target_hwnd)
            time.sleep(0.02)
            
        if char == '\n':
            VK_RETURN = 0x0D
            VK_HOME = 0x24
            VK_BACK = 0x08
            
            # Send Enter
            send_inputs([(VK_RETURN, True, False), (VK_RETURN, False, False)])
            time.sleep(0.10 if is_notepad else 0.06) # Let editor process newline and position cursor on next line
            
            if not is_notepad:
                # Safe auto-indent correction (space, shift+home+home, backspace) for IDEs
                space_char = ord(' ')
                play_sequence([
                    (space_char, True, True),
                    (space_char, False, True),
                    (VK_SHIFT, True, False),
                    (VK_HOME, True, False),
                    (VK_HOME, False, False),
                    (VK_HOME, True, False),
                    (VK_HOME, False, False),
                    (VK_SHIFT, False, False),
                    (VK_BACK, True, False),
                    (VK_BACK, False, False)
                ], delay=0.003)
                time.sleep(0.01)
        else:
            unicode_val = ord(char)
            # Send character down and up sequentially
            send_inputs([(unicode_val, True, True)])
            time.sleep(hold_delay) # Let legacy applications register down event
            send_inputs([(unicode_val, False, True)])
            time.sleep(spacing_delay) # Let UI message loops dispatch keyboard state change
            
            # Smart auto-bracket neutralization for editors like VS Code
            # If we just typed an opening bracket and the next character is a newline,
            # press Delete to clear any auto-inserted closing brackets.
            if not is_notepad and char in ['{', '(', '['] and idx + 1 < len(text) and text[idx+1] == '\n':
                VK_DELETE = 0x2E
                send_inputs([(VK_DELETE, True, False), (VK_DELETE, False, False)])
                time.sleep(0.005)



class AppEventFilter(QObject):
    def __init__(self, overlay):
        super().__init__()
        self.overlay = overlay
        self.dragging = False
        self.did_drag_while_hidden = False
        self.resizing = False
        self.resize_edges = 0
        self.drag_offset = QPoint()
        self.start_geometry = self.overlay.geometry()
        self.start_mouse_pos = QPoint()
        self.cursor_modified = False # Prevent cursor fighting and crashes during text selection
        
        # Polling timer removed for latency optimization
        # self.timer = QTimer()
        # self.timer.timeout.connect(self.check_mouse_state)
        # self.timer.start(20)

    def check_mouse_state(self):
        # Stubbed out for performance. Hit testing is now done manually by the mouse hook.
        pass


    def get_resize_edges(self, global_pos):
        margin = 10
        rect = self.overlay.geometry()
        x = global_pos.x() - rect.x()
        y = global_pos.y() - rect.y()
        edges = 0
        if x >= 0 and x < margin: edges |= 1
        elif x <= rect.width() and x > rect.width() - margin: edges |= 2
        if y >= 0 and y < margin: edges |= 4
        elif y <= rect.height() and y > rect.height() - margin: edges |= 8
        return edges

    def update_cursor(self, edges):
        if edges == 1 or edges == 2: self.overlay.setCursor(Qt.SizeHorCursor)
        elif edges == 4 or edges == 8: self.overlay.setCursor(Qt.SizeVerCursor)
        elif edges == (1|4) or edges == (2|8): self.overlay.setCursor(Qt.SizeFDiagCursor)
        elif edges == (1|8) or edges == (2|4): self.overlay.setCursor(Qt.SizeBDiagCursor)
        self.cursor_modified = True

    def do_resize(self, global_pos):
        dx = global_pos.x() - self.start_mouse_pos.x()
        dy = global_pos.y() - self.start_mouse_pos.y()
        rect = self.start_geometry
        x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
        
        if self.resize_edges & 1: x += dx; w -= dx
        elif self.resize_edges & 2: w += dx
        if self.resize_edges & 4: y += dy; h -= dy
        elif self.resize_edges & 8: h += dy
            
        if w < 120:
            if self.resize_edges & 1: x -= (120 - w)
            w = 120
        if h < 200:
            if self.resize_edges & 4: y -= (200 - h)
            h = 200
            
        if hasattr(self.overlay, 'adjust_responsive_layout'):
            self.overlay.adjust_responsive_layout(w)
            
        self.overlay.setGeometry(x, y, w, h)

    def eventFilter(self, obj, event):
        if isinstance(event, QMouseEvent):
            global_pos = event.globalPos()
            local_pos = self.overlay.mapFromGlobal(global_pos)
            
            is_hidden = getattr(self.overlay, 'is_hidden', False)
            edges = self.get_resize_edges(global_pos)
            is_resizing_area = (edges != 0) and not is_hidden
            
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                if is_hidden:
                    self.dragging = True
                    self.drag_offset = self.overlay.pos() - global_pos
                    self.did_drag_while_hidden = False
                    return True
                    
                if obj == self.overlay.drag_handle:
                    self.dragging = True
                    self.drag_offset = self.overlay.pos() - global_pos
                elif is_resizing_area:
                    self.resizing = True
                    self.resize_edges = edges
                    self.start_geometry = self.overlay.geometry()
                    self.start_mouse_pos = global_pos
                    
            elif event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
                if self.dragging:
                    self.dragging = False
                    if is_hidden:
                        if not self.did_drag_while_hidden: self.overlay.restore_from_edge()
                        else: self.overlay.snap_to_closest_edge()
                    self.overlay.save_settings()
                elif self.resizing:
                    self.resizing = False
                    self.overlay.save_settings()
                    
            elif event.type() == QEvent.MouseMove:
                if not (event.buttons() & Qt.LeftButton):
                    if is_resizing_area: 
                        self.update_cursor(edges)
                    else: 
                        if getattr(self, 'cursor_modified', False):
                            self.overlay.unsetCursor()
                            self.cursor_modified = False
                else:
                    if self.dragging:
                        if is_hidden:
                            self.did_drag_while_hidden = True
                            new_pos = global_pos + self.drag_offset
                            delta = new_pos - self.overlay.pos()
                            if self.overlay.normal_geometry:
                                self.overlay.normal_geometry.translate(delta.x(), delta.y())
                        self.overlay.move(global_pos + self.drag_offset)
                    elif self.resizing:
                        self.do_resize(global_pos)
                        
        return super().eventFilter(obj, event)

class TTSWorker(QThread):
    speech_status_signal = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.q = queue.Queue()
        self.selected_voice_name = None  # None = system default
        self.current_proc = None
        
    def set_voice(self, voice_name):
        """Set voice by display name (used by SelectVoice in SAPI)."""
        self.selected_voice_name = voice_name
        
    def _speak_via_powershell(self, text, voice_name=None):
        """Speak text using Windows SAPI via PowerShell subprocess (fresh process every call)."""
        import subprocess
        # Sanitize text for PowerShell single-quoted string
        safe = text.replace("'", "").replace('"', '').replace('`', '').replace('\n', ' ')
        # Sanitize voice name
        voice_cmd = ''
        if voice_name:
            safe_v = voice_name.replace("'", '').replace('"', '')
            voice_cmd = f'$s.SelectVoice("{safe_v}"); '
        ps = (
            'Add-Type -AssemblyName System.Speech; '
            '$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; '
            f'{voice_cmd}'
            '$s.Rate = 2; '
            f'$s.Speak("{safe}"); '
            '$s.Dispose()'
        )
        try:
            self.current_proc = subprocess.Popen(
                ['powershell', '-WindowStyle', 'Hidden', '-NonInteractive', '-Command', ps],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=0x08000000  # CREATE_NO_WINDOW
            )
            self.current_proc.wait(timeout=90)
        except Exception as e:
            print('TTS PowerShell error:', e)
        finally:
            self.current_proc = None
        
    def run(self):
        while True:
            text = self.q.get()
            if text is None:
                break
            # Clean markdown/code from spoken text
            text_to_speak = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
            text_to_speak = re.sub(r'[`*#]', '', text_to_speak).strip()
            if text_to_speak:
                self.speech_status_signal.emit(True)
                self._speak_via_powershell(text_to_speak, self.selected_voice_name)
                self.speech_status_signal.emit(False)

    def speak(self, text):
        self.q.put(text)
        
    def stop_speech(self):
        # Drain queue
        while not self.q.empty():
            try: self.q.get_nowait()
            except queue.Empty: break
        # Kill any running subprocess
        if self.current_proc and self.current_proc.poll() is None:
            try: self.current_proc.kill()
            except Exception: pass
        
    def stop(self):
        self.stop_speech()
        self.q.put(None)

class DictationWorker(QThread):
    finished_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str)

    def run(self):
        try:
            # pyrefly: ignore [missing-import]
            import speech_recognition as sr
            import pyaudio
            
            r = sr.Recognizer()
            p = pyaudio.PyAudio()
            
            stereo_mix_idx = None
            for i in range(p.get_device_count()):
                try:
                    dev_info = p.get_device_info_by_index(i)
                    name = dev_info.get('name', '').lower()
                    max_inputs = dev_info.get('maxInputChannels', 0)
                    if 'stereo mix' in name and max_inputs > 0:
                        stereo_mix_idx = i
                        break
                except Exception:
                    pass
            p.terminate()

            audio = None
            text = ""
            
            # 1. Attempt to capture and recognize from System Speaker Output (Stereo Mix loopback - 80% chance)
            if stereo_mix_idx is not None:
                try:
                    self.status_signal.emit("Listening Speaker...")
                    with sr.Microphone(device_index=stereo_mix_idx) as source:
                        r.adjust_for_ambient_noise(source, duration=0.2)
                        # Quick timeout to check if interviewer speaks
                        audio = r.listen(source, timeout=3.5, phrase_time_limit=15)
                    if audio:
                        self.status_signal.emit("Recognizing Speaker...")
                        text = r.recognize_google(audio).strip()
                except Exception:
                    audio = None # Force fallback to Mic
                    
            # 2. Fall back to Microphone Input (Microphone Array - 20% chance)
            if not text:
                try:
                    self.status_signal.emit("Listening Mic...")
                    with sr.Microphone() as source:
                        r.adjust_for_ambient_noise(source, duration=0.2)
                        audio = r.listen(source, timeout=5, phrase_time_limit=15)
                    if audio:
                        self.status_signal.emit("Recognizing Mic...")
                        text = r.recognize_google(audio).strip()
                except Exception:
                    pass
                
            if text:
                self.finished_signal.emit(text)
            else:
                self.error_signal.emit("No speech recognized.")
        except ImportError:
            self.error_signal.emit("Please run: pip install SpeechRecognition pyaudio")
        except Exception as e:
            self.error_signal.emit(f"Audio capture error: {str(e)}")

from PyQt5.QtWidgets import QWidget

class AudioWaveWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.phase = 0.0
        self.active = False
        self.mode = "listening" # "listening" or "speaking"
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_wave)
        self.timer.start(30) # ~33 fps
        self.setFixedHeight(24)
        self.setMinimumWidth(85)
        
    def set_active(self, active, mode="listening"):
        self.active = active
        self.mode = mode
        if active: self.show()
        else: self.hide()
        
    def update_wave(self):
        if self.active:
            self.phase += 0.15
            self.update()
            
    def paintEvent(self, event):
        if not self.active:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        w = self.width()
        h = self.height()
        mid_y = h / 2.0
        
        if self.mode == "listening":
            colors = [
                QColor(139, 92, 246, 120),  # Purple
                QColor(236, 72, 153, 90),   # Pink
                QColor(59, 130, 246, 70)    # Blue
            ]
        else: # speaking
            colors = [
                QColor(16, 185, 129, 120),  # Emerald
                QColor(52, 211, 153, 90),   # Light Emerald
                QColor(139, 92, 246, 70)    # Purple
            ]
            
        import math
        for idx, color in enumerate(colors):
            path = QPainterPath()
            path.moveTo(0, mid_y)
            
            amp_factor = 0.8 - (idx * 0.2)
            max_amp = (h / 2.0 - 2) * amp_factor
            freq = 2.0 + idx * 0.5
            
            for x in range(0, w + 1):
                t = x / w
                taper = math.sin(t * math.pi)
                y = mid_y + taper * max_amp * math.sin(freq * t * 2 * math.pi - self.phase + idx * 1.5)
                path.lineTo(x, y)
                
            pen = QPen(color, 2)
            painter.setPen(pen)
            painter.drawPath(path)

class VoiceSetupWorker(QThread):
    setup_done = pyqtSignal(object, object) # recognizer, microphone
    error_signal = pyqtSignal(str)

    def run(self):
        try:
            # pyrefly: ignore [missing-import]
            import speech_recognition as sr
            r = sr.Recognizer()
            m = sr.Microphone()
            with m as source:
                r.adjust_for_ambient_noise(source, duration=0.5)
            self.setup_done.emit(r, m)
        except ImportError:
            self.error_signal.emit("Please run: pip install SpeechRecognition pyaudio")
        except Exception as e:
            self.error_signal.emit(str(e))

class ModernIconButton(QPushButton):
    def __init__(self, icon_type, text="", parent=None):
        super().__init__(text, parent)
        self.icon_type = icon_type
        self.setMinimumHeight(28)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        # Override stylesheet defaults so QPainter doesn't get messed up by CSS padding/border
        self.setStyleSheet("""
            background: transparent;
            border: none;
            padding: 0px;
        """)
        
    def sizeHint(self):
        base_hint = super().sizeHint()
        # Add extra width to fit the left icon, text gap, and right margin safely
        extra_w = 40 if self.icon_type else 20
        return QSize(base_hint.width() + extra_w, max(base_hint.height(), 28))
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        is_hovered = self.underMouse()
        is_checked = self.isChecked() if self.isCheckable() else False
        
        is_dark = True
        w = self.window()
        if hasattr(w, 'is_dark'):
            is_dark = w.is_dark

        if is_dark:
            if is_checked:
                bg_color = QColor(139, 92, 246, 70)
                border_color = QColor(139, 92, 246, 220)
                icon_color = QColor(167, 139, 250)
                text_color = QColor(255, 255, 255)
            elif is_hovered:
                bg_color = QColor(255, 255, 255, 22)
                border_color = QColor(255, 255, 255, 45)
                icon_color = QColor(255, 255, 255)
                text_color = QColor(255, 255, 255)
            else:
                bg_color = QColor(255, 255, 255, 8)
                border_color = QColor(255, 255, 255, 18)
                icon_color = QColor(203, 213, 225)
                text_color = QColor(203, 213, 225)
        else:
            if is_checked:
                bg_color = QColor(139, 92, 246, 70)
                border_color = QColor(139, 92, 246, 220)
                icon_color = QColor(109, 40, 217)
                text_color = QColor(17, 24, 39)
            elif is_hovered:
                bg_color = QColor(0, 0, 0, 15)
                border_color = QColor(0, 0, 0, 30)
                icon_color = QColor(17, 24, 39)
                text_color = QColor(17, 24, 39)
            else:
                bg_color = QColor(0, 0, 0, 5)
                border_color = QColor(0, 0, 0, 40)
                icon_color = QColor(75, 85, 99)
                text_color = QColor(75, 85, 99)
            
        rect = self.rect()
        painter.setBrush(bg_color)
        painter.setPen(QPen(border_color, 1))
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 6, 6)
        
        # Left icon dimensions
        icon_width = 14
        icon_height = 14
        margin = 8
        
        icon_rect = QRect(margin, (rect.height() - icon_height) // 2, icon_width, icon_height)
        
        painter.setPen(QPen(icon_color, 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(Qt.NoBrush)
        
        itype = self.icon_type
        if itype == "send":
            # Paper airplane / Send arrow
            path = QPainterPath()
            path.moveTo(icon_rect.x() + 2, icon_rect.y() + 2)
            path.lineTo(icon_rect.x() + 14, icon_rect.y() + 7)
            path.lineTo(icon_rect.x() + 2, icon_rect.y() + 12)
            path.lineTo(icon_rect.x() + 5, icon_rect.y() + 7)
            path.closeSubpath()
            painter.setBrush(icon_color)
            painter.drawPath(path)
        elif itype == "stop":
            # Square stop icon
            painter.setBrush(icon_color)
            painter.drawRoundedRect(icon_rect.x() + 2, icon_rect.y() + 2, 10, 10, 2, 2)
        elif itype == "scan":
            # Camera
            painter.drawRoundedRect(icon_rect.x(), icon_rect.y() + 2, 14, 10, 1.5, 1.5)
            painter.drawEllipse(icon_rect.x() + 3, icon_rect.y() + 4, 8, 8)
            painter.drawRect(icon_rect.x() + 4, icon_rect.y(), 6, 2)
        elif itype == "inject":
            # Lightning bolt
            path = QPainterPath()
            path.moveTo(icon_rect.x() + 9, icon_rect.y())
            path.lineTo(icon_rect.x() + 2, icon_rect.y() + 8)
            path.lineTo(icon_rect.x() + 7, icon_rect.y() + 8)
            path.lineTo(icon_rect.x() + 5, icon_rect.y() + 14)
            path.lineTo(icon_rect.x() + 12, icon_rect.y() + 6)
            path.lineTo(icon_rect.x() + 7, icon_rect.y() + 6)
            path.closeSubpath()
            painter.setBrush(icon_color)
            painter.drawPath(path)
        elif itype in ["voice_on", "voice"]:
            # Speaker on
            painter.drawPolygon(QPoint(icon_rect.x() + 1, icon_rect.y() + 4),
                                QPoint(icon_rect.x() + 5, icon_rect.y() + 4),
                                QPoint(icon_rect.x() + 9, icon_rect.y() + 1),
                                QPoint(icon_rect.x() + 9, icon_rect.y() + 13),
                                QPoint(icon_rect.x() + 5, icon_rect.y() + 10),
                                QPoint(icon_rect.x() + 1, icon_rect.y() + 10))
            # Sound waves arc
            painter.drawArc(icon_rect.x() + 5, icon_rect.y() + 3, 7, 8, -60 * 16, 120 * 16)
        elif itype == "voice_off":
            # Speaker off / muted
            painter.drawPolygon(QPoint(icon_rect.x() + 1, icon_rect.y() + 4),
                                QPoint(icon_rect.x() + 5, icon_rect.y() + 4),
                                QPoint(icon_rect.x() + 9, icon_rect.y() + 1),
                                QPoint(icon_rect.x() + 9, icon_rect.y() + 13),
                                QPoint(icon_rect.x() + 5, icon_rect.y() + 10),
                                QPoint(icon_rect.x() + 1, icon_rect.y() + 10))
            painter.drawLine(icon_rect.x() + 1, icon_rect.y() + 1, icon_rect.x() + 13, icon_rect.y() + 13)
        elif itype == "settings":
            # Gear
            cx = icon_rect.x() + 7
            cy = icon_rect.y() + 7
            painter.drawEllipse(cx - 3, cy - 3, 6, 6)
            for i in range(8):
                angle = i * 45
                import math
                rad = math.radians(angle)
                x1 = cx + 3 * math.cos(rad)
                y1 = cy + 3 * math.sin(rad)
                x2 = cx + 6 * math.cos(rad)
                y2 = cy + 6 * math.sin(rad)
                painter.drawLine(int(x1), int(y1), int(x2), int(y2))
        elif itype in ["mic", "single_mic", "interview_mic"]:
            # Standard push-to-talk microphone
            painter.drawRoundedRect(icon_rect.x() + 4, icon_rect.y(), 6, 9, 2.5, 2.5)
            painter.drawArc(icon_rect.x() + 1, icon_rect.y() + 3, 12, 8, -180 * 16, 180 * 16)
            painter.drawLine(icon_rect.x() + 7, icon_rect.y() + 11, icon_rect.x() + 7, icon_rect.y() + 14)
            painter.drawLine(icon_rect.x() + 3, icon_rect.y() + 14, icon_rect.x() + 11, icon_rect.y() + 14)
        elif itype == "continuous_mic":
            # Microphone with radiating sound waves
            painter.drawRoundedRect(icon_rect.x() + 4, icon_rect.y(), 6, 9, 2.5, 2.5)
            painter.drawArc(icon_rect.x() + 1, icon_rect.y() + 3, 12, 8, -180 * 16, 180 * 16)
            painter.drawLine(icon_rect.x() + 7, icon_rect.y() + 11, icon_rect.x() + 7, icon_rect.y() + 14)
            painter.drawLine(icon_rect.x() + 3, icon_rect.y() + 14, icon_rect.x() + 11, icon_rect.y() + 14)
            
            # Left and right radiating waves
            painter.drawArc(icon_rect.x() - 1, icon_rect.y(), 3, 9, 90 * 16, 180 * 16)
            painter.drawArc(icon_rect.x() + 12, icon_rect.y(), 3, 9, -90 * 16, 180 * 16)
        elif itype == "interview":
            # Overlapping Conversation bubbles
            painter.drawRoundedRect(icon_rect.x(), icon_rect.y() + 1, 9, 7, 1.5, 1.5)
            path = QPainterPath()
            path.moveTo(icon_rect.x() + 2, icon_rect.y() + 8)
            path.lineTo(icon_rect.x() + 1, icon_rect.y() + 11)
            path.lineTo(icon_rect.x() + 4, icon_rect.y() + 8)
            painter.drawPath(path)
            
            painter.drawRoundedRect(icon_rect.x() + 5, icon_rect.y() + 5, 9, 7, 1.5, 1.5)
            path2 = QPainterPath()
            path2.moveTo(icon_rect.x() + 12, icon_rect.y() + 12)
            path2.lineTo(icon_rect.x() + 13, icon_rect.y() + 15)
            path2.lineTo(icon_rect.x() + 10, icon_rect.y() + 12)
            painter.drawPath(path2)
        elif itype == "clear":
            # Trash can
            painter.drawRect(icon_rect.x() + 2, icon_rect.y() + 3, 10, 11)
            painter.drawLine(icon_rect.x(), icon_rect.y() + 3, icon_rect.x() + 14, icon_rect.y() + 3)
            painter.drawRect(icon_rect.x() + 5, icon_rect.y(), 4, 3)
            painter.drawLine(icon_rect.x() + 5, icon_rect.y() + 6, icon_rect.x() + 5, icon_rect.y() + 11)
            painter.drawLine(icon_rect.x() + 9, icon_rect.y() + 6, icon_rect.x() + 9, icon_rect.y() + 11)
        elif itype == "new_chat":
            # Plus
            painter.drawLine(icon_rect.x() + 7, icon_rect.y() + 1, icon_rect.x() + 7, icon_rect.y() + 13)
            painter.drawLine(icon_rect.x() + 1, icon_rect.y() + 7, icon_rect.x() + 13, icon_rect.y() + 7)
        elif itype == "hide":
            # Minimize/Hide icon (horizontal line)
            painter.drawLine(icon_rect.x() + 2, icon_rect.y() + 10, icon_rect.x() + 12, icon_rect.y() + 10)
        elif itype == "close":
            # X icon
            painter.drawLine(icon_rect.x() + 3, icon_rect.y() + 3, icon_rect.x() + 11, icon_rect.y() + 11)
            painter.drawLine(icon_rect.x() + 3, icon_rect.y() + 11, icon_rect.x() + 11, icon_rect.y() + 3)
        elif itype == "web_scrap":
            # Crop / Selection brackets & lens
            painter.drawLine(icon_rect.x(), icon_rect.y() + 4, icon_rect.x(), icon_rect.y())
            painter.drawLine(icon_rect.x(), icon_rect.y(), icon_rect.x() + 4, icon_rect.y())
            painter.drawLine(icon_rect.x() + 10, icon_rect.y(), icon_rect.x() + 14, icon_rect.y())
            painter.drawLine(icon_rect.x() + 14, icon_rect.y(), icon_rect.x() + 14, icon_rect.y() + 4)
            painter.drawLine(icon_rect.x(), icon_rect.y() + 10, icon_rect.x(), icon_rect.y() + 14)
            painter.drawLine(icon_rect.x(), icon_rect.y() + 14, icon_rect.x() + 4, icon_rect.y() + 14)
            painter.drawLine(icon_rect.x() + 10, icon_rect.y() + 14, icon_rect.x() + 14, icon_rect.y() + 14)
            painter.drawLine(icon_rect.x() + 14, icon_rect.y() + 14, icon_rect.x() + 14, icon_rect.y() + 10)
            painter.drawEllipse(icon_rect.x() + 4, icon_rect.y() + 4, 6, 6)
        elif itype == "sidebar":
            # Hamburger menu
            painter.drawLine(icon_rect.x() + 2, icon_rect.y() + 3, icon_rect.x() + 12, icon_rect.y() + 3)
            painter.drawLine(icon_rect.x() + 2, icon_rect.y() + 7, icon_rect.x() + 12, icon_rect.y() + 7)
            painter.drawLine(icon_rect.x() + 2, icon_rect.y() + 11, icon_rect.x() + 12, icon_rect.y() + 11)
        elif itype == "theme_dark":
            # Moon
            painter.drawArc(icon_rect.x() + 1, icon_rect.y() + 1, 10, 10, 30 * 16, 250 * 16)
        elif itype == "theme_light":
            # Sun
            painter.drawEllipse(icon_rect.x() + 3, icon_rect.y() + 3, 8, 8)
            painter.drawLine(icon_rect.x() + 7, icon_rect.y(), icon_rect.x() + 7, icon_rect.y() + 2)
            painter.drawLine(icon_rect.x() + 7, icon_rect.y() + 12, icon_rect.x() + 7, icon_rect.y() + 14)
            painter.drawLine(icon_rect.x(), icon_rect.y() + 7, icon_rect.x() + 2, icon_rect.y() + 7)
            painter.drawLine(icon_rect.x() + 12, icon_rect.y() + 7, icon_rect.x() + 14, icon_rect.y() + 7)
        elif itype == "focus":
            # Target / Crosshair
            painter.drawEllipse(icon_rect.x() + 2, icon_rect.y() + 2, 10, 10)
            painter.drawEllipse(icon_rect.x() + 6, icon_rect.y() + 6, 2, 2)
            painter.drawLine(icon_rect.x() + 7, icon_rect.y() - 1, icon_rect.x() + 7, icon_rect.y() + 2)
            painter.drawLine(icon_rect.x() + 7, icon_rect.y() + 12, icon_rect.x() + 7, icon_rect.y() + 15)
            painter.drawLine(icon_rect.x() - 1, icon_rect.y() + 7, icon_rect.x() + 2, icon_rect.y() + 7)
            painter.drawLine(icon_rect.x() + 12, icon_rect.y() + 7, icon_rect.x() + 15, icon_rect.y() + 7)
        elif itype == "more":
            cx = icon_rect.x() + 7
            cy = icon_rect.y() + 7
            painter.setBrush(icon_color)
            painter.drawEllipse(cx - 5, cy - 1, 2, 2)
            painter.drawEllipse(cx - 1, cy - 1, 2, 2)
            painter.drawEllipse(cx + 3, cy - 1, 2, 2)
        else:
            painter.drawEllipse(icon_rect)
            
        # Draw Text centered with icon margin offset
        if self.text():
            painter.setPen(text_color)
            painter.setFont(self.font())
            text_rect = QRect(icon_rect.right() + 6, 0, rect.width() - icon_rect.right() - 12, rect.height())
            painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, self.text())

class AITaskWorker(QThread):
    finished_signal = pyqtSignal(str, str, str) # type, content, raw_code
    error_signal = pyqtSignal(str)

    def __init__(self, provider, api_keys, task_type, prompt, history=None, image_path=None, provider_models=None):
        super().__init__()
        self.provider = provider
        self.api_keys = api_keys
        self.task_type = task_type
        self.prompt = prompt
        self.history = history or []
        self.image_path = image_path
        self.provider_models = provider_models or {}

    def run(self):
        import urllib.request
        import urllib.parse
        try:
            if self.task_type == "imagine":
                import time
                encoded_prompt = urllib.parse.quote(self.prompt)
                url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=512&height=512&nologo=true"
                filename = f"generated_image_{int(time.time())}.jpg"
                save_path = os.path.join(get_app_dir(), filename)
                
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'})
                with urllib.request.urlopen(req) as response, open(save_path, 'wb') as out_file:
                    out_file.write(response.read())
                self.finished_signal.emit("image", save_path, "")
                
            elif self.task_type in ["text", "vision"]:
                system_prompt = (
                    "You are a highly capable AI assistant operating within a stealth overlay. Provide direct, concise answers. "
                    "If providing code, always wrap it in ``` backticks. You have access to the user's Chat History. "
                    "Use context intelligently: if the user's request is a continuation, reference past history. "
                    "If they change the subject or upload a completely new image, treat it as a new context while retaining general memory."
                )
                
                history_text = ""
                for msg in self.history:
                    if msg['role'] == 'user': history_text += f"\nUser: {msg['content']}"
                    elif msg['role'] == 'ai': history_text += f"\nAI: {msg['content']}"
                    
                full_prompt = f"{system_prompt}\n\nChat History:{history_text}\n\nCurrent User Request: {self.prompt}"
                
                text_response = ""
                
                active_provider = "Gemini" if (self.task_type == "vision" and self.provider != "NVIDIA") else self.provider
                
                if active_provider == "Gemini":
                    try:
                        import google.generativeai as genai
                        import PIL.Image
                    except ImportError:
                        self.error_signal.emit("google-generativeai and pillow are not installed.")
                        return
                    
                    key = self.api_keys.get("gemini", "")
                    if not key:
                        self.error_signal.emit("Gemini API Key is missing.")
                        return
                    genai.configure(api_key=key)
                    
                    try:
                        # Try the selected model from settings first
                        chosen_model = self.provider_models.get("gemini", "gemini-2.5-flash")
                        model = genai.GenerativeModel(chosen_model)
                        if self.task_type == "vision" and self.image_path and os.path.exists(self.image_path):
                            img = PIL.Image.open(self.image_path)
                            response = model.generate_content([full_prompt, img], request_options={"timeout": 15.0})
                        else:
                            response = model.generate_content(full_prompt, request_options={"timeout": 15.0})
                        text_response = response.text
                    except Exception as ge:
                        # Fallback to gemini-1.5-flash before listing models to save quota
                        try:
                            model = genai.GenerativeModel('gemini-1.5-flash')
                            if self.task_type == "vision" and self.image_path and os.path.exists(self.image_path):
                                img = PIL.Image.open(self.image_path)
                                response = model.generate_content([full_prompt, img], request_options={"timeout": 15.0})
                            else:
                                response = model.generate_content(full_prompt, request_options={"timeout": 15.0})
                            text_response = response.text
                        except Exception as ge2:
                            # Final fallback: list_models to find what's available
                            try:
                                available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                                if available_models:
                                    valid_fallback = None
                                    preferred = ["models/gemini-2.5-flash", "models/gemini-2.0-flash-exp", "models/gemini-1.5-flash", "models/gemini-1.5-pro", "models/gemini-1.0-pro", "models/gemini-pro"]
                                    for p in preferred:
                                        if p in available_models:
                                            valid_fallback = p
                                            break
                                    if not valid_fallback:
                                        valid_fallback = available_models[0]
                                        
                                    first_model = valid_fallback.replace('models/', '') 
                                    model = genai.GenerativeModel(first_model)
                                    if self.task_type == "vision" and self.image_path and os.path.exists(self.image_path):
                                        img = PIL.Image.open(self.image_path)
                                        response = model.generate_content([full_prompt, img], request_options={"timeout": 15.0})
                                    else:
                                        response = model.generate_content(full_prompt, request_options={"timeout": 15.0})
                                    text_response = response.text
                                else:
                                    raise Exception("No generative models found for this API key.")
                            except Exception as fallback_e:
                                raise Exception(f"Dynamic fallback failed: {fallback_e}. Original error: {ge2}")
                    
                elif active_provider == "Groq":
                    try:
                        import groq
                    except ImportError:
                        self.error_signal.emit("groq is not installed.")
                        return
                        
                    key = self.api_keys.get("groq", "")
                    if not key:
                        self.error_signal.emit("Groq API Key is missing.")
                        return
                    client = groq.Groq(api_key=key, timeout=15.0)
                    messages = [{"role": "system", "content": system_prompt}]
                    for msg in self.history:
                        if msg['role'] == 'user': messages.append({"role": "user", "content": msg['content']})
                        elif msg['role'] == 'ai': messages.append({"role": "assistant", "content": msg['content']})
                    messages.append({"role": "user", "content": self.prompt})
                    
                    try:
                        chat_completion = client.chat.completions.create(
                            messages=messages,
                            model=self.provider_models.get("groq", "llama-3.3-70b-versatile"),
                        )
                        text_response = chat_completion.choices[0].message.content
                    except Exception as e:
                        gemini_key = self.api_keys.get("gemini", "")
                        if gemini_key:
                            try:
                                import google.generativeai as genai
                                import PIL.Image
                                genai.configure(api_key=gemini_key)
                                model = genai.GenerativeModel('gemini-2.5-flash')
                                response = model.generate_content(full_prompt, request_options={"timeout": 15.0})
                                text_response = f"⚠️ *[Groq Error: Fell back to Gemini]*\n\n" + response.text
                            except Exception as ge_fallback:
                                self.error_signal.emit(f"Groq Error: {e} and Gemini fallback failed: {ge_fallback}")
                                return
                        else:
                            self.error_signal.emit(f"Groq Error: {e} (No Gemini key for fallback)")
                            return
                    
                elif active_provider == "OpenRouter":
                    try:
                        # pyrefly: ignore [missing-import]
                        import openai
                    except ImportError:
                        self.error_signal.emit("openai is not installed.")
                        return
                        
                    key = self.api_keys.get("openrouter", "")
                    if not key:
                        self.error_signal.emit("OpenRouter API Key is missing.")
                        return
                    client = openai.OpenAI(base_url="https://openrouter.ai/api/v1", api_key=key, timeout=15.0)
                    
                    try:
                        req = urllib.request.Request(
                            "https://openrouter.ai/api/v1/models",
                            headers={"User-Agent": "Mozilla/5.0"}
                        )
                        with urllib.request.urlopen(req, timeout=5.0) as response:
                            models_data = json.loads(response.read())
                        
                        free_models = []
                        for m in models_data.get('data', []):
                            pricing = m.get('pricing', {})
                            prompt_price = pricing.get('prompt', 0)
                            try:
                                is_free = float(prompt_price) == 0.0
                            except (ValueError, TypeError):
                                is_free = False
                            
                            if is_free and m.get('id', '').endswith(':free'):
                                free_models.append(m['id'])
                    except Exception as e:
                        print("Failed to fetch OpenRouter free models dynamically:", e)
                        free_models = []
                        
                    if not free_models:
                        free_models = [
                            "google/gemini-2.5-flash:free",
                            "meta-llama/llama-3.3-70b-instruct:free",
                            "qwen/qwen-2.5-7b-instruct:free",
                            "meta-llama/llama-3.2-3b-instruct:free",
                            "mistralai/mistral-7b-instruct:free"
                        ]
                        
                    chosen_or_model = self.provider_models.get("openrouter", "google/gemini-2.5-flash:free")
                    if chosen_or_model:
                        free_models = [chosen_or_model] + [m for m in free_models if m != chosen_or_model]
                        
                    messages = [{"role": "system", "content": system_prompt}]
                    for msg in self.history:
                        if msg['role'] == 'user': messages.append({"role": "user", "content": msg['content']})
                        elif msg['role'] == 'ai': messages.append({"role": "assistant", "content": msg['content']})
                    messages.append({"role": "user", "content": self.prompt})
                    
                    completion = None
                    last_err = None
                    for model_id in free_models[:10]:
                        try:
                            completion = client.chat.completions.create(
                                extra_headers={"HTTP-Referer": "https://invisible.ai", "X-Title": "Stealth AI"},
                                model=model_id,
                                messages=messages
                            )
                            break
                        except Exception as e:
                            last_err = e
                            continue
                    
                    if not completion:
                        gemini_key = self.api_keys.get("gemini", "")
                        if gemini_key:
                            try:
                                import google.generativeai as genai
                                import PIL.Image
                                genai.configure(api_key=gemini_key)
                                model = genai.GenerativeModel('gemini-2.5-flash')
                                response = model.generate_content(full_prompt, request_options={"timeout": 15.0})
                                text_response = f"⚠️ *[OpenRouter Error: Fell back to Gemini]*\n\n" + response.text
                            except Exception as ge_fallback:
                                self.error_signal.emit(f"All OpenRouter free models failed. Last Error: {last_err} and Gemini fallback failed: {ge_fallback}")
                                return
                        else:
                            self.error_signal.emit(f"All OpenRouter free models failed. Last Error: {last_err}")
                            return
                    else:
                        text_response = completion.choices[0].message.content
 
                elif active_provider == "NVIDIA":
                    try:
                        # pyrefly: ignore [missing-import]
                        import openai
                    except ImportError:
                        self.error_signal.emit("openai is not installed.")
                        return
                        
                    key = self.api_keys.get("nvidia", "")
                    if not key:
                        self.error_signal.emit("NVIDIA API Key is missing.")
                        return
                        
                    client = openai.OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=key, timeout=15.0)
                    
                    if self.task_type == "vision" and self.image_path and os.path.exists(self.image_path):
                        import base64
                        try:
                            with open(self.image_path, "rb") as img_file:
                                base64_image = base64.b64encode(img_file.read()).decode('utf-8')
                            
                            messages = [
                                {
                                    "role": "user",
                                    "content": [
                                        {"type": "text", "text": full_prompt},
                                        {
                                            "type": "image_url",
                                            "image_url": {
                                                "url": f"data:image/png;base64,{base64_image}"
                                            }
                                        }
                                    ]
                                }
                            ]
                            
                            chosen_nv_model = self.provider_models.get("nvidia", "nvidia/llama-3.1-nemotron-70b-instruct")
                            vision_model = chosen_nv_model if "vision" in chosen_nv_model.lower() else "meta/llama-3.2-11b-vision-instruct"
                            completion = client.chat.completions.create(
                                model=vision_model,
                                messages=messages,
                                max_tokens=1024,
                                temperature=0.70,
                                top_p=1.00
                            )
                            text_response = completion.choices[0].message.content
                        except Exception as e:
                            self.error_signal.emit(f"NVIDIA Vision Error: {e}")
                            return
                    else:
                        messages = [{"role": "system", "content": system_prompt}]
                        for msg in self.history:
                            if msg['role'] == 'user': messages.append({"role": "user", "content": msg['content']})
                            elif msg['role'] == 'ai': messages.append({"role": "assistant", "content": msg['content']})
                        messages.append({"role": "user", "content": self.prompt})
                        
                        try:
                            chosen_nv_model = self.provider_models.get("nvidia", "nvidia/llama-3.1-nemotron-70b-instruct")
                            # Standard fast mode: do not force reasoning_budget to prevent 1-minute server-side generation lags
                            completion = client.chat.completions.create(
                                model=chosen_nv_model,
                                messages=messages,
                                temperature=0.70,
                                top_p=0.95,
                                max_tokens=4096
                            )
                            msg_obj = completion.choices[0].message
                            reasoning = getattr(msg_obj, "reasoning_content", None)
                            main_content = msg_obj.content or ""
                            if reasoning:
                                text_response = f"> 💭 **Thinking Process:**\n> {reasoning.replace(chr(10), chr(10) + '> ')}\n\n{main_content}"
                            else:
                                text_response = main_content
                        except Exception as e:
                            # Try alternative model on NVIDIA first
                            fallback_nv = "meta/llama3-70b-instruct" if chosen_nv_model != "meta/llama3-70b-instruct" else "meta/llama-3.2-11b-vision-instruct"
                            try:
                                completion = client.chat.completions.create(
                                    model=fallback_nv,
                                    messages=messages,
                                    temperature=0.70,
                                    top_p=0.95,
                                    max_tokens=4096
                                )
                                msg_obj = completion.choices[0].message
                                text_response = msg_obj.content or ""
                            except Exception as e2:
                                # Full fallback to Gemini!
                                gemini_key = self.api_keys.get("gemini", "")
                                if gemini_key:
                                    try:
                                        import google.generativeai as genai
                                        import PIL.Image
                                        genai.configure(api_key=gemini_key)
                                        model = genai.GenerativeModel('gemini-2.5-flash')
                                        response = model.generate_content(full_prompt, request_options={"timeout": 15.0})
                                        text_response = f"⚠️ *[NVIDIA Error: Fell back to Gemini]*\n\n" + response.text
                                    except Exception as ge_fallback:
                                        self.error_signal.emit(f"NVIDIA Error: {e} (Fallback {fallback_nv} failed: {e2}) and Gemini fallback failed: {ge_fallback}")
                                        return
                                else:
                                    self.error_signal.emit(f"NVIDIA Error: {e} (Fallback {fallback_nv} failed: {e2}, no Gemini key)")
                                    return

                elif active_provider == "Google Web Search":
                    import urllib.request
                    import urllib.parse
                    import re
                    
                    self.finished_signal.emit("system", "Scraping web results...", "")
                    
                    query = urllib.parse.quote(self.prompt)
                    url = f"https://html.duckduckgo.com/html/?q={query}"
                    req = urllib.request.Request(
                        url, 
                        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
                    )
                    
                    try:
                        html = urllib.request.urlopen(req, timeout=10).read().decode('utf-8')
                        
                        text_response = "### 🌐 Live Web Search Results:\n\n"
                        
                        # Parse duckduckgo html results natively
                        pattern = r'<a class="result__snippet[^>]*href="([^"]+)"[^>]*>(.*?)</a>'
                        snippets = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)
                        
                        title_pattern = r'<h2 class="result__title">.*?<a[^>]*>(.*?)</a>'
                        titles = re.findall(title_pattern, html, re.DOTALL | re.IGNORECASE)
                        
                        import html as html_lib
                        count = 0
                        for i in range(min(5, len(snippets), len(titles))):
                            url = snippets[i][0]
                            desc = html_lib.unescape(re.sub(r'<[^>]+>', '', snippets[i][1]).strip())
                            title = html_lib.unescape(re.sub(r'<[^>]+>', '', titles[i]).strip())
                            
                            if url.startswith("//"): url = "https:" + url
                            
                            if "duckduckgo.com/l/?uddg=" in url:
                                try:
                                    encoded_url = url.split("uddg=")[1]
                                    if "&amp;rut=" in encoded_url:
                                        encoded_url = encoded_url.split("&amp;rut=")[0]
                                    elif "&rut=" in encoded_url:
                                        encoded_url = encoded_url.split("&rut=")[0]
                                    url = urllib.parse.unquote(encoded_url)
                                except: pass
                            
                            text_response += f"**[{title}]({url})**\n{desc}\n\n"
                            count += 1
                            
                        if count > 0:
                            gemini_key = self.api_keys.get("gemini", "")
                            if gemini_key:
                                try:
                                    import google.generativeai as genai
                                    genai.configure(api_key=gemini_key)
                                    
                                    target_model = "gemini-2.5-flash"
                                    try:
                                        models_list = genai.list_models()
                                        for m in models_list:
                                            if 'generateContent' in m.supported_generation_methods and "flash" in m.name.lower() and "8b" not in m.name.lower():
                                                target_model = m.name.replace('models/', '')
                                                break
                                    except Exception:
                                        pass
                                            
                                    model = genai.GenerativeModel(target_model)
                                    ai_prompt = (
                                        f"User Request: {self.prompt}\n\nLive Web Search Results:\n{text_response}\n\n"
                                        f"Please provide a comprehensive answer to the user's request. "
                                        f"Use the provided web search results as context and cite them where appropriate. "
                                        f"IMPORTANT: You are a senior developer. If the user asks how to do something (especially programming/technical), "
                                        f"you MUST provide a full, easy, step-by-step guide with COMPLETE code examples for every step. "
                                        f"Even if the search results do not contain the exact code, use your own expert programming knowledge to generate the code examples and solve the request."
                                    )
                                    self.finished_signal.emit("system", f"Synthesizing AI summary using {target_model}...", "")
                                    response = model.generate_content(ai_prompt)
                                    
                                    clean_sources = text_response.replace("### 🌐 Live Web Search Results:\n\n", "")
                                    text_response = f"{response.text}\n\n---\n**Sources Scanned:**\n" + clean_sources
                                except Exception as ai_e:
                                    text_response += f"\n\n*(AI Synthesis failed: {ai_e})*"
                            else:
                                text_response += "\n\n*(Note: Add a Gemini API Key in the top settings to automatically synthesize these web results!)*"
                        else:
                            text_response += "No results found or search engine blocked the request."
                            
                            
                    except Exception as e:
                        text_response = f"### 🌐 Web Search Failed:\n\n{str(e)}"
                    
                else:
                    self.error_signal.emit(f"Provider {active_provider} not implemented.")
                    return
                    
                raw_code = ""
                if "```" in text_response:
                    parts = text_response.split("```")
                    if len(parts) >= 3:
                        code_block = parts[1]
                        if '\n' in code_block:
                            first_line = code_block.split('\n')[0].strip()
                            if not any(c.isspace() for c in first_line):
                                code_block = code_block[code_block.find('\n')+1:]
                        raw_code = code_block.strip()
                        
                self.finished_signal.emit("text", text_response, raw_code)

        except Exception as e:
            self.error_signal.emit(str(e))

class ChatHistoryItemWidget(QWidget):
    def __init__(self, title, session_id, parent_overlay, parent_item):
        super().__init__()
        self.session_id = session_id
        self.parent_overlay = parent_overlay
        self.parent_item = parent_item
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 6, 4)
        layout.setSpacing(4)
        self.setMinimumHeight(34)
        
        is_dark = getattr(parent_overlay, 'is_dark', True)
        text_color = "#E5E7EB" if is_dark else "#1F2937"
        
        self.label = QLabel(title)
        self.label.setObjectName("history_label")
        self.label.setStyleSheet(f"color: {text_color}; font-size: 13px; font-weight: 500; background: transparent; border: none;")
        layout.addWidget(self.label, 1)
        
        self.delete_btn = QPushButton("✕")
        self.delete_btn.setFixedSize(20, 20)
        self.delete_btn.setCursor(Qt.PointingHandCursor)
        self.delete_btn.setToolTip("Delete this chat")
        self.delete_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: rgba(239, 68, 68, 150);
                border: none;
                font-weight: bold;
                font-size: 12px;
                border-radius: 4px;
                padding: 0px;
            }
            QPushButton:hover {
                background: rgba(239, 68, 68, 60);
                color: #ef4444;
            }
        """)
        self.delete_btn.clicked.connect(self.delete_item)
        layout.addWidget(self.delete_btn, 0, Qt.AlignVCenter)
        
    def delete_item(self):
        self.parent_overlay.delete_session(self.session_id)
        
    def mousePressEvent(self, event):
        self.parent_overlay.chat_list.setCurrentItem(self.parent_item)
        self.parent_overlay.on_chat_selected(self.parent_item)
        super().mousePressEvent(event)

class VisionInterviewWorker(QThread):
    result_signal = pyqtSignal(str, str) # question, answer
    chunk_signal = pyqtSignal(str)
    
    def __init__(self, image_data, voice_text=""):
        super().__init__()
        self.image_data = image_data
        self.voice_text = voice_text
        
    def run(self):
        try:
            import requests
            import json
            import io
            from PIL import Image
            import base64
            
            # Compress image to JPEG with lower quality to drastically reduce upload payload size and latency
            img_data_bytes = base64.b64decode(self.image_data)
            img = Image.open(io.BytesIO(img_data_bytes))
            # Resize image down to max width 1920px to preserve code and text readability
            img.thumbnail((1920, 1920), Image.Resampling.LANCZOS)
            
            output_buffer = io.BytesIO()
            img.convert('RGB').save(output_buffer, format="JPEG", quality=50, optimize=True)
            compressed_b64 = base64.b64encode(output_buffer.getvalue()).decode('utf-8')
            
            # Fetch Groq API Key if available from the parent application overlay
            app = QApplication.instance()
            groq_key = ""
            if hasattr(app, '_overlay_instance') and app._overlay_instance:
                groq_key = app._overlay_instance.api_keys.get("groq", "")
            
            prompt = (
                "You are an expert stealth technical and behavioral interviewer assistant. Your goal is to help the user pass their interview.\n"
                "Analyze the screen image and the transcribed audio of the interviewer. Perform intelligent context classification first:\n"
                "- DETECT USER CODE INTENTION: Scan the active code editor on the screen. Auto-identify the programming language/framework in use. If there is a coding task comment (e.g., `# find biggest prime number`) or an incomplete/undefined function signature (e.g., `def find_biggest_prime(numbers):` with no body or pass), treat this as an active coding intention and solve the programming task directly! Complete the function signature with clean code. Present the implementation using different approaches (e.g., Approach 1: Iterative, Approach 2: Recursive/Optimized) and format each approach in separate, cleanly defined code blocks.\n"
                "- DIRECT EXPLANATIONS: If the interviewer verbally asks an explicit explanation question in the audio, or if a reasoning/aptitude question is presented, provide a straight, direct, and neat explanation immediately without introductory pleasantries or meta commentary.\n"
                "- DETECT SCREEN QUESTIONS & COMMENTS: If there is a code comment describing a coding challenge, or if a coding test statement is visible on the screen, you MUST solve it. Do NOT return NO_QUESTION if there is a comment task, an undefined function signature, or a programming prompt on the screen.\n"
                "- IGNORE AUDIO NOISE AND POOR TRANSLCRIPTIONS: If the Transcribed Interviewer Audio is short, fragmented, poorly recognized (e.g. random letters, background chatter, gibberish, or words that do not form a coherent interview question), IGNORE it completely. Do not try to understand or answer noisy/broken audio messages.\n"
                "- ONLY INTERVIEW QUESTIONS: You must ONLY respond if there is an active technical coding challenge statement/prompt on the screen, an incomplete function signature to fill, a comment task, a new behavioral question verbally asked, or an active coding intention visible on the screen. Do NOT explain what is on the screen, do not summarize completed files, and do not describe the IDE structure or terminal window.\n"
                "- DISTINGUISH BETWEEN INTERVIEWER VS USER: Do not misunderstand the user's own active code typing (such as completed solutions) as questions asked by the interviewer. But ALWAYS complete empty or undefined functions and solve comments describing algorithms/tasks.\n\n"
                "RULES:\n"
                "1. If the interviewer asks a verbal question in the audio (behavioral, technical, or personal questions like 'why should we hire you', 'tell me about yourself', or experience questions), you MUST prioritize answering this audio question directly.\n"
                "2. If the interviewer presents a new technical/coding question on the screen, or if there is a task comment/incomplete function signature, synthesize the visual and spoken context and complete/solve it.\n"
                "3. Optimize your response: Keep explanations concise, clear, and direct. Do not include introductory filler. Speak or write code like a competent, professional candidate presenting their work naturally. Keep solutions simple and intermediate.\n\n"
                "Output your response strictly in this format:\n\n"
                "QUESTION:\n[The detected question/prompt (either from audio, screen text, comment, or function name)]\n\n"
                "SOLUTION:\n[Your response. Keep it in a neat, professional, and intermediate-level context. For coding questions, provide clean, simple code in the detected language/framework with realistic developer comments, preceded by a brief, natural 'thinking out loud' explanation. Format different approaches in separate code blocks. For behavioral/general questions, write a professional response in a natural, spoken human voice (simple, clear, and confident).]\n\n"
                "CRITICAL: If the Transcribed Interviewer Audio has no question from the interviewer AND the screen image contains only empty space, unrelated UI elements, or fully completed code without any task comments or undefined functions, you MUST reply EXACTLY with the single word: NO_QUESTION. Do not hallucinate questions or explain visual layout elements."
            )
            if self.voice_text:
                prompt += f"\n\nTranscribed Interviewer Audio: '{self.voice_text}'"
            
            full_text = ""
            
            if groq_key:
                # Use blazingly fast Groq LPU Vision (llama-3.2-11b-vision-preview)
                import groq
                client = groq.Groq(api_key=groq_key, timeout=15.0)
                try:
                    chat_completion = client.chat.completions.create(
                        messages=[
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": prompt},
                                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{compressed_b64}"}}
                                ]
                            }
                        ],
                        model="llama-3.2-11b-vision-preview",
                        max_tokens=512,
                        temperature=0.2
                    )
                    full_text = chat_completion.choices[0].message.content
                except Exception as ge_err:
                    # Clear groq_key so it falls back to NVIDIA NIM
                    groq_key = ""
                    
            if not groq_key:
                # Fallback to Nvidia NIM
                invoke_url = "https://integrate.api.nvidia.com/v1/chat/completions"
                headers = {
                    "Authorization": "Bearer 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",
                    "Accept": "text/event-stream"
                }
                payload = {
                    "model": "meta/llama-3.2-11b-vision-instruct",
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{compressed_b64}"}}
                            ]
                        }
                    ],
                    "max_tokens": 512,
                    "temperature": 0.2,
                    "top_p": 1.0,
                    "stream": True
                }
                response = requests.post(invoke_url, headers=headers, json=payload, timeout=25, stream=True)
                if response.status_code == 200:
                    for line in response.iter_lines():
                        if line:
                            decoded_line = line.decode('utf-8').strip()
                            if decoded_line.startswith("data:"):
                                data_str = decoded_line[5:].strip()
                                if data_str == "[DONE]":
                                    break
                                try:
                                    data_json = json.loads(data_str)
                                    chunk_text = data_json.get("choices", [{}])[0].get("delta", {}).get("content", "")
                                    if chunk_text:
                                        full_text += chunk_text
                                except Exception:
                                    pass
                else:
                    self.result_signal.emit("NO_QUESTION", "NO_QUESTION")
                    return
            
            # Check if the output contains NO_QUESTION (case-insensitive) or fails format validation
            full_text_upper = full_text.upper()
            if "NO_QUESTION" in full_text_upper or not full_text.strip():
                self.result_signal.emit("NO_QUESTION", "NO_QUESTION")
                return
                
            import re
            q_match = re.search(r'(?i)QUESTION:\s*(.*?)\s*SOLUTION:', full_text, re.DOTALL)
            s_match = re.search(r'(?i)SOLUTION:\s*(.*)', full_text, re.DOTALL)
            
            if not q_match or not s_match:
                self.result_signal.emit("NO_QUESTION", "NO_QUESTION")
                return
                
            question = q_match.group(1).strip()
            solution = s_match.group(1).strip()
            self.result_signal.emit(question, solution)
        except Exception as e:
            self.result_signal.emit("NO_QUESTION", "NO_QUESTION")

class LivePreviewPopup(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Make the preview popup completely invisible to standard screenshot and capture APIs
        try:
            hwnd = int(self.winId())
            ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x00000011) # WDA_EXCLUDEFROMCAPTURE
        except Exception as e:
            print("Failed to register popup display affinity:", e)
        
        self.resize(340, 260)
        self.offset = QPoint()
        
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(15, 15, 15, 15)
        
        self.frame = QFrame(self)
        self.frame.setStyleSheet("""
            QFrame {
                background-color: rgba(10, 7, 18, 140);
                border: 2px solid rgba(236, 72, 153, 160);
                border-radius: 12px;
            }
        """)
        self.frame_layout = QVBoxLayout(self.frame)
        self.frame_layout.setContentsMargins(12, 12, 12, 12)
        
        self.title = QLabel("🔴 LIVE VISION ACTIVE")
        self.title.setStyleSheet("color: #ec4899; font-weight: bold; font-family: 'Segoe UI'; font-size: 12px; border: none; background: transparent;")
        self.title.setAlignment(Qt.AlignCenter)
        self.frame_layout.addWidget(self.title)
        
        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setStyleSheet("border: 1px solid rgba(236, 72, 153, 40); background: rgba(0, 0, 0, 80); border-radius: 6px;")
        self.preview_label.setMinimumHeight(160)
        self.frame_layout.addWidget(self.preview_label)
        
        self.status_label = QLabel("Scanning for questions...")
        self.status_label.setStyleSheet("color: #a1a1aa; font-family: 'Segoe UI'; font-size: 11px; border: none; background: transparent;")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.frame_layout.addWidget(self.status_label)
        
        self.main_layout.addWidget(self.frame)
        
    def update_frame(self, pixmap):
        self.preview_label.setPixmap(pixmap.scaled(self.preview_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))


class OCRWorker(QThread):
    finished_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)

    def __init__(self, api_key, pixmap_or_list, chosen_model="gemini-2.5-flash"):
        super().__init__()
        self.api_key = api_key
        self.pixmap_or_list = pixmap_or_list
        self.chosen_model = chosen_model

    def run(self):
        try:
            import google.generativeai as genai
            import PIL.Image
            import io
            from PyQt5.QtCore import QBuffer, QByteArray, QIODevice
            
            # Configure Gemini
            genai.configure(api_key=self.api_key)
            
            # Check if list or single
            if isinstance(self.pixmap_or_list, list):
                pixmaps = self.pixmap_or_list
            else:
                pixmaps = [self.pixmap_or_list]
                
            imgs = []
            for pixmap in pixmaps:
                byte_array = QByteArray()
                buffer = QBuffer(byte_array)
                buffer.open(QIODevice.WriteOnly)
                pixmap.save(buffer, "PNG")
                img_bytes = byte_array.data()
                img = PIL.Image.open(io.BytesIO(img_bytes))
                imgs.append(img)
                
            # Generate OCR content
            model = genai.GenerativeModel(self.chosen_model)
            if len(imgs) > 1:
                prompt = (
                    "Perform OCR on these sequential images of a scrolling screen capture. "
                    "Extract all text, code, and content exactly as it appears. "
                    "Combine the content from all images in correct order (from first to last), "
                    "automatically aligning overlapping lines and deduplicating any content that "
                    "appears in multiple consecutive images. "
                    "Do not add any introduction, headers, markdown explanations, or footnotes. "
                    "Just return the raw unified text/code."
                )
            else:
                prompt = (
                    "Perform OCR on this image. Extract all text, code, and content exactly as it appears. "
                    "Do not add any introduction, headers, markdown explanations, or footnotes. "
                    "Just return the raw extracted text/code."
                )
                
            response = model.generate_content([prompt] + imgs, request_options={"timeout": 20.0})
            extracted_text = response.text
            self.finished_signal.emit(extracted_text)
        except Exception as e:
            self.error_signal.emit(str(e))


class MultiSnipController(QWidget):
    """Floating toolbar widget for managing manual multi-capture workflow.
    
    Allows user to manually scroll documents/pages and capture successive sections.
    Once finished, stacks all captured regions vertically into a single clean QPixmap.
    """
    snip_completed = pyqtSignal(QPixmap)

    def __init__(self, parent_overlay=None):
        super().__init__()
        self.parent_overlay = parent_overlay
        self.captures = []
        self.last_rect = QRect()

        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Position in bottom right corner
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen.width() - 360, screen.height() - 110, 340, 70)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        frame = QFrame()
        frame.setObjectName("controller_frame")
        frame.setStyleSheet("""
            QFrame#controller_frame {
                background-color: rgba(15, 23, 42, 235);
                border: 2px solid #8b5cf6;
                border-radius: 8px;
            }
            QLabel {
                color: #e2e8f0;
                font-family: 'Segoe UI';
                font-size: 11px;
                font-weight: bold;
                background: transparent;
                border: none;
            }
            QPushButton {
                background-color: rgba(255, 255, 255, 12);
                color: #f1f5f9;
                border: 1px solid rgba(255, 255, 255, 20);
                padding: 5px 10px;
                border-radius: 5px;
                font-family: 'Segoe UI';
                font-size: 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(139, 92, 246, 60);
                border-color: #a78bfa;
            }
            QPushButton#finish_btn {
                background-color: #8b5cf6;
                color: white;
                border: none;
            }
            QPushButton#finish_btn:hover {
                background-color: #7c3aed;
            }
        """)
        flayout = QVBoxLayout(frame)
        flayout.setContentsMargins(10, 6, 10, 6)
        flayout.setSpacing(6)

        # Status Label
        self.status_label = QLabel("Multi-Snip Mode  │  0 captures")
        self.status_label.setAlignment(Qt.AlignCenter)
        flayout.addWidget(self.status_label)

        # Buttons Row
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(6)

        self.btn_next = QPushButton("📸  Snip Next")
        self.btn_next.clicked.connect(self._snip_next)
        btn_layout.addWidget(self.btn_next)

        self.btn_finish = QPushButton("✔  Finish & Extract")
        self.btn_finish.setObjectName("finish_btn")
        self.btn_finish.clicked.connect(self._finish)
        self.btn_finish.setEnabled(False)
        btn_layout.addWidget(self.btn_finish)

        self.btn_cancel = QPushButton("✕")
        self.btn_cancel.setFixedWidth(26)
        self.btn_cancel.setStyleSheet("padding: 0px;")
        self.btn_cancel.clicked.connect(self._cancel)
        btn_layout.addWidget(self.btn_cancel)

        flayout.addLayout(btn_layout)
        layout.addWidget(frame)

    def showEvent(self, event):
        super().showEvent(event)
        try:
            hwnd = int(self.winId())
            if not ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x00000011):
                ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x00000001)
        except Exception:
            pass

    def add_capture(self, pixmap, rect):
        self.captures.append(pixmap)
        self.last_rect = rect
        self.status_label.setText(f"Multi-Snip Mode  │  {len(self.captures)} captures")
        self.btn_finish.setEnabled(True)
        self.show()

    def _snip_next(self):
        self.hide()
        self.sniper = ScreenSniper(controller=self, parent_overlay=self.parent_overlay)
        if self.parent_overlay:
            self.sniper.snip_completed.connect(self.parent_overlay.on_snip_completed)
        self.sniper.destroyed.connect(self._on_sniper_destroyed)
        self.sniper.setAttribute(Qt.WA_DeleteOnClose)
        self.sniper.show()

    def _on_sniper_destroyed(self):
        if not self.isVisible() and len(self.captures) > 0:
            self.show()

    def _finish(self):
        if not self.captures:
            if self.parent_overlay:
                self.parent_overlay._restore_overlay()
            self.close()
            return
        
        # Combine all captures vertically
        w = max(img.width() for img in self.captures)
        h = sum(img.height() for img in self.captures)
        
        combined = QPixmap(w, h)
        combined.fill(Qt.transparent)
        p = QPainter(combined)
        current_y = 0
        for img in self.captures:
            p.drawPixmap(0, current_y, img)
            current_y += img.height()
        p.end()

        self.snip_completed.emit(combined)
        if self.parent_overlay:
            self.parent_overlay._restore_overlay()
        self.close()

    def _cancel(self):
        if self.parent_overlay:
            self.parent_overlay._restore_overlay()
        self.close()


class ScreenSniper(QWidget):
    snip_completed = pyqtSignal(QPixmap)

    def __init__(self, controller=None, parent_overlay=None):
        super().__init__()
        self.controller = controller
        self.parent_overlay = parent_overlay
        app = QApplication.instance()
        screen = app.primaryScreen()
        self.full_screen_pixmap = screen.grabWindow(0)

        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setWindowState(Qt.WindowFullScreen)
        self.setCursor(Qt.CrossCursor)
        self.setMouseTracking(True)

        self.begin = QPoint()
        self.end = QPoint()
        self.is_drawing = False
        self.selection_rect = QRect()
        self.active_handle = None
        self.status_text = "Click and drag to select crop area"
        self.toolbar_widget = None

        if self.controller and not self.controller.last_rect.isNull():
            self.selection_rect = QRect(self.controller.last_rect)
            self.status_text = "Adjust selection edges, or add to multi-snip"
            QTimer.singleShot(50, self._show_toolbar)

    def showEvent(self, event):
        super().showEvent(event)
        try:
            hwnd = int(self.winId())
            if not ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x00000011):
                ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x00000001)
        except Exception:
            pass

    def get_drag_handle(self, pos):
        if self.selection_rect.isNull():
            return None
        rect = self.selection_rect
        margin = 10
        if abs(pos.y() - rect.top()) <= margin and rect.left() <= pos.x() <= rect.right():
            return "top"
        elif abs(pos.y() - rect.bottom()) <= margin and rect.left() <= pos.x() <= rect.right():
            return "bottom"
        elif abs(pos.x() - rect.left()) <= margin and rect.top() <= pos.y() <= rect.bottom():
            return "left"
        elif abs(pos.x() - rect.right()) <= margin and rect.top() <= pos.y() <= rect.bottom():
            return "right"
        elif rect.contains(pos):
            return "move"
        return None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.drawPixmap(0, 0, self.full_screen_pixmap)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 120))

        rect = QRect()
        if self.is_drawing:
            rect = QRect(self.begin, self.end).normalized()
        elif not self.selection_rect.isNull():
            rect = self.selection_rect

        if not rect.isNull() and rect.width() > 0 and rect.height() > 0:
            painter.drawPixmap(rect.topLeft(), self.full_screen_pixmap.copy(rect))
            painter.setPen(QPen(QColor(139, 92, 246), 2, Qt.SolidLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(rect)
            painter.setPen(QPen(QColor(167, 139, 250), 5, Qt.SolidLine))
            painter.drawLine(rect.left(), rect.top(), rect.right(), rect.top())
            painter.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())

            info = f"  {rect.width()} x {rect.height()}  "
            painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
            fm = painter.fontMetrics()
            bar_x, bar_y = rect.x(), max(0, rect.y() - fm.height() - 8)
            painter.fillRect(bar_x, bar_y, fm.width(info) + 4, fm.height() + 4, QColor(15, 23, 42, 210))
            painter.setPen(QColor(241, 245, 249))
            painter.drawText(bar_x + 2, bar_y + fm.height(), info)

        if self.status_text:
            painter.setFont(QFont("Segoe UI", 10, QFont.Bold))
            fm = painter.fontMetrics()
            sw = fm.width(self.status_text) + 24
            sx = (self.width() - sw) // 2
            sy = self.height() - 50
            painter.fillRect(sx, sy, sw, 30, QColor(15, 23, 42, 210))
            painter.setPen(QColor(167, 139, 250))
            painter.drawText(sx + 12, sy + 22, self.status_text)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if not self.selection_rect.isNull():
                h = self.get_drag_handle(event.pos())
                if h:
                    self.active_handle = h
                    self._drag_origin = event.pos()
                    self._orig_rect = QRect(self.selection_rect)
                    return
            self.begin = event.pos()
            self.end = self.begin
            self.is_drawing = True
            self.active_handle = None
            self.selection_rect = QRect()
            self.status_text = "Drag to select area"
            if self.toolbar_widget:
                self.toolbar_widget.hide()
            self.update()

    def mouseMoveEvent(self, event):
        if self.is_drawing:
            self.end = event.pos()
            self.update()
            return
        if self.active_handle and not self.selection_rect.isNull():
            delta = event.pos() - self._drag_origin
            r = QRect(self._orig_rect)
            if self.active_handle == "top":
                r.setTop(min(r.bottom() - 15, r.top() + delta.y()))
            elif self.active_handle == "bottom":
                r.setBottom(max(r.top() + 15, r.bottom() + delta.y()))
            elif self.active_handle == "left":
                r.setLeft(min(r.right() - 15, r.left() + delta.x()))
            elif self.active_handle == "right":
                r.setRight(max(r.left() + 15, r.right() + delta.x()))
            elif self.active_handle == "move":
                r.translate(delta)
            self.selection_rect = r.normalized()
            self.update()
            return
        if not self.selection_rect.isNull():
            h = self.get_drag_handle(event.pos())
            cursors = {"top": Qt.SizeVerCursor, "bottom": Qt.SizeVerCursor,
                       "left": Qt.SizeHorCursor, "right": Qt.SizeHorCursor,
                       "move": Qt.SizeAllCursor}
            self.setCursor(cursors.get(h, Qt.CrossCursor))
        else:
            self.setCursor(Qt.CrossCursor)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.is_drawing:
                self.end = event.pos()
                self.is_drawing = False
                rect = QRect(self.begin, self.end).normalized()
                if rect.width() > 20 and rect.height() > 20:
                    self.selection_rect = rect
                    self._show_toolbar()
                    self.status_text = "Adjust selection edges, then capture"
                else:
                    self.status_text = "Click and drag to select crop area"
                self.update()
            elif self.active_handle:
                self.active_handle = None
                self._show_toolbar()

    def _show_toolbar(self):
        if self.toolbar_widget:
            self.toolbar_widget.deleteLater()
            self.toolbar_widget = None

        STYLE = """
            QFrame#snipping_toolbar {
                background-color: rgba(15,23,42,235);
                border: 1px solid rgba(139,92,246,120);
                border-radius: 8px;
            }
            QPushButton {
                background: rgba(255,255,255,12);
                color: #f1f5f9;
                border: 1px solid rgba(255,255,255,20);
                padding: 6px 14px;
                border-radius: 6px;
                font: bold 11px 'Segoe UI';
            }
            QPushButton:hover { background: rgba(139,92,246,60); border-color:#a78bfa; }
            QPushButton#pri { background:#8b5cf6; color:white; border:none; }
            QPushButton#pri:hover { background:#7c3aed; }
        """

        tb = QFrame(self)
        tb.setObjectName("snipping_toolbar")
        tb.setStyleSheet(STYLE)
        layout = QHBoxLayout(tb)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)

        btn_single = QPushButton("✂  Crop Single View")
        btn_single.clicked.connect(self._accept_single)
        layout.addWidget(btn_single)

        if self.controller:
            cap_cnt = len(self.controller.captures) + 1
            btn_add = QPushButton(f"➕  Add to Multi-Snip ({cap_cnt})")
            btn_add.setObjectName("pri")
            btn_add.clicked.connect(self._accept_multi_add)
            layout.addWidget(btn_add)
        else:
            btn_start = QPushButton("➕  Start Multi-Snip")
            btn_start.setObjectName("pri")
            btn_start.clicked.connect(self._accept_multi_start)
            layout.addWidget(btn_start)

        btn_cancel = QPushButton("✕")
        btn_cancel.setFixedWidth(28)
        btn_cancel.setStyleSheet("padding: 0px;")
        btn_cancel.clicked.connect(self.close)
        layout.addWidget(btn_cancel)

        tb.adjustSize()
        rect = self.selection_rect
        x = rect.x() + (rect.width() - tb.width()) // 2
        y = rect.y() + rect.height() + 12
        x = max(10, min(x, self.width() - tb.width() - 10))
        if y + tb.height() > self.height() - 10:
            y = rect.y() - tb.height() - 12
        y = max(10, y)
        tb.move(x, y)
        tb.show()
        self.toolbar_widget = tb

    def _accept_single(self):
        r = self.selection_rect
        px = QApplication.primaryScreen().grabWindow(0, r.x(), r.y(), r.width(), r.height())
        self.snip_completed.emit(px)
        self.close()

    def _accept_multi_start(self):
        r = self.selection_rect
        px = QApplication.primaryScreen().grabWindow(0, r.x(), r.y(), r.width(), r.height())
        
        # Disconnect parent restore overlay so it stays hidden during multi-snip
        if self.parent_overlay:
            try:
                self.destroyed.disconnect(self.parent_overlay._restore_overlay)
            except Exception:
                pass
                
        self.hide()
        
        app = QApplication.instance()
        controller = MultiSnipController(parent_overlay=self.parent_overlay)
        app._multi_snip_controller = controller
        
        if self.parent_overlay:
            controller.snip_completed.connect(self.parent_overlay.on_snip_completed)
            
        controller.add_capture(px, r)
        self.close()

    def _accept_multi_add(self):
        r = self.selection_rect
        px = QApplication.primaryScreen().grabWindow(0, r.x(), r.y(), r.width(), r.height())
        self.controller.add_capture(px, r)
        self.close()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()


class TransparentOverlay(QFrame):
    hotkey_signal = pyqtSignal()
    scan_hotkey_signal = pyqtSignal()
    inject_hotkey_signal = pyqtSignal()
    send_hotkey_signal = pyqtSignal()
    focus_hotkey_signal = pyqtSignal()
    clear_hotkey_signal = pyqtSignal()
    ghost_char_signal = pyqtSignal(str)
    ghost_backspace_signal = pyqtSignal()
    ghost_enter_signal = pyqtSignal()
    ghost_typing_signal = pyqtSignal(bool)
    rotate_provider_hotkey_signal = pyqtSignal()
    theme_hotkey_signal = pyqtSignal()
    exit_hotkey_signal = pyqtSignal()
    voice_transcript_signal = pyqtSignal(str)
    voice_status_signal = pyqtSignal(str)
    inject_indexed_hotkey_signal = pyqtSignal(int)
    app_log_signal = pyqtSignal(str, str)
    focus_chat_hotkey_signal = pyqtSignal()
    
    def apply_initial_focus_styles(self):
        try:
            hwnd = int(self.winId())
            GWL_EXSTYLE = -20
            WS_EX_NOACTIVATE = 0x08000000
            WS_EX_TRANSPARENT = 0x00000020
            ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            if getattr(self, 'focus_mode', 'Background') == 'Background':
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style | WS_EX_NOACTIVATE | WS_EX_TRANSPARENT)
            else:
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style & ~WS_EX_NOACTIVATE & ~WS_EX_TRANSPARENT)
            ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020)
        except Exception:
            pass

    def __init__(self):
        super().__init__()
        app = QApplication.instance()
        app._overlay_instance = self
        
        self.hotkey_signal.connect(self.toggle_visibility_from_hotkey)
        self.scan_hotkey_signal.connect(self.scan_screen)
        self.inject_hotkey_signal.connect(self.inject_code)
        self.inject_indexed_hotkey_signal.connect(self.inject_code)
        self.send_hotkey_signal.connect(self.handle_chat)
        self.focus_chat_hotkey_signal.connect(self.focus_chat_from_hotkey)
        self.app_log_signal.connect(self.append_log)
        self.focus_hotkey_signal.connect(self.toggle_focus_mode)
        self.clear_hotkey_signal.connect(self.clear_chat)
        
        self.ghost_char_signal.connect(self.on_ghost_char)
        self.ghost_backspace_signal.connect(self.on_ghost_backspace)
        self.ghost_enter_signal.connect(self.handle_chat)
        self.ghost_typing_signal.connect(self.on_ghost_typing_toggled)
        self.rotate_provider_hotkey_signal.connect(self.rotate_provider)
        self.theme_hotkey_signal.connect(self.toggle_theme)
        self.exit_hotkey_signal.connect(self.force_exit)
        self.voice_transcript_signal.connect(self.process_voice_input)
        self.voice_status_signal.connect(self.on_voice_status)
        self.stop_listening_fn = None
        
        self.typing_timer = QTimer(self)
        self.typing_timer.timeout.connect(self.animate_typing)
        self.typing_dots = 0
        
        self.tts_worker = TTSWorker()
        self.tts_worker.speech_status_signal.connect(self.on_tts_speech_status)
        self.tts_worker.start()
        
        self.collapsed_codes = set()
        self.suppress_scroll = False
        
        settings = self.load_settings()
        self.is_dark = settings.get("is_dark", True)
        self.focus_mode = settings.get("focus_mode", "Background")
        self.dock_edge = settings.get("dock_edge", "right")
        self.opacity_val = int((settings.get("opacity", 90) / 100.0) * 255)
        self.voice_enabled = settings.get("voice_enabled", True)
            
        self.setWindowTitle("SystemResourceNotifyWindow")
        
        flags = Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool
        if self.focus_mode == 'Background':
            flags |= Qt.WindowDoesNotAcceptFocus
        self.setWindowFlags(flags)
        
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.hwnd = int(self.winId())
        self.setObjectName("overlay")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        self.is_hidden = False
        self.normal_geometry = None
        self.last_ai_code = ""
        self.last_ai_codes = []
        self.injection_in_progress = False
        self.leader_active = False
        self.sessions = []
        self.current_chat_id = None
        self.usage_counts = {"Gemini": 0, "Groq": 0, "OpenRouter": 0, "NVIDIA": 0}
        
        try:
            from dotenv import load_dotenv
            if getattr(sys, 'frozen', False):
                env_path = os.path.join(sys._MEIPASS, '.env')
                load_dotenv(env_path)
            else:
                load_dotenv()
        except ImportError:
            pass
            
        default_keys = {
            "gemini": os.environ.get("GEMINI_API_KEY", ""),
            "groq": os.environ.get("GROQ_API_KEY", ""),
            "openrouter": os.environ.get("OPENROUTER_API_KEY", ""),
            "nvidia": os.environ.get("NVIDIA_API_KEY", "")
        }
        self.api_keys = settings.get("api_keys", default_keys)
        
        # Ensure default keys are non-removable: fallback to default environmental keys if empty/missing
        if not self.api_keys.get("gemini", "").strip(): self.api_keys["gemini"] = default_keys["gemini"]
        if not self.api_keys.get("groq", "").strip(): self.api_keys["groq"] = default_keys["groq"]
        if not self.api_keys.get("openrouter", "").strip(): self.api_keys["openrouter"] = default_keys["openrouter"]
        if not self.api_keys.get("nvidia", "").strip(): self.api_keys["nvidia"] = default_keys["nvidia"]
            
        self.active_provider = settings.get("active_provider", "Gemini")
        
        default_models = {
            "gemini": "gemini-2.5-flash",
            "groq": "llama-3.3-70b-versatile",
            "openrouter": "google/gemini-2.5-flash:free",
            "nvidia": "nvidia/llama-3.1-nemotron-70b-instruct"
        }
        self.provider_models = settings.get("provider_models", default_models)
        for k, v in default_models.items():
            if k not in self.provider_models or not self.provider_models[k].strip():
                self.provider_models[k] = v
        
        default_geo = [100, 100, 900, 600]
        geo = settings.get("geometry", default_geo)
        if len(geo) == 4: self.setGeometry(geo[0], geo[1], geo[2], geo[3])
        else: self.setGeometry(*default_geo)
        
        self.cached_geometry = (self.x(), self.y(), self.width(), self.height())
            
        self.hotkey_signal.connect(self.toggle_visibility_from_hotkey)
        
        # --- TOP CONTROLS ---
        self.controls_widget = QFrame()
        self.controls_widget.setObjectName("controls")
        controls_layout = QVBoxLayout(self.controls_widget)
        controls_layout.setContentsMargins(10, 10, 10, 10)
        
        row1 = QHBoxLayout()
        self.sidebar_btn = ModernIconButton("sidebar")
        self.sidebar_btn.setObjectName("action_btn")
        self.sidebar_btn.clicked.connect(self.toggle_sidebar)
        row1.addWidget(self.sidebar_btn)

        self.drag_handle = QLabel(" ✥ Drag ")
        self.drag_handle.setCursor(Qt.SizeAllCursor)
        row1.addWidget(self.drag_handle)
        
        self.theme_btn = ModernIconButton("theme_light" if self.is_dark else "theme_dark", "Light" if self.is_dark else "Dark")
        self.theme_btn.setObjectName("action_btn")
        self.theme_btn.setToolTip("Toggle Light/Dark Theme (Hotkey: Alt+Z then T)")
        self.theme_btn.clicked.connect(self.toggle_theme)
        row1.addWidget(self.theme_btn)
        
        self.focus_btn = ModernIconButton("focus", f"Type In: {self.focus_mode}")
        self.focus_btn.setObjectName("action_btn")
        self.focus_btn.setToolTip("Toggle keyboard input focus mode (Hotkey: Alt+Z then F)")
        self.focus_btn.clicked.connect(self.toggle_focus_mode)
        row1.addWidget(self.focus_btn)
        
        opacity_percent = settings.get("opacity", 90)
        self.opacity_label = QLabel(f"Alpha: {opacity_percent}%")
        row1.addWidget(self.opacity_label)
        
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(1)
        self.slider.setMaximum(100)
        self.slider.setValue(opacity_percent)
        self.slider.setToolTip("Scroll mouse wheel here to adjust Background Transparency")
        self.slider.valueChanged.connect(self.change_opacity)
        row1.addWidget(self.slider)
        
        self.current_alpha = opacity_percent
        
        row1.addStretch()
        
        self.scrap_btn = ModernIconButton("web_scrap", "Scrap")
        self.scrap_btn.setObjectName("action_btn")
        self.scrap_btn.setToolTip("Crop screen region and extract text/code (OCR)")
        self.scrap_btn.clicked.connect(self.start_screen_scrap)
        row1.addWidget(self.scrap_btn)

        self.clear_btn = ModernIconButton("clear", "Clear")
        self.clear_btn.setObjectName("action_btn")
        self.clear_btn.setToolTip("Clear current chat history (Hotkey: Alt+Z then C)")
        self.clear_btn.clicked.connect(self.clear_chat)
        row1.addWidget(self.clear_btn)
        
        self.hide_btn = ModernIconButton("hide", "Hide")
        self.hide_btn.setObjectName("action_btn")
        self.hide_btn.setToolTip("Minimize overlay to edge (Hotkey: Alt+Z then Space or Alt+Z then H)")
        self.hide_btn.clicked.connect(self.minimize_to_edge)
        row1.addWidget(self.hide_btn)
        
        self.close_btn = ModernIconButton("close", "Exit")
        self.close_btn.setObjectName("danger_btn")
        self.close_btn.setToolTip("Exit application (Hotkey: Alt+Z then X)")
        self.close_btn.clicked.connect(self.force_exit)
        
        self.header_more_btn = ModernIconButton("more", "")
        self.header_more_btn.setToolTip("More Options")
        self.header_more_btn.clicked.connect(self.show_header_more_menu)
        self.header_more_btn.hide()
        
        row1.addWidget(self.header_more_btn)
        row1.addWidget(self.close_btn)
        
        controls_layout.addLayout(row1)
        
        layout.addWidget(self.controls_widget)
        
        # --- MAIN CONTENT LAYOUT ---
        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        
        # --- SIDEBAR ---
        self.sidebar_frame = QFrame()
        self.sidebar_frame.setObjectName("sidebar_frame")
        self.sidebar_frame.setFixedWidth(220)
        sidebar_layout = QVBoxLayout(self.sidebar_frame)
        sidebar_layout.setContentsMargins(10, 10, 10, 10)
        
        self.new_chat_btn = ModernIconButton("new_chat", "New Chat")
        self.new_chat_btn.setObjectName("new_chat_btn")
        self.new_chat_btn.clicked.connect(self.new_chat)
        sidebar_layout.addWidget(self.new_chat_btn)
        
        self.chat_list = QListWidget()
        self.chat_list.setObjectName("chat_list")
        self.chat_list.itemClicked.connect(self.on_chat_selected)
        sidebar_layout.addWidget(self.chat_list)
        
        self.clear_all_btn = ModernIconButton("clear", "Clear All History")
        self.clear_all_btn.setObjectName("danger_btn")
        self.clear_all_btn.clicked.connect(self.clear_all_chats)
        sidebar_layout.addWidget(self.clear_all_btn)
        
        self.settings_sidebar_btn = ModernIconButton("settings", "Settings")
        self.settings_sidebar_btn.setObjectName("new_chat_btn")
        self.settings_sidebar_btn.clicked.connect(self.show_settings)
        sidebar_layout.addWidget(self.settings_sidebar_btn)
        
        self.sidebar_frame.hide()
        content_layout.addWidget(self.sidebar_frame)
        
        # --- CHAT CONTAINER ---
        self.chat_container = QWidget()
        chat_container_layout = QVBoxLayout(self.chat_container)
        chat_container_layout.setContentsMargins(0, 0, 0, 0)
        
        # --- CHAT HISTORY ---
        self.chat_history = SafeTextBrowser()
        self.chat_history.setObjectName("chat_history")
        self.chat_history.setReadOnly(True) 
        self.chat_history.setViewportMargins(20, 20, 20, 10)
        self.chat_history.setOpenExternalLinks(False)
        self.chat_history.setOpenLinks(False)
        self.chat_history.anchorClicked.connect(self.on_chat_link_clicked)
        self.chat_history.setContextMenuPolicy(Qt.CustomContextMenu)
        self.chat_history.customContextMenuRequested.connect(self.show_custom_context_menu)
        self.chat_history.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.chat_history.verticalScrollBar().setToolTip("Scroll mouse wheel on the right edge to scroll chat history (Background Mode)")
        self.chat_history.verticalScrollBar().valueChanged.connect(self.on_chat_scroll_changed)
        chat_container_layout.addWidget(self.chat_history)
        self.init_settings_frame(chat_container_layout)
        
        self.typing_label = QLabel("")
        self.typing_label.setObjectName("typing_label")
        self.typing_label.setStyleSheet("color: #8b5cf6; font-weight: bold; font-family: 'Segoe UI', sans-serif; font-size: 13px; margin: 0px 15px 5px 15px;")
        self.typing_label.hide()
        chat_container_layout.addWidget(self.typing_label)
        
        # --- MODERN BOTTOM INPUT FRAME ---
        self.input_container = QWidget()
        input_container_layout = QVBoxLayout(self.input_container)
        input_container_layout.setContentsMargins(15, 0, 15, 15)
        
        self.input_frame = QFrame()
        self.input_frame.setObjectName("input_frame")
        self.input_layout = QVBoxLayout(self.input_frame)
        self.input_layout.setContentsMargins(15, 15, 15, 10)
        self.input_layout.setSpacing(10)
        
        # --- ATTACHMENT PREVIEW PANEL ---
        self.attachment_preview = QFrame()
        self.attachment_preview.setObjectName("attachment_preview")
        self.attachment_preview.setStyleSheet("""
            QFrame#attachment_preview {
                background-color: rgba(139, 92, 246, 12);
                border: 1px dashed rgba(139, 92, 246, 50);
                border-radius: 8px;
                padding: 8px;
            }
        """)
        self.attachment_preview.hide()
        
        attach_layout = QHBoxLayout(self.attachment_preview)
        attach_layout.setContentsMargins(5, 5, 5, 5)
        attach_layout.setSpacing(10)
        
        # Image thumbnail
        self.attach_thumb = QLabel()
        self.attach_thumb.setFixedSize(60, 40)
        self.attach_thumb.setStyleSheet("border-radius: 4px; border: 1px solid rgba(255, 255, 255, 20); background: #1e1b4b;")
        self.attach_thumb.setScaledContents(True)
        attach_layout.addWidget(self.attach_thumb)
        
        # Details & Status layout
        attach_details = QVBoxLayout()
        attach_details.setContentsMargins(0, 0, 0, 0)
        attach_details.setSpacing(2)
        
        self.attach_title = QLabel("Captured Snippet")
        self.attach_title.setStyleSheet("color: #f1f5f9; font-weight: bold; font-size: 11px; background: transparent; border: none;")
        
        self.attach_status = QLabel("🔍 Extracting text...")
        self.attach_status.setStyleSheet("color: #a78bfa; font-size: 10px; background: transparent; border: none;")
        
        attach_details.addWidget(self.attach_title)
        attach_details.addWidget(self.attach_status)
        attach_layout.addLayout(attach_details)
        
        attach_layout.addStretch()
        
        # Buttons layout
        self.btn_extract = QPushButton("📋 Copy Text")
        self.btn_extract.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 10);
                color: #e2e8f0;
                border: 1px solid rgba(255, 255, 255, 20);
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 20);
            }
            QPushButton:disabled {
                color: #64748b;
                background-color: rgba(255, 255, 255, 2);
            }
        """)
        self.btn_extract.setEnabled(False)
        self.btn_extract.clicked.connect(self.copy_extracted_text)
        attach_layout.addWidget(self.btn_extract)
        
        self.btn_attach = QPushButton("📎 Auto-Attach")
        self.btn_attach.setCheckable(True)
        self.btn_attach.setChecked(True)
        self.btn_attach.setStyleSheet("""
            QPushButton {
                background-color: rgba(139, 92, 246, 30);
                color: #f5f3ff;
                border: 1px solid rgba(139, 92, 246, 50);
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: rgba(139, 92, 246, 50);
            }
            QPushButton:checked {
                background-color: #8b5cf6;
                color: white;
                border-color: #8b5cf6;
            }
            QPushButton:disabled {
                color: #64748b;
                background-color: rgba(255, 255, 255, 2);
                border-color: rgba(255, 255, 255, 5);
            }
        """)
        self.btn_attach.setEnabled(False)
        self.btn_attach.hide()
        attach_layout.addWidget(self.btn_attach)
        
        # Close / Delete button
        self.btn_remove_attach = QPushButton("✕")
        self.btn_remove_attach.setFixedSize(20, 20)
        self.btn_remove_attach.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #94a3b8;
                border: none;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                color: #ef4444;
            }
        """)
        self.btn_remove_attach.clicked.connect(self.clear_attachment)
        attach_layout.addWidget(self.btn_remove_attach)
        
        self.input_layout.addWidget(self.attachment_preview)

        self.chat_input = QLineEdit()
        self.chat_input.setObjectName("chat_input")
        self.chat_input.setPlaceholderText(f"Ask {self.active_provider} anything, or /imagine...")
        self.chat_input.returnPressed.connect(self.handle_chat)
        self.chat_input.installEventFilter(self)
        self.input_layout.addWidget(self.chat_input)
        
        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(0, 0, 0, 0)
        bottom_row.setSpacing(8)
        
        self.provider_combo = QComboBox()
        self.provider_combo.setObjectName("provider_combo")
        self.provider_combo.addItems(["Gemini", "Groq", "OpenRouter", "NVIDIA", "Google Web Search"])
        self.provider_combo.setCurrentText(self.active_provider)
        self.provider_combo.setToolTip("Select active AI Provider (Hotkey: Alt+Z then P to rotate)")
        self.provider_combo.currentTextChanged.connect(self.change_provider)
        bottom_row.addWidget(self.provider_combo)
        
        bottom_row.addStretch()
        
        self.scan_btn = ModernIconButton("scan", "Scan")
        self.scan_btn.setObjectName("action_btn")
        self.scan_btn.setToolTip("Capture screen to Gemini Vision (Hotkey: Alt+Z then S)")
        self.scan_btn.clicked.connect(lambda: self.trigger_with_bg_click(self.scan_screen))
        bottom_row.addWidget(self.scan_btn)
        
        self.inject_btn = ModernIconButton("inject", "Inject")
        self.inject_btn.setObjectName("action_btn")
        self.inject_btn.setToolTip("Type generated code into active window (Hotkey: Alt+Z then I for latest | Alt+Z then 1..9 for indexed blocks)")
        self.inject_btn.clicked.connect(lambda: self.trigger_with_bg_click(self.inject_code))
        bottom_row.addWidget(self.inject_btn)
        
        self.voice_btn = ModernIconButton("voice_on" if self.voice_enabled else "voice_off", "Speaker")
        self.voice_btn.setObjectName("action_btn")
        self.voice_btn.setCheckable(True)
        self.voice_btn.setChecked(self.voice_enabled)
        self.voice_btn.setToolTip("Toggle TTS Voice Readback (Hotkey: Alt+Z then V)")
        self.voice_btn.clicked.connect(self.toggle_voice)
        bottom_row.addWidget(self.voice_btn)
        
        self.interview_btn = ModernIconButton("interview", "Live\nInterview")
        self.interview_btn.setObjectName("action_btn")
        self.interview_btn.setToolTip("Toggle Live Interview Mode (Hotkey: Alt+Z then L)")
        self.interview_btn.setCheckable(True)
        self.interview_btn.clicked.connect(self.toggle_interview_mode)
        bottom_row.addWidget(self.interview_btn)
        
        # Voice model selector — populated with system TTS voices
        self.voice_combo = QComboBox()
        self.voice_combo.setObjectName("provider_combo")
        self.voice_combo.setToolTip("Select TTS voice model (Hotkey: Alt+Z then O to rotate)")
        self.voice_combo.setMaximumWidth(120)
        # Populate voices via PowerShell (no pyttsx3 singleton risk)
        try:
            import subprocess
            ps = (
                'Add-Type -AssemblyName System.Speech; '
                '$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; '
                '$s.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name }; '
                '$s.Dispose()'
            )
            result = subprocess.run(
                ['powershell', '-WindowStyle', 'Hidden', '-NonInteractive', '-Command', ps],
                capture_output=True, text=True, timeout=10, creationflags=0x08000000
            )
            voice_names = [v.strip() for v in result.stdout.strip().splitlines() if v.strip()]
            for vn in voice_names:
                label = vn.replace('Microsoft ', '').replace(' Desktop', '').strip()
                self.voice_combo.addItem(label, userData=vn)  # userData = full SAPI name
        except Exception:
            self.voice_combo.addItem("Default", userData=None)
        self.voice_combo.currentIndexChanged.connect(self._on_voice_combo_changed)
        bottom_row.addWidget(self.voice_combo)
        
        self.single_mic_btn = ModernIconButton("single_mic", "Voice\nInput")
        self.single_mic_btn.setObjectName("action_btn")
        self.single_mic_btn.setToolTip("Single Voice Input (Types into chat box) (Hotkey: Alt+Z then U)")
        self.single_mic_btn.clicked.connect(self.start_single_voice)
        bottom_row.addWidget(self.single_mic_btn)
        
        self.mic_btn = ModernIconButton("continuous_mic", "Live\nVoice")
        self.mic_btn.setObjectName("action_btn")
        self.mic_btn.setCheckable(True)
        self.mic_btn.setToolTip("Continuous Live Voice Chat (Hotkey: Alt+Z then M)")
        self.mic_btn.clicked.connect(self.toggle_continuous_voice)
        bottom_row.addWidget(self.mic_btn)
        
        self.wave_widget = AudioWaveWidget()
        self.wave_widget.hide()
        bottom_row.addWidget(self.wave_widget)
        
        self.bottom_more_btn = ModernIconButton("more", "")
        self.bottom_more_btn.setToolTip("More Tools")
        self.bottom_more_btn.clicked.connect(self.show_bottom_more_menu)
        self.bottom_more_btn.hide()
        bottom_row.addWidget(self.bottom_more_btn)
        
        self.send_btn = ModernIconButton("send", "Send")
        self.send_btn.setObjectName("action_btn")
        self.send_btn.setToolTip("Send Message (Hotkey: Alt+Z then D)")
        self.send_btn.clicked.connect(lambda: self.trigger_with_bg_click(self.handle_chat))
        bottom_row.addWidget(self.send_btn)
        
        self.input_layout.addLayout(bottom_row)
        input_container_layout.addWidget(self.input_frame)
        chat_container_layout.addWidget(self.input_container)
        
        content_layout.addWidget(self.chat_container)
        
        layout.addLayout(content_layout)
        
        self.restore_bubble = QLabel("", self)
        self.restore_bubble.setAlignment(Qt.AlignCenter)
        self.restore_bubble.hide()
        
        self.scroll_cursor_label = QLabel("↕", self)
        self.scroll_cursor_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.scroll_cursor_label.setStyleSheet("color: #ec4899; font-size: 24px; font-weight: bold; background: transparent; padding: 0; margin: 0;")
        self.scroll_cursor_label.hide()
        
        # Sleek, modern floating downward arrow to scroll to the bottom of the chat log
        self.scroll_bottom_btn = QPushButton("↓", self.chat_container)
        self.scroll_bottom_btn.setFixedSize(30, 30)
        self.scroll_bottom_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(139, 92, 246, 180);
                color: #ffffff;
                border: 1px solid rgba(139, 92, 246, 220);
                border-radius: 15px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(139, 92, 246, 245);
            }
        """)
        self.scroll_bottom_btn.setCursor(Qt.PointingHandCursor)
        self.scroll_bottom_btn.clicked.connect(lambda: self.scroll_to_bottom(force=True))
        self.scroll_bottom_btn.hide()
        
        self.setup_global_hotkeys()
        self.setMouseTracking(True)
        
        for widget in [self.theme_btn, self.focus_btn, self.clear_btn, self.hide_btn, self.close_btn,
                       self.provider_combo, self.scan_btn, self.inject_btn, self.voice_btn,
                       self.single_mic_btn, self.mic_btn, self.send_btn, self.new_chat_btn, self.clear_all_btn]:
            widget.installEventFilter(self)
            
        self.update_style()
        self.load_chat_history()
        self.setup_global_hotkeys()
        
    def trigger_with_bg_click(self, func):
        func()
        def _click():
            hwnd = int(self.winId())
            user32 = ctypes.windll.user32
            GWL_EXSTYLE = -20
            WS_EX_TRANSPARENT = 0x00000020
            
            ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style | WS_EX_TRANSPARENT)
            
            time.sleep(0.02)
            stealth_click()
            time.sleep(0.05)
            
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style & ~WS_EX_TRANSPARENT)
            
        threading.Thread(target=_click, daemon=True).start()
        
    def log_event(self, message, level="info"):
        self.app_log_signal.emit(message, level)
        
    def append_log(self, message, level):
        if not hasattr(self, 'log_viewer'):
            return
        
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Color coding based on theme and level
        if level == "success":
            color = "#10b981" if self.is_dark else "#059669"
        elif level in ["error", "failure"]:
            color = "#ef4444" if self.is_dark else "#dc2626"
        elif level in ["warning", "misbehave"]:
            color = "#f59e0b" if self.is_dark else "#d97706"
        elif level == "performance":
            color = "#3b82f6" if self.is_dark else "#2563eb"
        else: # info
            color = "#94a3b8" if self.is_dark else "#475569"
            
        html_msg = f"<span style='color: #64748b;'>[{timestamp}]</span> <span style='color: {color}; font-weight: bold;'>[{level.upper()}]</span> <span style='color: {'#cbd5e1' if self.is_dark else '#334155'};'>{message}</span>"
        self.log_viewer.append(html_msg)
        
        scrollbar = self.log_viewer.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def get_settings_path(self):
        return os.path.join(get_app_dir(), "settings.json")
        
    def get_history_path(self):
        return os.path.join(get_app_dir(), "chat_history.json")

    def load_chat_history(self):
        self.sessions = []
        try:
            with open(self.get_history_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0 and 'id' in data[0]:
                    self.sessions = data
        except Exception:
            pass

        self._calculate_initial_usage()

        if not self.sessions:
            self.new_chat()
        else:
            self.refresh_sidebar()
            self.load_session(self.sessions[-1]['id'])

    def _calculate_initial_usage(self):
        self.usage_counts = {"Gemini": 0, "Groq": 0, "OpenRouter": 0, "NVIDIA": 0}
        try:
            for s in self.sessions:
                for m in s.get('messages', []):
                    if m.get('role') == 'ai':
                        p = m.get('provider', '')
                        if "Gemini" in p: self.usage_counts["Gemini"] += 1
                        elif "Groq" in p: self.usage_counts["Groq"] += 1
                        elif "OpenRouter" in p: self.usage_counts["OpenRouter"] += 1
                        elif "NVIDIA" in p: self.usage_counts["NVIDIA"] += 1
        except Exception:
            pass

    def refresh_sidebar(self):
        self.chat_list.clear()
        from PyQt5.QtCore import QSize
        for session in reversed(self.sessions):
            title = session.get('title', 'Untitled')
            display_text = title if title.startswith("💬") else f"💬 {title}"
            
            item = QListWidgetItem()
            item.setData(Qt.UserRole, session['id'])
            
            widget = ChatHistoryItemWidget(display_text, session['id'], self, item)
            item.setSizeHint(QSize(180, 32))
            
            self.chat_list.addItem(item)
            self.chat_list.setItemWidget(item, widget)

    def delete_session(self, session_id):
        self.sessions = [s for s in self.sessions if s['id'] != session_id]
        self.save_sessions()
        self.refresh_sidebar()
        
        if self.current_chat_id == session_id:
            if self.sessions:
                self.load_session(self.sessions[-1]['id'])
            else:
                self.new_chat()

    def new_chat(self):
        self.current_chat_id = str(uuid.uuid4())
        title = f"Chat {len(self.sessions) + 1}"
        self.sessions.append({"id": self.current_chat_id, "title": title, "messages": []})
        self.refresh_sidebar()
        self.load_session(self.current_chat_id)
        self.save_sessions()

    def load_session(self, chat_id):
        self.current_chat_id = chat_id
        self.chat_history.clear()
        self.last_ai_codes = []
        self.last_ai_code = ""
        self.code_block_counter = 0
        
        session = next((s for s in self.sessions if s['id'] == chat_id), None)
        if session:
            for msg in session['messages']:
                if msg['role'] == 'user':
                    self.add_user_message(msg['content'], save=False)
                elif msg['role'] == 'ai':
                    self.add_ai_message(msg['content'], msg.get('provider', 'System'), save=False)
                elif msg['role'] == 'system':
                    self.add_system_message(msg['content'], save=False)
        
        if not session or not session['messages']:
            self.add_system_message("Layer active on top of UI. Capture Stealth: ENABLED.", save=False)

    def render_current_session(self, streaming_text=None):
        self.chat_history.clear()
        self.last_ai_codes = []
        self.last_ai_code = ""
        self.code_block_counter = 0
        
        session = next((s for s in self.sessions if s['id'] == self.current_chat_id), None)
        if session:
            for msg in session['messages']:
                if msg['role'] == 'user':
                    self.add_user_message(msg['content'], save=False)
                elif msg['role'] == 'ai':
                    self.add_ai_message(msg['content'], msg.get('provider', 'System'), save=False)
                elif msg['role'] == 'system':
                    self.add_system_message(msg['content'], save=False)
                    
        if streaming_text:
            self.add_ai_message(streaming_text, "Stealth AI", save=False)

    def on_chat_selected(self, item):
        chat_id = item.data(Qt.UserRole)
        self.load_session(chat_id)

    def save_sessions(self):
        try:
            path = self.get_history_path()
            tmp_path = path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self.sessions, f, indent=2)
            os.replace(tmp_path, path)
        except Exception as e:
            print("Failed to save history:", e)

    def save_chat_message(self, role, content, provider="System"):
        session = next((s for s in self.sessions if s['id'] == self.current_chat_id), None)
        if not session:
            return
            
        session['messages'].append({"role": role, "content": content, "provider": provider})
        
        if role == 'ai':
            if "Gemini" in provider: self.usage_counts["Gemini"] += 1
            elif "Groq" in provider: self.usage_counts["Groq"] += 1
            elif "OpenRouter" in provider: self.usage_counts["OpenRouter"] += 1
            elif "NVIDIA" in provider: self.usage_counts["NVIDIA"] += 1
        
        if role == 'user' and session['title'].startswith('Chat '):
            title = content[:20] + "..." if len(content) > 20 else content
            session['title'] = title
            self.refresh_sidebar()
            
        self.save_sessions()

    def clear_chat(self):
        self.chat_history.clear()
        self.last_ai_codes = []
        self.last_ai_code = ""
        session = next((s for s in self.sessions if s['id'] == self.current_chat_id), None)
        if session:
            session['messages'] = []
            self.save_sessions()
        self._calculate_initial_usage()
        self.add_system_message("Chat history cleared. Layer active. Capture Stealth: ENABLED.", save=False)

    def clear_all_chats(self):
        self.sessions = []
        self.last_ai_codes = []
        self.last_ai_code = ""
        self.usage_counts = {"Gemini": 0, "Groq": 0, "OpenRouter": 0, "NVIDIA": 0}
        self.new_chat()
        self.add_system_message("All chat histories have been permanently deleted.", save=False)

    def init_settings_frame(self, parent_layout):
        self.settings_frame = QFrame()
        self.settings_frame.setObjectName("settings_frame")
        self.settings_frame.setStyleSheet("""
            QFrame#settings_frame {
                background-color: rgba(20, 20, 30, 0.95);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 12px;
            }
            QLabel {
                color: #cbd5e1;
                font-family: 'Segoe UI', sans-serif;
                font-size: 12px;
            }
            QLineEdit {
                background-color: rgba(15, 15, 25, 0.9);
                border: 1.5px solid rgba(139, 92, 246, 0.4);
                border-radius: 6px;
                color: #ffffff;
                padding: 6px 8px;
                font-size: 12px;
                font-family: 'Segoe UI', sans-serif;
            }
            QLineEdit:focus {
                border: 1.5px solid rgba(139, 92, 246, 0.9);
            }
            QComboBox {
                background-color: rgba(15, 15, 25, 0.9);
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 6px;
                color: #ffffff;
                padding: 6px;
                font-size: 12px;
            }
            QComboBox QAbstractItemView {
                background-color: #1e1e2e;
                color: #cbd5e1;
                border: 1px solid rgba(139, 92, 246, 0.5);
                selection-background-color: #6366f1;
                selection-color: #ffffff;
            }
            QPushButton {
                background-color: #6366f1;
                border: none;
                border-radius: 6px;
                color: white;
                padding: 8px 12px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #4f46e5;
            }
        """)
        self.settings_frame.hide()
        
        sf_layout = QVBoxLayout(self.settings_frame)
        sf_layout.setContentsMargins(15, 15, 15, 15)
        sf_layout.setSpacing(10)
        
        # Header
        hdr_layout = QHBoxLayout()
        hdr_lbl = QLabel("⚙️ Settings")
        hdr_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #a78bfa;")
        hdr_layout.addWidget(hdr_lbl)
        hdr_layout.addStretch()
        
        close_settings_btn = QPushButton("✕ Close")
        close_settings_btn.setStyleSheet("background-color: rgba(255, 255, 255, 0.1); color: #e2e8f0; padding: 5px 10px;")
        close_settings_btn.clicked.connect(self.hide_settings)
        hdr_layout.addWidget(close_settings_btn)
        sf_layout.addLayout(hdr_layout)
        
        # Horizontal Splitter Layout
        split_layout = QHBoxLayout()
        split_layout.setSpacing(15)
        
        # Left Sidebar Navigation
        self.settings_nav = QListWidget()
        self.settings_nav.setFixedWidth(140)
        self.settings_nav.setObjectName("settings_nav")
        self.settings_nav.setStyleSheet("""
            QListWidget#settings_nav {
                background-color: rgba(15, 15, 25, 0.5);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 8px;
            }
            QListWidget#settings_nav::item {
                color: #cbd5e1;
                padding: 8px;
                border-radius: 4px;
            }
            QListWidget#settings_nav::item:selected {
                background-color: rgba(99, 102, 241, 0.2);
                color: #a78bfa;
                font-weight: bold;
            }
        """)
        
        model_item = QListWidgetItem("🤖 Models & Keys")
        self.settings_nav.addItem(model_item)
        
        log_item = QListWidgetItem("📜 Live Logs")
        self.settings_nav.addItem(log_item)
        
        self.settings_nav.setCurrentItem(model_item)
        self.settings_nav.currentRowChanged.connect(lambda idx: self.settings_stack.setCurrentIndex(idx))
        split_layout.addWidget(self.settings_nav)
        
        # Right Stacked Widget
        self.settings_stack = QStackedWidget()
        
        # --- PAGE 1: Models & Keys ---
        models_page = QWidget()
        models_layout = QVBoxLayout(models_page)
        models_layout.setContentsMargins(0, 0, 0, 0)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")
        scroll_widget = QWidget()
        scroll_widget.setStyleSheet("background: transparent;")
        form_layout = QGridLayout(scroll_widget)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(10)
        
        # Helper to create key input row with eye and paste buttons
        def create_key_input_row(key_widget, key_name):
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(4)
            
            key_widget.setEchoMode(QLineEdit.Password)
            row_layout.addWidget(key_widget)
            
            # Eye Toggle Button
            eye_btn = QPushButton("👁️")
            eye_btn.setToolTip("Show/Hide Key")
            eye_btn.setFixedWidth(28)
            eye_btn.setStyleSheet("background-color: rgba(255, 255, 255, 0.05); padding: 4px;")
            
            def toggle_echo():
                if key_widget.echoMode() == QLineEdit.Password:
                    key_widget.setEchoMode(QLineEdit.Normal)
                    eye_btn.setText("🙈")
                else:
                    key_widget.setEchoMode(QLineEdit.Password)
                    eye_btn.setText("👁️")
            eye_btn.clicked.connect(toggle_echo)
            row_layout.addWidget(eye_btn)
            
            # Paste Button
            paste_btn = QPushButton("📋")
            paste_btn.setToolTip("Paste from Clipboard")
            paste_btn.setFixedWidth(28)
            paste_btn.setStyleSheet("background-color: rgba(255, 255, 255, 0.05); padding: 4px;")
            
            def paste_key():
                clipboard = QApplication.clipboard()
                key_widget.setText(clipboard.text().strip())
                self.save_settings()
            paste_btn.clicked.connect(paste_key)
            row_layout.addWidget(paste_btn)
            
            return row_widget

        row = 0
        
        # Gemini
        form_layout.addWidget(QLabel("<b>Gemini Key:</b>"), row, 0)
        self.key_gemini = QLineEdit()
        self.key_gemini.setText(self.api_keys.get("gemini", ""))
        self.key_gemini.textChanged.connect(self.save_settings)
        form_layout.addWidget(create_key_input_row(self.key_gemini, "gemini"), row, 1)
        
        form_layout.addWidget(QLabel("<b>Model:</b>"), row, 2)
        self.model_gemini = QComboBox()
        gemini_models = ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-1.5-flash", "gemini-1.5-pro"]
        saved_gemini = self.provider_models.get("gemini", "gemini-2.5-flash")
        if saved_gemini not in gemini_models:
            gemini_models.append(saved_gemini)
        self.model_gemini.addItems(gemini_models)
        self.model_gemini.setCurrentText(saved_gemini)
        self.model_gemini.currentTextChanged.connect(self.save_settings)
        form_layout.addWidget(self.model_gemini, row, 3)
        row += 1
        
        # Groq
        form_layout.addWidget(QLabel("<b>Groq Key:</b>"), row, 0)
        self.key_groq = QLineEdit()
        self.key_groq.setText(self.api_keys.get("groq", ""))
        self.key_groq.textChanged.connect(self.save_settings)
        form_layout.addWidget(create_key_input_row(self.key_groq, "groq"), row, 1)
        
        form_layout.addWidget(QLabel("<b>Model:</b>"), row, 2)
        self.model_groq = QComboBox()
        groq_models = ["llama-3.3-70b-versatile", "llama-3.1-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768", "gemma2-9b-it"]
        saved_groq = self.provider_models.get("groq", "llama-3.3-70b-versatile")
        if saved_groq not in groq_models:
            groq_models.append(saved_groq)
        self.model_groq.addItems(groq_models)
        self.model_groq.setCurrentText(saved_groq)
        self.model_groq.currentTextChanged.connect(self.save_settings)
        form_layout.addWidget(self.model_groq, row, 3)
        row += 1
        
        # OpenRouter
        form_layout.addWidget(QLabel("<b>OpenRouter Key:</b>"), row, 0)
        self.key_or = QLineEdit()
        self.key_or.setText(self.api_keys.get("openrouter", ""))
        self.key_or.textChanged.connect(self.save_settings)
        form_layout.addWidget(create_key_input_row(self.key_or, "openrouter"), row, 1)
        
        form_layout.addWidget(QLabel("<b>Model:</b>"), row, 2)
        self.model_or = QComboBox()
        or_models = ["google/gemini-2.5-flash:free", "meta-llama/llama-3.3-70b-instruct:free", "qwen/qwen-2.5-7b-instruct:free", "meta-llama/llama-3.2-3b-instruct:free", "microsoft/phi-3-medium-128k-instruct:free"]
        saved_or = self.provider_models.get("openrouter", "google/gemini-2.5-flash:free")
        if saved_or not in or_models:
            or_models.append(saved_or)
        self.model_or.addItems(or_models)
        self.model_or.setCurrentText(saved_or)
        self.model_or.currentTextChanged.connect(self.save_settings)
        form_layout.addWidget(self.model_or, row, 3)
        row += 1
        
        # NVIDIA
        form_layout.addWidget(QLabel("<b>NVIDIA Key:</b>"), row, 0)
        self.key_nv = QLineEdit()
        self.key_nv.setText(self.api_keys.get("nvidia", ""))
        self.key_nv.textChanged.connect(self.save_settings)
        form_layout.addWidget(create_key_input_row(self.key_nv, "nvidia"), row, 1)
        
        form_layout.addWidget(QLabel("<b>Model:</b>"), row, 2)
        self.model_nv = QComboBox()
        nvidia_models = ["nvidia/llama-3.1-nemotron-70b-instruct", "meta/llama-3.2-11b-vision-instruct", "meta/llama3-70b-instruct"]
        saved_nv = self.provider_models.get("nvidia", "nvidia/llama-3.1-nemotron-70b-instruct")
        if saved_nv not in nvidia_models:
            nvidia_models.append(saved_nv)
        self.model_nv.addItems(nvidia_models)
        self.model_nv.setCurrentText(saved_nv)
        self.model_nv.currentTextChanged.connect(self.save_settings)
        form_layout.addWidget(self.model_nv, row, 3)
        
        # Percentage of model use display
        self.usage_stats_lbl = QLabel("<b>Usage Stats:</b> Loading metrics...")
        self.usage_stats_lbl.setWordWrap(True)
        self.usage_stats_lbl.setStyleSheet("color: #a78bfa; font-size: 11px; padding: 6px; background: rgba(139, 92, 246, 0.1); border-radius: 4px; line-height: 14px;")
        models_layout.addWidget(self.usage_stats_lbl)
        
        scroll.setWidget(scroll_widget)
        models_layout.addWidget(scroll)
        
        # Bottom Buttons inside models layout
        btn_layout = QHBoxLayout()
        reset_btn = QPushButton("🔄 Reset Models")
        reset_btn.setStyleSheet("background-color: rgba(239, 68, 68, 0.2); border: 1px solid rgba(239, 68, 68, 0.4); color: #f87171; padding: 6px 12px;")
        reset_btn.clicked.connect(self.reset_to_default_models)
        btn_layout.addWidget(reset_btn)
        
        reset_keys_btn = QPushButton("🔑 Reset Keys")
        reset_keys_btn.setStyleSheet("background-color: rgba(239, 68, 68, 0.2); border: 1px solid rgba(239, 68, 68, 0.4); color: #f87171; padding: 6px 12px;")
        reset_keys_btn.clicked.connect(self.reset_to_default_keys)
        btn_layout.addWidget(reset_keys_btn)
        
        # Fetch Dynamic Active Models Button
        fetch_models_btn = QPushButton("📡 Fetch Models")
        fetch_models_btn.setStyleSheet("background-color: rgba(139, 92, 246, 0.2); border: 1px solid rgba(139, 92, 246, 0.4); color: #c084fc; padding: 6px 12px;")
        fetch_models_btn.setToolTip("Dynamically fetch online active models from your configured keys, filter non-working ones, and refresh dropdowns")
        fetch_models_btn.clicked.connect(self.fetch_active_working_models)
        btn_layout.addWidget(fetch_models_btn)
        
        btn_layout.addStretch()
        
        save_btn = QPushButton("💾 Save Config")
        save_btn.setStyleSheet("padding: 6px 12px;")
        save_btn.clicked.connect(self.hide_settings)
        btn_layout.addWidget(save_btn)
        models_layout.addLayout(btn_layout)
        
        self.settings_stack.addWidget(models_page)
        
        # --- PAGE 2: Live Logs ---
        logs_page = QWidget()
        logs_layout = QVBoxLayout(logs_page)
        logs_layout.setContentsMargins(0, 0, 0, 0)
        
        self.log_viewer = QTextEdit()
        self.log_viewer.setReadOnly(True)
        self.log_viewer.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        self.log_viewer.setStyleSheet("background-color: rgba(15, 15, 25, 0.9); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 6px; color: #cbd5e1; padding: 6px; font-family: Consolas, monospace; font-size: 11px;")
        logs_layout.addWidget(self.log_viewer)
        
        log_btn_layout = QHBoxLayout()
        clear_logs_btn = QPushButton("🗑️ Clear Logs")
        clear_logs_btn.setStyleSheet("background-color: rgba(239, 68, 68, 0.2); border: 1px solid rgba(239, 68, 68, 0.4); color: #f87171; padding: 6px 12px;")
        clear_logs_btn.clicked.connect(self.log_viewer.clear)
        log_btn_layout.addWidget(clear_logs_btn)
        
        copy_logs_btn = QPushButton("📋 Copy All")
        copy_logs_btn.setStyleSheet("background-color: rgba(99, 102, 241, 0.2); border: 1px solid rgba(99, 102, 241, 0.4); color: #818cf8; padding: 6px 12px;")
        copy_logs_btn.clicked.connect(lambda: QApplication.clipboard().setText(self.log_viewer.toPlainText()))
        log_btn_layout.addWidget(copy_logs_btn)
        
        log_btn_layout.addStretch()
        logs_layout.addLayout(log_btn_layout)
        
        self.settings_stack.addWidget(logs_page)
        
        split_layout.addWidget(self.settings_stack)
        
        sf_layout.addLayout(split_layout)
        parent_layout.addWidget(self.settings_frame)

    def calculate_usage_statistics(self):
        """Calculate and update API usage metrics, remaining quotas, and reset times from message logs."""
        try:
            import datetime
            now = datetime.datetime.now()
            
            # Find time remaining until midnight local time when quotas reset
            tomorrow = datetime.datetime(now.year, now.month, now.day) + datetime.timedelta(days=1)
            time_until_reset = tomorrow - now
            hours, remainder = divmod(time_until_reset.seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            reset_str = f"{hours}h {minutes}m"
            
            # All providers reset at 00:00 UTC. Let's calculate remaining time until 00:00 UTC.
            now_utc = datetime.datetime.utcnow()
            tomorrow_utc = datetime.datetime(now_utc.year, now_utc.month, now_utc.day) + datetime.timedelta(days=1)
            time_until_utc_reset = tomorrow_utc - now_utc
            utc_hours, remainder_utc = divmod(time_until_utc_reset.seconds, 3600)
            utc_minutes, _ = divmod(remainder_utc, 60)
            utc_reset_str = f"{utc_hours}h {utc_minutes}m (UTC)"

            limits = {"Gemini": 1500, "Groq": 14400, "OpenRouter": 200, "NVIDIA": 1000}
            
            stats = []
            for p in ["Gemini", "Groq", "OpenRouter", "NVIDIA"]:
                used = self.usage_counts.get(p, 0)
                limit = limits[p]
                remaining = max(0, limit - used)
                # Show quota remaining and its specific API provider reset time
                stats.append(f"• <b>{p}:</b> {remaining}/{limit} Left &nbsp;(Resets in {utc_reset_str})")
                
            self.usage_stats_lbl.setText(
                f"<b>📊 Daily Quota Status:</b><br>" + 
                "<br>".join(stats)
            )
        except Exception as e:
            self.usage_stats_lbl.setText(f"<b>📊 Quota Status:</b> Error loading metrics ({e})")

    def fetch_active_working_models(self):
        """Query each provider API dynamically to fetch active working models and update comboboxes."""
        self.usage_stats_lbl.setText("🔄 Fetching online active models dynamically from API endpoints...")
        QApplication.processEvents()
        
        import urllib.request
        import json
        
        # 1. OpenRouter Free Models Fetch
        or_key = self.key_or.text().strip() or os.environ.get("OPENROUTER_API_KEY", "")
        if or_key:
            try:
                req = urllib.request.Request(
                    "https://openrouter.ai/api/v1/models",
                    headers={"Authorization": f"Bearer {or_key}", "User-Agent": "Mozilla/5.0"}
                )
                with urllib.request.urlopen(req, timeout=5) as response:
                    data = json.loads(response.read())
                    working_or = []
                    for m in data.get('data', []):
                        pricing = m.get('pricing', {})
                        # Filter only verified working and free models
                        if float(pricing.get('prompt', 0)) == 0.0 and m.get('id', '').endswith(':free'):
                            working_or.append(m['id'])
                    
                    if working_or:
                        current = self.model_or.currentText()
                        self.model_or.clear()
                        self.model_or.addItems(working_or)
                        if current in working_or:
                            self.model_or.setCurrentText(current)
                        else:
                            self.model_or.setCurrentIndex(0)
            except Exception as e:
                self.log_event(f"OpenRouter models fetch failed: {e}", "warning")

        # 2. Groq Models Fetch
        groq_key = self.key_groq.text().strip() or os.environ.get("GROQ_API_KEY", "")
        if groq_key:
            try:
                req = urllib.request.Request(
                    "https://api.groq.com/openai/v1/models",
                    headers={"Authorization": f"Bearer {groq_key}", "User-Agent": "Mozilla/5.0"}
                )
                with urllib.request.urlopen(req, timeout=5) as response:
                    data = json.loads(response.read())
                    working_groq = [m['id'] for m in data.get('data', []) if "whisper" not in m['id'].lower() and "guard" not in m['id'].lower()]
                    if working_groq:
                        current = self.model_groq.currentText()
                        self.model_groq.clear()
                        self.model_groq.addItems(working_groq)
                        if current in working_groq:
                            self.model_groq.setCurrentText(current)
                        else:
                            self.model_groq.setCurrentIndex(0)
            except Exception as e:
                self.log_event(f"Groq models fetch failed: {e}", "warning")

        # 3. NVIDIA Models Fetch
        nv_key = self.key_nv.text().strip() or os.environ.get("NVIDIA_API_KEY", "")
        if nv_key:
            try:
                req = urllib.request.Request(
                    "https://integrate.api.nvidia.com/v1/models",
                    headers={"Authorization": f"Bearer {nv_key}", "User-Agent": "Mozilla/5.0"}
                )
                with urllib.request.urlopen(req, timeout=5) as response:
                    data = json.loads(response.read())
                    # Filter models to keep general chat models and vision models that are currently active
                    working_nv = [m['id'] for m in data.get('data', []) if "/" in m['id']]
                    if working_nv:
                        current = self.model_nv.currentText()
                        self.model_nv.clear()
                        self.model_nv.addItems(working_nv)
                        if current in working_nv:
                            self.model_nv.setCurrentText(current)
                        else:
                            self.model_nv.setCurrentIndex(0)
            except Exception as e:
                self.log_event(f"NVIDIA models fetch failed: {e}", "warning")

        self.calculate_usage_statistics()
        self.save_settings()
        QMessageBox.information(self, "Models Updated", "Available working models refreshed dynamically from API providers.")

    def show_settings(self):
        self.log_event("Settings opened.", "info")
        self.chat_history.hide()
        self.input_container.hide()
        self.settings_frame.show()
        # Calculate stats asynchronously in the background so the GUI opens instantly
        QTimer.singleShot(50, self.calculate_usage_statistics)
        
    def hide_settings(self):
        self.log_event("Settings closed.", "info")
        self.settings_frame.hide()
        self.chat_history.show()
        self.input_container.show()
        if self.focus_mode == 'Background':
            hwnd = int(self.winId())
            GWL_EXSTYLE = -20
            WS_EX_NOACTIVATE = 0x08000000
            WS_EX_TRANSPARENT = 0x00000020
            ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style | WS_EX_NOACTIVATE | WS_EX_TRANSPARENT)
        
    def reset_to_default_models(self):
        self.model_gemini.setCurrentText("gemini-2.5-flash")
        self.model_groq.setCurrentText("llama-3.3-70b-versatile")
        self.model_or.setCurrentText("google/gemini-2.5-flash:free")
        self.model_nv.setCurrentText("nvidia/llama-3.1-nemotron-70b-instruct")
        self.save_settings()
        QMessageBox.information(self, "Models Reset", "Models reset to defaults and saved.")
        
    def reset_to_default_keys(self):
        self.key_gemini.setText(os.environ.get("GEMINI_API_KEY", ""))
        self.key_groq.setText(os.environ.get("GROQ_API_KEY", ""))
        self.key_or.setText(os.environ.get("OPENROUTER_API_KEY", ""))
        self.key_nv.setText(os.environ.get("NVIDIA_API_KEY", ""))
        self.save_settings()
        QMessageBox.information(self, "Keys Reset", "API Keys overridden with default keys and saved.")


    def toggle_sidebar(self):
        if self.sidebar_frame.isVisible():
            self.sidebar_frame.hide()
        else:
            self.sidebar_frame.show()

    def load_settings(self):
        try:
            with open(self.get_settings_path(), "r") as f: return json.load(f)
        except Exception: return {}

    def save_settings(self):
        if self.is_hidden and self.normal_geometry:
            geo = [self.normal_geometry.x(), self.normal_geometry.y(), self.normal_geometry.width(), self.normal_geometry.height()]
        else:
            geo = [self.x(), self.y(), self.width(), self.height()]
            
        # Read from key fields if they are initialized, otherwise preserve existing
        if hasattr(self, 'key_gemini'):
            self.api_keys = {
                "gemini": self.key_gemini.text().strip(),
                "groq": self.key_groq.text().strip(),
                "openrouter": self.key_or.text().strip(),
                "nvidia": self.key_nv.text().strip()
            }
        
        if hasattr(self, 'model_gemini'):
            self.provider_models = {
                "gemini": self.model_gemini.currentText().strip(),
                "groq": self.model_groq.currentText().strip(),
                "openrouter": self.model_or.currentText().strip(),
                "nvidia": self.model_nv.currentText().strip()
            }
            
        settings = {
            "is_dark": self.is_dark,
            "opacity": getattr(self, 'current_alpha', 90),
            "focus_mode": self.focus_mode,
            "geometry": geo,
            "dock_edge": self.dock_edge,
            "active_provider": self.active_provider,
            "api_keys": self.api_keys,
            "provider_models": self.provider_models,
            "voice_enabled": self.voice_enabled
        }
        try:
            with open(self.get_settings_path(), "w") as f: json.dump(settings, f)
        except Exception as e: print("Failed to save settings:", e)
        
    def toggle_voice(self):
        self.voice_enabled = not self.voice_enabled
        self.voice_btn.setChecked(self.voice_enabled)
        self.voice_btn.icon_type = "voice_on" if self.voice_enabled else "voice_off"
        self.voice_btn.update()
        self.save_settings()
        if not self.voice_enabled:
            self.tts_worker.stop_speech()
            
    def _on_voice_combo_changed(self, idx):
        voice_name = self.voice_combo.itemData(idx)
        self.tts_worker.set_voice(voice_name)
        
    def rotate_voice(self):
        """Cycle to next TTS voice and speak a sample line."""
        if not hasattr(self, 'voice_combo') or self.voice_combo.count() == 0:
            return
        curr = self.voice_combo.currentIndex()
        nxt = (curr + 1) % self.voice_combo.count()
        self.voice_combo.setCurrentIndex(nxt)
        voice_name = self.voice_combo.itemData(nxt)
        self.add_system_message(f"🔊 Voice: <b>{self.voice_combo.itemText(nxt)}</b>")
        if self.voice_enabled:
            self.tts_worker.speak(f"Hi, I'm {self.voice_combo.itemText(nxt)}. Ready to assist you.")

    def change_provider(self, text):
        self.active_provider = text
        self.chat_input.setPlaceholderText(f"Ask {self.active_provider}... (Alt+Z then K: Type | P: Model | S: Scan | I: Inject | Space/H: Hide | U: Voice Typist | M: Live Chat | V: Speaker)")
        self.save_settings()
        
    def rotate_provider(self):
        curr_idx = self.provider_combo.currentIndex()
        next_idx = (curr_idx + 1) % self.provider_combo.count()
        self.provider_combo.setCurrentIndex(next_idx)

    def add_user_message(self, text, save=True):
        import html as html_lib
        import datetime
        formatted_text = html_lib.escape(text).replace('\n', '<br>')
        
        # Muted timestamp formatted to Weekday, Month Day, Year, HH:MM AM/PM
        now = datetime.datetime.now()
        date_time_str = now.strftime("%A, %b %d, %Y, %I:%M %p")
        if " 0" in date_time_str:
            date_time_str = date_time_str.replace(" 0", " ")
        parts_dt = date_time_str.split(", ")
        if len(parts_dt) > 3:
            time_part = parts_dt[3]
            if time_part.startswith("0"):
                time_part = time_part[1:]
            date_time_str = f"{parts_dt[0]}, {parts_dt[1]}, {parts_dt[2]}, {time_part}"
            
        alpha = getattr(self, 'current_alpha', 90) / 100.0
            
        if self.is_dark:
            user_bg = f"rgba(24, 24, 27, {alpha})"  # zinc-900 with alpha
            text_color = "#e2e8f0"
            border_color = f"rgba(39, 39, 42, {alpha})"
            prefix_color = "#818cf8"
        else:
            user_bg = f"rgba(255, 255, 255, {alpha})"  # white with alpha
            text_color = "#1f2937"
            border_color = f"rgba(229, 229, 235, {alpha})"
            prefix_color = "#4f46e5"
            
        html = f"""
        <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom: 15px;">
            <tr>
                <td align="left">
                    <table width="95%" style="background-color: {user_bg}; border: 1px solid {border_color};" cellpadding="0" cellspacing="0">
                        <tr>
                            <td bgcolor="{prefix_color}" width="4" style="font-size: 1px;">&nbsp;</td>
                            <td style="font-family: 'Segoe UI', sans-serif; font-size: 14px; color: {text_color}; padding: 12px 18px; line-height: 1.5;">
                                <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom: 6px;">
                                    <tr>
                                        <td align="left" style="font-family: 'Segoe UI', sans-serif; font-weight: bold; font-size: 11px; color: {prefix_color}; text-transform: uppercase; letter-spacing: 0.5px;">
                                            👤 YOU
                                        </td>
                                        <td align="right" style="font-family: 'Segoe UI', sans-serif; font-size: 10px; color: #71717a; font-weight: normal; padding-left: 20px;">
                                            {date_time_str}
                                        </td>
                                    </tr>
                                </table>
                                {formatted_text}
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
        """
        self.chat_history.append(html)
        if save:
            self.save_chat_message("user", text)
        self.scroll_to_bottom(force=True)

    def on_chat_scroll_changed(self, value):
        """Show/hide the floating scroll-to-bottom button based on scroll position."""
        if getattr(self, 'suppress_scroll', False):
            return
        scrollbar = self.chat_history.verticalScrollBar()
        at_bottom = value >= scrollbar.maximum() - 80
        if hasattr(self, 'scroll_bottom_btn'):
            if at_bottom:
                self.scroll_bottom_btn.hide()
            else:
                # Position at bottom-center of chat_container, just above the input box
                try:
                    container = self.chat_container
                    input_h = self.input_container.height() if hasattr(self, 'input_container') else 115
                    bx = (container.width() - self.scroll_bottom_btn.width()) // 2
                    by = container.height() - input_h - self.scroll_bottom_btn.height() - 8
                    self.scroll_bottom_btn.move(bx, by)
                    self.scroll_bottom_btn.raise_()
                except Exception:
                    pass
                self.scroll_bottom_btn.show()

    def scroll_to_bottom(self, force=False):
        if getattr(self, 'suppress_scroll', False):
            return
        scrollbar = self.chat_history.verticalScrollBar()
        # If force is True, or the user is already near the bottom (within 80px), perform auto-scroll
        if force or (scrollbar.value() >= scrollbar.maximum() - 80):
            QApplication.processEvents()
            scrollbar.setValue(scrollbar.maximum())
            if hasattr(self, 'scroll_bottom_btn'):
                self.scroll_bottom_btn.hide()
        else:
            # If the user is scrolled up and a message arrives, show the floating scroll down button
            if hasattr(self, 'scroll_bottom_btn'):
                self.scroll_bottom_btn.show()

    def on_chat_link_clicked(self, url):
        url_str = url.toString()
        if url_str.startswith("inject:"):
            idx_str = url_str.replace("inject:", "")
            try:
                idx = int(idx_str)
                self.inject_code(idx + 1)
            except Exception as e:
                self.add_system_message(f"Injection failed: {e}")
        elif url_str.startswith("copy:"):
            idx_str = url_str.replace("copy:", "")
            try:
                idx = int(idx_str)
                code = self.last_ai_codes[idx]
                QApplication.clipboard().setText(code)
                self.add_system_message("📋 Code copied to clipboard.")
            except Exception as e:
                self.add_system_message(f"Copy failed: {e}")
        elif url_str.startswith("collapse:"):
            cb_id = url_str.replace("collapse:", "")
            if not hasattr(self, 'collapsed_codes'):
                self.collapsed_codes = set()
            if cb_id in self.collapsed_codes:
                self.collapsed_codes.remove(cb_id)
            else:
                self.collapsed_codes.add(cb_id)
                
            scrollbar = self.chat_history.verticalScrollBar()
            scroll_pos = scrollbar.value()
            self.suppress_scroll = True
            self.load_session(self.current_chat_id)
            self.suppress_scroll = False
            QApplication.processEvents()
            scrollbar.setValue(scroll_pos)
            
    def show_custom_context_menu(self, pos):
        menu = QMenu(self)
        # Apply dark styling to match premium aesthetics
        menu.setStyleSheet("""
            QMenu {
                background-color: #1e1b29;
                color: #e5e7eb;
                border: 1px solid #8b5cf6;
                border-radius: 8px;
                padding: 4px 0px;
            }
            QMenu::item {
                padding: 6px 20px;
                font-family: "Segoe UI", sans-serif;
                font-size: 11px;
            }
            QMenu::item:selected {
                background-color: rgba(139, 92, 246, 40);
                color: #ffffff;
            }
            QMenu::item:disabled {
                color: #6b7280;
            }
        """)
        copy_action = menu.addAction("📋 Copy Selection")
        select_all_action = menu.addAction("🔍 Select All")
        
        # Only enable copy if text selection exists
        if not self.chat_history.textCursor().hasSelection():
            copy_action.setEnabled(False)
            
        action = menu.exec_(self.chat_history.mapToGlobal(pos))
        if action == copy_action:
            text = self.chat_history.textCursor().selectedText().replace('\u2029', '\n')
            QApplication.clipboard().setText(text)
        elif action == select_all_action:
            self.chat_history.selectAll()

    def add_ai_message(self, text, provider_name="System", save=True):
        import html as html_lib
        import base64
        import datetime
        
        now = datetime.datetime.now()
        date_time_str = now.strftime("%A, %b %d, %Y, %I:%M %p")
        if " 0" in date_time_str:
            date_time_str = date_time_str.replace(" 0", " ")
        parts_dt = date_time_str.split(", ")
        if len(parts_dt) > 3:
            time_part = parts_dt[3]
            if time_part.startswith("0"):
                time_part = time_part[1:]
            date_time_str = f"{parts_dt[0]}, {parts_dt[1]}, {parts_dt[2]}, {time_part}"
        
        alpha = getattr(self, 'current_alpha', 90) / 100.0
        
        code_bg = f"rgba(9, 9, 11, {alpha})" if self.is_dark else f"rgba(249, 250, 251, {alpha})"
        code_border = f"border: 1px solid rgba(39, 39, 42, {alpha});" if self.is_dark else f"border: 1px solid rgba(229, 229, 235, {alpha});"
        code_color = "#f4f4f5" if self.is_dark else "#1f2937"
        
        parts = text.split("```")
        formatted_parts = []
        for i, part in enumerate(parts):
            if i % 2 == 1:
                lines = part.split('\n', 1)
                lang = lines[0] if len(lines) > 1 else ""
                code = lines[1] if len(lines) > 1 else lines[0]
                
                clean_code = code.strip()
                self.last_ai_codes.append(clean_code)
                self.last_ai_code = clean_code
                code_index = len(self.last_ai_codes) - 1
                
                # Retrieve collapse status
                cb_id = f"cb_{getattr(self, 'code_block_counter', 0)}"
                self.code_block_counter = getattr(self, 'code_block_counter', 0) + 1
                
                is_collapsed = cb_id in getattr(self, 'collapsed_codes', set())
                
                chevron_char = "Collapse code snippet" if not is_collapsed else "Expand code snippet"
                chevron_icon = "▲" if not is_collapsed else "▼"
                
                header_bg = f"rgba(31, 41, 55, {alpha})" if self.is_dark else f"rgba(243, 244, 246, {alpha})"
                header_text = "#e2e8f0" if self.is_dark else "#1f2937"
                body_bg = f"rgba(13, 17, 23, {alpha})" if self.is_dark else f"rgba(255, 255, 255, {alpha})"
                body_border = f"border: 1px solid rgba(48, 54, 61, {alpha});" if self.is_dark else f"border: 1px solid rgba(229, 229, 235, {alpha});"
                divider_color = f"rgba(48, 54, 61, {alpha})" if self.is_dark else f"rgba(229, 229, 235, {alpha})"
                
                lang_display = lang.strip().capitalize() if lang.strip() else "Code"
                
                html_code = f"""
                <table width="100%" style="background-color: {body_bg}; {body_border} margin: 10px 0; border-radius: 8px;" cellpadding="0" cellspacing="0">
                    <!-- Header -->
                    <tr style="background-color: {header_bg};">
                        <td style="padding: 8px 12px; font-family: 'Segoe UI', sans-serif; font-size: 13px; color: {header_text};">
                            <span style="font-weight: bold; color: {header_text};">{lang_display}</span> &nbsp;
                            <a href="collapse:{cb_id}" style="color: #8b5cf6; text-decoration: none; font-weight: bold; font-size: 12px;" title="{chevron_char}">{chevron_icon}</a>
                        </td>
                        <td align="right" style="padding: 8px 12px; font-family: 'Segoe UI', sans-serif; font-size: 13px;">
                            <a href="copy:{code_index}" style="color: #58a6ff; text-decoration: none; font-weight: bold; margin-right: 15px;">📋 Copy</a>
                            <a href="inject:{code_index}" style="color: #a5d6ff; text-decoration: none; font-weight: bold;">⚡ Inject {code_index + 1}</a>
                        </td>
                    </tr>
                    <!-- Divider line -->
                    <tr>
                        <td colspan="2" height="1" style="background-color: {divider_color}; font-size: 1px;">&nbsp;</td>
                    </tr>
                """
                if not is_collapsed:
                    highlighted_code = self.highlight_code(clean_code, lang, self.is_dark)
                    html_code += f"""
                    <!-- Code Body -->
                    <tr>
                        <td colspan="2" style="padding: 12px; font-family: Consolas, monospace; font-size: 13px; color: {code_color};">
                            <pre style="margin: 0; white-space: pre-wrap;">{highlighted_code}</pre>
                        </td>
                    </tr>
                    """
                else:
                    html_code += f"""
                    <!-- Collapsed message placeholder -->
                    <tr>
                        <td colspan="2" style="padding: 8px 12px; font-family: 'Segoe UI', sans-serif; font-size: 12px; color: #888; font-style: italic;">
                            Code block collapsed. Click chevron to expand.
                        </td>
                    </tr>
                    """
                html_code += "</table>"
                formatted_parts.append(html_code)
            else:
                escaped_part = html_lib.escape(part).replace('\n', '<br>')
                import re
                escaped_part = re.sub(r"\[IMAGE:\s*(file:///[^\]]+)\]", r"<img src='\1' width='400' style='border-radius: 10px; margin-top: 10px;'/>", escaped_part)
                formatted_parts.append(escaped_part)
                
        formatted_text = "".join(formatted_parts)
        
        # Color coding by AI provider
        provider_colors = {
            "gemini": "#10b981",       # Emerald Green
            "groq": "#f97316",         # Orange
            "openrouter": "#a855f7",   # Purple
            "google web search": "#3b82f6", # Blue
            "system": "#6b7280"        # Gray
        }
        
        p_key = provider_name.lower().strip()
        provider_color = provider_colors.get(p_key, "#8b5cf6") # Default purple
        
        if "gemini" in p_key:
            icon = "✨"
        elif "groq" in p_key:
            icon = "⚡"
        elif "openrouter" in p_key:
            icon = "🔮"
        elif "search" in p_key:
            icon = "🌐"
        else:
            icon = "🤖"
            
        if self.is_dark:
            ai_bg = f"rgba(24, 24, 27, {alpha})"  # zinc-900 with alpha
            text_color = "#e4e4e7"
            border_color = f"rgba(39, 39, 42, {alpha})"
        else:
            ai_bg = f"rgba(255, 255, 255, {alpha})"  # white with alpha
            text_color = "#1f2937"
            border_color = f"rgba(229, 229, 235, {alpha})"
            
        html = f"""
        <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom: 20px;">
            <tr>
                <td align="left">
                    <table width="95%" style="background-color: {ai_bg}; border: 1px solid {border_color};" cellpadding="0" cellspacing="0">
                        <tr>
                            <td bgcolor="{provider_color}" width="4" style="font-size: 1px;">&nbsp;</td>
                            <td style="font-family: 'Segoe UI', sans-serif; font-size: 14px; color: {text_color}; padding: 12px 18px; line-height: 1.5;">
                                <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom: 6px;">
                                    <tr>
                                        <td align="left" style="font-family: 'Segoe UI', sans-serif; font-weight: bold; font-size: 11px; color: {provider_color}; text-transform: uppercase; letter-spacing: 0.5px;">
                                            {icon} {provider_name}
                                        </td>
                                        <td align="right" style="font-family: 'Segoe UI', sans-serif; font-size: 10px; color: #71717a; font-weight: normal; padding-left: 20px;">
                                            {date_time_str}
                                        </td>
                                    </tr>
                                </table>
                                {formatted_text}
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
        """
        self.chat_history.append(html)
        if save:
            self.save_chat_message("ai", text, provider_name)
        self.scroll_to_bottom(force=True)

    def add_system_message(self, text, save=True):
        text_lower = text.lower()
        import datetime
        
        now = datetime.datetime.now()
        date_time_str = now.strftime("%A, %b %d, %Y, %I:%M %p")
        if " 0" in date_time_str:
            date_time_str = date_time_str.replace(" 0", " ")
        parts_dt = date_time_str.split(", ")
        if len(parts_dt) > 3:
            time_part = parts_dt[3]
            if time_part.startswith("0"):
                time_part = time_part[1:]
            date_time_str = f"{parts_dt[0]}, {parts_dt[1]}, {parts_dt[2]}, {time_part}"
        
        # Determine warning / success (stealth) / info category
        is_warn = "warning" in text_lower or "error" in text_lower or "failed" in text_lower
        is_stealth = "stealth mode" in text_lower or "ghost typing active" in text_lower or "enabled" in text_lower or "activated" in text_lower or "un-focusable" in text_lower
        is_info = "ghost typing inactive" in text_lower or "disabled" in text_lower or "deactivated" in text_lower or "cancelled" in text_lower or "cleared" in text_lower
        
        # Prevent "warnings" inside stealth mode from triggering a red box
        if "stealth mode" in text_lower and "warnings" in text_lower:
            is_warn = False
            is_stealth = True
            
        if is_warn:
            color = "#ef4444" if self.is_dark else "#b91c1c"
        elif is_stealth:
            color = "#10b981" if self.is_dark else "#047857"
        elif is_info:
            color = "#3b82f6" if self.is_dark else "#1d4ed8"
        else:
            color = "#71717a"
            
        html = f"""
        <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom: 10px;">
            <tr>
                <td align="center" style="font-family: 'Segoe UI', sans-serif; font-size: 11px; color: {color};">
                    <i>{text}</i>
                </td>
                <td width="120" align="right" style="font-family: 'Segoe UI', sans-serif; font-size: 9px; color: #71717a; padding-left: 10px;">
                    {date_time_str}
                </td>
            </tr>
        </table>
        """
            
        self.chat_history.append(html)
        if save:
            self.save_chat_message("system", text)
        self.scroll_to_bottom(force=False)
        
    def highlight_code(self, code_text, lang_name, is_dark):
        try:
            from pygments import highlight
            from pygments.lexers import get_lexer_by_name, guess_lexer
            from pygments.formatters import HtmlFormatter
            
            style_name = "monokai" if is_dark else "friendly"
            
            lang = lang_name.strip().lower() if lang_name else ""
            lang_map = {
                "py": "python", "python3": "python",
                "js": "javascript", "ts": "typescript",
                "html5": "html", "css3": "css",
                "sh": "bash", "shell": "bash",
                "cpp": "c++", "c": "c",
                "json": "json"
            }
            if lang in lang_map:
                lang = lang_map[lang]
                
            try:
                if lang:
                    lexer = get_lexer_by_name(lang)
                else:
                    lexer = guess_lexer(code_text)
            except Exception:
                from pygments.lexers.special import TextLexer
                lexer = TextLexer()
                
            formatter = HtmlFormatter(nowrap=True, noclasses=True, style=style_name)
            return highlight(code_text, lexer, formatter)
        except Exception:
            import html as html_lib
            return html_lib.escape(code_text)
            
    def toggle_continuous_voice(self):
        if self.mic_btn.isChecked():
            self.chat_input.setPlaceholderText("Calibrating mic...")
            self.mic_btn.setEnabled(False)
            self.voice_setup_worker = VoiceSetupWorker()
            self.voice_setup_worker.setup_done.connect(self.on_voice_setup_done)
            self.voice_setup_worker.error_signal.connect(self.on_voice_setup_error)
            self.voice_setup_worker.start()
        else:
            self.stop_continuous_voice()

    def on_voice_setup_done(self, recognizer, microphone):
        self.mic_btn.setEnabled(True)
        self.recognizer = recognizer
        self.microphone = microphone
        
        def callback(recognizer, audio):
            try:
                text = recognizer.recognize_google(audio)
                self.voice_transcript_signal.emit(text)
            except Exception:
                pass
                
        try:
            self.stop_listening_fn = self.recognizer.listen_in_background(self.microphone, callback, phrase_time_limit=12)
            self.chat_input.setPlaceholderText("[🎙️ Continuous Voice Chat Active... Speak naturally]")
            self.mic_btn.setStyleSheet("background-color: rgba(76, 175, 80, 100); border: 1.5px solid #4CAF50;")
            self.wave_widget.set_active(True, mode="listening")
            self.add_system_message("🎙️ Continuous Voice Command Center activated. Speak controls or questions.")
        except Exception as e:
            self.on_voice_setup_error(str(e))

    def on_voice_setup_error(self, err):
        self.mic_btn.setEnabled(True)
        self.mic_btn.setChecked(False)
        self.mic_btn.setStyleSheet("")
        self.wave_widget.set_active(False)
        self.chat_input.setPlaceholderText(f"Ask {self.active_provider} anything, or /imagine...")
        self.add_system_message(f"<b style='color:red;'>Voice Center Setup Failed:</b> {err}")

    def stop_continuous_voice(self):
        if getattr(self, 'stop_listening_fn', None):
            try:
                self.stop_listening_fn(wait_for_stop=False)
            except Exception:
                pass
            self.stop_listening_fn = None
        self.mic_btn.setStyleSheet("")
        self.wave_widget.set_active(False)
        self.chat_input.setPlaceholderText(f"Ask {self.active_provider} anything, or /imagine...")
        self.add_system_message("🎙️ Continuous Voice Command Center deactivated.")

    def start_single_voice(self):
        if getattr(self, 'dictation_running', False):
            try: self.dictation_worker.terminate()
            except: pass
            self.on_single_voice_error("Recording cancelled.")
            return
            
        self.dictation_running = True
        self.single_mic_btn.setStyleSheet("background-color: rgba(236, 72, 153, 100); border: 1.5px solid #ec4899;")
        self.wave_widget.set_active(True, mode="listening")
        
        self.dictation_worker = DictationWorker()
        self.dictation_worker.finished_signal.connect(self.on_single_voice_finished)
        self.dictation_worker.error_signal.connect(self.on_single_voice_error)
        self.dictation_worker.status_signal.connect(self.on_single_voice_status)
        self.dictation_worker.start()
        
    def on_single_voice_finished(self, text):
        self.dictation_running = False
        self.single_mic_btn.setStyleSheet("")
        self.wave_widget.set_active(False)
        self.chat_input.setPlaceholderText(f"Ask {self.active_provider} anything, or /imagine...")
        
        if text.strip():
            current_text = self.chat_input.text()
            spacer = " " if current_text and not current_text.endswith(" ") else ""
            self.chat_input.setText(current_text + spacer + text.strip())
            self.chat_input.setFocus()
            
    def on_single_voice_error(self, err):
        self.dictation_running = False
        self.single_mic_btn.setStyleSheet("")
        self.wave_widget.set_active(False)
        self.chat_input.setPlaceholderText(f"Ask {self.active_provider} anything, or /imagine...")
        if "cancelled" not in err.lower():
            self.add_system_message(f"<b style='color:red;'>Voice Input Error:</b> {err}")
            
    def on_single_voice_status(self, status):
        self.chat_input.setPlaceholderText(f"[🎙️ {status}]")
        
    def on_tts_speech_status(self, speaking):
        if getattr(self, 'stop_listening_fn', None): # Continuous mode is active
            if speaking:
                self.wave_widget.set_active(True, mode="speaking")
            else:
                self.wave_widget.set_active(True, mode="listening")
                
        if getattr(self, 'interview_mode', False):
            if speaking:
                self.wave_widget.set_active(True, mode="speaking")
            else:
                self.wave_widget.set_active(True, mode="listening")
                QTimer.singleShot(500, self.start_interview_listening)

    def toggle_interview_mode(self):
        self.interview_mode = not getattr(self, 'interview_mode', False)
        self.interview_btn.setChecked(self.interview_mode)
        
        if self.interview_mode:
            self.add_system_message("🎙️ LIVE INTERVIEW MODE ENABLED: Continuous voice listening and screen capture analysis active.")
            self.start_interview_listening()
            
            # Pre-calculate screen hash on startup to prevent initial static screen trigger (in-memory)
            try:
                img = self.capture_stealth_image()
                if img:
                    import hashlib
                    self.last_img_hash = hashlib.md5(img.tobytes()).hexdigest()
            except Exception:
                pass
            
            # Start rainbow border timer
            self.rainbow_timer = QTimer(self)
            self.rainbow_timer.timeout.connect(self.update_interview_rainbow)
            self.rainbow_timer.start(40) # ~25 fps HSL cycle
            
            # Save original provider so we can restore it later
            self.saved_active_provider = self.active_provider
            if self.api_keys.get("groq", "").strip():
                self.active_provider = "Groq"
                self.provider_combo.setCurrentText("Groq")
            else:
                self.active_provider = "NVIDIA"
                self.provider_combo.setCurrentText("NVIDIA")
            
            # Show Live Preview Popup (parented to self to prevent focus disappearing issues)
            if not hasattr(self, 'preview_popup') or not self.preview_popup:
                self.preview_popup = LivePreviewPopup(self)
            self.preview_popup.show()
            
            # Position it sticking to the right/left of the main overlay window
            self.align_preview_popup()
            
            # Start continuous vision loop (AI analysis)
            self.interview_voice_buffer = ""
            self.vision_loop_timer = QTimer(self)
            self.vision_loop_timer.timeout.connect(self.on_vision_loop_tick)
            self.vision_loop_timer.start(5000) # Scan every 5 seconds
            
            # Start preview frame update timer (Visual screen feed)
            self.preview_timer = QTimer(self)
            self.preview_timer.timeout.connect(self.on_preview_timer_tick)
            self.preview_timer.start(1500) # Update mini window every 1.5 seconds
            
            # Start continuous voice loop
            QTimer.singleShot(500, self.start_interview_listening)
        else:
            # Deactive
            self.interview_btn.setStyleSheet("")
            if hasattr(self, 'rainbow_timer'):
                self.rainbow_timer.stop()
            if hasattr(self, 'vision_loop_timer'):
                self.vision_loop_timer.stop()
            if hasattr(self, 'preview_timer'):
                self.preview_timer.stop()
            self.add_system_message("🎤 LIVE INTERVIEW MODE DISABLED.")
            
            # Hide Live Preview Popup
            if hasattr(self, 'preview_popup') and self.preview_popup:
                self.preview_popup.hide()
                self.preview_popup.deleteLater()
                self.preview_popup = None
                
            # Restore saved provider
            if hasattr(self, 'saved_active_provider'):
                self.active_provider = self.saved_active_provider
                self.provider_combo.setCurrentText(self.active_provider)
                
            self.typing_timer.stop()
            self.typing_label.hide()
            self.typing_label.setText("")
            
            # Safely terminate the background dictation thread immediately
            if hasattr(self, 'dictation_worker') and self.dictation_worker:
                try:
                    if self.dictation_worker.isRunning():
                        self.dictation_worker.terminate()
                        self.dictation_worker.wait()
                except Exception: pass
                self.dictation_worker = None
                
            self.wave_widget.set_active(False)
            self.chat_input.setPlaceholderText(f"Ask {self.active_provider} anything, or /imagine...")
            self.update_style()
            
    def update_interview_rainbow(self):
        if getattr(self, 'interview_mode', False):
            self.rainbow_hue = (getattr(self, 'rainbow_hue', 0) + 8) % 360
            import colorsys
            r_f, g_f, b_f = colorsys.hsv_to_rgb(self.rainbow_hue / 360.0, 1.0, 1.0)
            r, g, b = int(r_f * 255), int(g_f * 255), int(b_f * 255)
            self.interview_border_color = f"rgb({r}, {g}, {b})"
            self.update_style()
            
    def start_interview_listening(self):
        if not getattr(self, 'interview_mode', False):
            return
            
        # Protect against active running thread garbage collection crashes
        if hasattr(self, 'dictation_worker') and self.dictation_worker and self.dictation_worker.isRunning():
            return
            
        self.wave_widget.set_active(True, mode="listening")
        self.chat_input.setPlaceholderText("[🎙️ Interview Mode: Listening... Speak naturally]")
        
        self.dictation_worker = DictationWorker()
        self.dictation_worker.finished_signal.connect(self.on_interview_voice_finished)
        self.dictation_worker.error_signal.connect(self.on_interview_voice_error)
        self.dictation_worker.status_signal.connect(lambda s: self.chat_input.setPlaceholderText(f"[🎙️ Interview: {s}]"))
        self.dictation_worker.start()
        
    def on_interview_voice_finished(self, text):
        if not getattr(self, 'interview_mode', False):
            return
            
        text = text.strip()
        if text:
            self.log_event(f"Interview Voice text: {text}", "info")
            # Update preview popup with transcribed voice
            if hasattr(self, 'preview_popup') and self.preview_popup:
                display_text = text if len(text) <= 42 else f"{text[:39]}..."
                self.preview_popup.status_label.setText(f"🗣️ Heard: {display_text}")
            
            self.interview_voice_buffer = getattr(self, 'interview_voice_buffer', '') + " " + text
            
        # Instantly loop the voice listening so we don't miss anything
        QTimer.singleShot(100, self.start_interview_listening)
        
    def on_vision_loop_tick(self):
        if not getattr(self, 'interview_mode', False):
            return
            
        # Protect against active running thread garbage collection crashes
        if hasattr(self, 'vision_worker') and self.vision_worker and self.vision_worker.isRunning():
            return
            
        # Capture screen in-memory
        img = self.capture_stealth_image()
        if not img:
            return
            
        voice_context = getattr(self, 'interview_voice_buffer', '').strip()
        self.interview_voice_buffer = "" # Flush the buffer
        
        # Calculate image hash to check if screen changed (in-memory)
        img_changed = True
        try:
            import hashlib
            img_bytes = img.tobytes()
            img_hash = hashlib.md5(img_bytes).hexdigest()
            
            last_hash = getattr(self, 'last_img_hash', None)
            if last_hash == img_hash:
                img_changed = False
            self.last_img_hash = img_hash
        except Exception:
            pass
            
        # If screen hasn't changed AND there is no voice context, calm down and skip API call
        if not img_changed and not voice_context:
            return
            
        self.typing_dots = 0
        self.typing_label.setText("⚡ AI is continuously analyzing screen & voice")
        self.typing_label.show()
        self.typing_timer.start(400)
        
        self.current_streaming_text = ""
        
        if hasattr(self, 'preview_popup') and self.preview_popup:
            self.preview_popup.status_label.setText(f"Scanning voice & screen...")
            try:
                import io
                import base64
                from PyQt5.QtGui import QImage, QPixmap
                
                # Update visual preview popup using safe in-memory JPEG compression
                buffer_preview = io.BytesIO()
                img.save(buffer_preview, format="JPEG", quality=50)
                qim = QImage()
                qim.loadFromData(buffer_preview.getvalue())
                pixmap = QPixmap.fromImage(qim)
                self.preview_popup.update_frame(pixmap)
                
                # Convert PIL Image to base64 string directly in-memory using JPEG for optimal vision payload
                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=50)
                b64_img = base64.b64encode(buffer.getvalue()).decode('utf-8')
                
                self.vision_worker = VisionInterviewWorker(b64_img, voice_context)
                self.vision_worker.chunk_signal.connect(self.on_vision_chunk_received)
                self.vision_worker.result_signal.connect(self.on_vision_interview_result)
                self.vision_worker.start()
            except Exception as e:
                print("Failed to convert image to base64 in-memory:", e)
            
    def on_vision_chunk_received(self, chunk):
        pass
            
    def on_vision_interview_result(self, question, solution):
        if not getattr(self, 'interview_mode', False):
            return
            
        # Hide the compiling spinner label
        self.typing_timer.stop()
        self.typing_label.hide()
        
        if question == "NO_QUESTION":
            if hasattr(self, 'preview_popup') and self.preview_popup:
                self.preview_popup.status_label.setText("👀 Monitoring (No question detected)")
            return
            
        if hasattr(self, 'preview_popup') and self.preview_popup:
            self.preview_popup.status_label.setText("💡 Answer Generated!")
            
        # Display the result in the chat box
        self.add_command_message(f"🎙️ Interview Detected Question: {question}")
        self.add_ai_message(solution, provider_name="System")
        
        # Trigger speech TTS if enabled
        if self.voice_enabled:
            # Clean formatting markdown tags for clean voice synthesizer narration
            import re
            clean_speech = re.sub(r'```[a-zA-Z]*\n[\\s\\S]*?```', '[code snippet skipped]', solution)
            clean_speech = re.sub(r'[*`#_]', '', clean_speech)
            clean_speech = clean_speech.replace("Approach 1:", "").replace("Approach 2:", "")
            self.speak_response(clean_speech)
            
    def on_interview_voice_error(self, err):
        if not getattr(self, 'interview_mode', False):
            return
        QTimer.singleShot(100, self.start_interview_listening)

    def on_preview_timer_tick(self):
        if not getattr(self, 'interview_mode', False):
            return
        img = self.capture_stealth_image()
        if img:
            if hasattr(self, 'preview_popup') and self.preview_popup:
                from PyQt5.QtGui import QImage, QPixmap
                import io
                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=50)
                qim = QImage()
                qim.loadFromData(buffer.getvalue())
                pixmap = QPixmap.fromImage(qim)
                self.preview_popup.update_frame(pixmap)

    def capture_stealth_image(self):
        try:
            import mss
            from PIL import Image
            
            screen = QApplication.primaryScreen().geometry()
            monitor = {"top": screen.y(), "left": screen.x(), "width": screen.width(), "height": screen.height()}
            
            with mss.mss() as sct:
                sct_img = sct.grab(monitor)
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                
            return img
        except Exception as e:
            print("Interview screen capture failed:", e)
            return None

    def on_voice_status(self, status):
        self.chat_input.setPlaceholderText(status)

    def process_voice_input(self, text):
        text_lower = text.lower().strip()
        words = text_lower.split()
        
        # 1. Clear Chat ("clear chat", "wipe conversation", "reset screen", "click clear", "clear", etc.)
        clear_verbs = ["clear", "wipe", "reset", "empty", "delete", "flush"]
        chat_nouns = ["chat", "history", "conversation", "messages", "screen", "board", "window", "overlay"]
        has_clear_verb = any(v in words for v in clear_verbs) or any(v in text_lower for v in ["clear", "wipe", "reset"])
        has_chat_noun = any(n in words for n in chat_nouns)
        
        is_clear_cmd = False
        if text_lower in ["clear", "reset", "wipe"]:
            is_clear_cmd = True
        elif has_clear_verb and has_chat_noun:
            is_clear_cmd = True
        elif has_clear_verb and any(w in words for w in ["click", "press", "hit"]):
            is_clear_cmd = True
            
        if is_clear_cmd:
            self.clear_chat()
            self.add_command_message("⚙️ Action: Cleared Chat History")
            return
            
        # 2. Theme Control
        dark_keywords = ["dark mode", "go dark", "night mode", "dark theme", "enable dark", "black mode"]
        light_keywords = ["light mode", "go light", "day mode", "light theme", "enable light", "white mode"]
        if any(kw in text_lower for kw in dark_keywords):
            self.set_theme(True)
            self.add_command_message("⚙️ Action: Switched to Dark Theme")
            return
        if any(kw in text_lower for kw in light_keywords):
            self.set_theme(False)
            self.add_command_message("⚙️ Action: Switched to Light Theme")
            return
            
        # 3. Focus / Focus Mode
        stealth_keywords = ["stealth", "background", "safe mode", "hide focus", "stealth mode", "type in background"]
        active_keywords = ["active", "overlay", "focus mode", "show focus", "active mode", "type in overlay"]
        if any(kw in text_lower for kw in stealth_keywords):
            if self.focus_mode != 'Background':
                self.toggle_focus_mode()
                self.add_command_message("⚙️ Action: Activated Stealth Mode (Background)")
            return
        if any(kw in text_lower for kw in active_keywords):
            if self.focus_mode != 'Overlay':
                self.toggle_focus_mode()
                self.add_command_message("⚙️ Action: Activated Active Mode (Overlay)")
            return
            
        # 4. Hide / Show
        hide_keywords = ["hide", "minimize", "collapse", "go away", "dock", "hide overlay", "hide window"]
        show_keywords = ["show", "restore", "expand", "bring back", "undock", "show overlay", "show window"]
        if any(kw in text_lower for kw in hide_keywords):
            self.minimize_to_edge()
            self.add_command_message("⚙️ Action: Minimized Window")
            return
        if any(kw in text_lower for kw in show_keywords):
            self.restore_from_edge()
            self.add_command_message("⚙️ Action: Restored Window")
            return
            
        # 5. Exit overlay
        exit_keywords = ["exit", "close", "quit", "shutdown", "stop app", "terminate", "exit overlay", "close overlay"]
        if any(kw in text_lower for kw in exit_keywords):
            self.add_command_message("⚙️ Action: Exiting Application...")
            self.force_exit()
            return
            
        # 6. Scan / Screenshot
        scan_verbs = ["scan", "screenshot", "capture", "read", "check", "analyze", "solve"]
        scan_nouns = ["screen", "display", "monitor", "page", "window", "image", "pic"]
        has_scan_verb = any(v in words for v in scan_verbs) or any(v in text_lower for v in ["screenshot", "capture"])
        has_scan_noun = any(n in words for n in scan_nouns)
        if (has_scan_verb and has_scan_noun) or text_lower in ["scan", "capture", "screenshot"]:
            self.add_command_message("⚙️ Action: Capturing Screen Scan...")
            self.scan_screen()
            return
            
        # 7. Inject / Paste Code
        inject_verbs = ["inject", "paste", "type", "send", "write", "insert"]
        inject_cmd = False
        target_index = None
        
        number_map = {
            "one": 1, "1": 1,
            "two": 2, "2": 2,
            "three": 3, "3": 3,
            "four": 4, "4": 4,
            "five": 5, "5": 5,
            "six": 6, "6": 6,
            "seven": 7, "7": 7,
            "eight": 8, "8": 8,
            "nine": 9, "9": 9,
            "ten": 10, "10": 10
        }
        
        for verb in inject_verbs:
            if verb in text_lower:
                parts_words = text_lower.split()
                try:
                    v_idx = parts_words.index(verb)
                    if v_idx + 1 < len(parts_words):
                        next_word = parts_words[v_idx + 1]
                        if next_word in number_map:
                            target_index = number_map[next_word]
                            inject_cmd = True
                            break
                except ValueError:
                    pass
                    
        if not inject_cmd:
            inject_nouns = ["code", "text", "answer", "snippet", "solution"]
            has_inject_verb = any(v in words for v in inject_verbs) or any(v in text_lower for v in ["paste", "inject"])
            has_inject_noun = any(n in words for n in inject_nouns)
            if (has_inject_verb and has_inject_noun) or text_lower in ["inject", "paste"]:
                inject_cmd = True
                
        if inject_cmd:
            if target_index is not None:
                self.add_command_message(f"⚙️ Action: Injecting Code Block {target_index}...")
                self.inject_code(target_index)
            else:
                self.add_command_message("⚙️ Action: Injecting Latest Code Snippet...")
                self.inject_code()
            return
            
        # 8. Mute / Unmute Speaker TTS
        mute_spk_keywords = ["mute speaker", "mute voice", "mute audio", "silence", "silent", "turn off voice", "disable voice"]
        unmute_spk_keywords = ["unmute speaker", "unmute voice", "unmute audio", "turn on voice", "enable voice"]
        if any(kw in text_lower for kw in mute_spk_keywords):
            if self.voice_enabled:
                self.toggle_voice()
                self.add_command_message("⚙️ Action: Speaker Audio Muted")
            return
        if any(kw in text_lower for kw in unmute_spk_keywords):
            if not self.voice_enabled:
                self.toggle_voice()
                self.add_command_message("⚙️ Action: Speaker Audio Unmuted")
            return
            
        # 9. Mute Microphone
        mute_mic_keywords = ["mute mic", "mute microphone", "stop listening", "turn off mic", "disable mic", "stop voice"]
        if any(kw in text_lower for kw in mute_mic_keywords):
            self.mic_btn.setChecked(False)
            self.stop_continuous_voice()
            self.add_command_message("⚙️ Action: Microphone Listening Deactivated")
            return
            
        # 10. Change Provider / Model
        model_verbs = ["model", "provider", "engine", "system", "ai"]
        change_verbs = ["change", "switch", "use", "swap", "select", "set", "open"]
        has_model_change = any(v in text_lower for v in change_verbs) and any(n in text_lower for n in model_verbs)
        
        provider_target = None
        if "gemini" in text_lower:
            provider_target = "Gemini"
        elif "groq" in text_lower:
            provider_target = "Groq"
        elif "openrouter" in text_lower or "open router" in text_lower or "router" in text_lower:
            provider_target = "OpenRouter"
        elif "search" in text_lower or "google" in text_lower or "web search" in text_lower:
            provider_target = "Google Web Search"
            
        is_provider_cmd = False
        if provider_target:
            if has_model_change:
                is_provider_cmd = True
            elif any(prefix in text_lower for prefix in ["switch to", "use", "set provider to", "change to", "select", "open"]):
                is_provider_cmd = True
            elif text_lower in ["open router", "openrouter", "groq", "gemini", "google web search", "router"]:
                is_provider_cmd = True
                
        if is_provider_cmd and provider_target:
            self.active_provider = provider_target
            index = self.provider_combo.findText(self.active_provider)
            if index >= 0:
                self.provider_combo.setCurrentIndex(index)
            self.update_style()
            self.add_command_message(f"⚙️ Action: Switched Provider to {self.active_provider}")
            return

        # 11. Transparency / Opacity Settings Command
        opacity_keywords = ["transparency", "opacity", "alpha", "transparent"]
        if any(kw in text_lower for kw in opacity_keywords):
            val = None
            word_num_map = {
                "zero": 0, "none": 0, "off": 0,
                "ten": 10, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
                "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100, "full": 100
            }
            import re
            m = re.search(r'\d+', text_lower)
            if m:
                val = int(m.group(0))
            else:
                for w, num in word_num_map.items():
                    if w in text_lower:
                        val = num
                        break
            if val is not None:
                val = max(0, min(100, val))
                if hasattr(self, 'change_opacity'): self.change_opacity(val)
                self.change_opacity(val)
                self.add_command_message(f"⚙️ Action: Set Transparency/Opacity to {val}%")
                return
            
        # 12. Otherwise, treat as regular chat message
        self.chat_input.setText(text)
        self.handle_chat(voice_input=True)

    def add_command_message(self, text):
        color = "#8b5cf6" if self.is_dark else "#6d28d9"
        html = f"""
        <div style='text-align: center; margin: 10px 0;'>
            <span style='background-color: rgba(139, 92, 246, 0.15); color: {color}; border: 1px solid rgba(139, 92, 246, 0.3); border-radius: 12px; padding: 4px 10px; font-size: 12px; font-family: "Segoe UI", sans-serif;'>
                {text}
            </span>
        </div>
        """
        self.chat_history.append(html)
        self.scroll_to_bottom(force=True)

    def animate_typing(self):
        self.typing_dots = (self.typing_dots + 1) % 4
        dots_str = "." * self.typing_dots
        self.typing_label.setText(f"⚡ AI is compiling response{dots_str}")

    def focus_chat_from_hotkey(self):
        self.log_event("Chat force-focused from hotkey.", "info")
        hwnd = int(self.winId())
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        self.chat_input.setFocus()

    def handle_chat(self, voice_input=False):
        # If clicked while AI is generating, act as a Stop Response button
        if hasattr(self, 'worker') and self.worker and self.worker.isRunning():
            try:
                self.worker.terminate()
                self.worker.wait()
            except Exception: pass
            self.worker = None
            
            self.typing_timer.stop()
            self.typing_label.hide()
            self.typing_label.setText("")
            self.add_system_message("⏹️ Response generation stopped.")
            self.update_send_button_state(is_generating=False)
            return
            
        text = self.chat_input.text().strip()
        has_attachment = hasattr(self, 'extracted_ocr_text') and self.extracted_ocr_text
        if not text and not has_attachment: return
        self.chat_input.clear()
        
        if getattr(self, 'ghost_active', False):
            self.ghost_typing_signal.emit(False)
            
        display_text = f"🎤 {text}" if voice_input else (text if text else "🖼️ Sent screenshot snippet")
        self.add_user_message(display_text)
        
        if text.startswith("/imagine "):
            prompt = text[9:].strip()
            self.add_system_message(f"Generating image for '{prompt}'...")
            self.start_ai_task("imagine", prompt)
        else:
            # Check if there is an active OCR text attachment
            prompt = text if text else "Analyze this screenshot context."
            if has_attachment:
                prompt = (
                    f"--- ATTACHED SCREENSHOT TEXT CONTEXT ---\n"
                    f"{self.extracted_ocr_text}\n"
                    f"-----------------------------------------\n\n"
                    f"{prompt}"
                )
                self.clear_attachment()
                
            self.typing_dots = 0
            self.typing_label.setText("⚡ AI is compiling response")
            self.typing_label.show()
            self.typing_timer.start(400)
            self.start_ai_task("text", prompt)

    def scan_screen(self):
        try:
            import mss
            import mss.tools
            import uuid
            
            # Capture the entire desktop dimensions instead of the transparent overlay geometry
            screen = QApplication.primaryScreen().geometry()
            monitor = {"top": screen.y(), "left": screen.x(), "width": screen.width(), "height": screen.height()}
            
            with mss.mss() as sct:
                sct_img = sct.grab(monitor)
                scan_path = os.path.join(get_app_dir(), "scan_result.png")
                mss.tools.to_png(sct_img.rgb, sct_img.size, output=scan_path)
                
        except ImportError:
            self.add_system_message("<b style='color:red;'>Missing dependencies. Run pip install mss pillow</b>")
            return
        except Exception as e:
            self.add_system_message(f"Screen capture failed: {str(e)}")
            return
            
        text = self.chat_input.text().strip()
        self.chat_input.clear()
        
        default_prompt = (
            "Analyze this full-screen image capture precisely. Perform these tasks:\n"
            "1. Extract all text content, coding problems, reasoning/aptitude questions, math queries, or technical descriptions visible on the screen.\n"
            "2. For any technical, programming, mathematical, reasoning, or multiple-choice questions found in the captured screen, provide the correct, optimal solution with concise step-by-step reasoning.\n"
            "3. If active code syntax, uncompleted functions, or comments are present in the code editor, complete the logic cleanly in the target programming language."
        )
        prompt = text if text else default_prompt
        
        if text:
            self.add_user_message(text)
            
        self.typing_dots = 0
        self.typing_label.setText("⚡ AI is compiling response")
        self.typing_label.show()
        self.typing_timer.start(400)
        self.start_ai_task("vision", prompt, image_path=scan_path)

    def get_menu_style(self):
        if self.is_dark:
            return """
                QMenu {
                    background-color: #1e1b4b;
                    border: 1px solid #8b5cf6;
                    border-radius: 6px;
                    padding: 4px;
                }
                QMenu::item {
                    color: #e2e8f0;
                    padding: 6px 20px;
                    border-radius: 4px;
                }
                QMenu::item:selected {
                    background-color: #8b5cf6;
                    color: white;
                }
            """
        else:
            return """
                QMenu {
                    background-color: #ffffff;
                    border: 1px solid #8b5cf6;
                    border-radius: 6px;
                    padding: 4px;
                }
                QMenu::item {
                    color: #1f2937;
                    padding: 6px 20px;
                    border-radius: 4px;
                }
                QMenu::item:selected {
                    background-color: #8b5cf6;
                    color: white;
                }
            """

    def show_header_more_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet(self.get_menu_style())
        
        act_sidebar = menu.addAction("📁 Toggle Sidebar")
        act_sidebar.triggered.connect(self.toggle_sidebar)
        
        act_theme = menu.addAction("🎨 Toggle Theme")
        act_theme.triggered.connect(self.toggle_theme)
        
        act_focus = menu.addAction(f"🔒 Toggle Focus Mode ({self.focus_mode})")
        act_focus.triggered.connect(self.toggle_focus_mode)
        
        act_scrap = menu.addAction("✂️ Crop & Scrap (OCR)")
        act_scrap.triggered.connect(self.start_screen_scrap)
        
        act_clear = menu.addAction("🧹 Clear Chat History")
        act_clear.triggered.connect(self.clear_chat)
        
        opacity_menu = menu.addMenu("🌓 Set Opacity")
        opacity_menu.setStyleSheet(self.get_menu_style())
        for p in [30, 50, 70, 90, 100]:
            act = opacity_menu.addAction(f"{p}%")
            act.triggered.connect(lambda checked, val=p: self.change_opacity(val))
            
        menu.exec_(self.header_more_btn.mapToGlobal(QPoint(0, self.header_more_btn.height())))

    def show_bottom_more_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet(self.get_menu_style())
        
        provider_menu = menu.addMenu("🤖 AI Provider")
        provider_menu.setStyleSheet(self.get_menu_style())
        providers = ["Gemini", "Groq", "OpenRouter", "NVIDIA", "Google Web Search"]
        for p in providers:
            act = provider_menu.addAction(f"{'● ' if self.active_provider == p else ''}{p}")
            act.triggered.connect(lambda checked, val=p: self.change_provider(val))
            
        act_scan = menu.addAction("📸 Scan Screen")
        act_scan.triggered.connect(lambda: self.trigger_with_bg_click(self.scan_screen))
        
        act_inject = menu.addAction("⚡ Inject Code")
        act_inject.triggered.connect(lambda: self.trigger_with_bg_click(self.inject_code))
        
        act_speaker = menu.addAction(f"🔊 Speaker ({'On' if self.voice_enabled else 'Off'})")
        act_speaker.triggered.connect(self.toggle_voice)
        
        act_interview = menu.addAction("💼 Live Interview Mode")
        act_interview.triggered.connect(self.toggle_interview_mode)
        
        voice_menu = menu.addMenu("🗣️ Select Voice Model")
        voice_menu.setStyleSheet(self.get_menu_style())
        for idx in range(self.voice_combo.count()):
            text = self.voice_combo.itemText(idx)
            act = voice_menu.addAction(text)
            act.triggered.connect(lambda checked, i=idx: self.voice_combo.setCurrentIndex(i))
            
        act_voice_input = menu.addAction("🎤 Voice Input (PTT)")
        act_voice_input.triggered.connect(self.start_single_voice)
        
        act_live_voice = menu.addAction("🎙️ Live Voice (Continuous)")
        act_live_voice.triggered.connect(self.toggle_continuous_voice)
        
        menu.exec_(self.bottom_more_btn.mapToGlobal(QPoint(0, -menu.sizeHint().height())))

    def adjust_responsive_layout(self, w):
        if getattr(self, 'is_hidden', False):
            return
            
        low_space = w < 760
        
        self.sidebar_btn.setVisible(not low_space)
        self.theme_btn.setVisible(not low_space)
        self.focus_btn.setVisible(not low_space)
        self.opacity_label.setVisible(not low_space)
        self.slider.setVisible(not low_space)
        self.scrap_btn.setVisible(not low_space)
        self.clear_btn.setVisible(not low_space)
        
        self.header_more_btn.setVisible(low_space)
        
        self.provider_combo.setVisible(not low_space)
        self.scan_btn.setVisible(not low_space)
        self.inject_btn.setVisible(not low_space)
        self.voice_btn.setVisible(not low_space)
        self.interview_btn.setVisible(not low_space)
        self.voice_combo.setVisible(not low_space)
        self.single_mic_btn.setVisible(not low_space)
        self.mic_btn.setVisible(not low_space)
        
        self.bottom_more_btn.setVisible(low_space)

    def resizeEvent(self, event):
        self.cached_geometry = (self.x(), self.y(), self.width(), self.height())
        super().resizeEvent(event)
        self.adjust_responsive_layout(self.width())
        self.align_preview_popup()
        if hasattr(self, 'scroll_bottom_btn') and self.scroll_bottom_btn:
            try:
                container = self.chat_container
                input_h = self.input_container.height() if hasattr(self, 'input_container') else 115
                bx = (container.width() - self.scroll_bottom_btn.width()) // 2
                by = container.height() - input_h - self.scroll_bottom_btn.height() - 8
                self.scroll_bottom_btn.move(bx, by)
            except Exception:
                pass

    def start_screen_scrap(self):
        self.hide()
        # Give the OS window manager time to fade out the overlay window
        QTimer.singleShot(250, self._open_sniper)
        
    def _open_sniper(self):
        self.sniper = ScreenSniper(parent_overlay=self)
        self.sniper.snip_completed.connect(self.on_snip_completed)
        self.sniper.destroyed.connect(self._restore_overlay)
        self.sniper.setAttribute(Qt.WA_DeleteOnClose)
        self.sniper.show()

    def _restore_overlay(self):
        self.show()
        self.activateWindow()
        self.raise_()



    def on_snip_completed(self, pixmap):
        # 1. Scale pixmap for thumbnail display
        self.attach_thumb.setPixmap(pixmap)
        
        # 2. Update status and show preview panel
        self.attach_status.setText("🔍 Extracting text...")
        self.attach_status.setStyleSheet("color: #a78bfa; font-size: 10px; background: transparent; border: none;")
        self.btn_extract.setEnabled(False)
        self.btn_attach.setEnabled(False)
        self.btn_attach.setChecked(True)
        self.attachment_preview.show()
        
        # 3. Cache snip
        self.current_snip_pixmap = pixmap
        if not hasattr(self, 'extracted_ocr_text'):
            self.extracted_ocr_text = ""
        
        # 4. Start background OCR
        key = self.api_keys.get("gemini", "")
        if not key:
            self.attach_status.setText("❌ Gemini API key missing!")
            self.attach_status.setStyleSheet("color: #f87171; font-size: 10px; background: transparent; border: none;")
            return
            
        chosen_model = self.provider_models.get("gemini", "gemini-2.5-flash")
        
        self.ocr_worker = OCRWorker(key, pixmap, chosen_model)
        self.ocr_worker.finished_signal.connect(self.on_ocr_success)
        self.ocr_worker.error_signal.connect(self.on_ocr_failure)
        self.ocr_worker.start()

    def on_ocr_success(self, text):
        new_text = text.strip()
        if not new_text:
            self.attach_status.setText("⚠️ No text found in capture!")
            self.attach_status.setStyleSheet("color: #fbbf24; font-size: 10px; background: transparent; border: none;")
            return
            
        if self.extracted_ocr_text:
            # We already have an active snippet, so we append the new snippet
            if not self.extracted_ocr_text.startswith("--- Snippet 1 ---"):
                self.extracted_ocr_text = f"--- Snippet 1 ---\n{self.extracted_ocr_text}"
            
            snippet_count = self.extracted_ocr_text.count("--- Snippet ") + 1
            self.extracted_ocr_text += f"\n\n--- Snippet {snippet_count} ---\n{new_text}"
            
            char_count = len(self.extracted_ocr_text)
            self.attach_status.setText(f"✅ {snippet_count} snippets attached ({char_count} chars)")
        else:
            # First snippet
            self.extracted_ocr_text = new_text
            char_count = len(self.extracted_ocr_text)
            self.attach_status.setText(f"✅ Text extracted ({char_count} chars)")
            
        self.attach_status.setStyleSheet("color: #34d399; font-size: 10px; background: transparent; border: none;")
        self.btn_extract.setEnabled(True)
        self.btn_attach.setEnabled(True)
        
    def on_ocr_failure(self, error):
        self.attach_status.setText("❌ Extraction failed!")
        self.attach_status.setStyleSheet("color: #f87171; font-size: 10px; background: transparent; border: none;")
        self.log_event(f"OCR Extraction failed: {error}", "error")

    def copy_extracted_text(self):
        if hasattr(self, 'extracted_ocr_text') and self.extracted_ocr_text:
            clipboard = QApplication.clipboard()
            clipboard.setText(self.extracted_ocr_text)
            self.add_system_message("📋 Extracted text copied to clipboard.")


    def clear_attachment(self):
        self.attachment_preview.hide()
        self.current_snip_pixmap = None
        self.extracted_ocr_text = ""
        if hasattr(self, 'ocr_worker') and self.ocr_worker and self.ocr_worker.isRunning():
            try:
                self.ocr_worker.terminate()
                self.ocr_worker.wait()
            except Exception: pass
            self.ocr_worker = None

    def start_ai_task(self, task_type, prompt, image_path=None):
        import time
        self.ai_task_start_time = time.time()
        self.log_event(f"Starting AI Task ({task_type}) with {self.active_provider}...", "info")
        session = next((s for s in self.sessions if s['id'] == self.current_chat_id), None)
        history = session['messages'] if session else []
        self.worker = AITaskWorker(self.active_provider, self.api_keys, task_type, prompt, history, image_path, self.provider_models)
        self.worker.finished_signal.connect(self.on_ai_finished)
        self.worker.error_signal.connect(self.on_ai_error)
        self.worker.start()
        self.update_send_button_state(is_generating=True)
        
    def update_send_button_state(self, is_generating):
        if is_generating:
            self.send_btn.icon_type = "stop"
            self.send_btn.setText("Stop")
            self.send_btn.setToolTip("Stop response generation")
            self.send_btn.update()
        else:
            self.send_btn.icon_type = "send"
            self.send_btn.setText("Send")
            self.send_btn.setToolTip("Send Message (Hotkey: Alt+Z then D)")
            self.send_btn.update()

    def on_ai_finished(self, task_type, content, raw_code):
        self.update_send_button_state(is_generating=False)
        self.typing_timer.stop()
        self.typing_label.hide()
        self.typing_label.setText("")
        
        import time
        duration = time.time() - getattr(self, 'ai_task_start_time', time.time())
        self.log_event(f"AI Task completed in {duration:.2f}s", "performance")
        
        if task_type == "text" or task_type == "vision":
            provider_name = "Gemini Vision" if task_type == "vision" else self.active_provider
            self.log_event(f"AI Response received from {provider_name}.", "success")
            self.add_ai_message(content, provider_name)
            
            text_to_speak = re.sub(r'```.*?```', '', content, flags=re.DOTALL)
            text_to_speak = re.sub(r'[`*#]', '', text_to_speak).strip()
            
            if getattr(self, 'interview_mode', False):
                if text_to_speak:
                    self.tts_worker.speak(content)
                else:
                    QTimer.singleShot(1000, self.start_interview_listening)
            elif self.voice_enabled:
                if text_to_speak:
                    self.tts_worker.speak(content)
            
            if raw_code:
                self.last_ai_code = raw_code
                self.add_system_message("Code snippet loaded. Click ⚡ Inject")
                
        elif task_type == "image":
            file_url = f"file:///{content.replace(os.sep, '/')}"
            self.add_ai_message(f"[IMAGE: {file_url}]", "Pollinations")
            
    def on_ai_error(self, error_msg):
        self.update_send_button_state(is_generating=False)
        self.typing_timer.stop()
        self.typing_label.hide()
        self.typing_label.setText("")
        
        import time
        duration = time.time() - getattr(self, 'ai_task_start_time', time.time())
        self.log_event(f"AI Task failed after {duration:.2f}s", "performance")
        
        self.log_event(f"AI Task Failed: {error_msg}", "error")
        self.add_system_message(f"<b style='color:red;'>Error:</b> {error_msg}")
        if getattr(self, 'interview_mode', False):
            QTimer.singleShot(2000, self.start_interview_listening)

    def get_text_to_inject_by_index(self, index):
        text_to_inject = None
        if index is not None:
            if hasattr(self, 'last_ai_codes') and 0 <= index - 1 < len(self.last_ai_codes):
                text_to_inject = self.last_ai_codes[index - 1]
        else:
            text_to_inject = getattr(self, 'last_ai_code', None)
            if not text_to_inject and hasattr(self, 'last_ai_codes') and self.last_ai_codes:
                text_to_inject = self.last_ai_codes[-1]
        return text_to_inject

    def inject_code(self, index=None):
        if getattr(self, 'injection_in_progress', False):
            self.add_system_message("<b style='color:orange;'>Warning:</b> An injection is already in progress. Please wait.")
            return
            
        if getattr(self, 'waiting_for_inject_click', False):
            text_to_inject = self.get_text_to_inject_by_index(index)
            if text_to_inject:
                if getattr(self, 'pending_inject_text', '') == text_to_inject:
                    return # Avoid duplicate logging if clicking the same inject trigger
                self.pending_inject_text = text_to_inject
                self.add_system_message("🎯 Target code block updated. Waiting for click...")
            return
            
        text_to_inject = self.get_text_to_inject_by_index(index)
        if not text_to_inject:
            text_to_inject = (
                "def solve_algorithm(data):\n"
                "    result = []\n"
                "    for item in data:\n"
                "        if item > 0:\n"
                "            result.append(item * 2)\n"
                "    return result\n"
            )
            
        self.pending_inject_text = text_to_inject
        self.pending_inject_switch_focus = False
        self.waiting_for_inject_click = True
        import time
        self._inject_armed_time = time.time()
        self.add_system_message("🎯 Waiting for you to click on the target text area / editor...")

    def perform_stealth_injection(self, text, switch_focus):
        self.injection_in_progress = True
        self.add_system_message(f"Commencing hardware injection ({len(text)} chars)...")
        
        # De-focus overlay window programmatically to guarantee keys reach target
        hwnd = int(self.winId())
        user32 = ctypes.windll.user32
        GWL_EXSTYLE = -20
        WS_EX_TRANSPARENT = 0x00000020
        WS_EX_NOACTIVATE = 0x08000000
        
        orig_ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        
        def run_injection():
            try:
                # Force overlay to lose focus and become click-through during typing
                user32.SetWindowLongW(hwnd, GWL_EXSTYLE, orig_ex | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE)
                time.sleep(0.05)
                stealth_type_text(text, switch_focus)
            finally:
                self.injection_in_progress = False
                # Restore original transparency and interactivity flags
                user32.SetWindowLongW(hwnd, GWL_EXSTYLE, orig_ex)
                
        t = threading.Thread(target=run_injection, daemon=True)
        t.start()

    def _stealth_inject(self, text, target_hwnd):
        """Inject text into target editor using hardware-level keystroke simulation (cannot be blocked by sites)."""
        self.injection_in_progress = True
        self.add_system_message(f"⌨️ Injecting {len(text)} chars via hardware keys...")
        
        # Make overlay transparent and non-activatable during injection
        hwnd = int(self.winId())
        user32 = ctypes.windll.user32
        GWL_EXSTYLE = -20
        WS_EX_TRANSPARENT = 0x00000020
        WS_EX_NOACTIVATE = 0x08000000
        orig_ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        
        def run_injection():
            try:
                # Force overlay click-through
                user32.SetWindowLongW(hwnd, GWL_EXSTYLE, orig_ex | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE)
                time.sleep(0.05)
                # Focus the target window and type
                stealth_type_text(text, switch_focus=False, target_hwnd=target_hwnd)
            finally:
                self.injection_in_progress = False
                user32.SetWindowLongW(hwnd, GWL_EXSTYLE, orig_ex)
        
        t = threading.Thread(target=run_injection, daemon=True)
        t.start()

    def is_input_field_active(self):
        class CURSORINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.c_ulong),
                ("flags", ctypes.c_ulong),
                ("hCursor", ctypes.c_void_p),
                ("ptScreenPos", POINT)
            ]
        info = CURSORINFO()
        info.cbSize = ctypes.sizeof(CURSORINFO)
        h_ibeam = ctypes.windll.user32.LoadCursorW(0, 32513) # IDC_IBEAM
        if ctypes.windll.user32.GetCursorInfo(ctypes.byref(info)):
            if info.hCursor == h_ibeam:
                return True
                
        class GUITHREADINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.c_ulong),
                ("flags", ctypes.c_ulong),
                ("hwndActive", ctypes.c_void_p),
                ("hwndFocus", ctypes.c_void_p),
                ("hwndCapture", ctypes.c_void_p),
                ("hwndMenuOwner", ctypes.c_void_p),
                ("hwndMoveSize", ctypes.c_void_p),
                ("hwndCaret", ctypes.c_void_p),
                ("rcCaret", RECT)
            ]
        gui = GUITHREADINFO()
        gui.cbSize = ctypes.sizeof(GUITHREADINFO)
        active_hwnd = ctypes.windll.user32.GetForegroundWindow()
        tid = ctypes.windll.user32.GetWindowThreadProcessId(active_hwnd, None)
        if ctypes.windll.user32.GetGUIThreadInfo(tid, ctypes.byref(gui)):
            if gui.hwndCaret or (gui.flags & 1):
                return True
                
        return False

    def toggle_visibility_from_hotkey(self):
        import time
        now = time.time()
        if now - getattr(self, 'last_visibility_toggle_time', 0.0) < 0.3:
            return
        self.last_visibility_toggle_time = now
        
        if self.is_hidden: self.restore_from_edge()
        else: self.minimize_to_edge()

    def force_exit(self):
        if getattr(self, 'stop_listening_fn', None):
            try: self.stop_listening_fn(wait_for_stop=False)
            except Exception: pass
        hwnd = int(self.winId())
        try: ctypes.windll.user32.UnregisterHotKey(hwnd, 1)
        except Exception: pass
        try: ctypes.windll.user32.UnregisterHotKey(hwnd, 2)
        except Exception: pass
        self.tts_worker.stop()
        self.save_settings()
        QApplication.quit()
        os._exit(0)
        
    def on_ghost_char(self, char):
        self.chat_input.setText(self.chat_input.text() + char)
        
    def on_ghost_backspace(self):
        text = self.chat_input.text()
        if text:
            self.chat_input.setText(text[:-1])
            
    def on_ghost_typing_toggled(self, active):
        self.ghost_active = active
        self.update_style()
        
        hwnd = int(self.winId())
        GWL_EXSTYLE = -20
        WS_EX_NOACTIVATE = 0x08000000
        
        if active:
            # Remove WS_EX_NOACTIVATE so overlay can receive focus (no window flash)
            ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style & ~WS_EX_NOACTIVATE)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            self.chat_input.setFocus()
            self.log_event("Ghost typing activated.", "warning")
            self.add_system_message("⌨️ GHOST TYPING ACTIVE: Keystrokes will be redirected to the chat input and swallowed from the system. Press Esc or Alt+Z then K to exit.")
        else:
            # Restore WS_EX_NOACTIVATE so overlay goes back to non-intrusive background (no window flash)
            if self.focus_mode == 'Background':
                ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style | WS_EX_NOACTIVATE)
            self.log_event("Ghost typing deactivated.", "info")
            self.add_system_message("🔒 GHOST TYPING INACTIVE: Keystrokes restored to normal system output.")


    def setup_global_hotkeys(self):
        self.ghost_active = False
        self.leader_active = False
        self.waiting_for_inject_click = False
        
        # Register global hotkeys using Windows RegisterHotKey API (failsafe, GIL-safe, 100% crash-proof)
        try:
            hwnd = int(self.winId())
            MOD_ALT = 0x0001
            
            # Hotkey 1: Alt + Z (Toggle leader Command Mode)
            ctypes.windll.user32.RegisterHotKey(hwnd, 1, MOD_ALT, 0x5A) # 0x5A is VK_Z
            
            # Hotkey 2: Alt + L (Toggle Live Interview Mode)
            ctypes.windll.user32.RegisterHotKey(hwnd, 2, MOD_ALT, 0x4C) # 0x4C is VK_L
        except Exception as e:
            print("Failed to register global hotkeys:", e)
            
        # Initialize safe mouse polling timer instead of crash-prone low-level Win32 mouse hook
        self.mouse_poll_timer = QTimer(self)
        self.mouse_poll_timer.timeout.connect(self.poll_mouse_position)
        self.mouse_poll_timer.start(50)
        
    def closeEvent(self, event):
        try:
            hwnd = int(self.winId())
            ctypes.windll.user32.UnregisterHotKey(hwnd, 1)
        except Exception: pass
        try:
            hwnd = int(self.winId())
            ctypes.windll.user32.UnregisterHotKey(hwnd, 2)
        except Exception: pass
        self.force_exit()
        
    def nativeEvent(self, eventType, message):
        if eventType == "windows_generic_MSG":
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == 0x0312: # WM_HOTKEY
                hotkey_id = msg.wParam
                if hotkey_id == 1: # Alt + Z (Toggle Command Mode)
                    self.toggle_leader_mode()
                    return True, 0
                elif hotkey_id == 2: # Alt + L (Toggle Live Interview Mode)
                    self.interview_btn.click()
                    return True, 0
        return super().nativeEvent(eventType, message)
        
    def toggle_leader_mode(self):
        self.leader_active = not getattr(self, 'leader_active', False)
        QTimer.singleShot(0, self.update_style)
        if self.leader_active:
            self.add_system_message("⚡ Command Mode Active (Press Space/H: Hide | S: Scan | I: Inject | 1-9: Indexed | P: Model | O: Voice | U: Voice Typist | M: Live Chat | L: Interview | V: Speaker | E: Focus Chat | Esc/Alt+Z: Exit)")
            
            # Clean leaked 'z' or 'Z' from chat input if Alt+Z was typed while focused
            txt = self.chat_input.text()
            if txt.endswith('z') or txt.endswith('Z'):
                self.chat_input.setText(txt[:-1])
                
            # Defocus chat_input and force focus to the main container
            self.chat_input.setReadOnly(True)
            self.chat_input.clearFocus()
            self.setFocus()
            try:
                hwnd = int(self.winId())
                ctypes.windll.user32.SetForegroundWindow(hwnd)
            except Exception: pass
        else:
            self.chat_input.setReadOnly(False)
            self.add_system_message("⚙️ Command Mode Deactivated")
            
    def keyPressEvent(self, event):
        vk = event.key()
        modifiers = event.modifiers()
        
        # 1. Ghost Typing input capture
        if getattr(self, 'ghost_active', False):
            if vk == Qt.Key_Escape:
                self.ghost_typing_signal.emit(False)
                event.accept()
                return
            elif vk == Qt.Key_Return or vk == Qt.Key_Enter:
                self.ghost_enter_signal.emit()
                event.accept()
                return
            elif vk == Qt.Key_Backspace:
                self.ghost_backspace_signal.emit()
                event.accept()
                return
            elif modifiers == Qt.ControlModifier and vk == Qt.Key_V:
                try:
                    clipboard_text = QApplication.clipboard().text()
                    self.ghost_char_signal.emit(clipboard_text)
                except:
                    pass
                event.accept()
                return
            else:
                char = event.text()
                if char:
                    self.ghost_char_signal.emit(char)
                    event.accept()
                    return
                    
        # 2. Command Mode handling (active either globally when leader_active is True, or when container is focused)
        if getattr(self, 'leader_active', False):
            if vk == Qt.Key_Escape:
                self.waiting_for_inject_click = False
                self.leader_active = False
                self.update_style()
                self.add_system_message("⚙️ Command Mode Deactivated")
                event.accept()
                return
            elif vk == Qt.Key_Left:
                self.move_by(-20, 0)
                event.accept()
                return
            elif vk == Qt.Key_Up:
                self.move_by(0, -20)
                event.accept()
                return
            elif vk == Qt.Key_Right:
                self.move_by(20, 0)
                event.accept()
                return
            elif vk == Qt.Key_Down:
                self.move_by(0, 20)
                event.accept()
                return
            elif vk == Qt.Key_Space or vk == Qt.Key_H:
                self.hotkey_signal.emit()
                event.accept()
                return
            elif vk == Qt.Key_S:
                self.scan_hotkey_signal.emit()
                event.accept()
                return
            elif vk == Qt.Key_I:
                self.inject_hotkey_signal.emit()
                event.accept()
                return
            elif Qt.Key_1 <= vk <= Qt.Key_9:
                self.inject_indexed_hotkey_signal.emit(vk - Qt.Key_0)
                event.accept()
                return
            elif vk == Qt.Key_D:
                self.send_hotkey_signal.emit()
                event.accept()
                return
            elif vk == Qt.Key_E:
                # Trigger Ghost Typing directly to enter secure background input mode
                self.ghost_typing_signal.emit(True)
                event.accept()
                return
            elif vk == Qt.Key_F:
                self.focus_hotkey_signal.emit()
                event.accept()
                return
            elif vk == Qt.Key_C:
                self.clear_hotkey_signal.emit()
                event.accept()
                return
            elif vk == Qt.Key_P:
                self.rotate_provider_hotkey_signal.emit()
                event.accept()
                return
            elif vk == Qt.Key_T:
                self.theme_hotkey_signal.emit()
                event.accept()
                return
            elif vk == Qt.Key_X:
                self.exit_hotkey_signal.emit()
                event.accept()
                return
            elif vk == Qt.Key_K:
                self.ghost_typing_signal.emit(not getattr(self, 'ghost_active', False))
                event.accept()
                return
            elif vk == Qt.Key_M:
                self.mic_btn.click()
                event.accept()
                return
            elif vk == Qt.Key_U:
                self.single_mic_btn.click()
                event.accept()
                return
            elif vk == Qt.Key_V:
                self.voice_btn.click()
                event.accept()
                return
            elif vk == Qt.Key_L:
                self.interview_btn.click()
                event.accept()
                return
            elif vk == Qt.Key_O:
                self.rotate_voice()
                event.accept()
                return
                
        super().keyPressEvent(event)
        
    def showEvent(self, event):
        super().showEvent(event)
        try:
            hwnd = int(self.winId())
            if not ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x00000011):
                ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x00000001)
        except Exception as e:
            print("Failed to register affinity:", e)
        QTimer.singleShot(150, self.apply_initial_focus_styles)
            
    def moveEvent(self, event):
        self.cached_geometry = (self.x(), self.y(), self.width(), self.height())
        super().moveEvent(event)
        self.align_preview_popup()
        

        
    def align_preview_popup(self):
        if hasattr(self, 'preview_popup') and self.preview_popup:
            try:
                rect = self.geometry()
                # Align inside the overlay window in the bottom-right corner, 
                # positioned above the bottom input frame (which starts at rect.height() - input_container.height() - spacing)
                # Spacing offsets: input container height is roughly 110px.
                input_h = self.input_container.height() if hasattr(self, 'input_container') else 115
                
                # Global coordinates of overlay bottom-right above input box
                px = rect.x() + rect.width() - self.preview_popup.width() - 25
                py = rect.y() + rect.height() - self.preview_popup.height() - input_h - 15
                
                self.preview_popup.move(px, py)
            except Exception: pass
            
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Enter:
            if hasattr(obj, 'toolTip') and obj.toolTip():
                from PyQt5.QtWidgets import QToolTip
                QToolTip.showText(QCursor.pos(), obj.toolTip(), obj)
        elif event.type() == QEvent.Leave:
            from PyQt5.QtWidgets import QToolTip
            QToolTip.hideText()
            
        chat_history = getattr(self, 'chat_history', None)
        if chat_history and obj == chat_history and event.type() == QEvent.MouseButtonPress:
            if getattr(self, 'sidebar_frame', None) and self.sidebar_frame.isVisible():
                self.sidebar_frame.hide()
        chat_input = getattr(self, 'chat_input', None)
        if chat_input and obj == chat_input:
            if event.type() == QEvent.MouseButtonPress:
                if self.focus_mode == 'Background' and not getattr(self, 'ghost_active', False):
                    self.ghost_typing_signal.emit(True)
                    return True
            elif event.type() == QEvent.KeyPress:
                if getattr(self, 'ghost_active', False) or getattr(self, 'leader_active', False):
                    # Redirect keypresses from chat_input to the main container handler during Ghost Typing or Command Mode
                    self.keyPressEvent(event)
                    return True
                
        # Collapse sidebar when clicking anywhere on the overlay outside of sidebar
        if event.type() == QEvent.MouseButtonPress:
            sidebar = getattr(self, 'sidebar_frame', None)
            if sidebar and sidebar.isVisible():
                click_pos = obj.mapTo(self, event.pos()) if hasattr(obj, 'mapTo') and hasattr(event, 'pos') else None
                if click_pos is not None:
                    sidebar_rect = sidebar.geometry()
                    if not sidebar_rect.contains(click_pos):
                        sidebar.hide()
        return super().eventFilter(obj, event)
                
    def mousePressEvent(self, event):
        # Collapse sidebar when clicking directly on the main overlay background
        sidebar = getattr(self, 'sidebar_frame', None)
        if sidebar and sidebar.isVisible():
            click_pos = event.pos()
            sidebar_rect = sidebar.geometry()
            if not sidebar_rect.contains(click_pos):
                sidebar.hide()
        super().mousePressEvent(event)
        
    def changeEvent(self, event):
        # Collapse sidebar when window loses focus (clicked outside the app entirely)
        if event.type() == QEvent.ActivationChange:
            if not self.isActiveWindow():
                sidebar = getattr(self, 'sidebar_frame', None)
                if sidebar and sidebar.isVisible():
                    sidebar.hide()
                if self.focus_mode == 'Background':
                    hwnd = int(self.winId())
                    GWL_EXSTYLE = -20
                    WS_EX_NOACTIVATE = 0x08000000
                    WS_EX_TRANSPARENT = 0x00000020
                    ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                    ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style | WS_EX_NOACTIVATE | WS_EX_TRANSPARENT)
        super().changeEvent(event)
        

        
    def move_by(self, dx, dy):
        if getattr(self, 'is_hidden', False):
            if self.normal_geometry:
                self.normal_geometry.translate(dx, dy)
            self.move(self.x() + dx, self.y() + dy)
        else:
            self.move(self.x() + dx, self.y() + dy)
        self.save_settings()

    def toggle_focus_mode(self):
        import time
        now = time.time()
        if now - getattr(self, 'last_focus_toggle_time', 0.0) < 0.3:
            return
        self.last_focus_toggle_time = now
        
        GWL_EXSTYLE = -20
        WS_EX_NOACTIVATE = 0x08000000
        WS_EX_TRANSPARENT = 0x00000020
        hwnd = int(self.winId())
        
        if self.focus_mode == 'Background':
            self.focus_mode = 'Overlay'
            self.focus_btn.setText("Type In: Overlay")
            # Remove WS_EX_NOACTIVATE and WS_EX_TRANSPARENT — allow focus and clicks
            ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style & ~WS_EX_NOACTIVATE & ~WS_EX_TRANSPARENT)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            self.add_system_message("⚠️ WARNING: Keyboard focus is now active. Typing or clicking the chat box WILL be detected by strict exam browsers.")
        else:
            self.focus_mode = 'Background'
            self.focus_btn.setText("Type In: Background")
            # Add WS_EX_NOACTIVATE and WS_EX_TRANSPARENT — suppress focus and intercept clicks at hook level
            ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style | WS_EX_NOACTIVATE | WS_EX_TRANSPARENT)
            self.add_system_message("🔒 STEALTH MODE: AI window is now un-focusable. Click-detection bypassed. Clicks will not trigger browser warnings.")
        self.save_settings()

            
    def minimize_to_edge(self):
        self.is_hidden = True
        self.normal_geometry = self.geometry()
        
        # Save visibility states so we restore only what was open
        self._was_sidebar_visible = self.sidebar_frame.isVisible()
        self._was_settings_visible = self.settings_frame.isVisible()
        
        self.controls_widget.hide()
        self.chat_container.hide()
        self.sidebar_frame.hide()
        self.settings_frame.hide()
        
        # Instantly apply stylesheet update to make background transparent before resizing
        self.update_style()
        self.apply_dock()

    def apply_dock(self):
        desktop = QApplication.desktop().availableGeometry(self)
        thickness = 8
        length = 150
        x, y = self.x(), self.y()
        
        if self.dock_edge in ['left', 'right']:
            if y < desktop.top(): y = desktop.top()
            if y + length > desktop.bottom(): y = desktop.bottom() - length
            w, h = thickness, length
            if self.dock_edge == 'left': x = desktop.left()
            else: x = desktop.right() - thickness
        else:
            if x < desktop.left(): x = desktop.left()
            if x + length > desktop.right(): x = desktop.right() - length
            w, h = length, thickness
            if self.dock_edge == 'top': y = desktop.top()
            else: y = desktop.bottom() - thickness
                
        self.setGeometry(x, y, w, h)
        self.restore_bubble.setGeometry(0, 0, w, h)
        self.update_restore_bubble_style(hovered=False)
        self.restore_bubble.show()

    def snap_to_closest_edge(self):
        desktop = QApplication.desktop().availableGeometry(self)
        cx = self.x() + self.width() / 2
        cy = self.y() + self.height() / 2
        
        d_left = cx - desktop.left()
        d_right = desktop.right() - cx
        d_top = cy - desktop.top()
        d_bottom = desktop.bottom() - cy
        
        m = min(d_left, d_right, d_top, d_bottom)
        if m == d_left: self.dock_edge = 'left'
        elif m == d_right: self.dock_edge = 'right'
        elif m == d_top: self.dock_edge = 'top'
        else: self.dock_edge = 'bottom'
        
        self.apply_dock()
        self.save_settings()

    def set_window_interactive(self, interactive):
        hwnd = getattr(self, 'hwnd', 0)
        if not hwnd:
            return
        GWL_EXSTYLE = -20
        WS_EX_TRANSPARENT = 0x00000020
        ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        if interactive:
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style & ~WS_EX_TRANSPARENT)
        else:
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style | WS_EX_TRANSPARENT)
        try:
            ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020)
        except Exception:
            pass

    def poll_mouse_position(self):
        try:
            from PyQt5.QtGui import QCursor
            from PyQt5.QtWidgets import QScrollBar, QComboBox, QListWidget, QAbstractScrollArea
            gp = QCursor.pos()
            rect = self.geometry()
            rx, ry, rw, rh = rect.x(), rect.y(), rect.width(), rect.height()
            is_inside = (rx <= gp.x() <= rx + rw and ry <= gp.y() <= ry + rh)
            
            # Read left mouse button state for programmatic click routing
            left_pressed = bool(ctypes.windll.user32.GetAsyncKeyState(0x01) & 0x8000)
            was_pressed = getattr(self, 'last_left_pressed', False)
            self.last_left_pressed = left_pressed
            is_click = left_pressed and not was_pressed
            
            # --- Inject click detection (works in ALL focus modes) ---
            if getattr(self, 'waiting_for_inject_click', False):
                import time
                arm_time = getattr(self, '_inject_armed_time', 0)
                if time.time() - arm_time > 0.3:
                    if left_pressed:
                        if not is_inside:
                            text_to_inject = getattr(self, 'pending_inject_text', '')
                            if text_to_inject:
                                self.waiting_for_inject_click = False
                                target_hwnd = ctypes.windll.user32.WindowFromPoint(POINT(gp.x(), gp.y()))
                                QTimer.singleShot(300, lambda: self._stealth_inject(text_to_inject, target_hwnd))
            
            # --- Background mode hover/interactivity management ---
            if getattr(self, 'focus_mode', '') != 'Background':
                return
                
            if getattr(self, 'is_hidden', False):
                if is_inside and is_click:
                    self.restore_from_edge()
                return
                
            # Programmatic click routing for pure ghost click-through interaction
            if is_inside and is_click:
                lp = self.mapFromGlobal(gp)
                child = self.childAt(lp)
                if child:
                    parent_widget = child
                    while parent_widget:
                        if isinstance(parent_widget, QPushButton):
                            parent_widget.click()
                            break
                        elif isinstance(parent_widget, QComboBox):
                            parent_widget.showPopup()
                            break
                        elif isinstance(parent_widget, QListWidget):
                            local_list_pos = parent_widget.mapFromGlobal(gp)
                            item = parent_widget.itemAt(local_list_pos)
                            if item:
                                parent_widget.setCurrentItem(item)
                                parent_widget.itemClicked.emit(item)
                            break
                        elif isinstance(parent_widget, QLineEdit):
                            parent_widget.setFocus()
                            break
                        elif parent_widget == getattr(self, 'slider', None):
                            sp = parent_widget.mapFromGlobal(gp)
                            val = int((sp.x() / parent_widget.width()) * (parent_widget.maximum() - parent_widget.minimum())) + parent_widget.minimum()
                            parent_widget.setValue(val)
                            break
                        parent_widget = parent_widget.parent()
                        
            # Force the window to remain permanently click-through (no interactive toggle)
            # This ensures mouse clicks physically pass straight through to the underlying window at all times!
            is_interactive = getattr(self, 'temp_interactive', False)
            if is_interactive:
                self.temp_interactive = False
                self.set_window_interactive(False)
        except Exception:
            pass

    def restore_from_edge(self):
        self.is_hidden = False
        self.restore_bubble.hide()
        
        # Instantly restore normal background and border
        self.update_style()
        
        self.controls_widget.show()
        self.chat_container.show()
        
        # Restore sub-views based on their original states
        if getattr(self, '_was_sidebar_visible', False):
            self.sidebar_frame.show()
        else:
            self.sidebar_frame.hide()
            
        if getattr(self, '_was_settings_visible', False):
            self.settings_frame.show()
        else:
            self.settings_frame.hide()
            
        # Ensure inner widgets are also shown
        self.chat_history.show()
        self.input_container.show()
        
        if self.normal_geometry:
            self.setGeometry(self.normal_geometry)

    def enterEvent(self, event):
        if self.is_hidden:
            rect = self.geometry()
            expansion = 10
            x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
            if self.dock_edge == 'left': w += expansion
            elif self.dock_edge == 'right': x -= expansion; w += expansion
            elif self.dock_edge == 'top': h += expansion
            elif self.dock_edge == 'bottom': y -= expansion; h += expansion
            self.setGeometry(x, y, w, h)
            self.restore_bubble.setGeometry(0, 0, w, h)
            self.update_restore_bubble_style(hovered=True)
        super().enterEvent(event)
            

        


    def leaveEvent(self, event):
        if self.is_hidden: self.apply_dock()
        super().leaveEvent(event)
        
    def paintEvent(self, event):
        from PyQt5.QtWidgets import QStyleOption, QStyle
        from PyQt5.QtGui import QPainter
        opt = QStyleOption()
        opt.initFrom(self)
        p = QPainter(self)
        self.style().drawPrimitive(QStyle.PE_Widget, opt, p, self)

    def update_style(self):
        # Premium dark glass vs light glass color tokens
        if self.is_dark:
            bg_gradient = f"qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(22, 22, 26, {self.opacity_val}), stop:1 rgba(15, 15, 18, {self.opacity_val}))"
            border_color = "rgba(255, 255, 255, 25)"
            ctrl_bg = f"rgba(30, 30, 35, {self.opacity_val})"
            ctrl_text = "#E5E7EB"
            input_frame_bg = f"rgba(12, 12, 16, {self.opacity_val})"
            input_text = "#F3F4F6"
            sidebar_bg = f"rgba(10, 10, 12, {int(self.opacity_val * 0.45)})"
        else:
            bg_gradient = f"qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(250, 250, 250, {self.opacity_val}), stop:1 rgba(240, 240, 243, {self.opacity_val}))"
            border_color = "rgba(0, 0, 0, 20)"
            ctrl_bg = f"rgba(235, 235, 240, {self.opacity_val})"
            ctrl_text = "#1F2937"
            input_frame_bg = f"rgba(255, 255, 255, {self.opacity_val})"
            input_text = "#111827"
            sidebar_bg = f"rgba(243, 244, 246, {int(self.opacity_val * 0.45)})"

        # Dynamic highlights: Purple for Command Mode, Green for Ghost Typing
        if getattr(self, 'leader_active', False):
            input_frame_border = "1.5px solid rgba(139, 92, 246, 220)"
            input_frame_bg = f"rgba(139, 92, 246, {int(self.opacity_val * 0.18)})"
        elif getattr(self, 'ghost_active', False):
            input_frame_border = "1.5px solid rgba(16, 185, 129, 200)"
            input_frame_bg = f"rgba(16, 185, 129, {int(self.opacity_val * 0.15)})"
        else:
            input_frame_border = f"1px solid {border_color}"

        border_width = "2px" if getattr(self, 'interview_mode', False) else "1px"
        if getattr(self, 'interview_mode', False):
            border_color = getattr(self, 'interview_border_color', "rgb(236, 72, 153)")

        provider_names = {"gemini": "Gemini", "groq": "Groq", "openrouter": "OpenRouter", "nvidia": "NVIDIA"}
        disp_name = provider_names.get(self.active_provider, self.active_provider.capitalize())
        
        if getattr(self, 'ghost_active', False):
            placeholder = "[Stealth Ghost Typing ACTIVE... Enter: Send, Esc: Exit]" 
        else:
            placeholder = f"Ask {disp_name}... (Alt+Z then: K=Type | P=Model | S=Scan | I=Inject | U=Voice Input | M=Live Voice | L=Live Interview | V=Speaker)"
        self.chat_input.setPlaceholderText(placeholder)

        tooltip_bg = "#2a1221" if self.is_dark else "#fdf2f8"
        tooltip_fg = "#fbcfe8" if self.is_dark else "#831843"
        tooltip_border = "#ec4899"
        
        # Master Global Application Stylesheet
        self.setStyleSheet(f"""
            QToolTip {{
                background-color: {tooltip_bg};
                color: {tooltip_fg};
                border: 1px solid {tooltip_border};
                border-radius: 6px;
                padding: 5px 8px;
                font-family: "Segoe UI", sans-serif;
                font-size: 11px;
            }}
            QFrame#overlay {{
                background-color: transparent;
                background: {"transparent" if getattr(self, 'is_hidden', False) else bg_gradient};
                border: {"none" if getattr(self, 'is_hidden', False) else f"{border_width} solid {border_color}"};
                border-radius: 16px;
            }}
            QScrollBar:vertical {{
                border: none;
                background: rgba(150, 150, 150, 40);
                width: 4px;
                border-radius: 2px;
                margin: 0px 0px 0px 0px;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(139, 92, 246, 200);
                border-radius: 2px;
                min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                border: none;
                background: none;
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
            QSlider::groove:horizontal {{
                background: rgba(150, 150, 150, 50);
                height: 4px;
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: #8b5cf6;
                width: 16px;
                margin-top: -6px;
                margin-bottom: -6px;
                border-radius: 8px;
            }}
            QSlider::sub-page:horizontal {{
                background: #7c3aed;
                border-radius: 2px;
            }}
            QTextEdit#chat_history {{
                background-color: transparent;
                color: {input_text};
                border: none;
            }}
            #chat_history QScrollBar:vertical {{
                background: rgba(15, 10, 25, 45);
                width: 6px;
                border-radius: 3px;
            }}
            #chat_history QScrollBar::handle:vertical {{
                background: rgba(139, 92, 246, 170);
                border-radius: 3px;
                min-height: 20px;
            }}
            #chat_history QScrollBar::handle:vertical:hover {{
                background: rgba(139, 92, 246, 245);
            }}
            #chat_history QScrollBar::add-line:vertical, #chat_history QScrollBar::sub-line:vertical {{
                height: 0px;
                border: none;
                background: none;
            }}
            #chat_history QScrollBar::add-page:vertical, #chat_history QScrollBar::sub-page:vertical {{
                background: none;
            }}
            QFrame#controls {{
                background-color: {ctrl_bg};
                border-bottom: 1px solid {border_color};
                border-top-left-radius: 15px;
                border-top-right-radius: 15px;
            }}
            #controls QPushButton {{
                background-color: rgba(139, 92, 246, 20);
                color: {ctrl_text};
                border-radius: 8px;
                padding: 4px 14px;
                font-family: "Segoe UI", sans-serif;
                font-size: 11px;
                font-weight: 600;
                border: 1px solid rgba(139, 92, 246, 30);
            }}
            #controls QPushButton:hover {{
                background-color: rgba(139, 92, 246, 60);
                border: 1px solid rgba(139, 92, 246, 100);
            }}
            #controls QLineEdit {{
                background-color: rgba(0, 0, 0, 40);
                color: {ctrl_text};
                border: 1px solid {border_color};
                border-radius: 8px;
                padding: 6px;
                font-family: "Segoe UI", sans-serif;
            }}
            #controls QLabel {{
                color: {ctrl_text};
                font-weight: bold;
                font-family: "Segoe UI", sans-serif;
                background: transparent;
            }}
            QFrame#input_frame {{
                background-color: {input_frame_bg};
                border-radius: 20px;
                border: {input_frame_border};
            }}
            QLineEdit#chat_input {{
                background-color: transparent;
                border: none;
                color: {input_text};
                font-family: "Segoe UI", sans-serif;
                font-size: 14px;
            }}
            QComboBox#provider_combo {{
                background-color: rgba(139, 92, 246, 15);
                color: #a0a0a0;
                border: 1px solid rgba(139, 92, 246, 20);
                font-family: "Segoe UI", sans-serif;
                font-weight: 600;
                padding: 4px 18px;
                border-radius: 12px;
            }}
            QComboBox#provider_combo:hover {{
                background-color: rgba(139, 92, 246, 40);
                color: {input_text};
                border: 1px solid rgba(139, 92, 246, 60);
            }}
            QComboBox#provider_combo::drop-down {{
                border: none;
            }}
            QPushButton#action_btn {{
                background-color: rgba(139, 92, 246, 15);
                color: #a855f7;
                border: 1px solid rgba(139, 92, 246, 20);
                font-family: "Segoe UI", sans-serif;
                font-weight: 600;
                padding: 4px 14px;
                border-radius: 10px;
                font-size: 11px;
            }}
            QPushButton#action_btn:hover {{
                background-color: rgba(139, 92, 246, 40);
                color: {input_text};
                border: 1px solid rgba(139, 92, 246, 60);
            }}
            QPushButton#icon_btn {{
                background-color: transparent;
                color: {ctrl_text};
                border: none;
                font-weight: bold;
                font-size: 16px;
                padding: 4px 8px;
                border-radius: 4px;
            }}
            QPushButton#icon_btn:hover {{
                background-color: rgba(100, 100, 100, 30);
            }}
            QFrame#sidebar_frame {{
                background-color: {sidebar_bg};
                border-right: 1px solid {border_color};
                border-top-left-radius: 15px;
                border-bottom-left-radius: 15px;
            }}
            QPushButton#new_chat_btn {{
                background-color: rgba(139, 92, 246, 15);
                color: #a855f7;
                border: 1px solid rgba(139, 92, 246, 20);
                border-radius: 12px;
                padding: 10px;
                font-family: "Segoe UI", sans-serif;
                font-size: 13px;
                font-weight: 600;
                margin-bottom: 15px;
            }}
            QPushButton#new_chat_btn:hover {{
                background-color: rgba(139, 92, 246, 40);
                color: {input_text};
                border: 1px solid rgba(139, 92, 246, 60);
            }}
            QListWidget#chat_list {{
                background-color: transparent;
                border: none;
                color: {ctrl_text};
                font-size: 13px;
                font-family: "Segoe UI", sans-serif;
            }}
            QListWidget#chat_list::item {{
                padding: 2px 4px;
                border-radius: 8px;
                margin-bottom: 4px;
                color: {ctrl_text};
                font-family: "Segoe UI", sans-serif;
                border: 1px solid {border_color};
                min-height: 34px;
            }}
            QListWidget#chat_list::item:hover {{
                background-color: rgba(139, 92, 246, 25);
                border: 1px solid rgba(139, 92, 246, 50);
                color: {ctrl_text};
            }}
            QListWidget#chat_list::item:selected {{
                background-color: rgba(139, 92, 246, 50);
                color: {ctrl_text};
                font-weight: bold;
                border: 1px solid rgba(139, 92, 246, 80);
            }}
            QPushButton#danger_btn {{
                background-color: rgba(239, 68, 68, 15);
                color: #f87171;
                border: 1px solid rgba(239, 68, 68, 20);
                border-radius: 10px;
                padding: 4px 14px;
                font-family: "Segoe UI", sans-serif;
                font-size: 11px;
                font-weight: 600;
            }}
            QPushButton#danger_btn:hover {{
                background-color: rgba(239, 68, 68, 40);
                color: {input_text};
                border: 1px solid rgba(239, 68, 68, 60);
            }}
            QPushButton#voice_btn {{
                background-color: transparent;
                border: none;
                font-size: 16px;
                padding: 6px;
                border-radius: 15px;
            }}
            QPushButton#voice_btn:checked {{
                background-color: rgba(139, 92, 246, 30);
            }}
        """)
        self.controls_widget.setStyleSheet("")
        self.input_frame.setStyleSheet("")
        self.chat_history.setStyleSheet("QTextEdit { background-color: transparent; border: none; }")
        # Refresh history widget label colors to match current theme
        if hasattr(self, 'chat_list'):
            text_color = "#E5E7EB" if self.is_dark else "#1F2937"
            for i in range(self.chat_list.count()):
                item = self.chat_list.item(i)
                widget = self.chat_list.itemWidget(item)
                if widget and hasattr(widget, 'label'):
                    widget.label.setStyleSheet(f"color: {text_color}; font-size: 13px; font-weight: 500; background: transparent; border: none;")
        self.update_restore_bubble_style(hovered=False)

    def update_restore_bubble_style(self, hovered=False):
        if not hasattr(self, 'restore_bubble') or not self.restore_bubble:
            return
        
        # Completely transparent background, only border visible. No theme coloring.
        bg = "transparent"
        if hovered:
            border = "1.5px solid rgba(139, 92, 246, 220)"  # Bright active purple border on hover
        else:
            border = "1.2px solid rgba(139, 92, 246, 100)"  # Translucent purple border at rest
            
        edge = getattr(self, 'dock_edge', 'right')
        if edge == 'left':
            corners = "border-top-right-radius: 6px; border-bottom-right-radius: 6px; border-top-left-radius: 0px; border-bottom-left-radius: 0px;"
        elif edge == 'right':
            corners = "border-top-left-radius: 6px; border-bottom-left-radius: 6px; border-top-right-radius: 0px; border-bottom-right-radius: 0px;"
        elif edge == 'top':
            corners = "border-bottom-left-radius: 6px; border-bottom-right-radius: 6px; border-top-left-radius: 0px; border-top-right-radius: 0px;"
        else:
            corners = "border-top-left-radius: 6px; border-top-right-radius: 6px; border-bottom-left-radius: 0px; border-bottom-right-radius: 0px;"

        self.restore_bubble.setStyleSheet(f"""
            QLabel {{
                background-color: {bg};
                background: {bg};
                border: {border};
                {corners}
            }}
        """)

    def set_theme(self, is_dark):
        self.is_dark = is_dark
        self.theme_btn.setText("Light" if is_dark else "Dark")
        self.update_style()
        self.save_settings()
        
        # Re-render chat preserving scroll position to update theme colors
        if getattr(self, 'current_chat_id', None):
            scrollbar = self.chat_history.verticalScrollBar()
            scroll_pos = scrollbar.value()
            self.suppress_scroll = True
            self.load_session(self.current_chat_id)
            self.suppress_scroll = False
            QApplication.processEvents()
            scrollbar.setValue(scroll_pos)
        
    def toggle_theme(self):
        import time
        now = time.time()
        if now - getattr(self, 'last_theme_toggle_time', 0.0) < 0.3:
            return
        self.last_theme_toggle_time = now
        
        self.set_theme(not self.is_dark)
        
    def change_opacity(self, value):
        self.current_alpha = value
        if hasattr(self, 'slider') and self.slider.value() != value:
            self.slider.blockSignals(True)
            self.slider.setValue(value)
            self.slider.blockSignals(False)
        self.opacity_label.setText(f"Alpha: {value}%")
        self.opacity_val = int((value / 100.0) * 255)
        if not getattr(self, 'is_hidden', False): 
            self.update_style()
        else:
            self.update_restore_bubble_style(hovered=False)
        self.save_settings()
        
        # Debounce the heavy chat re-rendering
        if getattr(self, 'current_chat_id', None):
            if hasattr(self, 'alpha_timer'):
                self.alpha_timer.stop()
            else:
                self.alpha_timer = QTimer(self)
                self.alpha_timer.setSingleShot(True)
                self.alpha_timer.timeout.connect(self.delayed_alpha_render)
            self.alpha_timer.start(150)
            
    def show_scroll_cursor(self, pos):
        if hasattr(self, 'scroll_cursor_label'):
            self.scroll_cursor_label.move(pos.x() + 12, pos.y() - 12)
            self.scroll_cursor_label.show()
            self.scroll_cursor_label.raise_()
            if hasattr(self, 'cursor_hide_timer'):
                self.cursor_hide_timer.stop()
            else:
                self.cursor_hide_timer = QTimer(self)
                self.cursor_hide_timer.setSingleShot(True)
                self.cursor_hide_timer.timeout.connect(self.scroll_cursor_label.hide)
            self.cursor_hide_timer.start(500)
            
    def delayed_alpha_render(self):
        if getattr(self, 'current_chat_id', None):
            scrollbar = self.chat_history.verticalScrollBar()
            scroll_pos = scrollbar.value()
            self.suppress_scroll = True
            self.load_session(self.current_chat_id)
            self.suppress_scroll = False
            QApplication.processEvents()
            scrollbar.setValue(scroll_pos)
            
    def scroll_chat(self, delta):
        if hasattr(self, 'chat_history'):
            scrollbar = self.chat_history.verticalScrollBar()
            # Increase sensitivity by using a multiplier of 8 (was 3)
            steps = int(delta / 120) * 8
            scrollbar.setValue(scrollbar.value() - (steps * scrollbar.singleStep()))

if __name__ == "__main__":
    try:
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        app = QApplication(sys.argv)
        overlay = TransparentOverlay()
        overlay.show()
        app_filter = AppEventFilter(overlay)
        app.installEventFilter(app_filter)
        sys.exit(app.exec_())
    except Exception as e:
        import traceback
        with open("crash_log.txt", "w") as f:
            traceback.print_exc(file=f)
        sys.exit(1)
