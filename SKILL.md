---
name: voxstudio
description: Render speech locally with Vox Studio (a free, offline voice studio on localhost). Use when a task needs narration, a voice-over, an audiobook chapter, a character voice, or captions timed to speech, and the user has Vox Studio installed or wants a local alternative to ElevenLabs.
---

# Vox Studio for agents

Vox Studio is a local HTTP server (`voxstudio`, default `http://127.0.0.1:7860`) with a browser app on top.
Everything the app does is an API call, so you can drive it directly. Full OpenAPI docs: `GET /api/docs`.

## Check it is running

```bash
curl -s localhost:7860/api/health
```
`languages` is empty while the model is still loading (about 10 s after start). If the call fails, start it:
`voxstudio` (or `uvx voxstudio`). Install: `pipx install voxstudio`.

## Speak one line

```bash
curl -s localhost:7860/api/speak -H 'content-type: application/json' \
  -d '{"text": "Hello.", "voice": "af_heart", "speed": 1.0, "pitch": 0, "effect": "none", "space": "dry"}'
```
Returns `{key, url, duration, cached, words}`; fetch `url` for a 24 kHz mono WAV. `words` is `[[word, start, end], …]`.
Identical requests are served from the cache in milliseconds.

- `voice`: a voice id (`GET /api/voices`; `af_heart`, `bf_emma`, `am_michael`, `bm_george` are safe defaults),
  a weighted blend `af_heart:0.6,bf_emma:0.4`, or a saved signature `@name`.
- `pitch`: semitones, −12..12. `effect`: `none radio deep tiny robot echo inner crystal ghost`.
  `space`: `dry room hall cave phone outdoor` (`GET /api/effects` lists them with descriptions).
- `project`: a project slug, to apply that project's pronunciations on top of the shared ones.

## Narrate a script and export with captions

```bash
# 1. create a project; blank lines in `script` become blocks
curl -s localhost:7860/api/projects -H 'content-type: application/json' \
  -d '{"title": "Chapter one", "script": "First paragraph.\n\nSecond paragraph.", "voice": "bm_george"}'
# -> {"slug": "chapter-one", "blocks": [...], "etag": "..."}

# 2. (optional) change a block's voice or settings: PUT the whole blocks list with the etag you got
curl -s -X PUT localhost:7860/api/projects/chapter-one -H 'content-type: application/json' \
  -d '{"blocks": [{"id": "b1", "text": "First paragraph.", "voice": "bm_george"}, {"id": "b2", "text": "Second paragraph.", "voice": "af_heart", "pause": 1.0}], "etag": "<etag>"}'

# 3. export: renders every block (cached ones are instant) and writes the files
curl -s -X POST localhost:7860/api/projects/chapter-one/export -H 'content-type: application/json' \
  -d '{"format": "mp3", "captions": ["srt", "vtt"]}'
# -> {"job_id": "..."};  poll GET /api/jobs/<id> until status is "done"; result.files has urls like /exports/chapter-one/chapter-one.mp3
```
Files land in `<workspace>/exports/<slug>/` (`GET /api/health` reports the workspace path). `format: "wav"`
works on every machine; MP3 needs an ffmpeg with libmp3lame (`capabilities.mp3` in health).

## Fix a pronunciation

```bash
curl -s -X PUT "localhost:7860/api/pronunciations/shared/Chandrayaan" -H 'content-type: application/json' -d '{"say": "Chun-druh-yaan"}'
```
A value between slashes is passed as exact phonemes. Use scope `project` with `"project": "<slug>"` for one project.
`POST /api/pronunciations/scan {"project": "<slug>"}` lists names in a script that may need an entry.

## Make a new voice

```bash
curl -s -X PUT localhost:7860/api/signatures/narrator -H 'content-type: application/json' \
  -d '{"mix": "af_heart:0.6,bf_emma:0.4", "speed": 0.95, "pitch": -1, "note": "warm, a little British"}'
```
Then use `"voice": "@narrator"` anywhere.

## Rules of the road

- Writes return `409` when the YAML file changed on disk since you read it; re-read and retry.
- Validation errors are `422` with a plain-language `detail`; show it to the user rather than guessing.
- The server only answers on localhost and refuses other `Host`/`Origin` values by design.
