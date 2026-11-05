# 0001: The front end has no framework and no build step

Date: 29 Oct 2026 · Status: accepted · Owner: maintainers of `src/voxstudio/app`

**Context.** Vox Studio installs with one command into a Python environment. A Node toolchain would add a
second ecosystem to build, audit and release, for an app with seven pages and one user at a time.

**Options.**
- React or similar with a bundler: rich ecosystem; needs a build in CI and in every contributor's setup.
- Alpine.js and a waveform library, vendored: no build; third-party files to carry and license.
- **Plain ES modules and CSS:** nothing to build or vendor; shared pieces are written by hand.

**Decision.** Plain ES modules, one small store and DOM helper, CSS tokens, inline SVG icons, a canvas waveform.

**Consequences.** Editing the app needs only a text editor and a reload. Complex state (a timeline editor, say)
will be harder; if a page outgrows this, that page gets its own record rather than a quiet framework import.
Front-end logic worth testing is kept in small pure modules (`lib/mixmath.js`).
