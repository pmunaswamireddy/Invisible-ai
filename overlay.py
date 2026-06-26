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
import signal
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QTextEdit, QTextBrowser, QPushButton, QSlider, QLabel, QHBoxLayout, QFrame, QLineEdit, QComboBox, QSizePolicy, QListWidget, QListWidgetItem
from PyQt5.QtCore import Qt, QPoint, QEvent, QObject, QTimer, pyqtSignal, QAbstractNativeEventFilter, QThread
from PyQt5.QtGui import QColor, QPainter, QPen, QCursor, QMouseEvent, QPixmap

try:
    import mss
    import mss.tools
    HAS_MSS = True
except ImportError:
    HAS_MSS = False

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

def stealth_type_text(text):
    KEYEVENTF_UNICODE = 0x0004
    KEYEVENTF_KEYUP = 0x0002
    INPUT_KEYBOARD = 1
    
    user32 = ctypes.windll.user32
    
    def press_key(vk, is_down):
        extra = ctypes.c_ulong(0)
        ii = Input_I()
        flags = 0 if is_down else KEYEVENTF_KEYUP
        ii.ki = KeyBdInput(vk, 0, flags, 0, ctypes.pointer(extra))
        x = Input(ctypes.c_ulong(INPUT_KEYBOARD), ii)
        user32.SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))
        time.sleep(0.01)

    VK_MENU = 0x12 
    VK_TAB = 0x09  
    press_key(VK_MENU, True)
    press_key(VK_TAB, True)
    press_key(VK_TAB, False)
    press_key(VK_MENU, False)
    
    time.sleep(0.3)
    
    for char in text:
        if char == '\n':
            VK_RETURN = 0x0D
            press_key(VK_RETURN, True)
            press_key(VK_RETURN, False)
            time.sleep(0.05)
            
            unicode_val = ord(' ')
            extra = ctypes.c_ulong(0)
            ii_ = Input_I()
            ii_.ki = KeyBdInput(0, unicode_val, KEYEVENTF_UNICODE, 0, ctypes.pointer(extra))
            x_down = Input(ctypes.c_ulong(INPUT_KEYBOARD), ii_)
            ctypes.windll.user32.SendInput(1, ctypes.pointer(x_down), ctypes.sizeof(x_down))
            
            ii_.ki = KeyBdInput(0, unicode_val, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, ctypes.pointer(extra))
            x_up = Input(ctypes.c_ulong(INPUT_KEYBOARD), ii_)
            ctypes.windll.user32.SendInput(1, ctypes.pointer(x_up), ctypes.sizeof(x_up))
            time.sleep(0.01)
            
            VK_SHIFT = 0x10
            VK_HOME = 0x24
            VK_BACK = 0x08
            
            press_key(VK_SHIFT, True)
            press_key(VK_HOME, True)
            press_key(VK_HOME, False)
            press_key(VK_HOME, True)
            press_key(VK_HOME, False)
            press_key(VK_SHIFT, False)
            time.sleep(0.01)
            
            press_key(VK_BACK, True)
            press_key(VK_BACK, False)
            time.sleep(0.015)
        else:
            unicode_val = ord(char)
            extra = ctypes.c_ulong(0)
            ii_ = Input_I()
            ii_.ki = KeyBdInput(0, unicode_val, KEYEVENTF_UNICODE, 0, ctypes.pointer(extra))
            x_down = Input(ctypes.c_ulong(INPUT_KEYBOARD), ii_)
            ctypes.windll.user32.SendInput(1, ctypes.pointer(x_down), ctypes.sizeof(x_down))
            
            time.sleep(0.005)
            
            ii_.ki = KeyBdInput(0, unicode_val, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, ctypes.pointer(extra))
            x_up = Input(ctypes.c_ulong(INPUT_KEYBOARD), ii_)
            ctypes.windll.user32.SendInput(1, ctypes.pointer(x_up), ctypes.sizeof(x_up))
            time.sleep(0.015)

class WinHotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, overlay):
        super().__init__()
        self.overlay = overlay
        
    def nativeEventFilter(self, eventType, message):
        if eventType == b"windows_generic_MSG" or eventType == b"windows_dispatcher_MSG":
            msg = ctypes.wintypes.MSG.from_address(message.__int__())
            if msg.message == 0x0312:
                if msg.wParam == 1:
                    self.overlay.hotkey_signal.emit()
                    return True, 0
        return False, 0

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
        
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_mouse_state)
        self.timer.start(20)

    def check_mouse_state(self):
        global_pos = QCursor.pos()
        local_pos = self.overlay.mapFromGlobal(global_pos)
        
        is_hidden = getattr(self.overlay, 'is_hidden', False)
        
        in_control_panel = self.overlay.controls_widget.isVisible() and self.overlay.controls_widget.geometry().contains(local_pos)
        in_bubble = is_hidden and getattr(self.overlay, 'restore_bubble', None) and self.overlay.restore_bubble.geometry().contains(local_pos)
        in_input_frame = getattr(self.overlay, 'input_frame', None) and self.overlay.input_frame.isVisible() and self.overlay.input_frame.geometry().contains(local_pos)
        
        edges = self.get_resize_edges(global_pos)
        in_resize_border = (edges != 0) and not is_hidden
        
        focus_mode = getattr(self.overlay, 'focus_mode', 'Background')
        
        interacting_with_overlay = in_control_panel or in_bubble or in_resize_border or in_input_frame
        should_be_transparent = not interacting_with_overlay and focus_mode == 'Background'
        
        if not self.overlay.geometry().contains(global_pos):
            should_be_transparent = False
            
        hwnd = int(self.overlay.winId())
        user32 = ctypes.windll.user32
        GWL_EXSTYLE = -20
        WS_EX_TRANSPARENT = 0x00000020
        ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        
        is_transparent = bool(ex_style & WS_EX_TRANSPARENT)
        
        if should_be_transparent and not is_transparent:
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style | WS_EX_TRANSPARENT)
        elif not should_be_transparent and is_transparent:
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style & ~WS_EX_TRANSPARENT)

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

    def do_resize(self, global_pos):
        dx = global_pos.x() - self.start_mouse_pos.x()
        dy = global_pos.y() - self.start_mouse_pos.y()
        rect = self.start_geometry
        x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
        
        if self.resize_edges & 1: x += dx; w -= dx
        elif self.resize_edges & 2: w += dx
        if self.resize_edges & 4: y += dy; h -= dy
        elif self.resize_edges & 8: h += dy
            
        if w < 300:
            if self.resize_edges & 1: x -= (300 - w)
            w = 300
        if h < 200:
            if self.resize_edges & 4: y -= (200 - h)
            h = 200
            
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
                    if is_resizing_area: self.update_cursor(edges)
                    else: self.overlay.unsetCursor()
                else:
                    if self.dragging:
                        if is_hidden: self.did_drag_while_hidden = True
                        self.overlay.move(global_pos + self.drag_offset)
                    elif self.resizing:
                        self.do_resize(global_pos)
                        
        return super().eventFilter(obj, event)

class TTSWorker(QThread):
    def __init__(self):
        super().__init__()
        self.q = queue.Queue()
        self.engine_initialized = False
        
    def run(self):
        try:
            import pyttsx3
            engine = pyttsx3.init()
            voices = engine.getProperty('voices')
            for v in voices:
                if "Zira" in v.name or "Female" in v.name:
                    engine.setProperty('voice', v.id)
                    break
            engine.setProperty('rate', 170)
            self.engine_initialized = True
            
            while True:
                text = self.q.get()
                if text is None: break
                
                text_to_speak = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
                text_to_speak = text_to_speak.replace('`', '').replace('*', '').replace('#', '').strip()
                
                if text_to_speak:
                    engine.say(text_to_speak)
                    engine.runAndWait()
        except ImportError:
            print("TTS Module missing (pyttsx3)")
        except Exception as e:
            print("TTS Engine Error:", e)

    def speak(self, text):
        self.q.put(text)
        
    def stop(self):
        self.q.put(None)

class DictationWorker(QThread):
    finished_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str)

    def run(self):
        try:
            import speech_recognition as sr
            r = sr.Recognizer()
            with sr.Microphone() as source:
                self.status_signal.emit("Listening...")
                r.adjust_for_ambient_noise(source, duration=0.5)
                audio = r.listen(source, timeout=5, phrase_time_limit=15)
                
            self.status_signal.emit("Recognizing...")
            text = r.recognize_google(audio)
            self.finished_signal.emit(text)
        except ImportError:
            self.error_signal.emit("Please run: pip install SpeechRecognition pyaudio")
        except Exception as e:
            self.error_signal.emit(f"Mic error: {str(e)}")

