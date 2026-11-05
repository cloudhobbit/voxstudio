"""The effects chain: pitch -> character effect -> space, all through one ffmpeg call.

Some effects shift pitch. ffmpeg's `rubberband` filter does that best, but many builds lack it (Homebrew's
default `ffmpeg` does), so every pitch shift has a fallback built from `asetrate` + `atempo`, which changes the
timbre a little more but is always available.
"""
import functools
import json
import shutil
import subprocess
import threading
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SAMPLE_RATE = 24000


@dataclass(frozen=True)
class Capabilities:
    ffmpeg: str | None
    rubberband: bool = False
    mp3: bool = False
    version: str = ""

    @staticmethod
    @functools.lru_cache(maxsize=4)
    def detect(ffmpeg: str | None = None) -> "Capabilities":
        path = ffmpeg or find_ffmpeg()
        if not path:
            return Capabilities(None)
        filters = _run([path, "-hide_banner", "-filters"])
        encoders = _run([path, "-hide_banner", "-encoders"])
        version = _run([path, "-version"]).splitlines()[:1]
        return Capabilities(path, rubberband=" rubberband " in filters, mp3="libmp3lame" in encoders,
                            version=version[0] if version else "")


def _run(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def find_ffmpeg() -> str | None:
    for candidate in ("/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg", "ffmpeg"):
        found = shutil.which(candidate)
        if found:
            return found
    return None


def pitch_filter(ratio: float, caps: Capabilities) -> str:
    """A filter that multiplies pitch by `ratio` and keeps the duration."""
    if abs(ratio - 1) < 1e-4:
        return ""
    if caps.rubberband:
        return f"rubberband=pitch={ratio:.5f}"
    return f"asetrate={int(SAMPLE_RATE * ratio)},aresample={SAMPLE_RATE},atempo={1 / ratio:.5f}"


def semitones_ratio(semitones: float) -> float:
    return 2 ** (semitones / 12)


# name: (description, pitch ratio or None, filter string with the pitch step left out)
EFFECTS = {
    "none":    ("Plain voice", None, ""),
    "radio":   ("Walkie-talkie, phone call, old recording", None,
                "highpass=f=300,lowpass=f=3200,acompressor=threshold=-20dB:ratio=4:makeup=4"),
    "deep":    ("Giant, monster, deep villain", 0.82, "lowpass=f=6000"),
    "tiny":    ("Cartoon creature, chipmunk, tiny sidekick", 1.35, ""),
    "robot":   ("Robot, AI, ship's computer", None,
                "afftfilt=real='hypot(re,im)*sin(0)':imag='hypot(re,im)*cos(0)':win_size=512:overlap=0.75,"
                "aecho=0.8:0.6:20:0.4"),
    "echo":    ("Big hall, ancient being, god-like voice", None, "aecho=0.8:0.85:120|240:0.35|0.2"),
    "inner":   ("Inner thoughts, memory, flashback", 0.94, "aecho=0.6:0.5:60:0.3,lowpass=f=7000"),
    "crystal": ("Alien, crystal creature, telepathy", 0.9,
                "chorus=0.6:0.9:50|60:0.4|0.32:0.25|0.4:2|2.3,aecho=0.8:0.7:40|80:0.3|0.2"),
    "ghost":   ("Ghost, dream, spirit", 0.96, "vibrato=f=5:d=0.25,aecho=0.8:0.9:300|600:0.35|0.25"),
}

# name: (description, filter string)
SPACES = {
    "dry":     ("Studio: no room at all", ""),
    "room":    ("A small room, two people talking", "aecho=0.8:0.7:12:0.15,lowpass=f=12000"),
    "hall":    ("Hall, church, command centre", "aecho=0.8:0.88:60|120:0.3|0.2"),
    "cave":    ("Cave, alien chamber", "aecho=0.8:0.9:200|400:0.4|0.25,lowpass=f=5000"),
    "phone":   ("Telephone, earpiece", "highpass=f=300,lowpass=f=3400,acompressor=threshold=-18dB:ratio=3:makeup=3"),
    "outdoor": ("Open air, a slight slap-back", "highpass=f=120,aecho=0.6:0.4:40:0.08"),
}


def chain(pitch: float, effect: str, space: str, caps: Capabilities) -> str:
    """The full ffmpeg -af string, or "" when nothing changes the audio."""
    if effect not in EFFECTS:
        raise ValueError(f"Unknown effect '{effect}' (use {', '.join(EFFECTS)})")
    if space not in SPACES:
        raise ValueError(f"Unknown space '{space}' (use {', '.join(SPACES)})")
    _, fx_ratio, fx_filter = EFFECTS[effect]
    ratio = semitones_ratio(pitch) * (fx_ratio or 1.0)
    steps = [pitch_filter(ratio, caps), fx_filter, SPACES[space][1]]
    return ",".join(s for s in steps if s)


def apply_chain(wav_in: Path, wav_out: Path, pitch: float, effect: str, space: str, caps: Capabilities) -> None:
    filters = chain(pitch, effect, space, caps)
    if not filters:
        shutil.copyfile(wav_in, wav_out)
        return
    if not caps.ffmpeg:
        raise RuntimeError("ffmpeg is needed for pitch, effects and spaces (brew install ffmpeg / apt install ffmpeg)")
    subprocess.run([caps.ffmpeg, "-y", "-v", "error", "-i", str(wav_in), "-af", filters,
                    "-ar", str(SAMPLE_RATE), "-ac", "1", "-c:a", "pcm_s16le", str(wav_out)], check=True)


def to_s16(audio) -> bytes:
    return (np.clip(np.asarray(audio, dtype=np.float32), -1.0, 1.0) * 32767).astype("<i2").tobytes()


def stream_chain(chunks: Iterable, pitch: float, effect: str, space: str, caps: Capabilities) -> Iterator[bytes]:
    """Float audio in, 16-bit PCM bytes out, through the same chain as apply_chain but as the audio arrives.

    With no pitch, effect or space the audio only changes format. Otherwise one ffmpeg process filters the stream:
    a helper thread feeds it while this generator reads what comes out, so sound leaves before the input ends.
    """
    filters = chain(pitch, effect, space, caps)
    if not filters:
        for chunk in chunks:
            yield to_s16(chunk)
        return
    if not caps.ffmpeg:
        raise RuntimeError("ffmpeg is needed for pitch, effects and spaces (brew install ffmpeg / apt install ffmpeg)")
    proc = subprocess.Popen([caps.ffmpeg, "-v", "error", "-f", "f32le", "-ar", str(SAMPLE_RATE), "-ac", "1", "-i", "pipe:0",
                             "-af", filters, "-f", "s16le", "-ar", str(SAMPLE_RATE), "-ac", "1", "-flush_packets", "1", "pipe:1"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    failed: list[BaseException] = []

    def feed() -> None:
        try:
            for chunk in chunks:
                try:
                    proc.stdin.write(np.asarray(chunk, dtype="<f4").tobytes())
                except (OSError, ValueError):   # the reader went away and the pipe is closed; stop quietly
                    break
        except BaseException as e:              # the engine failed: report it from the reading side
            failed.append(e)
        finally:
            close = getattr(chunks, "close", None)
            if close:
                close()
            try:
                proc.stdin.close()
            except OSError:
                pass

    feeder = threading.Thread(target=feed, name="fx-feed", daemon=True)
    feeder.start()
    try:
        while True:
            data = proc.stdout.read1(8192)
            if not data:
                break
            yield data
        feeder.join()
        code = proc.wait()
        if failed:
            raise failed[0]
        if code:
            raise RuntimeError(f"ffmpeg failed: {proc.stderr.read().decode(errors='replace').strip()[:300]}")
    finally:
        if proc.poll() is None:
            proc.kill()
        for pipe in (proc.stdout, proc.stderr):
            pipe.close()


def measure_loudness(wav: Path, caps: Capabilities) -> tuple[float, float] | None:
    """(integrated loudness in LUFS, true peak in dBTP) by EBU R128, or None when it cannot be measured
    (no ffmpeg, or audio too short or too quiet to gate)."""
    if not caps.ffmpeg:
        return None
    done = subprocess.run([caps.ffmpeg, "-hide_banner", "-nostats", "-i", str(wav), "-af", "loudnorm=print_format=json", "-f", "null", "-"],
                          capture_output=True, text=True)
    start, end = done.stderr.rfind("{"), done.stderr.rfind("}")
    if done.returncode or start < 0 or end < start:
        return None
    try:
        report = json.loads(done.stderr[start:end + 1])
        loudness, peak = float(report["input_i"]), float(report["input_tp"])
    except (ValueError, KeyError):
        return None
    if not np.isfinite(loudness) or loudness < -60:
        return None
    return loudness, peak


def levelling_gain(loudness: float, peak: float, target: float = -16.0, ceiling: float = -1.0) -> float:
    """Decibels to add so the audio sits at `target` LUFS, held back so its peak stays under `ceiling`."""
    return round(min(target - loudness, ceiling - peak), 2)
