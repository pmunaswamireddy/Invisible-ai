import math
from PyQt5.QtWidgets import (
    QTextBrowser, QTabBar, QWidget, QPushButton, QLabel, QHBoxLayout,
    QApplication, QStylePainter, QStyle, QStyleOptionTab
)
from PyQt5.QtCore import Qt, QSize, QRect, QPoint, QTimer
from PyQt5.QtGui import (
    QColor, QPainter, QPen, QCursor, QPainterPath, QTextCursor
)

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

class CustomTabBar(QTabBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)  # Enable mouse tracking for hover updates

    def tabSizeHint(self, index):
        size = super().tabSizeHint(index)
        if self.tabText(index) == "+":
            return QSize(24, size.height())
        return size

    def paintEvent(self, event):
        painter = QStylePainter(self)
        for i in range(self.count()):
            if self.tabText(i) == "+":
                rect = self.tabRect(i)
                mouse_pos = self.mapFromGlobal(QCursor.pos())
                is_hovered = rect.contains(mouse_pos)
                
                painter.save()
                painter.setRenderHint(QPainter.Antialiasing)
                
                if is_hovered:
                    painter.setBrush(QColor(255, 255, 255, 30))
                    painter.setPen(Qt.NoPen)
                    painter.drawRoundedRect(rect.adjusted(2, 2, -2, -2), 4, 4)
                
                plus_color = QColor(243, 232, 255) if is_hovered else QColor(167, 139, 250)
                painter.setPen(QPen(plus_color, 1.8, Qt.SolidLine, Qt.RoundCap))
                cx, cy = rect.center().x(), rect.center().y()
                painter.drawLine(cx - 4, cy, cx + 4, cy)
                painter.drawLine(cx, cy - 4, cx, cy + 4)
                painter.restore()
            else:
                option = QStyleOptionTab()
                self.initStyleOption(option, i)
                painter.drawControl(QStyle.CE_TabBarTab, option)

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
        
        self.colors_listening = [
            QColor(139, 92, 246, 120),  # Purple
            QColor(236, 72, 153, 90),   # Pink
            QColor(59, 130, 246, 70)    # Blue
        ]
        self.colors_speaking = [
            QColor(16, 185, 129, 120),  # Emerald
            QColor(52, 211, 153, 90),   # Light Emerald
            QColor(139, 92, 246, 70)    # Purple
        ]
        
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
        
        colors = self.colors_listening if self.mode == "listening" else self.colors_speaking
            
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

