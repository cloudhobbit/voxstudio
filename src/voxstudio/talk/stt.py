"""Speech to text. `transcribe(audio)` takes mono float32 at 16 kHz and returns the words."""
import platform
from typing import Protocol

import numpy as np


class STT(Protocol):
    name: str

    def warm(self) -> None: ...

    def transcribe(self, audio: np.ndarray) -> str: ...


class FakeSTT:
    """Returns scripted lines in order (then "words words" by length), so tests and demos need no model."""
    name = "fake"

    def __init__(self, lines: list[str] | None = None, delay: float = 0.0):
        self.lines, self.delay, self.heard = list(lines or []), delay, []

    def warm(self) -> None:
        pass

    def transcribe(self, audio: np.ndarray) -> str:
        import time
        time.sleep(self.delay)
        self.heard.append(len(audio))
        if self.lines:
            return self.lines.pop(0)
        return " ".join(["word"] * max(1, round(len(audio) / 16000 / 0.4)))


class MlxWhisperSTT:
    """Whisper on Apple Silicon through MLX."""

    def __init__(self, model: str = "mlx-community/whisper-large-v3-turbo", language: str | None = "en"):
        self.model, self.language, self.name = model, language, f"mlx-whisper:{model.split('/')[-1]}"

    def warm(self) -> None:
        self.transcribe(np.zeros(8000, dtype=np.float32))

    def transcribe(self, audio: np.ndarray) -> str:
        import mlx_whisper
        r = mlx_whisper.transcribe(audio.astype(np.float32), path_or_hf_repo=self.model, language=self.language,
                                   condition_on_previous_text=False, verbose=None)
        return r["text"].strip()


class FasterWhisperSTT:
    """Whisper through CTranslate2: runs on any CPU."""

    def __init__(self, model: str = "base.en", language: str | None = "en"):
        self.model, self.language, self.name, self._loaded = model, language, f"faster-whisper:{model}", None

    def _model(self):
        if self._loaded is None:
            from faster_whisper import WhisperModel
            self._loaded = WhisperModel(self.model, device="cpu", compute_type="int8")
        return self._loaded

    def warm(self) -> None:
        self._model()

    def transcribe(self, audio: np.ndarray) -> str:
        segments, _ = self._model().transcribe(audio.astype(np.float32), language=self.language, beam_size=1,
                                               condition_on_previous_text=False, vad_filter=False)
        return " ".join(s.text.strip() for s in segments).strip()


def load_stt(kind: str = "auto", model: str | None = None) -> STT:
    import importlib.util as u
    if kind == "fake":
        return FakeSTT()
    apple = platform.system() == "Darwin" and platform.machine() == "arm64"
    if kind == "mlx" or (kind == "auto" and apple and u.find_spec("mlx_whisper")):
        return MlxWhisperSTT(model) if model else MlxWhisperSTT()
    if kind in ("faster-whisper", "auto") and u.find_spec("faster_whisper"):
        return FasterWhisperSTT(model) if model else FasterWhisperSTT()
    raise RuntimeError("No speech-to-text is installed. Install the extra: pip install 'voxstudio[talk]'")
