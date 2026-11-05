"""One conversation: microphone audio in, events and speech out.

The transport (a WebSocket, a test) calls `feed()` with 16 kHz mono 16-bit audio and receives everything through
`emit`: dicts for events, bytes for speech (24 kHz mono 16-bit). Nothing here knows about sockets.

Two things keep the wait short. Transcription starts during the silence that ends a turn, so the words are
usually ready when the turn is declared over. And the reply is spoken clause by clause as the model writes it.

Speaking over the reply interrupts it: the model and the voice stop within one audio chunk.
"""
import threading
import time
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field

import numpy as np

from .speakable import Speakable
from .vad import FRAME, FRAME_MS, EnergyVAD

DEFAULT_SYSTEM = ("You are talking with someone out loud. Answer the way a person speaks: one to three short sentences, "
                  "plain words, no lists, no markdown, no emoji. If you did not catch something, say so and ask.")
MIN_SPEECH_MS = 200      # shorter than this is a cough or a click, not a turn
PREROLL_FRAMES = 10      # 200 ms kept from before the turn was noticed, so the first word is whole
MAX_HISTORY = 24


@dataclass
class Persona:
    voice: str = "af_heart"
    system: str = DEFAULT_SYSTEM
    speed: float = 1.0
    pitch: float = 0.0
    effect: str = "none"
    space: str = "dry"
    greeting: str = ""


@dataclass
class _Turn:
    cancel: threading.Event = field(default_factory=threading.Event)
    done: threading.Event = field(default_factory=threading.Event)
    spoken: list = field(default_factory=list)
    after: "_Turn | None" = None   # the turn this one replaced; it finishes first, so the history stays in order


