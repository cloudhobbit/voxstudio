// Projects: a script as blocks, each with its own voice and settings. Render, then export audio with captions.
import { api, speak } from "../lib/api.js";
import { icon } from "../lib/icons.js";
import { go } from "../lib/router.js";
import { h, clear, debounce, fmtTime, local } from "../lib/store.js";
import { chip, dialog, empty, iconBtn, menu, popover, slider, toast } from "../lib/ui.js";
import { voicePicker } from "../lib/voicepicker.js";
import { player, refreshProjects, refreshVoices, setTitle, store, voiceName } from "../app.js";

const COLOURS = ["#4F46E5", "#15803D", "#B45309", "#0F766E", "#B91C1C", "#6B6B76", "#7C3AED", "#0369A1"];
let p = null, els = {}, dirty = false, saving = false, root;

// ---------- list ----------
async function listProjects(el) {
  setTitle("Projects", [h("button.btn.primary", { onclick: () => createProject() }, { __html: icon("plus") }, "New project")]);
  clear(el);
  const projects = await refreshProjects();
  if (!projects.length) { el.append(h("div.page-inner", {}, empty("No projects yet. A project is a script in blocks, each read by a voice of your choice, exported as audio with captions.", { icon: "projects", action: h("button.btn.primary", { onclick: () => createProject() }, "New project") }))); return; }
  el.append(h("div.page-inner", {}, h("div.grid", {}, projects.map((pr) => h("article.card.vcard", { tabindex: 0, onclick: () => go(`projects/${pr.slug}`), onkeydown: (e) => { if (e.key === "Enter") go(`projects/${pr.slug}`); } },
    h("div.head", {}, h("span.name", {}, pr.title), h("span.badge", {}, `${pr.blocks} block${pr.blocks === 1 ? "" : "s"}`)),
    h("div.meta", {}, h("span", {}, `${pr.words} words`), pr.created ? ["·", h("span", {}, pr.created)] : null),
    h("div.actions", { onclick: (e) => e.stopPropagation() }, h("span.grow"), iconBtn("more", { label: "More", onclick: (e) => menu(e.currentTarget, [
      { label: "Open", icon: "projects", onclick: () => go(`projects/${pr.slug}`) }, "-",
      { label: "Delete", icon: "trash", danger: true, onclick: async () => { if (await dialog({ title: `Delete "${pr.title}"?`, body: "The script and its exports are deleted. Rendered audio stays in the cache.", ok: "Delete", danger: true })) { await api.del(`/api/projects/${pr.slug}`); toast("Deleted"); listProjects(el); } } }]) })))))));
}

async function createProject() {
  const title = h("input.input", { placeholder: "Chapter one", "aria-label": "Title", required: true });
  const script = h("textarea.textarea", { rows: 8, placeholder: "Paste your script. Blank lines separate blocks; each block can have its own voice.", "aria-label": "Script" });
  const picker = voicePicker({ value: local.get("projects.voice", "af_heart"), id: "np-voice" });
  const ok = await dialog({ title: "New project", form: h("div.stack.tight", {}, h("div.field", {}, h("label", {}, "Title"), title), h("div.field", {}, h("label", {}, "Script (optional)"), script), h("div.field", {}, h("label", { for: "np-voice" }, "Voice for every block"), picker)), ok: "Create" });
  if (!ok || !title.value.trim()) return;
  local.set("projects.voice", picker.get());
  try { const r = await api.post("/api/projects", { title: title.value.trim(), script: script.value, voice: picker.get() }); store.set("project", r.slug); local.set("project", r.slug); await refreshProjects(); go(`projects/${r.slug}`); } catch { /* toasted */ }
}

// ---------- editor ----------
function blockVoiceColour(voice) { const ids = [...new Set(p.blocks.map((b) => b.voice))]; return COLOURS[ids.indexOf(voice) % COLOURS.length]; }
function statusOf(id) { return (p.status || []).find((s) => s.id === id) || {}; }
function markDirty() { dirty = true; els.saveState.textContent = "Unsaved changes"; els.saveState.className = "small"; els.saveState.style.color = "var(--warn)"; saveSoon(); }
const saveSoon = debounce(() => save(), 800);