class ModernIconButton(QPushButton):
    def __init__(self, icon_type, text="", parent=None):
        super().__init__(text, parent)
        self.icon_type = icon_type
        self.setMinimumHeight(28)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setStyleSheet("""
            background: transparent;
            border: none;
            padding: 0px;
        """)
        
    def sizeHint(self):
        base_hint = super().sizeHint()
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
        
        icon_width = 14
        icon_height = 14
        margin = 8
        
        icon_rect = QRect(margin, (rect.height() - icon_height) // 2, icon_width, icon_height)
        
        painter.setPen(QPen(icon_color, 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(Qt.NoBrush)
        
        itype = self.icon_type
        if itype == "send":
            path = QPainterPath()
            path.moveTo(icon_rect.x() + 2, icon_rect.y() + 2)
            path.lineTo(icon_rect.x() + 14, icon_rect.y() + 7)
            path.lineTo(icon_rect.x() + 2, icon_rect.y() + 12)
            path.lineTo(icon_rect.x() + 5, icon_rect.y() + 7)
            path.closeSubpath()
            painter.setBrush(icon_color)
            painter.drawPath(path)
        elif itype == "stop":
            painter.setBrush(icon_color)
            painter.drawRoundedRect(icon_rect.x() + 2, icon_rect.y() + 2, 10, 10, 2, 2)
        elif itype in ["scan", "camera", "shot"]:
            painter.drawRoundedRect(icon_rect.x(), icon_rect.y() + 2, 14, 10, 1.5, 1.5)
            painter.drawEllipse(icon_rect.x() + 3, icon_rect.y() + 4, 8, 8)
            painter.drawRect(icon_rect.x() + 4, icon_rect.y(), 6, 2)
        elif itype == "inject":
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
            painter.drawPolygon(QPoint(icon_rect.x() + 1, icon_rect.y() + 4),
                                QPoint(icon_rect.x() + 5, icon_rect.y() + 4),
                                QPoint(icon_rect.x() + 9, icon_rect.y() + 1),
                                QPoint(icon_rect.x() + 9, icon_rect.y() + 13),
                                QPoint(icon_rect.x() + 5, icon_rect.y() + 10),
                                QPoint(icon_rect.x() + 1, icon_rect.y() + 10))
            painter.drawArc(icon_rect.x() + 5, icon_rect.y() + 3, 7, 8, -60 * 16, 120 * 16)
        elif itype == "voice_off":
            painter.drawPolygon(QPoint(icon_rect.x() + 1, icon_rect.y() + 4),
                                QPoint(icon_rect.x() + 5, icon_rect.y() + 4),
                                QPoint(icon_rect.x() + 9, icon_rect.y() + 1),
                                QPoint(icon_rect.x() + 9, icon_rect.y() + 13),
                                QPoint(icon_rect.x() + 5, icon_rect.y() + 10),
                                QPoint(icon_rect.x() + 1, icon_rect.y() + 10))
            painter.drawLine(icon_rect.x() + 1, icon_rect.y() + 1, icon_rect.x() + 13, icon_rect.y() + 13)
        elif itype == "settings":
            cx = icon_rect.x() + 7
            cy = icon_rect.y() + 7
            painter.drawEllipse(cx - 3, cy - 3, 6, 6)
            for i in range(8):
                angle = i * 45
                rad = math.radians(angle)
                x1 = cx + 3 * math.cos(rad)
                y1 = cy + 3 * math.sin(rad)
                x2 = cx + 6 * math.cos(rad)
                y2 = cy + 6 * math.sin(rad)
                painter.drawLine(int(x1), int(y1), int(x2), int(y2))
        elif itype in ["mic", "single_mic", "interview_mic"]:
            painter.drawRoundedRect(icon_rect.x() + 4, icon_rect.y(), 6, 9, 2.5, 2.5)
            painter.drawArc(icon_rect.x() + 1, icon_rect.y() + 3, 12, 8, -180 * 16, 180 * 16)
            painter.drawLine(icon_rect.x() + 7, icon_rect.y() + 11, icon_rect.x() + 7, icon_rect.y() + 14)
            painter.drawLine(icon_rect.x() + 3, icon_rect.y() + 14, icon_rect.x() + 11, icon_rect.y() + 14)
        elif itype == "continuous_mic":
            painter.drawRoundedRect(icon_rect.x() + 4, icon_rect.y(), 6, 9, 2.5, 2.5)
            painter.drawArc(icon_rect.x() + 1, icon_rect.y() + 3, 12, 8, -180 * 16, 180 * 16)
            painter.drawLine(icon_rect.x() + 7, icon_rect.y() + 11, icon_rect.x() + 7, icon_rect.y() + 14)
            painter.drawLine(icon_rect.x() + 3, icon_rect.y() + 14, icon_rect.x() + 11, icon_rect.y() + 14)
            painter.drawArc(icon_rect.x() - 1, icon_rect.y(), 3, 9, 90 * 16, 180 * 16)
            painter.drawArc(icon_rect.x() + 12, icon_rect.y(), 3, 9, -90 * 16, 180 * 16)
        elif itype == "interview":
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
            painter.drawRect(icon_rect.x() + 2, icon_rect.y() + 3, 10, 11)
            painter.drawLine(icon_rect.x(), icon_rect.y() + 3, icon_rect.x() + 14, icon_rect.y() + 3)
            painter.drawRect(icon_rect.x() + 5, icon_rect.y(), 4, 3)
            painter.drawLine(icon_rect.x() + 5, icon_rect.y() + 6, icon_rect.x() + 5, icon_rect.y() + 11)
            painter.drawLine(icon_rect.x() + 9, icon_rect.y() + 6, icon_rect.x() + 9, icon_rect.y() + 11)
        elif itype == "new_chat":
            painter.drawLine(icon_rect.x() + 7, icon_rect.y() + 1, icon_rect.x() + 7, icon_rect.y() + 13)
            painter.drawLine(icon_rect.x() + 1, icon_rect.y() + 7, icon_rect.x() + 13, icon_rect.y() + 7)
        elif itype == "hide":
            painter.drawLine(icon_rect.x() + 2, icon_rect.y() + 10, icon_rect.x() + 12, icon_rect.y() + 10)
        elif itype == "close":
            painter.drawLine(icon_rect.x() + 3, icon_rect.y() + 3, icon_rect.x() + 11, icon_rect.y() + 11)
            painter.drawLine(icon_rect.x() + 3, icon_rect.y() + 11, icon_rect.x() + 11, icon_rect.y() + 3)
        elif itype == "web_scrap":
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
            painter.drawLine(icon_rect.x() + 2, icon_rect.y() + 3, icon_rect.x() + 12, icon_rect.y() + 3)
            painter.drawLine(icon_rect.x() + 2, icon_rect.y() + 7, icon_rect.x() + 12, icon_rect.y() + 7)
            painter.drawLine(icon_rect.x() + 2, icon_rect.y() + 11, icon_rect.x() + 12, icon_rect.y() + 11)
        elif itype == "theme_dark":
            painter.drawArc(icon_rect.x() + 1, icon_rect.y() + 1, 10, 10, 30 * 16, 250 * 16)
        elif itype == "theme_light":
            painter.drawEllipse(icon_rect.x() + 3, icon_rect.y() + 3, 8, 8)
            painter.drawLine(icon_rect.x() + 7, icon_rect.y(), icon_rect.x() + 7, icon_rect.y() + 2)
            painter.drawLine(icon_rect.x() + 7, icon_rect.y() + 12, icon_rect.x() + 7, icon_rect.y() + 14)
            painter.drawLine(icon_rect.x(), icon_rect.y() + 7, icon_rect.x() + 2, icon_rect.y() + 7)
            painter.drawLine(icon_rect.x() + 12, icon_rect.y() + 7, icon_rect.x() + 14, icon_rect.y() + 7)
        elif itype == "focus":
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
        elif itype == "browser":
            painter.drawEllipse(icon_rect.x() + 2, icon_rect.y() + 2, 10, 10)
            painter.drawEllipse(icon_rect.x() + 4, icon_rect.y() + 2, 6, 10)
            painter.drawLine(icon_rect.x() + 2, icon_rect.y() + 7, icon_rect.x() + 12, icon_rect.y() + 7)
        else:
            painter.drawEllipse(icon_rect)
            
        if self.text():
            painter.setPen(text_color)
            painter.setFont(self.font())
            text_rect = QRect(icon_rect.right() + 6, 0, rect.width() - icon_rect.right() - 12, rect.height())
            painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, self.text())

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
