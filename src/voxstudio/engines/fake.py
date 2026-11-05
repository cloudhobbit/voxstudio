"""A stand-in engine: a 0.2 s tone per word. Used by the tests and by `voxstudio serve --engine fake`,
so the app can be developed and demonstrated without downloading a model."""
import re

import numpy as np

from ..catalogue import VOICES
from .base import Parts, VoiceInfo, Words, bracket_word


class FakeEngine:
    name = "fake"
    sample_rate = 24000

    def __init__(self):
        self.said: list[str] = []
        self.languages: list[str] = []

    def voices(self) -> list[VoiceInfo]:
        return [VoiceInfo(id=v, name=info["name"], language=info["language"], accent=info["accent"],
                          gender=info["gender"], grade=info["grade"], character=info["character"], uses=info["uses"])
                for v, info in VOICES.items()]

    def warm(self) -> None:
        self.languages = ["en-US", "en-GB"]

    def speak(self, text: str, parts: Parts, speed: float) -> np.ndarray:
        return self.speak_timed(text, parts, speed)[0]

    def speak_timed(self, text: str, parts: Parts, speed: float) -> tuple[np.ndarray, Words]:
        pieces = list(self.speak_stream(text, parts, speed))
        return np.concatenate([a for a, _ in pieces]), [w for _, ws in pieces for w in ws]

    def speak_stream(self, text: str, parts: Parts, speed: float):
        """One piece per sentence, like a real engine."""
        self.said.append(text)
        # the blend's weights shift the tone, so different mixes give different audio (and cache keys)
        pitch = 220 + 40 * sum(i * w for i, (_, w) in enumerate(parts))
        step, done = 0.2 / speed, 0
        for sentence in re.split(r"(?<=[.!?])\s+", text.strip()) or [""]:
            words = sentence.split() or [""]
            t = np.arange(int(step * self.sample_rate * len(words))) / self.sample_rate
            audio = (0.3 * np.sin(2 * np.pi * pitch * t)).astype(np.float32)
            yield audio, [(w.strip(".,!?;:\"'()"), (done + i) * step, (done + i) * step + step * 0.9) for i, w in enumerate(words)]
            done += len(words)

    def emphasise(self, stretch: str, parts: Parts) -> str:
        return " ".join(bracket_word(w) for w in stretch.split())
