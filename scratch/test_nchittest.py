import sys
import ctypes
import ctypes.wintypes
from PyQt5.QtWidgets import QApplication, QWidget, QPushButton, QVBoxLayout
from PyQt5.QtCore import Qt

class HitTestTest(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        self.btn = QPushButton("Click Me (Solid)")
        self.btn.clicked.connect(lambda: print("Button clicked!"))
        
        layout = QVBoxLayout(self)
        layout.addWidget(self.btn)
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
                
                local_pos = self.mapFromGlobal(self.mapToGlobal(self.mapFromGlobal(self.pos())) + self.mapFromGlobal(self.mapToGlobal(self.mapFromGlobal(self.pos())))) # simple approximation
                # Better local pos mapping:
                from PyQt5.QtCore import QPoint
                local_pos = self.mapFromGlobal(QPoint(x, y))
                
                if self.btn.geometry().contains(local_pos):
                    return False, 0 # Let Qt handle it (HTCLIENT)
                else:
                    return True, -1 # HTTRANSPARENT
                    
        return super().nativeEvent(eventType, message)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = HitTestTest()
    w.show()
    sys.exit(app.exec_())
