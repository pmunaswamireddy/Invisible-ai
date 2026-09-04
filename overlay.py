import sys
import os
import logging
from datetime import datetime, timezone
from logging_config import setup_logging, mask_key

# Global application directory
APP_DIR = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'InvisibleAI')

# Setup logging
logger = setup_logging(APP_DIR)
logger.info("Starting InvisibleAI...")

import os
import ctypes
import json
import time
import threading
import urllib.request
import urllib.parse
import http.server
import socketserver
import re
import queue
import uuid
from ctypes.wintypes import POINT
from ctypes import wintypes
import signal
from PyQt5.QtWidgets import QStylePainter, QStyle, QStyleOptionTab, QApplication, QMenu, QWidget, QVBoxLayout, QTextEdit, QTextBrowser, QPushButton, QSlider, QLabel, QHBoxLayout, QFrame, QLineEdit, QComboBox, QSizePolicy, QListWidget, QListWidgetItem, QScrollArea, QGridLayout, QMessageBox, QStackedWidget, QTabWidget, QFileDialog, QTabBar
from PyQt5.QtCore import QUrl, Qt, QPoint, QEvent, QObject, QTimer, pyqtSignal, QAbstractNativeEventFilter, QThread, QRect, QSize, QEventLoop
from PyQt5.QtGui import QColor, QPainter, QPen, QCursor, QMouseEvent, QPixmap, QPainterPath, QTextCursor, QFont

from core.constants import (
    KBDLLHOOKSTRUCT, POINT, RECT, MSLLHOOKSTRUCT, HOOKPROC,
    translate_vk_to_char, get_app_dir, KeyBdInput, HardwareInput,
    MouseInput, Input_I, Input
)
from core.stealth import stealth_click, set_win32_clipboard, get_win32_clipboard
from utils.typing_engine import stealth_paste_text, stealth_type_text
from ai.web2api import Web2APIHandler, EmbeddedWeb2APIServer
from ai.worker import AITaskWorker
from ai.vision_worker import VisionInterviewWorker, OCRWorker
from ui.widgets import (
    SafeTextBrowser, CustomTabBar, AudioWaveWidget, ModernIconButton, ChatHistoryItemWidget
)
from ui.snip import LivePreviewPopup, MultiSnipController, ScreenSniper
from ui.event_filter import AppEventFilter
from features.voice import TTSWorker, DictationWorker, VoiceSetupWorker

HAS_MSS = True
_overlay_instance = None
GLOBAL_GEMINI_THROTTLED_UNTIL = 0.0

def global_mouse_hook_callback(nCode, wParam, lParam):
    try:
        global _overlay_instance
        if _overlay_instance:
            return _overlay_instance._mouse_hook_callback_impl(nCode, wParam, lParam)
    except Exception:
        pass
    return ctypes.windll.user32.CallNextHookEx(None, nCode, wParam, lParam)