async function save() {
  if (!dirty || saving) return;
  saving = true;
  try {
    const r = await api.put(`/api/projects/${p.slug}`, { title: p.title, blocks: p.blocks.map(({ id, text, voice, speed, pitch, effect, space, pause }) => ({ id, text, voice, speed, pitch, effect, space, pause })), pronunciations: p.pronunciations, etag: p.etag }, { quiet: true });
    Object.assign(p, r); dirty = false;
    els.saveState.textContent = "Saved"; els.saveState.style.color = "var(--muted)";
    renderStatus();
  } catch (e) {
    if (e.status === 409) {
      const reload = await dialog({ title: "Changed on disk", body: "project.yaml was edited outside the app since you opened it. Reload it (your unsaved edits here are lost) or overwrite it with this version?", ok: "Reload", cancel: "Overwrite" });
      if (reload) { dirty = false; return openProject(root, p.slug); }
      p.etag = e.body.etag || null; p.etag = null; saving = false; return save();
    }
    els.saveState.textContent = e.message; els.saveState.style.color = "var(--danger)";
  } finally { saving = false; }
}

function renderStatus() {
  const total = p.duration;
  els.duration.textContent = total ? `${fmtTime(total)} total` : `${p.blocks.length} block${p.blocks.length === 1 ? "" : "s"}, not rendered yet`;
  clear(els.timeline);
  if (p.status && p.status.every((s) => s.duration)) {
    const sum = p.status.reduce((a, s, i) => a + s.duration + p.blocks[i].pause, 0) || 1;
    p.blocks.forEach((b, i) => els.timeline.append(h("span", { title: `${i + 1}. ${voiceName(b.voice)} · ${fmtTime(statusOf(b.id).duration)}`, style: { width: `${((statusOf(b.id).duration + b.pause) / sum) * 100}%`, background: blockVoiceColour(b.voice), opacity: .85 } })));
  }
  p.blocks.forEach((b) => { const st = statusOf(b.id); const badge = els.main.querySelector(`[data-block="${b.id}"] .status`); if (badge) { badge.className = "badge status " + (st.error ? "danger" : st.cached ? "ok" : ""); badge.textContent = st.error ? "error" : st.cached ? fmtTime(st.duration) : "not rendered"; badge.title = st.error || ""; } });
  renderExports();
}

function renderExports() {
  clear(els.exports);
  if (!p.exports || !p.exports.length) { els.exports.append(h("span.muted.small", {}, "Nothing exported yet.")); return; }
  els.exports.append(...p.exports.map((f) => h("a.chip", { href: f.url, download: f.name, title: `${(f.bytes / 1024).toFixed(0)} KB` }, { __html: icon(f.name.endsWith(".srt") || f.name.endsWith(".vtt") || f.name.endsWith(".json") ? "copy" : "download", "s") }, f.name)));
}

async function playBlock(b) {
  try {
    const r = await speak({ text: b.text, voice: b.voice, speed: b.speed, pitch: b.pitch, effect: b.effect, space: b.space, project: p.slug });
    player.play({ id: `blk:${b.id}`, url: r.url, title: `${voiceName(b.voice)} · block ${p.blocks.indexOf(b) + 1}`, subtitle: b.text });
    const st = statusOf(b.id); if (st) { st.cached = true; st.duration = r.duration; st.url = r.url; }
    renderStatus();
  } catch { /* toasted */ }
}

