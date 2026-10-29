"""Audio cache keyed by content: the same inputs always map to the same file, so keys never go stale.

<workspace>/cache/<key>.wav (24 kHz, 16-bit mono) + <key>.json (inputs, duration, words, created)
"""
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import soundfile as sf

from .fx import SAMPLE_RATE


def make_key(**inputs) -> str:
    """sha1 of the canonical JSON of the inputs. Pass the *spoken* text (after pronunciations) and the resolved
    voice blend, so editing a respelling or re-saving a signature changes the key."""
    return hashlib.sha1(json.dumps(inputs, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]


class AudioCache:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def wav(self, key: str) -> Path:
        return self.root / f"{key}.wav"

    def meta(self, key: str) -> dict | None:
        path = self.root / f"{key}.json"
        return json.loads(path.read_text()) if path.exists() and self.wav(key).exists() else None

    def put(self, key: str, audio: np.ndarray, inputs: dict, extra: dict | None = None) -> dict:
        sf.write(self.wav(key), audio, SAMPLE_RATE, subtype="PCM_16")
        return self.put_file(key, inputs, extra)

    def put_file(self, key: str, inputs: dict, extra: dict | None = None) -> dict:
        """Record metadata for a wav already written to wav(key) (for example by ffmpeg)."""
        info = sf.info(self.wav(key))
        meta = {"inputs": inputs, "duration": round(info.duration, 3), "created": time.time(), **(extra or {})}
        (self.root / f"{key}.json").write_text(json.dumps(meta, ensure_ascii=False))
        return meta

    def stats(self) -> dict:
        files = list(self.root.glob("*.wav"))
        return {"files": len(files), "mb": round(sum(f.stat().st_size for f in files) / 1e6, 1)}

    def trim(self, older_than_days: float) -> int:
        cutoff = time.time() - older_than_days * 86400
        removed = 0
        for wav in self.root.glob("*.wav"):
            if wav.stat().st_mtime < cutoff:
                wav.unlink()
                wav.with_suffix(".json").unlink(missing_ok=True)
                wav.with_suffix(".png").unlink(missing_ok=True)
                removed += 1
        return removed

    @staticmethod
    def is_key(key: str) -> bool:
        return len(key) == 20 and all(c in "0123456789abcdef" for c in key)
