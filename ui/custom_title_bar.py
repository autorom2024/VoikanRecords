# D:\VOIKAN R\ui\custom_title_bar.py
from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton

class CustomTitleBar(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent_window = parent
        self.setObjectName("CustomTitleBar")
        
        self.icon_label = QLabel(self)
        self.title_label = QLabel(self.parent_window.windowTitle(), self)
        
        self.minimize_button = QPushButton("—", self)
        self.maximize_button = QPushButton("☐", self)
        self.close_button = QPushButton("✕", self)

        self.title_label.setObjectName("titleBarLabel")
        self.minimize_button.setObjectName("minimizeButton")
        self.maximize_button.setObjectName("maximizeButton")
        self.close_button.setObjectName("closeButton")
        
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(10, 0, 0, 0)
        self.layout.setSpacing(10)
        
        self.layout.addWidget(self.icon_label)
        self.layout.addWidget(self.title_label)
        self.layout.addStretch()
        
        self.right_widgets_layout = QHBoxLayout()
        self.right_widgets_layout.setContentsMargins(0, 0, 0, 0)
        self.right_widgets_layout.setSpacing(10)
        self.layout.addLayout(self.right_widgets_layout)
        
        self.layout.addWidget(self.minimize_button)
        self.layout.addWidget(self.maximize_button)
        self.layout.addWidget(self.close_button)

        self.minimize_button.clicked.connect(self.parent_window.showMinimized)
        self.maximize_button.clicked.connect(self.toggle_maximize_restore)
        self.close_button.clicked.connect(self.parent_window.close)
        
        self.update_window_state()

    def add_widget_to_right(self, widget):
        self.right_widgets_layout.addWidget(widget)

    def toggle_maximize_restore(self):
        if self.parent_window.isMaximized(): self.parent_window.showNormal()
        else: self.parent_window.showMaximized()
        self.update_window_state()

    def update_window_state(self):
        self.title_label.setText(self.parent_window.windowTitle())
        icon = self.parent_window.windowIcon()
        if not icon.isNull(): self.icon_label.setPixmap(icon.pixmap(16, 16))
        if self.parent_window.isMaximized(): self.maximize_button.setText("⧉")
        else: self.maximize_button.setText("☐")
            
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self.parent_window.isMaximized():
            self.drag_pos = event.globalPosition().toPoint()
            event.accept()

    def mouseMoveEvent(self, event):
        if hasattr(self, 'drag_pos') and event.buttons() == Qt.LeftButton and not self.parent_window.isMaximized():
            try:
                new_pos = self.parent_window.pos() + event.globalPosition().toPoint() - self.drag_pos
                self.parent_window.move(new_pos)
                self.drag_pos = event.globalPosition().toPoint()
                event.accept()
            except RuntimeError: pass
            
    def mouseDoubleClickEvent(self, event):
        self.toggle_maximize_restore(); event.accept()