# -*- coding: utf-8 -*-
"""
Theme loader with dark modern QSS application-wide.

Functions:
- load_stylesheet(path) -> str
- apply_stylesheet(app, path)

If path is None or unreadable, built-in theme is used.
"""

from __future__ import annotations
from pathlib import Path
from typing import Optional

# Built-in fallback QSS (kept moderate; main button styling is custom-painted in AnimatedButton)
_BUILTIN_QSS = r"""
/* Base */
* {
    font-family: "Segoe UI", "Inter", "Roboto", sans-serif;
    font-size: 14px;
}
QWidget {
    background-color: #0f1115;
    color: #e5e7eb;
}
QToolTip {
    background-color: #111827;
    color: #e5e7eb;
    border: 1px solid #374151;
    padding: 6px 8px;
    border-radius: 8px;
}

/* Containers */
QGroupBox {
    border: 1px solid #1f2937;
    border-radius: 10px;
    margin-top: 12px;
    padding: 10px 12px 12px 12px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    color: #f3f4f6;
    font-weight: 600;
}

/* Inputs */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #111827;
    color: #e5e7eb;
    border: 1px solid #374151;
    border-radius: 8px;
    padding: 8px 10px;
    selection-background-color: #60a5fa;
}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus,
QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 1px solid #3b82f6;
}

/* Lists/Tables */
QListWidget, QTreeWidget, QTableWidget, QListView, QTreeView, QTableView {
    background-color: #0b0f14;
    border: 1px solid #1f2937;
    border-radius: 8px;
}
QHeaderView::section {
    background-color: #111827;
    color: #d1d5db;
    padding: 6px 8px;
    border: none;
    border-right: 1px solid #1f2937;
    font-weight: 600;
}
QTableWidget::item:selected, QTreeWidget::item:selected, QListView::item:selected, QTreeView::item:selected {
    background-color: #2563eb;
    color: #ffffff;
}

/* Tabs */
QTabWidget::pane {
    border: 1px solid #1f2937;
    border-radius: 10px;
    padding: 8px;
}
QTabBar::tab {
    background-color: #0b0f14;
    color: #9ca3af;
    border: 1px solid #111827;
    border-radius: 8px;
    padding: 6px 12px;
    margin-right: 6px;
}
QTabBar::tab:selected {
    background-color: #1f2937;
    color: #f3f4f6;
}

/* Menus */
QMenuBar, QMenu {
    background-color: #0f1115;
    color: #e5e7eb;
    border: 1px solid #111827;
}
QMenu::item {
    padding: 6px 12px;
    border-radius: 6px;
}
QMenu::item:selected {
    background-color: #1f2937;
}

/* Progress/Slider */
QProgressBar {
    background: #0b0f14;
    border: 1px solid #1f2937;
    border-radius: 8px;
    height: 18px;
    text-align: center;
    color: #e5e7eb;
}
QProgressBar::chunk {
    background-color: #22c55e;
    border-radius: 8px;
}
QSlider::groove:horizontal {
    height: 6px;
    background: #1f2937;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #3b82f6;
    width: 16px;
    margin: -5px 0;
    border-radius: 8px;
}

/* Scrollbars */
QScrollBar:vertical, QScrollBar:horizontal {
    background: transparent;
    border: none;
    margin: 0px;
}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: #374151;
    border-radius: 5px;
}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {
    background: #4b5563;
}
"""

def load_stylesheet(path: Optional[str] = None) -> str:
    if path:
        p = Path(path).expanduser()
        if p.is_file():
            try:
                return p.read_text(encoding="utf-8")
            except Exception:
                pass
    return _BUILTIN_QSS

def apply_stylesheet(app, path: Optional[str] = None) -> None:
    app.setStyleSheet(load_stylesheet(path))
