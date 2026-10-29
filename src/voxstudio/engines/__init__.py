"""Speech engines. Kokoro is the first; anything that implements Engine can be added."""
from .base import Engine, VoiceInfo


def load_engine(name: str) -> Engine:
    if name == "kokoro":
        from .kokoro import KokoroEngine
        return KokoroEngine()
    if name == "fake":
        from .fake import FakeEngine
        return FakeEngine()
    raise ValueError(f"Unknown engine '{name}' (use kokoro or fake)")


__all__ = ["Engine", "VoiceInfo", "load_engine"]
