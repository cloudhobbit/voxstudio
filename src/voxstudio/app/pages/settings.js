import { api } from "../lib/api.js";
import { icon } from "../lib/icons.js";
import { h, clear } from "../lib/store.js";
import { dialog, toast, copyText } from "../lib/ui.js";
import { refreshHealth, setTitle, store } from "../app.js";

function row(label, value) { return h("tr", {}, h("td.muted", { style: { width: "220px" } }, label), h("td", {}, value)); }

export async function mount(el) {
  setTitle("Settings");
  clear(el);
  const hlth = (await refreshHealth()) || store.get("health");
  if (!hlth) { el.append(h("div.empty", {}, "The server is not reachable.")); return; }
  const caps = hlth.capabilities;
  const engineState = hlth.warm_error ? h("span.badge.danger", {}, "failed") : hlth.languages.length ? h("span.badge.ok", {}, "ready") : h("span.badge.warn", {}, "loading…");
  const inner = h("div.page-inner.stack", {},
    h("div.card", {}, h("h2", {}, "Engine"), h("table.table", {},
      row("Engine", h("span.row", {}, hlth.engine, engineState)),
      row("Languages loaded", hlth.languages.join(", ") || "none yet"),
      hlth.warm_error ? row("Error", h("span", { style: { color: "var(--danger)" } }, hlth.warm_error)) : null,
      row("Queue", String(hlth.queue)))),
    h("div.card", {}, h("h2", {}, "Audio tools"), h("table.table", {},
      row("ffmpeg", caps.ffmpeg ? h("span", {}, h("code", {}, caps.ffmpeg), h("div.muted.small", {}, caps.ffmpeg_version)) : h("span", { style: { color: "var(--danger)" } }, "not found: pitch, effects, spaces and MP3 export need it (brew install ffmpeg / apt install ffmpeg)")),
      row("Pitch shifting", caps.rubberband ? h("span.badge.ok", {}, "rubberband") : h("span", {}, h("span.badge.warn", {}, "fallback"), h("span.muted.small", { style: { marginLeft: "8px" } }, "asetrate + atempo: works everywhere, changes the timbre a little. For the best quality install an ffmpeg build with the rubberband filter (brew install ffmpeg-full)."))),
      row("MP3 export", caps.mp3 ? h("span.badge.ok", {}, "libmp3lame") : h("span.badge.warn", {}, "WAV only")))),
    h("div.card", {}, h("h2", {}, "Workspace"), h("table.table", {},
      row("Folder", h("span.row", {}, h("code", {}, hlth.workspace), h("button.icon-btn.sm", { "aria-label": "Copy path", html: icon("copy", "s"), onclick: () => copyText(hlth.workspace, "Path") }))),
      row("What's in it", h("span.muted", {}, "library.yaml, signatures.yaml, pronunciations.yaml, presets.yaml, projects/, cache/, exports/. Plain YAML: edit by hand or keep it in git.")),
      row("Audio cache", h("span.row", {}, `${hlth.cache.files} files, ${hlth.cache.mb} MB`,
        h("button.btn.sm", { onclick: async () => { if (await dialog({ title: "Clear the audio cache?", body: "Rendered lines are deleted; anything you play again is rendered again. Projects and voices are not affected.", ok: "Clear", danger: true })) { const r = await api.del("/api/cache?older_than_days=0"); toast(`Removed ${r.removed} files`); mount(el); } } }, "Clear"))))),
    h("div.card", {}, h("h2", {}, "About"), h("p", {}, `${hlth.name} ${hlth.version}. Local, free, open source (MIT). `, h("a", { href: "/api/docs", target: "_blank" }, "API docs"), " · ", h("a", { href: "https://github.com/cloudhobbit/voxstudio", target: "_blank", rel: "noopener" }, "GitHub")),
      h("p.muted.small", {}, "Voices by Kokoro-82M (Apache-2.0). Nothing you type or render leaves this machine.")));
  el.append(inner);
}
