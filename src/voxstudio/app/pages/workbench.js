// Workbench: one line × voice × speed × pitch × effect × space, heard in about a second.
import { api, speak } from "../lib/api.js";
import { icon } from "../lib/icons.js";
import { go } from "../lib/router.js";
import { h, clear, debounce, local } from "../lib/store.js";
import { chip, dialog, menu, slider, toast } from "../lib/ui.js";
import { voicePicker } from "../lib/voicepicker.js";
import { player, refreshProjects, setTitle, store, voiceName } from "../app.js";

const MAX = 2000;
let s, els = {}, last = null, presets = [];

function pitchLabel(v) { return v === 0 ? "0 st" : `${v > 0 ? "+" : "−"}${Math.abs(v)} st (${v > 0 ? "higher" : "lower"})`; }
function settings() { return { voice: s.voice, speed: s.speed, pitch: s.pitch, effect: s.effect, space: s.space }; }
function describe(x) { return `${voiceName(x.voice)} · ${x.speed}× · ${pitchLabel(x.pitch)}${x.effect !== "none" ? " · " + x.effect : ""}${x.space !== "dry" ? " · " + x.space : ""}`; }

async function hear() {
  const text = els.text.value.trim();
  if (!text) { els.text.focus(); return; }
  els.hearBtn.disabled = true;
  try {
    const r = await speak({ text, ...settings(), project: store.get("project") || null });
    last = { ...r, text, ...settings() };
    player.play({ id: `wb:${r.key}`, url: r.url, title: voiceName(s.voice), subtitle: text });
    els.status.textContent = r.cached ? "from cache" : `rendered in this session${r.queued_ahead ? ` (${r.queued_ahead} ahead)` : ""}`;
    els.download.href = r.url; els.download.download = `${s.voice.replace(/[^a-z0-9]+/gi, "-")}.wav`; els.download.classList.remove("hidden"); els.download.style.display = "";
    const recent = [{ text, ...settings(), at: Date.now() }, ...local.get("wb.recent", []).filter((x) => describe(x) + x.text !== describe(settings()) + text)].slice(0, 12);
    local.set("wb.recent", recent);
    renderRecent();
  } catch (e) { els.status.textContent = ""; }
  finally { els.hearBtn.disabled = false; }
}
const autoHear = debounce(() => { if (els.auto.checked && els.text.value.trim()) hear(); }, 300);

function renderRecent() {
  clear(els.recent);
  const recent = local.get("wb.recent", []);
  if (!recent.length) return;
  els.recent.append(h("span.label", {}, "Recent"), ...recent.map((r) => chip(describe(r), { title: r.text, onclick: () => { apply(r); els.text.value = r.text; updateCounter(); hear(); } })));
}
function apply(x) {
  s = { ...s, voice: x.voice, speed: +x.speed, pitch: +x.pitch, effect: x.effect, space: x.space };
  els.picker.set(s.voice); els.speed.set(s.speed); els.pitch.set(s.pitch); renderChips(); save();
}
function save() { local.set("wb.settings", settings()); }
function updateCounter() { els.counter.textContent = `${els.text.value.length} / ${MAX}`; previewPron(); }

const previewPron = debounce(async () => {
  const text = els.text.value;
  clear(els.pron);
  if (!text.trim()) return;
  try {
    const { hits } = await api.post("/api/pronunciations/preview", { text, project: store.get("project") || null }, { quiet: true });
    if (!hits.length) { els.pron.append(h("span.muted.small", {}, "No words are respelled. ", h("a", { href: "#/pronunciations" }, "Pronunciations"))); return; }
    const frag = h("div.small", { style: { lineHeight: "20px" } });
    let pos = 0;
    for (const hit of hits) { frag.append(text.slice(pos, hit.start), h("a.hl", { href: `#/pronunciations?word=${encodeURIComponent(hit.word)}`, title: `said as: ${hit.say}` }, hit.word)); pos = hit.end; }
    frag.append(text.slice(pos));
    els.pron.append(h("div.label", {}, `${hits.length} word${hits.length > 1 ? "s" : ""} respelled`), frag);
  } catch { /* offline */ }
}, 250);

