"""OpenAI-compatible speech routes, so any tool that speaks to `/v1/audio/speech` can use Vox Studio by changing
its base URL to http://127.0.0.1:7860/v1 (the API key is ignored).

`voice` takes the OpenAI names (mapped to the nearest Vox Studio voice), any voice id, a blend
(`af_heart:0.6,bf_emma:0.4`) or a saved signature (`@narrator`). Extra fields `pitch`, `effect` and `space` work too.
`response_format: "pcm"` is streamed: bytes leave after the first sentence, not the last.
"""
import io
import subprocess
from typing import Annotated

import soundfile as sf
from fastapi import Body, FastAPI
from fastapi.responses import JSONResponse, Response, StreamingResponse

from .catalogue import VOICES
from .fx import SAMPLE_RATE

# OpenAI's voice names -> the closest voice here (same name where one exists)
OPENAI_VOICES = {
    "alloy": "af_alloy", "echo": "am_echo", "fable": "bm_fable", "onyx": "am_onyx", "nova": "af_nova",
    "shimmer": "af_heart", "ash": "am_michael", "coral": "af_bella", "sage": "af_sarah", "ballad": "bm_george",
    "verse": "am_puck",
}
MODELS = ("kokoro", "tts-1", "tts-1-hd", "gpt-4o-mini-tts")   # every name is served by the loaded engine
MEDIA = {"wav": "audio/wav", "pcm": "audio/pcm", "flac": "audio/flac", "mp3": "audio/mpeg", "opus": "audio/ogg", "aac": "audio/aac"}
FFMPEG_ARGS = {"mp3": ["-f", "mp3", "-codec:a", "libmp3lame", "-q:a", "2"], "opus": ["-f", "ogg", "-codec:a", "libopus"],
               "aac": ["-f", "adts", "-codec:a", "aac"]}
MAX_INPUT = 4096


def error(message: str, status: int = 400, param: str | None = None, code: str | None = None) -> JSONResponse:
    return JSONResponse({"error": {"message": message, "type": "invalid_request_error", "param": param, "code": code}}, status_code=status)


def encode(wav_path, fmt: str, caps) -> bytes:
    if fmt == "wav":
        return wav_path.read_bytes()
    audio, _ = sf.read(wav_path, dtype="int16")
    if fmt == "flac":
        buf = io.BytesIO()
        sf.write(buf, audio, SAMPLE_RATE, format="FLAC")
        return buf.getvalue()
    if not caps.ffmpeg:
        raise ValueError(f"'{fmt}' needs ffmpeg; ask for wav, pcm or flac, or install ffmpeg")
    done = subprocess.run([caps.ffmpeg, "-v", "error", "-i", str(wav_path), *FFMPEG_ARGS[fmt], "-"], capture_output=True)
    if done.returncode or not done.stdout:
        raise ValueError(f"This ffmpeg cannot write '{fmt}' ({done.stderr.decode(errors='replace').strip()[:160]}); ask for wav, pcm or flac")
    return done.stdout


def register(app: FastAPI, synth, cache, caps, engine_name: str) -> None:
    @app.post("/v1/audio/speech", tags=["OpenAI-compatible"])
    def speech(body: Annotated[dict, Body()]):
        """Text to speech in the OpenAI shape: {model, input, voice, response_format, speed}."""
        text = body.get("input")
        if not isinstance(text, str) or not text.strip():
            return error("'input' is required: the text to speak", param="input")
        if len(text) > MAX_INPUT:
            return error(f"'input' is {len(text)} characters; the limit is {MAX_INPUT}", param="input", code="string_above_max_length")
        fmt = str(body.get("response_format") or "mp3").lower()
        if fmt not in MEDIA:
            return error(f"Unknown response_format '{fmt}' (use {', '.join(MEDIA)})", param="response_format")
        voice = body.get("voice") or "alloy"
        if isinstance(voice, dict):   # newer clients may send {"id": "..."}
            voice = voice.get("id") or "alloy"
        voice = OPENAI_VOICES.get(str(voice).lower(), str(voice))
        try:
            speed = float(body.get("speed", 1.0))
            pitch = float(body.get("pitch", 0))
        except (TypeError, ValueError):
            return error("'speed' and 'pitch' must be numbers", param="speed")
        if not 0.25 <= speed <= 4.0:
            return error("'speed' must be between 0.25 and 4.0", param="speed")
        if not -12 <= pitch <= 12:
            return error("'pitch' must be between -12 and 12 semitones", param="pitch")
        speed = min(2.0, max(0.5, speed))   # the engine's own range
        try:
            line = synth.plan(text, voice, speed, pitch, str(body.get("effect", "none")), str(body.get("space", "dry")), body.get("project"))
            if fmt == "pcm":   # raw audio can leave while it is still being made
                return StreamingResponse(synth.stream(line), media_type=MEDIA[fmt],
                                         headers={"X-Voxstudio-Key": line.key, "X-Voxstudio-Cached": str(line.cached).lower()})
            r = synth.render(line)
            data = encode(cache.wav(r["key"]), fmt, caps)
        except (ValueError, RuntimeError) as e:
            return error(str(e), param="voice" if "voice" in str(e).lower() else None)
        return Response(content=data, media_type=MEDIA[fmt], headers={"X-Voxstudio-Key": r["key"], "X-Voxstudio-Duration": str(r["duration"]),
                                                                       "X-Voxstudio-Cached": str(r["cached"]).lower()})

    @app.get("/v1/models", tags=["OpenAI-compatible"])
    def models():
        return {"object": "list", "data": [{"id": m, "object": "model", "created": 0, "owned_by": f"voxstudio/{engine_name}"} for m in MODELS]}

    @app.get("/v1/audio/voices", tags=["OpenAI-compatible"])
    def voices():
        """Voice ids this server accepts, plus the OpenAI names it maps."""
        return {"voices": [{"id": vid, "name": v["name"], "language": v["language"], "gender": v["gender"]} for vid, v in VOICES.items()],
                "aliases": OPENAI_VOICES}
