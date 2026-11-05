# 0005: The voice-agent scorecard lives in its own repository

Date: 5 Nov 2026 · Status: accepted · Owner: project lead

**Context.** Vox Studio can produce many distinct speakers in realistic conditions (phone-line sound, speed,
pitch, mispronounced names). That makes it a good source of simulated callers for testing voice agents.

**Options.**
- Inside this repository: shares code directly; its users are teams shipping agents on other stacks who have no
  use for a narration app, and it must test agents that never touch Vox Studio.
- **A separate repository that depends on `voxstudio`:** its own audience, pitch and release rhythm; proves the
  engine works as a library.

**Decision.** A separate repository. Vox Studio stays the voice source; the scorecard owns scenarios, target
adapters, metrics and reports.

**Consequences.** Anything the scorecard needs from Vox Studio must be a public, stable API, which is a useful
pressure. Two repositories to release. Work starts after the Talk loop exists, because it is the reference target.
