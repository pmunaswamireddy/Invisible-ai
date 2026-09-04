import os
import sys
import re
import time
import urllib.request
import urllib.parse
import datetime

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit, 
    QMenu, QFileDialog, QSizePolicy, QAction
)
from PyQt5.QtCore import QUrl, Qt, QPoint, QEvent, QRect, QSize
from PyQt5.QtGui import QColor, QPainter, QPen, QCursor, QPixmap, QIcon

# Dynamic import check inside the module is not needed since this file is only imported on demand
from PyQt5.QtWebEngineWidgets import (
    QWebEngineView, QWebEnginePage, QWebEngineProfile, QWebEngineSettings, QWebEngineScript
)

from core.constants import get_app_dir

_NORMAL_WEBENGINE_PROFILE = None
_ANONYMOUS_WEBENGINE_PROFILE = None

def setup_profile_common(profile):
    profile.setHttpUserAgent(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:115.0) Gecko/20100101 Firefox/115.0"
    )
    profile.scripts().clear()

def get_normal_webengine_profile():
    global _NORMAL_WEBENGINE_PROFILE
    if _NORMAL_WEBENGINE_PROFILE is None:
        profile = QWebEngineProfile("normal_persistent_profile", None)
        storage_path = os.path.join(get_app_dir(), "browser_profile", "normal_data")
        cache_path = os.path.join(get_app_dir(), "browser_profile", "normal_cache")
        if not os.path.exists(storage_path): os.makedirs(storage_path, exist_ok=True)
        if not os.path.exists(cache_path): os.makedirs(cache_path, exist_ok=True)
        
        profile.setPersistentStoragePath(storage_path)
        profile.setCachePath(cache_path)
        profile.setPersistentCookiesPolicy(QWebEngineProfile.AllowPersistentCookies)
        setup_profile_common(profile)
        _NORMAL_WEBENGINE_PROFILE = profile
    return _NORMAL_WEBENGINE_PROFILE

def get_anonymous_webengine_profile():
    global _ANONYMOUS_WEBENGINE_PROFILE
    if _ANONYMOUS_WEBENGINE_PROFILE is None:
        profile = QWebEngineProfile() # In-memory off-the-record profile
        profile.setPersistentCookiesPolicy(QWebEngineProfile.NoPersistentCookies)
        setup_profile_common(profile)
        _ANONYMOUS_WEBENGINE_PROFILE = profile
    return _ANONYMOUS_WEBENGINE_PROFILE

def get_shared_webengine_profile(is_anonymous=False):
    return get_anonymous_webengine_profile() if is_anonymous else get_normal_webengine_profile()

class CustomWebEnginePage(QWebEnginePage):
    def __init__(self, parent_tab, is_anonymous=False):
        profile = get_anonymous_webengine_profile() if is_anonymous else get_normal_webengine_profile()
        super().__init__(profile, parent_tab.browser)
        self.parent_tab = parent_tab
        self.is_anonymous = is_anonymous
        
        self.featurePermissionRequested.connect(self.handle_feature_permission)
        
        try:
            profile.downloadRequested.disconnect(parent_tab.handle_download)
        except Exception:
            pass
        profile.downloadRequested.connect(parent_tab.handle_download)

    def handle_feature_permission(self, securityOrigin, feature):
        self.setFeaturePermission(securityOrigin, feature, QWebEnginePage.PermissionGrantedByUser)
        
    def createWindow(self, type_):
        new_tab = self.parent_tab.parent_overlay.create_empty_browser_tab(is_anonymous=self.is_anonymous)
        return new_tab.browser.page()