class AITaskWorker(QThread):
    finished_signal = pyqtSignal(str, str, str) # type, content, raw_code
    error_signal = pyqtSignal(str)

    def __init__(self, provider, api_keys, task_type, prompt, image_path=None):
        super().__init__()
        self.provider = provider
        self.api_keys = api_keys
        self.task_type = task_type
        self.prompt = prompt
        self.image_path = image_path

    def run(self):
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
                system_prompt = "You are a highly capable AI assistant operating within a stealth overlay. Provide direct, concise answers. If providing code, always wrap it in ``` backticks."
                full_prompt = f"{system_prompt}\n\nUser: {self.prompt}"
                
                text_response = ""
                
                active_provider = "Gemini" if self.task_type == "vision" else self.provider
                
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
                        model = genai.GenerativeModel('gemini-1.5-flash')
                        if self.task_type == "vision" and self.image_path and os.path.exists(self.image_path):
                            img = PIL.Image.open(self.image_path)
                            response = model.generate_content([full_prompt, img])
                        else:
                            response = model.generate_content(full_prompt)
                        text_response = response.text
                    except Exception as ge:
                        if "404" in str(ge):
                            try:
                                available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                                if available_models:
                                    valid_fallback = None
                                    preferred = ["models/gemini-2.0-flash-exp", "models/gemini-1.5-flash", "models/gemini-1.5-pro", "models/gemini-1.0-pro", "models/gemini-pro"]
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
                                        response = model.generate_content([full_prompt, img])
                                    else:
                                        response = model.generate_content(full_prompt)
                                    text_response = response.text
                                else:
                                    raise Exception("No generative models found for this API key.")
                            except Exception as fallback_e:
                                raise Exception(f"Dynamic fallback failed: {fallback_e}. Original error: {ge}")
                        else:
                            raise ge
                    
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
                    client = groq.Groq(api_key=key)
                    chat_completion = client.chat.completions.create(
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": self.prompt}
                        ],
                        model="llama-3.3-70b-versatile",
                    )
                    text_response = chat_completion.choices[0].message.content
                    
                elif active_provider == "OpenRouter":
                    try:
                        import openai
                    except ImportError:
                        self.error_signal.emit("openai is not installed.")
                        return
                        
                    key = self.api_keys.get("openrouter", "")
                    if not key:
                        self.error_signal.emit("OpenRouter API Key is missing.")
                        return
                    client = openai.OpenAI(base_url="https://openrouter.ai/api/v1", api_key=key)
                    
                    try:
                        req = urllib.request.Request("https://openrouter.ai/api/v1/models")
                        with urllib.request.urlopen(req) as response:
                            models_data = json.loads(response.read())
                        free_models = [m['id'] for m in models_data.get('data', []) if str(m.get('pricing', {}).get('prompt')) == "0" and m['id'].endswith(':free')]
                    except Exception:
                        free_models = []
                        
                    if not free_models:
                        free_models = [
                            "meta-llama/llama-3.2-3b-instruct:free",
                            "mistralai/mistral-7b-instruct:free",
                            "google/gemini-2.0-flash-lite-preview-02-05:free"
                        ]
                        
                    completion = None
                    last_err = None
                    for model_id in free_models[:10]:
                        try:
                            completion = client.chat.completions.create(
                                extra_headers={"HTTP-Referer": "https://invisible.ai", "X-Title": "Stealth AI"},
                                model=model_id,
                                messages=[
                                    {"role": "system", "content": system_prompt},
                                    {"role": "user", "content": self.prompt}
                                ]
                            )
                            break
                        except Exception as e:
                            last_err = e
                            continue
                    
                    if not completion:
                        if last_err:
                            raise last_err
                        else:
                            raise Exception("No free models were available to try.")
                        
                    text_response = completion.choices[0].message.content
                
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

