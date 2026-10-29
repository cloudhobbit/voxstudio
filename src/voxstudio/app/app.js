// Boot: load health and voices, wire the shell, start the router.
import { api } from "./lib/api.js";
import { icon } from "./lib/icons.js";
import { createPlayer } from "./lib/player.js";
import { route, start, go } from "./lib/router.js";
import { installShortcuts, SHORTCUTS } from "./lib/shortcuts.js";
import { createStore, h, clear, local } from "./lib/store.js";
import { dialog, closeMenus, toast } from "./lib/ui.js";

export const store = createStore({ voices: [], voicesEtag: null, health: null, project: local.get("project", ""), projects: [], effects: [], spaces: [], sampleLines: {} });
export const player = createPlayer(document.getElementById("player"));
export const drawer = document.getElementById("drawer");

const SECTIONS = [
  ["library", "Library", "library"], ["workbench", "Workbench", "mic"], ["mixer", "Mixer", "sliders"],
  ["signatures", "Signatures", "signature"], ["pronunciations", "Pronunciations", "spell"], ["projects", "Projects", "projects"],
];
const TABS = [["library", "Library", "library"], ["workbench", "Work", "mic"], ["mixer", "Mix", "sliders"], ["projects", "Projects", "projects"], ["settings", "More", "settings"]];

export async function refreshVoices() {
  const r = await api.get("/api/voices", { quiet: true });
  store.set("voicesEtag", r.etag);
  store.set("voices", r.voices);
  return r.voices;
}
export async function refreshProjects() {
  const r = await api.get("/api/projects", { quiet: true });
  store.set("projects", r.projects);
  renderProjectSelect();
  return r.projects;
}
export async function refreshHealth() {
  try { const hlth = await api.get("/api/health", { quiet: true }); store.set("health", hlth); return hlth; } catch { return null; }
}
export const voiceById = (id) => store.get("voices").find((v) => v.id === id);
export const voiceName = (id) => { const v = voiceById(id); return v ? (v.display_name || v.name) : id; };

function renderNav() {
  const nav = document.getElementById("nav");
  clear(nav);
  nav.append(h("div.nav-group", {}, "Voice"));
  for (const [id, label, ic] of SECTIONS) nav.append(h("a", { href: `#/${id}`, "data-route": id }, { __html: icon(ic) }, h("span", {}, label)));
  const bottom = document.getElementById("nav-bottom");
  clear(bottom);
  bottom.append(h("a", { href: "#/settings", "data-route": "settings" }, { __html: icon("settings") }, h("span", {}, "Settings")));
  const tabs = document.getElementById("tabbar");
  clear(tabs);
  for (const [id, label, ic] of TABS) tabs.append(h("a", { href: `#/${id}`, "data-route": id }, { __html: icon(ic) }, label));
}

function renderProjectSelect() {
  const sel = document.getElementById("project-select");
  clear(sel);
  sel.append(h("option", { value: "" }, "No project"));
  for (const p of store.get("projects")) sel.append(h("option", { value: p.slug, selected: p.slug === store.get("project") }, p.title));
  if (store.get("project") && !store.get("projects").some((p) => p.slug === store.get("project"))) { store.set("project", ""); local.set("project", ""); }
  sel.value = store.get("project");
}
document.getElementById("project-select").addEventListener("change", (e) => { store.set("project", e.target.value); local.set("project", e.target.value); });

// theme
const themeBtn = document.getElementById("theme-btn");
function applyTheme(t) { if (t) document.documentElement.dataset.theme = t; else delete document.documentElement.dataset.theme; local.set("theme", t || null); renderThemeBtn(); }
function isDark() { const t = document.documentElement.dataset.theme; return t ? t === "dark" : matchMedia("(prefers-color-scheme: dark)").matches; }
function renderThemeBtn() { themeBtn.innerHTML = icon(isDark() ? "sun" : "moon"); }
themeBtn.addEventListener("click", () => applyTheme(isDark() ? "light" : "dark"));
renderThemeBtn();

// help sheet
const helpBtn = document.getElementById("help-btn");
helpBtn.innerHTML = icon("help");
function openHelp() {
  dialog({ title: "Keyboard shortcuts", body: h("div.shortcuts", {}, SHORTCUTS.flatMap(([k, d]) => [h("span", {}, ...k.split(" ").map((x, i) => [i ? " " : "", h("kbd.kbd", {}, x)])), h("span", {}, d)])), ok: "Close", cancel: null });
}
helpBtn.addEventListener("click", openHelp);

// busy line, offline banner
let busy = 0;
document.addEventListener("vox:busy", (e) => { busy = Math.max(0, busy + e.detail); document.getElementById("progress").classList.toggle("on", busy > 0); });
const banner = document.getElementById("banner");
document.addEventListener("vox:offline", () => { banner.textContent = "Can't reach the server. Start it with:  voxstudio"; banner.classList.add("on"); });
document.addEventListener("vox:online", () => banner.classList.remove("on"));

export function setTitle(text, actions = []) {
  document.getElementById("title").textContent = text;
  document.title = `${text} · Vox Studio`;
  const slot = document.getElementById("topbar-actions");
  clear(slot);
  slot.append(...actions);
}
export function openDrawer(content) { clear(drawer); drawer.append(h("button.icon-btn.close", { "aria-label": "Close", html: icon("x"), onclick: closeDrawer }), content); drawer.classList.add("on"); drawer.querySelector("h2, h1, button:not(.close)")?.focus(); }
export function closeDrawer() { drawer.classList.remove("on"); }

installShortcuts({ player, openHelp,
  openSearch: () => { const s = document.querySelector("#main input[type=search]"); if (s) s.focus(); else go("library"); },
  closeAll: () => { closeMenus(); closeDrawer(); player.closeTray(); const d = document.getElementById("dialog"); if (d.open) d.close(); } });

// pages
import * as library from "./pages/library.js";
import * as workbench from "./pages/workbench.js";
import * as mixer from "./pages/mixer.js";
import * as signatures from "./pages/signatures.js";
import * as pronunciations from "./pages/pronunciations.js";
import * as projects from "./pages/projects.js";
import * as settings from "./pages/settings.js";
import * as kitchen from "./pages/kitchen.js";
for (const [name, page] of Object.entries({ library, workbench, mixer, signatures, pronunciations, projects, settings, "kitchen-sink": kitchen })) route(name, page);
route("404", { mount: (el) => { clear(el); el.append(h("div.empty", {}, "No such page.", h("a", { href: "#/library" }, "Go to the Library"))); setTitle("Not found"); } });

renderNav();
(async () => {
  const hlth = await refreshHealth();
  if (!hlth) return start(document.getElementById("main"));
  const [eff, lines] = await Promise.all([api.get("/api/effects", { quiet: true }), api.get("/api/sample-lines", { quiet: true })]);
  store.set("effects", eff.effects); store.set("spaces", eff.spaces); store.set("sampleLines", lines.lines);
  await Promise.all([refreshVoices(), refreshProjects()]);
  await start(document.getElementById("main"), () => { closeMenus(); closeDrawer(); });
  // keep the engine status fresh while it warms up
  const tick = async () => { const hh = await refreshHealth(); if (hh && (!hh.languages.length || hh.queue)) setTimeout(tick, 1500); };
  if (!hlth.languages.length) tick();
  if (hlth.warm_error) toast(`The engine failed to load: ${hlth.warm_error}`, { kind: "error", ms: 15000 });
})();
