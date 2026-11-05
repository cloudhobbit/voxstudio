# 0007: Talk: what the latency spike found and how the loop is built

Date: 5 Nov 2026 · Status: accepted · Owner: Talk maintainers (`src/voxstudio/talk`)

**Context.** Record 0004 said building would start only after a latency spike, with a target of 1.5 s median from
the end of a turn to the first sound, on a laptop, with local models.

**The spike** (Apple M5, 24 GB; Whisper large-v3-turbo through MLX; qwen3:14b through Ollama; Kokoro on CPU):

| Stage | Measured |
|---|---|
| Speech to text, 3 s and 8 s utterances | 390–420 ms (faster-whisper base.en on CPU: 330–480 ms) |
| Language model, first token | 300 ms |
| Language model, first clause / first full sentence (13 tokens per second) | 1.2 s / 2.5 s |
| Voice, first audio for a 50-character piece | 330 ms (370 ms while the model is still writing) |

Waiting for a full sentence would have given about 3.2 s. Two things were also learned the hard way: a second,
18 GB model left loaded made every number worse through memory pressure, and Ollama's thinking models spend their
first tokens on hidden reasoning unless the request says `reasoning_effort: "none"`.

**Decision.**
- **Speak the first clause, not the first sentence.** The first piece leaves at a clause boundary once it has
  three words, at a sentence end, or after fourteen words; later pieces are whole sentences.
- **Start transcribing during the pause that ends a turn.** After 250 ms of quiet the audio so far is sent to
  speech-to-text; if the person speaks again the result is dropped. The wait for the transcript fell from about
  490 ms to about 220 ms.
- **One thread reads the model and speaks.** While a piece is being spoken the model keeps writing into the
  socket, so nothing is lost, and there is one place to cancel.
- **Interruption is a cancel flag checked between tokens and audio chunks,** plus closing the model's connection so
  it stops writing. A new turn waits for the old one to finish its bookkeeping, so the history stays in order.
- **End-of-turn detection by loudness,** with the room's level measured at the start and tracked. No dependency;
  good in a quiet room; a learned detector is on the roadmap.
- **Every stage sits behind a protocol with a fake** (`STT`, `LLM`, the engine), and the loop takes an `emit`
  callable instead of a socket, so all of it is tested without a model or a network.
- **Any OpenAI-compatible model server.** The page shows whether that server is on this machine.

**Result** (same machine, five spoken questions fed at microphone pace through the real loop):

| | Median |
|---|---|
| Wait for the transcript after the turn ends | 220 ms |
| Language model, first piece | 1.5 s |
| Voice, first audio | 510 ms |
| End of turn → first sound | **2.1 s** (worst 2.8 s) |
| Last word → first sound (adds the 0.5 s pause that ends a turn) | 2.6 s |

**The target is missed by 0.6 s**, and the language model is the reason: at 13 tokens per second its first
sentence costs 1.5 s. Speech-to-text and the voice together are about 0.7 s. A model that writes three or four
times faster would bring the median to roughly 1.2 s; that is the next thing to measure, not a result.

**Consequences.** Talk ships marked experimental. The clause-first rule sometimes opens with a short fragment
("Start with fresh,"), which sounds slightly clipped. The loudness detector will false-start on a slammed door and
needs headphones in hands-free mode, because the browser's echo cancellation is not something we control. The
history records what was sent, not what was heard, when a reply is interrupted. One conversation per server at a
time is the practical limit, since there is one voice worker.

**A measuring mistake worth recording.** The first end-to-end run reported 2.3 s for the voice's first audio.
The audio had left on time; the metric was being overwritten by every later piece. A test now pins the wait to
the first sound.
