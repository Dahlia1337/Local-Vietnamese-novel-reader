import io
from typing import List
from PIL import Image
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QListWidget,
    QListWidgetItem, QPushButton, QLabel, QComboBox, QSlider, QSplitter,
    QTextEdit, QDialog, QFileDialog, QStyle, QFrame, QProgressBar,
    QApplication, QMessageBox
)
from PyQt6.QtCore import Qt, QSize, QBuffer, QIODevice, QEvent
from PyQt6.QtGui import QFont, QIcon, QImage, QPixmap, QKeySequence, QShortcut

from ocr_engine import OCRWorker

DARK_QSS = """
QMainWindow, QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 13px;
}
QListWidget {
    background-color: #181825;
    border: 1px solid #313244;
    border-radius: 8px;
    padding: 5px;
}
QListWidget::item {
    padding: 8px;
    border-radius: 4px;
    margin-bottom: 2px;
}
QListWidget::item:selected {
    background-color: #45475a;
    color: #89b4fa;
}
QListWidget::item:hover {
    background-color: #313244;
}
QPushButton {
    background-color: #89b4fa;
    color: #11111b;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #b4befe;
}
QPushButton:pressed {
    background-color: #74c7ec;
}
QComboBox, QSlider {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 4px;
    color: #cdd6f4;
}
QFrame#ControlBar {
    background-color: #181825;
    border-top: 1px solid #313244;
}
QTextEdit {
    background-color: #181825;
    color: #cdd6f4;
    border: 1px solid #313244;
    border-radius: 8px;
    padding: 8px;
    line-height: 1.5;
}
QProgressBar {
    background-color: #181825;
    border: 1px solid #313244;
    border-radius: 6px;
    text-align: center;
    color: #cdd6f4;
    min-height: 18px;
}
QProgressBar::chunk {
    background-color: #89b4fa;
    border-radius: 5px;
}
QPushButton:disabled {
    background-color: #45475a;
    color: #7f849c;
}
QPushButton#DangerBtn {
    background-color: #f38ba8;
    color: #11111b;
}
QPushButton#DangerBtn:hover {
    background-color: #eba0ac;
}
QPushButton#SecondaryBtn {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
}
QPushButton#SecondaryBtn:hover {
    background-color: #45475a;
}
"""

