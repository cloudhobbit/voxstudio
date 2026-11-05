"""What every engine provides. Voices are addressed by id; blends are a list of (id, weight) summing to 1."""
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Protocol

import numpy as np

Parts = list[tuple[str, float]]
_WORD = re.compile(r"^(\W*)(.*?)(\W*)$", re.S)


def bracket_word(word: str, mark: str = "+2") -> str:
    """[word](+2), with any punctuation left outside the brackets: "go." -> "[go](+2)."."""
    lead, core, tail = _WORD.match(word).groups()
    return f"{lead}[{core}]({mark}){tail}" if core else word

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

    def speak_stream(self, text: str, parts: Parts, speed: float) -> Iterator[tuple[np.ndarray, Words]]:
        """The same audio in pieces (a sentence or so each) as soon as each exists. Word times count from the
        start of the whole text, so joining the pieces gives exactly what speak_timed returns."""

    def emphasise(self, stretch: str, parts: Parts) -> str:
        """How this engine writes emphasis on a word or phrase; return it unchanged if it has no way to."""
