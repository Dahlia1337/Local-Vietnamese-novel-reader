import os
import asyncio
import pygame
from PyQt6.QtCore import QThread, pyqtSignal
from tts_engine import TTSEngine

TEMP_DIR = "temp_audio"

class AudioWorker(QThread):
    sentence_changed = pyqtSignal(int)
    playback_state_changed = pyqtSignal(bool) # True: Playing, False: Paused/Stopped
    error_occurred = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tts = TTSEngine()
        self.sentences = []
        self.current_index = 0
        self.is_running = False
        self.is_paused = False
        self.loop = None
        
        # Audio Params
        self.engine = "Edge-TTS (Online)"
        self.voice = "vi-VN-NamMinhNeural"
        self.pitch = "+0Hz"
        self.rate = "+0%"
        self.speed = 1.0

        os.makedirs(TEMP_DIR, exist_ok=True)
        pygame.mixer.init()

    def set_data(self, sentences: list, start_index: int, engine: str, voice: str, pitch: str, rate: str, speed: float):
        self.sentences = sentences
        self.current_index = start_index
        self.engine = engine
        self.voice = voice
        self.pitch = pitch
        self.rate = rate
        self.speed = speed

    def run(self):
        self.is_running = True
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._playback_loop())

    def stop(self):
        self.is_running = False
        self.is_paused = False
        pygame.mixer.music.stop()
        try:
            pygame.mixer.music.unload()
        except AttributeError:
            pass
        self.playback_state_changed.emit(False)

    def pause(self):
        if self.is_running and not self.is_paused:
            self.is_paused = True
            pygame.mixer.music.pause()
            self.playback_state_changed.emit(False)

    def resume(self):
        if self.is_running and self.is_paused:
            self.is_paused = False
            pygame.mixer.music.unpause()
            self.playback_state_changed.emit(True)

    def _get_audio_path(self, idx: int) -> str:
        ext = "wav" if self.engine == "Piper TTS (Offline)" else "mp3"
        return os.path.join(TEMP_DIR, f"seg_{idx}.{ext}")

    async def _prefetch(self, idx: int):
        """Tải trước file audio cho các câu tiếp theo."""
        if idx >= len(self.sentences):
            return
        path = self._get_audio_path(idx)
        if not os.path.exists(path):
            try:
                await self.tts.synthesize(
                    text=self.sentences[idx],
                    output_path=path,
                    engine=self.engine,
                    voice=self.voice,
                    rate=self.rate,
                    pitch=self.pitch
                )
            except Exception as e:
                print(f"[Prefetch Error] Câu {idx}: {e}")

    def _cleanup_old_files(self, keep_idx: int):
        """Xóa bớt file tạm đã phát xong để tiết kiệm bộ nhớ đĩa."""
        for f in os.listdir(TEMP_DIR):
            file_path = os.path.join(TEMP_DIR, f)
            try:
                # Giữ lại câu hiện tại và 2 câu prefetch kế tiếp
                prefix, ext = os.path.splitext(f)
                num = int(prefix.split("_")[1])
                if num < keep_idx - 1:
                    os.remove(file_path)
            except Exception:
                pass

    async def _playback_loop(self):
        while self.is_running and self.current_index < len(self.sentences):
            if self.is_paused:
                await asyncio.sleep(0.1)
                continue

            idx = self.current_index
            curr_path = self._get_audio_path(idx)

            # Synthesize câu hiện tại nếu chưa prefetch kịp
            if not os.path.exists(curr_path):
                try:
                    await self.tts.synthesize(
                        text=self.sentences[idx],
                        output_path=curr_path,
                        engine=self.engine,
                        voice=self.voice,
                        rate=self.rate,
                        pitch=self.pitch
                    )
                except Exception as e:
                    self.error_occurred.emit(f"Lỗi TTS câu {idx}: {str(e)}")
                    break

            # Bật Prefetch ngầm cho 2 câu tiếp theo
            asyncio.create_task(self._prefetch(idx + 1))
            asyncio.create_task(self._prefetch(idx + 2))

            # Phát Audio
            try:
                pygame.mixer.music.load(curr_path)
                pygame.mixer.music.play()
                self.sentence_changed.emit(idx)
                self.playback_state_changed.emit(True)
            except Exception as e:
                self.error_occurred.emit(f"Lỗi Audio Player: {str(e)}")
                break

            # Chờ phát xong câu
            while pygame.mixer.music.get_busy() or self.is_paused:
                if not self.is_running:
                    break
                await asyncio.sleep(0.05)

            # Unload file audio để tránh dính lock file trên Windows
            try:
                pygame.mixer.music.unload()
            except AttributeError:
                pass

            self._cleanup_old_files(keep_idx=idx)

            if self.is_running and not self.is_paused:
                self.current_index += 1

        self.is_running = False
        self.playback_state_changed.emit(False)