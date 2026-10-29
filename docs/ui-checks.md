# UI checks before a release

Run `voxstudio serve --engine fake --workspace /tmp/vox-check` and walk through this in a browser, in light and
dark, and once at 375 px wide.

1. **Library:** filters (Female, UK) narrow the grid; search "warm" finds Heart; play a card: the player shows
   the waveform and the card gets a mini waveform; `J`/`K` move the focus ring; `F` favourites; `1`–`5` rate; the
   drawer edits tags and display name; `C` on two cards fills the compare tray and `Space` plays the next one;
   "Pre-render all" shows progress; reload keeps the filters (they are in the URL).
2. **Workbench:** typing re-renders on pause (Hear on change); pitch label reads "−2 st (lower)"; effect and
   space chips change the sound; Download WAV works; Save preset then apply it; Add to project appends a block.
3. **Mixer:** dragging one slider moves the others so the bar stays full; lock pins a share; Save as signature
   with an existing name asks to replace and lists projects using it.
4. **Signatures:** play, rename (a project using it follows), duplicate, delete refused while used.
5. **Pronunciations:** add a word, Before and After differ, save, the entry shows in the table; project scope
   shows "overrides shared"; Scan lists names from the current project.
6. **Projects:** new project from a pasted script; change one block's voice; Render all shows progress and the
   timeline; change one block and render again: only that block re-renders (status badge); Export writes
   WAV/MP3 + SRT + VTT; the exports chips download; delete asks first.
7. **Keyboard only:** Tab reaches every control; `?` opens the shortcut sheet; `Esc` closes drawer, menus, tray.
8. **Offline:** stop the server: the red banner appears; start it: the banner goes.