function renderChips() {
  clear(els.effects); clear(els.spaces);
  for (const e of store.get("effects")) els.effects.append(chip(e.id, { on: s.effect === e.id, title: e.description, onclick: () => { s.effect = e.id; renderChips(); save(); autoHear(); } }));
  for (const sp of store.get("spaces")) els.spaces.append(chip(sp.id, { on: s.space === sp.id, title: sp.description, onclick: () => { s.space = sp.id; renderChips(); save(); autoHear(); } }));
  const caps = store.get("health")?.capabilities;
  els.fxNote.textContent = caps && !caps.ffmpeg ? "ffmpeg is not installed: pitch, effects and spaces will fail until it is." : "";
}

async function loadPresets() {
  try { presets = (await api.get("/api/presets", { quiet: true })).presets; } catch { presets = []; }
  clear(els.presets);
  els.presets.append(h("option", { value: "" }, presets.length ? "Apply a preset…" : "No presets yet"), ...presets.map((p) => h("option", { value: p.name }, p.name)));
}
async function savePreset() {
  const name = h("input.input", { placeholder: "villain-in-cave", "aria-label": "Preset name", pattern: "[a-z0-9][a-z0-9_\\-]*" });
  const ok = await dialog({ title: "Save as preset", body: `Saves ${describe(settings())} to presets.yaml.`, form: h("div.field", {}, h("label", {}, "Name (lowercase, digits, - and _)"), name), ok: "Save" });
  if (!ok || !name.value.trim()) return;
  try { await api.put(`/api/presets/${encodeURIComponent(name.value.trim().toLowerCase())}`, settings()); toast(`Preset "${name.value.trim()}" saved`, { kind: "ok" }); loadPresets(); } catch { /* toasted */ }
}
async function addToProject() {
  const slug = store.get("project");
  if (!slug) { toast("Pick a project in the top bar first, or create one in Projects", { action: { label: "Projects", fn: () => go("projects") } }); return; }
  const text = els.text.value.trim();
  if (!text) { els.text.focus(); return; }
  try {
    const p = await api.get(`/api/projects/${slug}`);
    const blocks = [...p.blocks, { id: `b${Date.now().toString(36)}`, text, ...settings() }];
    await api.put(`/api/projects/${slug}`, { blocks, etag: p.etag });
    toast(`Added to ${p.title}`, { kind: "ok", action: { label: "Open", fn: () => go(`projects/${slug}`) } });
    refreshProjects();
  } catch { /* toasted */ }
}

