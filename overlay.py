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
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QTextEdit, QTextBrowser, QPushButton, QSlider, QLabel, QHBoxLayout, QFrame, QLineEdit, QComboBox, QSizePolicy, QListWidget, QListWidgetItem
from PyQt5.QtCore import Qt, QPoint, QEvent, QObject, QTimer, pyqtSignal, QAbstractNativeEventFilter, QThread
from PyQt5.QtGui import QColor, QPainter, QPen, QCursor, QMouseEvent, QPixmap, QPainterPath, QImage

from utils import (get_app_dir, apply_acrylic_blur, translate_vk_to_char,
                   stealth_click, stealth_type_text, KBDLLHOOKSTRUCT, POINT, RECT, MSLLHOOKSTRUCT, HOOKPROC)



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



from PyQt5.QtWidgets import QWidget


from widgets import AudioWaveWidget, SelectionOverlay, ChatHistoryItemWidget
from workers import TTSWorker, DictationWorker, VoiceSetupWorker, SystemAudioWorker, AITaskWorker
from security import check_security

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
    system_audio_signal = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        
        self.hotkey_signal.connect(self.toggle_visibility_from_hotkey)
        self.scan_hotkey_signal.connect(self.scan_screen)
        self.inject_hotkey_signal.connect(self.inject_code)
        self.inject_indexed_hotkey_signal.connect(self.inject_code)
        self.send_hotkey_signal.connect(self.handle_chat)
        self.focus_hotkey_signal.connect(self.toggle_focus_mode)
        self.clear_hotkey_signal.connect(self.clear_chat)
        self.system_audio_signal.connect(self.toggle_system_audio_recording)
        
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
        self.user_tier = settings.get("tier", "Free")
        self.focus_mode = settings.get("focus_mode", "Background")
        if self.user_tier not in ["Pro", "Ultra"] and self.focus_mode == "Background":
            self.focus_mode = "Overlay"
            
        # Anti-Tampering Check on Startup
        self.security_timer = QTimer(self)
        self.security_timer.timeout.connect(check_security)
        self.security_timer.start(5000) # Check every 5 seconds
        check_security()
            
        self.dock_edge = settings.get("dock_edge", "right")
        self.opacity_val = int((settings.get("opacity", 90) / 100.0) * 255)
        self.voice_enabled = settings.get("voice_enabled", True)
            
        self.setWindowTitle("SystemResourceNotifyWindow")
        
        flags = Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool
        if self.focus_mode == 'Background':
            flags |= Qt.WindowDoesNotAcceptFocus
        self.setWindowFlags(flags)
        
        self.setAttribute(Qt.WA_TranslucentBackground)
        apply_acrylic_blur(self, self.is_dark)
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
        
        # Load Custom API properties and tier
        self.api_keys["custom_api_base"] = settings.get("custom_api_base", "")
        self.api_keys["custom_api_key"] = settings.get("custom_api_key", "")
        self.api_keys["custom_api_model"] = settings.get("custom_api_model", "")
        self.user_tier = settings.get("tier", "Free")
            
        self.active_provider = settings.get("active_provider", "Gemini")
        
        default_geo = [100, 100, 900, 600]
        geo = settings.get("geometry", default_geo)
        if len(geo) == 4: self.setGeometry(geo[0], geo[1], geo[2], geo[3])
        else: self.setGeometry(*default_geo)
            
        self.hotkey_signal.connect(self.toggle_visibility_from_hotkey)
        
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
        self.theme_btn.setToolTip("Toggle Light/Dark Theme (Hotkey: Alt+Z then T)")
        self.theme_btn.clicked.connect(self.toggle_theme)
        row1.addWidget(self.theme_btn)
        
        self.focus_btn = QPushButton(f"Type In: {self.focus_mode}")
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
        self.slider.valueChanged.connect(self.change_opacity)
        row1.addWidget(self.slider)
        
        row1.addStretch()
        
        self.clear_btn = QPushButton("🗑️ Clear")
        self.clear_btn.setToolTip("Clear current chat history (Hotkey: Alt+Z then C)")
        self.clear_btn.clicked.connect(self.clear_chat)
        row1.addWidget(self.clear_btn)
        
        self.hide_btn = QPushButton("Hide")
        self.hide_btn.setToolTip("Minimize overlay to edge (Hotkey: Alt+Z then Space or Alt+Z then H)")
        self.hide_btn.clicked.connect(self.minimize_to_edge)
        row1.addWidget(self.hide_btn)
        
        self.close_btn = QPushButton("Exit")
        self.close_btn.setToolTip("Exit application (Hotkey: Alt+Z then X)")
        self.close_btn.clicked.connect(self.force_exit)
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
        self.chat_history.setOpenLinks(False)
        self.chat_history.anchorClicked.connect(self.on_chat_link_clicked)
        self.chat_history.installEventFilter(self)
        chat_container_layout.addWidget(self.chat_history)
        
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
        self.provider_combo.addItems(["Gemini", "Groq", "OpenRouter", "Custom API", "Google Web Search"])
        self.provider_combo.setCurrentText(self.active_provider)
        self.provider_combo.setToolTip("Select active AI Provider (Hotkey: Alt+Z then P to rotate)")
        self.provider_combo.currentTextChanged.connect(self.change_provider)
        bottom_row.addWidget(self.provider_combo)
        
        bottom_row.addStretch()
        
        self.scan_btn = QPushButton("📷 Scan")
        self.scan_btn.setObjectName("action_btn")
        self.scan_btn.setToolTip("Capture screen to Gemini Vision (Hotkey: Alt+Z then S)")
        self.scan_btn.clicked.connect(lambda: self.trigger_with_bg_click(self.scan_screen))
        bottom_row.addWidget(self.scan_btn)
        
        self.inject_btn = QPushButton("⚡ Inject")
        self.inject_btn.setObjectName("action_btn")
        self.inject_btn.setToolTip("Type generated code into active window (Hotkey: Alt+Z then I for latest | Alt+Z then 1..9 for indexed blocks)")
        self.inject_btn.clicked.connect(lambda: self.trigger_with_bg_click(self.inject_code))
        bottom_row.addWidget(self.inject_btn)
        
        self.voice_btn = QPushButton("🔊" if self.voice_enabled else "🔇")
        self.voice_btn.setObjectName("voice_btn")
        self.voice_btn.setCheckable(True)
        self.voice_btn.setChecked(self.voice_enabled)
        self.voice_btn.setToolTip("Toggle TTS Voice Readback (Hotkey: Alt+Z then V)")
        self.voice_btn.clicked.connect(self.toggle_voice)
        bottom_row.addWidget(self.voice_btn)
        
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
        
        self.single_mic_btn = QPushButton("🎤")
        self.single_mic_btn.setObjectName("action_btn")
        self.single_mic_btn.setToolTip("Single Voice Input (Types into chat box) (Hotkey: Alt+Z then U)")
        self.single_mic_btn.clicked.connect(self.start_single_voice)
        bottom_row.addWidget(self.single_mic_btn)
        
        self.mic_btn = QPushButton("🎙️")
        self.mic_btn.setObjectName("action_btn")
        self.mic_btn.setCheckable(True)
        self.mic_btn.setToolTip("Continuous Live Voice Chat (Hotkey: Alt+Z then M)")
        self.mic_btn.clicked.connect(self.toggle_continuous_voice)
        bottom_row.addWidget(self.mic_btn)
        
        self.loopback_btn = QPushButton("🔊")
        self.loopback_btn.setObjectName("action_btn")
        self.loopback_btn.setToolTip("Capture System Audio / Meetings (Hotkey: Alt+Z then A)")
        self.loopback_btn.clicked.connect(self.toggle_system_audio_recording)
        bottom_row.addWidget(self.loopback_btn)
        
        self.wave_widget = AudioWaveWidget()
        self.wave_widget.hide()
        bottom_row.addWidget(self.wave_widget)
        
        self.send_btn = QPushButton("➤")
        self.send_btn.setObjectName("send_btn")
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
        
        self.setMouseTracking(True)
        
        for widget in [self.theme_btn, self.focus_btn, self.clear_btn, self.hide_btn, self.close_btn,
                       self.provider_combo, self.scan_btn, self.inject_btn, self.voice_btn,
                       self.single_mic_btn, self.mic_btn, self.loopback_btn, self.send_btn, self.new_chat_btn, self.clear_all_btn]:
            widget.installEventFilter(self)
            
        self.update_style()
        self.load_chat_history()
        self.install_keyboard_hook()
        
        self.setAcceptDrops(True)
        self.attached_files = []
        self.system_audio_worker = None
        
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            
    def dropEvent(self, event):
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if os.path.exists(file_path):
                ext = os.path.splitext(file_path)[1].lower()
                allowed_exts = ['.txt', '.py', '.js', '.ts', '.html', '.css', '.json', '.c', '.cpp', '.h', '.java', '.go', '.rs', '.md', '.bat', '.sh']
                if ext in allowed_exts:
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                        filename = os.path.basename(file_path)
                        self.attached_files.append({"name": filename, "content": content})
                        size_kb = len(content.encode('utf-8')) / 1024.0
                        self.add_system_message(f"📎 Attached file: <b>{filename}</b> ({size_kb:.1f} KB)")
                    except Exception as e:
                        self.add_system_message(f"❌ Failed to attach file: {str(e)}")
                else:
                    self.add_system_message("⚠️ Unsupported file type. Only text/code files can be attached.")

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
        self.last_ai_codes = []
        self.last_ai_code = ""
        session = next((s for s in self.sessions if s['id'] == self.current_chat_id), None)
        if session:
            session['messages'] = []
            self.save_sessions()
        self.add_system_message("Chat history cleared. Layer active. Capture Stealth: ENABLED.", save=False)

    def clear_all_chats(self):
        self.sessions = []
        self.last_ai_codes = []
        self.last_ai_code = ""
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
            
        settings = {
            "is_dark": self.is_dark,
            "opacity": self.slider.value(),
            "focus_mode": self.focus_mode,
            "geometry": geo,
            "dock_edge": self.dock_edge,
            "active_provider": self.active_provider,
            "api_keys": self.api_keys,
            "voice_enabled": self.voice_enabled,
            "custom_api_base": self.api_keys.get("custom_api_base", ""),
            "custom_api_key": self.api_keys.get("custom_api_key", ""),
            "custom_api_model": self.api_keys.get("custom_api_model", ""),
            "tier": getattr(self, "user_tier", "Free")
        }
        try:
            with open(self.get_settings_path(), "w") as f: json.dump(settings, f)
        except Exception as e: print("Failed to save settings:", e)
        
    def toggle_voice(self):
        self.voice_enabled = not self.voice_enabled
        self.voice_btn.setText("🔊" if self.voice_enabled else "🔇")
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
        if text == "Custom API" and getattr(self, 'user_tier', 'Free') not in ["Pro", "Ultra"]:
            self.add_system_message("🔒 Upgrade Required: <b>Custom API Integration</b> is a Pro/Ultra feature. Please upgrade in the Manager Panel.")
            QTimer.singleShot(0, lambda: self.provider_combo.setCurrentText("Gemini"))
            return
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
            
        alpha = self.slider.value() / 100.0 if hasattr(self, 'slider') else 0.9
            
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
                    <table style="background-color: {user_bg}; border: 1px solid {border_color};" cellpadding="0" cellspacing="0">
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
        self.scroll_to_bottom()

    def scroll_to_bottom(self):
        if getattr(self, 'suppress_scroll', False):
            return
        QApplication.processEvents()
        scrollbar = self.chat_history.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

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
        
        alpha = self.slider.value() / 100.0 if hasattr(self, 'slider') else 0.9
        
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
                    <table style="background-color: {ai_bg}; border: 1px solid {border_color};" cellpadding="0" cellspacing="0">
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
        self.scroll_to_bottom()

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
        self.scroll_to_bottom()
        
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
                self.slider.setValue(val)
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
        self.scroll_to_bottom()

    def animate_typing(self):
        self.typing_dots = (self.typing_dots + 1) % 4
        dots_str = "." * self.typing_dots
        self.typing_label.setText(f"⚡ AI is compiling response{dots_str}")

    def handle_chat(self, voice_input=False):
        text = self.chat_input.text().strip()
        if not text: return
        self.chat_input.clear()
        
        if getattr(self, 'ghost_active', False):
            self.ghost_typing_signal.emit(False)
            
        display_text = f"🎤 {text}" if voice_input else text
        self.add_user_message(display_text)
        
        if text.startswith("/imagine "):
            prompt = text[9:].strip()
            self.add_system_message(f"Generating image for '{prompt}'...")
            self.start_ai_task("imagine", prompt)
        else:
            self.typing_dots = 0
            self.typing_label.setText("⚡ AI is compiling response")
            self.typing_label.show()
            self.typing_timer.start(400)
            self.start_ai_task("text", text)

    def scan_screen(self):
        scan_method = getattr(self, 'settings', {}).get("scan_method", "Overlay Bounds")
        
        if scan_method == "Selection":
            self.hide()
            # Give OS half a second to complete hide animation to avoid rendering the overlay
            QTimer.singleShot(150, self.launch_selection_cropper)
        else:
            self.run_bounds_scan()
            
    def launch_selection_cropper(self):
        self.selection_overlay = SelectionOverlay()
        self.selection_overlay.finished_signal.connect(self.on_selection_scan_completed)
        # Re-display the overlay when selection overlay closes
        self.selection_overlay.destroyed.connect(self.show)
        
    def run_bounds_scan(self):
        try:
            import mss
            import mss.tools
            with mss.mss() as sct:
                rect = self.geometry()
                monitor = {"top": rect.y(), "left": rect.x(), "width": rect.width(), "height": rect.height()}
                sct_img = sct.grab(monitor)
                scan_path = os.path.join(get_app_dir(), "scan_result.png")
                mss.tools.to_png(sct_img.rgb, sct_img.size, output=scan_path)
        except ImportError:
            self.add_system_message("<b style='color:red;'>Missing dependencies. Run pip install mss pillow</b>")
            self.show()
            return
        except Exception as e:
            self.add_system_message(f"Screen capture failed: {str(e)}")
            self.show()
            return
            
        self.process_vision_scan(scan_path)
        
    def on_selection_scan_completed(self, scan_path):
        self.show()
        self.process_vision_scan(scan_path)
        
    def process_vision_scan(self, scan_path):
        text = self.chat_input.text().strip()
        self.chat_input.clear()
        
        default_prompt = (
            "Extract all text from this image and display it neatly in a markdown block. "
            "Then, if there are any questions, tests, or actionable tasks found within the text, "
            "immediately provide the correct, direct answers below it. If there is code, solve it."
        )
        prompt = text if text else default_prompt
        
        if text:
            self.add_user_message(text)
            
        self.typing_dots = 0
        self.typing_label.setText("⚡ AI is compiling response")
        self.typing_label.show()
        self.typing_timer.start(400)
        self.start_ai_task("vision", prompt, image_path=scan_path)

    def start_ai_task(self, task_type, prompt, image_path=None):
        session = next((s for s in self.sessions if s['id'] == self.current_chat_id), None)
        history = session['messages'] if session else []
        
        # Load active system prompt
        prompts = getattr(self, 'settings', {}).get("prompts", [])
        active_name = getattr(self, 'settings', {}).get("active_prompt", "")
        system_prompt = (
            "You are a highly capable AI assistant operating within a stealth overlay. Provide direct, concise answers. "
            "If providing code, always wrap it in ``` backticks. You have access to the user's Chat History. "
            "Use context intelligently: if the user's request is a continuation, reference past history. "
            "If they change the subject or upload a completely new image, treat it as a new context while retaining general memory."
        )
        for p in prompts:
            if p["name"] == active_name:
                system_prompt = p["content"]
                break
                
        # Enforce response length and language constraints
        response_length = getattr(self, 'settings', {}).get("response_length", "Medium")
        response_language = getattr(self, 'settings', {}).get("response_language", "English")
        
        constraints = f"\n\n[Formatting Constraints]\n- Response Length: Provide a {response_length.lower()} response."
        if response_language and response_language != "English":
            constraints += f"\n- Response Language: Write the entire response in {response_language}."
            
        system_prompt = f"{system_prompt}{constraints}"
                
        # Append file attachments if any
        if getattr(self, 'attached_files', []) and task_type in ["text", "vision"]:
            attachments = "\n\n--- Attached Files ---"
            for f in self.attached_files:
                attachments += f"\n\n[File Name: {f['name']}]\n{f['content']}"
            prompt = f"{prompt}{attachments}"
            self.attached_files = [] # Clear attachments queue
            
        self.worker = AITaskWorker(self.active_provider, self.api_keys, task_type, prompt, history, image_path, system_prompt)
        self.worker.finished_signal.connect(self.on_ai_finished)
        self.worker.error_signal.connect(self.on_ai_error)
        self.worker.start()

    def on_ai_finished(self, task_type, content, raw_code):
        self.typing_timer.stop()
        self.typing_label.hide()
        self.typing_label.setText("")
        
        if task_type == "text" or task_type == "vision":
            provider_name = "Gemini Vision" if task_type == "vision" else self.active_provider
            self.add_ai_message(content, provider_name)
            
            if self.voice_enabled:
                self.tts_worker.speak(content)
            
            if raw_code:
                self.last_ai_code = raw_code
                self.add_system_message("Code snippet loaded. Click ⚡ Inject")
                
        elif task_type == "image":
            file_url = f"file:///{content.replace(os.sep, '/')}"
            self.add_ai_message(f"[IMAGE: {file_url}]", "Pollinations")
            
    def on_ai_error(self, error_msg):
        self.typing_timer.stop()
        self.typing_label.hide()
        self.typing_label.setText("")
        
        self.add_system_message(f"<b style='color:red;'>Error:</b> {error_msg}")

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
        self.add_system_message("🎯 Waiting for you to click on the target text area / editor...")

    def perform_stealth_injection(self, text, switch_focus):
        self.injection_in_progress = True
        self.add_system_message(f"Commencing hardware injection ({len(text)} chars)...")
        
        def run_injection():
            try:
                stealth_type_text(text, switch_focus)
            finally:
                self.injection_in_progress = False
                
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
        if hasattr(self, 'hook_id') and self.hook_id:
            try: ctypes.windll.user32.UnhookWindowsHookEx(self.hook_id)
            except Exception: pass
        if hasattr(self, 'mouse_hook_id') and self.mouse_hook_id:
            try: ctypes.windll.user32.UnhookWindowsHookEx(self.mouse_hook_id)
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
            self.add_system_message("⌨️ GHOST TYPING ACTIVE: Keystrokes will be redirected to the chat input and swallowed from the system. Press Esc or Alt+Z then K to exit.")
        else:
            # Restore WS_EX_NOACTIVATE so overlay goes back to non-intrusive background (no window flash)
            if self.focus_mode == 'Background':
                ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style | WS_EX_NOACTIVATE)
            self.add_system_message("🔒 GHOST TYPING INACTIVE: Keystrokes restored to normal system output.")


    def install_keyboard_hook(self):
        self.ghost_active = False
        self.leader_active = False
        self.waiting_for_inject_click = False
        
        # --- Keyboard Hook ---
        def hook_proc(nCode, wParam, lParam):
            if nCode >= 0:
                if wParam == 0x0100 or wParam == 0x0104: # WM_KEYDOWN or WM_SYSKEYDOWN
                    kbd = KBDLLHOOKSTRUCT.from_address(lParam)
                    if kbd.flags & 0x00000010: # LLKHF_INJECTED
                        return ctypes.windll.user32.CallNextHookEx(self.hook_id, nCode, wParam, lParam)
                        
                    vk = kbd.vkCode
                    
                    ctrl_down = (ctypes.windll.user32.GetKeyState(0x11) & 0x8000) != 0
                    shift_down = (ctypes.windll.user32.GetKeyState(0x10) & 0x8000) != 0
                    alt_down = ((ctypes.windll.user32.GetKeyState(0x12) & 0x8000) != 0) or bool(kbd.flags & 0x20)
                    
                    # 1. Chorded Command Mode check
                    if getattr(self, 'leader_active', False):
                        is_arrow = vk in [0x25, 0x26, 0x27, 0x28]
                        if not is_arrow:
                            self.leader_active = False
                            QTimer.singleShot(0, self.update_style)
                        
                        if vk == 0x1B: # Escape
                            self.waiting_for_inject_click = False
                            self.leader_active = False
                            QTimer.singleShot(0, self.update_style)
                            self.add_system_message("⚙️ Command Mode Deactivated")
                            return 1
                        elif vk == 0x25: # Left Arrow (Move Left)
                            QTimer.singleShot(0, lambda: self.move_by(-20, 0))
                            return 1
                        elif vk == 0x26: # Up Arrow (Move Up)
                            QTimer.singleShot(0, lambda: self.move_by(0, -20))
                            return 1
                        elif vk == 0x27: # Right Arrow (Move Right)
                            QTimer.singleShot(0, lambda: self.move_by(20, 0))
                            return 1
                        elif vk == 0x28: # Down Arrow (Move Down)
                            QTimer.singleShot(0, lambda: self.move_by(0, 20))
                            return 1
                        elif vk == 0x20 or vk == 0x48: # Space or H (Toggle Visibility)
                            self.hotkey_signal.emit()
                            return 1
                        elif vk == 0x53: # S (Scan Screen)
                            self.scan_hotkey_signal.emit()
                            return 1
                        elif vk == 0x49: # I (Inject Latest Code)
                            self.inject_hotkey_signal.emit()
                            return 1
                        elif 0x31 <= vk <= 0x39: # 1 to 9 top row (Indexed Injection)
                            self.inject_indexed_hotkey_signal.emit(vk - 0x30)
                            return 1
                        elif 0x61 <= vk <= 0x69: # 1 to 9 numpad (Indexed Injection)
                            self.inject_indexed_hotkey_signal.emit(vk - 0x60)
                            return 1
                        elif vk == 0x44: # D (Send Chat)
                            self.send_hotkey_signal.emit()
                            return 1
                        elif vk == 0x46: # F (Focus Mode Toggle)
                            self.focus_hotkey_signal.emit()
                            return 1
                        elif vk == 0x43: # C (Clear Chat)
                            self.clear_hotkey_signal.emit()
                            return 1
                        elif vk == 0x50: # P (Rotate Provider/Model)
                            self.rotate_provider_hotkey_signal.emit()
                            return 1
                        elif vk == 0x54: # T (Theme Toggle)
                            self.theme_hotkey_signal.emit()
                            return 1
                        elif vk == 0x58: # X (Exit)
                            self.exit_hotkey_signal.emit()
                            return 1
                        elif vk == 0x4B: # K (Toggle Ghost Typing)
                            self.ghost_typing_signal.emit(not getattr(self, 'ghost_active', False))
                            return 1
                        elif vk == 0x4D: # M (Toggle Continuous Mic)
                            self.mic_btn.click()
                            return 1
                        elif vk == 0x41: # A (Toggle System Audio Loopback)
                            self.system_audio_signal.emit()
                            return 1
                        elif vk == 0x55: # U (Toggle Single Voice Typist)
                            self.single_mic_btn.click()
                            return 1
                        elif vk == 0x56: # V (Toggle Speaker Mute)
                            self.voice_btn.click()
                            return 1
                        elif vk == 0x4F: # O (Rotate Voice Model)
                            QTimer.singleShot(0, self.rotate_voice)
                            return 1
                            
                        return ctypes.windll.user32.CallNextHookEx(self.hook_id, nCode, wParam, lParam)
                    
                    # 2. Toggle Leader Active with Alt + Z
                    if alt_down and vk == 0x5A: # Z
                        self.leader_active = True
                        QTimer.singleShot(0, self.update_style)
                        self.add_system_message("⚡ Command Mode Active (Press Space/H: Hide | S: Scan | I: Inject | 1-9: Indexed | P: Model | O: Voice | U: Voice Typist | M: Live Chat | V: Speaker)")
                        return 1
                        
                    # 3. Normal Ghost typing capture (only when overlay is foreground window)
                    if getattr(self, 'ghost_active', False):
                        # Only capture keystrokes if this overlay is the active foreground window
                        overlay_hwnd = int(self.winId())
                        fg_hwnd = ctypes.windll.user32.GetForegroundWindow()
                        if fg_hwnd == overlay_hwnd:
                            if vk == 0x0D: # Enter
                                self.ghost_enter_signal.emit()
                                return 1
                            elif vk == 0x08: # Backspace
                                self.ghost_backspace_signal.emit()
                                return 1
                            elif vk == 0x1B: # Escape
                                self.ghost_typing_signal.emit(False)
                                return 1
                            elif ctrl_down and vk == 0x56: # Ctrl+V (Paste)
                                try:
                                    clipboard_text = QApplication.clipboard().text()
                                    self.ghost_char_signal.emit(clipboard_text)
                                except: pass
                                return 1
                            else:
                                char = translate_vk_to_char(vk, shift_down)
                                if char is not None:
                                    self.ghost_char_signal.emit(char)
                                    return 1
                        else:
                            # Overlay is not foreground — pass keys through to the active app
                            # But still intercept Escape to deactivate ghost mode
                            if vk == 0x1B:
                                self.ghost_typing_signal.emit(False)
                                return 1
            return ctypes.windll.user32.CallNextHookEx(self.hook_id, nCode, wParam, lParam)
            
        self.hook_callback = HOOKPROC(hook_proc)
        try:
            ctypes.windll.kernel32.GetModuleHandleW.restype = ctypes.wintypes.HINSTANCE
            ctypes.windll.kernel32.GetModuleHandleW.argtypes = [ctypes.wintypes.LPCWSTR]
            hmod = ctypes.windll.kernel32.GetModuleHandleW(None)
            self.hook_id = ctypes.windll.user32.SetWindowsHookExW(
                13, # WH_KEYBOARD_LL
                self.hook_callback,
                hmod,
                0
            )
        except Exception:
            pass
            
        # --- Mouse Hook (WH_MOUSE_LL = 14) ---
        def mouse_hook_proc(nCode, wParam, lParam):
            if nCode >= 0:
                if wParam == 0x0201: # WM_LBUTTONDOWN
                    m_struct = MSLLHOOKSTRUCT.from_address(lParam)
                    mx, my = m_struct.pt.x, m_struct.pt.y
                    global_pos = QPoint(mx, my)
                    
                    if getattr(self, 'waiting_for_inject_click', False):
                        if self.geometry().contains(global_pos):
                            # Click was inside overlay — ignore it so we don't cancel injection
                            pass
                        else:
                            self.waiting_for_inject_click = False
                            text_to_type = getattr(self, 'pending_inject_text', '')
                            sw_focus = getattr(self, 'pending_inject_switch_focus', False)
                            QTimer.singleShot(150, lambda: self.perform_stealth_injection(text_to_type, sw_focus))
                            return ctypes.windll.user32.CallNextHookEx(self.mouse_hook_id, nCode, wParam, lParam)
                            
                    # Strict Stealth Mode Clicks
                    if getattr(self, 'focus_mode', '') == 'Background':
                        if self.geometry().contains(global_pos) and not getattr(self, 'is_hidden', False):
                            local_pos = self.mapFromGlobal(global_pos)
                            child = self.childAt(local_pos)
                            
                            # Intercept if child is an interactive control
                            if child and (isinstance(child, (QPushButton, QLineEdit, QSlider)) or child.objectName() == "drag_handle"):
                                # We must swallow the click so the OS doesn't send it to the browser.
                                # Then, we simulate the click event on the Qt widget.
                                # QTimer.singleShot ensures the click is executed safely on the main thread.
                                def _click_widget(w):
                                    w.click() if hasattr(w, 'click') else None
                                QTimer.singleShot(0, lambda w=child: _click_widget(w))
                                return 1
                                
                        elif getattr(self, 'is_hidden', False) and getattr(self, 'restore_bubble', None):
                            if self.restore_bubble.geometry().contains(global_pos):
                                QTimer.singleShot(0, self.restore_from_edge)
                                return 1

            return ctypes.windll.user32.CallNextHookEx(self.mouse_hook_id, nCode, wParam, lParam)

            
        self.mouse_hook_callback = HOOKPROC(mouse_hook_proc)
        try:
            hmod = ctypes.windll.kernel32.GetModuleHandleW(None)
            self.mouse_hook_id = ctypes.windll.user32.SetWindowsHookExW(
                14, # WH_MOUSE_LL
                self.mouse_hook_callback,
                hmod,
                0
            )
        except Exception as e:
            print("Failed to install mouse hook:", e)
        
    def showEvent(self, event):
        super().showEvent(event)
        try:
            hwnd = int(self.winId())
            ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x00000011) # WDA_EXCLUDEFROMCAPTURE
        except Exception as e:
            print("Failed to register affinity:", e)
            
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
        if chat_input and obj == chat_input and event.type() == QEvent.MouseButtonPress:
            if self.focus_mode == 'Background' and not getattr(self, 'ghost_active', False):
                self.ghost_typing_signal.emit(True)
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
        super().changeEvent(event)
        
    def closeEvent(self, event):
        self.force_exit()
        
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
            if getattr(self, 'user_tier', 'Free') not in ["Pro", "Ultra"]:
                self.add_system_message("🔒 Upgrade Required: <b>Background Stealth Mode</b> is a Pro/Ultra feature. Please upgrade in the Manager Panel.")
                return
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
        # Refresh Acrylic blur effect on Windows
        apply_acrylic_blur(self, self.is_dark)
        
        # Premium dark glass vs light glass color tokens
        if self.is_dark:
            bg_gradient = f"rgba(15, 15, 18, {int(self.opacity_val * 0.45)})"
            border_color = "rgba(139, 92, 246, 70)"
            ctrl_bg = f"rgba(30, 30, 35, {int(self.opacity_val * 0.5)})"
            ctrl_text = "#E5E7EB"
            input_frame_bg = f"rgba(12, 12, 16, {int(self.opacity_val * 0.6)})"
            input_text = "#F3F4F6"
            sidebar_bg = f"rgba(10, 10, 12, {int(self.opacity_val * 0.35)})"
        else:
            bg_gradient = f"rgba(240, 240, 243, {int(self.opacity_val * 0.45)})"
            border_color = "rgba(139, 92, 246, 50)"
            ctrl_bg = f"rgba(235, 235, 240, {int(self.opacity_val * 0.5)})"
            ctrl_text = "#1F2937"
            input_frame_bg = f"rgba(255, 255, 255, {int(self.opacity_val * 0.6)})"
            input_text = "#111827"
            sidebar_bg = f"rgba(243, 244, 246, {int(self.opacity_val * 0.35)})"

        # Dynamic highlights: Purple for Command Mode, Green for Ghost Typing
        if getattr(self, 'leader_active', False):
            input_frame_border = "1.5px solid rgba(139, 92, 246, 220)"
            input_frame_bg = f"rgba(139, 92, 246, {int(self.opacity_val * 0.18)})"
        elif getattr(self, 'ghost_active', False):
            input_frame_border = "1.5px solid rgba(16, 185, 129, 200)"
            input_frame_bg = f"rgba(16, 185, 129, {int(self.opacity_val * 0.15)})"
        else:
            input_frame_border = f"1px solid {border_color}"

        placeholder = "[Stealth Ghost Typing ACTIVE... Enter: Send, Esc: Exit]" if getattr(self, 'ghost_active', False) else f"Ask {self.active_provider}... (Alt+Z then K: Type | P: Model | S: Scan | I: Inject | Space/H: Hide | U: Voice Typist | M: Live Chat | V: Speaker)"
        self.chat_input.setPlaceholderText(placeholder)

        # Master Global Application Stylesheet
        self.setStyleSheet(f"""
            QToolTip {{
                background-color: #1a1a24;
                color: #ffffff;
                border: 1px solid rgba(139, 92, 246, 180);
                border-radius: 6px;
                padding: 5px 8px;
                font-family: "Segoe UI", sans-serif;
                font-size: 11px;
            }}
            QFrame#overlay {{
                background-color: transparent;
                background: {bg_gradient};
                border: 1px solid {border_color};
                border-radius: 16px;
            }}
            QTextEdit#chat_history {{
                background-color: transparent;
                border: none;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 6px;
                margin: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(139, 92, 246, 60);
                border-radius: 3px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: rgba(139, 92, 246, 180);
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
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
                padding: 6px 12px;
                font-family: "Segoe UI", sans-serif;
                font-size: 12px;
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
                padding: 4px 12px;
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
                padding: 6px 14px;
                border-radius: 12px;
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
                border-radius: 12px;
                padding: 10px;
                font-family: "Segoe UI", sans-serif;
                font-size: 12px;
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
            QPushButton#send_btn {{
                background-color: #8b5cf6;
                color: white;
                border: none;
                border-radius: 16px;
                min-width: 32px;
                min-height: 32px;
                max-width: 32px;
                max-height: 32px;
            }}
            QPushButton#send_btn:hover {{
                background-color: #7c3aed;
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
        
        alpha = getattr(self, 'opacity_val', 220)
        
        if self.is_dark:
            if hovered:
                bg = f"qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(139, 92, 246, {min(255, int(alpha * 1.35))}), stop:1 rgba(99, 102, 241, {min(255, int(alpha * 1.35))}))"
                border = "rgba(255, 255, 255, 180)"
            else:
                bg = f"qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(30, 30, 45, {int(alpha * 0.95)}), stop:1 rgba(20, 20, 30, {int(alpha * 0.95)}))"
                border = "rgba(139, 92, 246, 120)"
        else:
            if hovered:
                bg = f"qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(139, 92, 246, {min(255, int(alpha * 1.35))}), stop:1 rgba(99, 102, 241, {min(255, int(alpha * 1.35))}))"
                border = "rgba(0, 0, 0, 160)"
            else:
                bg = f"qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(245, 245, 250, {int(alpha * 0.95)}), stop:1 rgba(235, 235, 240, {int(alpha * 0.95)}))"
                border = "rgba(139, 92, 246, 120)"

        edge = getattr(self, 'dock_edge', 'right')
        if edge == 'left':
            corners = "border-top-right-radius: 8px; border-bottom-right-radius: 8px; border-top-left-radius: 0px; border-bottom-left-radius: 0px;"
        elif edge == 'right':
            corners = "border-top-left-radius: 8px; border-bottom-left-radius: 8px; border-top-right-radius: 0px; border-bottom-right-radius: 0px;"
        elif edge == 'top':
            corners = "border-bottom-left-radius: 8px; border-bottom-right-radius: 8px; border-top-left-radius: 0px; border-top-right-radius: 0px;"
        else:
            corners = "border-top-left-radius: 8px; border-top-right-radius: 8px; border-bottom-left-radius: 0px; border-bottom-right-radius: 0px;"

        self.restore_bubble.setStyleSheet(f"""
            QLabel {{
                background: {bg};
                border: 1px solid {border};
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
        self.opacity_label.setText(f"Alpha: {value}%")
        self.opacity_val = int((value / 100.0) * 255)
        if not getattr(self, 'is_hidden', False): 
            self.update_style()
        else:
            self.update_restore_bubble_style(hovered=False)
        self.save_settings()
        
        # Re-render chat preserving scroll position to update message opacities
        if getattr(self, 'current_chat_id', None):
            scrollbar = self.chat_history.verticalScrollBar()
            scroll_pos = scrollbar.value()
            self.suppress_scroll = True
            self.load_session(self.current_chat_id)
            self.suppress_scroll = False
            QApplication.processEvents()
            scrollbar.setValue(scroll_pos)

    def toggle_system_audio_recording(self):
        # Premium check
        if getattr(self, 'user_tier', 'Free') not in ["Pro", "Ultra"]:
            self.add_system_message("🔒 Upgrade Required: <b>System Audio Loopback Transcription</b> is a Pro/Ultra feature. Please upgrade in the Manager Panel.")
            return
            
        if self.system_audio_worker and self.system_audio_worker.isRunning():
            self.system_audio_worker.stop()
            self.add_system_message("⏹️ Stopping system audio recording...")
            return
            
        self.system_audio_worker = SystemAudioWorker(duration=15)
        self.system_audio_worker.status_signal.connect(self.add_system_message)
        self.system_audio_worker.finished_signal.connect(self.on_system_audio_transcribed)
        self.system_audio_worker.error_signal.connect(self.on_system_audio_error)
        self.system_audio_worker.start()
        
    def on_system_audio_transcribed(self, text):
        self.system_audio_worker = None
        if not text.strip():
            self.add_system_message("⚠️ No system audio speech detected.")
            return
        self.add_system_message(f"🔊 Transcribed System Audio: <i>{text}</i>")
        self.chat_input.setText(text)
        # Send immediately
        self.handle_chat(voice_input=True)
        
    def on_system_audio_error(self, err_msg):
        self.system_audio_worker = None
        self.add_system_message(f"❌ System Audio Error: {err_msg}")


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    app = QApplication(sys.argv)
    overlay = TransparentOverlay()
    overlay.show()
    app_filter = AppEventFilter(overlay)
    app.installEventFilter(app_filter)
    sys.exit(app.exec_())