class MainWindowUI(QMainWindow):
    def setup_ui(self):
        self.setWindowTitle("Vietnamese Novel Dual TTS Reader")
        self.resize(1100, 700)
        self.setStyleSheet(DARK_QSS)

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Splitter chính
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ---- SIDEBAR LEFT ----
        sidebar = QWidget()
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(10, 10, 10, 10)

        sidebar_layout.addWidget(QLabel("<b>DANH SÁCH TRUYỆN</b>"))
        self.book_list = QListWidget()
        sidebar_layout.addWidget(self.book_list)

        self.btn_new_book = QPushButton("Tạo truyện mới")
        self.btn_import_txt = QPushButton("Nhập file .TXT")
        self.btn_bulk_paste = QPushButton("Dán hàng loạt")
        self.btn_ocr_scan = QPushButton("Quét ảnh OCR (Ctrl+V)")
        sidebar_layout.addWidget(self.btn_new_book)
        sidebar_layout.addWidget(self.btn_import_txt)
        sidebar_layout.addWidget(self.btn_bulk_paste)
        sidebar_layout.addWidget(self.btn_ocr_scan)

        sidebar_layout.addWidget(QLabel("<b>DANH SÁCH CHƯƠNG</b>"))
        self.chapter_list = QListWidget()
        sidebar_layout.addWidget(self.chapter_list)

        splitter.addWidget(sidebar)

        # ---- CENTER READER VIEW ----
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(10, 10, 10, 10)

        self.lbl_chapter_title = QLabel("Chọn chương để đọc")
        self.lbl_chapter_title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        center_layout.addWidget(self.lbl_chapter_title)

        self.sentence_list = QListWidget()
        self.sentence_list.setWordWrap(True)
        center_layout.addWidget(self.sentence_list)

        splitter.addWidget(center_widget)
        splitter.setSizes([300, 800])
        main_layout.addWidget(splitter)

        # ---- BOTTOM CONTROL BAR ----
        control_bar = QFrame()
        control_bar.setObjectName("ControlBar")
        control_layout = QHBoxLayout(control_bar)
        control_layout.setContentsMargins(15, 10, 15, 10)

        # Playback Controls
        self.btn_prev_chap = QPushButton("Chương trước")
        self.btn_prev_sent = QPushButton("◄ Câu")
        self.btn_play = QPushButton("Phát")
        self.btn_next_sent = QPushButton("Câu ►")
        self.btn_next_chap = QPushButton("Chương sau")

        control_layout.addWidget(self.btn_prev_chap)
        control_layout.addWidget(self.btn_prev_sent)
        control_layout.addWidget(self.btn_play)
        control_layout.addWidget(self.btn_next_sent)
        control_layout.addWidget(self.btn_next_chap)

        control_layout.addSpacing(20)

        # Engine & Voice Selector
        control_layout.addWidget(QLabel("Engine:"))
        self.combo_engine = QComboBox()
        self.combo_engine.addItems(["Edge-TTS (Online)", "Piper TTS (Offline)"])
        control_layout.addWidget(self.combo_engine)

        control_layout.addWidget(QLabel("Giọng đọc:"))
        self.combo_voice = QComboBox()
        self.combo_voice.addItems([
            "Nam chuẩn (NamMinh)",
            "Nữ chuẩn (HoaiMy)",
            "Nam trầm (Pitch -6Hz)",
            "Nữ trẻ (Pitch +8Hz)"
        ])
        control_layout.addWidget(self.combo_voice)

        # Speed Slider
        control_layout.addWidget(QLabel("Tốc độ:"))
        self.slider_speed = QSlider(Qt.Orientation.Horizontal)
        self.slider_speed.setRange(75, 200)
        self.slider_speed.setValue(100)
        self.lbl_speed_val = QLabel("1.0x")
        control_layout.addWidget(self.slider_speed)
        control_layout.addWidget(self.lbl_speed_val)

        main_layout.addWidget(control_bar)


