import re
from typing import List

class TextParser:
    @staticmethod
    def clean_text(text: str) -> str:
        """Loại bỏ các chuỗi văn bản rác phổ biến trên các trang novel Việt Nam."""
        junk_patterns = [
            r"https?://\S+",                         # URLs
            r"www\.\S+",                             # Links
            r"Đọc tại\s+[\w\.]+",                    # Quảng cáo nguồn
            r"Báo lỗi\s*-\s*Góp ý",                  # Nút báo lỗi
            r"Chúc bạn có những giây phút vui vẻ.*",  # Lời chúc rác
            r"Nguồn:\s*.*",                           # Ghi chú nguồn
            r"Truyện được cập nhật nhanh nhất tại.*", # Text SEO
            r"\[.*?\]",                              # Quảng cáo trong ngoặc vuông
        ]
        
        cleaned = text
        for pattern in junk_patterns:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
            
        # Xóa khoảng trắng thừa và dòng trống liên tiếp
        lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
        return "\n".join(lines)

    @staticmethod
    def split_chapters(text: str) -> List[tuple[str, str]]:
        """
        Tự động tách khối văn bản lớn thành các chương dựa vào Regex.
        Returns: List[(Tiêu đề chương, Nội dung chương)]
        """
        pattern = r"(^(?:Chương|Chapter|Tập)\s+\d+[:\s\.-].*)"
        parts = re.split(pattern, text, flags=re.MULTILINE | re.IGNORECASE)
        
        chapters = []
        if len(parts) <= 1:
            # Nếu không tìm thấy pattern, xem toàn bộ là 1 chương
            chapters.append(("Chương 1", text.strip()))
            return chapters

        # Nếu phần đầu trước khi match có chữ
        if parts[0].strip():
            chapters.append(("Mở đầu", parts[0].strip()))

        for i in range(1, len(parts), 2):
            title = parts[i].strip()
            content = parts[i+1].strip() if i+1 < len(parts) else ""
            chapters.append((title, content))

        return chapters

    @staticmethod
    def split_sentences(text: str) -> List[str]:
        """Tách nội dung chương thành danh sách câu để phát TTS."""
        cleaned = TextParser.clean_text(text)
        # Tách theo dấu chấm, chấm hỏi, chấm cảm hoặc xuống dòng
        raw_sentences = re.split(r'(?<=[.!?\n])\s+', cleaned)
        sentences = []
        for s in raw_sentences:
            s_clean = s.strip()
            if len(s_clean) > 0:
                sentences.append(s_clean)
        return sentences