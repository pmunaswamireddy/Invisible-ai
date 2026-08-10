import ctypes
import logging
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton, QApplication
)
from PyQt5.QtCore import Qt, QPoint, QRect, QTimer, pyqtSignal
from PyQt5.QtGui import QPixmap, QColor, QPainter, QPen, QFont

logger = logging.getLogger("invisibleai")

class LivePreviewPopup(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        try:
            hwnd = int(self.winId())
            ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x00000011) # WDA_EXCLUDEFROMCAPTURE
        except Exception as e:
            logger.debug("Failed to register popup display affinity: %s", e)
        
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

class MultiSnipController(QWidget):
    snip_completed = pyqtSignal(QPixmap)

    def __init__(self, parent_overlay=None):
        super().__init__()
        self.parent_overlay = parent_overlay
        self.captures = []
        self.last_rect = QRect()

        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
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

        self.status_label = QLabel("Multi-Snip Mode  │  0 captures")
        self.status_label.setAlignment(Qt.AlignCenter)
        flayout.addWidget(self.status_label)

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

    def _apply_startup_ghost_styles(self):
        try:
            hwnd = int(self.winId())
            GWL_EXSTYLE = -20
            WS_EX_NOACTIVATE = 0x08000000
            WS_EX_TRANSPARENT = 0x00000020
            ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            if getattr(self, 'focus_mode', 'Background') == 'Background':
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE,
                    ex_style | WS_EX_NOACTIVATE | WS_EX_TRANSPARENT)
            else:
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE,
                    ex_style & ~WS_EX_NOACTIVATE & ~WS_EX_TRANSPARENT)
            ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0,
                0x0001 | 0x0002 | 0x0020)
            
            if hasattr(self, 'setup_global_hotkeys'):
                self.setup_global_hotkeys()
        except Exception as e:
            logger.debug("Failed to apply startup ghost styles: %s", e)

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
        self.sniper.raise_()
        self.sniper.activateWindow()

    def _on_sniper_destroyed(self):
        if not self.isVisible() and len(self.captures) > 0:
            self.show()

    def _finish(self):
        if not self.captures:
            if self.parent_overlay:
                self.parent_overlay._restore_overlay()
            self.close()
            return
        
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

    def _apply_startup_ghost_styles(self):
        try:
            hwnd = int(self.winId())
            GWL_EXSTYLE = -20
            WS_EX_NOACTIVATE = 0x08000000
            WS_EX_TRANSPARENT = 0x00000020
            ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            if getattr(self, 'focus_mode', 'Background') == 'Background':
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE,
                    ex_style | WS_EX_NOACTIVATE | WS_EX_TRANSPARENT)
            else:
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE,
                    ex_style & ~WS_EX_NOACTIVATE & ~WS_EX_TRANSPARENT)
            ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0,
                0x0001 | 0x0002 | 0x0020)
            
            if hasattr(self, 'setup_global_hotkeys'):
                self.setup_global_hotkeys()
        except Exception as e:
            logger.debug("Failed to apply startup ghost styles (sniper): %s", e)

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
