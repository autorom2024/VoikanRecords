# -*- coding: utf-8 -*-
import os
import sys
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow
from ui.theme_loader import load_stylesheet

# ---- Safe mode for Qt ----
os.environ.setdefault("QT_OPENGL", "software")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "0")

if not QApplication.instance():
    app = QApplication(sys.argv)
else:
    app = QApplication.instance()

# Використовуємо нову сучасну тему
app.setStyleSheet(load_stylesheet("dark_modern.qss"))

w = MainWindow(app)
w.show()
app.exec()