export async function mount(root, { query }) {
  setTitle("Workbench");
  const saved = local.get("wb.settings", {});
  s = { voice: query.voice || saved.voice || "af_heart", speed: +(saved.speed ?? 1), pitch: +(saved.pitch ?? 0), effect: saved.effect || "none", space: saved.space || "dry" };
  if (query.voice) { const v = store.get("voices").find((x) => x.id === query.voice); if (v && v.kind === "signature") { s.speed = v.speed || 1; s.pitch = v.pitch || 0; } }
  els.text = h("textarea.textarea", { id: "wb-text", maxlength: MAX, rows: 4, placeholder: "Type a line and press ⌘Enter (or Hear).", oninput: () => { updateCounter(); autoHear(); }, onkeydown: (e) => { if ((e.metaKey || e.ctrlKey) && e.key === "Enter") { e.preventDefault(); hear(); } } });
  els.text.value = query.text || local.get("wb.text", "") || store.get("sampleLines").narration || "";
  els.text.addEventListener("input", () => local.set("wb.text", els.text.value));
  els.counter = h("div.counter");
  els.pron = h("div.stack.tight", { style: { marginTop: "4px" } });
  els.picker = voicePicker({ value: s.voice, id: "wb-voice", onchange: (v) => { s.voice = v; const sig = store.get("voices").find((x) => x.id === v); if (sig && sig.kind === "signature") { els.speed.set(sig.speed || 1); els.pitch.set(sig.pitch || 0); s.speed = sig.speed || 1; s.pitch = sig.pitch || 0; } save(); autoHear(); } });
  els.speed = slider({ label: "Speed", min: 0.5, max: 2, step: 0.05, value: s.speed, def: 1, id: "wb-speed", onchange: (v) => { s.speed = v; save(); autoHear(); } });
  els.pitchLabel = h("span.muted.small", {}, pitchLabel(s.pitch));
  els.pitch = slider({ label: "Pitch", min: -12, max: 12, step: 1, value: s.pitch, def: 0, id: "wb-pitch", oninput: (v) => (els.pitchLabel.textContent = pitchLabel(v)), onchange: (v) => { s.pitch = v; els.pitchLabel.textContent = pitchLabel(v); save(); autoHear(); } });
  els.effects = h("div.chips"); els.spaces = h("div.chips"); els.fxNote = h("div.small", { style: { color: "var(--warn)" } });
  els.hearBtn = h("button.btn.primary", { onclick: hear }, { __html: icon("play") }, "Hear");
  els.auto = h("input", { type: "checkbox", id: "wb-auto", checked: local.get("wb.auto", true), onchange: (e) => local.set("wb.auto", e.target.checked) });
  els.status = h("span.muted.small");
  els.download = h("a.btn", { href: "#", style: { display: "none" } }, { __html: icon("download") }, "Download WAV");
  els.presets = h("select.select", { "aria-label": "Presets", style: { width: "auto" }, onchange: (e) => { const p = presets.find((x) => x.name === e.target.value); if (p) { apply(p); hear(); } e.target.value = ""; } });
  els.recent = h("div.chips", { style: { alignItems: "center" } });
  const projectName = () => { const p = store.get("projects").find((x) => x.slug === store.get("project")); return p ? p.title : null; };
  const addBtn = h("button.btn", { onclick: addToProject }, { __html: icon("plus") }, `Add to project`);
  const page = h("div.page-inner.stack", {},
    h("div.card.stack", {},
      h("div.field", {}, h("label", { for: "wb-text" }, "Text"), els.text, h("div.row.between", {}, els.pron, els.counter)),
      h("div.field", {}, h("label", { for: "wb-voice" }, "Voice"), els.picker),
      els.speed, h("div", {}, els.pitch, h("div", { style: { paddingLeft: "78px" } }, els.pitchLabel)),
      h("div.field", {}, h("span.label", {}, "Effect"), els.effects), h("div.field", {}, h("span.label", {}, "Space"), els.spaces), els.fxNote,
      h("div.row.wrap", {}, els.hearBtn, h("label.row.small", { for: "wb-auto", style: { gap: "4px" } }, els.auto, "Hear on change"), els.status, h("span.grow"),
        h("button.btn", { onclick: () => { const text = els.text.value.trim(); if (!text) return; player.addToTray({ id: `wb:${JSON.stringify([text, settings()])}`, title: describe(settings()), subtitle: text, resolve: async () => ({ url: (await speak({ text, ...settings(), project: store.get("project") || null })).url }) }); toast("Added to Compare", { ms: 1500 }); } }, { __html: icon("compare") }, "Compare"),
        els.download),
      h("div.row.wrap", {}, els.presets, h("button.btn", { onclick: savePreset }, "Save preset"), presets.length ? null : null, h("button.btn.ghost", { onclick: (e) => { if (!presets.length) return toast("No presets saved yet"); menu(e.currentTarget, presets.map((p) => ({ label: `Delete "${p.name}"`, icon: "trash", danger: true, onclick: async () => { await api.del(`/api/presets/${p.name}`); toast(`Preset "${p.name}" deleted`); loadPresets(); } }))); } }, "Manage…"), h("span.grow"), addBtn)),
    h("div.card", {}, els.recent));
  clear(root);
  root.append(page);
  renderChips(); updateCounter(); renderRecent(); loadPresets();
  store.on("project", () => { addBtn.lastChild.textContent = projectName() ? ` Add to ${projectName()}` : " Add to project"; previewPron(); });
  addBtn.lastChild.textContent = projectName() ? ` Add to ${projectName()}` : " Add to project";
  if (query.voice && query.text) hear();
}
