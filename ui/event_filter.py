from PyQt5.QtCore import QObject, QPoint, QEvent, Qt
from PyQt5.QtGui import QMouseEvent

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
        self.cursor_modified = False

    def check_mouse_state(self):
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
            
            if getattr(self.overlay, 'focus_mode', '') == 'Background':
                is_resizing_area = False
                
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
