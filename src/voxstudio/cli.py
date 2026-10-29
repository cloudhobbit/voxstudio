"""The voxstudio command: serve the app, or speak a line without the UI."""
import argparse
import logging
import socket
import sys
import webbrowser
from pathlib import Path

from . import NAME, __version__


def free_port(start: int) -> int:
    for port in range(start, start + 20):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise SystemExit(f"No free port between {start} and {start + 19}")


def serve(port: int, workspace: str | None, open_browser: bool, engine: str) -> None:
    import uvicorn

    from .api import create_app
    from .workspace import Workspace

    ws = Workspace(workspace)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S",
                        handlers=[logging.StreamHandler(), logging.FileHandler(ws.root / "voxstudio.log")])
    chosen = free_port(port)
    if chosen != port:
        print(f"Port {port} is busy; using {chosen}")
    url = f"http://127.0.0.1:{chosen}/"
    print(f"{NAME} {__version__}: {url}   (API docs: {url}api/docs)\nWorkspace: {ws.root}")
    if engine == "kokoro":
        print("Loading Kokoro in the background (the first start downloads the model, about 330 MB)...")
    app = create_app(ws, engine_name=engine)
    if open_browser:
        webbrowser.open(url)
    uvicorn.run(app, host="127.0.0.1", port=chosen, log_level="warning")


def speak(text: str, voice: str, out: str, speed: float, pitch: float, effect: str, space: str, engine: str,
          workspace: str | None) -> None:
    import soundfile as sf

    from .engines import load_engine
    from .fx import SAMPLE_RATE, Capabilities, apply_chain
    from .specs import parse_voice
    from .workspace import Workspace

    ws = Workspace(workspace)
    parts = parse_voice(voice, ws.signatures.entries()[0])
    eng = load_engine(engine)
    audio = eng.speak(text, parts, speed)
    path = Path(out)
    sf.write(path, audio, SAMPLE_RATE, subtype="PCM_16")
    if pitch or effect != "none" or space != "dry":
        tmp = path.with_suffix(".raw.wav")
        path.rename(tmp)
        apply_chain(tmp, path, pitch, effect, space, Capabilities.detect())
        tmp.unlink()
    print(f"Wrote {path} ({len(audio) / SAMPLE_RATE:.1f}s)")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="voxstudio", description=f"{NAME}: a local, free voice studio.")
    p.add_argument("--version", action="version", version=f"{NAME} {__version__}")
    sub = p.add_subparsers(dest="cmd")

    s = sub.add_parser("serve", help="start the app (default)")
    s.add_argument("--port", type=int, default=7860)
    s.add_argument("--workspace", help="folder for your voices and projects (default: ~/VoxStudio)")
    s.add_argument("--open", action="store_true", help="open the browser")
    s.add_argument("--engine", default="kokoro", choices=["kokoro", "fake"], help="fake: tones instead of a model")

    k = sub.add_parser("speak", help="write one line to a wav file")
    k.add_argument("text")
    k.add_argument("--voice", default="af_heart")
    k.add_argument("--out", default="out.wav")
    k.add_argument("--speed", type=float, default=1.0)
    k.add_argument("--pitch", type=float, default=0.0, help="semitones, -12..12")
    k.add_argument("--effect", default="none")
    k.add_argument("--space", default="dry")
    k.add_argument("--engine", default="kokoro", choices=["kokoro", "fake"])
    k.add_argument("--workspace")

    sub.add_parser("voices", help="list the voices")

    a = p.parse_args(argv)
    if a.cmd in (None, "serve"):
        if a.cmd is None:
            a = p.parse_args(["serve"] + (argv or sys.argv[1:]))
        serve(a.port, a.workspace, a.open, a.engine)
    elif a.cmd == "speak":
        speak(a.text, a.voice, a.out, a.speed, a.pitch, a.effect, a.space, a.engine, a.workspace)
    elif a.cmd == "voices":
        from .catalogue import VOICES
        for vid, v in VOICES.items():
            print(f"{vid:14} {v['name']:10} {v['accent']:6} {v['gender']}  {v['grade']:3} {v['character']}")
