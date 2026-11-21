import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import List, Optional
import numpy as np
from PIL import Image, ImageOps
from PyQt6.QtCore import QThread, pyqtSignal


@dataclass
class TextBox:
    """Biểu diễn một khối chữ nhận diện được từ RapidOCR + VietOCR."""
    text: str
    x_left: float
    x_right: float
    y_top: float
    y_bottom: float

    @property
    def height(self) -> float:
        return max(1.0, self.y_bottom - self.y_top)

    @property
    def width(self) -> float:
        return max(1.0, self.x_right - self.x_left)


@dataclass
class TextLine:
    """Một dòng chữ sau khi gom các TextBox cùng hàng ngang."""
    text: str
    x_left: float
    y_top: float
    y_bottom: float
    avg_height: float


class OCREngine:
    """
    Engine nhận diện chữ tiếng Việt chạy Local 100% trên CPU:
    - RapidOCR (ONNX Runtime) phát hiện vùng dòng chữ (Text Detection).
    - VietOCR (vgg_seq2seq) nhận diện chữ tiếng Việt chuẩn dấu.
    - Tích hợp tiền xử lý Dark Mode + thuật toán sắp xếp & ghép đoạn văn thông minh.
    """

    # Ký tự bắt đầu lời thoại hoặc gạch đầu dòng đoạn mới
    DIALOGUE_PREFIXES = ("「", "『", '"', "“", "‘", "-", "—", "–", "•", "*")
    # Dấu kết thúc câu / kết đoạn
    SENTENCE_ENDINGS = (".", "!", "?", "…", ":", "”", '"', "」", "』")

    # Các mẫu rác trình duyệt / giao diện web đọc truyện phổ biến
    JUNK_PATTERNS = [
        re.compile(r"^https?://\S+$", re.IGNORECASE),
        re.compile(r"^www\.\S+$", re.IGNORECASE),
        re.compile(r"^[\W_]+$"),  # Chỉ gồm ký tự đặc biệt/icon rời rạc
        re.compile(
            r"^(Trang chủ|Mục lục|Chương trước|Chương sau|Báo lỗi|Cài đặt|Cỡ chữ|Đọc tiếp|Đăng nhập|Tìm kiếm)$",
            re.IGNORECASE,
        ),
        re.compile(r"^\d{1,2}:\d{2}(\s*(AM|PM))?$", re.IGNORECASE),
        re.compile(r"^\d{1,3}%$"),
    ]

    def __init__(self) -> None:
        self._detector = None
        self._recognizer = None

    def _ensure_models(self) -> None:
        """Khởi tạo lazy RapidOCR (Detection) và VietOCR (Recognition) trên CPU."""
        if self._detector is None:
            from rapidocr_onnxruntime import RapidOCR

            self._detector = RapidOCR(use_det=True, use_cls=False, use_rec=False)

        if self._recognizer is None:
            from vietocr.tool.config import Cfg
            from vietocr.tool.predictor import Predictor

            cfg = Cfg.load_config_from_name("vgg_seq2seq")
            cfg["device"] = "cpu"
            cfg["predictor"]["beamsearch"] = False
            self._recognizer = Predictor(cfg)

    @staticmethod
    def _preprocess_image(image: Image.Image) -> Image.Image:
        """
        Chuẩn hóa ảnh trước khi OCR:
        - Nếu ảnh là Dark Mode (nền tối, chữ sáng), đảo màu thành nền trắng chữ đen.
        """
        rgb_img = image.convert("RGB")
        gray = rgb_img.convert("L")
        mean_brightness = float(np.mean(np.asarray(gray)))
        if mean_brightness < 128.0:
            return ImageOps.invert(rgb_img)
        return rgb_img

    @classmethod
    def _is_noise_text(cls, text: str) -> bool:
        """Lọc nhiễu chuỗi rác trình duyệt hoặc ký tự vô nghĩa."""
        cleaned = text.strip()
        if not cleaned:
            return True
        for pattern in cls.JUNK_PATTERNS:
            if pattern.match(cleaned):
                return True
        return False

    @staticmethod
    def _crop_box(image: Image.Image, x_left: float, y_top: float, x_right: float, y_bottom: float, pad: int = 3) -> Image.Image:
        """Cắt vùng chữ có thêm padding nhỏ để không bị mất dấu ở mép box."""
        w, h = image.size
        left = max(0, int(x_left) - pad)
        top = max(0, int(y_top) - pad)
        right = min(w, int(x_right) + pad)
        bottom = min(h, int(y_bottom) + pad)
        return image.crop((left, top, right, bottom))

    @staticmethod
    def _group_into_lines(boxes: List[TextBox]) -> List[TextLine]:
        """
        1. Sắp xếp đúng thứ tự đọc:
           - Sắp xếp theo y_top từ trên xuống dưới.
           - Gom các box có độ lệch y < 0.5 * chiều cao chữ vào cùng một hàng.
           - Sắp xếp các box trong cùng hàng theo x_left từ trái sang phải.
        """
        if not boxes:
            return []

        sorted_boxes = sorted(boxes, key=lambda b: (b.y_top, b.x_left))
        rows: List[List[TextBox]] = []

        for box in sorted_boxes:
            if not rows:
                rows.append([box])
                continue

            current_row = rows[-1]
            row_y_top = sum(b.y_top for b in current_row) / len(current_row)
            row_avg_h = sum(b.height for b in current_row) / len(current_row)

            if abs(box.y_top - row_y_top) < 0.5 * row_avg_h:
                current_row.append(box)
            else:
                rows.append([box])

        lines: List[TextLine] = []
        for row in rows:
            row.sort(key=lambda b: b.x_left)
            merged_text = " ".join(b.text for b in row)
            merged_text = re.sub(r"\s+", " ", merged_text).strip()
            if not merged_text:
                continue

            lines.append(
                TextLine(
                    text=merged_text,
                    x_left=min(b.x_left for b in row),
                    y_top=min(b.y_top for b in row),
                    y_bottom=max(b.y_bottom for b in row),
                    avg_height=sum(b.height for b in row) / len(row),
                )
            )
        return lines

    @classmethod
    def merge_lines_to_paragraphs(cls, lines: List[TextLine]) -> str:
        """
        2. Tự động nối dòng thành đoạn văn (Paragraph Merging):
           - Nếu delta_y < 1.5 * line_height và dòng trước không kết thúc bằng dấu kết câu/ngắt đoạn,
             nối liền bằng dấu cách (" ").
           - Nếu delta_y lớn, hoặc dòng mới bắt đầu bằng ký tự hội thoại / thụt đầu dòng,
             ngắt xuống dòng mới ("\\n").
        """
        if not lines:
            return ""
        if len(lines) == 1:
            return lines[0].text

        heights = sorted(line.avg_height for line in lines)
        line_height = heights[len(heights) // 2]

        x_lefts = sorted(line.x_left for line in lines)
        base_x_left = x_lefts[max(0, int(len(x_lefts) * 0.2))]
        indent_threshold = max(12.0, 0.8 * line_height)

        paragraphs: List[str] = [lines[0].text]

        for i in range(1, len(lines)):
            prev_line = lines[i - 1]
            curr_line = lines[i]

            delta_y = curr_line.y_top - prev_line.y_top
            is_normal_spacing = delta_y < 1.5 * line_height

            prev_text = paragraphs[-1].rstrip()
            curr_text = curr_line.text.lstrip()

            ends_sentence = prev_text.endswith(cls.SENTENCE_ENDINGS)
            starts_dialogue = curr_text.startswith(cls.DIALOGUE_PREFIXES)
            is_indented = (curr_line.x_left - base_x_left) > indent_threshold
            is_chapter_heading = bool(
                re.match(r"^(Chương|Chapter|Tập)\s+\d+", curr_text, re.IGNORECASE)
            )

            if (
                is_normal_spacing
                and not ends_sentence
                and not starts_dialogue
                and not is_indented
                and not is_chapter_heading
            ):
                paragraphs[-1] = f"{prev_text} {curr_text}"
            else:
                paragraphs.append(curr_text)

        return "\n".join(paragraphs)

    def process_image(self, image: Image.Image) -> str:
        """Nhận diện OCR một ảnh PIL và trả về văn bản đã ghép đoạn hoàn chỉnh."""
        self._ensure_models()
        processed_img = self._preprocess_image(image)
        img_np = np.array(processed_img)

        det_boxes, _ = self._detector(img_np, use_det=True, use_cls=False, use_rec=False)
        if not det_boxes:
            return ""

        valid_coords = []
        crops: List[Image.Image] = []
        for poly in det_boxes:
            xs = [float(pt[0]) for pt in poly]
            ys = [float(pt[1]) for pt in poly]
            x_left, x_right = min(xs), max(xs)
            y_top, y_bottom = min(ys), max(ys)

            # Lọc box quá nhỏ (icon, dấu chấm nhiễu) trước khi đưa vào VietOCR
            if (y_bottom - y_top) < 8.0 or (x_right - x_left) < 8.0:
                continue

            valid_coords.append((x_left, x_right, y_top, y_bottom))
            crops.append(self._crop_box(processed_img, x_left, y_top, x_right, y_bottom))

        if not crops:
            return ""

        rec_texts = self._recognizer.predict_batch(crops)

        boxes: List[TextBox] = []
        for (x_left, x_right, y_top, y_bottom), text in zip(valid_coords, rec_texts):
            cleaned = str(text).strip()
            if self._is_noise_text(cleaned):
                continue
            boxes.append(
                TextBox(
                    text=cleaned,
                    x_left=x_left,
                    x_right=x_right,
                    y_top=y_top,
                    y_bottom=y_bottom,
                )
            )

        lines = self._group_into_lines(boxes)
        return self.merge_lines_to_paragraphs(lines)


class OCRWorker(QThread):
    """
    Luồng nền thực hiện OCR tuần tự trên danh sách ảnh trong hàng đợi,
    đảm bảo giao diện PyQt6 không bị treo.
    """

    progress_signal = pyqtSignal(int, int, str)  # (current_idx, total, status_message)
    finished_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)

    def __init__(self, images: Optional[List[Image.Image]] = None, parent=None) -> None:
        super().__init__(parent)
        self.images: List[Image.Image] = images or []
        self._engine = OCREngine()
        self._is_cancelled = False

    def set_images(self, images: List[Image.Image]) -> None:
        self.images = images
        self._is_cancelled = False

    def cancel(self) -> None:
        self._is_cancelled = True

    @staticmethod
    def _normalize_for_match(text: str) -> str:
        """Chuẩn hóa nhẹ chuỗi để so khớp trùng lặp giữa 2 ảnh chụp chồng lấn."""
        return re.sub(r"\s+", " ", text).strip().lower()

    @classmethod
    def _is_similar(cls, a: str, b: str, threshold: float = 0.85) -> bool:
        na = cls._normalize_for_match(a)
        nb = cls._normalize_for_match(b)
        if not na or not nb:
            return False
        if na == nb:
            return True
        return SequenceMatcher(None, na, nb).ratio() >= threshold

    @classmethod
    def _deduplicate_overlap(cls, prev_text: str, curr_text: str) -> tuple[str, str]:
        """
        Loại bỏ các dòng trùng lặp ở phần giao giữa cuối ảnh trước và đầu ảnh sau
        khi người dùng chụp cuộn trang có chồng lấn.
        Trả về (prev_text_đã_cập_nhật, curr_text_sau_khi_bỏ_phần_trùng).
        """
        prev_lines = [line.strip() for line in prev_text.splitlines() if line.strip()]
        curr_lines = [line.strip() for line in curr_text.splitlines() if line.strip()]
        if not prev_lines or not curr_lines:
            return prev_text, curr_text

        max_overlap = min(8, len(prev_lines), len(curr_lines))
        for k in range(max_overlap, 0, -1):
            exact_prefix_match = all(
                cls._is_similar(prev_lines[-k + i], curr_lines[i])
                for i in range(k - 1)
            )
            if not exact_prefix_match:
                continue

            last_prev = prev_lines[-1]
            last_curr = curr_lines[k - 1]
            if cls._is_similar(last_prev, last_curr):
                return prev_text, "\n".join(curr_lines[k:])

            # Cho phép dòng cuối của phần giao bị cắt dở ở ảnh trước và đầy đủ hơn ở ảnh sau
            n_prev = cls._normalize_for_match(last_prev)
            n_curr = cls._normalize_for_match(last_curr)
            if len(n_prev) >= 10 and len(n_curr) >= len(n_prev):
                if SequenceMatcher(None, n_prev, n_curr[: len(n_prev)]).ratio() >= 0.85:
                    prev_lines[-1] = last_curr
                    return "\n".join(prev_lines), "\n".join(curr_lines[k:])

        # Trường hợp 1 dòng cuối ảnh trước chứa trọn 1 dòng đầu ảnh sau
        n_prev = cls._normalize_for_match(prev_lines[-1])
        n_curr = cls._normalize_for_match(curr_lines[0])
        if len(n_curr) >= 15 and len(n_prev) >= len(n_curr):
            suffix_of_prev = n_prev[-len(n_curr) :]
            if SequenceMatcher(None, suffix_of_prev, n_curr).ratio() >= 0.85:
                return prev_text, "\n".join(curr_lines[1:])

        return prev_text, curr_text

    @classmethod
    def _join_page_texts(cls, page_texts: List[str]) -> str:
        """Ghép văn bản giữa các ảnh liên tiếp, tự động lọc trùng lặp và nối câu cắt ngang."""
        merged: List[str] = []
        for text in page_texts:
            cleaned = text.strip()
            if not cleaned:
                continue
            if not merged:
                merged.append(cleaned)
                continue

            updated_prev, dedup_curr = cls._deduplicate_overlap(merged[-1], cleaned)
            merged[-1] = updated_prev
            dedup_curr = dedup_curr.strip()
            if not dedup_curr:
                continue

            prev = merged[-1].rstrip()
            first_line = dedup_curr.splitlines()[0].lstrip()
            if (
                not prev.endswith(OCREngine.SENTENCE_ENDINGS)
                and not first_line.startswith(OCREngine.DIALOGUE_PREFIXES)
            ):
                merged[-1] = f"{prev} {dedup_curr}"
            else:
                merged.append(dedup_curr)
        return "\n\n".join(merged)

    def run(self) -> None:
        try:
            total = len(self.images)
            if total == 0:
                self.finished_signal.emit("")
                return

            self.progress_signal.emit(0, total, "Đang khởi tạo mô hình RapidOCR + VietOCR (CPU)...")
            page_texts: List[str] = []

            for idx, img in enumerate(self.images):
                if self._is_cancelled:
                    self.progress_signal.emit(idx, total, "Đã hủy tác vụ OCR.")
                    return

                self.progress_signal.emit(
                    idx, total, f"Đang quét ảnh {idx + 1}/{total}..."
                )
                text = self._engine.process_image(img)
                if text:
                    page_texts.append(text)

                self.progress_signal.emit(
                    idx + 1, total, f"Đã xong ảnh {idx + 1}/{total}."
                )

            final_text = self._join_page_texts(page_texts)
            self.finished_signal.emit(final_text)
        except Exception as exc:
            self.error_signal.emit(f"Lỗi khi chạy OCR: {exc}")
