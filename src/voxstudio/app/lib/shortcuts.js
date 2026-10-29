// Global keys. Pages add their own with onKey(); the global ones never fire inside inputs.
const handlers = [];
export function onKey(fn) { handlers.push(fn); return () => handlers.splice(handlers.indexOf(fn), 1); }
const typing = (e) => ["INPUT", "TEXTAREA", "SELECT"].includes(e.target.tagName) || e.target.isContentEditable;

export function installShortcuts({ player, openSearch, openHelp, closeAll }) {
  document.addEventListener("keydown", (e) => {
    if (e.metaKey && e.key.toLowerCase() === "k") { e.preventDefault(); openSearch(); return; }
    if (e.key === "Escape") { closeAll(); e.target.blur && e.target.blur(); return; }
    if (typing(e)) return;
    if (e.key === "/") { e.preventDefault(); openSearch(); return; }
    if (e.key === "?") { e.preventDefault(); openHelp(); return; }
    if (e.key === " " || e.code === "Space") {
      e.preventDefault();
      if (player.isTrayOpen() && player.tray.length) player.nextInTray(); else player.toggle();
      return;
    }
    if (e.key === "ArrowRight" && player.isTrayOpen()) { player.nextInTray(); return; }
    if (e.key === "ArrowLeft" && player.isTrayOpen()) { player.prevInTray(); return; }
    for (const fn of handlers) if (fn(e) === true) { e.preventDefault(); return; }
  });
}

export const SHORTCUTS = [
  ["Space", "Play / pause (next voice when the compare tray is open)"], ["← →", "Previous / next in the compare tray"],
  ["J / K", "Next / previous voice in the list"], ["Enter", "Open the focused voice"], ["F", "Favourite the focused voice"],
  ["C", "Add the focused voice to Compare"], ["1–5", "Rate the focused voice"], ["/ or ⌘K", "Search"], ["?", "This sheet"], ["Esc", "Close panels and menus"],
];
