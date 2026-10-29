"""Kokoro-82M (Apache-2.0): small, runs on a CPU, 50+ voices in several languages, with word timestamps."""
from collections import OrderedDict

import numpy as np

from ..catalogue import VOICES
from .base import Parts, VoiceInfo, Words

REPO = "hexgrad/Kokoro-82M"
LANG_CODES = {"a": "en-US", "b": "en-GB", "h": "hi-IN", "e": "es", "f": "fr-FR", "i": "it", "j": "ja", "p": "pt-BR", "z": "zh"}


class KokoroEngine:
    name = "kokoro"
    sample_rate = 24000

    def __init__(self, warm_voices=("af_heart", "bf_emma")):
        self.pipelines: dict[str, object] = {}
        self.blends: OrderedDict = OrderedDict()
        self.warm_voices = warm_voices

    @property
    def languages(self) -> list[str]:
        return sorted(LANG_CODES.get(c, c) for c in self.pipelines)

    def voices(self) -> list[VoiceInfo]:
        return [VoiceInfo(id=v, name=info["name"], language=info["language"], accent=info["accent"],
                          gender=info["gender"], grade=info["grade"], character=info["character"], uses=info["uses"])
                for v, info in VOICES.items()]

    def warm(self) -> None:
        for voice in self.warm_voices:
            self.speak("Ready.", [(voice, 1.0)], 1.0)

    def _pipeline(self, lang: str):
        if lang not in self.pipelines:
            from kokoro import KPipeline  # imported late: loading torch takes seconds
            self.pipelines[lang] = KPipeline(lang_code=lang, repo_id=REPO)
        return self.pipelines[lang]

    def _voice(self, parts: Parts):
        lang = parts[0][0][0]  # first letter of a Kokoro voice is its language: a=US, b=UK, h=Hindi...
        pipe = self._pipeline(lang)
        if len(parts) == 1:
            return pipe, parts[0][0]
        key = tuple(parts)
        if key not in self.blends:
            self.blends[key] = sum(w * pipe.load_voice(name) for name, w in parts)
            while len(self.blends) > 32:
                self.blends.popitem(last=False)
        return pipe, self.blends[key]

    def speak(self, text: str, parts: Parts, speed: float) -> np.ndarray:
        return self.speak_timed(text, parts, speed)[0]

    def speak_timed(self, text: str, parts: Parts, speed: float) -> tuple[np.ndarray, Words]:
        pipe, voice = self._voice(parts)
        chunks, words, offset = [], [], 0.0
        for result in pipe(text, voice=voice, speed=speed):
            audio = np.asarray(result.audio, dtype=np.float32)
            for tok in result.tokens or []:
                word = tok.text.strip(".,!?;:\"'()…")
                if word and tok.start_ts is not None and tok.end_ts is not None:
                    words.append((word, offset + float(tok.start_ts), offset + float(tok.end_ts)))
            chunks.append(audio)
            offset += len(audio) / self.sample_rate
        if not chunks:
            raise ValueError(f"The engine produced no audio for: {text!r}")
        return np.concatenate(chunks), words
