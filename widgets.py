import os
import sys
from PyQt5.QtWidgets import QWidget, QApplication, QHBoxLayout, QLabel, QPushButton, QFrame
from PyQt5.QtCore import Qt, QPoint, pyqtSignal, QRect, QTimer
from PyQt5.QtGui import QColor, QPainter, QPen, QCursor, QPixmap, QImage
from utils import get_app_dir

# --- AudioWaveWidget ---
class AudioWaveWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(120, 24)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_wave)
        self.timer.start(100)
        self.amplitudes = [2] * 12
        self.active = False
        self.mode = "listening"

    def set_active(self, active, mode="listening"):
        self.active = active
        self.mode = mode
        if not active:
            self.amplitudes = [2] * 12
        self.update()

    def update_wave(self):
        if not self.active:
            return
        import random
        max_val = 18 if self.mode == "listening" else 8
        self.amplitudes = [random.randint(2, max_val) for _ in range(12)]
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        w = self.width()
        h = self.height()
        spacing = 4
        bar_w = 4
        total_w = len(self.amplitudes) * (bar_w + spacing) - spacing
        start_x = (w - total_w) // 2
        
        color = QColor("#ef4444") if self.mode == "speaking" else QColor("#8b5cf6")
        if not self.active:
            color = QColor("#4b5563")
            
        for i, amp in enumerate(self.amplitudes):
            x = start_x + i * (bar_w + spacing)
            bar_h = amp
            y = (h - bar_h) // 2
            
            painter.setBrush(color)
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(x, y, bar_w, bar_h, 2, 2)

# --- SelectionOverlay ---
class SelectionOverlay(QWidget):
    finished_signal = pyqtSignal(str) # Path to cropped image
    
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        screen = QApplication.primaryScreen()
        self.full_screenshot = screen.grabWindow(0)
        
        self.setGeometry(screen.geometry())
        self.showFullScreen()
        self.setCursor(Qt.CrossCursor)
        
        self.start_pos = None
        self.end_pos = None
        self.is_selecting = False
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self.full_screenshot)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 100)) # Dark veil
        
        if self.is_selecting and self.start_pos and self.end_pos:
            rect = QRect(self.start_pos, self.end_pos).normalized()
            painter.setCompositionMode(QPainter.CompositionMode_Source)
            painter.drawPixmap(rect, self.full_screenshot, rect)
            
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            pen = QPen(QColor(139, 92, 246), 2)
            painter.setPen(pen)
            painter.drawRect(rect)
            
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.start_pos = event.pos()
            self.end_pos = event.pos()
            self.is_selecting = True
            self.update()
            
    def mouseMoveEvent(self, event):
        if self.is_selecting:
            self.end_pos = event.pos()
            self.update()
            
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.is_selecting:
            self.is_selecting = False
            self.end_pos = event.pos()
            self.crop_and_save()
            self.close()
            
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
            
    def crop_and_save(self):
        rect = QRect(self.start_pos, self.end_pos).normalized()
        if rect.width() < 5 or rect.height() < 5:
            return
            
        cropped = self.full_screenshot.copy(rect)
        scan_path = os.path.join(get_app_dir(), "scan_result.png")
        cropped.save(scan_path, "PNG")
        self.finished_signal.emit(scan_path)

# --- ChatHistoryItemWidget ---
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
