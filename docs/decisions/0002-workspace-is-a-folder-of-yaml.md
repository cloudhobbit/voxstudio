# 0002: The workspace is a folder of YAML files

Date: 29 Oct 2026 · Status: accepted · Owner: maintainers of `workspace.py`

**Context.** Voices, pronunciations and projects are small, hand-editable and personal. People want to keep them
in git, edit them in an editor, and let scripts and agents write them too.

**Options.**
- SQLite: transactions and queries; opaque to people, needs migrations.
- **YAML files in one folder:** readable, diffable, portable; concurrent writers can collide.

**Decision.** YAML files. Every read returns an etag (modification time and size); a write must send the etag it
loaded and is refused with `409` if the file changed, so nothing is silently overwritten.

**Consequences.** No migrations and no lock-in. Two tabs editing one project see a conflict dialog instead of
merging. Rendered audio is not in YAML: it sits in a content-addressed cache that is safe to delete.