class BrowserIconButton(QPushButton):
    def __init__(self, action_type, parent=None):
        super().__init__("", parent)
        self.action_type = action_type
        self.setFixedSize(20, 20)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setStyleSheet("QPushButton { background: transparent; border: none; }")
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        is_hovered = self.underMouse()
        is_enabled = self.isEnabled()
        
        if not is_enabled:
            color = QColor(100, 116, 139, 100)
        elif is_hovered:
            color = QColor(255, 255, 255)
            painter.setBrush(QColor(255, 255, 255, 20))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(self.rect(), 4, 4)
            painter.setBrush(Qt.NoBrush)
        else:
            color = QColor(203, 213, 225)
            
        painter.setPen(QPen(color, 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        
        rect = self.rect()
        cx, cy = int(rect.width() / 2), int(rect.height() / 2)
        
        if self.action_type == "back":
            painter.drawLine(cx - 5, cy, cx + 5, cy)
            painter.drawLine(cx - 5, cy, cx - 2, cy - 3)
            painter.drawLine(cx - 5, cy, cx - 2, cy + 3)
        elif self.action_type == "forward":
            painter.drawLine(cx - 5, cy, cx + 5, cy)
            painter.drawLine(cx + 5, cy, cx + 2, cy - 3)
            painter.drawLine(cx + 5, cy, cx + 2, cy + 3)
        elif self.action_type == "refresh":
            import math
            r = 4.5
            painter.drawArc(int(cx - r), int(cy - r), int(r * 2), int(r * 2), 45 * 16, 270 * 16)
            ax = cx + r * 0.707
            ay = cy - r * 0.707
            painter.drawLine(int(ax), int(ay), int(ax - 3), int(ay))
            painter.drawLine(int(ax), int(ay), int(ax), int(ay + 3))

class SearchDropdownButton(QPushButton):
    # Cache loaded pixmaps for performance
    _icon_cache = {}
    
    def __init__(self, parent_tab):
        super().__init__("", parent_tab)
        self.parent_tab = parent_tab
        self.setFixedSize(32, 20)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setStyleSheet("QPushButton { background: transparent; border: none; }")
        self._load_icons()
        
    def _load_icons(self):
        if SearchDropdownButton._icon_cache:
            return
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")
        icon_files = {
            "duckduckgo": os.path.join(base, "duckduckgo.ico"),
            "mojeek": os.path.join(base, "mojeek.ico"),
            "brave": os.path.join(base, "brave.ico"),
            "startpage": os.path.join(base, "startpage.png"),
            "google": os.path.join(base, "google.ico"),
        }
        for key, path in icon_files.items():
            if os.path.exists(path):
                pm = QPixmap(path)
                if not pm.isNull():
                    SearchDropdownButton._icon_cache[key] = pm.scaled(16, 16, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        
    def _get_icon_key(self):
        se = self.parent_tab.active_search_engine
        if "duck" in se.lower():
            return "duckduckgo"
        elif se == "Mojeek":
            return "mojeek"
        elif se == "Brave Search":
            return "brave"
        elif se == "Startpage":
            return "startpage"
        elif se == "Google":
            return "google"
        return "duckduckgo"
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        
        rect = self.rect()
        is_hovered = self.underMouse()
        
        if is_hovered:
            painter.setBrush(QColor(255, 255, 255, 20))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(rect, 4, 4)
            painter.setBrush(Qt.NoBrush)
        
        # Draw the actual search engine logo
        icon_key = self._get_icon_key()
        pm = SearchDropdownButton._icon_cache.get(icon_key)
        if pm and not pm.isNull():
            icon_size = 14
            ix = int((rect.width() - 10 - icon_size) / 2)
            iy = int((rect.height() - icon_size) / 2)
            painter.drawPixmap(ix, iy, icon_size, icon_size, pm)
        else:
            # Fallback: draw a colored circle with initial letter
            se = self.parent_tab.active_search_engine
            colors = {"duckduckgo": QColor(222, 88, 51), "mojeek": QColor(34, 197, 94),
                      "brave": QColor(234, 88, 12), "startpage": QColor(89, 106, 214),
                      "google": QColor(66, 133, 244)}
            c = colors.get(icon_key, QColor(100, 100, 200))
            painter.setPen(Qt.NoPen)
            painter.setBrush(c)
            cx_pos = int((rect.width() - 10) / 2)
            cy_pos = int(rect.height() / 2)
            painter.drawEllipse(cx_pos - 6, cy_pos - 6, 12, 12)
            painter.setPen(QColor(255, 255, 255))
            font = painter.font()
            font.setPixelSize(8)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(QRect(cx_pos - 6, cy_pos - 6, 12, 12), Qt.AlignCenter, se[0].upper())
        
        # Draw dropdown chevron arrow
        arrow_color = QColor(180, 190, 210)
        painter.setPen(QPen(arrow_color, 1.3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(Qt.NoBrush)
        ax = int(rect.width() - 7)
        ay = int(rect.height() / 2)
        painter.drawLine(ax - 3, ay - 2, ax, ay + 1)
        painter.drawLine(ax, ay + 1, ax + 3, ay - 2)

class WebBrowserTab(QWidget):
    def __init__(self, url, parent_overlay, is_anonymous=False):
        super().__init__()
        self.parent_overlay = parent_overlay
        self.active_search_engine = "DuckDuckGo"
        self.url = ""
        self.is_anonymous = is_anonymous
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # --- NAVIGATION BAR ---
        nav_bar = QWidget()
        nav_bar.setStyleSheet("background-color: #1e1b29; border-bottom: 1px solid #4c1d95;")
        nav_bar.setFixedHeight(30)
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(6, 2, 6, 2)
        nav_layout.setSpacing(5)
        
        # Back/Forward/Refresh Buttons
        self.back_btn = BrowserIconButton("back", self)
        self.back_btn.clicked.connect(self.go_back)
        nav_layout.addWidget(self.back_btn)
        
        self.forward_btn = BrowserIconButton("forward", self)
        self.forward_btn.clicked.connect(self.go_forward)
        nav_layout.addWidget(self.forward_btn)
        
        self.refresh_btn = BrowserIconButton("refresh", self)
        self.refresh_btn.clicked.connect(self.refresh)
        nav_layout.addWidget(self.refresh_btn)
        
        # Mode Switcher Button (🌐 Normal vs 🕵️ Anonymous)
        self.mode_btn = QPushButton()
        self.mode_btn.setFixedHeight(20)
        self.mode_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.mode_btn.setToolTip("Switch between 🌐 Normal Mode (Persistent cookies, cache & logins) and 🕵️ Anonymous Mode (Incognito / Zero Footprint)")
        self.mode_btn.clicked.connect(self.toggle_browser_mode)
        self.update_mode_button_style()
        nav_layout.addWidget(self.mode_btn)
        
        # Search Engine Dropdown Button
        self.search_dropdown_btn = SearchDropdownButton(self)
        self.search_dropdown_btn.clicked.connect(self.show_search_menu)
        nav_layout.addWidget(self.search_dropdown_btn)
        
        # Address Bar
        self.address_bar = QLineEdit()
        self.address_bar.setPlaceholderText("Search with DuckDuckGo or enter address")
        self.address_bar.returnPressed.connect(self.load_address)
        self.address_bar.setStyleSheet("""
            QLineEdit {
                background-color: #0f172a;
                color: #e2e8f0;
                border: 1px solid #475569;
                border-radius: 4px;
                padding: 1px 6px;
                font-family: 'Segoe UI', sans-serif;
                font-size: 11px;
                height: 18px;
            }
            QLineEdit:focus {
                border: 1px solid #8b5cf6;
            }
        """)
        nav_layout.addWidget(self.address_bar)
        
        # Star / Bookmark button
        self.bookmark_btn = QPushButton("☆")
        self.bookmark_btn.setToolTip("Bookmark current page")
        self.bookmark_btn.setFixedSize(20, 20)
        self.bookmark_btn.clicked.connect(self.toggle_bookmark)
        self.bookmark_btn.setStyleSheet("QPushButton { background: transparent; color: #e2e8f0; border: none; font-size: 13px; } QPushButton:hover { color: #fbbf24; }")
        nav_layout.addWidget(self.bookmark_btn)
        
        # Close Button
        self.close_btn = QPushButton("✕")
        self.close_btn.setToolTip("Close Tab")
        self.close_btn.setFixedSize(20, 20)
        self.close_btn.clicked.connect(self.close_self)
        self.close_btn.setStyleSheet("QPushButton { background: transparent; color: #ef4444; border: none; font-weight: bold; font-size: 11px; } QPushButton:hover { background: #fee2e2; border-radius: 4px; }")
        nav_layout.addWidget(self.close_btn)
        
        layout.addWidget(nav_bar, 0)
        
        # --- CHROMIUM BROWSER VIEW ---
        self.browser = QWebEngineView()
        self.browser.setPage(CustomWebEnginePage(self, is_anonymous=self.is_anonymous))
        self.apply_browser_settings(self.browser)
        
        self.browser.urlChanged.connect(self.on_url_changed)
        self.browser.titleChanged.connect(self.on_title_changed)
        self.browser.loadFinished.connect(self.update_buttons)
        
        # Install event filter for horizontal swipe gestures (back/forward)
        self.browser.installEventFilter(self)
        self._swipe_start_x = None
        
        layout.addWidget(self.browser, 1)
        
        if url:
            self.load_url(url)

    def apply_browser_settings(self, browser):
        settings = browser.settings()
        settings.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.PluginsEnabled, True)
        settings.setAttribute(QWebEngineSettings.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.AutoLoadImages, True)
        settings.setAttribute(QWebEngineSettings.ScrollAnimatorEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebGLEnabled, True)
        settings.setAttribute(QWebEngineSettings.Accelerated2dCanvasEnabled, True)
        settings.setAttribute(QWebEngineSettings.ScreenCaptureEnabled, True)
        settings.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.AllowRunningInsecureContent, True)
        settings.setAttribute(QWebEngineSettings.JavascriptCanAccessClipboard, True)
        settings.setAttribute(QWebEngineSettings.JavascriptCanOpenWindows, True)
        settings.setAttribute(QWebEngineSettings.FocusOnNavigationEnabled, True)
        settings.setAttribute(QWebEngineSettings.ShowScrollBars, True)
        settings.setAttribute(QWebEngineSettings.ErrorPageEnabled, True)
        settings.setAttribute(QWebEngineSettings.PlaybackRequiresUserGesture, False)
        settings.setAttribute(QWebEngineSettings.FullScreenSupportEnabled, True)

    def update_mode_button_style(self):
        if getattr(self, 'is_anonymous', False):
            self.mode_btn.setText("🕵️ Anonymous")
            self.mode_btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(139, 92, 246, 0.25);
                    color: #c084fc;
                    border: 1px solid rgba(139, 92, 246, 0.5);
                    border-radius: 4px;
                    padding: 0px 6px;
                    font-size: 10px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: rgba(139, 92, 246, 0.4);
                }
            """)
        else:
            self.mode_btn.setText("🌐 Normal")
            self.mode_btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(16, 185, 129, 0.25);
                    color: #34d399;
                    border: 1px solid rgba(16, 185, 129, 0.5);
                    border-radius: 4px;
                    padding: 0px 6px;
                    font-size: 10px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: rgba(16, 185, 129, 0.4);
                }
            """)

    def toggle_browser_mode(self):
        self.is_anonymous = not getattr(self, 'is_anonymous', False)
        self.update_mode_button_style()
        
        current_qurl = self.browser.url()
        new_page = CustomWebEnginePage(self, is_anonymous=self.is_anonymous)
        self.browser.setPage(new_page)
        self.apply_browser_settings(self.browser)
        if current_qurl and current_qurl.isValid():
            self.browser.setUrl(current_qurl)
            
        mode_label = "Anonymous (Incognito / Zero Footprint)" if self.is_anonymous else "Normal (Persistent Logins & Cookies)"
        if hasattr(self.parent_overlay, 'add_system_message'):
            self.parent_overlay.add_system_message(f"🌐 Browser Mode: <b>{mode_label}</b>")
        if hasattr(self.parent_overlay, 'log_event'):
            self.parent_overlay.log_event(f"Browser Mode toggled to {mode_label}", "info")
            
    def eventFilter(self, obj, event):
        """Handle horizontal swipe gestures for back/forward navigation."""
        if obj == self.browser:
            from PyQt5.QtCore import QEvent as _QE
            if event.type() == _QE.ChildAdded:
                # Install event filter on child widgets (the render widget)
                child = event.child()
                if child:
                    child.installEventFilter(self)
            elif event.type() == _QE.Wheel:
                # Check for horizontal scroll (shift+wheel or touchpad horizontal)
                if hasattr(event, 'angleDelta'):
                    dx = event.angleDelta().x()
                    if abs(dx) > 60:
                        if dx > 0:
                            self.go_back()
                            return True
                        else:
                            self.go_forward()
                            return True
        return super().eventFilter(obj, event)

    def load_url(self, url):
        if not url.startswith("http://") and not url.startswith("https://") and not url.startswith("browser://"):
            if "." in url and " " not in url:
                url = "https://" + url
            else:
                query = urllib.parse.quote(url)
                se = self.active_search_engine
                if se == "DuckDuckGo (HTML)":
                    url = f"https://html.duckduckgo.com/html/?q={query}"
                elif se == "DuckDuckGo (no AI)":
                    url = f"https://duckduckgo.com/?q={query}&ia=web"
                elif se == "Mojeek":
                    url = f"https://www.mojeek.com/search?q={query}"
                elif se == "Brave Search":
                    url = f"https://search.brave.com/search?q={query}"
                elif se == "Startpage":
                    url = f"https://www.startpage.com/sp/search?query={query}"
                elif se == "Google":
                    url = f"https://www.google.com/search?q={query}"
                else:
                    url = f"https://duckduckgo.com/?q={query}"
                    
        self.address_bar.setText(url)
        self.browser.load(QUrl(url))
        
    def on_url_changed(self, qurl):
        url_str = qurl.toString()
        self.url = url_str
        self.address_bar.setText(url_str)
        
        # Handle browser:// action URLs
        if url_str.startswith("browser://"):
            self._handle_browser_action(url_str)
            return
    
    def _handle_browser_action(self, url_str):
        """Handle internal browser:// action URLs for history, bookmarks, tabs management."""
        if url_str == "browser://clear-history":
            self.parent_overlay.browser_history = []
            self.show_history()
        elif url_str.startswith("browser://delete-history-"):
            m = re.match(r"browser://delete-history-(\d+)", url_str)
            if m:
                idx = int(m.group(1))
                history = getattr(self.parent_overlay, 'browser_history', [])
                if 0 <= idx < len(history):
                    history.pop(idx)
                self.show_history()
        elif url_str == "browser://clear-bookmarks":
            self.parent_overlay.browser_bookmarks = []
            self.show_bookmarks()
        elif url_str.startswith("browser://delete-bookmark-"):
            m = re.match(r"browser://delete-bookmark-(\d+)", url_str)
            if m:
                idx = int(m.group(1))
                bookmarks = getattr(self.parent_overlay, 'browser_bookmarks', [])
                if 0 <= idx < len(bookmarks):
                    bookmarks.pop(idx)
                self.show_bookmarks()
        elif url_str == "browser://close-all-tabs":
            tab_widget = self.parent_overlay.tab_widget
            # Close all tabs except chat (index 0) and current tab
            current_idx = tab_widget.indexOf(self)
            to_remove = []
            for i in range(tab_widget.count() - 1, 0, -1):
                if i != current_idx:
                    to_remove.append(i)
            for i in to_remove:
                self.parent_overlay.close_tab(i)
            self.show_tabs_list()
        elif url_str.startswith("browser://close-tab-"):
            m = re.match(r"browser://close-tab-(\d+)", url_str)
            if m:
                idx = int(m.group(1))
                if idx > 0:
                    self.parent_overlay.close_tab(idx)
                self.show_tabs_list()
        elif url_str.startswith("browser://switch-tab-"):
            m = re.match(r"browser://switch-tab-(\d+)", url_str)
            if m:
                idx = int(m.group(1))
                tab_widget = self.parent_overlay.tab_widget
                if 0 <= idx < tab_widget.count():
                    tab_widget.setCurrentIndex(idx)
        
        # Update bookmark star button status
        bookmarks = getattr(self.parent_overlay, 'browser_bookmarks', [])
        is_bookmarked = any(b['url'] == url_str for b in bookmarks)
        if is_bookmarked:
            self.bookmark_btn.setText("★")
            self.bookmark_btn.setStyleSheet("QPushButton { background: transparent; color: #fbbf24; border: none; font-size: 13px; }")
        else:
            self.bookmark_btn.setText("☆")
            self.bookmark_btn.setStyleSheet("QPushButton { background: transparent; color: #e2e8f0; border: none; font-size: 13px; } QPushButton:hover { color: #fbbf24; }")
            
        # Log to history
        title = self.browser.title() or "Web Page"
        if not url_str.startswith("browser://"):
            history = getattr(self.parent_overlay, 'browser_history', [])
            if not history or history[-1]['url'] != url_str:
                time_str = datetime.datetime.now().strftime("%H:%M")
                self.parent_overlay.browser_history.append({"url": url_str, "title": title, "time": time_str})
                
        self.update_buttons()
        
    def on_title_changed(self, title):
        tab_widget = self.parent_overlay.tab_widget
        idx = tab_widget.indexOf(self)
        if idx != -1:
            tab_widget.setTabText(idx, title[:15] + "..." if len(title) > 15 else title)
            
    def update_buttons(self, ok=True):
        self.back_btn.setEnabled(self.browser.history().canGoBack())
        self.forward_btn.setEnabled(self.browser.history().canGoForward())
        
    def go_back(self):
        self.browser.back()
        
    def go_forward(self):
        self.browser.forward()
        
    def refresh(self):
        self.browser.reload()
        
    def load_address(self):
        self.load_url(self.address_bar.text())
        
    def toggle_bookmark(self):
        url = self.url
        title = self.browser.title() or "Web Page"
        if not url or url.startswith("browser://"):
            return
            
        bookmarks = getattr(self.parent_overlay, 'browser_bookmarks', [])
        existing = [b for b in bookmarks if b['url'] == url]
        if existing:
            bookmarks.remove(existing[0])
            self.bookmark_btn.setText("☆")
            self.bookmark_btn.setStyleSheet("QPushButton { background: transparent; color: #e2e8f0; border: none; font-size: 13px; } QPushButton:hover { color: #fbbf24; }")
        else:
            bookmarks.append({"url": url, "title": title})
            self.bookmark_btn.setText("★")
            self.bookmark_btn.setStyleSheet("QPushButton { background: transparent; color: #fbbf24; border: none; font-size: 13px; }")
            
        self.parent_overlay.browser_bookmarks = bookmarks
        
    def show_search_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #1e1b29;
                color: #e2e8f0;
                border: 1px solid #4c1d95;
                border-radius: 6px;
                padding: 4px 0px;
            }
            QMenu::item {
                padding: 6px 24px;
                font-family: 'Segoe UI', sans-serif;
                font-size: 11px;
            }
            QMenu::item:selected {
                background-color: #2e1065;
                color: #f3e8ff;
            }
        """)
        
        header_act = menu.addAction("This time search with:")
        header_act.setEnabled(False)
        menu.addSeparator()
        
        _icons_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")
        def _se_icon(name):
            p = os.path.join(_icons_dir, name)
            return QIcon(p) if os.path.exists(p) else QIcon()
        
        ddg_act = menu.addAction(_se_icon("duckduckgo.ico"), "DuckDuckGo")
        ddg_html_act = menu.addAction(_se_icon("duckduckgo.ico"), "DuckDuckGo (HTML)")
        ddg_no_ai_act = menu.addAction(_se_icon("duckduckgo.ico"), "DuckDuckGo (no AI)")
        google_act = menu.addAction(_se_icon("google.ico"), "Google")
        mojeek_act = menu.addAction(_se_icon("mojeek.ico"), "Mojeek")
        brave_act = menu.addAction(_se_icon("brave.ico"), "Brave Search")
        startpage_act = menu.addAction(_se_icon("startpage.png"), "Startpage")
        
        menu.addSeparator()
        bookmarks_act = menu.addAction("⭐ Bookmarks")
        tabs_act = menu.addAction("🗂️ Tabs")
        history_act = menu.addAction("🕒 History")
        downloads_act = menu.addAction("📥 Downloads")
        
        action = menu.exec_(self.search_dropdown_btn.mapToGlobal(QPoint(0, self.search_dropdown_btn.height())))
        
        if action == ddg_act:
            self.set_search_engine("DuckDuckGo")
        elif action == ddg_html_act:
            self.set_search_engine("DuckDuckGo (HTML)")
        elif action == ddg_no_ai_act:
            self.set_search_engine("DuckDuckGo (no AI)")
        elif action == google_act:
            self.set_search_engine("Google")
        elif action == mojeek_act:
            self.set_search_engine("Mojeek")
        elif action == brave_act:
            self.set_search_engine("Brave Search")
        elif action == startpage_act:
            self.set_search_engine("Startpage")
        elif action == bookmarks_act:
            self.show_bookmarks()
        elif action == tabs_act:
            self.show_tabs_list()
        elif action == history_act:
            self.show_history()
        elif action == downloads_act:
            self.show_downloads()
            
    def set_search_engine(self, name):
        self.active_search_engine = name
        self.address_bar.clear()
        self.address_bar.setPlaceholderText(f"Search with {name} or enter address")
        self.search_dropdown_btn.update()
        
    def show_history(self):
        history = getattr(self.parent_overlay, 'browser_history', [])
        html = """
        <html>
        <head>
            <style>
                body { background-color: #0b0f19; color: #e2e8f0; font-family: 'Segoe UI', sans-serif; padding: 20px; margin: 0; }
                h2 { color: #8b5cf6; border-bottom: 1px solid #4c1d95; padding-bottom: 8px; display: flex; align-items: center; justify-content: space-between; }
                ul { list-style-type: none; padding: 0; }
                li { padding: 8px 12px; margin-bottom: 4px; background-color: #1e1b29; border-radius: 6px; display: flex; align-items: center; justify-content: space-between; }
                li:hover { background-color: #2e1065; }
                a { color: #a78bfa; text-decoration: none; font-weight: 500; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
                a:hover { text-decoration: underline; color: #c4b5fd; }
                .time { color: #64748b; font-size: 11px; margin: 0 10px; white-space: nowrap; }
                .del-btn { background: none; border: 1px solid #ef4444; color: #ef4444; border-radius: 4px; padding: 2px 8px; cursor: pointer; font-size: 11px; white-space: nowrap; }
                .del-btn:hover { background: #ef4444; color: white; }
                .clear-btn { background: #dc2626; color: white; border: none; border-radius: 6px; padding: 6px 16px; cursor: pointer; font-size: 12px; font-weight: 600; }
                .clear-btn:hover { background: #b91c1c; }
                .empty { color: #64748b; text-align: center; padding: 40px; }
            </style>
        </head>
        <body>
            <h2><span>🕒 Browsing History</span>"""
        if history:
            html += ' <a href="browser://clear-history" style="text-decoration:none;"><button class="clear-btn">🗑 Clear All</button></a>'
        html += "</h2>"
        if not history:
            html += '<p class="empty">No history entries recorded yet.</p>'
        else:
            html += "<ul>"
            for i, item in enumerate(reversed(history)):
                idx = len(history) - 1 - i
                title = item.get('title', 'Web Page')
                url = item.get('url', '')
                time_str = item.get('time', '')
                html += f'<li><a href="{url}">{title}</a><span class="time">{time_str}</span><a href="browser://delete-history-{idx}" style="text-decoration:none;"><button class="del-btn">✕</button></a></li>'
            html += "</ul>"
        html += "</body></html>"
        self.browser.setHtml(html)
        self.address_bar.setText("browser://history")
        
    def show_bookmarks(self):
        bookmarks = getattr(self.parent_overlay, 'browser_bookmarks', [])
        html = """
        <html>
        <head>
            <style>
                body { background-color: #0b0f19; color: #e2e8f0; font-family: 'Segoe UI', sans-serif; padding: 20px; margin: 0; }
                h2 { color: #8b5cf6; border-bottom: 1px solid #4c1d95; padding-bottom: 8px; display: flex; align-items: center; justify-content: space-between; }
                ul { list-style-type: none; padding: 0; }
                li { padding: 8px 12px; margin-bottom: 4px; background-color: #1e1b29; border-radius: 6px; display: flex; align-items: center; justify-content: space-between; }
                li:hover { background-color: #2e1065; }
                a { color: #a78bfa; text-decoration: none; font-weight: 500; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
                a:hover { text-decoration: underline; color: #c4b5fd; }
                .del-btn { background: none; border: 1px solid #ef4444; color: #ef4444; border-radius: 4px; padding: 2px 8px; cursor: pointer; font-size: 11px; margin-left: 8px; white-space: nowrap; }
                .del-btn:hover { background: #ef4444; color: white; }
                .clear-btn { background: #dc2626; color: white; border: none; border-radius: 6px; padding: 6px 16px; cursor: pointer; font-size: 12px; font-weight: 600; }
                .clear-btn:hover { background: #b91c1c; }
                .empty { color: #64748b; text-align: center; padding: 40px; }
            </style>
        </head>
        <body>
            <h2><span>⭐ Bookmarks</span>"""
        if bookmarks:
            html += ' <a href="browser://clear-bookmarks" style="text-decoration:none;"><button class="clear-btn">🗑 Clear All</button></a>'
        html += "</h2>"
        if not bookmarks:
            html += '<p class="empty">No bookmarks saved yet. Click the star icon to save pages.</p>'
        else:
            html += "<ul>"
            for i, item in enumerate(bookmarks):
                title = item.get('title', 'Web Page')
                url = item.get('url', '')
                html += f'<li><a href="{url}">{title}</a><a href="browser://delete-bookmark-{i}" style="text-decoration:none;"><button class="del-btn">✕</button></a></li>'
            html += "</ul>"
        html += "</body></html>"
        self.browser.setHtml(html)
        self.address_bar.setText("browser://bookmarks")
        
    def show_tabs_list(self):
        tab_widget = self.parent_overlay.tab_widget
        html = """
        <html>
        <head>
            <style>
                body { background-color: #0b0f19; color: #e2e8f0; font-family: 'Segoe UI', sans-serif; padding: 20px; margin: 0; }
                h2 { color: #8b5cf6; border-bottom: 1px solid #4c1d95; padding-bottom: 8px; display: flex; align-items: center; justify-content: space-between; }
                ul { list-style-type: none; padding: 0; }
                li { padding: 8px 12px; margin-bottom: 4px; background-color: #1e1b29; border-radius: 6px; display: flex; align-items: center; justify-content: space-between; }
                li:hover { background-color: #2e1065; }
                .tab-title { color: #a78bfa; font-weight: 500; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
                .tab-chat { color: #22c55e; }
                .close-btn { background: none; border: 1px solid #ef4444; color: #ef4444; border-radius: 4px; padding: 2px 8px; cursor: pointer; font-size: 11px; margin-left: 8px; white-space: nowrap; }
                .close-btn:hover { background: #ef4444; color: white; }
                .clear-btn { background: #dc2626; color: white; border: none; border-radius: 6px; padding: 6px 16px; cursor: pointer; font-size: 12px; font-weight: 600; }
                .clear-btn:hover { background: #b91c1c; }
                .switch-btn { background: none; border: 1px solid #8b5cf6; color: #8b5cf6; border-radius: 4px; padding: 2px 8px; cursor: pointer; font-size: 11px; margin-left: 8px; white-space: nowrap; }
                .switch-btn:hover { background: #8b5cf6; color: white; }
            </style>
        </head>
        <body>
            <h2><span>🗂️ Active Tabs</span>"""
        if tab_widget.count() > 2:  # more than chat + current browser tab
            html += ' <a href="browser://close-all-tabs" style="text-decoration:none;"><button class="clear-btn">✕ Close All Tabs</button></a>'
        html += """</h2>
            <ul>
        """
        for i in range(tab_widget.count()):
            title = tab_widget.tabText(i)
            if i == 0:
                html += f'<li><span class="tab-title tab-chat">💬 {title}</span><a href="browser://switch-tab-{i}" style="text-decoration:none;"><button class="switch-btn">Switch</button></a></li>'
            else:
                html += f'<li><span class="tab-title">{title}</span><a href="browser://switch-tab-{i}" style="text-decoration:none;"><button class="switch-btn">Switch</button></a><a href="browser://close-tab-{i}" style="text-decoration:none;"><button class="close-btn">✕</button></a></li>'
        html += """
            </ul>
        </body>
        </html>
        """
        self.browser.setHtml(html)
        self.address_bar.setText("browser://tabs")

    def show_downloads(self):
        downloads = getattr(self.parent_overlay, 'browser_downloads', [])
        html = """
        <html>
        <head>
            <style>
                body { background-color: #0b0f19; color: #e2e8f0; font-family: 'Segoe UI', sans-serif; padding: 20px; margin: 0; }
                h2 { color: #8b5cf6; border-bottom: 1px solid #4c1d95; padding-bottom: 8px; }
                ul { list-style-type: none; padding: 0; }
                li { padding: 10px 12px; margin-bottom: 4px; background-color: #1e1b29; border-radius: 6px; display: flex; align-items: center; justify-content: space-between; }
                li:hover { background-color: #2e1065; }
                .dl-name { color: #a78bfa; font-weight: 500; flex: 1; }
                .dl-status { font-size: 11px; margin-left: 10px; padding: 2px 8px; border-radius: 4px; }
                .completed { background: #166534; color: #4ade80; }
                .downloading { background: #1e40af; color: #60a5fa; }
                .cancelled { background: #7f1d1d; color: #fca5a5; }
                .empty { color: #64748b; text-align: center; padding: 40px; }
            </style>
        </head>
        <body>
            <h2>📥 Downloads</h2>
        """
        if not downloads:
            html += '<p class="empty">No downloads yet.</p>'
        else:
            html += "<ul>"
            for dl in reversed(downloads):
                name = dl.get('filename', 'file')
                status = dl.get('status', 'unknown')
                status_class = status if status in ('completed', 'downloading', 'cancelled') else 'downloading'
                path = dl.get('path', '')
                html += f'<li><span class="dl-name">📄 {name}</span><span class="dl-status {status_class}">{status.upper()}</span></li>'
            html += "</ul>"
        html += "</body></html>"
        self.browser.setHtml(html)
        self.address_bar.setText("browser://downloads")

    def handle_download(self, download):
        """Handle file download requests from the browser."""
        import os
        suggested = download.path()
        filename = os.path.basename(suggested) if suggested else "download"
        
        # Ask user where to save
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Save File", os.path.join(os.path.expanduser("~"), "Downloads", filename),
            "All Files (*)"
        )
        if save_path:
            download.setPath(save_path)
            download.accept()
            
            # Track downloads
            if not hasattr(self.parent_overlay, 'browser_downloads'):
                self.parent_overlay.browser_downloads = []
            dl_entry = {
                'filename': os.path.basename(save_path),
                'path': save_path,
                'status': 'downloading',
                'download': download
            }
            self.parent_overlay.browser_downloads.append(dl_entry)
            
            def on_finished():
                dl_entry['status'] = 'completed'
            def on_state_changed(state):
                if state == 0:  # DownloadCancelled
                    dl_entry['status'] = 'cancelled'
                elif state == 3:  # DownloadCompleted  
                    dl_entry['status'] = 'completed'
            
            download.finished.connect(on_finished)
            download.stateChanged.connect(on_state_changed)
        else:
            download.cancel()

    def cleanup(self):
        """Safely disarm signals and clean up QWebEngineView page memory before tab deletion."""
        if hasattr(self, 'browser') and self.browser:
            try:
                self.browser.urlChanged.disconnect()
                self.browser.titleChanged.disconnect()
                self.browser.loadFinished.disconnect()
            except Exception:
                pass
            page = self.browser.page()
            if page:
                self.browser.setPage(None)
                page.deleteLater()
            self.browser.deleteLater()
            self.browser = None

    def close_self(self):
        tab_widget = self.parent_overlay.tab_widget
        idx = tab_widget.indexOf(self)
        if idx != -1:
            self.parent_overlay.close_tab(idx)
