# -*- coding: utf-8 -*-
# ui/pages/photo_page.py

import os
import json
import threading
import queue
from typing import Tuple, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit,
    QPushButton, QFileDialog, QComboBox, QSpinBox, QCheckBox,
    QGridLayout, QMessageBox, QSplitter, QSizePolicy, QGroupBox,
    QDialog, QInputDialog, QScrollArea, QFrame
)
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QPixmap, QIcon, QFont

from logic.vertex_api import list_models_and_caps, vertex_generate_images

CONFIG_PATH = os.path.join(os.getcwd(), "photo_qt_config.json")
PRESETS_PATH = os.path.join(os.getcwd(), "photo_qt_presets.json")


def parse_aspect(text: str) -> Tuple[int, int]:
    """Парсинг '16:9' -> (16, 9). Якщо невідомо — 1:1."""
    try:
        a, b = text.replace("×", ":").split(":")
        w, h = int(a.strip()), int(b.strip())
        return (w if w > 0 else 1, h if h > 0 else 1)
    except Exception:
        return (1, 1)


class PreviewTile(QLabel):
    """
    Плитка превʼю з підтримкою аспекту та масштабування.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._aspect = (1, 1)
        self._image_path = None
        self.setAlignment(Qt.AlignCenter)
        self.setScaledContents(False)
        self.setStyleSheet("background: #f0f0f0; border: 1px solid #ccc;")
        self.setMinimumSize(100, 100)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_aspect(self, aspect: Tuple[int, int]):
        self._aspect = aspect

    def clear(self):
        super().clear()
        self._image_path = None

    def set_image_path(self, path: str):
        self._image_path = path
        pm = QPixmap(path)
        if pm.isNull():
            return
        self.setPixmap(pm)

    def resizeEvent(self, event):
        # Масштабуємо зображення при зміні розміру
        if self.pixmap() and not self.pixmap().isNull():
            pixmap = self.pixmap()
            scaled_pixmap = pixmap.scaled(
                self.size(), 
                Qt.KeepAspectRatio, 
                Qt.SmoothTransformation
            )
            self.setPixmap(scaled_pixmap)
        super().resizeEvent(event)

    def mousePressEvent(self, event):
        """Обробник кліку по зображенню - відкриває повний розмір"""
        if self._image_path and os.path.exists(self._image_path):
            self._show_fullsize_image()
        super().mousePressEvent(event)

    def _show_fullsize_image(self):
        """Показує зображення в повному розмірі"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Повний розмір зображення")
        dialog.setModal(True)
        dialog.resize(1000, 800)
        
        layout = QVBoxLayout(dialog)
        image_label = QLabel()
        image_label.setAlignment(Qt.AlignCenter)
        image_label.setStyleSheet("background: #222;")
        
        pixmap = QPixmap(self._image_path)
        if not pixmap.isNull():
            pixmap = pixmap.scaled(980, 780, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            image_label.setPixmap(pixmap)
        
        layout.addWidget(image_label)
        
        # Кнопка закриття
        btn_close = QPushButton("Закрити")
        btn_close.clicked.connect(dialog.close)
        layout.addWidget(btn_close)
        
        dialog.exec()


class PhotoPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self._host = None
        self.cancel_event = threading.Event()
        self.status_q = queue.Queue()
        self.models = []
        self.caps_by_model = {}
        self.gpt_key: Optional[str] = None
        self._preview_slot = 0
        self.presets = {}

        # --- Основний layout ---
        root = QVBoxLayout(self)
        root.setContentsMargins(5, 5, 5, 5)
        root.setSpacing(5)

        # --- Верхня панель ---
        top = QHBoxLayout()
        top.setSpacing(5)

        # GPT ключ
        gpt_group = QGroupBox("GPT API")
        gpt_group.setMaximumHeight(70)
        gpt_layout = QHBoxLayout(gpt_group)
        gpt_layout.addWidget(QLabel("Ключ:"))
        self.gpt_key_edit = QLineEdit()
        self.gpt_key_edit.setPlaceholderText("sk-...")
        self.gpt_key_edit.setEchoMode(QLineEdit.Password)
        gpt_layout.addWidget(self.gpt_key_edit, 1)
        
        self.btn_check_gpt = QPushButton("Перевірити")
        gpt_layout.addWidget(self.btn_check_gpt)
        top.addWidget(gpt_group)

        # Vertex JSON
        vertex_group = QGroupBox("Vertex AI")
        vertex_group.setMaximumHeight(70)
        vertex_layout = QHBoxLayout(vertex_group)
        vertex_layout.addWidget(QLabel("JSON:"))
        self.key_edit = QLineEdit()
        self.key_edit.setPlaceholderText("Johnson.json")
        vertex_layout.addWidget(self.key_edit, 1)
        
        self.btn_browse_key = QPushButton()
        self.btn_browse_key.setIcon(QIcon.fromTheme("document-open"))
        vertex_layout.addWidget(self.btn_browse_key)
        
        self.btn_auth = QPushButton("Авторизація")
        vertex_layout.addWidget(self.btn_auth)
        top.addWidget(vertex_group)

        # Вивід
        output_group = QGroupBox("Вивід")
        output_group.setMaximumHeight(70)
        output_layout = QHBoxLayout(output_group)
        output_layout.addWidget(QLabel("Тека:"))
        self.outdir_edit = QLineEdit()
        self.outdir_edit.setPlaceholderText("Збереження зображень")
        output_layout.addWidget(self.outdir_edit, 1)
        
        self.btn_browse_out = QPushButton()
        self.btn_browse_out.setIcon(QIcon.fromTheme("folder"))
        output_layout.addWidget(self.btn_browse_out)
        top.addWidget(output_group)

        root.addLayout(top)

        # --- Центральна панель ---
        center_splitter = QSplitter(Qt.Horizontal)
        
        # Ліва частина - налаштування
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        
        # Модель та параметри
        model_group = QGroupBox("Модель та параметри")
        model_layout = QGridLayout(model_group)
        
        model_layout.addWidget(QLabel("Модель:"), 0, 0)
        self.model_cb = QComboBox()
        model_layout.addWidget(self.model_cb, 0, 1)
        
        model_layout.addWidget(QLabel("Аспект:"), 1, 0)
        self.aspect_cb = QComboBox()
        model_layout.addWidget(self.aspect_cb, 1, 1)
        
        model_layout.addWidget(QLabel("Якість:"), 2, 0)
        self.quality_cb = QComboBox()
        self.quality_cb.addItems(["1K", "2K"])
        model_layout.addWidget(self.quality_cb, 2, 1)
        
        model_layout.addWidget(QLabel("Формат:"), 3, 0)
        self.format_cb = QComboBox()
        self.format_cb.addItems(["PNG", "JPEG", "WEBP"])
        model_layout.addWidget(self.format_cb, 3, 1)
        
        model_layout.addWidget(QLabel("x/виклик:"), 4, 0)
        self.pergen_sb = QSpinBox()
        self.pergen_sb.setRange(1, 4)
        self.pergen_sb.setValue(2)
        model_layout.addWidget(self.pergen_sb, 4, 1)
        
        model_layout.addWidget(QLabel("Генерацій:"), 5, 0)
        self.gens_sb = QSpinBox()
        self.gens_sb.setRange(1, 200)
        self.gens_sb.setValue(1)
        model_layout.addWidget(self.gens_sb, 5, 1)
        
        model_layout.addWidget(QLabel("Генератор:"), 6, 0)
        self.generator_cb = QComboBox()
        self.generator_cb.addItems(["Vertex", "GPT", "Gemini"])
        model_layout.addWidget(self.generator_cb, 6, 1)
        
        left_layout.addWidget(model_group)
        
        # Пресети
        presets_group = QGroupBox("Пресети налаштувань")
        presets_layout = QHBoxLayout(presets_group)
        
        self.presets_cb = QComboBox()
        self.presets_cb.setMinimumWidth(150)
        presets_layout.addWidget(self.presets_cb)
        
        self.btn_save_preset = QPushButton("Зберегти")
        presets_layout.addWidget(self.btn_save_preset)
        
        self.btn_load_preset = QPushButton("Завантажити")
        presets_layout.addWidget(self.btn_load_preset)
        
        self.btn_delete_preset = QPushButton("Видалити")
        presets_layout.addWidget(self.btn_delete_preset)
        
        left_layout.addWidget(presets_group)
        left_layout.addStretch()
        
        center_splitter.addWidget(left_widget)
        
        # Права частина - прев'ю
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        
        preview_group = QGroupBox("Попередній перегляд")
        preview_layout = QVBoxLayout(preview_group)
        
        # Контейнер для прев'ю з прокруткою
        preview_scroll = QScrollArea()
        preview_scroll.setWidgetResizable(True)
        preview_scroll.setMinimumHeight(300)
        
        self.preview_container = QWidget()
        self.preview_grid = QGridLayout(self.preview_container)
        self.preview_grid.setSpacing(10)
        self.preview_grid.setContentsMargins(10, 10, 10, 10)
        
        self.preview_tiles = [PreviewTile() for _ in range(4)]
        self._update_preview_layout(2)
        
        preview_scroll.setWidget(self.preview_container)
        preview_layout.addWidget(preview_scroll)
        
        right_layout.addWidget(preview_group)
        center_splitter.addWidget(right_widget)
        
        # Встановлюємо пропорції розділення
        center_splitter.setSizes([400, 600])
        
        root.addWidget(center_splitter, 1)

        # --- Нижня панель ---
        bottom = QVBoxLayout()
        
        # Поле введення промпту
        prompt_group = QGroupBox("Опис зображення")
        prompt_layout = QVBoxLayout(prompt_group)
        self.prompt_edit = QTextEdit()
        self.prompt_edit.setPlaceholderText("Введіть основний опис…")
        self.prompt_edit.setPlainText("Ultra realistic 8K cinematic sunset on a Hawaiian beach, beautiful young woman in bikini posing in different natural postures, wet skin with visible water drops and morning dew reflections, golden sunlight glowing on the ocean, cinematic lens flare, vivid tropical colors, professional album cover composition, modern stylish text 'DEEP HOUSE' integrated in neon/glow effect, photorealistic details, cinematic lighting, trending music artwork, deep house vibe, ultra sharp details")
        self.prompt_edit.setMaximumHeight(100)
        prompt_layout.addWidget(self.prompt_edit)
        bottom.addWidget(prompt_group)

        # Ключові характеристики
        keys_group = QGroupBox("Ключові характеристики")
        keys_layout = QGridLayout(keys_group)
        keys = [
            "Фотореалізм", "Кінематографічне світло", "Студійне освітлення", "8K HDR",
            "35mm Lens", "F1.8 Bokeh", "Глибина різкості", "Контрастні тіні",
            "Деталізовані текстури", "Субповерхневе розсіювання", "Натуральні кольори",
            "Портретний крупний план", "Ландшафт Golden Hour", "Продукт-шот на циклі", "Атмосферний туман",
            "Editorial / Vogue", "Аніме-ілюстрація", "CGI High-poly", "Cinematic Color Grade"
        ]
        self.key_checks = []
        for i, t in enumerate(keys):
            chk = QCheckBox(t)
            if t in ("Фотореалізм", "Кінематографічне світло", "8K HDR", "Натуральні кольори"):
                chk.setChecked(True)
            self.key_checks.append(chk)
            keys_layout.addWidget(chk, i // 3, i % 3)

        # Пресети трендів
        presets_row = QHBoxLayout()
        presets_row.addWidget(QLabel("Пресет трендів:"))
        self.preset_cb = QComboBox()
        self.preset_cb.addItems([
            "—", "Фотореал портрет", "Фешн editorial", "Продукт-шот", "Ландшафт", "Аніме / манґа"
        ])
        self.btn_apply_preset = QPushButton("Застосувати")
        presets_row.addWidget(self.preset_cb)
        presets_row.addWidget(self.btn_apply_preset)
        presets_row.addStretch()
        keys_layout.addLayout(presets_row, (len(keys) // 3) + 1, 0, 1, 3)

        bottom.addWidget(keys_group)
        root.addLayout(bottom)

        # --- Масштабування та стилі ---
        self._setup_scaling()

        # --- Події ---
        self.btn_browse_key.clicked.connect(self._choose_key)
        self.btn_browse_out.clicked.connect(self._choose_out)
        self.btn_auth.clicked.connect(self._auth_vertex)
        self.btn_check_gpt.clicked.connect(self._check_gpt_key)
        self.btn_apply_preset.clicked.connect(self._apply_preset)
        self.btn_save_preset.clicked.connect(self._save_current_preset)
        self.btn_load_preset.clicked.connect(self._load_selected_preset)
        self.btn_delete_preset.clicked.connect(self._delete_selected_preset)

        self.model_cb.currentIndexChanged.connect(self._on_model_changed)
        self.aspect_cb.currentIndexChanged.connect(self._on_aspect_changed)
        self.pergen_sb.valueChanged.connect(self._on_pergen_changed)

        self.preset_cb.currentIndexChanged.connect(self._maybe_hint_preset)

        # Таймер логів
        self.timer = QTimer(self)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self._drain_status)
        self.timer.start()

        # Встановлюємо дефолтні значення
        self.quality_cb.setCurrentText("2K")
        self.format_cb.setCurrentText("JPEG")
        self.generator_cb.setCurrentText("Vertex")
        self._load_config()
        self._load_presets()

    def _setup_scaling(self):
        """Налаштування масштабування для всіх елементів"""
        # Основний шрифт
        self.setFont(QFont("Arial", 9))
        
        # Стилі для масштабування
        scalable_style = """
            QWidget {
                font-size: 9pt;
            }
            QGroupBox {
                font-weight: bold;
                font-size: 9pt;
            }
            QLabel {
                font-size: 9pt;
            }
            QLineEdit, QTextEdit, QComboBox, QSpinBox {
                font-size: 9pt;
                padding: 3px;
            }
            QPushButton {
                font-size: 9pt;
                padding: 5px 10px;
            }
            QCheckBox {
                font-size: 9pt;
            }
        """
        
        self.setStyleSheet(scalable_style)
        
        # Встановлюємо розширювані політики розмірів
        for widget in [self.prompt_edit]:
            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            
        for group in self.findChildren(QGroupBox):
            group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    # ---------------- інтеграція з MainWindow ----------------
    def _resolve_host(self):
        if self._host:
            return self._host
        w = self.window()
        if w and hasattr(w, "log") and hasattr(w, "set_running"):
            self._host = w
        return self._host

    def handle_start(self, auto_mode: bool):
        self._start()

    def handle_stop(self):
        self._stop()

    # ---------------- утиліти ----------------
    def _log(self, text: str):
        host = self._resolve_host()
        if host:
            try:
                host.log(self, text)
            except Exception:
                pass

    def _choose_key(self):
        fn, _ = QFileDialog.getOpenFileName(self, "Johnson.json", "", "JSON Files (*.json)")
        if fn:
            self.key_edit.setText(fn)

    def _choose_out(self):
        d = QFileDialog.getExistingDirectory(self, "Тека збереження", os.getcwd())
        if d:
            self.outdir_edit.setText(d)

    # ---- Перевірка GPT ключа ----
    def _check_gpt_key(self):
        key = self.gpt_key_edit.text().strip()
        if not key:
            self._log("[GPT] ❌ Введіть GPT ключ")
            return
            
        try:
            from openai import OpenAI
            client = OpenAI(api_key=key)
            models = client.models.list()
            self._log("[GPT] ✅ Ключ валідний! Доступно моделей: " + str(len(models.data)))
            self.gpt_key = key
            self._save_config()
        except Exception as e:
            self._log(f"[GPT] ❌ Помилка перевірки ключа: {str(e)}")

    # ---- Авторизація Vertex ----
    def _auth_vertex(self):
        key = self.key_edit.text().strip()
        if not key or not os.path.exists(key):
            self._log("[Фото] ❌ Оберіть Johnson.json")
            return
        try:
            data = list_models_and_caps(key)
            self.models = data["models"]
            self.caps_by_model = data["caps"]

            self.model_cb.blockSignals(True)
            self.model_cb.clear()
            for m in self.models:
                self.model_cb.addItem(m["display"], m["id"])
            self.model_cb.blockSignals(False)

            # Вибираємо модель 'ultra' за замовчуванням
            ultra_index = -1
            for i in range(self.model_cb.count()):
                if "ultra" in self.model_cb.itemText(i).lower():
                    ultra_index = i
                    break
            
            if ultra_index >= 0:
                self.model_cb.setCurrentIndex(ultra_index)
            elif self.model_cb.count() > 0:
                self.model_cb.setCurrentIndex(0)

            if self.model_cb.count() > 0:
                self._on_model_changed()

            self.aspect_cb.blockSignals(True)
            if self.aspect_cb.findText("16:9") >= 0:
                self.aspect_cb.setCurrentText("16:9")
            self.aspect_cb.blockSignals(False)
            self._on_aspect_changed()

            self._save_config()
            self._log(f"[Фото] 🔐 Авторизація OK. Моделей: {len(self.models)}")
        except Exception as e:
            self._log(f"[Фото] ❌ Авторизація/моделі: {e}")

    # ---- Моделі/Аспекти ----
    def _on_model_changed(self):
        mid = self.model_cb.currentData()
        if not mid or mid not in self.caps_by_model:
            return
        caps = self.caps_by_model[mid]
        self.aspect_cb.blockSignals(True)
        self.aspect_cb.clear()
        self.aspect_cb.addItems(caps["aspects"])
        if self.aspect_cb.findText("16:9") >= 0:
            self.aspect_cb.setCurrentText("16:9")
        self.aspect_cb.blockSignals(False)
        self._on_aspect_changed()

    def _on_aspect_changed(self):
        asp = self.aspect_cb.currentText() or "1:1"
        a = parse_aspect(asp)
        for t in self.preview_tiles:
            t.set_aspect(a)

    def _on_pergen_changed(self, val: int):
        self._update_preview_layout(val)

    # ---- Старт/Стоп ----
    def _start(self):
        # Автоочистка превʼю
        for t in self.preview_tiles:
            t.clear()

        key = self.key_edit.text().strip()
        if not key or not os.path.exists(key):
            QMessageBox.warning(self, "Vertex", "Оберіть Johnson.json")
            return

        base_prompt = self.prompt_edit.toPlainText().strip()
        if not base_prompt:
            QMessageBox.warning(self, "Vertex", "Введіть промт")
            return

        tags = [chk.text() for chk in self.key_checks if chk.isChecked()]
        outdir = self.outdir_edit.text().strip() or os.path.join(os.getcwd(), "vertex_out")
        os.makedirs(outdir, exist_ok=True)

        model = self.model_cb.currentData()
        aspect = self.aspect_cb.currentText()
        quality = self.quality_cb.currentText()
        per_gen = int(self.pergen_sb.value())
        gens = int(self.gens_sb.value())
        file_format = self.format_cb.currentText().lower()

        host = self._resolve_host()
        if host:
            try:
                host.set_running(self, True)
            except Exception:
                pass

        self.cancel_event.clear()
        self._preview_slot = 0  # Скидаємо лічильник прев'ю

        def work():
            try:
                for i in range(gens):
                    if self.cancel_event.is_set():
                        break

                    prompt_i = self._make_prompt_for_batch(base_prompt, tags, aspect, quality, i + 1, gens)
                    self._log(f"[GPT] 📝 Prompt {i+1}/{gens}: {prompt_i[:140]}…")

                    # Скидаємо прев'ю для кожної нової генерації
                    self._preview_slot = 0
                    for t in self.preview_tiles:
                        t.clear()

                    vertex_generate_images(
                        prompts=[prompt_i],
                        key_file=key,
                        outdir=outdir,
                        batches=1,
                        per_gen=per_gen,
                        quality=quality,
                        model=model,
                        file_format=file_format,
                        aspect=aspect,
                        enhance=False,
                        cancel_event=self.cancel_event,
                        status_q=self.status_q,
                        preview_cb=self._preview_set,
                        location=None,
                    )
            finally:
                h = self._resolve_host()
                if h:
                    try:
                        h.set_running(self, False)
                    except Exception:
                        pass

        threading.Thread(target=work, daemon=True).start()
        self._log("[Фото] ▶ Старт генерації → " + outdir)

    def _stop(self):
        self.cancel_event.set()
        self._log("[Фото] ⏹ Зупинка.")

    # ---- Промт-двигун ----
    def _make_prompt_for_batch(self, base: str, tags: list, aspect: str, quality: str, idx: int, total: int) -> str:
        preset = self.preset_cb.currentText()
        preset_tags = {
            "Фотореал портрет": ["Фотореалізм", "Студійне освітлення", "F1.8 Bokeh", "35mm Lens", "Глибина різкості", "Cinematic Color Grade"],
            "Фешн editorial": ["Editorial / Vogue", "Студійне освітлення", "Натуральні кольори", "Фотореалізм", "Контрастні тіні"],
            "Продукт-шот": ["Продукт-шот на циклі", "Студійне освітлення", "Деталізовані текстури", "8K HDR", "Cinematic Color Grade"],
            "Ландшафт": ["Ландшафт Golden Hour", "Кінематографічне світло", "Натуральні кольори", "Атмосферний туман"],
            "Аніме / манґа": ["Аніме-ілюстрація", "CGI High-poly", "Натуральні кольори"],
        }
        
        if preset != "—" and preset in preset_tags:
            tags = list(set(tags + preset_tags[preset]))
        
        if self.generator_cb.currentText() == "GPT" and self.gpt_key:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=self.gpt_key)
                sys = (
                    "Ти – майстер складання стислих промтів для фотореалістичної генерації. "
                    "Використовуй ключові слова користувача, уникай води, без зайвих пояснень. "
                    "В 1 рядок. Без хештегів. Без лапок."
                )
                user = (
                    f"Опис: {base}\n"
                    f"Ключові: {', '.join(tags)}\n"
                    f"Аспект: {aspect}; Якість: {quality}\n"
                    f"Зроби унікальний промт №{idx} із {total} (варіюй деталі/світло/оптику)."
                )
                resp = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "system", "content": sys},
                              {"role": "user", "content": user}],
                    temperature=0.9,
                    max_tokens=160
                )
                text = (resp.choices[0].message.content or "").strip()
                return text if text else f"{base}, {', '.join(tags)}"
            except Exception as e:
                self._log(f"[GPT] ⚠️ Fallback: {e}")
                return f"{base}, {', '.join(tags)}"
        else:
            import random
            sel = tags[:]
            random.shuffle(sel)
            sel = sel[: min(6, len(sel))]
            return base + (", " + ", ".join(sel) if sel else "")

    # ---- Превʼю ----
    def _update_preview_layout(self, count: int):
        # Очищаємо сітку
        while self.preview_grid.count():
            item = self.preview_grid.takeAt(0)
            if item and item.widget():
                item.widget().setParent(None)
        
        # Додаємо потрібну кількість плиток
        if count == 1:
            self.preview_grid.addWidget(self.preview_tiles[0], 0, 0)
            self.preview_tiles[0].show()
            for i in range(1, 4):
                self.preview_tiles[i].hide()
        elif count == 2:
            self.preview_grid.addWidget(self.preview_tiles[0], 0, 0)
            self.preview_grid.addWidget(self.preview_tiles[1], 0, 1)
            for i in range(2):
                self.preview_tiles[i].show()
            for i in range(2, 4):
                self.preview_tiles[i].hide()
        else:
            self.preview_grid.addWidget(self.preview_tiles[0], 0, 0)
            self.preview_grid.addWidget(self.preview_tiles[1], 0, 1)
            self.preview_grid.addWidget(self.preview_tiles[2], 1, 0)
            self.preview_grid.addWidget(self.preview_tiles[3], 1, 1)
            for i in range(4):
                self.preview_tiles[i].show()

    def _preview_set(self, path: str):
        """Відображає згенероване зображення в прев'ю"""
        if self._preview_slot >= len(self.preview_tiles):
            return
            
        if not os.path.exists(path):
            return
            
        # Оновлюємо відповідну плитку
        tile = self.preview_tiles[self._preview_slot]
        tile.set_image_path(path)
        self._preview_slot += 1

    # ---- Логи ----
    def _drain_status(self):
        try:
            while True:
                msg = self.status_q.get_nowait()
                if isinstance(msg, dict) and "msg" in msg:
                    self._log(msg["msg"])
        except queue.Empty:
            pass

    # ---- Пресети ----
    def _maybe_hint_preset(self, _):
        pass

    def _apply_preset(self):
        preset = self.preset_cb.currentText()
        map_on = {
            "Фотореал портрет": {"Фотореалізм","Студійне освітлення","F1.8 Bokeh","35mm Lens","Глибина різкості","Cinematic Color Grade"},
            "Фешн editorial": {"Editorial / Vogue","Студійне освітлення","Натуральні кольори","Фотореалізм","Контрастні тіні"},
            "Продукт-шот": {"Продукт-шот на циклі","Студійне освітлення","Деталізовані текстури","8K HDR","Cinematic Color Grade"},
            "Ландшафт": {"Ландшафт Golden Hour","Кінематографічне світло","Натуральні кольори","Атмосферний туман"},
            "Аніме / манґа": {"Аніме-ілюстрація","CGI High-poly","Натуральні кольори"},
        }
        if preset in map_on:
            wanted = map_on[preset]
            for chk in self.key_checks:
                chk.setChecked(chk.text() in wanted)

    # ---- Збереження/завантаження пресетів ----
    def _load_presets(self):
        if not os.path.exists(PRESETS_PATH):
            return
        try:
            with open(PRESETS_PATH, "r", encoding="utf-8") as f:
                self.presets = json.load(f)
            
            self.presets_cb.clear()
            self.presets_cb.addItems(list(self.presets.keys()))
        except Exception as e:
            self._log(f"[Пресети] ❌ Помилка завантаження: {e}")

    def _save_presets(self):
        try:
            with open(PRESETS_PATH, "w", encoding="utf-8") as f:
                json.dump(self.presets, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            self._log(f"[Пресети] ❌ Помилка збереження: {e}")
            return False

    def _save_current_preset(self):
        preset_name, ok = QInputDialog.getText(
            self, "Збереження пресету", "Введіть назву пресету:"
        )
        
        if not ok or not preset_name:
            return
            
        preset_data = {
            "prompt": self.prompt_edit.toPlainText(),
            "keys": [chk.text() for chk in self.key_checks if chk.isChecked()],
            "model": self.model_cb.currentText(),
            "aspect": self.aspect_cb.currentText(),
            "quality": self.quality_cb.currentText(),
            "format": self.format_cb.currentText(),
            "per_gen": self.pergen_sb.value(),
            "gens": self.gens_sb.value(),
            "generator": self.generator_cb.currentText(),
            "key_file": self.key_edit.text(),
            "outdir": self.outdir_edit.text(),
            "gpt_key": self.gpt_key_edit.text()
        }
        
        self.presets[preset_name] = preset_data
        
        if self._save_presets():
            self.presets_cb.clear()
            self.presets_cb.addItems(list(self.presets.keys()))
            self.presets_cb.setCurrentText(preset_name)
            self._log(f"[Пресети] ✅ Пресет '{preset_name}' збережено")

    def _load_selected_preset(self):
        preset_name = self.presets_cb.currentText()
        if not preset_name or preset_name not in self.presets:
            self._log("[Пресети] ❌ Оберіть пресет для завантаження")
            return
            
        preset_data = self.presets[preset_name]
        
        self.prompt_edit.setPlainText(preset_data.get("prompt", ""))
        
        for chk in self.key_checks:
            chk.setChecked(chk.text() in preset_data.get("keys", []))
        
        self.model_cb.setCurrentText(preset_data.get("model", ""))
        self.aspect_cb.setCurrentText(preset_data.get("aspect", "16:9"))
        self.quality_cb.setCurrentText(preset_data.get("quality", "2K"))
        self.format_cb.setCurrentText(preset_data.get("format", "JPEG"))
        self.pergen_sb.setValue(preset_data.get("per_gen", 2))
        self.gens_sb.setValue(preset_data.get("gens", 1))
        self.generator_cb.setCurrentText(preset_data.get("generator", "Vertex"))
        self.key_edit.setText(preset_data.get("key_file", ""))
        self.outdir_edit.setText(preset_data.get("outdir", ""))
        self.gpt_key_edit.setText(preset_data.get("gpt_key", ""))
        
        self._log(f"[Пресети] ✅ Пресет '{preset_name}' завантажено")

    def _delete_selected_preset(self):
        preset_name = self.presets_cb.currentText()
        if not preset_name or preset_name not in self.presets:
            self._log("[Пресети] ❌ Оберіть пресет для видалення")
            return
            
        reply = QMessageBox.question(
            self, 
            "Підтвердження видалення", 
            f"Ви впевнені, що хочете видалити пресет '{preset_name}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            del self.presets[preset_name]
            if self._save_presets():
                self.presets_cb.clear()
                self.presets_cb.addItems(list(self.presets.keys()))
                self._log(f"[Пресети] ✅ Пресет '{preset_name}' видалено")

    # ---- Конфіг ----
    def _save_config(self):
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump({
                    "key": self.key_edit.text().strip(),
                    "outdir": self.outdir_edit.text().strip(),
                    "gpt_key": self.gpt_key_edit.text().strip() or ""
                }, f)
        except Exception:
            pass

    def _load_config(self):
        if not os.path.exists(CONFIG_PATH):
            return
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                d = json.load(f)
            if d.get("key"):
                self.key_edit.setText(d["key"])
            if d.get("outdir"):
                self.outdir_edit.setText(d["outdir"])
            if d.get("gpt_key"):
                self.gpt_key_edit.setText(d["gpt_key"])
                self.gpt_key = d["gpt_key"]
        except Exception:
            pass