// Pronunciations: how words are said, shared or per project, with before/after playback.
import { api, speak } from "../lib/api.js";
import { icon } from "../lib/icons.js";
import { go } from "../lib/router.js";
import { h, clear, local } from "../lib/store.js";
import { dialog, empty, iconBtn, toast } from "../lib/ui.js";
import { voicePicker } from "../lib/voicepicker.js";
import { player, setTitle, store } from "../app.js";

let root, scope = "shared", testVoice, els = {};
const context = (word) => `The word is ${word}. ${word} again.`;
const applySay = (text, word, say) => text.split(word).join(say.startsWith("/") ? `[${word}](${say})` : say);
const typeOf = (say) => (say.trim().startsWith("/") ? "phonemes" : "respelling");

async function before(word) {
  const r = await speak({ text: context(word), voice: testVoice.get(), pronounce: false });
  player.play({ id: `pb:${word}`, url: r.url, title: `${word} (before)`, subtitle: context(word) });
}
async function after(word, say) {
  if (!say.trim()) return toast("Type how to say it first");
  const r = await speak({ text: applySay(context(word), word, say.trim()), voice: testVoice.get(), pronounce: false });
  player.play({ id: `pa:${word}:${say}`, url: r.url, title: `${word} (after)`, subtitle: say });
}

function scopeQuery() { return scope === "shared" ? "scope=shared" : `scope=project&project=${encodeURIComponent(store.get("project"))}`; }

async function save(word, say, etag) {
  const body = { say: say.trim(), etag, ...(scope === "project" ? { project: store.get("project") } : {}) };
  try {
    await api.put(`/api/pronunciations/${scope}/${encodeURIComponent(word.trim())}`, body, { quiet: true });
    toast(`Saved: ${word} → ${say.trim()}`, { kind: "ok", ms: 2500 });
  } catch (e) { toast(e.status === 409 ? "The file changed on disk; reloaded" : e.message, { kind: "error" }); }
  load();
}
async function remove(word, etag) {
  const q = scope === "project" ? `?project=${encodeURIComponent(store.get("project"))}&etag=${encodeURIComponent(etag)}` : `?etag=${encodeURIComponent(etag)}`;
  try { await api.del(`/api/pronunciations/${scope}/${encodeURIComponent(word)}${q}`); toast(`Removed ${word}`); } catch { /* toasted */ }
  load();
}

async function suggest(word, into) {
  if (!word.trim()) return toast("Type the word first");
  try {
    const r = await api.post("/api/pronunciations/suggest", { word: word.trim() }, { quiet: true });
    into.value = r.ipa; into.dispatchEvent(new Event("input"));
    toast("A starting point from espeak-ng: edit it, then press After to check", { ms: 4000 });
  } catch (e) { toast(e.status === 501 ? e.message : e.message, { kind: "error", ms: 7000 }); }
}

function addRow(prefill = "") {
  const word = h("input.input", { placeholder: "Word", "aria-label": "Word", value: prefill, style: { maxWidth: "200px" } });
  const say = h("input.input", { placeholder: "Chun-druh-yaan  or  /pɹˈʌɡjɑn/", "aria-label": "Say it as" });
  const type = h("span.badge", {}, "respelling");
  say.addEventListener("input", () => (type.textContent = typeOf(say.value)));
  const row = h("div.row.wrap", { style: { alignItems: "center" } },
    h("span.label", {}, "Add"), word, say, type,
    h("button.btn.sm", { onclick: () => before(word.value.trim()) }, { __html: icon("play", "s") }, "Before"),
    h("button.btn.sm", { onclick: () => after(word.value.trim(), say.value) }, { __html: icon("play", "s") }, "After"),
    h("button.btn.sm.ghost", { title: "Ask espeak-ng for phonemes", onclick: () => suggest(word.value, say) }, { __html: icon("wand", "s") }, "Suggest phonemes"),
    h("button.btn.sm.primary", { onclick: () => { if (!word.value.trim() || !say.value.trim()) return toast("Both fields are needed"); save(word.value, say.value, els.etag); word.value = ""; say.value = ""; } }, "Save"));
  row.focusWord = () => word.focus();
  return row;
}

