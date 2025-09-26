from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout

class OutputPage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout()
        title = QLabel("📝 Сторінка опису заповнення")
        title.setStyleSheet("font-size: 24px;")
        layout.addWidget(title)
        self.setLayout(layout)