function settingsPopover(anchor, b) {
  const sp = slider({ label: "Speed", min: 0.5, max: 2, step: 0.05, value: b.speed, def: 1, id: `bs-${b.id}`, onchange: (v) => { b.speed = v; markDirty(); } });
  const pi = slider({ label: "Pitch", min: -12, max: 12, step: 1, value: b.pitch, def: 0, id: `bp-${b.id}`, onchange: (v) => { b.pitch = v; markDirty(); } });
  const pa = slider({ label: "Pause after", min: 0, max: 5, step: 0.1, value: b.pause, def: 0.5, id: `bpa-${b.id}`, onchange: (v) => { b.pause = v; markDirty(); } });
  const fx = h("div.chips"), sps = h("div.chips");
  const paint = () => { clear(fx); clear(sps); for (const e of store.get("effects")) fx.append(chip(e.id, { on: b.effect === e.id, title: e.description, onclick: () => { b.effect = e.id; paint(); markDirty(); } })); for (const s of store.get("spaces")) sps.append(chip(s.id, { on: b.space === s.id, title: s.description, onclick: () => { b.space = s.id; paint(); markDirty(); } })); };
  paint();
  popover(anchor, h("div.stack.tight", { style: { width: "360px", maxWidth: "calc(100vw - 32px)" } }, h("b", {}, `Block ${p.blocks.indexOf(b) + 1} settings`), sp, pi, pa, h("div.label", {}, "Effect"), fx, h("div.label", {}, "Space"), sps,
    h("div.row", {}, h("button.btn.sm", { onclick: () => playBlock(b) }, { __html: icon("play", "s") }, "Hear"), h("button.btn.sm.ghost", { onclick: () => { p.blocks.forEach((o) => { o.speed = b.speed; o.pitch = b.pitch; o.effect = b.effect; o.space = b.space; }); markDirty(); toast("Applied to every block"); } }, "Apply to all blocks"))));
}

function blockEl(b, i) {
  const ta = h("textarea.textarea", { rows: 2, "aria-label": `Block ${i + 1} text`, style: { minHeight: "56px" }, oninput: () => { b.text = ta.value; autosize(ta); markDirty(); } }, b.text);
  const picker = voicePicker({ value: b.voice, id: `bv-${b.id}`, onchange: (v) => { b.voice = v; markDirty(); renderBlocks(); } });
  picker.style.width = "200px";
  const st = statusOf(b.id);
  const el = h("div.card", { "data-block": b.id, style: { borderLeft: `3px solid ${blockVoiceColour(b.voice)}`, padding: "10px 12px" } },
    h("div.row.wrap", { style: { marginBottom: "6px" } },
      h("span.muted.small.mono", { style: { width: "24px" } }, String(i + 1)), picker,
      h("span.badge.status" + (st.error ? ".danger" : st.cached ? ".ok" : ""), { title: st.error || "" }, st.error ? "error" : st.cached ? fmtTime(st.duration) : "not rendered"),
      h("span.muted.small", {}, [b.speed !== 1 ? `${b.speed}×` : null, b.pitch ? `${b.pitch > 0 ? "+" : ""}${b.pitch} st` : null, b.effect !== "none" ? b.effect : null, b.space !== "dry" ? b.space : null, b.pause !== 0.5 ? `pause ${b.pause}s` : null].filter(Boolean).join(" · ")),
      h("span.grow"),
      iconBtn("play", { label: "Hear this block", cls: "sm", onclick: () => playBlock(b) }),
      iconBtn("sliders", { label: "Block settings", cls: "sm", onclick: (e) => settingsPopover(e.currentTarget, b) }),
      iconBtn("up", { label: "Move up", cls: "sm", onclick: () => { if (i > 0) { p.blocks.splice(i - 1, 0, p.blocks.splice(i, 1)[0]); markDirty(); renderBlocks(); } } }),
      iconBtn("down", { label: "Move down", cls: "sm", onclick: () => { if (i < p.blocks.length - 1) { p.blocks.splice(i + 1, 0, p.blocks.splice(i, 1)[0]); markDirty(); renderBlocks(); } } }),
      iconBtn("more", { label: "More", cls: "sm", onclick: (e) => menu(e.currentTarget, [
        { label: "Split at cursor", icon: "split", onclick: () => { const at = ta.selectionStart; if (!at || at >= ta.value.length) return toast("Put the cursor where the block should split"); const a = ta.value.slice(0, at).trim(), c = ta.value.slice(at).trim(); if (!a || !c) return; b.text = a; p.blocks.splice(i + 1, 0, { ...b, id: newId(), text: c }); markDirty(); renderBlocks(); } },
        { label: "Duplicate", icon: "copy", onclick: () => { p.blocks.splice(i + 1, 0, { ...b, id: newId() }); markDirty(); renderBlocks(); } },
        { label: "Open in Workbench", icon: "mic", onclick: () => go(`workbench?voice=${encodeURIComponent(b.voice)}&text=${encodeURIComponent(b.text)}`) }, "-",
        { label: "Delete block", icon: "trash", danger: true, onclick: () => { p.blocks.splice(i, 1); markDirty(); renderBlocks(); } }]) })),
    ta);
  requestAnimationFrame(() => autosize(ta));
  return el;
}
const newId = () => `b${Date.now().toString(36)}${Math.floor(Math.random() * 1e3)}`;
function autosize(ta) { ta.style.height = "auto"; ta.style.height = `${Math.max(56, ta.scrollHeight + 2)}px`; }

