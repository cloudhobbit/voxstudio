# Vox Studio

**A voice studio you start with one command.** Audition 30+ AI voices on your own line, blend them into new ones,
tune pitch and room sound, fix how names are said, then narrate a whole script and export MP3 with captions.
MIT, offline, no Electron, runs on a laptop CPU. Every button is also an HTTP call, so your coding agent can use it.

[![PyPI](https://img.shields.io/pypi/v/voxstudio?label=pypi)](https://pypi.org/project/voxstudio/)
[![CI](https://github.com/cloudhobbit/voxstudio/actions/workflows/ci.yml/badge.svg)](https://github.com/cloudhobbit/voxstudio/actions/workflows/ci.yml)
[![MIT](https://img.shields.io/badge/licence-MIT-blue)](LICENSE)
![Python 3.10–3.12](https://img.shields.io/badge/python-3.10%E2%80%933.12-blue)

```bash
uvx voxstudio
```

That is the whole install (`uv` fetches a Python 3.12 if your system one is newer; Kokoro has no 3.13 build yet). It opens `http://127.0.0.1:7860` and loads the Kokoro voice model in the background
(first run downloads about 330 MB). Prefer a permanent install? `pipx install voxstudio && voxstudio`.
No model yet? `uvx voxstudio --engine fake` shows the app with tones instead of speech.

<p align="center">
  <img src="docs/library.png" alt="The Library: every voice on the same line, with filters, ratings and a compare tray" width="820">
</p>

Hear an export made with it: [chapter-one.mp3](docs/demo/chapter-one.mp3) and [its captions](docs/demo/chapter-one.srt).

## 20-second tour

1. **Library**: every voice says your line. Filter by gender, accent and grade, favourite, rate, compare four back to back.
2. **Workbench**: pick a voice, set speed, pitch, a character effect (robot, ghost, radio…) and a space (room, hall, phone…). Hear it in about a second. Save it as a preset.
3. **Mixer**: blend two to four voices with linked sliders; save the blend as a signature voice, `@narrator`.
4. **Pronunciations**: `Chandrayaan: Chun-druh-yaan`, or exact phonemes. A scanner finds the names in your script.
5. **Projects**: paste a script, one block per paragraph, give each block a voice, render (only changed blocks re-render), export WAV or MP3 plus SRT and WebVTT captions timed from the engine's word timestamps.

Keyboard everywhere (`Space` play, `J`/`K` next voice, `F` favourite, `C` compare, `1`–`5` rate, `?` for the list).
Light and dark themes. Works at phone width.

<p align="center">
  <img src="docs/project.png" alt="A project: three blocks with two voices, rendered and exported with captions" width="820">
</p>

## For coding agents

Everything the app does is a localhost HTTP call, documented at `/api/docs`. [SKILL.md](SKILL.md) teaches Claude
Code, Codex and friends to narrate for you: start the server, speak a line, build a project, export with captions,
fix a pronunciation. Drop it in your skills folder or point the agent at this repo.

```bash
curl -s localhost:7860/api/speak -H 'content-type: application/json' \
  -d '{"text": "Hello from the command line.", "voice": "af_heart:0.6,bf_emma:0.4", "pitch": -1, "space": "room"}'
# {"key": "…", "url": "/audio/….wav", "duration": 2.1, "cached": false, "words": [["Hello", 0.1, 0.4], …]}
```

```python
import requests
r = requests.post("http://127.0.0.1:7860/api/speak", json={"text": "Rendered from Python.", "voice": "@narrator"}).json()
open("line.wav", "wb").write(requests.get("http://127.0.0.1:7860" + r["url"]).content)
```

Projects, signatures, presets and pronunciations have CRUD routes (`/api/projects`, `/api/signatures`, …).
Writes carry an `etag`; if the file changed on disk the server answers 409 instead of overwriting.

A small CLI covers scripts and cron jobs:

```bash
voxstudio speak "One line to a file." --voice bm_george --pitch -2 --space hall --out line.wav
voxstudio voices
```

## Which voice tool do you want?

| | **Vox Studio** | [VoiceStudio](https://github.com/debpalash/VoiceStudio) | ElevenLabs Studio |
|---|---|---|---|
| Install | `uvx voxstudio` | `curl \| sh`, Electron app | web account |
| Licence | MIT | AGPL-3.0 + commercial | proprietary |
| Runs | offline, laptop CPU | offline, GPU helps a lot | cloud |
| Voices | Kokoro's 30+ and any blend | dozens of engines, 646 languages | thousands |
| Cloning, dubbing | no | yes | yes |
| Pronunciation fixes with before/after | yes | partial | yes |
| Captions from word timings | SRT, WebVTT | yes | yes |
| Per-block voice and settings in a script | yes | yes | yes |
| Everything as an HTTP call + agent skill | yes | API | API |
| Your data | one folder of YAML | app data | their servers |

Pick VoiceStudio if you need cloning, dubbing or many languages and do not mind a desktop app. Pick ElevenLabs if
you need the best acting money can buy. Pick Vox Studio when you want a narration tool you `pip install`, keep in
git, and drive from scripts and agents.

## Honest limits

- Kokoro is good for narration and characters, not studio-grade acting. English (US and UK) is best; Hindi,
  Spanish, French, Italian, Japanese, Portuguese and Chinese work with fewer voices.
- No cloning. That is a feature for some users and a deal-breaker for others.
- `ffmpeg` is needed for pitch, effects, spaces and MP3 (`brew install ffmpeg` or `apt install ffmpeg`).
  Without it you still get plain speech and WAV. `espeak-ng` is optional and adds phoneme suggestions.

## The workspace

Everything lives in one folder (default `~/VoxStudio`, or `voxstudio --workspace DIR`):

```
library.yaml          favourites, ratings, tags, display names per voice
signatures.yaml       narrator: {mix: "af_heart:0.6,bf_emma:0.4", speed: 1.0, pitch: 0, note: "warm"}
pronunciations.yaml   Chandrayaan: "Chun-druh-yaan"      Pragyan: "/pɹˈʌɡjɑn/"
presets.yaml          villain: {voice: am_onyx, speed: 0.9, pitch: -2, effect: deep, space: cave}
projects/<slug>/project.yaml
cache/                rendered audio by content hash; safe to delete
exports/<slug>/       chapter-one.mp3, .srt, .vtt, timing.json
```

Plain YAML, so you can edit it by hand or keep it in git. The app never overwrites a file that changed under it.

## Engines

Kokoro-82M (Apache-2.0) is the first engine: 82 million parameters, runs on a CPU, word timestamps for captions.
An engine is a small class with `voices()`, `speak()` and `speak_timed()`; see
[`src/voxstudio/engines/base.py`](src/voxstudio/engines/base.py). Pull requests for other engines are welcome.

## Security

The server binds `127.0.0.1` only, refuses requests whose `Host` or `Origin` is not localhost (so a web page
cannot talk to it), keeps every file path inside the workspace, and never builds shell commands from your text.

## Development

```bash
git clone https://github.com/cloudhobbit/voxstudio && cd voxstudio
uv venv && uv pip install -e ".[dev]"
.venv/bin/pytest             # seconds: a fake engine stands in for the model
.venv/bin/pytest --slow      # also one real Kokoro test
.venv/bin/voxstudio serve --engine fake --workspace /tmp/vox
```

The front end is plain ES modules and CSS under `src/voxstudio/app`: no build step, no dependencies.
See [CONTRIBUTING.md](CONTRIBUTING.md).

## Roadmap

- More engines (Piper, Chatterbox) behind the same interface
- Emphasis and pauses inside a block
- A render queue for long scripts, chapter markers, M4B audiobooks
- An MCP server next to the HTTP API

## Licence

MIT. Voices by [Kokoro](https://github.com/hexgrad/kokoro) (Apache-2.0).
