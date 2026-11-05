"""One thread owns the engine; everything that needs speech goes through its queue.

Model code (torch) isn't safe to call from several threads at once, and one worker gives predictable timing:
requests wait in FIFO order and the queue length is reported, so the app can say "2 ahead of you".

Speech is streamed: the engine yields audio sentence by sentence, and each piece is handed to the caller as soon
as it exists. A caller that stops listening (a closed connection, an interruption) cancels the rest.
"""
import queue
import threading
from collections.abc import Iterator
from concurrent.futures import Future

from .engines.base import Engine

_DONE = object()


class TTSWorker:
    def __init__(self, engine: Engine, warm: bool = True):
        self.engine = engine
        self.jobs: queue.Queue = queue.Queue()
        self._busy = 0
        self._lock = threading.Lock()
        self.warm_error: str | None = None
        self.thread = threading.Thread(target=self._run, name="tts-worker", daemon=True)
        self.thread.start()
        if warm:
            self.submit("warm")

    def speak_timed(self, text: str, parts, speed: float, timeout: float = 300):
        return self.submit("speak_timed", text, parts, speed).result(timeout)

    def submit(self, method: str, *args) -> Future:
        fut: Future = Future()
        self.jobs.put(("call", fut, method, args))
        return fut

    def stream(self, text: str, parts, speed: float, timeout: float = 300) -> Iterator[tuple]:
        """Yields (audio, words) per sentence as the engine produces them. Closing the iterator cancels the rest."""
        out: queue.Queue = queue.Queue()
        cancel = threading.Event()
        self.jobs.put(("stream", out, cancel, (text, parts, speed)))

        def pieces():
            try:
                while True:
                    item = out.get(timeout=timeout)
                    if item is _DONE:
                        return
                    if isinstance(item, BaseException):
                        raise item
                    yield item
            finally:
                cancel.set()

        return pieces()

    @property
    def languages(self) -> list[str]:
        return list(getattr(self.engine, "languages", []))

    @property
    def queued(self) -> int:
        with self._lock:
            return self.jobs.qsize() + self._busy

    def _run(self) -> None:
        while True:
            job = self.jobs.get()
            with self._lock:
                self._busy = 1
            try:
                if job[0] == "call":
                    self._call(*job[1:])
                else:
                    self._stream(*job[1:])
            finally:
                with self._lock:
                    self._busy = 0

    def _call(self, fut: Future, method: str, args) -> None:
        try:
            if fut.set_running_or_notify_cancel():
                fut.set_result(getattr(self.engine, method)(*args))
        except Exception as e:
            if method == "warm":
                self.warm_error = str(e)
            fut.set_exception(e)

    def _stream(self, out: queue.Queue, cancel: threading.Event, args) -> None:
        try:
            if cancel.is_set():
                return
            for piece in self.engine.speak_stream(*args):
                out.put(piece)
                if cancel.is_set():   # nobody is listening any more: stop making audio
                    break
        except Exception as e:
            out.put(e)
        finally:
            out.put(_DONE)
