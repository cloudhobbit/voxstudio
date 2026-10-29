"""Render a project: every block through the engine, joined with pauses, plus captions from the word timings.

The audio of each block comes from the cache (content-addressed), so re-rendering a project only renders the
blocks that changed. Captions are grouped into cues of at most `max_chars` characters, timed from the words.
"""
import json
import re
import shutil
import subprocess
from itertools import pairwise
from pathlib import Path

import numpy as np
import soundfile as sf

from .fx import SAMPLE_RATE, Capabilities

MAX_CHARS = 42
MAX_CUE_SECONDS = 6.0
MAX_GAP = 0.8     # a pause longer than this starts a new cue


def group_captions(words: list, max_chars: int = MAX_CHARS) -> list[dict]:
    """[(word, start, end)] -> [{start, end, text}]."""
    cues, cur = [], []

    def flush():
        if cur:
            cues.append({"start": round(cur[0][1], 3), "end": round(cur[-1][2], 3), "text": " ".join(w for w, _, _ in cur)})
            cur.clear()

    for word, start, end in words:
        if cur:
            length = len(" ".join(w for w, _, _ in cur)) + 1 + len(word)
            gap = start - cur[-1][2]
            if length > max_chars or gap > MAX_GAP or end - cur[0][1] > MAX_CUE_SECONDS:
                flush()
        cur.append((word, start, end))
    flush()
    # stretch each cue's end to the next cue's start (up to a limit) so captions don't flicker between words
    for a, b in pairwise(cues):
        a["end"] = round(min(b["start"], a["end"] + 0.6), 3)
    if cues:
        cues[-1]["end"] = round(cues[-1]["end"] + 0.4, 3)
    return cues


def _ts(seconds: float, sep: str) -> str:
    ms = round(seconds * 1000)
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02}{sep}{ms:03}"


def srt(cues: list[dict]) -> str:
    return "".join(f"{i}\n{_ts(c['start'], ',')} --> {_ts(c['end'], ',')}\n{c['text']}\n\n" for i, c in enumerate(cues, 1))


def vtt(cues: list[dict]) -> str:
    return "WEBVTT\n\n" + "".join(f"{_ts(c['start'], '.')} --> {_ts(c['end'], '.')}\n{c['text']}\n\n" for c in cues)


def punctuate(words: list, text: str) -> list:
    """Give the timed words back their punctuation and casing from the original text, where it lines up."""
    tokens = re.findall(r"\S+", text)
    if len(tokens) != len(words):
        return words
    return [(tok, s, e) for tok, (_, s, e) in zip(tokens, words, strict=True)]


def assemble(blocks: list[dict], cache_root: Path) -> dict:
    """blocks: [{id, text, key, duration, words, pause}] with their audio already in the cache.

    Returns {audio, duration, words (offset), spans: [{id, start, end}], cues}.
    """
    pieces, words, spans, cues, t = [], [], [], [], 0.0
    for b in blocks:
        audio, sr = sf.read(cache_root / f"{b['key']}.wav", dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        if sr != SAMPLE_RATE:
            raise ValueError(f"Block {b['id']} has sample rate {sr}, expected {SAMPLE_RATE}")
        length = len(audio) / SAMPLE_RATE
        block_words = [(w, round(t + s, 3), round(t + e, 3)) for w, s, e in punctuate(b.get("words") or [], b["text"])]
        words.extend(block_words)
        cues.extend(group_captions(block_words))   # captions never straddle two blocks
        spans.append({"id": b["id"], "start": round(t, 3), "end": round(t + length, 3)})
        pieces.append(audio)
        pieces.append(np.zeros(int(float(b.get("pause", 0.5)) * SAMPLE_RATE), dtype=np.float32))
        t += length + float(b.get("pause", 0.5))
    audio = np.concatenate(pieces) if pieces else np.zeros(0, dtype=np.float32)
    return {"audio": audio, "duration": round(len(audio) / SAMPLE_RATE, 3), "words": words, "spans": spans, "cues": cues}


def export(assembled: dict, out_dir: Path, name: str, fmt: str, captions: list[str], caps: Capabilities, blocks: list[dict]) -> list[Path]:
    """Write <name>.wav|mp3, captions and a blocks.json with the timings. Returns the files written."""
    out_dir.mkdir(parents=True, exist_ok=True)
    wav = out_dir / f"{name}.wav"
    sf.write(wav, assembled["audio"], SAMPLE_RATE, subtype="PCM_16")
    files = [wav]
    if fmt == "mp3":
        if not caps.ffmpeg or not caps.mp3:
            raise ValueError("MP3 export needs an ffmpeg build with libmp3lame; WAV was written instead")
        mp3 = out_dir / f"{name}.mp3"
        subprocess.run([caps.ffmpeg, "-y", "-v", "error", "-i", str(wav), "-codec:a", "libmp3lame", "-q:a", "2", str(mp3)], check=True)
        files = [mp3]
        wav.unlink()
    if "srt" in captions:
        (out_dir / f"{name}.srt").write_text(srt(assembled["cues"]), encoding="utf-8")
        files.append(out_dir / f"{name}.srt")
    if "vtt" in captions:
        (out_dir / f"{name}.vtt").write_text(vtt(assembled["cues"]), encoding="utf-8")
        files.append(out_dir / f"{name}.vtt")
    meta = {"duration": assembled["duration"], "blocks": [{**s, "text": b["text"], "voice": b["voice"]} for s, b in zip(assembled["spans"], blocks, strict=True)],
            "words": assembled["words"]}
    (out_dir / "timing.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    files.append(out_dir / "timing.json")
    return files


def clear_exports(folder: Path) -> None:
    if folder.exists():
        shutil.rmtree(folder)
