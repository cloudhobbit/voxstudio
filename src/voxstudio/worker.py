"""One thread owns the engine; everything that needs speech goes through its queue.

Model code (torch) isn't safe to call from several threads at once, and one worker gives predictable timing:
requests wait in FIFO order and the queue length is reported, so the app can say "2 ahead of you".
"""
import queue
import threading
from concurrent.futures import Future

from .engines.base import Engine


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
        self.jobs.put((fut, method, args))
        return fut

    @property
    def languages(self) -> list[str]:
        return list(getattr(self.engine, "languages", []))

    @property
    def queued(self) -> int:
        with self._lock:
            return self.jobs.qsize() + self._busy

    def _run(self) -> None:
        while True:
            fut, method, args = self.jobs.get()
            with self._lock:
                self._busy = 1
            try:
                if fut.set_running_or_notify_cancel():
                    fut.set_result(getattr(self.engine, method)(*args))
            except Exception as e:
                if method == "warm":
                    self.warm_error = str(e)
                fut.set_exception(e)
            finally:
                with self._lock:
                    self._busy = 0
