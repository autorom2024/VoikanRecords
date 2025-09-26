# Зміна дизайну заборонена поки я вказівку не дам

def load_stylesheet(path=None):
    qss = '''
QWidget {
    background-color: #1e1e1e;
    color: #ffffff;
    font-size: 15px;
    font-family: "Segoe UI", sans-serif;
}

QGroupBox {
    border: 1px solid #444;
    border-radius: 10px;
    margin-top: 14px;
    padding: 12px;
    color: #ffffff;
    font-size: 16px;
    font-weight: 600;
    margin-bottom: 12px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    font-size: 17px;
    font-weight: 700;
    color: #ffffff;
}

QLineEdit, QComboBox, QSpinBox, QTextEdit {
    background-color: #2a2a2a;
    color: #ffffff;
    border: 1px solid #444;
    border-radius: 8px;
    padding: 6px 10px;
    font-size: 15px;
    selection-background-color: #4ADE80;
}

QPushButton {
    background-color: #3a3a3a;
    border: none;
    border-radius: 10px;
    padding: 10px 20px;
    color: #ffffff;
    font-size: 15px;
    font-weight: 600;
    transition: all 0.25s ease-in-out;
}

QPushButton#startBtn {
    background-color: #2563eb;
}

QPushButton#stopBtn {
    background-color: #ef4444;
}

QPushButton:hover {
    background-color: #4b5563;
}

QPushButton:pressed {
    background-color: #6b7280;
}

QRadioButton, QCheckBox {
    spacing: 6px;
    color: #ffffff;
    font-size: 15px;
}

QListWidget {
    background-color: #1e1e1e;
    color: #ffffff;
    font-size: 17px;
    border: none;
    padding: 10px;
}

QListWidget::item {
    padding: 12px 16px;
    border-radius: 8px;
    margin-bottom: 6px;
}

QListWidget::item:selected {
    background-color: #3b82f6;
    color: #ffffff;
    font-weight: 700;
}

QTabWidget::pane {
    border: 1px solid #444;
    border-radius: 10px;
    background: #1e1e1e;
    padding: 8px;
}

QTabBar::tab {
    background-color: #2a2a2a;
    border: 1px solid #333;
    border-radius: 6px;
    padding: 6px 14px;
    margin-right: 4px;
    color: #ccc;
}

QTabBar::tab:selected {
    background-color: #3b82f6;
    color: #fff;
    font-weight: 600;
}

QProgressBar {
    border: 1px solid #444;
    border-radius: 6px;
    background: #2a2a2a;
    text-align: center;
    color: #ffffff;
    font-size: 13px;
    height: 18px;
}

QProgressBar::chunk {
    background-color: #4ADE80;
    border-radius: 6px;
}

QMenuBar, QMenu {
    background-color: #1e1e1e;
    color: #ffffff;
    font-size: 14px;
}

QMenuBar::item {
    background: transparent;
    padding: 6px 12px;
    border-radius: 4px;
}

QMenuBar::item:selected {
    background: #333;
}

QMenu::item:selected {
    background-color: #3a3a3a;
}

/* ---- Лише додано темний стиль для таблиць і списків ---- */
QTableWidget, QTreeWidget, QListView {
    background-color: #1e1e1e;
    color: #ffffff;
    border: 1px solid #333;
    border-radius: 6px;
    gridline-color: #333;
}

QHeaderView::section {
    background-color: #2a2a2a;
    color: #ddd;
    padding: 6px;
    border: none;
    border-right: 1px solid #444;
    font-weight: 600;
}

QTableWidget::item:selected, QTreeWidget::item:selected, QListView::item:selected {
    background-color: #3b82f6;
    color: #ffffff;
    font-weight: 600;
}

QScrollBar:vertical, QScrollBar:horizontal {
    background: #1e1e1e;
    border: none;
    margin: 0px;
}

QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: #444;
    border-radius: 5px;
}

QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {
    background: #666;
}
'''
    return qss
