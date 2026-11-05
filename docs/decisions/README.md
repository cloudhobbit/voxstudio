# Decision records

Short notes on choices that shape the project: the context, the options, what was chosen and what it costs.
A record is added when a change introduces a dependency, a file format, a public route or a new package
boundary. Records are not edited after the fact; a later record supersedes an earlier one.

| # | Decision | Status |
|---|---|---|
| [0001](0001-front-end-without-a-framework.md) | The front end has no framework and no build step | Accepted |
| [0002](0002-workspace-is-a-folder-of-yaml.md) | The workspace is a folder of YAML files | Accepted |
| [0003](0003-speak-existing-protocols.md) | Offer the OpenAI speech shape and MCP, written in-house | Accepted |
| [0004](0004-conversation-as-an-optional-extra.md) | Conversation mode ships as an optional extra in this repository | Accepted |
| [0005](0005-scorecard-in-its-own-repository.md) | The voice-agent scorecard lives in its own repository | Accepted |
| [0006](0006-one-streaming-synthesis-path.md) | One synthesis path, streamed; the engine is fed sentence by sentence | Accepted |
| [0007](0007-talk-latency-and-the-loop.md) | Talk: what the latency spike found and how the loop is built | Accepted |

Template: **Context** (what forced a choice), **Options** (with the cost of each), **Decision**, **Consequences**
(what gets harder), **Owner** (who to ask, and who may reverse it).
