# Roadmap

Three tracks. Each item says what a user gets and how we will know it worked. Updated at every release;
last update 5 Nov 2026 (0.3.0).

## Studio: narration

| When | Item | Success measure |
|---|---|---|
| **Shipped 0.2** | OpenAI-compatible `/v1/audio/speech` | A tool that only knows the OpenAI speech API works by changing its base URL |
| **Shipped 0.2** | MCP server (`voxstudio mcp`) | An agent exports a captioned narration with no HTTP knowledge |
| **Shipped 0.2** | Script import: Markdown, SRT/VTT, `NAME: line` dialogue | A two-speaker scene becomes blocks with two voices in one step |
| **Shipped 0.2** | Docker image | `docker run -p 7860:7860 …` serves the app |
| **Shipped 0.3** | Streaming first audio | Met: first bytes in 350–510 ms on a 14-second paragraph (M-series laptop, Kokoro), down from 1.4 s |
| **Shipped 0.3** | Pauses, pace and emphasis inside a block | Met: `[pause 0.8]` and `*word*` change the audio and never appear in captions (tested) |
| **Shipped 0.3** | Loudness levelling on export | Met: two blocks 14 dB apart come out within 1 LU of each other (tested) |
| Next (0.4) | Stronger emphasis | A listener picks the emphasised word in a blind A/B more often than chance; today's stress marks are subtle |
| Later | Project cast (named speakers) | Changing one cast entry re-voices every block of that speaker |
| Later | Long scripts: a queue that survives a restart, chapters, M4B | A 3-hour book exports after an interrupted render without starting over |
| Later | A second engine (Piper) | A language Kokoro lacks can be narrated with captions |

## Talk: conversation (optional extra `voxstudio[talk]`)

| When | Item | Success measure |
|---|---|---|
| Next | Latency spike: speech in, speech out, timed | Numbers for each stage on a laptop, published in the decision record |
| Next | The loop: end-of-turn detection, speech-to-text, language model, streamed speech, interruption | Median voice-to-voice under 1.5 s locally; interrupting stops the reply within one audio chunk |
| Later | Talk page and personas | A persona (voice + prompt + tools) holds a five-minute conversation and exports the transcript |

## Check: a scorecard for voice agents (separate repository)

| When | Item | Success measure |
|---|---|---|
| Later | Simulated callers built from Vox Studio voices | Ten scenarios run against the Talk loop and produce a scorecard |
| Later | CI mode | A deliberately worse prompt fails a threshold |

## Not planned

Voice cloning (consent and licence questions need their own decision), accounts or cloud sync, a framework or
build step for the front end.

How decisions get made: [docs/decisions](docs/decisions/README.md). Want to pick something up? Issues labelled
`good first issue` are scoped to an afternoon; [CONTRIBUTING.md](CONTRIBUTING.md) has the map of the code.
