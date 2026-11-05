"""Talk: a real-time voice conversation on top of the studio's voices (optional extra `voxstudio[talk]`).

    microphone -> end-of-turn detection -> speech-to-text -> language model -> speech, piece by piece

Each stage sits behind a small protocol with a fake, so the loop is tested without any model.
"""
import importlib.util


def missing() -> list[str]:
    """What the extra still needs before a browser can connect (uvicorn serves WebSockets through `websockets`)."""
    return [] if importlib.util.find_spec("websockets") or importlib.util.find_spec("wsproto") else ["websockets"]
