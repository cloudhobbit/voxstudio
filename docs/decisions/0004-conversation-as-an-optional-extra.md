# 0004: Conversation mode ships as an optional extra in this repository

Date: 5 Nov 2026 · Status: accepted · Owner: project lead (packaging); Talk maintainers (the loop)

**Context.** A real-time voice conversation needs speech-to-text, end-of-turn detection, a language model client
and a streaming transport. Narration needs none of them. The project's position is small and one-line to install.

**Options.**
- Inside the core package: one install; core gains heavy dependencies most users never run.
- A separate repository: clean scope; duplicates the app shell and stores, and splits a small community.
- **An optional extra, `voxstudio[talk]`, in this repository:** core unchanged; shared voices, pronunciations,
  effects and shell; the Talk page appears only when the extra is installed.

**Decision.** The optional extra. Speech-to-text, the language model and end-of-turn detection sit behind small
protocols with fake implementations, the same way engines do, so each can be owned and tested alone.

**Consequences.** The README must keep narration first and link to Talk. CI gains a second install profile.
Building starts only after a latency spike; if local models miss the budget, this record is revisited.
