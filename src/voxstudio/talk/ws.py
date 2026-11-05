"""The WebSocket a browser talks through: `/api/talk`.

Client to server
    text   {"type": "start", "persona": {voice, system, speed, pitch, effect, space, greeting}, "end_silence_ms": 500}
    binary microphone audio: 16 kHz mono 16-bit little-endian
    text   {"type": "begin_turn"} / {"type": "end_turn"}     push-to-talk
    text   {"type": "text", "text": "..."}                    a typed turn
    text   {"type": "interrupt"}

Server to client
    text   {"type": "ready" | "speech_start" | "thinking" | "final" | "speaking" | "interrupted" | "metrics" | "done" | "listening" | "error", ...}
    binary speech: 24 kHz mono 16-bit little-endian
"""
import asyncio
import json
import os
from dataclasses import dataclass, fields
from urllib.parse import urlsplit

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from ..fx import SAMPLE_RATE
from . import missing
from .llm import LLM, FakeLLM, OpenAICompatLLM, pick_local_model
from .loop import DEFAULT_SYSTEM, Conversation, Persona
from .stt import STT, FakeSTT, load_stt
from .vad import SAMPLE_RATE as MIC_RATE


@dataclass
class TalkParts:
    """The models behind a conversation, made on first use and shared by every connection."""
    stt: STT | None = None
    llm: LLM | None = None
    fake: bool = False

    def get_stt(self) -> STT:
        if self.stt is None:
            self.stt = FakeSTT() if self.fake else load_stt(os.environ.get("VOXSTUDIO_STT", "auto"), os.environ.get("VOXSTUDIO_STT_MODEL") or None)
        return self.stt

    def get_llm(self) -> LLM:
        if self.llm is None:
            if self.fake:
                self.llm = FakeLLM()
            else:
                url = os.environ.get("VOXSTUDIO_LLM_URL", "http://127.0.0.1:11434/v1")
                self.llm = OpenAICompatLLM(url, os.environ.get("VOXSTUDIO_LLM_MODEL") or pick_local_model(url), os.environ.get("VOXSTUDIO_LLM_KEY", ""))
        return self.llm

    def describe(self) -> dict:
        out = {"available": not missing(), "missing": missing(), "default_system": DEFAULT_SYSTEM}
        try:
            llm = self.get_llm()
            out.update(llm=llm.name, llm_local=llm.local, llm_url=getattr(llm, "base_url", ""))
        except Exception as e:   # health must answer even when a model server is down
            out.update(llm=None, llm_local=True, llm_error=str(e))
        try:
            out["stt"] = self.get_stt().name
        except Exception as e:
            out.update(stt=None, stt_error=str(e))
        return out


def _persona(data: dict) -> Persona:
    known = {f.name for f in fields(Persona)}
    clean = {k: v for k, v in (data or {}).items() if k in known and v not in (None, "")}
    for k in ("speed", "pitch"):
        if k in clean:
            clean[k] = float(clean[k])
    if not 0.5 <= clean.get("speed", 1.0) <= 2.0 or not -12 <= clean.get("pitch", 0.0) <= 12:
        raise ValueError("speed must be 0.5-2.0 and pitch -12..12")
    return Persona(**clean)


def register(app: FastAPI, synth, allowed: set[str], parts: TalkParts) -> None:
    app.state.talk = parts

    @app.websocket("/api/talk")
    async def talk(ws: WebSocket):
        # The HTTP middleware does not see WebSockets, so the same local-only rule is applied here.
        origin = ws.headers.get("origin")
        if ws.url.hostname not in allowed or (origin and urlsplit(origin).hostname not in allowed):
            await ws.close(code=1008)
            return
        await ws.accept()
        loop = asyncio.get_running_loop()
        out: asyncio.Queue = asyncio.Queue()

        def emit(item) -> None:   # called from the conversation's threads
            loop.call_soon_threadsafe(out.put_nowait, item)

        async def sender() -> None:
            while True:
                item = await out.get()
                if item is None:
                    return
                try:
                    if isinstance(item, (bytes, bytearray)):
                        await ws.send_bytes(bytes(item))
                    else:
                        await ws.send_text(json.dumps(item, ensure_ascii=False))
                except (RuntimeError, WebSocketDisconnect):
                    return

        sending = asyncio.create_task(sender())
        conv: Conversation | None = None
        try:
            while True:
                msg = await ws.receive()
                if msg["type"] == "websocket.disconnect":
                    break
                if msg.get("bytes") is not None:
                    if conv:
                        conv.feed(msg["bytes"])
                    continue
                try:
                    data = json.loads(msg.get("text") or "{}")
                except ValueError:
                    emit({"type": "error", "message": "Messages must be JSON"})
                    continue
                kind = data.get("type")
                if kind == "start":
                    if conv:
                        conv.close()
                    try:
                        stt, llm = await asyncio.to_thread(parts.get_stt), await asyncio.to_thread(parts.get_llm)
                        conv = Conversation(synth, stt, llm, _persona(data.get("persona")), emit,
                                            end_silence_ms=int(min(2000, max(200, data.get("end_silence_ms", 500)))))
                    except (ValueError, RuntimeError, TypeError) as e:
                        emit({"type": "error", "message": str(e)})
                        conv = None
                        continue
                    emit({"type": "ready", "stt": stt.name, "llm": llm.name, "llm_local": llm.local, "mic_rate": MIC_RATE, "speech_rate": SAMPLE_RATE})
                    loop.run_in_executor(None, stt.warm)   # load the model while the person is still reading the page
                    conv.greet()
                elif conv is None:
                    emit({"type": "error", "message": 'Send {"type": "start"} first'})
                elif kind == "text" and str(data.get("text", "")).strip():
                    conv.say(str(data["text"])[:2000])
                elif kind == "begin_turn":
                    conv.begin_turn()
                elif kind == "end_turn":
                    conv.end_turn()
                elif kind == "interrupt":
                    conv.interrupt()
        except WebSocketDisconnect:
            pass
        finally:
            if conv:
                conv.close()
            out.put_nowait(None)
            await sending