class Conversation:
    def __init__(self, synth, stt, llm, persona: Persona | None = None, emit=lambda item: None,
                 end_silence_ms: int = 500, eager_ms: int = 250, clock=time.monotonic):
        self.synth, self.stt, self.llm = synth, stt, llm
        self.persona = persona or Persona()
        self.emit, self.clock = emit, clock
        self.end_silence_ms, self.eager_ms = end_silence_ms, min(eager_ms, end_silence_ms)
        self.vad = EnergyVAD(end_silence_ms=end_silence_ms)
        self.history: list[dict] = []
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="talk-stt")
        self.lock = threading.Lock()
        self._pending = b""
        self._preroll: deque = deque(maxlen=PREROLL_FRAMES)
        self._utterance: list[np.ndarray] = []
        self._loud = 0                       # loud frames in the current turn: how much was actually said
        self._manual = False                 # push-to-talk: the client marks the turn, loudness is ignored
        self._eager: Future | None = None
        self._turn: _Turn | None = None
        self.closed = False
        self.synth.plan("Hello.", self.persona.voice, self.persona.speed, self.persona.pitch, self.persona.effect, self.persona.space)  # fail now on a bad voice

    # ---- audio in --------------------------------------------------------------------------

    def feed(self, pcm: bytes) -> None:
        """Microphone audio: 16 kHz, mono, 16-bit little-endian, any chunking."""
        data = self._pending + pcm
        whole = len(data) // (FRAME * 2) * (FRAME * 2)
        self._pending = data[whole:]
        for i in range(0, whole, FRAME * 2):
            self._frame(np.frombuffer(data[i:i + FRAME * 2], dtype="<i2"))

    def _frame(self, frame: np.ndarray) -> None:
        if self._manual:
            self._utterance.append(frame)
            return
        event = self.vad.feed(frame)
        if event == "start":
            self._utterance, self._loud = list(self._preroll), self.vad.start_frames
            self._begin()
        elif self.vad.in_speech and self.vad.silence_ms == 0:
            self._loud += 1
        if self.vad.in_speech or event == "end":
            self._utterance.append(frame)
        else:
            self._preroll.append(frame)
        if self.vad.in_speech:
            if self.vad.silence_ms == 0:
                self._eager = None           # they kept talking: what was heard so far is not the whole turn
            elif self._eager is None and self.vad.silence_ms >= self.eager_ms:
                self._eager = self.pool.submit(self._transcribe, self._audio())
        if event == "end":
            speech_ms = self._loud * FRAME_MS
            eager, self._eager = self._eager, None
            if speech_ms < MIN_SPEECH_MS:
                self.emit({"type": "listening"})
                return
            self._answer(eager or self.pool.submit(self._transcribe, self._audio()), eager is not None, self.end_silence_ms)

    def _audio(self) -> np.ndarray:
        return np.concatenate(self._utterance).astype(np.float32) / 32768.0

    def _transcribe(self, audio: np.ndarray) -> tuple[str, float]:
        started = self.clock()
        return self.stt.transcribe(audio), (self.clock() - started) * 1000

    # ---- turns marked by the client (push-to-talk) and typed text ------------------------------

    def begin_turn(self) -> None:
        self._manual, self._utterance, self._eager = True, [], None
        self.vad.reset()
        self._begin()

    def end_turn(self) -> None:
        if not self._manual:
            return
        self._manual = False
        if len(self._utterance) * FRAME_MS < MIN_SPEECH_MS:
            self.emit({"type": "listening"})
            return
        self._answer(self.pool.submit(self._transcribe, self._audio()), False, 0)

    def say(self, text: str) -> None:
        """A typed turn: the same reply path without the microphone."""
        self._begin()
        done: Future = Future()
        done.set_result((text, 0.0))
        self._answer(done, False, 0)

    def interrupt(self) -> None:
        self._stop_reply()

    def greet(self) -> None:
        if self.persona.greeting.strip():
            turn = self._new_turn()
            threading.Thread(target=self._speak_only, args=(turn, self.persona.greeting.strip()), name="talk-greet", daemon=True).start()

    # ---- the reply -----------------------------------------------------------------------------

    def _begin(self) -> None:
        """The person started a turn: whatever was being said stops."""
        self.emit({"type": "speech_start"})
        self._stop_reply()

    def _stop_reply(self) -> None:
        with self.lock:
            turn = self._turn
        if turn and not turn.done.is_set() and not turn.cancel.is_set():
            turn.cancel.set()
            self.emit({"type": "interrupted"})

    def _new_turn(self) -> _Turn:
        turn = _Turn()
        with self.lock:
            old, self._turn = self._turn, turn
        if old:
            old.cancel.set()
            turn.after = old
        return turn

    @staticmethod
    def _settle(turn: _Turn) -> None:
        if turn.after:
            turn.after.done.wait(5)
            turn.after = None

    def _answer(self, heard: Future, eager: bool, silence_ms: int) -> None:
        turn = self._new_turn()
        threading.Thread(target=self._reply, args=(turn, heard, eager, silence_ms, self.clock()), name="talk-reply", daemon=True).start()

    def _speak(self, turn: _Turn, piece: str, on_first_audio=None) -> bool:
        """Speak one piece; False if the turn was interrupted before it finished."""
        p = self.persona
        line = self.synth.plan(piece, p.voice, p.speed, p.pitch, p.effect, p.space)
        self.emit({"type": "speaking", "text": piece})
        stream = self.synth.stream(line)
        try:
            for chunk in stream:
                if turn.cancel.is_set():
                    return False
                if on_first_audio:
                    on_first_audio()
                    on_first_audio = None
                self.emit(chunk)
        finally:
            stream.close()
        turn.spoken.append(piece)
        return True

    def _speak_only(self, turn: _Turn, text: str) -> None:
        try:
            self._settle(turn)
            if self._speak(turn, text):
                self.history.append({"role": "assistant", "content": text})
            self.emit({"type": "done", "text": text, "interrupted": turn.cancel.is_set()})
        except Exception as e:   # the page must hear about it, not hang
            self.emit({"type": "error", "message": str(e)})
        finally:
            turn.done.set()

    def _reply(self, turn: _Turn, heard: Future, eager: bool, silence_ms: int, t_end: float) -> None:
        m: dict = {"eager_stt": eager, "end_silence_ms": silence_ms}
        try:
            self.emit({"type": "thinking"})
            text, stt_ms = heard.result(timeout=120)
            self._settle(turn)
            m["stt_ms"], m["stt_wait_ms"] = round(stt_ms), round((self.clock() - t_end) * 1000)
            text = text.strip()
            if turn.cancel.is_set():
                return
            if not text:
                self.emit({"type": "listening"})
                return
            self.emit({"type": "final", "text": text})
            self.history.append({"role": "user", "content": text})
            messages = [{"role": "system", "content": self.persona.system}, *self.history[-MAX_HISTORY:]]
            t_llm = self.clock()

            piece_at: list[float] = []   # when the first speakable piece existed

            def first_audio():
                if "voice_to_voice_ms" in m:   # only the first sound of the reply is the wait the person feels
                    return
                now = self.clock()
                m["tts_first_audio_ms"] = round((now - piece_at[0]) * 1000)
                m["voice_to_voice_ms"] = round((now - t_end) * 1000)        # from the turn being declared over
                m["from_speech_end_ms"] = m["voice_to_voice_ms"] + silence_ms   # from the last word, as the person feels it

            def speak(piece: str) -> bool:
                if not piece_at:
                    piece_at.append(self.clock())
                    m["llm_first_piece_ms"] = round((piece_at[0] - t_llm) * 1000)
                return self._speak(turn, piece, first_audio)

            split, tokens = Speakable(), self.llm.stream(messages)
            try:
                for token in tokens:
                    if turn.cancel.is_set():
                        break
                    m.setdefault("llm_first_token_ms", round((self.clock() - t_llm) * 1000))
                    if not all(speak(piece) for piece in split.feed(token)):
                        break
                if not turn.cancel.is_set():
                    all(speak(piece) for piece in split.flush())
            finally:
                close = getattr(tokens, "close", None)
                if close:
                    close()   # drops the connection, so the model stops writing a reply nobody will hear
            said = " ".join(turn.spoken)
            if said:
                self.history.append({"role": "assistant", "content": said + (" …" if turn.cancel.is_set() else "")})
            m["reply_ms"] = round((self.clock() - t_end) * 1000)
            self.emit({"type": "metrics", **m})
            self.emit({"type": "done", "text": said, "interrupted": turn.cancel.is_set()})
        except Exception as e:
            self.emit({"type": "error", "message": str(e)})
        finally:
            turn.done.set()

    def wait(self, timeout: float = 60) -> bool:
        """Block until the current reply has finished (for tests and scripts)."""
        with self.lock:
            turn = self._turn
        return turn.done.wait(timeout) if turn else True

    def close(self) -> None:
        self.closed = True
        with self.lock:
            turn = self._turn
        if turn:
            turn.cancel.set()
        self.pool.shutdown(wait=False, cancel_futures=True)
