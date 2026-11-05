# 0006: One synthesis path, streamed; the engine is fed sentence by sentence

Date: 5 Nov 2026 · Status: accepted · Owner: maintainers of `synth.py`, `worker.py` and `fx.py`

**Context.** A long line made the listener wait for all of it. Conversation mode (record 0004) needs sound within
a few hundred milliseconds and needs to stop work the moment the listener interrupts. The first measurement was a
surprise: Kokoro returned a 14-second paragraph as one piece after 1.4 s, because it only cuts text at its own
length limit. Streaming the engine's output as it stood gained nothing.

**Options.**
- Keep whole-line rendering and add a second, streaming code path: two behaviours to keep identical.
- Stream, cutting text at every sentence: earliest sound; the voice loses context at each join.
- **Stream, with the first sentence alone and the rest in longer stretches (up to about 240 characters):** early
  sound and few joins.

**Decision.** One path. A line is planned (cache key, segments for inline pauses and pace), the engine speaks it
piece by piece on the worker thread, the audio runs through one ffmpeg process when pitch, an effect or a space is
set, and the bytes go to the caller while they are collected for the cache. Rendering a line is reading that
stream to its end. Closing the stream cancels the remaining pieces.

**Measured** (M-series laptop, Kokoro, 14 s of speech): first bytes after 350–510 ms, effects included; before, 1.4 s.

**Consequences.** Audio for long lines differs slightly from 0.2 because sentences are now spoken in groups; old
cache entries stay valid and are simply reused. The sentence splitter must know abbreviations and bracketed marks,
and will meet cases it gets wrong. An error after the first bytes cannot change the HTTP status, so a client must
treat a short stream as a failure. Effects with long tails (echo, cave) add up to about 150 ms to the first bytes.