async function load() {
  clear(els.table);
  if (scope === "project" && !store.get("project")) { els.table.append(empty("Pick a project in the top bar to edit its own list.", { icon: "projects", action: h("button.btn", { onclick: () => go("projects") }, "Projects") })); return; }
  let data;
  try { data = await api.get(`/api/pronunciations?${scopeQuery()}`); } catch { return; }
  els.etag = data.etag;
  if (!data.entries.length) { els.table.append(empty(scope === "shared" ? "No shared pronunciations yet. Add a word above, hear it before and after, save." : "This project has no overrides. Entries here win over the shared list.", { icon: "spell" })); return; }
  els.table.append(h("div.card", { style: { padding: 0 } }, h("div.table-wrap", {}, h("table.table", {},
    h("thead", {}, h("tr", {}, ...["Word", "Say it as", "Type", "", "", ""].map((t) => h("th", {}, t)))),
    h("tbody", {}, data.entries.map((e) => {
      const say = h("input.input", { value: e.say, "aria-label": `How to say ${e.word}`, style: { minWidth: "200px" }, onchange: () => save(e.word, say.value, els.etag) });
      return h("tr", {}, h("td", {}, h("b", {}, e.word), e.overrides_shared ? h("div.small.muted", {}, "overrides shared") : null), h("td", {}, say), h("td", {}, h("span.badge", {}, e.type)),
        h("td", {}, h("button.btn.sm", { onclick: () => before(e.word) }, "Before")), h("td", {}, h("button.btn.sm", { onclick: () => after(e.word, say.value) }, "After")),
        h("td", {}, iconBtn("trash", { label: `Remove ${e.word}`, cls: "sm", onclick: async () => { if (await dialog({ title: `Remove ${e.word}?`, body: "Lines using it will be said plainly on their next render.", ok: "Remove", danger: true })) remove(e.word, els.etag); } })));
    }))))));
}

async function scan() {
  const slug = store.get("project");
  if (!slug) return toast("Pick a project in the top bar first");
  try {
    const { words } = await api.post("/api/pronunciations/scan", { project: slug });
    clear(els.scan);
    if (!words.length) { els.scan.append(h("span.muted.small", {}, "Nothing stands out in this script.")); return; }
    els.scan.append(h("span.label", {}, `From the script (${words.length})`), ...words.map((w) => h("button.chip", { onclick: () => { const row = els.add; row.querySelector("input").value = w.word; row.focusWord(); row.querySelectorAll("input")[1].focus(); } }, `${w.word} ×${w.count}`)));
  } catch { /* toasted */ }
}

function renderTabs() {
  clear(els.tabs);
  const proj = store.get("projects").find((p) => p.slug === store.get("project"));
  els.tabs.append(
    h("button.chip", { "aria-pressed": scope === "shared" ? "true" : "false", onclick: () => { scope = "shared"; renderTabs(); load(); } }, "Shared (every project)"),
    h("button.chip", { "aria-pressed": scope === "project" ? "true" : "false", onclick: () => { scope = "project"; renderTabs(); load(); } }, proj ? `This project: ${proj.title}` : "This project"));
}

export async function mount(el, { query }) {
  root = el;
  setTitle("Pronunciations");
  testVoice = voicePicker({ value: local.get("pron.voice", "af_heart"), id: "pron-voice", onchange: (v) => local.set("pron.voice", v) });
  els.tabs = h("div.chips"); els.table = h("div"); els.scan = h("div.chips", { style: { alignItems: "center" } });
  els.add = addRow(query.word || "");
  clear(el);
  el.append(h("div.page-inner.stack", {},
    h("div.card.stack", {},
      h("div.row.wrap.between", {}, els.tabs, h("div.row", {}, h("span.label", {}, "Test voice"), h("div", { style: { width: "220px" } }, testVoice))),
      els.add,
      h("p.muted.small", { style: { margin: 0 } }, "A respelling is written the way it sounds (", h("code", {}, "Chun-druh-yaan"), "). Phonemes between slashes are exact (", h("code", {}, "/pɹˈʌɡjɑn/"), "). Before plays the plain word; After plays your entry. Captions keep the original spelling."),
      h("div.row", {}, h("button.btn.sm", { onclick: scan }, { __html: icon("search", "s") }, "Scan the current project for names"), els.scan)),
    els.table));
  renderTabs(); load();
  store.on("project", () => { renderTabs(); if (scope === "project") load(); });
  if (query.word) els.add.querySelectorAll("input")[1].focus();
}
