import sys
import ctypes
import ctypes.wintypes
from PyQt5.QtWidgets import QApplication, QWidget, QPushButton, QVBoxLayout, QLineEdit
from PyQt5.QtCore import Qt

class HitTestTest(QWidget):
    def __init__(self):
        super().__init__()
        # No WS_EX_NOACTIVATE here!
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        self.btn = QPushButton("Click Me (No Activate)")
        self.btn.clicked.connect(lambda: print("Button clicked!"))
        
        self.input = QLineEdit("Click Me (Activate)")
        
        layout = QVBoxLayout(self)
        layout.addWidget(self.btn)
        layout.addWidget(self.input)
        layout.addStretch()
        
        self.resize(400, 400)
        
    def nativeEvent(self, eventType, message):
        if eventType == "windows_generic_MSG":
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == 0x0084: # WM_NCHITTEST
                x = msg.lParam & 0xFFFF
                if x > 32767: x -= 65536
                y = (msg.lParam >> 16) & 0xFFFF
                if y > 32767: y -= 65536
                
                from PyQt5.QtCore import QPoint
                local_pos = self.mapFromGlobal(QPoint(x, y))
                
                if self.btn.geometry().contains(local_pos) or self.input.geometry().contains(local_pos):
                    return False, 0 # Let Qt handle it (HTCLIENT)
                else:
                    return True, -1 # HTTRANSPARENT
                    
            elif msg.message == 0x0021: # WM_MOUSEACTIVATE
                # lParam low word is hit test code
                import win32api
                x, y = win32api.GetCursorPos()
                from PyQt5.QtCore import QPoint
                local_pos = self.mapFromGlobal(QPoint(x, y))
                
                if self.input.geometry().contains(local_pos):
                    return True, 1 # MA_ACTIVATE
                else:
                    return True, 3 # MA_NOACTIVATE
                    
        return super().nativeEvent(eventType, message)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = HitTestTest()
    w.show()
    sys.exit(app.exec_())
