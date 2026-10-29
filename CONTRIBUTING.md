# Contributing

Thanks for looking. Vox Studio is small on purpose; here is how it fits together.

- `src/voxstudio/engines/` speech engines behind one protocol (`base.py`). Kokoro is the first; `fake.py` is
  for tests and demos.
- `api.py` the HTTP API; `worker.py` one thread that owns the model; `cache.py` content-addressed audio;
  `fx.py` the ffmpeg chain; `workspace.py` the YAML stores; `render.py` project assembly and captions.
- `app/` the front end: ES modules and CSS, no build step. `lib/` holds the shared pieces, `pages/` one file per page.

## Working on it

```bash
uv venv && uv pip install -e ".[dev,kokoro]"
.venv/bin/pytest                 # seconds, fake engine
.venv/bin/pytest --slow          # also loads Kokoro once
.venv/bin/ruff check src tests
.venv/bin/voxstudio serve --engine fake --workspace /tmp/vox   # the UI without a model
```

## Adding an engine

Implement `voices()`, `warm()`, `speak()` and `speak_timed()` from `engines/base.py`, register the name in
`engines/__init__.py`, and add its voices to `catalogue.py` (or return them from `voices()` and extend the
catalogue loader). Word timings are optional but captions need them.

## Pull requests

Keep the zero-dependency front end (no frameworks, no CDN). Add a test next to the code you change. Plain words
in UI text and error messages: say what happened and what to do.