def global_kb_hook_callback(nCode, wParam, lParam):
    try:
        global _overlay_instance
        if _overlay_instance:
            return _overlay_instance._kb_hook_callback_impl(nCode, wParam, lParam)
    except Exception:
        pass
    return ctypes.windll.user32.CallNextHookEx(None, nCode, wParam, lParam)


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
    type_hotkey_signal = pyqtSignal()
    type_indexed_hotkey_signal = pyqtSignal(int)
    app_log_signal = pyqtSignal(str, str)
    focus_chat_hotkey_signal = pyqtSignal()
    bg_click_signal = pyqtSignal(int, int)  # x, y of click
    
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
            # Use HWND_TOPMOST (-1) to guarantee window stays on top
            ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0020)
        except Exception:
            pass

    def __init__(self):
        super().__init__()
        global _overlay_instance
        _overlay_instance = self
        app = QApplication.instance()
        app._overlay_instance = self
        
        self.scan_hotkey_signal.connect(self.scan_screen)
        self.inject_hotkey_signal.connect(self.inject_code)
        self.inject_indexed_hotkey_signal.connect(self.inject_code)
        self.type_hotkey_signal.connect(self.type_code)
        self.type_indexed_hotkey_signal.connect(self.type_code)
        self.send_hotkey_signal.connect(self.handle_chat)
        self.focus_chat_hotkey_signal.connect(self.focus_chat_from_hotkey)
        self.bg_click_signal.connect(self.process_hook_click)
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
        self.swallowed_mouse_down = False
        
        # Initialize voice recognizer and microphone once on startup to prevent PortAudio thread segfaults
        try:
            import speech_recognition as sr  # type: ignore # pyright: ignore [reportMissingImports]
            self._shared_recognizer = sr.Recognizer()
            self._shared_microphone = sr.Microphone()
        except Exception:
            self._shared_recognizer = None
            self._shared_microphone = None
        
        self.tts_worker = TTSWorker()
        self.tts_worker.speech_status_signal.connect(self.on_tts_speech_status)
        self.tts_worker.start()
        
        self.collapsed_codes = set()
        self.browser_history = []
        self.browser_bookmarks = []
        self.suppress_scroll = False
        
        settings = self.load_settings()
        self.is_dark = settings.get("is_dark", True)
        self.focus_mode = settings.get("focus_mode", "Background")
        self.dock_edge = settings.get("dock_edge", "right")
        self.current_alpha = settings.get("opacity", 90)
        self.opacity_val = int((self.current_alpha / 100.0) * 255)
        self.voice_enabled = settings.get("voice_enabled", True)
            
        self.setWindowTitle("SystemResourceNotifyWindow")
        
        flags = Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool
        self.setWindowFlags(flags)
        
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowOpacity(max(0.15, self.current_alpha / 100.0))
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
        self.abort_injection = False
        self.leader_active = False
        self.sessions = []
        self.current_chat_id = None
        self.usage_counts = {"Gemini": 0, "Groq": 0, "OpenRouter": 0, "NVIDIA": 0, "Web2API": 0}
        
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
            "nvidia": os.environ.get("NVIDIA_API_KEY", ""),
            "web2api": os.environ.get("WEB2API_API_KEY", "") or "http://localhost:8081/v1"
        }
        self.api_keys = settings.get("api_keys", default_keys)
        
        # Ensure default keys are non-removable: fallback to default environmental keys if empty/missing
        if not self.api_keys.get("gemini", "").strip(): self.api_keys["gemini"] = default_keys["gemini"]
        if not self.api_keys.get("groq", "").strip(): self.api_keys["groq"] = default_keys["groq"]
        if not self.api_keys.get("openrouter", "").strip(): self.api_keys["openrouter"] = default_keys["openrouter"]
        if not self.api_keys.get("nvidia", "").strip(): self.api_keys["nvidia"] = default_keys["nvidia"]
        if not self.api_keys.get("web2api", "").strip(): self.api_keys["web2api"] = default_keys["web2api"]
            
        self.active_provider = settings.get("active_provider", "Gemini")
        self.embedded_web2api_server = EmbeddedWeb2APIServer(port=8081)
        self.check_web2api_server_lifecycle()
        
        default_models = {
            "gemini": "gemini-flash-latest",
            "groq": "llama-3.3-70b-versatile",
            "openrouter": "google/gemini-2.0-flash:free",
            "nvidia": "meta/llama-3.2-11b-vision-instruct",
            "web2api": "gemini-3.5-flash-thinking"
        }
        self.provider_models = settings.get("provider_models", default_models)
        for k, v in default_models.items():
            if k not in self.provider_models or not self.provider_models[k].strip():
                self.provider_models[k] = v
                
        # Settings migration: Ensure gemini uses working models
        if self.provider_models.get("gemini") not in ["gemini-flash-latest", "gemini-2.5-flash"]:
            self.provider_models["gemini"] = "gemini-flash-latest" 
        
        self.setMinimumSize(350, 200)
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
        self.sidebar_btn.setToolTip("Toggle Chat History Sidebar (Hotkey: Alt+Z -> B)")
        self.sidebar_btn.clicked.connect(self.toggle_sidebar)
        row1.addWidget(self.sidebar_btn)

        self.drag_handle = QLabel(" ✥ Drag ")
        self.drag_handle.setObjectName("drag_handle")
        self.drag_handle.setCursor(Qt.SizeAllCursor)
        self.drag_handle.setToolTip("Click & Drag window (Hotkey: Alt+Z -> Arrow keys to move/resize)")
        row1.addWidget(self.drag_handle)
        
        self.theme_btn = ModernIconButton("theme_light" if self.is_dark else "theme_dark", "Light" if self.is_dark else "Dark")
        self.theme_btn.setObjectName("action_btn")
        self.theme_btn.setToolTip("Toggle Light/Dark Theme (Hotkey: Alt+Z -> J)")
        self.theme_btn.clicked.connect(self.toggle_theme)
        row1.addWidget(self.theme_btn)
        
        self.focus_btn = ModernIconButton("focus", f"Type In: {self.focus_mode}")
        self.focus_btn.setObjectName("action_btn")
        self.focus_btn.setToolTip("Toggle Focus Mode (Background vs Overlay) (Hotkey: Alt+F or Alt+Z -> F)")
        self.focus_btn.clicked.connect(self.toggle_focus_mode)
        row1.addWidget(self.focus_btn)
        
        opacity_percent = settings.get("opacity", 90)
        self.opacity_label = QLabel(f"Alpha: {opacity_percent}%")
        self.opacity_label.setObjectName("opacity_label")
        row1.addWidget(self.opacity_label)
        
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(1)
        self.slider.setMaximum(100)
        self.slider.setValue(opacity_percent)
        self.slider.setFixedWidth(75)
        self.slider.setToolTip("Background Transparency Slider (Hotkey: Alt+Z -> [ / ] or Mouse Wheel)")
        self.slider.valueChanged.connect(self.change_opacity)
        row1.addWidget(self.slider)
        
        self.current_alpha = opacity_percent
        
        row1.addStretch()
        
        self.scrap_btn = ModernIconButton("web_scrap", "Scrap")
        self.scrap_btn.setObjectName("action_btn")
        self.scrap_btn.setToolTip("Crop screen region & extract text/code via OCR (Hotkey: Alt+S or Alt+Z -> S)")
        self.scrap_btn.clicked.connect(self.start_screen_scrap)
        row1.addWidget(self.scrap_btn)

        self.overlay_snip_btn = ModernIconButton("camera", "Shot")
        self.overlay_snip_btn.setObjectName("action_btn")
        self.overlay_snip_btn.setToolTip("Take Overlay Window Screenshot (Saves PNG & Copies to Clipboard)")
        self.overlay_snip_btn.clicked.connect(self.capture_overlay_screenshot)
        row1.addWidget(self.overlay_snip_btn)

        self.browser_btn = ModernIconButton("browser", "Browser")
        self.browser_btn.setObjectName("action_btn")
        self.browser_btn.setToolTip("Toggle Embedded Web Browser (Hotkey: Alt+W or Alt+Z -> W | Alt+B for Address Bar)")
        self.browser_btn.clicked.connect(self.toggle_browser_visibility)
        row1.addWidget(self.browser_btn)

        self.clear_btn = ModernIconButton("clear", "Clear")
        self.clear_btn.setObjectName("action_btn")
        self.clear_btn.setToolTip("Clear current chat history (Hotkey: Alt+Z -> C)")
        self.clear_btn.clicked.connect(self.clear_chat)
        row1.addWidget(self.clear_btn)
        
        self.hide_btn = ModernIconButton("hide", "Hide")
        self.hide_btn.setObjectName("action_btn")
        self.hide_btn.setToolTip("Minimize overlay to screen edge (Hotkey: Alt+H or Alt+Z -> Space)")
        self.hide_btn.clicked.connect(self.minimize_to_edge)
        row1.addWidget(self.hide_btn)
        
        self.close_btn = ModernIconButton("close", "Exit")
        self.close_btn.setObjectName("danger_btn")
        self.close_btn.setToolTip("Exit Application (Hotkey: Alt+Z -> X)")
        self.close_btn.clicked.connect(self.force_exit)
        
        self.header_more_btn = ModernIconButton("more", "")
        self.header_more_btn.setToolTip("More Header Options (Hotkey: Alt+Z)")
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
        self.new_chat_btn.setToolTip("Start a brand new chat session (Hotkey: Alt+Z then N)")
        self.new_chat_btn.clicked.connect(self.new_chat)
        sidebar_layout.addWidget(self.new_chat_btn)
        
        self.chat_list = QListWidget()
        self.chat_list.setObjectName("chat_list")
        self.chat_list.itemClicked.connect(self.on_chat_selected)
        sidebar_layout.addWidget(self.chat_list)
        
        self.clear_all_btn = ModernIconButton("clear", "Clear All History")
        self.clear_all_btn.setObjectName("danger_btn")
        self.clear_all_btn.setToolTip("Delete all past saved chat sessions (Hotkey: Alt+Z then C)")
        self.clear_all_btn.clicked.connect(self.clear_all_chats)
        sidebar_layout.addWidget(self.clear_all_btn)
        
        self.settings_sidebar_btn = ModernIconButton("settings", "Settings")
        self.settings_sidebar_btn.setObjectName("new_chat_btn")
        self.settings_sidebar_btn.setToolTip("Open API Keys & System Settings Modal (Hotkey: Alt+Z then G)")
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

        # Tab widget containing Chat and Web Browser tabs
        self.tab_widget = QTabWidget()
        self.tab_bar = CustomTabBar(self.tab_widget)
        self.tab_widget.setTabBar(self.tab_bar)
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.tabCloseRequested.connect(self.close_tab)
        self.tab_widget.currentChanged.connect(self.on_tab_changed)
        self.close_all_tabs_btn = QPushButton("✕ Close All")
        self.close_all_tabs_btn.setObjectName("action_btn")
        self.close_all_tabs_btn.setToolTip("Close all browser tabs")
        self.close_all_tabs_btn.clicked.connect(self.close_all_browser_tabs)
        self.close_all_tabs_btn.setStyleSheet("padding: 4px 8px; font-weight: bold; background: rgba(200, 50, 50, 0.4); border-radius: 4px;")
        self.tab_widget.setCornerWidget(self.close_all_tabs_btn, Qt.TopRightCorner)
        self.close_all_tabs_btn.setVisible(False)

        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: none;
                background: transparent;
            }
            QTabBar::tab {
                background: #1e1b29;
                color: #a78bfa;
                border: 1px solid #4c1d95;
                padding: 3px 8px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-family: 'Segoe UI', sans-serif;
                font-size: 10px;
                min-width: 80px;
                height: 18px;
            }
            QTabBar::tab:selected {
                background: #2e1065;
                color: #f3e8ff;
                border-bottom: 2px solid #8b5cf6;
            }
            QTabBar::tab:hover {
                background: #3b0764;
                color: #f3e8ff;
            }
        """)
        self.tab_widget.addTab(self.chat_history, "\U0001F4AC Chat")
        self.tab_widget.tabBar().setVisible(False)
        
        chat_container_layout.addWidget(self.tab_widget)
        self.init_settings_frame(chat_container_layout)
        
        self.typing_container = QWidget()
        self.typing_container.setFixedHeight(22)
        typing_layout = QHBoxLayout(self.typing_container)
        typing_layout.setContentsMargins(0, 0, 0, 0)
        typing_layout.setSpacing(0)
        
        self.typing_label = QLabel("")
        self.typing_label.setObjectName("typing_label")
        self.typing_label.setStyleSheet("color: #8b5cf6; font-weight: bold; font-family: 'Segoe UI', sans-serif; font-size: 13px; margin: 0px 15px 0px 15px;")
        self.typing_label.hide()
        typing_layout.addWidget(self.typing_label)
        chat_container_layout.addWidget(self.typing_container)
        
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
        self.provider_combo.addItems(["Gemini", "Groq", "OpenRouter", "NVIDIA", "Google Web Search", "Web2API"])
        self.provider_combo.setCurrentText(self.active_provider)
        self.provider_combo.setToolTip("Select active AI Provider (Hotkey: Alt+Z then P to rotate)")
        self.provider_combo.currentTextChanged.connect(self.change_provider)
        bottom_row.addWidget(self.provider_combo)
        
        bottom_row.addStretch()
        
        self.scan_btn = ModernIconButton("scan", "Scan")
        self.scan_btn.setObjectName("action_btn")
        self.scan_btn.setToolTip("Capture full screen & extract text/code to AI (Hotkey: Alt+Z then S)")
        self.scan_btn.clicked.connect(lambda: self.trigger_with_bg_click(self.scan_screen))
        bottom_row.addWidget(self.scan_btn)
        
        self.inject_btn = ModernIconButton("inject", "Inject")
        self.inject_btn.setObjectName("action_btn")
        self.inject_btn.setToolTip("Fast Clipboard Inject code into target window (Hotkey: Alt+Z then I | Alt+Z then 1..9 then I)")
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
        self.interview_btn.setToolTip("Toggle Live Interview Audio Stream (Hotkey: Alt+Z then L)")
        self.interview_btn.setCheckable(True)
        self.interview_btn.clicked.connect(self.toggle_interview_mode)
        bottom_row.addWidget(self.interview_btn)
        
        # Voice model selector — populated with system TTS voices
        self.voice_combo = QComboBox()
        self.voice_combo.setObjectName("provider_combo")
        self.voice_combo.setToolTip("Select TTS Voice Model (Hotkey: Alt+Z then O to rotate)")
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
            stdout_str = (result.stdout or "").strip()
            voice_names = [v.strip() for v in stdout_str.splitlines() if v.strip()]
            for vn in voice_names:
                label = vn.replace('Microsoft ', '').replace(' Desktop', '').strip()
                self.voice_combo.addItem(label, userData=vn)  # userData = full SAPI name
        except Exception:
            self.voice_combo.addItem("Default", userData=None)
        self.voice_combo.currentIndexChanged.connect(self._on_voice_combo_changed)
        bottom_row.addWidget(self.voice_combo)
        
        self.single_mic_btn = ModernIconButton("single_mic", "Voice\nInput")
        self.single_mic_btn.setObjectName("action_btn")
        self.single_mic_btn.setToolTip("Single Voice Input — Transcribes into chat box (Hotkey: Alt+Z then U)")
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
        self.bottom_more_btn.setToolTip("More Bottom Tools (Hotkey: Alt+Z)")
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
        
        self.ghost_active = False
        self.leader_active = False
        self.waiting_for_inject_click = False
        self._mouse_hook = None
        self._keyboard_hook = None
        self.setMouseTracking(True)
        
        for widget in [self.theme_btn, self.focus_btn, self.clear_btn, self.hide_btn, self.close_btn,
                       self.provider_combo, self.scan_btn, self.inject_btn, self.voice_btn,
                       self.single_mic_btn, self.mic_btn, self.send_btn, self.new_chat_btn, self.clear_all_btn]:
            widget.installEventFilter(self)
            
        self.update_style()
        self.load_chat_history()
        
    def trigger_with_bg_click(self, func):
        # In Background mode, WM_NCHITTEST returns HTTRANSPARENT for all overlay areas,
        # so the physical mouse click ALREADY passed through to the browser below us.
        # We just programmatically execute the overlay action — no stealth_click needed.
        try:
            func()
        except Exception:
            pass
        
    def format_log_html(self, timestamp, message, level):
        lvl_str = str(level).lower().strip()
        
        # Color coding strictly matching user requirements:
        # Errors = RED, Successful = GREEN, Ongoing = BLUE, Others = GRAY
        if lvl_str in ["error", "failure", "fail", "err", "warning", "misbehave"]:
            tag_color = "#ff5555" # Vibrant Red
            msg_color = "#ff8888"
            tag_label = "ERROR" if "warning" not in lvl_str else "WARN"
        elif lvl_str in ["success", "completed", "done", "ok", "successful", "successfull"]:
            tag_color = "#50fa7b" # Vibrant Green
            msg_color = "#a6e22e"
            tag_label = "SUCCESS"
        elif lvl_str in ["ongoing", "progress", "running", "start", "starting", "active", "typing", "injecting", "performance"]:
            tag_color = "#38bdf8" # Vibrant Blue
            msg_color = "#7dd3fc"
            tag_label = "ONGOING" if lvl_str in ["ongoing", "progress", "running", "active"] else lvl_str.upper()
        else: # info, system, debug, and all others
            tag_color = "#94a3b8" # Sleek Gray
            msg_color = "#cbd5e1"
            tag_label = lvl_str.upper() if lvl_str else "INFO"
            
        return (
            f"<span style='color: #64748b; font-family: Consolas, monospace;'>[{timestamp}]</span> "
            f"<span style='color: {tag_color}; font-weight: bold; font-family: Consolas, monospace;'>[{tag_label}]</span> "
            f"<span style='color: {msg_color}; font-family: Consolas, monospace;'>{message}</span>"
        )

    def log_event(self, message, level="info"):
        if not hasattr(self, 'log_history'):
            self.log_history = []
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_history.append((timestamp, message, level))
        if len(self.log_history) > 1000:
            self.log_history = self.log_history[-1000:]
        self.app_log_signal.emit(message, level)
        
    def append_log(self, message, level):
        if not hasattr(self, 'log_viewer') or self.log_viewer is None:
            return
        
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        html_msg = self.format_log_html(timestamp, message, level)
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
        self.usage_counts = {"Gemini": 0, "Groq": 0, "OpenRouter": 0, "NVIDIA": 0, "Web2API": 0}
        try:
            for s in self.sessions:
                for m in s.get('messages', []):
                    if m.get('role') == 'ai':
                        p = m.get('provider', '')
                        if "Gemini" in p: self.usage_counts["Gemini"] += 1
                        elif "Groq" in p: self.usage_counts["Groq"] += 1
                        elif "OpenRouter" in p: self.usage_counts["OpenRouter"] += 1
                        elif "NVIDIA" in p: self.usage_counts["NVIDIA"] += 1
                        elif "Web2API" in p: self.usage_counts["Web2API"] += 1
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
            logger.error("Failed to save history: %s", e)

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
            elif "Web2API" in provider: self.usage_counts["Web2API"] += 1
        
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
        self.usage_counts = {"Gemini": 0, "Groq": 0, "OpenRouter": 0, "NVIDIA": 0, "Web2API": 0}
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
        self.key_gemini.textChanged.connect(self.save_settings_debounced)
        form_layout.addWidget(create_key_input_row(self.key_gemini, "gemini"), row, 1)
        
        form_layout.addWidget(QLabel("<b>Model:</b>"), row, 2)
        self.model_gemini = QComboBox()
        gemini_models = ["gemini-flash-latest", "gemini-2.5-flash"]
        saved_gemini = self.provider_models.get("gemini", "gemini-flash-latest")
        if saved_gemini not in gemini_models:
            gemini_models.append(saved_gemini)
        self.model_gemini.addItems(gemini_models)
        self.model_gemini.setCurrentText(saved_gemini)
        self.model_gemini.currentTextChanged.connect(self.save_settings_debounced)
        form_layout.addWidget(self.model_gemini, row, 3)
        row += 1
        
        # Groq
        form_layout.addWidget(QLabel("<b>Groq Key:</b>"), row, 0)
        self.key_groq = QLineEdit()
        self.key_groq.setText(self.api_keys.get("groq", ""))
        self.key_groq.textChanged.connect(self.save_settings_debounced)
        form_layout.addWidget(create_key_input_row(self.key_groq, "groq"), row, 1)
        
        form_layout.addWidget(QLabel("<b>Model:</b>"), row, 2)
        self.model_groq = QComboBox()
        groq_models = ["llama-3.3-70b-versatile", "llama-3.1-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768", "gemma2-9b-it"]
        saved_groq = self.provider_models.get("groq", "llama-3.3-70b-versatile")
        if saved_groq not in groq_models:
            groq_models.append(saved_groq)
        self.model_groq.addItems(groq_models)
        self.model_groq.setCurrentText(saved_groq)
        self.model_groq.currentTextChanged.connect(self.save_settings_debounced)
        form_layout.addWidget(self.model_groq, row, 3)
        row += 1
        
        # OpenRouter
        form_layout.addWidget(QLabel("<b>OpenRouter Key:</b>"), row, 0)
        self.key_or = QLineEdit()
        self.key_or.setText(self.api_keys.get("openrouter", ""))
        self.key_or.textChanged.connect(self.save_settings_debounced)
        form_layout.addWidget(create_key_input_row(self.key_or, "openrouter"), row, 1)
        
        form_layout.addWidget(QLabel("<b>Model:</b>"), row, 2)
        self.model_or = QComboBox()
        or_models = ["google/gemini-2.0-flash:free", "meta-llama/llama-3.3-70b-instruct:free", "qwen/qwen-2.5-7b-instruct:free", "meta-llama/llama-3.2-3b-instruct:free", "microsoft/phi-3-medium-128k-instruct:free"]
        saved_or = self.provider_models.get("openrouter", "google/gemini-2.0-flash:free")
        if saved_or not in or_models:
            or_models.append(saved_or)
        self.model_or.addItems(or_models)
        self.model_or.setCurrentText(saved_or)
        self.model_or.currentTextChanged.connect(self.save_settings_debounced)
        form_layout.addWidget(self.model_or, row, 3)
        row += 1
        
        # NVIDIA
        form_layout.addWidget(QLabel("<b>NVIDIA Key:</b>"), row, 0)
        self.key_nv = QLineEdit()
        self.key_nv.setText(self.api_keys.get("nvidia", ""))
        self.key_nv.textChanged.connect(self.save_settings_debounced)
        form_layout.addWidget(create_key_input_row(self.key_nv, "nvidia"), row, 1)
        
        form_layout.addWidget(QLabel("<b>Model:</b>"), row, 2)
        self.model_nv = QComboBox()
        nvidia_models = ["meta/llama-3.2-11b-vision-instruct", "meta/llama-3.1-8b-instruct", "upstage/solar-10.7b-instruct", "meta/llama-3.2-3b-instruct", "nvidia/llama-3.1-nemotron-70b-instruct", "meta/llama-3.1-70b-instruct"]
        saved_nv = self.provider_models.get("nvidia", "meta/llama-3.2-11b-vision-instruct")
        if saved_nv not in nvidia_models:
            nvidia_models.append(saved_nv)
        self.model_nv.addItems(nvidia_models)
        self.model_nv.setCurrentText(saved_nv)
        self.model_nv.currentTextChanged.connect(self.save_settings_debounced)
        form_layout.addWidget(self.model_nv, row, 3)
        row += 1
        
        # Web2API
        form_layout.addWidget(QLabel("<b>Web2API Key/URL:</b>"), row, 0)
        self.key_web2api = QLineEdit()
        self.key_web2api.setPlaceholderText("http://localhost:8081/v1")
        self.key_web2api.setText(self.api_keys.get("web2api", "http://localhost:8081/v1"))
        self.key_web2api.textChanged.connect(self.save_settings_debounced)
        form_layout.addWidget(create_key_input_row(self.key_web2api, "web2api"), row, 1)
        
        form_layout.addWidget(QLabel("<b>Model:</b>"), row, 2)
        self.model_web2api = QComboBox()
        web2api_models = ["gemini-3.5-flash-thinking", "gemini-3.6-flash", "gemini-3.5-flash-thinking-lite", "gemini-3.1-pro", "gemini-auto", "gemini-flash-lite"]
        saved_web2api = self.provider_models.get("web2api", "gemini-3.5-flash-thinking")
        if saved_web2api not in web2api_models:
            web2api_models.append(saved_web2api)
        self.model_web2api.addItems(web2api_models)
        self.model_web2api.setCurrentText(saved_web2api)
        self.model_web2api.currentTextChanged.connect(self.save_settings_debounced)
        form_layout.addWidget(self.model_web2api, row, 3)
        
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
        save_btn.clicked.connect(self.on_save_config_clicked)
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
        self.log_viewer.document().setMaximumBlockCount(1000)
        logs_layout.addWidget(self.log_viewer)
        
        # Populate history logs into log_viewer
        if hasattr(self, 'log_history') and self.log_history:
            self.log_viewer.clear()
            for ts, msg, lvl in self.log_history:
                self.log_viewer.append(self.format_log_html(ts, msg, lvl))
            scrollbar = self.log_viewer.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
        
        log_btn_layout = QHBoxLayout()
        clear_logs_btn = QPushButton("🗑️ Clear Logs")
        clear_logs_btn.setStyleSheet("background-color: rgba(239, 68, 68, 0.2); border: 1px solid rgba(239, 68, 68, 0.4); color: #f87171; padding: 6px 12px;")
        
        def clear_logs_action():
            self.log_history = []
            if hasattr(self, 'log_viewer') and self.log_viewer:
                self.log_viewer.clear()
        clear_logs_btn.clicked.connect(clear_logs_action)
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
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            tomorrow_utc = datetime.datetime(now_utc.year, now_utc.month, now_utc.day) + datetime.timedelta(days=1)
            time_until_utc_reset = tomorrow_utc - now_utc
            utc_hours, remainder_utc = divmod(time_until_utc_reset.seconds, 3600)
            utc_minutes, _ = divmod(remainder_utc, 60)
            utc_reset_str = f"{utc_hours}h {utc_minutes}m (UTC)"

            limits = {"Gemini": 1500, "Groq": 14400, "OpenRouter": 200, "NVIDIA": 1000, "Web2API": 10000}
            
            stats = []
            for p in ["Gemini", "Groq", "OpenRouter", "NVIDIA", "Web2API"]:
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

        # 0. Gemini Models Update (Only verified free working endpoints)
        working_gemini = ["gemini-flash-latest", "gemini-2.5-flash"]
        current_g = self.model_gemini.currentText()
        self.model_gemini.clear()
        self.model_gemini.addItems(working_gemini)
        if current_g in working_gemini:
            self.model_gemini.setCurrentText(current_g)
        else:
            self.model_gemini.setCurrentIndex(0)
        
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
                        m_id = m.get('id', '')
                        pricing = m.get('pricing', {})
                        p_val = float(pricing.get('prompt', 0) or 0)
                        c_val = float(pricing.get('completion', 0) or 0)
                        # Filter all free models ending with :free or having zero pricing
                        if ':free' in m_id or (p_val == 0.0 and c_val == 0.0 and 'free' in m_id.lower()):
                            working_or.append(m_id)
                    
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

        # 4. Web2API Models Fetch
        web2_entry = self.key_web2api.text().strip() if hasattr(self, 'key_web2api') else "http://localhost:8081/v1"
        web2_base_url = "http://localhost:8081/v1"
        web2_key = "sk-web2api"
        if "http://" in web2_entry or "https://" in web2_entry:
            web2_base_url = web2_entry.rstrip('/')
            if not web2_base_url.endswith('/v1'):
                web2_base_url += '/v1'
        else:
            if web2_entry:
                web2_key = web2_entry

        try:
            models_url = f"{web2_base_url}/models"
            req = urllib.request.Request(
                models_url,
                headers={"Authorization": f"Bearer {web2_key}", "User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read())
                working_web2 = [m['id'] for m in data.get('data', []) if 'id' in m]
                if working_web2 and hasattr(self, 'model_web2api'):
                    current = self.model_web2api.currentText()
                    self.model_web2api.clear()
                    self.model_web2api.addItems(working_web2)
                    if current in working_web2:
                        self.model_web2api.setCurrentText(current)
                    else:
                        self.model_web2api.setCurrentIndex(0)
        except Exception as e:
            self.log_event(f"Web2API models fetch failed: {e}", "warning")

        self.calculate_usage_statistics()
        self.save_settings()
        QMessageBox.information(self, "Models Updated", "Available working models refreshed dynamically from API providers.")

    def sync_settings_to_ui(self):
        # Sync all settings widgets with actual in-memory settings to avoid inconsistencies
        if hasattr(self, 'key_gemini'):
            self.key_gemini.blockSignals(True)
            self.key_gemini.setText(self.api_keys.get("gemini", ""))
            self.key_gemini.blockSignals(False)
        if hasattr(self, 'key_groq'):
            self.key_groq.blockSignals(True)
            self.key_groq.setText(self.api_keys.get("groq", ""))
            self.key_groq.blockSignals(False)
        if hasattr(self, 'key_or'):
            self.key_or.blockSignals(True)
            self.key_or.setText(self.api_keys.get("openrouter", ""))
            self.key_or.blockSignals(False)
        if hasattr(self, 'key_nv'):
            self.key_nv.blockSignals(True)
            self.key_nv.setText(self.api_keys.get("nvidia", ""))
            self.key_nv.blockSignals(False)
        if hasattr(self, 'key_web2api'):
            self.key_web2api.blockSignals(True)
            self.key_web2api.setText(self.api_keys.get("web2api", "http://localhost:8081/v1"))
            self.key_web2api.blockSignals(False)

        if hasattr(self, 'model_gemini'):
            self.model_gemini.blockSignals(True)
            self.model_gemini.setCurrentText(self.provider_models.get("gemini", "gemini-flash-latest"))
            self.model_gemini.blockSignals(False)
        if hasattr(self, 'model_groq'):
            self.model_groq.blockSignals(True)
            self.model_groq.setCurrentText(self.provider_models.get("groq", "llama-3.3-70b-versatile"))
            self.model_groq.blockSignals(False)
        if hasattr(self, 'model_or'):
            self.model_or.blockSignals(True)
            self.model_or.setCurrentText(self.provider_models.get("openrouter", "google/gemini-2.0-flash:free"))
            self.model_or.blockSignals(False)
        if hasattr(self, 'model_nv'):
            self.model_nv.blockSignals(True)
            self.model_nv.setCurrentText(self.provider_models.get("nvidia", "meta/llama-3.2-11b-vision-instruct"))
            self.model_nv.blockSignals(False)
        if hasattr(self, 'model_web2api'):
            self.model_web2api.blockSignals(True)
            self.model_web2api.setCurrentText(self.provider_models.get("web2api", "gemini-3.5-flash-thinking"))
            self.model_web2api.blockSignals(False)

    def on_save_config_clicked(self):
        # Stop debounce timer if active and save immediately
        if hasattr(self, 'save_settings_timer'):
            self.save_settings_timer.stop()
        self.save_settings()
        self.hide_settings()
        self.log_event("Settings saved successfully.", "success")
        QMessageBox.information(self, "Settings Saved", "Your configuration has been saved successfully.")

    def show_settings(self):
        self.log_event("Settings opened.", "info")
        self.settings_frame.show()
        self.tab_widget.hide()
        self.input_container.hide()
        # Sync settings and calculate stats asynchronously in the background for 0ms instant GUI opening
        QTimer.singleShot(10, self.sync_settings_to_ui)
        QTimer.singleShot(50, self.calculate_usage_statistics)
        
    def hide_settings(self):
        self.log_event("Settings closed.", "info")
        self.settings_frame.hide()
        self.tab_widget.show()
        self.input_container.show()
        if self.focus_mode == 'Background':
            hwnd = int(self.winId())
            GWL_EXSTYLE = -20
            WS_EX_NOACTIVATE = 0x08000000
            WS_EX_TRANSPARENT = 0x00000020
            ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style | WS_EX_NOACTIVATE | WS_EX_TRANSPARENT)
        
    def reset_to_default_models(self):
        self.model_gemini.setCurrentText("gemini-flash-latest")
        self.model_groq.setCurrentText("llama-3.3-70b-versatile")
        self.model_or.setCurrentText("google/gemini-2.0-flash:free")
        self.model_nv.setCurrentText("meta/llama-3.2-11b-vision-instruct")
        if hasattr(self, 'model_web2api'):
            self.model_web2api.setCurrentText("gemini-3.5-flash-thinking")
        self.save_settings()
        QMessageBox.information(self, "Models Reset", "Models reset to defaults and saved.")
        
    def reset_to_default_keys(self):
        try:
            from dotenv import load_dotenv
            env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
            load_dotenv(dotenv_path=env_path, override=True)
        except Exception:
            pass
        self.key_gemini.setText(os.environ.get("GEMINI_API_KEY", ""))
        self.key_groq.setText(os.environ.get("GROQ_API_KEY", ""))
        self.key_or.setText(os.environ.get("OPENROUTER_API_KEY", ""))
        self.key_nv.setText(os.environ.get("NVIDIA_API_KEY", ""))
        if hasattr(self, 'key_web2api'):
            self.key_web2api.setText(os.environ.get("WEB2API_API_KEY", "") or "http://localhost:8081/v1")
        self.save_settings()
        QMessageBox.information(self, "Keys Reset", "API Keys reloaded directly from .env file and saved.")


    def toggle_sidebar(self):
        if self.sidebar_frame.isVisible():
            self.sidebar_frame.hide()
        else:
            self.sidebar_frame.show()

    def load_settings(self):
        try:
            with open(self.get_settings_path(), "r") as f: return json.load(f)
        except Exception: return {}

    def save_settings_debounced(self):
        if not hasattr(self, 'save_settings_timer'):
            self.save_settings_timer = QTimer(self)
            self.save_settings_timer.setSingleShot(True)
            self.save_settings_timer.timeout.connect(self.save_settings)
        self.save_settings_timer.start(1000)

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
                "nvidia": self.key_nv.text().strip(),
                "web2api": self.key_web2api.text().strip() if hasattr(self, 'key_web2api') else self.api_keys.get("web2api", "http://localhost:8081/v1")
            }
        
        if hasattr(self, 'model_gemini'):
            self.provider_models = {
                "gemini": self.model_gemini.currentText().strip(),
                "groq": self.model_groq.currentText().strip(),
                "openrouter": self.model_or.currentText().strip(),
                "nvidia": self.model_nv.currentText().strip(),
                "web2api": self.model_web2api.currentText().strip() if hasattr(self, 'model_web2api') else self.provider_models.get("web2api", "gemini-3.5-flash-thinking")
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
        except Exception as e: logger.error("Failed to save settings: %s", e)
        
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

    def check_web2api_server_lifecycle(self):
        if getattr(self, "active_provider", "") == "Web2API":
            if hasattr(self, "embedded_web2api_server"):
                self.embedded_web2api_server.start()
        else:
            if hasattr(self, "embedded_web2api_server"):
                self.embedded_web2api_server.stop()

    def change_provider(self, text):
        self.active_provider = text
        self.check_web2api_server_lifecycle()
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
            text_color = "#000000"
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
            QTimer.singleShot(0, lambda: self.chat_history.verticalScrollBar().setValue(self.chat_history.verticalScrollBar().maximum()))
            if hasattr(self, 'scroll_bottom_btn'):
                self.scroll_bottom_btn.hide()
        else:
            # If the user is scrolled up and a message arrives, show the floating scroll down button
            if hasattr(self, 'scroll_bottom_btn'):
                self.scroll_bottom_btn.show()

    def on_tab_changed(self, index):
        if index >= 0 and self.tab_widget.tabText(index) == "+":
            self.open_new_empty_browser_tab()
            
        # If switching back to Chat (index 0) while in Background Mode, release focus and restore stealth click-through
        if index == 0 and getattr(self, 'focus_mode', '') == 'Background':
            hwnd = int(self.winId())
            GWL_EXSTYLE = -20
            WS_EX_NOACTIVATE = 0x08000000
            WS_EX_TRANSPARENT = 0x00000020
            ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style | WS_EX_NOACTIVATE | WS_EX_TRANSPARENT)
            try:
                ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0020)
                shell_hwnd = ctypes.windll.user32.GetShellWindow()
                if shell_hwnd:
                    ctypes.windll.user32.SetForegroundWindow(shell_hwnd)
            except Exception:
                pass

    def update_tab_buttons(self):
        bar = self.tab_widget.tabBar()
        for i in range(self.tab_widget.count()):
            if i == 0 or self.tab_widget.tabText(i) == "+":
                bar.setTabButton(i, QTabBar.RightSide, None)

    def toggle_browser_visibility(self):
        # Toggle browser tab visibility
        if self.tab_widget.currentIndex() > 0:
            self.last_browser_idx = self.tab_widget.currentIndex()
            self.tab_widget.setCurrentIndex(0)
            self.tab_widget.tabBar().setVisible(False)
        else:
            last_idx = getattr(self, 'last_browser_idx', 1)
            if self.tab_widget.count() > 1:
                self.tab_widget.tabBar().setVisible(True)
                if 1 <= last_idx < self.tab_widget.count() and self.tab_widget.tabText(last_idx) != "+":
                    self.tab_widget.setCurrentIndex(last_idx)
                else:
                    self.tab_widget.setCurrentIndex(1)
            else:
                self.open_new_empty_browser_tab()

    def open_new_empty_browser_tab(self):
        new_tab = self.create_empty_browser_tab()
        new_tab.load_url("https://duckduckgo.com")

    def create_empty_browser_tab(self, is_anonymous=False):
        from browser_tab import WebBrowserTab
        new_tab = WebBrowserTab(None, self, is_anonymous=is_anonymous)
        
        # Check if "+" tab exists at the end
        plus_idx = -1
        for i in range(self.tab_widget.count()):
            if self.tab_widget.tabText(i) == "+":
                plus_idx = i
                break
        
        if plus_idx != -1:
            idx = self.tab_widget.insertTab(plus_idx, new_tab, "Loading...")
        else:
            idx = self.tab_widget.addTab(new_tab, "Loading...")
            # Also append the "+" tab
            dummy = QWidget()
            self.tab_widget.addTab(dummy, "+")
            
        self.tab_widget.tabBar().setVisible(True)
        self.tab_widget.setCurrentIndex(idx)
        self.update_tab_buttons()
        return new_tab

    def open_in_mini_browser(self, url_str, is_anonymous=False):
        from browser_tab import WebBrowserTab
        new_tab = WebBrowserTab(url_str, self, is_anonymous=is_anonymous)
        
        # Check if "+" tab exists at the end
        plus_idx = -1
        for i in range(self.tab_widget.count()):
            if self.tab_widget.tabText(i) == "+":
                plus_idx = i
                break
                
        if plus_idx != -1:
            idx = self.tab_widget.insertTab(plus_idx, new_tab, "Loading...")
        else:
            idx = self.tab_widget.addTab(new_tab, "Loading...")
            # Also append the "+" tab
            dummy = QWidget()
            self.tab_widget.addTab(dummy, "+")
            
        self.tab_widget.tabBar().setVisible(True)
        self.tab_widget.setCurrentIndex(idx)
        self.update_tab_buttons()

    def toggle_browser_tab(self):
        """Toggle/Open embedded browser tab in stealth background mode."""
        curr_widget = self.tab_widget.currentWidget()
        if curr_widget and hasattr(curr_widget, 'browser'):
            # Return to chat tab
            self.tab_widget.setCurrentIndex(0)
        else:
            # Check if an existing browser tab is already open
            found_idx = -1
            for i in range(1, self.tab_widget.count()):
                w = self.tab_widget.widget(i)
                if hasattr(w, 'browser'):
                    found_idx = i
                    break
            if found_idx != -1:
                self.tab_widget.setCurrentIndex(found_idx)
            else:
                self.open_new_empty_browser_tab()

    def focus_browser_address_bar(self):
        """Focus the browser address bar in Background mode without breaking ghost click-through."""
        curr_widget = self.tab_widget.currentWidget()
        if not (curr_widget and hasattr(curr_widget, 'address_bar')):
            self.toggle_browser_tab()
            curr_widget = self.tab_widget.currentWidget()
            
        if curr_widget and hasattr(curr_widget, 'address_bar'):
            self._temp_focus_input(curr_widget.address_bar)
        
    def close_all_browser_tabs(self):
        """Completely destroys all browser tabs and returns to Chat."""
        if self.tab_widget.count() > 0:
            self.tab_widget.setCurrentIndex(0)
            
        for i in range(self.tab_widget.count() - 1, 0, -1):
            if self.tab_widget.tabText(i) != "+":
                self.close_tab(i)
                
        if self.tab_widget.count() == 2 and self.tab_widget.tabText(1) == "+":
            plus_widget = self.tab_widget.widget(1)
            self.tab_widget.removeTab(1)
            if plus_widget:
                plus_widget.deleteLater()
                
        self.tab_widget.tabBar().setVisible(False)
        if hasattr(self, 'close_all_tabs_btn'):
            self.close_all_tabs_btn.setVisible(False)

    def close_tab(self, index):
        if index == 0:
            return  # Protect chat history tab from closing
        if self.tab_widget.tabText(index) == "+":
            return  # Protect "+" tab from closing
            
        widget = self.tab_widget.widget(index)
        self.tab_widget.removeTab(index)
        if widget:
            if hasattr(widget, 'cleanup'):
                try:
                    widget.cleanup()
                except Exception:
                    pass
            widget.deleteLater()
            
        # If the only tabs left are Chat and "+", remove the "+" tab
        if self.tab_widget.count() == 2 and self.tab_widget.tabText(1) == "+":
            plus_widget = self.tab_widget.widget(1)
            self.tab_widget.removeTab(1)
            if plus_widget:
                plus_widget.deleteLater()
                
        if self.tab_widget.count() <= 1:
            self.tab_widget.tabBar().setVisible(False)
            self.tab_widget.setCurrentIndex(0)
        else:
            self.update_tab_buttons()

    def on_chat_link_clicked(self, url):
        url_str = url.toString()
        if url_str.startswith("http://") or url_str.startswith("https://"):
            self.open_in_mini_browser(url_str)
        elif url_str.startswith("inject:"):
            idx_str = url_str.replace("inject:", "")
            try:
                idx = int(idx_str)
                self.inject_code(idx + 1)
            except Exception as e:
                self.add_system_message(f"Injection failed: {e}")
        elif url_str.startswith("type:"):
            idx_str = url_str.replace("type:", "")
            try:
                idx = int(idx_str)
                self.type_code(idx + 1)
            except Exception as e:
                self.add_system_message(f"Typing failed: {e}")
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
                            <a href="copy:{code_index}" title="Copy code block to system clipboard" style="color: #58a6ff; text-decoration: none; font-weight: bold; margin-right: 12px;">📋 Copy</a>
                            <a href="inject:{code_index}" title="Fast Clipboard Inject (Hotkey: Alt+Z then {code_index + 1} then I)" style="color: #a5d6ff; text-decoration: none; font-weight: bold; margin-right: 12px;">⚡ Inject {code_index + 1}</a>
                            <a href="type:{code_index}" title="Hardware Character Typing (Hotkey: Alt+Z then {code_index + 1} then K)" style="color: #c084fc; text-decoration: none; font-weight: bold;">⌨️ Type {code_index + 1}</a>
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
            text_color = "#000000"
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
                    # Bypass expensive guess_lexer call on untagged blocks to prevent CPU thread lag
                    from pygments.lexers.special import TextLexer
                    lexer = TextLexer()
            except Exception:
                from pygments.lexers.special import TextLexer
                lexer = TextLexer()
                
            formatter = HtmlFormatter(nowrap=True, noclasses=True, style=style_name)
            return highlight(code_text, lexer, formatter)
        except Exception:
            import html as html_lib
            return html_lib.escape(code_text)
            
    def get_ai_message_html(self, text, provider_name="System"):
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
        
        temp_counter = 0
        
        for i, part in enumerate(parts):
            if i % 2 == 1:
                lines = part.split('\n', 1)
                lang = lines[0] if len(lines) > 1 else ""
                code = lines[1] if len(lines) > 1 else lines[0]
                
                clean_code = code.strip()
                cb_id = f"cb_stream_{temp_counter}"
                temp_counter += 1
                
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
                            <span style="font-weight: bold; color: {header_text};">{lang_display}</span>
                        </td>
                        <td align="right" style="padding: 8px 12px; font-family: 'Segoe UI', sans-serif; font-size: 13px;">
                            <span style="color: #71717a; font-style: italic; font-size: 11px;">Streaming...</span>
                        </td>
                    </tr>
                    <!-- Divider line -->
                    <tr>
                        <td colspan="2" height="1" style="background-color: {divider_color}; font-size: 1px;">&nbsp;</td>
                    </tr>
                """
                highlighted_code = self.highlight_code(clean_code, lang, self.is_dark)
                html_code += f"""
                <!-- Code Body -->
                <tr>
                    <td colspan="2" style="padding: 12px; font-family: Consolas, monospace; font-size: 13px; color: {code_color};">
                        <pre style="margin: 0; white-space: pre-wrap;">{highlighted_code}</pre>
                    </td>
                </tr>
                </table>
                """
                formatted_parts.append(html_code)
            else:
                escaped_part = html_lib.escape(part).replace('\n', '<br>')
                import re
                escaped_part = re.sub(r"\[IMAGE:\s*(file:///[^\]]+)\]", r"<img src='\1' width='400' style='border-radius: 10px; margin-top: 10px;'/>", escaped_part)
                formatted_parts.append(escaped_part)
                
        formatted_text = "".join(formatted_parts)
        
        provider_colors = {
            "gemini": "#10b981",
            "groq": "#f97316",
            "openrouter": "#a855f7",
            "google web search": "#3b82f6",
            "system": "#6b7280",
            "stealth ai": "#8b5cf6"
        }
        
        p_key = provider_name.lower().strip()
        provider_color = provider_colors.get(p_key, "#8b5cf6")
        
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
            ai_bg = f"rgba(24, 24, 27, {alpha})"
            text_color = "#e4e4e7"
            border_color = f"rgba(39, 39, 42, {alpha})"
        else:
            ai_bg = f"rgba(255, 255, 255, {alpha})"
            text_color = "#000000"
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
        return html
            
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
        self.last_interview_question = None
        self.update_style()
        
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
            if self.active_provider in ["Groq", "NVIDIA", "Gemini", "Web2API"]:
                pass
            else:
                if self.api_keys.get("gemini", "").strip():
                    self.active_provider = "Gemini"
                elif self.api_keys.get("groq", "").strip():
                    self.active_provider = "Groq"
                else:
                    self.active_provider = "NVIDIA"
            self.provider_combo.setCurrentText(self.active_provider)
            
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
            self.vision_loop_timer.start(2500) # Scan every 2.5 seconds
            
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
        if getattr(self, 'interview_mode', False) and not getattr(self, 'is_hidden', False):
            self.rainbow_hue = (getattr(self, 'rainbow_hue', 0) + 6) % 360
            import colorsys
            from PyQt5.QtGui import QColor
            r_f, g_f, b_f = colorsys.hsv_to_rgb(self.rainbow_hue / 360.0, 0.9, 1.0)
            self.interview_qcolor = QColor(int(r_f * 255), int(g_f * 255), int(b_f * 255))
            self.update()
            
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
        self.dictation_worker.status_signal.connect(self.on_interview_voice_status)
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
            
            if not hasattr(self, 'interview_voice_history'):
                self.interview_voice_history = []
            self.interview_voice_history.append(text)
            if len(self.interview_voice_history) > 5:
                self.interview_voice_history.pop(0)
            
            self.interview_voice_buffer = " ".join(self.interview_voice_history)
            
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
            
        # Run if screen changed, OR if voice context exists, OR if no question answered yet
        last_q = getattr(self, 'last_interview_question', None)
        if not img_changed and not voice_context and last_q is not None:
            return
            
        self.typing_dots = 0
        self.typing_label.setText("⚡ AI analyzing screen & voice...")
        self.typing_label.show()
        self.typing_timer.start(400)
        
        self.current_streaming_text = ""
        self.vision_message_inserted = False
        self.vision_streaming_buffer = ""
        
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
                
                self.vision_worker = VisionInterviewWorker(
                    image_data=b64_img,
                    voice_text=voice_context,
                    api_keys=self.api_keys,
                    active_provider=self.active_provider,
                    provider_models=self.provider_models
                )
                self.vision_worker.chunk_signal.connect(self.on_vision_chunk_received)
                self.vision_worker.result_signal.connect(self.on_vision_interview_result)
                self.vision_worker.start()
            except Exception as e:
                logger.warning("Failed to convert image to base64 in-memory: %s", e)
            
    def on_vision_chunk_received(self, chunk):
        if not hasattr(self, 'vision_streaming_buffer'):
            self.vision_streaming_buffer = ""
        self.vision_streaming_buffer += chunk
        
        if not hasattr(self, '_vision_update_timer'):
            self._vision_update_timer = QTimer(self)
            self._vision_update_timer.setSingleShot(True)
            self._vision_update_timer.timeout.connect(self._flush_vision_chunk_ui)
            
        if not self._vision_update_timer.isActive():
            self._vision_update_timer.start(30) # Throttle to 30ms

    def _flush_vision_chunk_ui(self):
        from PyQt5.QtGui import QTextCursor
        if not hasattr(self, 'vision_streaming_buffer'):
            self.vision_streaming_buffer = ""
        text = self.vision_streaming_buffer
        
        # Parse QUESTION and SOLUTION in real-time
        import re
        q_match = re.search(r'(?i)QUESTION:\s*(.*?)(?:\s*SOLUTION:|$)', text, re.DOTALL)
        s_match = re.search(r'(?i)SOLUTION:\s*(.*)', text, re.DOTALL)
        
        question_text = q_match.group(1).strip() if q_match else ""
        solution_text = s_match.group(1).strip() if s_match else ""
        
        if "NO_QUESTION" in text.upper():
            return
            
        display_text = ""
        if question_text:
            display_text += f"🎙️ **Interview Detected Question:** {question_text}\n\n"
        if solution_text:
            display_text += f"**Solution:**\n{solution_text}"
        elif not solution_text and question_text:
            display_text += "*Thinking of solution...*"
        else:
            display_text += text
            
        html = self.get_ai_message_html(display_text, "Stealth AI")
        
        if not getattr(self, 'vision_message_inserted', False):
            # Record the position before appending the first chunk
            cursor = QTextCursor(self.chat_history.document())
            cursor.movePosition(QTextCursor.End)
            self.vision_start_pos = cursor.position()
            
            # Append the first version of the message
            self.chat_history.append(html)
            self.vision_message_inserted = True
        else:
            # Replace the streaming message in-place
            cursor = QTextCursor(self.chat_history.document())
            cursor.setPosition(self.vision_start_pos)
            cursor.movePosition(QTextCursor.End, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()
            cursor.insertHtml(html)
            
        self.scroll_to_bottom(force=True)
            
    def on_vision_interview_result(self, question, solution):
        if hasattr(self, '_vision_update_timer') and self._vision_update_timer.isActive():
            self._vision_update_timer.stop()
        self._flush_vision_chunk_ui()
        if not getattr(self, 'interview_mode', False):
            return
            
        # Hide the compiling spinner label
        self.typing_timer.stop()
        self.typing_label.hide()
        
        if question == "NO_QUESTION":
            self.vision_streaming_buffer = ""
            self.vision_message_inserted = False
            self.render_current_session()
            if hasattr(self, 'preview_popup') and self.preview_popup:
                self.preview_popup.status_label.setText("👀 Monitoring (No question detected)")
            return
            
        # Deduplicate repeated questions
        import re
        last_q = getattr(self, 'last_interview_question', None)
        clean_new = re.sub(r'\s+', ' ', question).strip().lower()
        clean_last = re.sub(r'\s+', ' ', last_q).strip().lower() if last_q else ""
        if clean_new == clean_last:
            self.vision_streaming_buffer = ""
            self.vision_message_inserted = False
            self.render_current_session()
            if hasattr(self, 'preview_popup') and self.preview_popup:
                self.preview_popup.status_label.setText("👀 Monitoring (Question already answered)")
            return
            
        self.last_interview_question = question
        self.interview_voice_buffer = ""
        self.interview_voice_history = []
            
        if hasattr(self, 'preview_popup') and self.preview_popup:
            self.preview_popup.status_label.setText("💡 Answer Generated!")
            
        self.vision_streaming_buffer = ""
        self.vision_message_inserted = False

        # Display the result permanently in the chat box session
        self.add_command_message(f"🎙️ Interview Detected Question: {question}")
        self.add_ai_message(solution, provider_name="Stealth AI")
        
        # Trigger speech TTS if enabled or if in interview mode
        if getattr(self, 'voice_enabled', False) or getattr(self, 'interview_mode', False):
            import re
            clean_speech = re.sub(r'```[a-zA-Z]*\n[\s\S]*?```', '[code snippet skipped]', solution)
            clean_speech = re.sub(r'[*`#_]', '', clean_speech)
            clean_speech = clean_speech.replace("Approach 1:", "").replace("Approach 2:", "")
            self.speak_response(clean_speech)
            
    def on_interview_voice_error(self, err):
        if not getattr(self, 'interview_mode', False):
            return
        QTimer.singleShot(100, self.start_interview_listening)
        
    def on_interview_voice_status(self, status):
        if not getattr(self, 'interview_mode', False):
            return
        self.chat_input.setPlaceholderText(f"[🎙️ Interview: {status}]")

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
            
            if not hasattr(self, '_sct') or not self._sct:
                self._sct = mss.MSS()
                
            sct_img = self._sct.grab(monitor)
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            return img
        except Exception as e:
            logger.warning("Interview screen capture failed: %s", e)
            self._sct = None
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
        elif "web2api" in text_lower or "web2" in text_lower or "web 2" in text_lower:
            provider_target = "Web2API"
        elif "search" in text_lower or "google" in text_lower or "web search" in text_lower:
            provider_target = "Google Web Search"
            
        is_provider_cmd = False
        if provider_target:
            if has_model_change:
                is_provider_cmd = True
            elif any(prefix in text_lower for prefix in ["switch to", "use", "set provider to", "change to", "select", "open"]):
                is_provider_cmd = True
            elif text_lower in ["open router", "openrouter", "groq", "gemini", "google web search", "router", "web2api", "web2"]:
                is_provider_cmd = True
                
        if is_provider_cmd and provider_target:
            self.active_provider = provider_target
            index = self.provider_combo.findText(self.active_provider)
            if index >= 0:
                self.provider_combo.setCurrentIndex(index)
            self.update_style()
            self.add_command_message(f"⚙️ Action: Switched Provider to {self.active_provider}")
            return

        # 11. Click UI Buttons by Name
        click_cmds = {
            "browser": self.browser_btn,
            "focus chat": getattr(self, "focus_btn", None),
            "interview": getattr(self, "interview_btn", None),
            "speaker": getattr(self, "voice_btn", None),
            "voice typist": getattr(self, "single_mic_btn", None),
            "voice": getattr(self, "voice_select_btn", None),
            "model": getattr(self, "provider_btn", None),
            "provider": getattr(self, "provider_btn", None),
            "live chat": getattr(self, "mic_btn", None),
        }
        click_verbs = ["click", "open", "toggle", "start", "press", "go to"]
        if any(v in text_lower for v in ["close browser", "close all tabs", "close tabs"]):
            self.close_all_browser_tabs()
            self.add_command_message("⚙️ Action: Closed All Browser Tabs")
            return
        for btn_name, btn_widget in click_cmds.items():
            if btn_widget and btn_name in text_lower:
                if text_lower == btn_name or any(f"{v} {btn_name}" in text_lower for v in click_verbs):
                    if btn_widget == self.browser_btn:
                        self.toggle_browser_visibility()
                    else:
                        btn_widget.click()
                    self.add_command_message(f"⚙️ Action: Clicked '{btn_name.title()}' Button")
                    return

        # 12. Transparency / Opacity Settings Command
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

    def print_all_hotkeys_to_chat(self):
        color = "#8b5cf6" if getattr(self, 'is_dark', True) else "#6d28d9"
        bg_card = "#181524" if getattr(self, 'is_dark', True) else "#f8fafc"
        border_col = "rgba(139, 92, 246, 0.4)"
        text_col = "#e2e8f0" if getattr(self, 'is_dark', True) else "#1e293b"
        
        html = f"""
        <div style='background-color: {bg_card}; border: 1px solid {border_col}; border-radius: 10px; padding: 12px; margin: 10px 0; font-family: "Segoe UI", sans-serif; color: {text_col}; font-size: 11px;'>
            <div style='text-align: center; font-weight: bold; font-size: 13px; color: {color}; margin-bottom: 8px;'>
                ⚡ INVISIBLE AI — COMPLETE HOTKEYS & VOICE COMMANDS DIRECTORY
            </div>
            
            <table style='width: 100%; border-collapse: collapse; text-align: left; font-size: 11px;'>
                <tr style='border-bottom: 1px solid {border_col}; color: {color}; font-weight: bold;'>
                    <th style='padding: 4px;'>Shortcut / Command</th>
                    <th style='padding: 4px;'>Action Triggered</th>
                </tr>
                <tr style='border-bottom: 1px solid rgba(255,255,255,0.05);'>
                    <td style='padding: 4px;'><b>Alt + I</b></td>
                    <td style='padding: 4px;'>Target Code Block Injection</td>
                </tr>
                <tr style='border-bottom: 1px solid rgba(255,255,255,0.05);'>
                    <td style='padding: 4px;'><b>Alt + S</b></td>
                    <td style='padding: 4px;'>Screen Snipe & Vision OCR Extraction</td>
                </tr>
                <tr style='border-bottom: 1px solid rgba(255,255,255,0.05);'>
                    <td style='padding: 4px;'><b>Alt + K / Alt + T</b></td>
                    <td style='padding: 4px;'>Character Hardware Key Emulation Typing</td>
                </tr>
                <tr style='border-bottom: 1px solid rgba(255,255,255,0.05);'>
                    <td style='padding: 4px;'><b>Alt + W</b></td>
                    <td style='padding: 4px;'>Toggle Embedded Multi-Tab Browser Window</td>
                </tr>
                <tr style='border-bottom: 1px solid rgba(255,255,255,0.05);'>
                    <td style='padding: 4px;'><b>Alt + B</b></td>
                    <td style='padding: 4px;'>Focus Stealth Browser Address Bar</td>
                </tr>
                <tr style='border-bottom: 1px solid rgba(255,255,255,0.05);'>
                    <td style='padding: 4px;'><b>Alt + F</b></td>
                    <td style='padding: 4px;'>Toggle Focus Mode (Overlay vs Background)</td>
                </tr>
                <tr style='border-bottom: 1px solid rgba(255,255,255,0.05);'>
                    <td style='padding: 4px;'><b>Alt + P</b></td>
                    <td style='padding: 4px;'>Rotate AI Provider (Groq / Gemini / NVIDIA / Web2API)</td>
                </tr>
                <tr style='border-bottom: 1px solid rgba(255,255,255,0.05);'>
                    <td style='padding: 4px;'><b>Alt + M</b></td>
                    <td style='padding: 4px;'>Toggle Voice Dictation Microphone</td>
                </tr>
                <tr style='border-bottom: 1px solid rgba(255,255,255,0.05);'>
                    <td style='padding: 4px;'><b>Alt + V</b></td>
                    <td style='padding: 4px;'>Toggle TTS Audio Speaker Response</td>
                </tr>
                <tr style='border-bottom: 1px solid rgba(255,255,255,0.05);'>
                    <td style='padding: 4px;'><b>Alt + L</b></td>
                    <td style='padding: 4px;'>Toggle Mock Interview Listening Mode</td>
                </tr>
                <tr style='border-bottom: 1px solid rgba(255,255,255,0.05);'>
                    <td style='padding: 4px;'><b>Alt + Z</b></td>
                    <td style='padding: 4px;'>Toggle Command Leader Mode (Single-Key Shortcuts)</td>
                </tr>
                <tr style='border-bottom: 1px solid rgba(255,255,255,0.05);'>
                    <td style='padding: 4px;'><b>Alt + H</b></td>
                    <td style='padding: 4px;'>Minimize Overlay Window to Screen Edge</td>
                </tr>
                <tr style='border-bottom: 1px solid rgba(255,255,255,0.05);'>
                    <td style='padding: 4px;'><b>Alt + R</b></td>
                    <td style='padding: 4px;'>Reload Browser Page / Rotate AI Provider</td>
                </tr>
                <tr style='border-bottom: 1px solid rgba(255,255,255,0.05);'>
                    <td style='padding: 4px;'><b>Alt + Esc</b></td>
                    <td style='padding: 4px;'>Panic Boss Key (Emergency Hide & Sanitize)</td>
                </tr>
                <tr style='border-bottom: 1px solid rgba(255,255,255,0.05);'>
                    <td style='padding: 4px;'><b>Alt + / or Alt + ?</b></td>
                    <td style='padding: 4px;'>Print All Hotkeys & Voice Commands Directory</td>
                </tr>
                <tr>
                    <td style='padding: 4px;'><b>Voice Commands</b></td>
                    <td style='padding: 4px;'>Speak/type: <i>"type code"</i>, <i>"inject target"</i>, <i>"take screenshot"</i>, <i>"open browser"</i>, <i>"clear chat"</i>, <i>"use groq"</i>, <i>"print hotkeys"</i></td>
                </tr>
            </table>
        </div>
        """
        self.chat_history.append(html)
        self.scroll_to_bottom(force=True)
        self.log_event("Printed Complete Hotkeys & Voice Commands Directory to Chat", "success")

    def process_voice_or_text_command(self, text):
        if not text:
            return False
            
        import re
        raw = text.strip().lower()
        cleaned = re.sub(r'[^\w\s]', '', raw).strip()

        # Print All Hotkeys Directory Command
        if any(cleaned == k or cleaned.startswith(k + " ") for k in [
            "print hotkeys", "show hotkeys", "list hotkeys", "hotkey list", "all hotkeys", "hotkeys", "help", "shortcut list", "shortcuts", "print shortcuts"
        ]):
            self.print_all_hotkeys_to_chat()
            return True

        # --- 1. Top Header Bar Commands ---
        # Sidebar Menu (≡)
        if any(cleaned == k or cleaned.startswith(k + " ") for k in [
            "toggle sidebar", "open sidebar", "show sidebar", "hide sidebar", "close sidebar", "toggle sessions"
        ]):
            self.toggle_sidebar()
            self.add_system_message("≡ Voice/Text Action: <b>Toggled Sidebar Menu</b>.")
            self.log_event("Voice/Text Command: Toggled Sidebar Menu", "success")
            return True

        # Center Window (+ Drag)
        if any(cleaned == k or cleaned.startswith(k + " ") for k in [
            "center window", "reset position", "center overlay", "reposition window"
        ]):
            self.center_on_screen()
            self.add_system_message("🎯 Voice/Text Action: <b>Centered Overlay Window</b>.")
            self.log_event("Voice/Text Command: Centered Window", "success")
            return True

        # Theme Toggle (☀️ / 🌙)
        if any(cleaned == k or cleaned.startswith(k + " ") for k in [
            "toggle theme", "dark theme", "light theme", "switch theme", "light mode", "dark mode"
        ]):
            self.toggle_theme()
            self.add_system_message("🎨 Voice/Text Action: <b>Toggled Theme</b>.")
            self.log_event("Voice/Text Command: Toggled Theme", "success")
            return True

        # Focus Mode Toggle (🎯 Focus)
        if any(cleaned == k or cleaned.startswith(k + " ") for k in [
            "toggle focus", "switch focus", "overlay focus", "background focus", "focus mode"
        ]):
            self.toggle_focus_mode()
            self.add_system_message("🎯 Voice/Text Action: <b>Toggled Focus Mode</b>.")
            self.log_event("Voice/Text Command: Toggled Focus Mode", "success")
            return True

        # Alpha / Opacity Slider (Alpha: 100%)
        opacity_keywords = ["alpha", "opacity", "transparency", "transparent"]
        if any(kw in cleaned for kw in opacity_keywords):
            val = None
            word_num_map = {
                "zero": 0, "none": 0, "off": 0,
                "ten": 10, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "half": 50,
                "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100, "full": 100
            }
            m = re.search(r'\d+', cleaned)
            if m:
                val = int(m.group(0))
            else:
                for w, num in word_num_map.items():
                    if w in cleaned:
                        val = num
                        break
            if val is not None:
                val = max(1, min(100, val))
                self.change_opacity(val)
                self.add_system_message(f"👁️ Voice/Text Action: Set Opacity/Alpha to <b>{val}%</b>.")
                self.log_event(f"Voice/Text Command: Set Opacity to {val}%", "success")
                return True

        # Screen Scrap / OCR (✂️ Scrap)
        if any(cleaned == k or cleaned.startswith(k + " ") or cleaned.endswith(" " + k) for k in [
            "scrap", "snip screen", "crop screen", "scan screen", "ocr screen", "take screenshot", "capture screen", "screen snip", "start scan"
        ]):
            self.scan_screen()
            self.add_system_message("✂️ Voice/Text Action: Initiated <b>Screen Snipe & OCR</b>.")
            self.log_event("Voice/Text Command: Triggered Screen Snipe", "success")
            return True

        # Overlay Screenshot (📸 Shot)
        if any(cleaned == k or cleaned.startswith(k + " ") or cleaned.endswith(" " + k) for k in [
            "screenshot overlay", "shot overlay", "snap overlay", "window screenshot", "overlay shot", "overlay screenshot", "take overlay shot", "take shot"
        ]):
            self.capture_overlay_screenshot()
            self.log_event("Voice/Text Command: Triggered Overlay Screenshot", "success")
            return True

        # Embedded Browser (🌐 Browse)
        if any(cleaned == k or cleaned.startswith(k + " ") for k in [
            "open browser", "show browser", "toggle browser", "hide browser", "close browser", "browser"
        ]):
            self.toggle_browser_visibility()
            self.add_system_message("🌐 Voice/Text Action: <b>Toggled Embedded Browser</b>.")
            self.log_event("Voice/Text Command: Toggled Browser", "success")
            return True

        # New Browser Tab (➕ Tab)
        if any(cleaned == k or cleaned.startswith(k + " ") for k in [
            "new browser tab", "new tab", "open tab"
        ]):
            self.open_new_empty_browser_tab()
            self.add_system_message("➕ Voice/Text Action: <b>Opened New Browser Tab</b>.")
            self.log_event("Voice/Text Command: Opened New Browser Tab", "success")
            return True

        # Clear Chat History (🗑️ Clear)
        if any(cleaned == k or cleaned.startswith(k + " ") for k in [
            "clear chat", "clear history", "erase chat", "delete chat", "clean chat"
        ]):
            self.clear_chat()
            self.log_event("Voice/Text Command: Cleared Chat History", "success")
            return True

        # Hide / Minimize Window (— Hide)
        if any(cleaned == k or cleaned.startswith(k + " ") for k in [
            "hide overlay", "minimize overlay", "hide window", "minimize window", "hide"
        ]):
            self.minimize_to_edge()
            self.log_event("Voice/Text Command: Minimized Overlay Window", "success")
            return True

        # Exit Application (✕ Exit)
        if any(cleaned == k or cleaned.startswith(k + " ") for k in [
            "exit app", "close app", "exit application", "quit app", "exit"
        ]):
            self.add_system_message("👋 Voice/Text Action: <b>Exiting Invisible AI Overlay...</b>")
            self.log_event("Voice/Text Command: Triggered Application Exit", "error")
            QTimer.singleShot(500, self.force_exit)
            return True

        # --- 2. Bottom Toolbar & Feature Commands ---
        # Hardware Typing Mode (⌨️ Type)
        if any(cleaned == k or cleaned.startswith(k + " ") or cleaned.endswith(" " + k) for k in [
            "type code", "type this out", "type character", "type char", "hardware typing", "type out", "type text", "start typing"
        ]):
            self.type_code()
            self.add_system_message("⌨️ Voice/Text Action: Initiated <b>Hardware Typing Mode</b>.")
            self.log_event("Voice/Text Command: Triggered Hardware Typing", "success")
            return True

        # Code Injection Mode (🎯 Inject)
        if any(cleaned == k or cleaned.startswith(k + " ") or cleaned.endswith(" " + k) for k in [
            "inject code", "paste code", "inject target", "hardware paste", "copy code", "start inject"
        ]):
            self.inject_code()
            self.add_system_message("🎯 Voice/Text Action: Initiated <b>Code Injection Mode</b>.")
            self.log_event("Voice/Text Command: Triggered Code Injection", "success")
            return True

        # Stop Typing (⏸️ Stop)
        if any(cleaned == k or cleaned.startswith(k + " ") for k in [
            "stop typing", "pause typing", "abort typing", "cancel typing"
        ]):
            self.abort_injection = True
            self.add_system_message("⏸️ Voice/Text Action: <b>Typing stopped</b>.")
            self.log_event("Voice/Text Command: Stopped Typing", "ongoing")
            return True

        # AI Provider Selection (🤖 Provider Combo)
        if any(cleaned == k or cleaned.startswith(k + " ") for k in [
            "switch provider", "change model", "rotate provider", "next model", "switch model"
        ]):
            self.rotate_provider()
            self.log_event("Voice/Text Command: Rotated AI Provider", "success")
            return True

        if "groq" in cleaned and ("use" in cleaned or "switch" in cleaned or "select" in cleaned or "model" in cleaned):
            self.active_provider = "groq"
            self.provider_combo.setCurrentText("groq")
            self.add_system_message("🤖 Voice/Text Action: Switched AI Provider to <b>Groq</b>.")
            self.log_event("Voice/Text Command: Switched AI Provider to Groq", "success")
            return True

        if "gemini" in cleaned and ("use" in cleaned or "switch" in cleaned or "select" in cleaned or "model" in cleaned):
            self.active_provider = "gemini"
            self.provider_combo.setCurrentText("gemini")
            self.add_system_message("🤖 Voice/Text Action: Switched AI Provider to <b>Gemini</b>.")
            self.log_event("Voice/Text Command: Switched AI Provider to Gemini", "success")
            return True

        if "nvidia" in cleaned and ("use" in cleaned or "switch" in cleaned or "select" in cleaned or "model" in cleaned):
            self.active_provider = "nvidia"
            self.provider_combo.setCurrentText("nvidia")
            self.add_system_message("🤖 Voice/Text Action: Switched AI Provider to <b>NVIDIA</b>.")
            self.log_event("Voice/Text Command: Switched AI Provider to NVIDIA", "success")
            return True

        if "web2api" in cleaned and ("use" in cleaned or "switch" in cleaned or "select" in cleaned or "model" in cleaned):
            self.active_provider = "web2api"
            self.provider_combo.setCurrentText("web2api")
            self.add_system_message("🤖 Voice/Text Action: Switched AI Provider to <b>Web2API</b>.")
            self.log_event("Voice/Text Command: Switched AI Provider to Web2API", "success")
            return True

        # Speaker Audio Output Toggle (🔊 Speaker)
        if any(cleaned == k or cleaned.startswith(k + " ") for k in [
            "toggle speaker", "mute speaker", "unmute speaker", "speaker on", "speaker off", "enable speaker", "disable speaker"
        ]):
            if hasattr(self, 'speaker_btn'): self.speaker_btn.click()
            self.log_event("Voice/Text Command: Toggled Audio Speaker", "success")
            return True

        # Live Interview Mode (💬 Live Interview)
        if any(cleaned == k or cleaned.startswith(k + " ") for k in [
            "interview mode", "start interview", "stop interview", "mock interview", "live interview"
        ]):
            self.toggle_interview_mode()
            self.log_event("Voice/Text Command: Toggled Interview Mode", "success")
            return True

        # Voice Actor / TTS Voice Switching (Hazel Combo)
        if any(cleaned == k or cleaned.startswith(k + " ") for k in [
            "switch voice", "change voice", "rotate voice", "next voice"
        ]):
            self.rotate_voice()
            self.log_event("Voice/Text Command: Rotated Voice Engine", "success")
            return True

        # Push-To-Talk Mic (🎤 Voice Input)
        if any(cleaned == k or cleaned.startswith(k + " ") for k in [
            "voice input", "single mic", "listen once", "dictate"
        ]):
            if hasattr(self, 'start_single_voice'): self.start_single_voice()
            self.log_event("Voice/Text Command: Triggered Voice Dictation", "success")
            return True

        # Continuous Hands-Free Mic (🎙️ Live Voice)
        if any(cleaned == k or cleaned.startswith(k + " ") for k in [
            "live voice", "continuous mic", "mic on", "mic off", "start mic", "stop mic", "voice command center"
        ]):
            self.toggle_continuous_voice()
            self.log_event("Voice/Text Command: Toggled Continuous Mic", "success")
            return True

        # Copy Last AI Response / Code (📋 Copy)
        if any(cleaned == k or cleaned.startswith(k + " ") for k in [
            "copy response", "copy last response", "copy answer", "copy code snippet"
        ]):
            if hasattr(self, 'copy_last_code'):
                self.copy_last_code()
                self.add_system_message("📋 Voice/Text Action: <b>Copied latest AI response to clipboard</b>.")
                self.log_event("Voice/Text Command: Copied Response to Clipboard", "success")
                return True

        # Scroll Commands (📜 Scroll)
        if any(cleaned == k or cleaned.startswith(k + " ") for k in [
            "scroll down", "scroll to bottom", "go to bottom"
        ]):
            self.scroll_to_bottom(force=True)
            self.log_event("Voice/Text Command: Scrolled to Bottom", "success")
            return True

        if any(cleaned == k or cleaned.startswith(k + " ") for k in [
            "scroll up", "go to top"
        ]):
            self.chat_history.verticalScrollBar().setValue(0)
            self.log_event("Voice/Text Command: Scrolled to Top", "success")
            return True

        # Settings Dialog (⚙️ Settings)
        if any(cleaned == k or cleaned.startswith(k + " ") for k in [
            "open settings", "show settings", "open config", "settings"
        ]):
            self.show_settings_dialog()
            self.log_event("Voice/Text Command: Opened Settings Dialog", "success")
            return True

        # Panic Boss Key (🚨 Panic)
        if any(cleaned == k or cleaned.startswith(k + " ") for k in [
            "panic", "boss key", "hide everything", "emergency hide"
        ]):
            self.panic_boss_key()
            self.log_event("Voice/Text Command: Triggered Panic Boss Key", "error")
            return True

        return False

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
        
        # Check natural language voice & text system commands
        if text and not has_attachment:
            if self.process_voice_or_text_command(text):
                return
        
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
            
            if not hasattr(self, '_sct') or not self._sct:
                self._sct = mss.MSS()
            sct_img = self._sct.grab(monitor)
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
        providers = ["Gemini", "Groq", "OpenRouter", "NVIDIA", "Google Web Search", "Web2API"]
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
            
        low_space = w < 820
        
        self.sidebar_btn.setVisible(not low_space)
        self.theme_btn.setVisible(not low_space)
        self.focus_btn.setVisible(not low_space)
        self.opacity_label.setVisible(not low_space)
        self.slider.setVisible(not low_space)
        self.scrap_btn.setVisible(not low_space)
        if hasattr(self, 'overlay_snip_btn') and self.overlay_snip_btn:
            self.overlay_snip_btn.setVisible(not low_space)
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

    def moveEvent(self, event):
        super().moveEvent(event)
        if not getattr(self, 'is_hidden', False):
            self.cached_geometry = (self.x(), self.y(), self.width(), self.height())
            self.save_settings_debounced()

    def resizeEvent(self, event):
        self.cached_geometry = (self.x(), self.y(), self.width(), self.height())
        super().resizeEvent(event)
        if not getattr(self, 'is_hidden', False):
            self.save_settings_debounced()
        
        # Throttle layout updates during window resize to prevent Chromium/UI stuttering
        if not hasattr(self, 'resize_timer'):
            self.resize_timer = QTimer(self)
            self.resize_timer.setSingleShot(True)
            self.resize_timer.timeout.connect(self._deferred_resize_updates)
        self.resize_timer.start(16) # ~60 FPS throttle

    def _deferred_resize_updates(self):
        try:
            self.adjust_responsive_layout(self.width())
            self.align_preview_popup()
            self.save_settings_debounced()
            if hasattr(self, 'scroll_bottom_btn') and self.scroll_bottom_btn:
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
        self.sniper.raise_()
        self.sniper.activateWindow()

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
        gemini_key = self.api_keys.get("gemini", "").strip()
        nvidia_key = self.api_keys.get("nvidia", "").strip()
        chosen_model = self.provider_models.get("gemini", "gemini-flash-latest")
        
        self.ocr_worker = OCRWorker(gemini_key=gemini_key, nvidia_key=nvidia_key, pixmap_or_list=pixmap, chosen_model=chosen_model)
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

    def capture_overlay_screenshot(self):
        try:
            # Grab exact visual pixmap of overlay window and all its active components
            pixmap = self.grab()
            
            # 1. Copy to clipboard
            clipboard = QApplication.clipboard()
            clipboard.setPixmap(pixmap)
            
            # 2. Save PNG image directly to local folder (works on any PC & compiled .exe)
            if getattr(sys, 'frozen', False):
                base_dir = os.path.dirname(os.path.abspath(sys.executable))
            else:
                base_dir = os.path.dirname(os.path.abspath(__file__))
                
            save_dir = os.path.join(base_dir, "screenshots")
            try:
                if not os.path.exists(save_dir):
                    os.makedirs(save_dir)
            except Exception:
                # Fallback to User AppData if directory is read-only
                save_dir = os.path.join(get_app_dir(), "screenshots")
                if not os.path.exists(save_dir):
                    os.makedirs(save_dir)
                
            from datetime import datetime
            filename = f"overlay_shot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            filepath = os.path.join(save_dir, filename)
            pixmap.save(filepath, "PNG")
            
            msg = f"📸 Overlay screenshot captured ({pixmap.width()}x{pixmap.height()}px) & saved to clipboard and folder: {filepath}"
            self.add_system_message(msg)
            self.log_event(f"Overlay screenshot saved: {filepath}", "success")
        except Exception as e:
            err_msg = f"Overlay screenshot failed: {e}"
            self.add_system_message(f"<b style='color:red;'>Error:</b> {err_msg}")
            self.log_event(err_msg, "error")


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
        self.streaming_buffer = ""
        self.streaming_message_inserted = False
        self.worker.chunk_signal.connect(self.on_ai_chunk)
        self.worker.start()
        self.update_send_button_state(is_generating=True)
        
    def on_ai_chunk(self, chunk):
        self.streaming_buffer += chunk
        
        if not hasattr(self, '_ai_update_timer'):
            self._ai_update_timer = QTimer(self)
            self._ai_update_timer.setSingleShot(True)
            self._ai_update_timer.timeout.connect(self._flush_ai_chunk_ui)
            
        if not self._ai_update_timer.isActive():
            self._ai_update_timer.start(30) # Throttle to 30ms

    def _flush_ai_chunk_ui(self):
        from PyQt5.QtGui import QTextCursor
        provider_name = self.active_provider
        html = self.get_ai_message_html(self.streaming_buffer, provider_name)
        
        if not getattr(self, 'streaming_message_inserted', False):
            # Record the position before appending the first chunk
            cursor = QTextCursor(self.chat_history.document())
            cursor.movePosition(QTextCursor.End)
            self.stream_start_pos = cursor.position()
            
            # Append the first version of the message
            self.chat_history.append(html)
            self.streaming_message_inserted = True
        else:
            # Replace the streaming message in-place
            cursor = QTextCursor(self.chat_history.document())
            cursor.setPosition(self.stream_start_pos)
            cursor.movePosition(QTextCursor.End, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()
            cursor.insertHtml(html)
            
        self.scroll_to_bottom(force=True)
        
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
        if hasattr(self, '_ai_update_timer') and self._ai_update_timer.isActive():
            self._ai_update_timer.stop()
        self._flush_ai_chunk_ui()
        self.streaming_buffer = ""
        self.streaming_message_inserted = False
        self.render_current_session()
        
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
        if hasattr(self, '_ai_update_timer') and self._ai_update_timer.isActive():
            self._ai_update_timer.stop()
        self.streaming_buffer = ""
        self.streaming_message_inserted = False
        self.render_current_session()
        
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
                set_win32_clipboard(text_to_inject)
                self.add_system_message("🎯 Target code block updated & copied. Waiting for click...")
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
            
        # Copy to Win32 system clipboard immediately on arming
        set_win32_clipboard(text_to_inject)
        
        self.pending_inject_text = text_to_inject
        self.pending_inject_use_paste = True
        self.pending_inject_switch_focus = False
        self.waiting_for_inject_click = True
        import time
        self._inject_armed_time = time.time()
        self.add_system_message("🎯 Code copied! Click your target editor window (or press Ctrl+V) to inject...")

    def type_code(self, index=None):
        if getattr(self, 'injection_in_progress', False):
            self.add_system_message("<b style='color:orange;'>Warning:</b> An injection is already in progress. Please wait.")
            return
            
        if getattr(self, 'waiting_for_inject_click', False):
            text_to_inject = self.get_text_to_inject_by_index(index)
            if text_to_inject:
                self.pending_inject_text = text_to_inject
                self.pending_inject_use_paste = False
                self.add_system_message("⌨️ Target code block updated. Click target editor window to type character-by-character...")
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
        self.pending_inject_use_paste = False
        self.pending_inject_switch_focus = False
        self.waiting_for_inject_click = True
        import time
        self._inject_armed_time = time.time()
        self.add_system_message("⌨️ <b>Character Typing Mode:</b> Click your target editor window to type out character-by-character (bypasses paste blockers)...")

    def perform_stealth_injection(self, text, switch_focus):
        self.injection_in_progress = True
        self.injection_paused = False
        self.abort_injection = False
        self.initial_mouse_pos = QCursor.pos()
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
                user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0020)
                time.sleep(0.05)
                stealth_type_text(text, switch_focus)
            finally:
                self.injection_in_progress = False
                self.injection_paused = False
                # Restore original transparency and interactivity flags
                user32.SetWindowLongW(hwnd, GWL_EXSTYLE, orig_ex)
                user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0020)
                QTimer.singleShot(0, lambda: self.add_system_message("✅ Injection completed!"))
                
        t = threading.Thread(target=run_injection, daemon=True)
        t.start()

    def _stealth_inject(self, text, target_hwnd, use_paste=True):
        """Inject text into target editor using hardware-level keystroke simulation (cannot be blocked by sites)."""
        self.injection_in_progress = True
        self.injection_paused = False
        self.abort_injection = False
        self.initial_mouse_pos = QCursor.pos()
        msg = f"⌨️ Typing {len(text)} chars via hardware keys..." if not use_paste else f"⌨️ Injecting {len(text)} chars via hardware keys..."
        self.add_system_message(msg)
        
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
                user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0020)
                time.sleep(0.05)
                # Focus the target window and type
                stealth_type_text(text, switch_focus=False, target_hwnd=target_hwnd, use_paste=use_paste)
            finally:
                self.injection_in_progress = False
                self.injection_paused = False
                user32.SetWindowLongW(hwnd, GWL_EXSTYLE, orig_ex)
                user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0020)
                QTimer.singleShot(0, lambda: self.add_system_message("✅ Injection completed!"))
        
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
        if now - getattr(self, 'last_visibility_toggle_time', 0.0) < 0.25:
            return
        self.last_visibility_toggle_time = now
        
        if self.is_hidden: self.restore_from_edge()
        else: self.minimize_to_edge()

    def force_exit(self):
        # 1. Unhook low-level Win32 Hooks instantly to prevent exit hang
        try:
            if hasattr(self, 'mouse_hook_id') and self.mouse_hook_id:
                ctypes.windll.user32.UnhookWindowsHookEx(self.mouse_hook_id)
            if hasattr(self, 'keyboard_hook_id') and self.keyboard_hook_id:
                ctypes.windll.user32.UnhookWindowsHookEx(self.keyboard_hook_id)
        except Exception:
            pass
            
        # 2. Stop active workers instantly
        if getattr(self, 'stop_listening_fn', None):
            try: self.stop_listening_fn(wait_for_stop=False)
            except Exception: pass
        if hasattr(self, 'tts_worker') and self.tts_worker:
            try: self.tts_worker.stop()
            except Exception: pass
        for w_attr in ['worker', 'ocr_worker', 'dictation_worker']:
            if hasattr(self, w_attr):
                w = getattr(self, w_attr)
                if w and hasattr(w, 'isRunning') and w.isRunning():
                    try: w.terminate()
                    except Exception: pass

        # 3. Unregister Hotkeys
        hwnd = int(self.winId())
        for hk_id in range(1, 10):
            try: ctypes.windll.user32.UnregisterHotKey(hwnd, hk_id)
            except Exception: pass
            
        # 4. Save settings and quit instantly
        try: self.save_settings()
        except Exception: pass
        
        QApplication.quit()
        os._exit(0)
        
    def on_ghost_char(self, char):
        self.chat_input.setText(self.chat_input.text() + char)
        
    def on_ghost_backspace(self):
        text = self.chat_input.text()
        if text:
            self.chat_input.setText(text[:-1])
            
    def force_foreground_focus(self):
        """Steal foreground keyboard focus using Win32 AttachThreadInput (bypasses OS lockout)."""
        try:
            hwnd = int(self.winId())
            fore_hwnd = ctypes.windll.user32.GetForegroundWindow()
            fore_thread = ctypes.windll.user32.GetWindowThreadProcessId(fore_hwnd, None)
            app_thread = ctypes.windll.kernel32.GetCurrentThreadId()
            
            if fore_hwnd != hwnd:
                ctypes.windll.user32.AttachThreadInput(fore_thread, app_thread, True)
                ctypes.windll.user32.SetForegroundWindow(hwnd)
                ctypes.windll.user32.SetFocus(hwnd)
                ctypes.windll.user32.AttachThreadInput(fore_thread, app_thread, False)
            else:
                ctypes.windll.user32.SetForegroundWindow(hwnd)
            
            self.activateWindow()
            self.raise_()
            self.chat_input.setFocus()
        except Exception:
            try:
                hwnd = int(self.winId())
                ctypes.windll.user32.SetForegroundWindow(hwnd)
                self.activateWindow()
                self.raise_()
                self.chat_input.setFocus()
            except Exception:
                pass

    def trigger_panic_boss_key(self):
        """Panic Boss-Key (Alt+Esc): Instantly hide window, purge clipboard, and stop audio."""
        try:
            self.hide()
            self.is_hidden = True
            if hasattr(self, 'restore_bubble'):
                self.restore_bubble.hide()
            # Clear system clipboard
            QApplication.clipboard().clear()
            # Stop any ongoing speech
            if hasattr(self, 'tts_worker') and self.tts_worker:
                try: self.tts_worker.stop()
                except Exception: pass
            self.log_event("🚨 Panic Boss-Key triggered: Hidden & Clipboard Cleared.", "warning")
        except Exception as e:
            logger.error("Error in trigger_panic_boss_key: %s", e)

    def trigger_clipboard_auto_clear(self, delay_sec=5.0):
        """Schedules clipboard auto-purge after specified seconds to prevent anti-cheat inspection."""
        try:
            def _purge():
                QApplication.clipboard().clear()
                self.log_event("🧹 Clipboard auto-purged for anti-cheat safety.", "info")
            QTimer.singleShot(int(delay_sec * 1000), _purge)
        except Exception:
            pass

    def show_cheatsheet_overlay(self):
        """Prints Hotkey Cheat-Sheet directly into chat history (Alt+Z -> ? or Alt+Z -> H)."""
        try:
            cheatsheet_html = """
<div style='background-color: rgba(15, 23, 42, 0.85); border: 1.5px solid #38bdf8; border-radius: 8px; padding: 10px; margin: 4px 0;'>
  <b style='color: #38bdf8; font-size: 14px;'>⌨️ Leader Mode Shortcuts (Alt + Z then ...)</b><br><br>
  <b style='color: #a855f7;'>⚡ Code Injection & Action:</b><br>
  • <b>I</b> / <b>Space</b> : Inject Code into Target Window<br>
  • <b>K</b> / <b>T</b> : Type Code via Keyboard Emulation<br>
  • <b>1..9 + I/K</b> : Inject specific response code block #N<br>
  • <b>S</b> : Trigger Screen Sniper / OCR Scan<br>
  • <b>L</b> : Toggle Live Voice Interview Mode<br><br>
  <b style='color: #38bdf8;'>🎨 Mode & UI Controls:</b><br>
  • <b>P</b> : Cycle AI Provider (Gemini / Groq / NVIDIA)<br>
  • <b>F</b> / <b>B</b> : Toggle Focus / Ghost Mode<br>
  • <b>J</b> : Cycle Theme Preset (OLED Black / Glass / Midnight)<br>
  • <b>[ / ]</b> : Decrease / Increase Overlay Opacity (-5% / +5%)<br>
  • <b>?</b> / <b>H</b> : Print Hotkey Cheat-Sheet in Chat<br>
  • <b>Alt + Esc</b> : 🚨 <b>Panic Boss-Key</b> (Instant Hide & Sanitize Clipboard)
</div>
"""
            self.add_system_message(cheatsheet_html)
            self.log_event("⌨️ Hotkey cheat-sheet displayed in chat.", "info")
        except Exception as e:
            logger.error("Error displaying cheatsheet in chat: %s", e)

    def deactivate_ghost_mode(self):
        """Helper to deactivate Ghost Typing, restore stealth click-through, and update styling."""
        try:
            self.ghost_active = False
            hwnd = int(self.winId())
            GWL_EXSTYLE = -20
            WS_EX_NOACTIVATE = 0x08000000
            WS_EX_TRANSPARENT = 0x00000020
            
            ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            if getattr(self, 'focus_mode', 'Background') == 'Background':
                # Background mode: restore full stealth click-through
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style | WS_EX_NOACTIVATE | WS_EX_TRANSPARENT)
            else:
                # Overlay mode: remove both flags so window remains solid and interactive
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style & ~WS_EX_NOACTIVATE & ~WS_EX_TRANSPARENT)
            ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0020)
            
            self.update_style()
            self.log_event("Ghost typing deactivated.", "info")
            self.add_system_message("🔒 GHOST TYPING INACTIVE: Keystrokes restored to normal system output.")
        except Exception:
            pass

    def on_ghost_typing_toggled(self, active):
        if active:
            self.ghost_active = True
            self.update_style()
            
            hwnd = int(self.winId())
            GWL_EXSTYLE = -20
            WS_EX_NOACTIVATE = 0x08000000
            WS_EX_TRANSPARENT = 0x00000020
            
            # Remove WS_EX_NOACTIVATE but KEEP WS_EX_TRANSPARENT so empty spaces remain click-through
            ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, (ex_style & ~WS_EX_NOACTIVATE) | WS_EX_TRANSPARENT)
            ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0020)
            self.force_foreground_focus()
            self.log_event("Ghost typing activated.", "warning")
            self.add_system_message("⌨️ GHOST TYPING ACTIVE: Keystrokes will be redirected to the chat input and swallowed from the system. Press Esc or Alt+Z then K to exit.")
        else:
            self.deactivate_ghost_mode()


    def setup_global_hotkeys(self):
        if not hasattr(self, 'ghost_active'): self.ghost_active = False
        if not hasattr(self, 'leader_active'): self.leader_active = False
        if not hasattr(self, 'waiting_for_inject_click'): self.waiting_for_inject_click = False
        
        # Install low-level mouse hook to route mouse click and wheel events in Background mode.
        if not getattr(self, '_mouse_hook', None):
            try:
                WH_MOUSE_LL = 14
                self._mouse_callback = HOOKPROC(global_mouse_hook_callback)
                self._mouse_hook = ctypes.windll.user32.SetWindowsHookExW(
                    WH_MOUSE_LL, self._mouse_callback, 0, 0
                )
                if self._mouse_hook:
                    logger.info("Mouse hook registered successfully.")
            except Exception as e:
                logger.error("Failed to register low-level mouse hook: %s", e)

        # Install global low-level keyboard hook permanently to handle Alt shortcuts and Command Mode keys
        if not getattr(self, '_keyboard_hook', None):
            try:
                WH_KEYBOARD_LL = 13
                self._kb_callback = HOOKPROC(global_kb_hook_callback)
                self._keyboard_hook = ctypes.windll.user32.SetWindowsHookExW(
                    WH_KEYBOARD_LL, self._kb_callback, 0, 0
                )
                if self._keyboard_hook:
                    logger.info("Keyboard hook registered successfully.")
            except Exception as e:
                logger.error("Failed to register keyboard hook: %s", e)

    def is_pos_over_interactive_widget(self, gp):
        """Helper to detect if a global logical coordinate is directly over any interactive overlay widget."""
        try:
            if hasattr(self, 'slider') and self.slider.isVisible():
                slider_local = self.slider.mapFromGlobal(gp)
                if self.slider.rect().contains(slider_local):
                    return True

            if hasattr(self, 'settings_frame') and self.settings_frame.isVisible():
                sf_local = self.settings_frame.mapFromGlobal(gp)
                if self.settings_frame.rect().contains(sf_local):
                    return True

            if hasattr(self, 'chat_history') and self.chat_history.isVisible():
                chat_local = self.chat_history.mapFromGlobal(gp)
                if self.chat_history.rect().contains(chat_local):
                    # Vertical scrollbar region (rightmost 24 pixels)
                    if chat_local.x() >= self.chat_history.width() - 24:
                        return True

            widgets_to_check = [
                getattr(self, 'sidebar_btn', None),
                getattr(self, 'theme_btn', None),
                getattr(self, 'focus_btn', None),
                getattr(self, 'scrap_btn', None),
                getattr(self, 'browser_btn', None),
                getattr(self, 'clear_btn', None),
                getattr(self, 'hide_btn', None),
                getattr(self, 'close_btn', None),
                getattr(self, 'new_chat_btn', None),
                getattr(self, 'clear_all_btn', None),
                getattr(self, 'settings_sidebar_btn', None),
                getattr(self, 'scan_btn', None),
                getattr(self, 'inject_btn', None),
                getattr(self, 'voice_btn', None),
                getattr(self, 'interview_btn', None),
                getattr(self, 'single_mic_btn', None),
                getattr(self, 'mic_btn', None),
                getattr(self, 'send_btn', None),
                getattr(self, 'scroll_bottom_btn', None),
                getattr(self, 'provider_combo', None),
                getattr(self, 'voice_combo', None),
                getattr(self, 'chat_list', None),
                getattr(self, 'chat_input', None),
            ]

            for w in widgets_to_check:
                if w and w.isVisible():
                    local_p = w.mapFromGlobal(gp)
                    if w.rect().contains(local_p):
                        return True
            return False
        except Exception:
            return False

    def process_hook_click(self, cx=None, cy=None):
        try:
            # Negative cx = keyboard signal from keyboard hook
            if cx is not None and cx < 0 and cx != -999:
                vk = -cx
                self._dispatch_leader_key_from_vk(vk)
                return

            gp = QCursor.pos()

            # --- Hidden (docked) mode: restore bubble ---
            if getattr(self, 'is_hidden', False):
                if self.geometry().contains(gp):
                    self.restore_from_edge()
                return

            if getattr(self, 'focus_mode', '') != 'Background':
                return

            # Direct geometry check for opacity slider click (DPI-independent)
            if hasattr(self, 'slider') and self.slider.isVisible():
                slider_local = self.slider.mapFromGlobal(gp)
                if self.slider.rect().contains(slider_local):
                    val = int((slider_local.x() / self.slider.width()) * 100)
                    val = max(10, min(100, val))
                    self.change_opacity(val)
                    return

            # Direct geometry & child click routing for Settings Frame
            if hasattr(self, 'settings_frame') and self.settings_frame.isVisible():
                sf_local = self.settings_frame.mapFromGlobal(gp)
                if self.settings_frame.rect().contains(sf_local):
                    target = self.settings_frame.childAt(sf_local)
                    if target:
                        curr = target
                        while curr and curr != self.settings_frame:
                            if isinstance(curr, QPushButton):
                                curr.click()
                                return
                            elif isinstance(curr, QComboBox):
                                curr.showPopup()
                                return
                            elif isinstance(curr, QLineEdit):
                                QTimer.singleShot(0, lambda w=curr: self._temp_focus_input(w))
                                return
                            elif isinstance(curr, QListWidget):
                                item_p = curr.mapFromGlobal(gp)
                                item = curr.itemAt(item_p)
                                if item:
                                    curr.setCurrentItem(item)
                                    curr.itemClicked.emit(item)
                                return
                            elif isinstance(curr, QTextEdit):
                                curr.setFocus()
                                return
                            curr = curr.parentWidget()
                    return

            widgets_to_check = [
                getattr(self, 'sidebar_btn', None),
                getattr(self, 'theme_btn', None),
                getattr(self, 'focus_btn', None),
                getattr(self, 'scrap_btn', None),
                getattr(self, 'browser_btn', None),
                getattr(self, 'clear_btn', None),
                getattr(self, 'hide_btn', None),
                getattr(self, 'close_btn', None),
                getattr(self, 'new_chat_btn', None),
                getattr(self, 'clear_all_btn', None),
                getattr(self, 'settings_sidebar_btn', None),
                getattr(self, 'scan_btn', None),
                getattr(self, 'inject_btn', None),
                getattr(self, 'voice_btn', None),
                getattr(self, 'interview_btn', None),
                getattr(self, 'single_mic_btn', None),
                getattr(self, 'mic_btn', None),
                getattr(self, 'send_btn', None),
                getattr(self, 'scroll_bottom_btn', None),
                getattr(self, 'provider_combo', None),
                getattr(self, 'voice_combo', None),
                getattr(self, 'chat_list', None),
                getattr(self, 'chat_input', None),
            ]

            for w in widgets_to_check:
                if w and w.isVisible():
                    local_p = w.mapFromGlobal(gp)
                    if w.rect().contains(local_p):
                        if isinstance(w, QPushButton):
                            w.click()
                            return
                        elif isinstance(w, QComboBox):
                            w.showPopup()
                            return
                        elif isinstance(w, QListWidget):
                            item = w.itemAt(local_p)
                            if item:
                                w.setCurrentItem(item)
                                w.itemClicked.emit(item)
                            return
                        elif isinstance(w, QLineEdit):
                            if w == getattr(self, 'chat_input', None):
                                QTimer.singleShot(0, lambda: self.ghost_typing_signal.emit(True))
                            else:
                                QTimer.singleShot(0, lambda: self._temp_focus_input(w))
                            return
        except Exception:
            pass

    def _mouse_hook_callback_impl(self, nCode, wParam, lParam):
        """Instance-level low-level mouse hook callback — immune to garbage collection."""
        try:
            if nCode >= 0:
                # INSTANT RETURN: Filter out non-click/non-scroll mouse events immediately (like WM_MOUSEMOVE)
                # to prevent blocking the OS input thread and causing mouse lag.
                if wParam not in (0x0201, 0x0202, 0x0203, 0x020A, 0x0204):
                    return ctypes.windll.user32.CallNextHookEx(None, nCode, wParam, lParam)

                # Check if user armed code injection and clicked a target window/editor
                if wParam == 0x0201 and getattr(self, 'waiting_for_inject_click', False):
                    import time
                    now = time.time()
                    armed_time = getattr(self, '_inject_armed_time', 0)
                    if now - armed_time >= 0.05:
                        pt = POINT()
                        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
                        gp = QCursor.pos()
                        
                        overlay_rect = self.geometry()
                        if not overlay_rect.contains(gp):
                            self.waiting_for_inject_click = False
                            child_hwnd = ctypes.windll.user32.WindowFromPoint(pt)
                            child_hwnd_val = int(child_hwnd) if child_hwnd is not None else 0
                            
                            GA_ROOTOWNER = 3
                            root_target = ctypes.windll.user32.GetAncestor(child_hwnd, GA_ROOTOWNER) if child_hwnd_val else None
                            root_target_val = int(root_target) if root_target is not None else 0
                            
                            target_hwnd = root_target if root_target_val else child_hwnd
                            target_hwnd_val = int(target_hwnd) if target_hwnd is not None else 0
                            
                            overlay_hwnd = int(self.winId())
                            if target_hwnd_val == overlay_hwnd or root_target_val == overlay_hwnd:
                                target_hwnd = ctypes.windll.user32.GetForegroundWindow()
                                target_hwnd_val = int(target_hwnd) if target_hwnd is not None else 0
                                if target_hwnd_val == overlay_hwnd:
                                    target_hwnd = None
                                    
                            text = getattr(self, 'pending_inject_text', '')
                            use_p = getattr(self, 'pending_inject_use_paste', True)
                            if text:
                                QTimer.singleShot(80, lambda t=text, h=target_hwnd, p=use_p: self._stealth_inject(t, h, use_paste=p))
                            return ctypes.windll.user32.CallNextHookEx(None, nCode, wParam, lParam)

                if getattr(self, 'focus_mode', '') == 'Background' and not getattr(self, 'is_hidden', False):
                    gp = QCursor.pos()
                    
                    if wParam in (0x0201, 0x0204):  # WM_LBUTTONDOWN or WM_RBUTTONDOWN
                        if self.is_pos_over_interactive_widget(gp):
                            if wParam == 0x0201:
                                self.swallowed_mouse_down = True
                                QTimer.singleShot(0, lambda: self.bg_click_signal.emit(-999, -999))
                            return 1
                        else:
                            # Clicked on empty space while typing: restore click-through style synchronously
                            # so Windows can immediately pass this click through to the window underneath (e.g. IDE)
                            if getattr(self, 'ghost_active', False):
                                self.deactivate_ghost_mode()
                    elif wParam == 0x0202:  # WM_LBUTTONUP
                        if getattr(self, 'swallowed_mouse_down', False):
                            self.swallowed_mouse_down = False
                            return 1
                    elif wParam == 0x0203:  # WM_LBUTTONDBLCLK
                        if self.is_pos_over_interactive_widget(gp):
                            return 1
                    elif wParam == 0x020A:  # WM_MOUSEWHEEL
                        # Use physical coordinates to check window containment (100% DPI-independent)
                        hwnd = int(self.winId())
                        rect = RECT()
                        ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
                        
                        # Query the actual cursor position from the system (bypasses unpopulated touchpad info.pt)
                        pt = POINT()
                        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
                        px = pt.x
                        py = pt.y
                        
                        contains = (rect.left <= px < rect.right) and (rect.top <= py < rect.bottom)
                        info = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT))[0]
                        delta = ctypes.c_short((info.mouseData >> 16) & 0xFFFF).value
                        
                        if contains:
                            QTimer.singleShot(0, lambda d=delta, x=px, y=py: self._dispatch_bg_wheel(d, x, y))
                            return 1
        except Exception:
            pass
        return ctypes.windll.user32.CallNextHookEx(None, nCode, wParam, lParam)

    def _kb_hook_callback_impl(self, nCode, wParam, lParam):
        """Instance-level low-level keyboard hook callback — immune to garbage collection."""
        try:
            if nCode >= 0 and wParam in (0x100, 0x104):
                info = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT))[0]
                vk = int(info.vkCode)
                is_injected = bool(info.flags & 0x10) # LLKHF_INJECTED
                alt_pressed = bool(ctypes.windll.user32.GetAsyncKeyState(0x12) & 0x8000)
                
                # Check physical ESC key during typing to toggle Pause/Resume
                if not is_injected and getattr(self, 'injection_in_progress', False):
                    if vk == 0x1B and not alt_pressed: # Physical ESC key
                        self.injection_paused = not getattr(self, 'injection_paused', False)
                        if self.injection_paused:
                            QTimer.singleShot(0, lambda: self.add_system_message("⏸️ Hardware typing PAUSED. Press ESC again to resume..."))
                        else:
                            QTimer.singleShot(0, lambda: self.add_system_message("▶️ Resuming hardware typing..."))
                        return 1
                
                # Alt / Alt+Shift-based Global Hotkeys (Runs at all times, conflict-free)
                if alt_pressed:
                    if vk == 0x1B: # Alt + Esc (Panic Boss-Key & Auto-Sanitize)
                        QTimer.singleShot(0, lambda: (self.add_command_message("⌨️ Hotkey Triggered: <b>[Alt+Esc]</b> ➔ Panic Boss Key"), self.trigger_panic_boss_key()))
                        return 1
                    elif vk in (0x5A, 0x43): # Alt + Z or Alt + C (Toggle Command Mode)
                        QTimer.singleShot(0, lambda: (self.add_command_message("⌨️ Hotkey Triggered: <b>[Alt+Z]</b> ➔ Command Leader Mode"), self.toggle_leader_mode()))
                        return 1
                    elif vk == 0x57: # Alt + W / Alt + Shift + W (Toggle Browser Tab)
                        QTimer.singleShot(0, lambda: (self.add_command_message("⌨️ Hotkey Triggered: <b>[Alt+W]</b> ➔ Toggle Embedded Browser"), self.toggle_browser_tab()))
                        return 1
                    elif vk == 0x42: # Alt + B / Alt + Shift + B (Focus Stealth Address Bar)
                        QTimer.singleShot(0, lambda: (self.add_command_message("⌨️ Hotkey Triggered: <b>[Alt+B]</b> ➔ Focus Address Bar"), self.focus_browser_address_bar()))
                        return 1
                    elif vk == 0x53: # Alt + S / Alt + Shift + S (Screen Snipe / Vision)
                        QTimer.singleShot(0, lambda: (self.add_command_message("⌨️ Hotkey Triggered: <b>[Alt+S]</b> ➔ Screen Snipe & OCR"), self.scan_screen()))
                        return 1
                    elif vk == 0x49: # Alt + I / Alt + Shift + I (Hardware Inject)
                        QTimer.singleShot(0, lambda: (self.add_command_message("⌨️ Hotkey Triggered: <b>[Alt+I]</b> ➔ Target Code Injection"), self.inject_code()))
                        return 1
                    elif vk in (0x4B, 0x54): # Alt + K or Alt + T (Hardware Key Typing)
                        QTimer.singleShot(0, lambda: (self.add_command_message("⌨️ Hotkey Triggered: <b>[Alt+K / Alt+T]</b> ➔ Hardware Key Typing"), self.type_code()))
                        return 1
                    elif vk == 0x46: # Alt + F / Alt + Shift + F (Toggle Focus Mode)
                        QTimer.singleShot(0, lambda: (self.add_command_message("⌨️ Hotkey Triggered: <b>[Alt+F]</b> ➔ Toggle Focus Mode"), self.toggle_focus_mode()))
                        return 1
                    elif vk == 0x52: # Alt + R / Alt + Shift + R (Reload Browser Page / Rotate AI Provider)
                        curr_w = self.tab_widget.currentWidget() if hasattr(self, 'tab_widget') else None
                        if curr_w and hasattr(curr_w, 'refresh'):
                            QTimer.singleShot(0, lambda: (self.add_command_message("⌨️ Hotkey Triggered: <b>[Alt+R]</b> ➔ Reload Browser Page"), curr_w.refresh()))
                        else:
                            QTimer.singleShot(0, lambda: (self.add_command_message("⌨️ Hotkey Triggered: <b>[Alt+R]</b> ➔ Rotate AI Provider"), self.rotate_provider()))
                        return 1
                    elif vk == 0x4D: # Alt + M (Dictation / Live Mic)
                        QTimer.singleShot(0, lambda: (self.add_command_message("⌨️ Hotkey Triggered: <b>[Alt+M]</b> ➔ Dictation Mic"), self.mic_btn.click()))
                        return 1
                    elif vk == 0x56: # Alt + V (Toggle Speaker Voice)
                        QTimer.singleShot(0, lambda: (self.add_command_message("⌨️ Hotkey Triggered: <b>[Alt+V]</b> ➔ Toggle Audio Speaker"), self.toggle_voice()))
                        return 1
                    elif vk == 0x50: # Alt + P (Rotate AI Provider)
                        QTimer.singleShot(0, lambda: (self.add_command_message("⌨️ Hotkey Triggered: <b>[Alt+P]</b> ➔ Rotate AI Provider"), self.rotate_provider()))
                        return 1
                    elif vk == 0x25: # Alt + Left Arrow (Browser Back)
                        curr_w = self.tab_widget.currentWidget() if hasattr(self, 'tab_widget') else None
                        if curr_w and hasattr(curr_w, 'go_back'):
                            QTimer.singleShot(0, lambda: (self.add_command_message("⌨️ Hotkey Triggered: <b>[Alt+Left]</b> ➔ Browser Back"), curr_w.go_back()))
                            return 1
                    elif vk == 0x27: # Alt + Right Arrow (Browser Forward)
                        curr_w = self.tab_widget.currentWidget() if hasattr(self, 'tab_widget') else None
                        if curr_w and hasattr(curr_w, 'go_forward'):
                            QTimer.singleShot(0, lambda: (self.add_command_message("⌨️ Hotkey Triggered: <b>[Alt+Right]</b> ➔ Browser Forward"), curr_w.go_forward()))
                            return 1
                    elif vk == 0x26: # Alt + Up Arrow (Scroll Up)
                        QTimer.singleShot(0, lambda: self._dispatch_bg_wheel(160, 0, 0))
                        return 1
                    elif vk == 0x28: # Alt + Down Arrow (Scroll Down)
                        QTimer.singleShot(0, lambda: self._dispatch_bg_wheel(-160, 0, 0))
                        return 1
                    elif vk == 0x21: # Alt + Page Up
                        QTimer.singleShot(0, lambda: self._dispatch_bg_wheel(600, 0, 0))
                        return 1
                    elif vk == 0x22: # Alt + Page Down
                        QTimer.singleShot(0, lambda: self._dispatch_bg_wheel(-600, 0, 0))
                        return 1
                    elif vk == 0x4C: # Alt + L (Interview Mode)
                        if hasattr(self, 'toggle_interview_mode'):
                            QTimer.singleShot(0, lambda: (self.add_command_message("⌨️ Hotkey Triggered: <b>[Alt+L]</b> ➔ Mock Interview Mode"), self.toggle_interview_mode()))
                        else:
                            QTimer.singleShot(0, lambda: (self.add_command_message("⌨️ Hotkey Triggered: <b>[Alt+L]</b> ➔ Live Interview"), self.interview_btn.click()))
                        return 1
                    elif vk == 0x48: # Alt + H (Toggle Visibility)
                        QTimer.singleShot(0, lambda: (self.add_command_message("⌨️ Hotkey Triggered: <b>[Alt+H]</b> ➔ Minimize Window"), self.toggle_visibility_from_hotkey()))
                        return 1
                        
                # Command Mode Shortcuts (Runs only when Leader is Active)
                if getattr(self, 'leader_active', False):
                    VK_MAP_IDS = {
                        0x48, 0x20, 0x53, 0x49, 0x4B, 0x54, 0x50, 0x4F, 0x55, 0x4D, 0x4C, 0x56,
                        0x45, 0x1B, 0x25, 0x26, 0x27, 0x28, 0x0D,
                        0x30, 0x31, 0x32, 0x33, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, # 0..9
                        0x46, 0x58, 0x43, 0x44, 0x42, 0x4E, 0x47, 0x57, 0x4A, # F, X, C, D, B, N, G, W, J
                        0xDB, 0xDD, 0xBF, 0x50 # [, ], ?, P
                    }
                    if vk in VK_MAP_IDS:
                        QTimer.singleShot(0, lambda v=vk: self._dispatch_leader_key_from_vk(v))
                        return 1
        except Exception:
            pass
        return ctypes.windll.user32.CallNextHookEx(None, nCode, wParam, lParam)

    def find_widget_at_pos(self, global_pos):
        """Recursively find the deepest child widget at global_pos (logical coordinates) bypassing WS_EX_TRANSPARENT."""
        debug_lines = []
        def find_widget_at(widget, gp):
            if not widget.isVisible():
                return None
            widget_global_rect = QRect(widget.mapToGlobal(QPoint(0, 0)), widget.size())
            contains = widget_global_rect.contains(gp)
            debug_lines.append(f"Widget {widget.__class__.__name__} (objName={widget.objectName()}): rect={widget_global_rect.x()},{widget_global_rect.y()} w={widget_global_rect.width()} h={widget_global_rect.height()} -> contains={contains}")
            if not contains:
                return None
            for child in reversed(widget.children()):
                if isinstance(child, QWidget):
                    found = find_widget_at(child, gp)
                    if found:
                        return found
            return widget
        try:
            res = find_widget_at(self, global_pos)
            with open("d:/invisibleai/click_debug.txt", "a", encoding="utf-8") as df:
                df.write(f"=== find_widget_at_pos query for {global_pos.x()},{global_pos.y()} ===\n")
                df.write("\n".join(debug_lines) + "\n")
                df.write(f"Result: {res}\n\n")
            return res
        except Exception as e:
            with open("d:/invisibleai/click_debug.txt", "a", encoding="utf-8") as df:
                df.write(f"find_widget_at_pos EXCEPTION: {e}\n")
            return None

    def _dispatch_bg_wheel(self, delta, px, py):
        """Handles mouse wheel scrolling in Background/Ghost mode (DPI-independent)."""
        try:
            # Check if over opacity slider using physical screen coordinates
            if hasattr(self, 'slider') and self.slider.isVisible():
                hwnd_slider = int(self.slider.winId())
                rect_slider = RECT()
                ctypes.windll.user32.GetWindowRect(hwnd_slider, ctypes.byref(rect_slider))
                if (rect_slider.left <= px < rect_slider.right) and (rect_slider.top <= py < rect_slider.bottom):
                    current = self.slider.value()
                    step = 5 if delta > 0 else -5
                    new_val = max(10, min(100, current + step))
                    self.change_opacity(new_val)
                    return
                    
            # Check if active tab is a WebBrowserTab — scroll the browser page smoothly in Background mode
            curr_widget = self.tab_widget.currentWidget() if hasattr(self, 'tab_widget') else None
            if curr_widget and hasattr(curr_widget, 'browser') and curr_widget.browser:
                scroll_amount = -160 if delta > 0 else 160
                js = f"window.scrollBy({{top: {scroll_amount}, behavior: 'smooth'}});"
                curr_widget.browser.page().runJavaScript(js)
                return

            # If Chat tab (index 0) is active, scroll the chat history directly
            if hasattr(self, 'chat_history') and self.chat_history.isVisible():
                if hasattr(self, 'tab_widget') and self.tab_widget.currentIndex() == 0:
                    self.scroll_chat(delta)
                    return
        except Exception as e:
            logger.debug("Error in _dispatch_bg_wheel: %s", e)

    def _flush_cmd_number_buffer(self, action="inject"):
        if hasattr(self, 'cmd_number_timer') and self.cmd_number_timer.isActive():
            self.cmd_number_timer.stop()
        buf = getattr(self, 'cmd_number_buffer', '')
        self.cmd_number_buffer = ""
        if buf:
            try:
                num = int(buf)
                if num > 0:
                    if action == "type":
                        self.type_code(num)
                    else:
                        self.inject_code(num)
            except Exception:
                pass

    def _flush_leader_number_buffer(self, action="inject"):
        if hasattr(self, '_leader_num_timer') and self._leader_num_timer.isActive():
            self._leader_num_timer.stop()
        buf = getattr(self, 'leader_number_buffer', '')
        self.leader_number_buffer = ""
        if buf:
            try:
                num = int(buf)
                if num > 0:
                    self.leader_active = False
                    self._apply_leader_state()
                    if action == "type":
                        self.type_code(num)
                    else:
                        self.inject_code(num)
            except Exception:
                pass

    def _dispatch_leader_key_from_vk(self, vk):
        """Called (deferred) from keyboard hook in Command Mode — dispatches leader key action."""
        try:
            if not getattr(self, 'leader_active', False):
                return
            VK_H = 0x48; VK_SPACE = 0x20; VK_S = 0x53; VK_I = 0x49; VK_K = 0x4B
            VK_P = 0x50; VK_O = 0x4F; VK_U = 0x55; VK_M = 0x4D
            VK_L = 0x4C; VK_V = 0x56; VK_E = 0x45; VK_ESC = 0x1B
            VK_LEFT = 0x25; VK_UP = 0x26; VK_RIGHT = 0x27; VK_DOWN = 0x28
            VK_RETURN = 0x0D
            
            # Tooltip-aligned shortcuts
            VK_F = 0x46; VK_X = 0x58; VK_T = 0x54; VK_C = 0x43; VK_D = 0x44
            VK_B = 0x42; VK_N = 0x4E; VK_G = 0x47; VK_W = 0x57
            VK_LBRACKET = 0xDB; VK_RBRACKET = 0xDD
            
            VK_J = 0x4A
            
            # Arrow key movement & resizing in Command Mode
            if vk in (VK_LEFT, VK_UP, VK_RIGHT, VK_DOWN):
                # Check if Ctrl key is held down (0x11 is VK_CONTROL)
                ctrl_held = bool(ctypes.windll.user32.GetAsyncKeyState(0x11) & 0x8000)
                geom = self.geometry()
                x, y, w, h = geom.x(), geom.y(), geom.width(), geom.height()
                
                if ctrl_held:
                    # Resize
                    step = 15
                    if vk == VK_LEFT:
                        w = max(200, w - step)
                    elif vk == VK_RIGHT:
                        w = min(1920, w + step)
                    elif vk == VK_UP:
                        h = max(200, h - step)
                    elif vk == VK_DOWN:
                        h = min(1080, h + step)
                    self.resize(w, h)
                else:
                    # Move
                    step = 10
                    if vk == VK_LEFT:
                        x -= step
                    elif vk == VK_RIGHT:
                        x += step
                    elif vk == VK_UP:
                        y -= step
                    elif vk == VK_DOWN:
                        y += step
                    self.move(x, y)
                return

            if vk == VK_RETURN:
                if getattr(self, 'leader_number_buffer', ''):
                    self._flush_leader_number_buffer()
                return

            if 0x30 <= vk <= 0x39: # Digits 0-9
                digit = str(vk - 0x30)
                if not hasattr(self, 'leader_number_buffer'):
                    self.leader_number_buffer = ""
                self.leader_number_buffer += digit
                
                self.add_system_message(f"🔢 Code Block Selection: <b>#{self.leader_number_buffer}</b> (Press I/Space to Inject, T/K to Type)")
                
                if not hasattr(self, '_leader_num_timer'):
                    self._leader_num_timer = QTimer(self)
                    self._leader_num_timer.setSingleShot(True)
                    self._leader_num_timer.timeout.connect(self._flush_leader_number_buffer)
                else:
                    self._leader_num_timer.stop()
                self._leader_num_timer.start(1200)
                return

            # If a number buffer is active and another command key is pressed
            if getattr(self, 'leader_number_buffer', ''):
                if vk in (VK_K, VK_T):
                    self._flush_leader_number_buffer(action="type")
                    return
                elif vk in (VK_SPACE, VK_I, VK_RETURN):
                    self._flush_leader_number_buffer(action="inject")
                    return

            if vk in (VK_H, VK_SPACE):
                self.leader_active = False
                self._apply_leader_state()
                self.minimize_to_edge()
            elif vk == VK_S:
                self.scan_screen()
            elif vk == VK_I:
                self.leader_active = False
                self._apply_leader_state()
                self.inject_code()
            elif vk in (VK_K, VK_T):
                self.leader_active = False
                self._apply_leader_state()
                self.type_code()
            elif vk in (VK_ESC,):
                self.leader_number_buffer = ""
                self.leader_active = False
                self._apply_leader_state()
            elif vk in (0xBF, VK_H): # ? or H key
                self.leader_active = False
                self._apply_leader_state()
                self.show_cheatsheet_overlay()
            elif vk == VK_P:
                self.rotate_provider()
            elif vk == VK_O:
                self.rotate_voice()
            elif vk == VK_U:
                self.start_single_voice()
            elif vk == VK_V:
                self.toggle_voice()
            elif vk == VK_L:
                self.toggle_interview_mode()
            elif vk == VK_M:
                self.mic_btn.click()
            elif vk == VK_D:
                self.handle_chat()
            elif vk == VK_F:
                self.toggle_focus_mode()
            elif vk == VK_X:
                self.force_exit()
            elif vk == VK_J:
                self.toggle_theme()
            elif vk == VK_C:
                self.clear_chat()
            elif vk == VK_B:
                self.toggle_sidebar()
            elif vk == VK_N:
                self.new_chat()
            elif vk == VK_G:
                self.open_settings_dialog()
            elif vk == VK_W:
                self.toggle_browser_tab()
            elif vk == VK_E:
                self.leader_active = False
                self._apply_leader_state()
                self.ghost_typing_signal.emit(True)
            elif vk == VK_LBRACKET:
                current = self.slider.value()
                new_val = max(10, current - 5)
                self.change_opacity(new_val)
            elif vk == VK_RBRACKET:
                current = self.slider.value()
                new_val = min(100, current + 5)
                self.change_opacity(new_val)
        except Exception as e:
            logger.debug("_dispatch_leader_key_from_vk error: %s", e)

    def show_cheatsheet_overlay(self):
        """Displays an interactive, beautiful Help, Tutorial & Hotkey Cheatsheet Card."""
        try:
            from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTextBrowser, QPushButton, QHBoxLayout, QLabel
            dlg = QDialog(self)
            dlg.setWindowTitle("Invisible AI - Complete Help, Tutorials & Hotkeys Guide")
            dlg.setFixedSize(620, 520)
            dlg.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Dialog)
            
            dlg.setStyleSheet("""
                QDialog {
                    background-color: #0f172a;
                    color: #f8fafc;
                    border: 1.5px solid #8b5cf6;
                    border-radius: 12px;
                }
                QTextBrowser {
                    background-color: #1e293b;
                    color: #f1f5f9;
                    border: 1px solid #334155;
                    border-radius: 8px;
                    font-family: 'Segoe UI', sans-serif;
                    font-size: 12px;
                    padding: 10px;
                }
                QPushButton {
                    background-color: #8b5cf6;
                    color: #ffffff;
                    border: none;
                    border-radius: 6px;
                    padding: 6px 16px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #7c3aed;
                }
            """)
            
            layout = QVBoxLayout(dlg)
            layout.setContentsMargins(16, 16, 16, 16)
            
            header_layout = QHBoxLayout()
            title = QLabel("🎓 Invisible AI — Complete Tutorial & Hotkey Guide")
            title.setStyleSheet("font-size: 15px; font-weight: bold; color: #a78bfa;")
            header_layout.addWidget(title)
            header_layout.addStretch()
            
            close_top = QPushButton("✕")
            close_top.setFixedSize(24, 24)
            close_top.clicked.connect(dlg.close)
            header_layout.addWidget(close_top)
            layout.addLayout(header_layout)
            
            tb = QTextBrowser()
            tb.setOpenExternalLinks(True)
            html = """
            <h3 style="color:#38bdf8; margin-top:0;">🚀 Beginner Quick-Start Guide</h3>
            <ol>
                <li><b>Background Stealth Mode</b> (Default): The window is a 100% click-through ghost window. Clicks pass through to your IDE/browser underneath without focus triggers.</li>
                <li><b>Command Mode (Leader Key)</b>: Press <code>Alt + Z</code> or <code>Alt + C</code> to activate single-key command mode. The border glows purple.</li>
                <li><b>Screen Snipe / OCR</b>: Press <code>Alt + S</code> (or <code>Leader -> S</code>) to capture a screen region and extract text/code.</li>
                <li><b>Hardware Inject Solution</b>: Click into your active code editor/input box and press <code>Alt + I</code> (or <code>Leader -> I</code>) to hardware-type the answer into your target app!</li>
            </ol>
            
            <h3 style="color:#38bdf8;">🌐 Embedded Stealth Browser Mode</h3>
            <ul>
                <li><b>Toggle Browser Tab</b>: Press <code>Alt + W</code> (or <code>Leader -> W</code>)</li>
                <li><b>Focus Stealth Address Bar</b>: Press <code>Alt + B</code> (or <code>Leader -> B</code>)</li>
                <li><b>Scroll Web Page</b>: Scroll mouse wheel directly over the browser tab.</li>
                <li><b>Back & Forward Navigation</b>: <code>Alt + Left Arrow</code> / <code>Alt + Right Arrow</code></li>
                <li><b>Reload Web Page</b>: Press <code>Alt + R</code></li>
            </ul>
            
            <h3 style="color:#38bdf8;">⌨️ Complete Deduplicated Hotkeys Reference</h3>
            <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse; border-color:#334155; width:100%;">
                <tr style="background-color:#0f172a; color:#a78bfa;">
                    <th>Action</th><th>Direct Global Hotkey</th><th>Leader Shortcut (Alt+Z)</th>
                </tr>
                <tr><td>Toggle Command Mode</td><td><code>Alt + Z</code> / <code>Alt + C</code></td><td>—</td></tr>
                <tr><td>Toggle Browser Tab</td><td><code>Alt + W</code></td><td><code>W</code></td></tr>
                <tr><td>Focus Address Bar</td><td><code>Alt + B</code></td><td><code>B</code></td></tr>
                <tr><td>Screen Snipe / OCR</td><td><code>Alt + S</code></td><td><code>S</code></td></tr>
                <tr><td>Hardware Inject Code</td><td><code>Alt + I</code></td><td><code>I</code> or <code>Space</code></td></tr>
                <tr><td>Hardware Key Typing</td><td><code>Alt + K</code> / <code>Alt + T</code></td><td><code>K</code> / <code>T</code></td></tr>
                <tr><td>Inject Code Block #N</td><td>—</td><td><code>1..9</code> then <code>I</code></td></tr>
                <tr><td>Toggle Focus Mode</td><td><code>Alt + F</code></td><td><code>F</code></td></tr>
                <tr><td>Rotate AI Provider</td><td><code>Alt + P</code> / <code>Alt + R</code></td><td><code>P</code></td></tr>
                <tr><td>Toggle Speaker Voice</td><td><code>Alt + V</code></td><td><code>V</code></td></tr>
                <tr><td>Start Dictation Mic</td><td><code>Alt + M</code></td><td><code>M</code> / <code>U</code></td></tr>
                <tr><td>Interview Mode</td><td><code>Alt + L</code></td><td><code>L</code></td></tr>
                <tr><td>Toggle Theme</td><td>—</td><td><code>J</code></td></tr>
                <tr><td>Clear Chat</td><td>—</td><td><code>C</code></td></tr>
                <tr><td>New Chat Tab</td><td>—</td><td><code>N</code></td></tr>
                <tr><td>Adjust Opacity</td><td>Mouse Wheel</td><td><code>[</code> / <code>]</code></td></tr>
                <tr><td>Move Window</td><td>Drag Header</td><td><code>Arrow Keys</code></td></tr>
                <tr><td>Resize Window</td><td>Drag Edges</td><td><code>Ctrl + Arrow Keys</code></td></tr>
                <tr><td>Panic Boss Key</td><td><code>Alt + Esc</code></td><td><code>Esc</code></td></tr>
            </table>
            
            <h3 style="color:#38bdf8;">💡 Advanced Stealth Tips</h3>
            <ul>
                <li><b>Zero Detection Safety Abort</b>: Moving your mouse more than 50px or pressing <code>Esc</code> while hardware-typing immediately aborts key injection to prevent accidental leakage.</li>
                <li><b>Human Cadence Simulation</b>: Key typing inserts random micro-delays (0.015s-0.045s) matching human rhythm to pass proctored environment checks.</li>
                <li><b>Root Window Tracking</b>: The injection engine matches <code>GetAncestor(GA_ROOTOWNER=3)</code> so editor popups or tooltips won't abort your typing stream.</li>
            </ul>
            """
            tb.setHtml(html)
            layout.addWidget(tb)
            
            btn_box = QHBoxLayout()
            btn_box.addStretch()
            ok_btn = QPushButton("Got It!")
            ok_btn.clicked.connect(dlg.close)
            btn_box.addWidget(ok_btn)
            layout.addLayout(btn_box)
            
            dlg.exec_()
        except Exception as e:
            logger.warning("Error displaying cheatsheet overlay: %s", e)

    def _temp_focus_input(self, widget):
        """Temporarily make the overlay interactive so the user can type in an input field."""
        try:
            hwnd = int(self.winId())
            GWL_EXSTYLE = -20
            WS_EX_NOACTIVATE = 0x08000000
            WS_EX_TRANSPARENT = 0x00000020
            ex = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            # Remove NOACTIVATE but KEEP TRANSPARENT so window is click-through on empty space
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE,
                (ex & ~WS_EX_NOACTIVATE) | WS_EX_TRANSPARENT)
            ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                0x0001 | 0x0002 | 0x0004 | 0x0020)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            widget.setFocus()
        except Exception:
            pass

    def closeEvent(self, event):
        if hasattr(self, "embedded_web2api_server"):
            try: self.embedded_web2api_server.stop()
            except Exception: pass
        # Uninstall permanent mouse hook
        if getattr(self, '_mouse_hook', None):
            try:
                ctypes.windll.user32.UnhookWindowsHookEx(self._mouse_hook)
            except Exception: pass
        # Uninstall permanent keyboard hook
        if getattr(self, '_keyboard_hook', None):
            try:
                ctypes.windll.user32.UnhookWindowsHookEx(self._keyboard_hook)
            except Exception: pass
        try:
            hwnd = int(self.winId())
            ctypes.windll.user32.UnregisterHotKey(hwnd, 1)
        except Exception: pass
        try:
            hwnd = int(self.winId())
            ctypes.windll.user32.UnregisterHotKey(hwnd, 2)
        except Exception: pass
        try:
            hwnd = int(self.winId())
            ctypes.windll.user32.UnregisterHotKey(hwnd, 3)
        except Exception: pass
        try:
            hwnd = int(self.winId())
            ctypes.windll.user32.UnregisterHotKey(hwnd, 4)
        except Exception: pass
        self.force_exit()
        
    def nativeEvent(self, eventType, message):
        try:
            if eventType == "windows_generic_MSG":
                msg = ctypes.wintypes.MSG.from_address(int(message))
                
                if msg.message == 0x0084: # WM_NCHITTEST
                    if getattr(self, 'focus_mode', '') == 'Background' or getattr(self, 'is_hidden', False):
                        x = msg.lParam & 0xFFFF
                        if x > 32767: x -= 65536
                        y = (msg.lParam >> 16) & 0xFFFF
                        if y > 32767: y -= 65536
                        gp = QPoint(x, y)
                        
                        is_solid = False
                        if getattr(self, 'is_hidden', False):
                            if hasattr(self, 'restore_bubble') and self.restore_bubble.isVisible():
                                bubble_local = self.restore_bubble.mapFromGlobal(gp)
                                if self.restore_bubble.rect().contains(bubble_local):
                                    is_solid = True
                        else:
                            # In Background/Ghost mode, the entire window is click-through at OS level
                            # so that clicks reach the underlying app/browser. Clicks on buttons are routed programmatically.
                            pass
                                    
                        if not is_solid:
                            return True, -1 # HTTRANSPARENT (click passes through)
                            
                elif msg.message == 0x0021: # WM_MOUSEACTIVATE
                    if getattr(self, 'focus_mode', '') == 'Background' or getattr(self, 'is_hidden', False):
                        import win32api
                        x, y = win32api.GetCursorPos()
                        from PyQt5.QtCore import QPoint
                        if hasattr(self, 'tab_widget') and self.tab_widget.isVisible():
                            tab_local = self.tab_widget.mapFromGlobal(QPoint(x, y))
                            if self.tab_widget.rect().contains(tab_local):
                                if self.tab_widget.currentIndex() > 0:
                                    return True, 1 # MA_ACTIVATE
                        if hasattr(self, 'settings_frame') and self.settings_frame.isVisible():
                            sf_local = self.settings_frame.mapFromGlobal(QPoint(x, y))
                            if self.settings_frame.rect().contains(sf_local):
                                return True, 1 # MA_ACTIVATE
                        return True, 3 # MA_NOACTIVATE
                
                if msg.message == 0x0312: # WM_HOTKEY
                    hotkey_id = msg.wParam
                    try:
                        with open("d:/invisibleai/hotkey_debug.txt", "a") as df:
                            df.write(f"Received WM_HOTKEY: id={hotkey_id}, is_hidden={getattr(self, 'is_hidden', False)}\n")
                    except Exception:
                        pass
                    if hotkey_id == 1 or hotkey_id == 4: # Alt + Z or Alt + C (Toggle Command Mode)
                        self.toggle_leader_mode()
                        return True, 0
                    elif hotkey_id == 2: # Alt + L (Toggle Live Interview Mode)
                        self.interview_btn.click()
                        return True, 0
                    elif hotkey_id == 3: # Alt + H (Global Toggle Visibility)
                        self.toggle_visibility_from_hotkey()
                        return True, 0
        except Exception as e:
            try: self.log_event(f'nativeEvent error: {e}', 'error')
            except: pass
        return super().nativeEvent(eventType, message)
        
    def toggle_leader_mode(self):
        if getattr(self, 'is_hidden', False):
            self.leader_active = True  # Set BEFORE restore so _apply_leader_state sees correct state
            self.restore_from_edge()
        else:
            self.leader_active = not getattr(self, 'leader_active', False)
            self._apply_leader_state()

    def _activate_leader_after_restore(self):
        # Kept for compatibility; leader_active is already set before restore_from_edge
        self._apply_leader_state()

    def _apply_leader_state(self):
        self.update_style()

        # In Background Mode, we ALWAYS keep WS_EX_TRANSPARENT & WS_EX_NOACTIVATE
        # to ensure the window remains a perfect, undetectable click-through ghost,
        # even in Command Mode! Keyboard hook handles shortcuts without needing focus.
        try:
            hwnd = int(self.winId())
            GWL_EXSTYLE = -20
            WS_EX_NOACTIVATE = 0x08000000
            WS_EX_TRANSPARENT = 0x00000020
            ex = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            if getattr(self, 'focus_mode', 'Background') == 'Background':
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE,
                    ex | WS_EX_NOACTIVATE | WS_EX_TRANSPARENT)
            else:
                # Overlay mode (normal solid state)
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE,
                    ex & ~WS_EX_NOACTIVATE & ~WS_EX_TRANSPARENT)
            # Use HWND_TOPMOST (-1) to guarantee window stays on top
            ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0,
                0x0001 | 0x0002 | 0x0020)
            
            # Re-register hotkeys on style update to prevent Qt window recreation unbinding
            self.setup_global_hotkeys()
        except Exception:
            pass

        hwnd = int(self.winId())

        if self.leader_active:
            # Command Mode: low-level keyboard hook is already permanently active.
            # We just display the system message and update chat input focus states.

            self.add_system_message("⚡ Command Mode Active (Space/H: Hide | S: Scan | I: Inject | K/T: Type | P: Model | O: Voice | U: Voice Typist | M: Live Chat | L: Interview | V: Speaker | W: Browser | B: Address Bar | F: Focus Mode | T: Theme | C: Clear | D: Send | ?: Print All Hotkeys | X: Exit | Hotkeys: Alt+I/S/W/B/F/P/M/V/L/Z/Esc)")

            # Clean leaked 'z' or 'Z' from chat input if Alt+Z was typed while focused
            txt = self.chat_input.text()
            if txt.endswith('z') or txt.endswith('Z'):
                self.chat_input.setText(txt[:-1])

            # Defocus chat_input — command mode uses single-key shortcuts, not typed text
            self.chat_input.setReadOnly(True)
            self.chat_input.clearFocus()
        else:
            # Re-enable chat input editability
            self.chat_input.setReadOnly(False)
            self.add_system_message("⚙️ Command Mode Deactivated")
            
    def _install_keyboard_hook(self):
        """Install WH_KEYBOARD_LL hook to intercept key presses in Command Mode
        without needing Qt window focus (bypasses Qt::Tool DoesNotAcceptFocus)."""
        if getattr(self, '_keyboard_hook', None) and self._keyboard_hook != 0:
            return  # Already installed
        try:
            WH_KEYBOARD_LL = 13
            self._kb_callback = HOOKPROC(global_kb_hook_callback)
            self._keyboard_hook = ctypes.windll.user32.SetWindowsHookExW(
                WH_KEYBOARD_LL, self._kb_callback, 0, 0
            )
        except Exception as e:
            logger.error("Failed to install keyboard hook: %s", e)

    def _uninstall_keyboard_hook(self):
        """Remove the WH_KEYBOARD_LL hook when leaving Command Mode."""
        try:
            if getattr(self, '_keyboard_hook', None):
                ctypes.windll.user32.UnhookWindowsHookEx(self._keyboard_hook)
                self._keyboard_hook = None
        except Exception:
            pass

    def keyPressEvent(self, event):
        if event.isAutoRepeat():
            event.accept()
            return
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
            # If a number buffer is active in keyPressEvent
            if getattr(self, 'cmd_number_buffer', ''):
                if vk in (Qt.Key_K, Qt.Key_T):
                    self._flush_cmd_number_buffer(action="type")
                    event.accept()
                    return
                elif vk in (Qt.Key_Space, Qt.Key_I, Qt.Key_Return):
                    self._flush_cmd_number_buffer(action="inject")
                    event.accept()
                    return

            if vk == Qt.Key_I:
                self.inject_hotkey_signal.emit()
                event.accept()
                return
            elif vk == Qt.Key_T or vk == Qt.Key_K:
                self.type_hotkey_signal.emit()
                event.accept()
                return
            elif vk == Qt.Key_J:
                self.theme_hotkey_signal.emit()
                event.accept()
                return
            elif Qt.Key_0 <= vk <= Qt.Key_9:
                if not hasattr(self, 'cmd_number_buffer'):
                    self.cmd_number_buffer = ""
                self.cmd_number_buffer += chr(vk)
                
                self.add_system_message(f"🔢 Code Block Selection: <b>#{self.cmd_number_buffer}</b> (Press I/Space to Inject, T/K to Type)")
                
                if hasattr(self, 'cmd_number_timer'):
                    self.cmd_number_timer.stop()
                else:
                    from PyQt5.QtCore import QTimer
                    self.cmd_number_timer = QTimer()
                    self.cmd_number_timer.setSingleShot(True)
                    self.cmd_number_timer.timeout.connect(lambda: self._flush_cmd_number_buffer(action="inject"))
                
                self.cmd_number_timer.start(1200)
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
            elif vk == Qt.Key_X:
                self.exit_hotkey_signal.emit()
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
            elif vk == Qt.Key_O:
                self.rotate_voice()
                event.accept()
                return
            elif vk == Qt.Key_B:
                self.toggle_sidebar()
                event.accept()
                return
            elif vk == Qt.Key_W:
                self.toggle_browser_visibility()
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
                
        super().keyPressEvent(event)
        
    def _apply_startup_ghost_styles(self):
        """Called once 150ms after window is shown — applies the saved focus_mode Win32 styles."""
        try:
            hwnd = int(self.winId())
            GWL_EXSTYLE = -20
            WS_EX_NOACTIVATE = 0x08000000
            WS_EX_TRANSPARENT = 0x00000020
            ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            if getattr(self, 'focus_mode', 'Background') == 'Background':
                # Ghost mode: add both flags so all clicks pass through
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE,
                    ex_style | WS_EX_NOACTIVATE | WS_EX_TRANSPARENT)
            else:
                # Overlay mode: remove both flags so window receives focus and clicks
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE,
                    ex_style & ~WS_EX_NOACTIVATE & ~WS_EX_TRANSPARENT)
            # Use HWND_TOPMOST (-1) to guarantee window stays on top
            ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0,
                0x0001 | 0x0002 | 0x0020)
            
            # Re-register hotkeys on the finalized HWND to prevent Qt window recreation unbinding
            self.setup_global_hotkeys()
        except Exception as e:
            logger.debug("Failed to apply startup ghost styles (overlay): %s", e)

    def showEvent(self, event):
        super().showEvent(event)
        try:
            hwnd = int(self.winId())
            if not ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x00000011):
                ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x00000001)
        except Exception as e:
            logger.debug("Failed to register display affinity: %s", e)
        
        # Re-register global hotkeys on the finalized native HWND
        self.setup_global_hotkeys()
        
        QTimer.singleShot(150, self._apply_startup_ghost_styles)
            
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
        # Quick exit check for non-essential high-frequency events (e.g. Paint, Layout, Update)
        ev_type = event.type()
        if ev_type not in (QEvent.Enter, QEvent.Leave, QEvent.MouseButtonPress, QEvent.KeyPress):
            return super().eventFilter(obj, event)
            
        if ev_type == QEvent.Enter:
            if hasattr(obj, 'toolTip') and obj.toolTip():
                from PyQt5.QtWidgets import QToolTip
                QToolTip.showText(QCursor.pos(), obj.toolTip(), obj)
        elif ev_type == QEvent.Leave:
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
                # Only apply NOACTIVATE in Background mode AND when NOT in Command Mode.
                # During Command Mode (leader_active=True), we need focus — never re-dock on focus-loss.
                if self.focus_mode == 'Background' and not getattr(self, 'leader_active', False):
                    # Synchronize ghost typing state when losing focus
                    if getattr(self, 'ghost_active', False):
                        self.deactivate_ghost_mode()
                    else:
                        hwnd = int(self.winId())
                        GWL_EXSTYLE = -20
                        WS_EX_NOACTIVATE = 0x08000000
                        WS_EX_TRANSPARENT = 0x00000020
                        ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style | WS_EX_NOACTIVATE | WS_EX_TRANSPARENT)
                        try:
                            # Use HWND_TOPMOST (-1) to guarantee window stays on top
                            ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0020)
                        except Exception:
                            pass
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
            try:
                # Use HWND_TOPMOST (-1) to guarantee window stays on top
                ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0020)
            except Exception:
                pass
            # Re-register hotkeys on the new HWND
            self.setup_global_hotkeys()
            self.add_system_message("⚠️ WARNING: Keyboard focus is now active. Typing or clicking the chat box WILL be detected by strict exam browsers.")
        else:
            self.focus_mode = 'Background'
            self.focus_btn.setText("Type In: Background")
            # Ghost mode: Add WS_EX_TRANSPARENT + WS_EX_NOACTIVATE so window is
            # fully click-through at OS level. WM_NCHITTEST still fires and can
            # selectively mark small areas (restore bubble) as solid.
            ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style | WS_EX_NOACTIVATE | WS_EX_TRANSPARENT)
            self.add_system_message("🔒 STEALTH MODE: Ghost active. All clicks pass through to background app. Buttons fire programmatically.")
            try:
                # Use HWND_TOPMOST (-1) to guarantee window stays on top
                ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0020)
            except Exception:
                pass
            
            # Re-register hotkeys on the new HWND
            self.setup_global_hotkeys()
            
            # Explicitly force focus back to the OS/desktop shell so Windows DWM instantly
            # activates the WS_EX_TRANSPARENT click-through behavior (otherwise active focus overrides click-through).
            try:
                shell_hwnd = ctypes.windll.user32.GetShellWindow()
                if shell_hwnd:
                    ctypes.windll.user32.SetForegroundWindow(shell_hwnd)
            except Exception:
                pass
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
        
        # WS_EX_NOACTIVATE is managed by _apply_leader_state to avoid conflicts on restore.
        try:
            hwnd = int(self.winId())
            # SWP_NOZORDER(0x0004) | SWP_FRAMECHANGED(0x0020)
            # Resizes and moves the native window to the docked geometry calculated by apply_dock()
            ctypes.windll.user32.SetWindowPos(hwnd, 0, self.x(), self.y(), self.width(), self.height(), 0x0004 | 0x0020)
        except Exception:
            pass

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
            
            # --- Background mode hover/interactivity management ---
            if getattr(self, 'is_hidden', False):
                # Restore is now handled by the mouse hook (process_hook_click)
                # Polling here only causes double-fire glitches — just return.
                return
                
            if getattr(self, 'focus_mode', '') != 'Background':
                return
                
            # Programmatic click routing is now handled by the WH_MOUSE_LL hook (process_hook_click)
            # Keeping this as a no-op to prevent poll_mouse_position double-firing conflicts.
                        
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
        self.tab_widget.show()
        self.input_container.show()
        
        if self.normal_geometry:
            self.setGeometry(self.normal_geometry)
            
        # Force redraw and active window state in OS
        self.show()
        self.raise_()
        if getattr(self, 'focus_mode', '') == 'Overlay':
            self.activateWindow()
            
        try:
            hwnd = int(self.winId())
            rect = self.normal_geometry
            if rect:
                # SWP_NOZORDER(0x0004) | SWP_FRAMECHANGED(0x0020) | SWP_SHOWWINDOW(0x0040)
                # Resizes and moves the native window to its original geometry
                ctypes.windll.user32.SetWindowPos(hwnd, 0, rect.x(), rect.y(), rect.width(), rect.height(), 0x0004 | 0x0020 | 0x0040)
            else:
                # Fallback if normal_geometry is missing
                ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0020 | 0x0040)
        except Exception:
            pass
            
        self._apply_leader_state()

    def enterEvent(self, event):
        if self.is_hidden:
            self.update_restore_bubble_style(hovered=True)
        super().enterEvent(event)
            
    def leaveEvent(self, event):
        if self.is_hidden:
            self.update_restore_bubble_style(hovered=False)
        super().leaveEvent(event)
        
    def paintEvent(self, event):
        from PyQt5.QtWidgets import QStyleOption, QStyle
        from PyQt5.QtGui import QPainter, QColor, QPen
        opt = QStyleOption()
        opt.initFrom(self)
        p = QPainter(self)
        self.style().drawPrimitive(QStyle.PE_Widget, opt, p, self)
        
        if getattr(self, 'interview_mode', False) and not getattr(self, 'is_hidden', False):
            p.setRenderHint(QPainter.Antialiasing)
            color = getattr(self, 'interview_qcolor', QColor(236, 72, 153))
            pen = QPen(color, 2)
            p.setPen(pen)
            rect = self.rect().adjusted(1, 1, -1, -1)
            p.drawRoundedRect(rect, 15, 15)

    def update_style(self):
        # Style cache: skip full rebuild if theme/opacity/state haven't changed
        _cache_key = (
            self.is_dark,
            self.opacity_val,
            getattr(self, 'leader_active', False),
            getattr(self, 'ghost_active', False),
            getattr(self, 'interview_mode', False),
            getattr(self, 'is_hidden', False),
            getattr(self, 'interview_border_color', ''),
            getattr(self, 'active_provider', ''),
        )
        if getattr(self, '_style_cache_key', None) == _cache_key:
            return
        self._style_cache_key = _cache_key

        # Premium dark glass vs light glass color tokens (Qt QSS rgba requires float alpha 0.0..1.0)
        alpha_ratio = round(max(0.15, min(1.0, getattr(self, 'current_alpha', 90) / 100.0)), 2)
        if self.is_dark:
            bg_gradient = f"qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(22, 22, 26, {alpha_ratio}), stop:1 rgba(15, 15, 18, {alpha_ratio}))"
            border_color = f"rgba(255, 255, 255, {round(alpha_ratio * 0.2, 2)})"
            ctrl_bg = f"rgba(30, 30, 35, {alpha_ratio})"
            ctrl_text = "#F8FAFC"
            input_frame_bg = f"rgba(12, 12, 16, {alpha_ratio})"
            input_text = "#F3F4F6"
            sidebar_bg = f"rgba(10, 10, 12, {round(alpha_ratio * 0.45, 2)})"
        else:
            bg_gradient = f"qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(250, 250, 250, {alpha_ratio}), stop:1 rgba(240, 240, 243, {alpha_ratio}))"
            border_color = f"rgba(0, 0, 0, {round(alpha_ratio * 0.15, 2)})"
            ctrl_bg = f"rgba(235, 235, 240, {alpha_ratio})"
            ctrl_text = "#000000"
            input_frame_bg = f"rgba(255, 255, 255, {alpha_ratio})"
            input_text = "#000000"
            sidebar_bg = f"rgba(243, 244, 246, {round(alpha_ratio * 0.45, 2)})"

        top_label_color = "#F8FAFC" if self.is_dark else "#000000"
        if hasattr(self, 'drag_handle'):
            self.drag_handle.setStyleSheet(f"color: {top_label_color}; font-weight: bold; font-family: 'Segoe UI', sans-serif; background: transparent;")
        if hasattr(self, 'opacity_label'):
            self.opacity_label.setStyleSheet(f"color: {top_label_color}; font-weight: bold; font-family: 'Segoe UI', sans-serif; background: transparent;")

        # Dynamic highlights: Purple for Command Mode, Green for Ghost Typing
        if getattr(self, 'leader_active', False):
            input_frame_border = "1.5px solid rgba(139, 92, 246, 0.85)"
            input_frame_bg = f"rgba(139, 92, 246, {round(alpha_ratio * 0.18, 2)})"
        elif getattr(self, 'ghost_active', False):
            input_frame_border = "1.5px solid rgba(16, 185, 129, 0.80)"
            input_frame_bg = f"rgba(16, 185, 129, {round(alpha_ratio * 0.15, 2)})"
        else:
            input_frame_border = f"1px solid {border_color}"

        border_width = "2px" if getattr(self, 'interview_mode', False) else "1px"
        if getattr(self, 'interview_mode', False):
            border_color = getattr(self, 'interview_border_color', "rgb(236, 72, 153)")

        provider_names = {"gemini": "Gemini", "groq": "Groq", "openrouter": "OpenRouter", "nvidia": "NVIDIA", "web2api": "Web2API"}
        disp_name = provider_names.get(self.active_provider, self.active_provider.capitalize())
        
        if getattr(self, 'ghost_active', False):
            placeholder = "[Stealth Ghost Typing ACTIVE... Enter: Send, Esc: Exit]" 
        else:
            placeholder = f"Ask {disp_name}... (Alt+Z then: E=Type | P=Model | S=Scan | I=Inject | U=Voice | M=Live Mic | L=Interview | V=Speaker | [ / ]=Alpha | X=Exit)"
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
                border: {"none" if getattr(self, 'is_hidden', False) or getattr(self, 'interview_mode', False) else f"{border_width} solid {border_color}"};
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
            text_color = "#E5E7EB" if self.is_dark else "#000000"
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
        
        # Debounce writing settings to disk to prevent GDI/Disk lag during theme toggle
        if not hasattr(self, 'save_settings_timer'):
            self.save_settings_timer = QTimer(self)
            self.save_settings_timer.setSingleShot(True)
            self.save_settings_timer.timeout.connect(self.save_settings)
        self.save_settings_timer.start(1000)
        
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
        value = max(10, min(100, value))
        self.current_alpha = value
        if hasattr(self, 'slider') and self.slider.value() != value:
            self.slider.blockSignals(True)
            self.slider.setValue(value)
            self.slider.blockSignals(False)
        self.opacity_label.setText(f"Alpha: {value}%")
        self.opacity_val = int((value / 100.0) * 255)
        self.setWindowOpacity(max(0.15, value / 100.0))
        if not getattr(self, 'is_hidden', False): 
            if not hasattr(self, '_style_update_timer'):
                self._style_update_timer = QTimer(self)
                self._style_update_timer.setSingleShot(True)
                self._style_update_timer.timeout.connect(self.update_style)
            if not self._style_update_timer.isActive():
                self._style_update_timer.start(25) # Throttle stylesheet updates to 25ms (40 FPS)
        else:
            self.update_restore_bubble_style(hovered=False)
            
        # Debounce writing settings to disk to prevent GDI/Disk lag during hover scrolling
        if not hasattr(self, 'save_settings_timer'):
            self.save_settings_timer = QTimer(self)
            self.save_settings_timer.setSingleShot(True)
            self.save_settings_timer.timeout.connect(self.save_settings)
        self.save_settings_timer.start(1000) # Save 1 second after changes stop
        
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
            # Direct pixel scrolling: scroll 40 pixels per standard notch (120 units)
            scroll_amount = int((delta / 120.0) * 40)
            # Safeguard for precision touchpads that send small values (1, 2, 15 etc.)
            if scroll_amount == 0 and delta != 0:
                scroll_amount = 1 if delta > 0 else -1
            
            scrollbar.setValue(scrollbar.value() - scroll_amount)

