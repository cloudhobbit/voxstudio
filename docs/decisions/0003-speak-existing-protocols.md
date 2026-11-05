# 0003: Offer the OpenAI speech shape and MCP, written in-house

Date: 5 Nov 2026 · Status: accepted · Owner: maintainers of `openai_compat.py` and `mcp.py`

**Context.** The quickest way for an existing tool or agent to use Vox Studio is a protocol it already speaks.
Many tools can call `/v1/audio/speech` with a configurable base URL; coding agents can call MCP servers.

**Options.**
- Only our own API plus a skill file: least code; every integration is custom.
- Add the official SDKs as dependencies: less protocol code; two more packages in a tool whose pitch is small.
- **Implement both surfaces directly:** about 300 lines; we own keeping up with the protocols.

**Decision.** `/v1/audio/speech`, `/v1/models` and `/v1/audio/voices` as plain routes over the existing renderer;
`voxstudio mcp` as a hand-written stdio JSON-RPC server that calls the HTTP API (starting a private server when
none is running). OpenAI voice names map to the nearest local voice; ids, blends and `@signatures` also work.

**Consequences.** No new dependencies. We track three MCP protocol revisions and answer with the client's when
we know it. Only tools are offered over MCP (no resources or prompts yet). The compatible routes cover speech
only: no streaming until 0.3, and no transcription.
