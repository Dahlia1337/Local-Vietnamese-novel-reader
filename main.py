import sys
import os
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QApplication, QInputDialog, QMessageBox, QDialog, QVBoxLayout, QTextEdit, QPushButton, QFileDialog
from ui_main import MainWindowUI, OCRDialog
from library_manager import LibraryManager
from text_parser import TextParser
from audio_worker import AudioWorker

class BulkPasteDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dán văn bản hàng loạt")
        self.resize(600, 400)
        layout = QVBoxLayout(self)
        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("Dán nội dung truyện vào đây... Hệ thống sẽ tự động lọc rác và tách chương.")
        layout.addWidget(self.text_edit)
        self.btn_save = QPushButton("Tách chương và Lưu")
        layout.addWidget(self.btn_save)
        self.btn_save.clicked.connect(self.accept)

class NovelReaderApp(MainWindowUI):
    def __init__(self):
        super().__init__()
        self.setup_ui()
        self.lib_mgr = LibraryManager()
        self.worker = AudioWorker()

        self.current_book = ""
        self.current_chap_idx = 0
        self.sentences = []

        self.init_events()
        self.load_books()

    def init_events(self):
        # Sidebar Events
        self.btn_new_book.clicked.connect(self.on_create_book)
        self.btn_import_txt.clicked.connect(self.on_import_txt)
        self.btn_bulk_paste.clicked.connect(self.on_bulk_paste)
        self.btn_ocr_scan.clicked.connect(lambda: self.on_ocr_scan(auto_paste=False))
        self.book_list.itemClicked.connect(self.on_book_selected)
        self.chapter_list.itemClicked.connect(self.on_chapter_selected)

        # Global Ctrl+V shortcut để mở nhanh OCRDialog nếu Clipboard đang có ảnh
        self.shortcut_ocr_paste = QShortcut(QKeySequence("Ctrl+V"), self)
        self.shortcut_ocr_paste.activated.connect(self.on_global_paste_ocr)

        # Controls Events
        self.btn_play.clicked.connect(self.toggle_play)
        self.btn_prev_sent.clicked.connect(self.prev_sentence)
        self.btn_next_sent.clicked.connect(self.next_sentence)
        self.btn_prev_chap.clicked.connect(self.prev_chapter)
        self.btn_next_chap.clicked.connect(self.next_chapter)
        self.sentence_list.itemDoubleClicked.connect(self.on_sentence_double_clicked)
        self.slider_speed.valueChanged.connect(self.on_speed_changed)

        # Worker Signals
        self.worker.sentence_changed.connect(self.highlight_sentence)
        self.worker.playback_state_changed.connect(self.update_play_button_text)
        self.worker.error_occurred.connect(self.show_error)

    def load_books(self):
        self.book_list.clear()
        books = self.lib_mgr.get_books()
        self.book_list.addItems(books)

    def on_create_book(self):
        name, ok = QInputDialog.getText(self, "Tạo bộ truyện", "Nhập tên bộ truyện:")
        if ok and name.strip():
            safe_name = self.lib_mgr.create_book(name.strip())
            self.load_books()
            items = self.book_list.findItems(safe_name, Qt.MatchFlag.MatchExactly)
            if items:
                self.book_list.setCurrentItem(items[0])
                self.on_book_selected(items[0])

    def on_book_selected(self, item):
        self.current_book = item.text()
        self.load_chapters()

    def load_chapters(self):
        self.chapter_list.clear()
        chapters = self.lib_mgr.get_chapters(self.current_book)
        self.chapter_list.addItems(chapters)
        
        progress = self.lib_mgr.load_progress(self.current_book)
        chap_idx = progress.get("current_chapter", 0)
        if 0 <= chap_idx < len(chapters):
            self.chapter_list.setCurrentRow(chap_idx)
            self.load_chapter_content(chap_idx)

    def on_chapter_selected(self, item):
        idx = self.chapter_list.row(item)
        self.load_chapter_content(idx)

    def load_chapter_content(self, chap_idx: int):
        self.worker.stop()
        self.current_chap_idx = chap_idx
        chapters = self.lib_mgr.get_chapters(self.current_book)
        if not chapters or chap_idx >= len(chapters):
            return

        file_name = chapters[chap_idx]
        file_path = os.path.join(self.lib_mgr.base_dir, self.current_book, file_name)
        
        with open(file_path, "r", encoding="utf-8") as f:
            raw_text = f.read()

        self.lbl_chapter_title.setText(f"{self.current_book} - {file_name.replace('.txt', '')}")
        self.sentences = TextParser.split_sentences(raw_text)
        
        self.sentence_list.clear()
        for idx, s in enumerate(self.sentences):
            self.sentence_list.addItem(f"[{idx+1}] {s}")

    def on_import_txt(self):
        if not self.current_book:
            QMessageBox.warning(self, "Cảnh báo", "Vui lòng chọn hoặc tạo bộ truyện trước!")
            return
        file_path, _ = QFileDialog.getOpenFileName(self, "Chọn file .txt", "", "Text Files (*.txt)")
        if file_path:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            self._process_and_save_text(content)

    def on_bulk_paste(self):
        if not self.current_book:
            QMessageBox.warning(self, "Cảnh báo", "Vui lòng chọn hoặc tạo bộ truyện trước!")
            return
        dlg = BulkPasteDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            content = dlg.text_edit.toPlainText()
            if content.strip():
                self._process_and_save_text(content)

    def on_global_paste_ocr(self):
        clipboard = QApplication.clipboard()
        mime = clipboard.mimeData()
        if mime and mime.hasImage():
            self.on_ocr_scan(auto_paste=True)

    def on_ocr_scan(self, auto_paste: bool = False):
        if not self.current_book:
            QMessageBox.warning(self, "Cảnh báo", "Vui lòng chọn hoặc tạo bộ truyện trước!")
            return
        dlg = OCRDialog(self)
        if auto_paste:
            dlg.paste_from_clipboard()
        if dlg.exec() == QDialog.DialogCode.Accepted:
            content = dlg.get_text()
            if content.strip():
                self._process_and_save_text(content)

    def _process_and_save_text(self, text: str):
        cleaned = TextParser.clean_text(text)
        split_chaps = TextParser.split_chapters(cleaned)
        
        existing_chaps = self.lib_mgr.get_chapters(self.current_book)
        start_idx = len(existing_chaps)

        for i, (title, content) in enumerate(split_chaps):
            chap_num = start_idx + i + 1
            full_content = f"{title}\n\n{content}"
            self.lib_mgr.save_chapter(self.current_book, chap_num, full_content)

        self.load_chapters()

    def get_tts_config(self):
        engine = self.combo_engine.currentText()
        preset = self.combo_voice.currentText()
        
        voice = "vi-VN-NamMinhNeural"
        pitch = "+0Hz"
        rate = "+0%"

        if preset == "Nữ chuẩn (HoaiMy)":
            voice = "vi-VN-HoaiMyNeural"
        elif preset == "Nam trầm (Pitch -6Hz)":
            voice = "vi-VN-NamMinhNeural"
            pitch = "-6Hz"
        elif preset == "Nữ trẻ (Pitch +8Hz)":
            voice = "vi-VN-HoaiMyNeural"
            pitch = "+8Hz"

        speed = self.slider_speed.value() / 100.0
        return engine, voice, pitch, rate, speed

    def toggle_play(self):
        if self.worker.isRunning():
            if self.worker.is_paused:
                self.worker.resume()
            else:
                self.worker.pause()
        else:
            if not self.sentences:
                return
            start_row = self.sentence_list.currentRow()
            if start_row < 0:
                start_row = 0
            
            engine, voice, pitch, rate, speed = self.get_tts_config()
            self.worker.set_data(
                sentences=self.sentences,
                start_index=start_row,
                engine=engine,
                voice=voice,
                pitch=pitch,
                rate=rate,
                speed=speed
            )
            self.worker.start()

    def highlight_sentence(self, idx: int):
        if 0 <= idx < self.sentence_list.count():
            self.sentence_list.setCurrentRow(idx)
            # Save progress
            progress = {
                "current_chapter": self.current_chap_idx,
                "current_sentence": idx,
            }
            self.lib_mgr.save_progress(self.current_book, progress)

    def on_sentence_double_clicked(self, item):
        row = self.sentence_list.row(item)
        self.worker.stop()
        self.toggle_play()

    def prev_sentence(self):
        row = max(0, self.sentence_list.currentRow() - 1)
        self.sentence_list.setCurrentRow(row)
        if self.worker.isRunning():
            self.worker.stop()
            self.toggle_play()

    def next_sentence(self):
        row = min(self.sentence_list.count() - 1, self.sentence_list.currentRow() + 1)
        self.sentence_list.setCurrentRow(row)
        if self.worker.isRunning():
            self.worker.stop()
            self.toggle_play()

    def prev_chapter(self):
        if self.current_chap_idx > 0:
            self.chapter_list.setCurrentRow(self.current_chap_idx - 1)
            self.load_chapter_content(self.current_chap_idx - 1)

    def next_chapter(self):
        if self.current_chap_idx < self.chapter_list.count() - 1:
            self.chapter_list.setCurrentRow(self.current_chap_idx + 1)
            self.load_chapter_content(self.current_chap_idx + 1)

    def on_speed_changed(self, val: int):
        self.lbl_speed_val.setText(f"{val/100:.2f}x")

    def update_play_button_text(self, is_playing: bool):
        self.btn_play.setText("Tạm dừng" if is_playing else "Phát")

    def show_error(self, err_msg: str):
        QMessageBox.critical(self, "Lỗi Phát Audio", err_msg)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = NovelReaderApp()
    window.show()
    sys.exit(app.exec())