if __name__ == "__main__":
    import os
    import sys
    
    # Enable safe Chromium rendering flags for all Win 10 / 11 GPUs & Integrated Graphics
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
        "--no-sandbox "
        "--enable-gpu-rasterization "
        "--ignore-gpu-blocklist "
        "--disable-logging "
        "--log-level=3"
    )
    
    # Setup programmatic logging in APPDATA/InvisibleAI to avoid CWD permission crashes
    try:
        from core.constants import get_app_dir
        app_log_dir = get_app_dir()
    except Exception:
        app_log_dir = "."
        
    for i in range(10):
        try:
            log_name = os.path.join(app_log_dir, f"error_{i}.log" if i > 0 else "error.log")
            log_file_handle = open(log_name, "a", encoding="utf-8", buffering=1)
            sys.stdout = log_file_handle
            sys.stderr = log_file_handle
            break
        except Exception:
            continue
            
    try:
        # Enable Win32 Per-Monitor DPI awareness for clean scaling on Win 10 & 11
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(2) # PROCESS_PER_MONITOR_DPI_AWARE
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
                
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        from PyQt5.QtCore import QCoreApplication, Qt
        QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QCoreApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
        QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
        
        app = QApplication(sys.argv)
        overlay = TransparentOverlay()
        overlay.show()
        app_filter = AppEventFilter(overlay)
        app.installEventFilter(app_filter)
        sys.exit(app.exec_())
    except Exception as e:
        import traceback
        try:
            crash_path = os.path.join(app_log_dir, "crash_log.txt")
            with open(crash_path, "w", encoding="utf-8") as f:
                traceback.print_exc(file=f)
        except Exception:
            pass
        sys.exit(1)
        