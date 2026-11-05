# Changelog

## 0.3.0 (5 Nov 2026)

- **Sound starts after the first sentence.** `POST /api/speak/stream` sends 16-bit PCM while the line is still
  being made, and the Workbench plays it live. On a laptop a 14-second paragraph starts in about 0.4 s instead of
  1.4 s, effects included. OpenAI-style requests with `response_format: "pcm"` are streamed too.
- **Inline control:** `[pause 0.8]`, `*emphasis*`, `[slow]…[/slow]` and `[fast]…[/fast]` inside any text. The
  marks never appear in captions. Emphasis uses the engine's stress marks and is subtle.
- **Loudness levelling on export:** each block gets one gain to reach −16 LUFS (EBU R128), so mixed voices sit
  together. On by default; `"loudness": null` leaves levels alone.
- Markdown import keeps `*emphasis*` instead of dropping it.
- Under the hood there is now one synthesis path: rendering a line is reading its stream to the end. A listener
  who leaves cancels the rest of the work.
- JavaScript unit tests for the Mixer maths and the router run in CI.
- The app's own files are served with `Cache-Control: no-cache`, so an upgrade never leaves old scripts in the browser.

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