function renderBlocks() {
  clear(els.blocks);
  if (!p.blocks.length) els.blocks.append(empty("No blocks yet. Add one, or paste a script.", { icon: "projects" }));
  p.blocks.forEach((b, i) => els.blocks.append(blockEl(b, i)));
  renderStatus();
}

async function renderAll() {
  await save();
  if (!p.blocks.length) return toast("Add a block first");
  els.renderBtn.disabled = true;
  const bar = h("div.bar", {}, h("span", { style: { width: "0%" } })), label = h("span.small.muted", {}, "Rendering…");
  clear(els.progress); els.progress.append(h("div.row", { style: { flex: 1 } }, label, h("div", { style: { flex: 1 } }, bar)));
  try {
    const { job_id } = await api.post(`/api/projects/${p.slug}/render`);
    const job = await api.job(job_id, (j) => { label.textContent = `Rendering ${j.done} of ${j.total}`; bar.firstChild.style.width = `${(100 * j.done) / j.total}%`; });
    clear(els.progress);
    if (job.status === "failed") throw new Error(job.error);
    Object.assign(p, await api.get(`/api/projects/${p.slug}`));
    renderBlocks();
    toast(job.failed.length ? `${job.failed.length} block(s) failed: ${job.failed[0].error}` : `Rendered: ${fmtTime(job.result.duration)}`, { kind: job.failed.length ? "error" : "ok" });
  } catch (e) { clear(els.progress); toast(e.message, { kind: "error" }); }
  finally { els.renderBtn.disabled = false; }
}

async function exportProject() {
  await save();
  const caps = store.get("health")?.capabilities || {};
  const fmt = h("select.select", { "aria-label": "Format" }, h("option", { value: "wav" }, "WAV (lossless)"), caps.mp3 ? h("option", { value: "mp3", selected: true }, "MP3") : h("option", { value: "mp3", disabled: true }, "MP3 (needs ffmpeg with libmp3lame)"));
  const srt = h("input", { type: "checkbox", id: "ex-srt", checked: true }), vtt = h("input", { type: "checkbox", id: "ex-vtt", checked: true });
  const ok = await dialog({ title: "Export", body: "Blocks that are not rendered yet are rendered first. Captions come from the engine's word timings and keep the original spelling.",
    form: h("div.stack.tight", {}, h("div.field", {}, h("label", {}, "Audio"), fmt), h("label.row", { for: "ex-srt" }, srt, "SRT captions"), h("label.row", { for: "ex-vtt" }, vtt, "WebVTT captions")), ok: "Export" });
  if (!ok) return;
  const bar = h("div.bar", {}, h("span", { style: { width: "0%" } })), label = h("span.small.muted", {}, "Exporting…");
  clear(els.progress); els.progress.append(h("div.row", { style: { flex: 1 } }, label, h("div", { style: { flex: 1 } }, bar)));
  try {
    const { job_id } = await api.post(`/api/projects/${p.slug}/export`, { format: fmt.value, captions: [srt.checked && "srt", vtt.checked && "vtt"].filter(Boolean) });
    const job = await api.job(job_id, (j) => { label.textContent = `Rendering ${j.done} of ${j.total}`; bar.firstChild.style.width = `${(100 * j.done) / j.total}%`; });
    clear(els.progress);
    if (job.status === "failed") throw new Error(job.error);
    Object.assign(p, await api.get(`/api/projects/${p.slug}`));
    renderBlocks();
    const audio = job.result.files.find((f) => /\.(wav|mp3)$/.test(f.name));
    toast(`Exported ${fmtTime(job.result.duration)} with ${job.result.cues} caption cues`, { kind: "ok", action: audio ? { label: "Play", fn: () => player.play({ id: `export:${p.slug}`, url: audio.url, title: p.title, subtitle: "exported" }) } : null });
  } catch (e) { clear(els.progress); toast(e.message, { kind: "error", ms: 8000 }); }
}

