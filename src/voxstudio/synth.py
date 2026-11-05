"""From a line of text to audio: plan it (cache key, segments), then stream it.

There is one path. A line is cut into segments (inline pauses and pace changes), each segment is spoken by the
engine sentence by sentence, the audio runs through the effects chain as it arrives, and the bytes are handed to
the caller while they are also collected for the cache. Rendering a whole line is just reading the stream to its end.
"""
from collections.abc import Iterator
from dataclasses import dataclass, field

import numpy as np
import soundfile as sf

from . import markup, pronounce
from .cache import AudioCache, make_key
from .fx import EFFECTS, SAMPLE_RATE, SPACES, Capabilities, stream_chain
from .specs import parse_voice
from .worker import TTSWorker

CHUNK = 4800 * 2   # bytes of 16-bit audio per piece when replaying a cached line: 0.2 s


@dataclass
class Line:
    """A line that has been planned but not necessarily rendered."""
    text: str
    key: str
    inputs: dict
    parts: list
    segments: list            # [(spoken text, speed, pause after)]
    pitch: float
    effect: str
    space: str
    meta: dict | None = None  # filled when the audio is in the cache
    cached: bool = False      # true when it was already there before this request
    queued_ahead: int = 0
    words: list = field(default_factory=list)


class Synth:
    def __init__(self, workspace, worker: TTSWorker, cache: AudioCache, caps: Capabilities):
        self.ws, self.worker, self.cache, self.caps = workspace, worker, cache, caps

    def _mark(self, stretch: str, parts: list) -> str:
        if "](" in stretch:   # a pronunciation already rewrote it; exact sounds win over emphasis
            return stretch
        mark = getattr(self.worker.engine, "emphasise", None)
        return mark(stretch, parts) if mark else stretch

    def plan(self, text: str, voice: str, speed: float = 1.0, pitch: float = 0.0, effect: str = "none", space: str = "dry",
             project: str | None = None, pronounce_: bool = True, table: dict | None = None) -> Line:
        parts = parse_voice(voice, self.ws.signatures.entries()[0])
        if effect not in EFFECTS:
            raise ValueError(f"Unknown effect '{effect}' (use {', '.join(EFFECTS)})")
        if space not in SPACES:
            raise ValueError(f"Unknown space '{space}' (use {', '.join(SPACES)})")
        speed, pitch = float(speed), float(pitch)   # 0 and 0.0 must give the same key
        if pronounce_ and table is None:
            table = self.ws.pronunciation_table(project)
        segs = []
        for seg in markup.segments(text):
            spoken = pronounce.apply(seg["text"], table) if pronounce_ and seg["text"] else seg["text"]
            segs.append((markup.emphasise(spoken, lambda stretch: self._mark(stretch, parts)), round(min(2.0, max(0.5, speed * seg["pace"])), 3), seg["pause"]))
        if not any(s for s, _, _ in segs) and not any(p for _, _, p in segs):
            raise ValueError("There is nothing to say in that text")
        # A line without inline control keeps the key it always had (one string), so older caches stay valid.
        simple = len(segs) == 1 and segs[0][1] == speed and not segs[0][2]
        inputs = {"kind": "speech", "engine": self.worker.engine.name, "spoken": segs[0][0] if simple else [list(s) for s in segs],
                  "voice": parts, "speed": speed, "pitch": pitch, "effect": effect, "space": space, "fx": "rb" if self.caps.rubberband else "ar"}
        key = make_key(**inputs)
        meta = self.cache.meta(key)
        return Line(text=text, key=key, inputs=inputs, parts=parts, segments=segs, pitch=pitch, effect=effect, space=space,
                    meta=meta, cached=bool(meta), words=(meta or {}).get("words", []))

    def _speech(self, line: Line) -> Iterator[np.ndarray]:
        """Float audio, sentence by sentence, with the word timings gathered on the line as it goes."""
        offset = 0.0
        for spoken, speed, pause in line.segments:
            if spoken:
                length = 0
                for audio, words in self.worker.stream(spoken, line.parts, speed):
                    line.words.extend((w, round(s + offset, 3), round(e + offset, 3)) for w, s, e in words)
                    length += len(audio)
                    yield audio
                offset += length / SAMPLE_RATE
            if pause:
                yield np.zeros(int(pause * SAMPLE_RATE), dtype=np.float32)
                offset += pause

    def stream(self, line: Line) -> Iterator[bytes]:
        """16-bit mono PCM at 24 kHz, as it is made. Reading to the end stores the line in the cache."""
        if line.meta:
            audio, _ = sf.read(self.cache.wav(line.key), dtype="int16")
            data = audio.tobytes()
            for i in range(0, len(data), CHUNK):
                yield data[i:i + CHUNK]
            return
        line.queued_ahead = self.worker.queued
        line.words = []
        buf = bytearray()
        for data in stream_chain(self._speech(line), line.pitch, line.effect, line.space, self.caps):
            buf += data
            yield data
        if len(buf) < 2:
            raise ValueError(f"The engine produced no audio for: {line.text!r}")
        audio = np.frombuffer(bytes(buf[:len(buf) // 2 * 2]), dtype="<i2")
        line.meta = self.cache.put(line.key, audio, line.inputs, {"text": line.text, "words": line.words})

    def render(self, line: Line) -> dict:
        for _ in self.stream(line):
            pass
        return {"key": line.key, "url": f"/audio/{line.key}.wav", "duration": line.meta["duration"], "cached": line.cached,
                "queued_ahead": line.queued_ahead, "words": line.meta.get("words", [])}
