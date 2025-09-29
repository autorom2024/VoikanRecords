# key_manager_ui.py
# v1.1 — PySide6 діалог та індикатор для керування Google ключами (з антидублем)
from __future__ import annotations
from typing import List
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QHBoxLayout, QPushButton, QFileDialog, QMessageBox, QWidget, QApplication
)
from PySide6.QtCore import Qt, QTimer
from google_key_pool import KeyPool, KeyMeta, valid_indicator_text

def _style_btn(btn: QPushButton, bg: str, fg: str="white"):
    btn.setStyleSheet(f"""
        QPushButton {{
            background-color: {bg};
            color: {fg};
            border: none;
            border-radius: 8px;
            padding: 6px 12px;
            font-weight: 600;
        }}
        QPushButton:hover {{ filter: brightness(1.05); }}
        QPushButton:disabled {{ background-color: #334155; color: #94a3b8; }}
    """)

class KeyManagerDialog(QDialog):
    def __init__(self, pool: KeyPool, parent=None):
        super().__init__(parent)
        self.pool = pool
        self.setWindowTitle("Менеджер Google ключів")
        self.resize(620, 480)
        v=QVBoxLayout(self)

        self.lbl_summary = QLabel("Валідні ключі: —"); v.addWidget(self.lbl_summary)
        self.list = QListWidget(); self.list.setAlternatingRowColors(True); v.addWidget(self.list,1)

        row = QHBoxLayout(); v.addLayout(row)
        self.btn_add = QPushButton("Додати ключ…"); _style_btn(self.btn_add, "#22c55e")
        self.btn_delete = QPushButton("Видалити"); _style_btn(self.btn_delete, "#ef4444")
        self.btn_switch = QPushButton("Зробити активним"); _style_btn(self.btn_switch, "#3b82f6")
        self.btn_check = QPushButton("Перевірити всі"); _style_btn(self.btn_check, "#64748b")
        row.addWidget(self.btn_add); row.addWidget(self.btn_delete); row.addWidget(self.btn_switch); row.addStretch(); row.addWidget(self.btn_check)

        # підказки
        self.btn_add.setToolTip("Завантажити JSON ключ (drag&drop у діалог теж працює). Дублікати не додаються.")
        self.btn_delete.setToolTip("Видалити вибраний ключ із пулу")
        self.btn_switch.setToolTip("Ручне перемикання на вибраний VALID ключ")
        self.btn_check.setToolTip("Примусова перевірка валідності всіх ключів")

        self.setAcceptDrops(True)
        self.btn_add.clicked.connect(self._add)
        self.btn_delete.clicked.connect(self._delete)
        self.btn_switch.clicked.connect(self._switch)
        self.btn_check.clicked.connect(self._check_all)

        self._refresh()

        self._tm = QTimer(self); self._tm.setInterval(10_000); self._tm.timeout.connect(self._refresh)
        self._tm.start()

    # drag&drop
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): e.acceptProposedAction()
    def dropEvent(self, e):
        for u in e.mimeData().urls():
            path = u.toLocalFile()
            if path and path.lower().endswith(".json"):
                self._add_file(path)

    def _refresh(self):
        self.list.clear()
        v, t = self.pool.get_valid_counts()
        self.lbl_summary.setText(f"Валідні: {v}/{t}")
        for m in self.pool.list_keys():
            it = QListWidgetItem(f"{m.id} · {m.status} · помилок: {m.errors}")
            it.setData(Qt.UserRole, m.id)
            it.setToolTip(f"last_check={m.last_check}, quota_reset_at={m.quota_reset_at}")
            self.list.addItem(it)

    def _add(self):
        path, _ = QFileDialog.getOpenFileName(self, "Вибрати JSON ключ", "", "JSON (*.json)")
        if not path: return
        self._add_file(path)

    def _add_file(self, path: str):
        try:
            kid = self.pool.add_key_from_file(path)
            QMessageBox.information(self, "Ключ додано", f"ID: {kid}")
            self._refresh()
        except Exception as e:
            # якщо дублікат — покажемо м’яко
            QMessageBox.warning(self, "Увага", str(e))
            self._refresh()

    def _delete(self):
        it = self.list.currentItem()
        if not it: return
        kid = it.data(Qt.UserRole)
        self.pool.delete_key(kid)
        self._refresh()

    def _switch(self):
        it = self.list.currentItem()
        if not it: return
        kid = it.data(Qt.UserRole)
        ok = self.pool.manual_switch(kid)
        if not ok:
            QMessageBox.warning(self, "Перемикання", "Ключ не VALID або відсутній.")
        self._refresh()

    def _check_all(self):
        try:
            self.pool.health_check_all()
            self._refresh()
        except Exception as e:
            QMessageBox.critical(self, "Помилка перевірки", str(e))

class KeyIndicator(QWidget):
    """Маленький віджет (X/Y) для шапки; клік → менеджер."""
    def __init__(self, pool: KeyPool, parent=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QHBoxLayout, QPushButton, QLabel
        self.pool = pool
        lay = QHBoxLayout(self); lay.setContentsMargins(0,0,0,0)
        self.lbl = QLabel("Ключі: —"); self.lbl.setStyleSheet("color:#e2e8f0; font-weight:600;")
        self.btn_open = QPushButton("Менеджер ключів")
        _style_btn(self.btn_open, "#111827", "white")
        self.btn_open.setToolTip("Відкрити менеджер ключів (додати/видалити/перемкнути/перевірити)")
        lay.addWidget(self.lbl); lay.addWidget(self.btn_open)
        self.btn_open.clicked.connect(self._open)

        self._tm = QTimer(self); self._tm.setInterval(5000); self._tm.timeout.connect(self._tick)
        self._tm.start()
        self._tick()

    def _tick(self):
        self.lbl.setText(f"Ключі: {valid_indicator_text(self.pool)}")

    def _open(self):
        dlg = KeyManagerDialog(self.pool, self)
        dlg.exec()
        self._tick()

# Додатково: щоб можна було запускати менеджер окремо
if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    pool = KeyPool(admin_secret="demo")
    dlg = KeyManagerDialog(pool)
    dlg.exec()