class OCRDialog(QDialog):
    """
    Cửa sổ hàng đợi ảnh OCR hỗ trợ dán liên tiếp từ Clipboard (Win+Shift+S -> Ctrl+V),
    quét OCR chạy nền qua OCRWorker, xem trước/chỉnh sửa văn bản và lưu vào thư viện.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Quét OCR từ Clipboard & Ghép đoạn")
        self.resize(960, 660)
        self.setStyleSheet(DARK_QSS)

        self._queued_images: List[Image.Image] = []
        self._worker: OCRWorker | None = None

        self._setup_ui()
        self._connect_events()

    def _setup_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setSpacing(10)

        hint_lbl = QLabel(
            "Mẹo: Dùng <b>Win + Shift + S</b> để chụp vùng chữ trên web chống copy, "
            "sau đó nhấn <b>Ctrl + V</b> liên tiếp vào đây để xếp hàng đợi theo thứ tự."
        )
        hint_lbl.setWordWrap(True)
        root_layout.addWidget(hint_lbl)

        # Thanh công cụ hàng đợi ảnh
        toolbar = QHBoxLayout()
        self.btn_paste_img = QPushButton("Dán ảnh (Ctrl+V)")
        self.btn_add_files = QPushButton("Chọn file ảnh...")
        self.btn_add_files.setObjectName("SecondaryBtn")
        self.btn_remove_img = QPushButton("Xóa ảnh")
        self.btn_remove_img.setObjectName("SecondaryBtn")
        self.btn_clear_imgs = QPushButton("Xóa tất cả")
        self.btn_clear_imgs.setObjectName("DangerBtn")

        toolbar.addWidget(self.btn_paste_img)
        toolbar.addWidget(self.btn_add_files)
        toolbar.addWidget(self.btn_remove_img)
        toolbar.addWidget(self.btn_clear_imgs)
        toolbar.addStretch()
        root_layout.addLayout(toolbar)

        # Splitter trái (Hàng đợi ảnh) - phải (Tiến độ & Xem trước văn bản)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.lbl_queue_count = QLabel("<b>Hàng đợi ảnh (0)</b>")
        left_layout.addWidget(self.lbl_queue_count)

        self.queue_list = QListWidget()
        self.queue_list.setIconSize(QSize(110, 72))
        left_layout.addWidget(self.queue_list)
        splitter.addWidget(left_panel)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        scan_bar = QHBoxLayout()
        self.btn_start_ocr = QPushButton("Bắt đầu quét OCR")
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        scan_bar.addWidget(self.btn_start_ocr)
        scan_bar.addWidget(self.progress_bar, 1)
        right_layout.addLayout(scan_bar)

        self.lbl_ocr_status = QLabel("Sẵn sàng. Hãy dán ảnh hoặc chọn file ảnh.")
        right_layout.addWidget(self.lbl_ocr_status)

        right_layout.addWidget(QLabel("<b>Xem trước & Chỉnh sửa văn bản sau ghép đoạn:</b>"))
        self.text_preview = QTextEdit()
        self.text_preview.setPlaceholderText(
            "Văn bản sau khi quét OCR và tự động ghép đoạn sẽ hiển thị tại đây..."
        )
        self.text_preview.installEventFilter(self)
        right_layout.addWidget(self.text_preview)

        self.btn_save = QPushButton("Tách chương và Lưu")
        right_layout.addWidget(self.btn_save)

        splitter.addWidget(right_panel)
        splitter.setSizes([320, 640])
        root_layout.addWidget(splitter, 1)

    def _connect_events(self):
        self.btn_paste_img.clicked.connect(self.paste_from_clipboard)
        self.btn_add_files.clicked.connect(self.add_image_files)
        self.btn_remove_img.clicked.connect(self.remove_selected_image)
        self.btn_clear_imgs.clicked.connect(self.clear_all_images)
        self.btn_start_ocr.clicked.connect(self.start_ocr)
        self.btn_save.clicked.connect(self._on_save_clicked)

        self._paste_shortcut = QShortcut(QKeySequence("Ctrl+V"), self)
        self._paste_shortcut.activated.connect(self._on_ctrl_v_shortcut)

    def eventFilter(self, obj, event):
        if obj is self.text_preview and event.type() == QEvent.Type.KeyPress:
            if event.matches(QKeySequence.StandardKey.Paste):
                clipboard = QApplication.clipboard()
                if clipboard.mimeData() and clipboard.mimeData().hasImage():
                    self.paste_from_clipboard()
                    return True
        return super().eventFilter(obj, event)

    def _on_ctrl_v_shortcut(self):
        clipboard = QApplication.clipboard()
        mime = clipboard.mimeData()
        if mime and mime.hasImage():
            self.paste_from_clipboard()
        elif self.text_preview.hasFocus():
            self.text_preview.paste()
        else:
            self.paste_from_clipboard()

    @staticmethod
    def _qimage_to_pil(qimage: QImage) -> Image.Image:
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.ReadWrite)
        qimage.save(buffer, "PNG")
        return Image.open(io.BytesIO(bytes(buffer.data()))).convert("RGB")

    def _enqueue_image(self, pil_img: Image.Image, qpixmap: QPixmap, label: str = ""):
        self._queued_images.append(pil_img)
        idx = len(self._queued_images)
        thumb = qpixmap.scaled(
            110, 72,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        title = label or f"Ảnh {idx} ({pil_img.width}x{pil_img.height})"
        item = QListWidgetItem(QIcon(thumb), title)
        self.queue_list.addItem(item)
        self.queue_list.setCurrentItem(item)
        self._refresh_queue_labels()

    def _refresh_queue_labels(self):
        total = len(self._queued_images)
        self.lbl_queue_count.setText(f"<b>Hàng đợi ảnh ({total})</b>")
        for i in range(self.queue_list.count()):
            img = self._queued_images[i]
            self.queue_list.item(i).setText(f"Ảnh {i + 1} ({img.width}x{img.height})")

    def paste_from_clipboard(self) -> bool:
        clipboard = QApplication.clipboard()
        mime = clipboard.mimeData()
        if not mime or not mime.hasImage():
            self.lbl_ocr_status.setText("Clipboard hiện không có ảnh.")
            return False

        qimage = clipboard.image()
        if qimage.isNull():
            self.lbl_ocr_status.setText("Không thể đọc dữ liệu ảnh từ Clipboard.")
            return False

        pil_img = self._qimage_to_pil(qimage)
        pixmap = QPixmap.fromImage(qimage)
        self._enqueue_image(pil_img, pixmap)
        self.lbl_ocr_status.setText(
            f"Đã thêm ảnh #{len(self._queued_images)} từ Clipboard."
        )
        return True

    def add_image_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Chọn ảnh cần quét OCR",
            "",
            "Image Files (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        for path in paths:
            try:
                pil_img = Image.open(path).convert("RGB")
                pixmap = QPixmap(path)
                self._enqueue_image(pil_img, pixmap)
            except Exception as exc:
                QMessageBox.warning(self, "Lỗi đọc ảnh", f"Không thể mở {path}:\n{exc}")

    def remove_selected_image(self):
        row = self.queue_list.currentRow()
        if 0 <= row < len(self._queued_images):
            self._queued_images.pop(row)
            self.queue_list.takeItem(row)
            self._refresh_queue_labels()

    def clear_all_images(self):
        self._queued_images.clear()
        self.queue_list.clear()
        self.progress_bar.setValue(0)
        self._refresh_queue_labels()
        self.lbl_ocr_status.setText("Đã xóa toàn bộ hàng đợi ảnh.")

    def _set_busy(self, busy: bool):
        self.btn_start_ocr.setEnabled(not busy)
        self.btn_paste_img.setEnabled(not busy)
        self.btn_add_files.setEnabled(not busy)
        self.btn_remove_img.setEnabled(not busy)
        self.btn_clear_imgs.setEnabled(not busy)
        self.btn_save.setEnabled(not busy)

    def start_ocr(self):
        if not self._queued_images:
            QMessageBox.information(
                self, "Hàng đợi trống", "Vui lòng dán hoặc chọn ít nhất 1 ảnh để quét OCR."
            )
            return

        if self._worker and self._worker.isRunning():
            return

        self._set_busy(True)
        self.progress_bar.setRange(0, len(self._queued_images))
        self.progress_bar.setValue(0)

        self._worker = OCRWorker(list(self._queued_images), parent=self)
        self._worker.progress_signal.connect(self._on_ocr_progress)
        self._worker.finished_signal.connect(self._on_ocr_finished)
        self._worker.error_signal.connect(self._on_ocr_error)
        self._worker.start()

    def _on_ocr_progress(self, current: int, total: int, message: str):
        self.progress_bar.setMaximum(max(1, total))
        self.progress_bar.setValue(current)
        self.lbl_ocr_status.setText(message)

    def _on_ocr_finished(self, merged_text: str):
        self._set_busy(False)
        existing = self.text_preview.toPlainText().strip()
        if existing and merged_text.strip():
            self.text_preview.setPlainText(f"{existing}\n\n{merged_text}")
        elif merged_text.strip():
            self.text_preview.setPlainText(merged_text)
        self.lbl_ocr_status.setText("Quét OCR hoàn tất! Kiểm tra lại văn bản trước khi lưu.")

    def _on_ocr_error(self, err_msg: str):
        self._set_busy(False)
        self.lbl_ocr_status.setText("Xảy ra lỗi khi quét OCR.")
        QMessageBox.critical(self, "Lỗi OCR", err_msg)

    def _on_save_clicked(self):
        if not self.text_preview.toPlainText().strip():
            QMessageBox.warning(self, "Chưa có nội dung", "Khung văn bản đang trống!")
            return
        self.accept()

    def get_text(self) -> str:
        return self.text_preview.toPlainText()

    def closeEvent(self, event):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(2000)
        super().closeEvent(event)