async function pasteScript() {
  const ta = h("textarea.textarea", { rows: 10, placeholder: "Blank lines separate blocks.", "aria-label": "Script" });
  const picker = voicePicker({ value: p.blocks.at(-1)?.voice || "af_heart", id: "ps-voice" });
  if (!(await dialog({ title: "Paste a script", form: h("div.stack.tight", {}, ta, h("div.field", {}, h("label", { for: "ps-voice" }, "Voice for the new blocks"), picker)), ok: "Add blocks" }))) return;
  const paras = ta.value.replace(/\r/g, "").split(/\n\s*\n/).map((x) => x.replace(/\s+/g, " ").trim()).filter(Boolean);
  if (!paras.length) return;
  const last = p.blocks.at(-1) || { speed: 1, pitch: 0, effect: "none", space: "dry", pause: 0.5 };
  for (const text of paras) p.blocks.push({ id: newId(), text, voice: picker.get(), speed: last.speed, pitch: last.pitch, effect: last.effect, space: last.space, pause: last.pause });
  markDirty(); renderBlocks();
}

async function openProject(el, slug) {
  clear(el);
  try { p = await api.get(`/api/projects/${slug}`); } catch (e) { if (e.status === 404) go("projects"); return; }
  store.set("project", slug); local.set("project", slug); document.getElementById("project-select").value = slug;
  dirty = false;
  const title = h("input.input", { value: p.title, "aria-label": "Project title", style: { fontWeight: 600, fontSize: "16px", maxWidth: "420px" }, onchange: () => { p.title = title.value.trim() || p.title; markDirty(); setTitle(p.title, actions()); } });
  els.saveState = h("span.small.muted", {}, "Saved");
  els.duration = h("span.muted.small");
  els.timeline = h("div.share-bar", { style: { height: "14px" }, "aria-hidden": "true" });
  els.blocks = h("div.stack.tight");
  els.progress = h("div");
  els.exports = h("div.chips");
  els.renderBtn = h("button.btn", { onclick: renderAll }, { __html: icon("refresh") }, "Render all");
  const actions = () => [els.renderBtn, h("button.btn.primary", { onclick: exportProject }, { __html: icon("download") }, "Export")];
  setTitle(p.title, actions());
  els.main = h("div.page-inner.stack", {},
    h("div.card.stack.tight", {},
      h("div.row.wrap", {}, title, els.saveState, h("span.grow"), els.duration),
      els.timeline, els.progress,
      h("div.row.wrap", {}, h("button.btn.sm", { onclick: () => { const last = p.blocks.at(-1) || { voice: local.get("projects.voice", "af_heart"), speed: 1, pitch: 0, effect: "none", space: "dry", pause: 0.5 }; p.blocks.push({ ...last, id: newId(), text: "" }); markDirty(); renderBlocks(); els.blocks.lastChild.querySelector("textarea").focus(); } }, { __html: icon("plus", "s") }, "Add block"),
        h("button.btn.sm", { onclick: pasteScript }, "Paste script…"), h("button.btn.sm.ghost", { onclick: () => go(`pronunciations?project=${slug}`) }, { __html: icon("spell", "s") }, "Pronunciations"),
        h("span.grow"), h("span.label", {}, "Exports"), els.exports)),
    els.blocks);
  el.append(els.main);
  renderBlocks();
  window.onbeforeunload = () => (dirty ? true : undefined);
}

export async function mount(el, { parts }) {
  root = el;
  if (parts[0]) await openProject(el, parts[0]); else await listProjects(el);
}
export function unmount() { if (dirty) save(); window.onbeforeunload = null; }
