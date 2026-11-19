import os
import json
import shutil
from typing import Dict, List, Any

LIBRARY_DIR = "library_data"

class LibraryManager:
    def __init__(self, base_dir: str = LIBRARY_DIR):
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)

    def get_books(self) -> List[str]:
        """Lấy danh sách các bộ truyện."""
        return [
            d for d in os.listdir(self.base_dir)
            if os.path.isdir(os.path.join(self.base_dir, d))
        ]

    def create_book(self, book_name: str) -> str:
        """Tạo bộ truyện mới."""
        safe_name = "".join(c for c in book_name if c.isalnum() or c in (" ", "_", "-")).strip()
        book_path = os.path.join(self.base_dir, safe_name)
        os.makedirs(book_path, exist_ok=True)
        
        default_progress = {
            "current_chapter": 0,
            "current_sentence": 0,
            "engine": "Edge-TTS",
            "voice": "vi-VN-NamMinhNeural",
            "pitch": "+0Hz",
            "rate": "+0%",
            "playback_speed": 1.0
        }
        self.save_progress(safe_name, default_progress)
        return safe_name

    def delete_book(self, book_name: str):
        """Xóa bộ truyện."""
        book_path = os.path.join(self.base_dir, book_name)
        if os.path.exists(book_path):
            shutil.rmtree(book_path)

    def get_chapters(self, book_name: str) -> List[str]:
        """Lấy danh sách file chương (Chap_xxx.txt) theo thứ tự."""
        book_path = os.path.join(self.base_dir, book_name)
        if not os.path.exists(book_path):
            return []
        
        files = [f for f in os.listdir(book_path) if f.startswith("Chap_") and f.endswith(".txt")]
        
        def extract_num(filename: str) -> int:
            try:
                return int(filename.split("_")[1].split(".")[0])
            except (IndexError, ValueError):
                return 0

        files.sort(key=extract_num)
        return files

    def get_progress_path(self, book_name: str) -> str:
        return os.path.join(self.base_dir, book_name, "progress.json")

    def load_progress(self, book_name: str) -> Dict[str, Any]:
        """Lưu và đọc progress.json."""
        path = self.get_progress_path(book_name)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "current_chapter": 0,
            "current_sentence": 0,
            "engine": "Edge-TTS",
            "voice": "vi-VN-NamMinhNeural",
            "pitch": "+0Hz",
            "rate": "+0%",
            "playback_speed": 1.0
        }

    def save_progress(self, book_name: str, data: Dict[str, Any]):
        """Cập nhật tiến trình đọc."""
        path = self.get_progress_path(book_name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def save_chapter(self, book_name: str, chap_index: int, content: str):
        """Lưu file chương lẻ."""
        book_path = os.path.join(self.base_dir, book_name)
        file_path = os.path.join(book_path, f"Chap_{chap_index:03d}.txt")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)