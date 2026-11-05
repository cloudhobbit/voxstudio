# Changelog

## 0.2.0 (5 Nov 2026)

- **OpenAI-compatible speech:** `POST /v1/audio/speech` (plus `/v1/models` and `/v1/audio/voices`). Point any
  OpenAI client at `http://127.0.0.1:7860/v1`. OpenAI voice names, voice ids, blends and `@signatures` all work.
- **MCP server:** `voxstudio mcp` gives agents seven tools over stdio, with no new dependencies.
- **Script import:** paste or upload plain text, Markdown, SRT/WebVTT or `NAME: line` dialogue; each speaker gets
  a voice, and blocks keep their speaker label.
- **Docker:** a CPU image, with `--host` and `--allow-host` flags for running inside a container.
- `ROADMAP.md`, decision records under `docs/decisions`, and a pull request template.

## 0.1.1 (29 Oct 2026)

Kokoro is a core dependency, so `uvx voxstudio` speaks on a fresh install. Python pinned to 3.10–3.12 (Kokoro has no
3.13 wheels yet), which lets `uv` pick a working interpreter instead of failing to resolve.

## 0.1.0 (29 Oct 2026)

First release: Library, Workbench, Mixer, Signatures, Pronunciations and Projects; Kokoro engine; HTTP API with
OpenAPI docs; WAV/MP3 export with SRT and WebVTT captions; one-folder YAML workspace.
