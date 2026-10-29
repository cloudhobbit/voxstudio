"""What every engine provides. Voices are addressed by id; blends are a list of (id, weight) summing to 1."""
from dataclasses import dataclass, field
from typing import Protocol

import numpy as np

Parts = list[tuple[str, float]]
Words = list[tuple[str, float, float]]  # (word, start, end) in seconds


@dataclass
class VoiceInfo:
    id: str
    name: str
    language: str          # BCP-47-ish: en-US, en-GB, hi-IN ...
    accent: str            # short label shown in the UI: US, UK, Hindi
    gender: str            # F, M
    grade: str             # A+ .. F
    character: str = ""    # plain words: "warm, clear, friendly"
    uses: list[str] = field(default_factory=list)


class Engine(Protocol):
    name: str
    sample_rate: int

    def voices(self) -> list[VoiceInfo]: ...

    def warm(self) -> None:
        """Load whatever makes the first request slow. Runs in the worker thread."""

    def speak(self, text: str, parts: Parts, speed: float) -> np.ndarray: ...

    def speak_timed(self, text: str, parts: Parts, speed: float) -> tuple[np.ndarray, Words]:
        """Audio plus word timings. Engines without timings return an empty list."""