class TransparentOverlay(QFrame):
    hotkey_signal = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        
        self.tts_worker = TTSWorker()
        self.tts_worker.start()
            
        self.setWindowTitle("SystemResourceNotifyWindow")
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        try: ctypes.windll.user32.SetWindowDisplayAffinity(int(self.winId()), 0x00000011)
        except Exception: pass
            
        self.setObjectName("overlay")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        settings = self.load_settings()
        self.is_dark = settings.get("is_dark", True)
        self.focus_mode = settings.get("focus_mode", "Background")
        self.dock_edge = settings.get("dock_edge", "right")
        self.opacity_val = int((settings.get("opacity", 90) / 100.0) * 255)
        self.voice_enabled = settings.get("voice_enabled", True)
        
        self.is_hidden = False
        self.normal_geometry = None
        self.last_ai_code = ""
        self.sessions = []
        self.current_chat_id = None
        
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
            "openrouter": os.environ.get("OPENROUTER_API_KEY", "")
        }
        self.api_keys = settings.get("api_keys", default_keys)
        
        if not self.api_keys.get("gemini", "").strip(): self.api_keys["gemini"] = default_keys["gemini"]
        if not self.api_keys.get("groq", "").strip(): self.api_keys["groq"] = default_keys["groq"]
        if not self.api_keys.get("openrouter", "").strip(): self.api_keys["openrouter"] = default_keys["openrouter"]
            
        self.active_provider = settings.get("active_provider", "Gemini")
        
        default_geo = [100, 100, 900, 600]
        geo = settings.get("geometry", default_geo)
        if len(geo) == 4: self.setGeometry(geo[0], geo[1], geo[2], geo[3])
        else: self.setGeometry(*default_geo)
            
        self.hotkey_signal.connect(self.toggle_visibility_from_hotkey)
        ctypes.windll.user32.RegisterHotKey(int(self.winId()), 1, 0x0002 | 0x0004, 0x20) # Ctrl+Shift+Space
        
        # --- TOP CONTROLS ---
        self.controls_widget = QFrame()
        self.controls_widget.setObjectName("controls")
        controls_layout = QVBoxLayout(self.controls_widget)
        controls_layout.setContentsMargins(10, 10, 10, 10)
        
        row1 = QHBoxLayout()
        self.sidebar_btn = QPushButton("☰")
        self.sidebar_btn.setObjectName("icon_btn")
        self.sidebar_btn.clicked.connect(self.toggle_sidebar)
        row1.addWidget(self.sidebar_btn)

        self.drag_handle = QLabel(" ✥ Drag ")
        self.drag_handle.setCursor(Qt.SizeAllCursor)
        row1.addWidget(self.drag_handle)
        
        self.theme_btn = QPushButton("Light" if self.is_dark else "Dark")
        self.theme_btn.clicked.connect(self.toggle_theme)
        row1.addWidget(self.theme_btn)
        
        self.focus_btn = QPushButton(f"Type In: {self.focus_mode}")
        self.focus_btn.clicked.connect(self.toggle_focus_mode)
        row1.addWidget(self.focus_btn)
        
        opacity_percent = settings.get("opacity", 90)
        self.opacity_label = QLabel(f"Alpha: {opacity_percent}%")
        row1.addWidget(self.opacity_label)
        
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(10)
        self.slider.setMaximum(100)
        self.slider.setValue(opacity_percent)
        self.slider.valueChanged.connect(self.change_opacity)
        row1.addWidget(self.slider)
        
        row1.addStretch()
        
        self.clear_btn = QPushButton("🗑️ Clear")
        self.clear_btn.clicked.connect(self.clear_chat)
        row1.addWidget(self.clear_btn)
        
        self.hide_btn = QPushButton("Hide")
        self.hide_btn.clicked.connect(self.minimize_to_edge)
        row1.addWidget(self.hide_btn)
        
        self.close_btn = QPushButton("Exit")
        self.close_btn.clicked.connect(self.force_exit)
        row1.addWidget(self.close_btn)
        
        controls_layout.addLayout(row1)
        
        # Row 2: API Keys
        row2 = QHBoxLayout()
        self.key_gemini = QLineEdit()
        self.key_gemini.setPlaceholderText("Gemini API Key")
        self.key_gemini.setEchoMode(QLineEdit.Password)
        self.key_gemini.setText(self.api_keys.get("gemini", ""))
        self.key_gemini.textChanged.connect(self.save_settings)
        row2.addWidget(self.key_gemini)
        
        self.key_groq = QLineEdit()
        self.key_groq.setPlaceholderText("Groq API Key")
        self.key_groq.setEchoMode(QLineEdit.Password)
        self.key_groq.setText(self.api_keys.get("groq", ""))
        self.key_groq.textChanged.connect(self.save_settings)
        row2.addWidget(self.key_groq)
        
        self.key_or = QLineEdit()
        self.key_or.setPlaceholderText("OpenRouter API Key")
        self.key_or.setEchoMode(QLineEdit.Password)
        self.key_or.setText(self.api_keys.get("openrouter", ""))
        self.key_or.textChanged.connect(self.save_settings)
        row2.addWidget(self.key_or)
        
        controls_layout.addLayout(row2)
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
        
        self.new_chat_btn = QPushButton("➕ New Chat")
        self.new_chat_btn.setObjectName("new_chat_btn")
        self.new_chat_btn.clicked.connect(self.new_chat)
        sidebar_layout.addWidget(self.new_chat_btn)
        
        self.chat_list = QListWidget()
        self.chat_list.setObjectName("chat_list")
        self.chat_list.itemClicked.connect(self.on_chat_selected)
        sidebar_layout.addWidget(self.chat_list)
        
        self.clear_all_btn = QPushButton("🗑️ Clear All History")
        self.clear_all_btn.setObjectName("danger_btn")
        self.clear_all_btn.clicked.connect(self.clear_all_chats)
        sidebar_layout.addWidget(self.clear_all_btn)
        
        self.sidebar_frame.hide()
        content_layout.addWidget(self.sidebar_frame)
        
        # --- CHAT CONTAINER ---
        self.chat_container = QWidget()
        chat_container_layout = QVBoxLayout(self.chat_container)
        chat_container_layout.setContentsMargins(0, 0, 0, 0)
        
        # --- CHAT HISTORY ---
        self.chat_history = QTextBrowser()
        self.chat_history.setObjectName("chat_history")
        self.chat_history.setReadOnly(True) 
        self.chat_history.setViewportMargins(20, 20, 20, 10)
        self.chat_history.setOpenExternalLinks(False)
        self.chat_history.anchorClicked.connect(self.on_chat_link_clicked)
        chat_container_layout.addWidget(self.chat_history)
        
        # --- MODERN BOTTOM INPUT FRAME ---
        self.input_container = QWidget()
        input_container_layout = QVBoxLayout(self.input_container)
        input_container_layout.setContentsMargins(15, 0, 15, 15)
        
        self.input_frame = QFrame()
        self.input_frame.setObjectName("input_frame")
        self.input_layout = QVBoxLayout(self.input_frame)
        self.input_layout.setContentsMargins(15, 15, 15, 10)
        self.input_layout.setSpacing(10)
        
        self.chat_input = QLineEdit()
        self.chat_input.setObjectName("chat_input")
        self.chat_input.setPlaceholderText(f"Ask {self.active_provider} anything, or /imagine...")
        self.chat_input.returnPressed.connect(self.handle_chat)
        self.input_layout.addWidget(self.chat_input)
        
        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(0, 0, 0, 0)
        bottom_row.setSpacing(8)
        
        self.provider_combo = QComboBox()
        self.provider_combo.setObjectName("provider_combo")
        self.provider_combo.addItems(["Gemini", "Groq", "OpenRouter"])
        self.provider_combo.setCurrentText(self.active_provider)
        self.provider_combo.currentTextChanged.connect(self.change_provider)
        bottom_row.addWidget(self.provider_combo)
        
        bottom_row.addStretch()
        
        self.scan_btn = QPushButton("📷 Scan")
        self.scan_btn.setObjectName("action_btn")
        self.scan_btn.setToolTip("Capture screen to Gemini Vision")
        self.scan_btn.clicked.connect(self.scan_screen)
        bottom_row.addWidget(self.scan_btn)
        
        self.inject_btn = QPushButton("⚡ Inject")
        self.inject_btn.setObjectName("action_btn")
        self.inject_btn.setToolTip("Type the generated AI code into the background")
        self.inject_btn.clicked.connect(self.inject_code)
        bottom_row.addWidget(self.inject_btn)
        
        self.voice_btn = QPushButton("🔊" if self.voice_enabled else "🔇")
        self.voice_btn.setObjectName("voice_btn")
        self.voice_btn.setCheckable(True)
        self.voice_btn.setChecked(self.voice_enabled)
        self.voice_btn.clicked.connect(self.toggle_voice)
        bottom_row.addWidget(self.voice_btn)
        
        self.mic_btn = QPushButton("🎤")
        self.mic_btn.setObjectName("action_btn")
        self.mic_btn.setToolTip("Voice Typing")
        self.mic_btn.clicked.connect(self.start_dictation)
        bottom_row.addWidget(self.mic_btn)
        
        self.send_btn = QPushButton("➤")
        self.send_btn.setObjectName("send_btn")
        self.send_btn.clicked.connect(self.handle_chat)
        bottom_row.addWidget(self.send_btn)
        
        self.input_layout.addLayout(bottom_row)
        input_container_layout.addWidget(self.input_frame)
        chat_container_layout.addWidget(self.input_container)
        
        content_layout.addWidget(self.chat_container)
        layout.addLayout(content_layout)
        
        self.restore_bubble = QLabel("", self)
        self.restore_bubble.setAlignment(Qt.AlignCenter)
        self.restore_bubble.hide()
        
        self.setMouseTracking(True)
        self.update_style()
        self.load_chat_history()
        
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

        if not self.sessions:
            self.new_chat()
        else:
            self.refresh_sidebar()
            self.load_session(self.sessions[-1]['id'])

    def refresh_sidebar(self):
        self.chat_list.clear()
        for session in reversed(self.sessions):
            title = session.get('title', 'Untitled')
            # Only add the icon if it doesn't already have one
            display_text = title if title.startswith("💬") else f"💬 {title}"
            item = QListWidgetItem(display_text)
            item.setData(Qt.UserRole, session['id'])
            self.chat_list.addItem(item)

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

    def on_chat_selected(self, item):
        chat_id = item.data(Qt.UserRole)
        self.load_session(chat_id)

    def save_sessions(self):
        try:
            with open(self.get_history_path(), "w", encoding="utf-8") as f:
                json.dump(self.sessions, f, indent=2)
        except Exception as e:
            print("Failed to save history:", e)

    def save_chat_message(self, role, content, provider="System"):
        session = next((s for s in self.sessions if s['id'] == self.current_chat_id), None)
        if not session:
            return
            
        session['messages'].append({"role": role, "content": content, "provider": provider})
        
        if role == 'user' and session['title'].startswith('Chat '):
            title = content[:20] + "..." if len(content) > 20 else content
            session['title'] = title
            self.refresh_sidebar()
            
        self.save_sessions()

    def clear_chat(self):
        self.chat_history.clear()
        session = next((s for s in self.sessions if s['id'] == self.current_chat_id), None)
        if session:
            session['messages'] = []
            self.save_sessions()
        self.add_system_message("Chat history cleared. Layer active. Capture Stealth: ENABLED.", save=False)

    def clear_all_chats(self):
        self.sessions = []
        self.new_chat()
        self.add_system_message("All chat histories have been permanently deleted.", save=False)

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
            
        self.api_keys = {
            "gemini": self.key_gemini.text().strip(),
            "groq": self.key_groq.text().strip(),
            "openrouter": self.key_or.text().strip()
        }
            
        settings = {
            "is_dark": self.is_dark,
            "opacity": self.slider.value(),
            "focus_mode": self.focus_mode,
            "geometry": geo,
            "dock_edge": self.dock_edge,
            "active_provider": self.active_provider,
            "api_keys": self.api_keys,
            "voice_enabled": self.voice_enabled
        }
        try:
            with open(self.get_settings_path(), "w") as f: json.dump(settings, f)
        except Exception as e: print("Failed to save settings:", e)
        
    def toggle_voice(self):
        self.voice_enabled = not self.voice_enabled
        self.voice_btn.setText("🔊" if self.voice_enabled else "🔇")
        self.save_settings()

    def change_provider(self, text):
        self.active_provider = text
        self.chat_input.setPlaceholderText(f"Ask {self.active_provider} anything, or /imagine...")
        self.save_settings()

    def add_user_message(self, text, save=True):
        import html as html_lib
        formatted_text = html_lib.escape(text).replace('\n', '<br>')
        user_bg = "#2f2f2f" if self.is_dark else "#f0f0f0"
        text_color = "#FFFFFF" if self.is_dark else "#000000"
        border_css = "border: 1px solid rgba(255, 255, 255, 40);" if self.is_dark else "border: 1px solid rgba(0, 0, 0, 30);"
        html = f"""
        <div style='text-align: right; margin-bottom: 15px;'>
            <div style='background-color: {user_bg}; color: {text_color}; {border_css} padding: 12px 18px; border-radius: 18px; display: inline-block; max-width: 80%; text-align: left; font-family: "Segoe UI", sans-serif; font-size: 14px;'>
                {formatted_text}
            </div>
        </div>
        """
        self.chat_history.append(html)
        if save:
            self.save_chat_message("user", text)

    def on_chat_link_clicked(self, url):
        url_str = url.toString()
        if url_str.startswith("inject://"):
            import base64
            import threading
            b64_code = url_str.replace("inject://", "")
            try:
                code = base64.b64decode(b64_code).decode('utf-8')
                self.add_system_message(f"Commencing hardware injection ({len(code)} chars)...")
                t = threading.Thread(target=stealth_type_text, args=(code,), daemon=True)
                t.start()
            except Exception as e:
                self.add_system_message(f"Injection failed: {e}")

    def add_ai_message(self, text, provider_name="System", save=True):
        import html as html_lib
        import base64
        code_bg = "#1e1e1e" if self.is_dark else "#e8e8e8"
        
        parts = text.split("```")
        formatted_parts = []
        for i, part in enumerate(parts):
            if i % 2 == 1:
                lines = part.split('\n', 1)
                lang = lines[0] if len(lines) > 1 else ""
                code = lines[1] if len(lines) > 1 else lines[0]
                
                b64_code = base64.b64encode(code.encode('utf-8')).decode('utf-8')
                escaped_code = html_lib.escape(code)
                
                html_code = f'''<div style='background: {code_bg}; padding: 10px; border-radius: 8px; margin: 10px 0;'>
    <table width='100%' style='margin-bottom: 5px;'><tr>
        <td style='color: #888; font-size: 12px; text-align: left;'>{lang}</td>
        <td style='text-align: right;'><a href='inject://{b64_code}' style='color: #4CAF50; text-decoration: none; font-size: 12px; font-weight: bold;'>⚡ Inject</a></td>
    </tr></table>
    <pre style='margin: 0; white-space: pre-wrap; font-family: Consolas, monospace;'>{escaped_code}</pre>
</div>'''
                formatted_parts.append(html_code)
            else:
                escaped_part = html_lib.escape(part).replace('\n', '<br>')
                import re
                escaped_part = re.sub(r"\[IMAGE:\s*(file:///[^\]]+)\]", r"<img src='\1' width='400' style='border-radius: 10px; margin-top: 10px;'/>", escaped_part)
                formatted_parts.append(escaped_part)
                
        formatted_text = "".join(formatted_parts)
        
        ai_bg = "#202020" if self.is_dark else "#ffffff"
        text_color = "#A0AEC0" if self.is_dark else "#4A5568"
        border_css = "border: 1px solid rgba(255, 255, 255, 10);" if self.is_dark else "border: 1px solid rgba(0, 0, 0, 15);"
        icon = "🤖" if provider_name != "System" else "⚙️"
        html = f"""
        <div style='text-align: left; margin-bottom: 20px;'>
            <div style='background-color: {ai_bg}; color: {text_color}; {border_css} padding: 12px 18px; border-radius: 18px; display: inline-block; max-width: 95%; font-family: "Segoe UI", sans-serif; font-size: 14px; line-height: 1.5;'>
                <b style='color: #888888; font-size: 12px;'>{icon} {provider_name}</b><br>
                {formatted_text}
            </div>
        </div>
        """
        self.chat_history.append(html)
        if save:
            self.save_chat_message("ai", text, provider_name)

    def add_system_message(self, text, save=True):
        self.chat_history.append(f"<div style='text-align: center; color: #888; font-size: 12px; margin-bottom: 15px;'><i>{text}</i></div>")
        if save:
            self.save_chat_message("system", text)
            
    def start_dictation(self):
        self.chat_input.setPlaceholderText("Listening...")
        self.mic_btn.setEnabled(False)
        self.dictation_worker = DictationWorker()
        self.dictation_worker.status_signal.connect(lambda s: self.chat_input.setPlaceholderText(s))
        self.dictation_worker.finished_signal.connect(self.on_dictation_finished)
        self.dictation_worker.error_signal.connect(self.on_dictation_error)
        self.dictation_worker.start()

    def on_dictation_finished(self, text):
        self.mic_btn.setEnabled(True)
        current = self.chat_input.text().strip()
        new_text = current + (" " if current else "") + text
        self.chat_input.setText(new_text)
        self.chat_input.setPlaceholderText(f"Ask {self.active_provider} anything, or /imagine...")
        
    def on_dictation_error(self, err):
        self.mic_btn.setEnabled(True)
        self.chat_input.setPlaceholderText(f"Ask {self.active_provider} anything, or /imagine...")
        self.add_system_message(f"<b style='color:red;'>Dictation Failed:</b> {err}")

    def handle_chat(self):
        text = self.chat_input.text().strip()
        if not text: return
        self.chat_input.clear()
        
        self.add_user_message(text)
        
        if text.startswith("/imagine "):
            prompt = text[9:].strip()
            self.add_system_message(f"Generating image for '{prompt}'...")
            self.start_ai_task("imagine", prompt)
        else:
            self.add_system_message("Generating response...")
            self.start_ai_task("text", text)

    def scan_screen(self):
        if not HAS_MSS:
            self.add_system_message("<b style='color:red;'>Missing dependencies. Run pip install mss pillow</b>")
            return
            
        with mss.mss() as sct:
            rect = self.geometry()
            monitor = {"top": rect.y(), "left": rect.x(), "width": rect.width(), "height": rect.height()}
            sct_img = sct.grab(monitor)
            scan_path = os.path.join(get_app_dir(), "scan_result.png")
            mss.tools.to_png(sct_img.rgb, sct_img.size, output=scan_path)
            
        self.add_system_message("Screen captured natively. Analyzing with Gemini Vision...")
        prompt = "Analyze this image and explain what is happening. If there is code, explain it or provide requested solutions."
        self.start_ai_task("vision", prompt, image_path=scan_path)

    def start_ai_task(self, task_type, prompt, image_path=None):
        self.worker = AITaskWorker(self.active_provider, self.api_keys, task_type, prompt, image_path)
        self.worker.finished_signal.connect(self.on_ai_finished)
        self.worker.error_signal.connect(self.on_ai_error)
        self.worker.start()

    def on_ai_finished(self, task_type, content, raw_code):
        if task_type == "text" or task_type == "vision":
            # Remove typing indicator
            html_text = self.chat_history.toHtml()
            import re
            html_text = re.sub(r"<div id='typing_indicator'.*?</div>", "", html_text, flags=re.DOTALL)
            self.chat_history.setHtml(html_text)
            
            provider_name = "Gemini Vision" if task_type == "vision" else self.active_provider
            self.add_ai_message(content, provider_name)
            
            # AUDIO TTS
            if self.voice_enabled:
                self.tts_worker.speak(content)
            
            if raw_code:
                self.last_ai_code = raw_code
                self.add_system_message("Code snippet loaded. Click ⚡ Inject")
                
        elif task_type == "image":
            file_url = f"file:///{content.replace(os.sep, '/')}"
            self.add_ai_message(f"[IMAGE: {file_url}]", "Pollinations")
            
    def on_ai_error(self, error_msg):
        self.add_system_message(f"<b style='color:red;'>Error:</b> {error_msg}")

    def inject_code(self):
        text_to_inject = getattr(self, 'last_ai_code', None)
        if not text_to_inject:
            text_to_inject = (
                "def solve_algorithm(data):\n"
                "    result = []\n"
                "    for item in data:\n"
                "        if item > 0:\n"
                "            result.append(item * 2)\n"
                "    return result\n"
            )
            
        self.add_system_message(f"Commencing hardware injection ({len(text_to_inject)} chars)...")
        t = threading.Thread(target=stealth_type_text, args=(text_to_inject,), daemon=True)
        t.start()

    def toggle_visibility_from_hotkey(self):
        if self.is_hidden: self.restore_from_edge()
        else: self.minimize_to_edge()

    def force_exit(self):
        self.tts_worker.stop()
        self.save_settings()
        QApplication.quit()
        os._exit(0)
        
    def closeEvent(self, event):
        self.force_exit()
        
    def toggle_focus_mode(self):
        if self.focus_mode == 'Background':
            self.focus_mode = 'Overlay'
            self.focus_btn.setText("Type In: Overlay")
            user32 = ctypes.windll.user32
            user32.SetForegroundWindow(int(self.winId()))
        else:
            self.focus_mode = 'Background'
            self.focus_btn.setText("Type In: Background")
        self.save_settings()
            
    def minimize_to_edge(self):
        self.is_hidden = True
        self.normal_geometry = self.geometry()
        self.controls_widget.hide()
        self.chat_history.hide()
        self.input_container.hide()
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
        self.restore_bubble.setStyleSheet("QLabel { background-color: rgba(80, 80, 80, 220); border: 1px solid rgba(255,255,255,80); }")
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

    def restore_from_edge(self):
        self.is_hidden = False
        self.restore_bubble.hide()
        self.controls_widget.show()
        self.chat_history.show()
        self.input_container.show()
        if self.normal_geometry: self.setGeometry(self.normal_geometry)

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
            self.restore_bubble.setStyleSheet("QLabel { background-color: rgba(120, 120, 120, 255); border: 1px solid rgba(255,255,255,150); }")
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
        bg_r, bg_g, bg_b = (20, 20, 20) if self.is_dark else (255, 255, 255)
        text_color = "white" if self.is_dark else "black"
        ctrl_bg = f"rgba(40, 40, 40, {self.opacity_val})" if self.is_dark else f"rgba(220, 220, 220, {self.opacity_val})"
        ctrl_text = "white" if self.is_dark else "black"
        
        self.setStyleSheet(f"""
            QFrame#overlay {{ background-color: rgba({bg_r}, {bg_g}, {bg_b}, {self.opacity_val}); border-radius: 12px; }}
            QTextEdit#chat_history {{ background-color: transparent; border: none; }}
        """)
        
        self.controls_widget.setStyleSheet(f"""
            QFrame#controls {{ background-color: {ctrl_bg}; border-bottom: 1px solid rgba(128, 128, 128, 50); }}
            QPushButton {{ background-color: rgba(100, 100, 100, 30); color: {ctrl_text}; border-radius: 6px; padding: 6px 12px; font-weight: 500; border: 1px solid rgba(150, 150, 150, 30); }}
            QPushButton:hover {{ background-color: rgba(130, 130, 130, 60); border: 1px solid rgba(150, 150, 150, 80); }}
            QLineEdit {{ background-color: rgba(0, 0, 0, 40); color: {ctrl_text}; border: 1px solid rgba(150, 150, 150, 30); border-radius: 6px; padding: 6px; }}
            QLabel {{ color: {ctrl_text}; font-weight: bold; background: transparent; }}
        """)
        
        input_frame_bg = f"rgba(47, 47, 47, {self.opacity_val})" if self.is_dark else f"rgba(244, 244, 244, {self.opacity_val})"
        input_text = "#FFFFFF" if self.is_dark else "#111827"
        
        self.input_frame.setStyleSheet(f"""
            QFrame#input_frame {{
                background-color: {input_frame_bg};
                border-radius: 20px;
                border: 1px solid rgba(128, 128, 128, 30);
            }}
            QLineEdit#chat_input {{
                background-color: transparent;
                border: none;
                color: {input_text};
                font-family: "Segoe UI", sans-serif;
                font-size: 15px;
            }}
            QComboBox#provider_combo {{
                background-color: transparent;
                color: #a0a0a0;
                border: none;
                font-weight: 600;
                padding: 4px 12px;
                border-radius: 12px;
            }}
            QComboBox#provider_combo:hover {{
                background-color: rgba(100, 100, 100, 30);
                color: {input_text};
            }}
            QComboBox#provider_combo::drop-down {{
                border: none;
            }}
            QPushButton#action_btn {{
                background-color: transparent;
                color: #a0a0a0;
                border: none;
                font-weight: 600;
                padding: 6px 14px;
                border-radius: 12px;
            }}
            QPushButton#action_btn:hover {{
                background-color: rgba(100, 100, 100, 30);
                color: {input_text};
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
                background-color: rgba(15, 15, 15, {self.opacity_val});
                border-right: 1px solid rgba(128, 128, 128, 30);
            }}
            QPushButton#new_chat_btn {{
                background-color: rgba(255, 255, 255, 10);
                color: {input_text};
                border: 1px solid rgba(255, 255, 255, 20);
                border-radius: 10px;
                padding: 10px;
                font-size: 14px;
                font-weight: 600;
                margin-bottom: 15px;
            }}
            QPushButton#new_chat_btn:hover {{
                background-color: rgba(255, 255, 255, 20);
            }}
            QListWidget#chat_list {{
                background-color: transparent;
                border: none;
                color: {input_text};
                font-size: 14px;
                font-family: "Segoe UI", sans-serif;
            }}
            QListWidget#chat_list::item {{
                padding: 12px 14px;
                border-radius: 8px;
                margin-bottom: 6px;
                color: #d1d5db;
            }}
            QListWidget#chat_list::item:hover {{
                background-color: rgba(255, 255, 255, 10);
            }}
            QListWidget#chat_list::item:selected {{
                background-color: rgba(255, 255, 255, 20);
                color: #ffffff;
                font-weight: bold;
            }}
            QPushButton#danger_btn {{
                background-color: rgba(255, 50, 50, 30);
                color: #ff6666;
                border: 1px solid rgba(255, 50, 50, 40);
                border-radius: 8px;
                padding: 10px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton#danger_btn:hover {{
                background-color: rgba(255, 50, 50, 60);
            }}
            QScrollBar:vertical {{ 
                background: transparent; 
                width: 8px; 
                margin: 0px; 
            }}
            QScrollBar::handle:vertical {{ 
                background: rgba(120, 120, 120, 120); 
                border-radius: 4px; 
            }}
            QScrollBar::handle:vertical:hover {{ 
                background: rgba(160, 160, 160, 180); 
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ 
                height: 0px; 
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ 
                background: none; 
            }}
            QPushButton#voice_btn {{
                background-color: transparent;
                border: none;
                font-size: 16px;
                padding: 6px;
                border-radius: 15px;
            }}
            QPushButton#voice_btn:checked {{
                background-color: rgba(100, 100, 100, 50);
            }}
            QPushButton#send_btn {{
                background-color: #4a4a4a;
                color: white;
                border: none;
                border-radius: 16px;
                min-width: 32px;
                min-height: 32px;
                max-width: 32px;
                max-height: 32px;
            }}
            QPushButton#send_btn:hover {{
                background-color: #606060;
            }}
        """)
        
        self.chat_history.setStyleSheet(f"QTextEdit {{ background-color: transparent; border: none; }}")

    def set_theme(self, is_dark):
        self.is_dark = is_dark
        self.theme_btn.setText("Light" if is_dark else "Dark")
        self.update_style()
        self.save_settings()
        
    def toggle_theme(self):
        self.set_theme(not self.is_dark)
        
    def change_opacity(self, value):
        self.opacity_label.setText(f"Alpha: {value}%")
        self.opacity_val = int((value / 100.0) * 255)
        if not getattr(self, 'is_hidden', False): self.update_style()
        self.save_settings()

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    app = QApplication(sys.argv)
    overlay = TransparentOverlay()
    hotkey_filter = WinHotkeyFilter(overlay)
    app.installNativeEventFilter(hotkey_filter)
    overlay.show()
    app_filter = AppEventFilter(overlay)
    app.installEventFilter(app_filter)
    sys.exit(app.exec_())
