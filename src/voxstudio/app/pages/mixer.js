// Mixer: blend 2-4 voices with linked sliders, hear each change, save as a signature.
import { api, speak } from "../lib/api.js";
import { icon } from "../lib/icons.js";
import { evenSplit, fromSpec, setShare, toSpec } from "../lib/mixmath.js";
import { go } from "../lib/router.js";
import { h, clear, debounce, local } from "../lib/store.js";
import { chip, dialog, gradeBadge, iconBtn, menu, slider, toast } from "../lib/ui.js";
import { voicePicker } from "../lib/voicepicker.js";
import { player, refreshVoices, setTitle, store, voiceName } from "../app.js";

const COLOURS = ["var(--accent)", "var(--ok)", "var(--warn)", "var(--danger)"];
let s, els = {};

function lineText() { const lines = store.get("sampleLines"); return s.line === "custom" ? (s.text || lines.narration) : (lines[s.line] || lines.narration); }
function spec() { return toSpec(s.parts); }
function stockVoices() { return store.get("voices").filter((v) => v.kind === "stock"); }
function describe() { return s.parts.map((p) => `${Math.round(p.w * 100)}% ${voiceName(p.id)}`).join(" + "); }
function persist() { local.set("mixer.state", { parts: s.parts, line: s.line, text: s.text, speed: s.speed, pitch: s.pitch }); }

async function hear() {
  const text = lineText();
  if (!s.parts.length) return;
  try {
    const r = await speak({ text, voice: spec(), speed: s.speed, pitch: s.pitch });
    player.play({ id: `mix:${r.key}`, url: r.url, title: describe(), subtitle: text });
    pushHistory();
  } catch { /* toasted */ }
}
const hearSoon = debounce(hear, 350);

function pushHistory() {
  const sp = spec();
  local.set("mixer.history", [sp, ...local.get("mixer.history", []).filter((x) => x !== sp)].slice(0, 10));
  renderHistory();
}
function renderHistory() {
  clear(els.history);
  const hist = local.get("mixer.history", []);
  if (!hist.length) { els.history.append(h("span.muted.small", {}, "Mixes you hear show up here, so you can go back to one you liked.")); return; }
  els.history.append(h("span.label", {}, "History"), ...hist.map((sp) => chip(sp.split(",").map((x) => { const [id, w] = x.split(":"); return `${w ? Math.round(w * 100) + "% " : ""}${voiceName(id)}`; }).join(" + "), { title: sp, onclick: () => { s.parts = fromSpec(sp); render(); hear(); } })));
}

function paint() {
  clear(els.bar);
  s.parts.forEach((p, i) => els.bar.append(h("span", { style: { width: `${p.w * 100}%`, background: COLOURS[i] }, title: `${Math.round(p.w * 100)}% ${voiceName(p.id)}` })));
  els.spec.textContent = spec();
  s.parts.forEach((p, i) => {
    const r = els.rows.querySelector(`#mix-${i}`);
    if (r && document.activeElement !== r) { r.value = Math.round(p.w * 100); r.parentElement.querySelector(".val input").value = Math.round(p.w * 100); }
  });
}

