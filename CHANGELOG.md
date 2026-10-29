# Changelog

## 0.1.1 (29 Oct 2026)

Kokoro is a core dependency, so `uvx voxstudio` speaks on a fresh install. Python pinned to 3.10–3.12 (Kokoro has no
3.13 wheels yet), which lets `uv` pick a working interpreter instead of failing to resolve.

## 0.1.0 (29 Oct 2026)

First release: Library, Workbench, Mixer, Signatures, Pronunciations and Projects; Kokoro engine; HTTP API with
OpenAPI docs; WAV/MP3 export with SRT and WebVTT captions; one-folder YAML workspace.
