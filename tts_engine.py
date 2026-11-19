import os
import asyncio
import edge_tts
from typing import Optional, Any

try:
    from piper import PiperVoice
    PIPER_AVAILABLE = True
except ImportError:
    PIPER_AVAILABLE = False

class TTSEngine:
    def __init__(self, piper_model_dir: str = "models/piper"):
        self.piper_model_dir = piper_model_dir
        self.piper_voice: Optional[Any] = None
        self.loaded_piper_model: Optional[str] = None
        
        os.makedirs(self.piper_model_dir, exist_ok=True)
        self._init_piper_if_possible()

    def _init_piper_if_possible(self):
        """Kiểm tra và nạp Piper TTS model nếu tồn tại."""
        if not PIPER_AVAILABLE:
            return

        onnx_files = [f for f in os.listdir(self.piper_model_dir) if f.endswith(".onnx")]
        if onnx_files:
            model_path = os.path.join(self.piper_model_dir, onnx_files[0])
            config_path = model_path + ".json"
            if os.path.exists(config_path):
                try:
                    self.piper_voice = PiperVoice.load(model_path, config_path)
                    self.loaded_piper_model = onnx_files[0]
                except Exception as e:
                    print(f"[Piper Error] Không thể nạp model: {e}")

    async def synthesize_edge(self, text: str, output_path: str, voice: str, rate: str = "+0%", pitch: str = "+0Hz"):
        """Tổng hợp giọng nói bằng Edge-TTS (Async Online)."""
        communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
        await communicate.save(output_path)

    def synthesize_piper(self, text: str, output_path: str):
        """Tổng hợp giọng nói bằng Piper TTS (Sync Offline)."""
        if not PIPER_AVAILABLE or not self.piper_voice:
            raise RuntimeError("Piper TTS chưa được cài đặt hoặc thiếu file .onnx/.onnx.json trong models/piper/")

        import wave
        with wave.open(output_path, "wb") as wav_file:
            self.piper_voice.synthesize(text, wav_file)

    async def synthesize(self, text: str, output_path: str, engine: str, voice: str, rate: str, pitch: str):
        """Interface chung xử lý linh hoạt 2 engine."""
        if engine == "Piper TTS (Offline)":
            # Chạy Piper đồng bộ trong Executor để không block loop
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self.synthesize_piper, text, output_path)
        else:
            # Mặc định Edge-TTS
            await self.synthesize_edge(text, output_path, voice=voice, rate=rate, pitch=pitch)