function render() {
  clear(els.rows);
  s.parts.forEach((p, i) => {
    const v = store.get("voices").find((x) => x.id === p.id) || { name: p.id };
    const row = slider({ label: "", min: 0, max: 100, step: 1, value: Math.round(p.w * 100), def: Math.round(100 / s.parts.length), id: `mix-${i}`,
      oninput: (val) => { s.parts = setShare(s.parts, i, val / 100); paint(); },
      onchange: (val) => { s.parts = setShare(s.parts, i, val / 100); render(); hearSoon(); } });
    row.querySelector("label").replaceWith(h("div.row", { style: { gap: "6px", minWidth: 0 } },
      h("span", { style: { width: "10px", height: "10px", borderRadius: "50%", background: COLOURS[i], flex: "none" } }),
      h("b", { style: { overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" } }, v.display_name || v.name), v.grade ? gradeBadge(v.grade) : null));
    row.style.gridTemplateColumns = "150px 1fr 56px 28px 28px 28px";
    row.querySelector("button").replaceWith(iconBtn(p.locked ? "lock" : "unlock", { label: p.locked ? "Unlock share" : "Lock share", on: p.locked, cls: "sm", onclick: () => { s.parts[i].locked = !s.parts[i].locked; render(); } }));
    row.append(
      iconBtn("mic", { label: `Hear ${v.name} alone`, cls: "sm", onclick: async () => { const r = await speak({ text: lineText(), voice: p.id }); player.play({ id: p.id, url: r.url, title: v.display_name || v.name, subtitle: lineText() }); } }),
      iconBtn("x", { label: `Remove ${v.name}`, cls: "sm", onclick: () => { if (s.parts.length <= 1) return toast("Keep at least one voice"); s.parts.splice(i, 1); s.parts = evenSplit(s.parts); render(); hearSoon(); } }));
    els.rows.append(row);
  });
  paint();
  els.add.style.display = s.parts.length >= 4 ? "none" : "";
  persist();
}

async function addVoice() {
  const first = stockVoices().find((v) => !s.parts.some((p) => p.id === v.id));
  const picker = voicePicker({ value: first ? first.id : "af_heart", id: "mix-add", allowCustom: false });
  const ok = await dialog({ title: "Add a voice to the mix", body: "Stock voices only: a signature is itself a mix.", form: h("div.field", {}, h("label", { for: "mix-add" }, "Voice"), picker), ok: "Add" });
  if (!ok) return;
  const id = picker.get();
  const v = store.get("voices").find((x) => x.id === id);
  if (!v || v.kind !== "stock") return toast("Pick a stock voice", { kind: "error" });
  if (s.parts.some((p) => p.id === id)) return toast(`${v.name} is already in the mix`);
  s.parts.push({ id, w: 0, locked: false });
  s.parts = evenSplit(s.parts);
  render(); hearSoon();
}

async function save() {
  const name = h("input.input", { placeholder: "narrator", "aria-label": "Signature name", pattern: "[a-z0-9][a-z0-9_\\-]*" });
  const note = h("input.input", { placeholder: "warm, slightly British polish", "aria-label": "Note" });
  const ok = await dialog({ title: "Save as signature voice",
    body: h("p.muted", {}, describe(), h("br"), `Default speed ${s.speed}×, pitch ${s.pitch} st. Use it anywhere as `, h("code", {}, "@name"), "."),
    form: h("div.stack.tight", {}, h("div.field", {}, h("label", {}, "Name (lowercase, digits, - and _)"), name), h("div.field", {}, h("label", {}, "Note (optional)"), note)), ok: "Save" });
  if (!ok) return;
  const slug = name.value.trim().toLowerCase();
  if (!slug) return;
  const body = { mix: spec(), speed: s.speed, pitch: s.pitch, note: note.value.trim() };
  try {
    await api.put(`/api/signatures/${encodeURIComponent(slug)}`, body, { quiet: true });
  } catch (e) {
    if (e.status === 422 && /already exists/.test(e.message)) {
      const existing = (await api.get("/api/signatures")).signatures.find((x) => x.name === slug);
      const used = existing && existing.used_in.length ? ` It is used by ${existing.used_in.join(", ")}: those will use the new mix on their next render.` : "";
      if (!(await dialog({ title: `Replace @${slug}?`, body: `A signature with this name exists (${existing ? existing.described : ""}).${used}`, ok: "Replace", danger: true }))) return;
      try { await api.put(`/api/signatures/${encodeURIComponent(slug)}`, { ...body, overwrite: true }); } catch { return; }
    } else { toast(e.message, { kind: "error" }); return; }
  }
  toast(`Saved @${slug} to signatures.yaml`, { kind: "ok", action: { label: "Signatures", fn: () => go("signatures") } });
  await refreshVoices();
}

export async function mount(root, { query }) {
  setTitle("Mixer");
  const saved = local.get("mixer.state", null);
  s = { parts: [{ id: "af_heart", w: 0.6, locked: false }, { id: "bf_emma", w: 0.4, locked: false }], line: local.get("library.line", "narration"), text: local.get("library.text", ""), speed: 1, pitch: 0, ...(saved || {}) };
  s.parts = s.parts.filter((p) => store.get("voices").some((v) => v.id === p.id));
  if (!s.parts.length) s.parts = evenSplit([{ id: "af_heart", w: 1 }, { id: "bf_emma", w: 1 }]);
  if (s.line === "custom" && !s.text) s.line = "narration";
  if (query.with) {
    const ids = query.with.split(",").filter((id) => store.get("voices").some((v) => v.id === id && v.kind === "stock"));
    if (ids.length) {
      s.parts = evenSplit(ids.map((id) => ({ id, w: 1 })));
      if (s.parts.length === 1) { const other = stockVoices().find((v) => v.id !== ids[0]); s.parts = evenSplit([...s.parts, { id: other.id, w: 1 }]); }
    }
  }
  if (query.from) { const v = store.get("voices").find((x) => x.id === query.from); if (v && v.mix) { s.parts = fromSpec(v.mix); s.speed = v.speed || 1; s.pitch = v.pitch || 0; } }
  const lines = store.get("sampleLines");
  els.rows = h("div.stack.tight");
  els.bar = h("div.share-bar", { "aria-hidden": "true" });
  els.spec = h("code.muted");
  els.add = h("button.btn", { onclick: addVoice }, { __html: icon("plus") }, "Add voice");
  els.history = h("div.chips", { style: { alignItems: "center" } });
  const customText = h("input.input", { placeholder: "Your own line, Enter to apply", "aria-label": "Custom line", value: s.text, style: { display: s.line === "custom" ? "" : "none", flex: 1, minWidth: "200px" }, onkeydown: (e) => { if (e.key === "Enter") { s.text = e.target.value.trim(); persist(); hear(); } } });
  const lineSel = h("select.select", { "aria-label": "Line", style: { width: "auto" }, onchange: (e) => { s.line = e.target.value; customText.style.display = s.line === "custom" ? "" : "none"; persist(); if (s.line !== "custom") hear(); else customText.focus(); } },
    Object.keys(lines).map((k) => h("option", { value: k, selected: s.line === k }, k[0].toUpperCase() + k.slice(1))), h("option", { value: "custom", selected: s.line === "custom" }, "Custom…"));
  const speedEl = slider({ label: "Speed", min: 0.5, max: 2, step: 0.05, value: s.speed, def: 1, id: "mix-speed", onchange: (v) => { s.speed = v; persist(); hearSoon(); } });
  const pitchEl = slider({ label: "Pitch", min: -12, max: 12, step: 1, value: s.pitch, def: 0, id: "mix-pitch", onchange: (v) => { s.pitch = v; persist(); hearSoon(); } });
  const startFrom = h("button.btn.ghost", { onclick: (e) => {
    const sigs = store.get("voices").filter((v) => v.kind !== "stock");
    if (!sigs.length) return toast("No signatures or blends yet");
    menu(e.currentTarget, sigs.map((v) => ({ label: `${v.kind === "signature" ? "@" : ""}${v.name}`, icon: v.kind === "signature" ? "signature" : "sliders",
      onclick: () => { s.parts = fromSpec(v.mix); if (v.kind === "signature") { s.speed = v.speed || 1; s.pitch = v.pitch || 0; speedEl.set(s.speed); pitchEl.set(s.pitch); } render(); hear(); } })));
  } }, "Start from…");
  const page = h("div.page-inner.stack", {},
    h("div.card.stack", {},
      h("div.row.wrap", {}, h("span.label", {}, "Line"), lineSel, customText, h("span.grow"), startFrom, h("button.btn.primary", { onclick: hear }, { __html: icon("play") }, "Hear")),
      h("div", {}, h("div.label", { style: { marginBottom: "6px" } }, "Voices in the mix"), els.rows),
      h("div.row.wrap", {}, els.add, h("button.btn.ghost", { onclick: () => { s.parts = evenSplit(s.parts); render(); hearSoon(); } }, "Even split"), h("button.btn.ghost", { onclick: () => { s.parts = s.parts.map((p) => ({ ...p, locked: false })); render(); } }, "Unlock all")),
      els.bar,
      h("div.row", {}, h("span.label", {}, "Spec"), els.spec, iconBtn("copy", { label: "Copy spec", cls: "sm", onclick: () => navigator.clipboard?.writeText(spec()).then(() => toast("Spec copied", { ms: 1500 })) })),
      h("div.label", {}, "Defaults for the saved voice"), speedEl, pitchEl,
      h("div.row.wrap", {}, h("button.btn.primary", { onclick: save }, { __html: icon("signature") }, "Save as signature"),
        h("button.btn", { onclick: () => { const text = lineText(); player.addToTray({ id: `mix:${spec()}`, title: describe(), subtitle: text, resolve: async () => ({ url: (await speak({ text, voice: spec(), speed: s.speed, pitch: s.pitch })).url }) }); toast("Added to Compare", { ms: 1500 }); } }, { __html: icon("compare") }, "Compare"),
        h("button.btn.ghost", { onclick: () => go(`workbench?voice=${encodeURIComponent(spec())}&text=${encodeURIComponent(lineText())}`) }, "Open in Workbench"))),
    h("div.card", {}, els.history));
  clear(root); root.append(page);
  render(); renderHistory();
  if (query.with || query.from) hear();
}
