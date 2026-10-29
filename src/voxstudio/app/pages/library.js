// Library: every voice on the same line. Filter, search, favourite, rate, tag, compare.
import { api, speak } from "../lib/api.js";
import { icon } from "../lib/icons.js";
import { miniWave } from "../lib/player.js";
import { setQuery, go } from "../lib/router.js";
import { onKey } from "../lib/shortcuts.js";
import { h, clear, debounce, local } from "../lib/store.js";
import { chip, dialog, empty, gradeBadge, iconBtn, menu, stars, toast, copyText, skeletons } from "../lib/ui.js";
import { closeDrawer, openDrawer, player, refreshVoices, setTitle, store } from "../app.js";

const GRADE_ORDER = ["A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "D-", "F+", "F"];
const gradeRank = (g) => (g ? GRADE_ORDER.indexOf(g) : 99);
let state, els = {}, focused = -1, visible = [], unkey, lineText = "";

function lineFor() {
  const lines = store.get("sampleLines");
  return state.line === "custom" ? (state.text || lines.narration) : (lines[state.line] || lines.narration);
}

function readState(query) {
  state = { q: query.q || "", gender: query.gender || "", accent: query.accent || "", grade: query.grade || "", uses: query.uses || "",
            fav: query.fav === "1", rating: +query.rating || 0, sort: query.sort || "grade", view: query.view || local.get("library.view", "grid"),
            line: query.line || local.get("library.line", "narration"), text: query.text || local.get("library.text", "") };
}
function writeState() { setQuery({ ...state, fav: state.fav ? "1" : "", rating: state.rating || "" }); local.set("library.view", state.view); local.set("library.line", state.line); local.set("library.text", state.text); }

function filtered() {
  const q = state.q.toLowerCase();
  let vs = store.get("voices").filter((v) => {
    if (q && ![v.id, v.name, v.display_name, v.character, v.described, ...(v.tags || []), ...(v.uses || [])].filter(Boolean).some((s) => String(s).toLowerCase().includes(q))) return false;
    if (state.gender && v.kind === "stock" && v.gender !== state.gender) return false;
    if (state.accent && v.kind === "stock" && v.accent !== state.accent) return false;
    if (state.grade && v.kind === "stock" && gradeRank(v.grade) > gradeRank(state.grade + "-")) return false;
    if (state.uses && !(v.uses || []).includes(state.uses) && !(v.tags || []).includes(state.uses)) return false;
    if (state.fav && !v.favourite) return false;
    if (state.rating && (v.rating || 0) < state.rating) return false;
    return true;
  });
  const recent = local.get("library.recent", {});
  const sorters = { grade: (a, b) => gradeRank(a.grade) - gradeRank(b.grade) || a.name.localeCompare(b.name),
                    name: (a, b) => (a.display_name || a.name).localeCompare(b.display_name || b.name),
                    rating: (a, b) => (b.rating || 0) - (a.rating || 0) || gradeRank(a.grade) - gradeRank(b.grade),
                    recent: (a, b) => (recent[b.id] || 0) - (recent[a.id] || 0) };
  vs.sort(sorters[state.sort] || sorters.grade);
  return vs;
}

async function playVoice(v) {
  const text = lineFor();
  local.set("library.recent", { ...local.get("library.recent", {}), [v.id]: Date.now() });
  const r = await speak({ text, voice: v.id, speed: v.speed || 1, pitch: v.pitch || 0 });
  v.sample = { url: r.url, duration: r.duration };
  player.play({ id: v.id, url: r.url, title: v.display_name || v.name, subtitle: text });
  const c = els.main.querySelector(`[data-voice="${CSS.escape(v.id)}"] canvas`);
  if (c) miniWave(c, r.url);
  if (r.queued_ahead > 1) toast(`${r.queued_ahead} lines ahead of yours`, { ms: 2000 });
}
function compareVoice(v) {
  const text = lineFor();
  const added = player.addToTray({ id: v.id, title: v.display_name || v.name, subtitle: text, resolve: async () => ({ url: (await speak({ text, voice: v.id, speed: v.speed || 1, pitch: v.pitch || 0 })).url }) });
  toast(added ? `${v.display_name || v.name} added to Compare` : `${v.display_name || v.name} removed from Compare`, { ms: 1500 });
  render();
}
async function patch(v, fields, what) {
  try {
    const r = await api.patch(`/api/voices/${encodeURIComponent(v.id)}`, { ...fields, etag: store.get("voicesEtag") }, { quiet: true });
    Object.assign(v, { favourite: false, rating: 0, tags: [], display_name: undefined }, r.entry);
    store.set("voicesEtag", r.etag);
    if (what) toast(what, { ms: 2000 });
  } catch (e) {
    if (e.status === 409) { toast("library.yaml changed on disk; reloaded it", { kind: "error" }); await refreshVoices(); }
    else toast(e.message, { kind: "error" });
  }
  render();
  if (els.drawerFor === v.id) openDetails(v);
}
const toggleFav = (v) => patch(v, { favourite: !v.favourite }, v.favourite ? "Removed from favourites" : "Added to favourites");

function moreMenu(e, v) {
  e.stopPropagation();
  menu(e.currentTarget, [
    { label: "Open in Workbench", icon: "mic", onclick: () => go(`workbench?voice=${encodeURIComponent(v.id)}&text=${encodeURIComponent(lineFor())}`) },
    { label: "Mix with…", icon: "sliders", onclick: () => go(`mixer?with=${encodeURIComponent(v.id)}`) },
    { label: "Copy id", icon: "copy", onclick: () => copyText(v.id, "Voice id") },
  ]);
}

function card(v, i) {
  const name = v.display_name || v.name;
  const el = h("article.vcard.card" + (i === focused ? ".focus" : "") + (player.current && player.current.id === v.id && !player.audio.paused ? ".playing" : ""),
    { "data-voice": v.id, "data-play-url": v.sample ? v.sample.url : "", tabindex: 0, "aria-label": name, onclick: () => openDetails(v), onkeydown: (e) => { if (e.key === "Enter") openDetails(v); } },
    h("div.head", {}, h("span.name", {}, name), v.kind === "signature" ? h("span.badge.accent", {}, "signature") : v.kind === "blend" ? h("span.badge", {}, "blend") : gradeBadge(v.grade, v.grade_note)),
    h("div.meta", {}, v.kind === "stock" ? [h("span", {}, v.accent), "·", h("span", {}, v.gender === "F" ? "Female" : "Male")] : h("span.mono", {}, v.described || v.mix),
      (v.rating ? h("span", { title: `Your rating ${v.rating}/5` }, "·", " ", "★".repeat(v.rating)) : null)),
    h("div.char", { title: v.character }, v.character || " "),
    h("div.chips", {}, (v.tags || []).slice(0, 3).map((t) => h("span.chip.static", {}, t)), (v.uses || []).slice(0, 2).map((t) => h("span.chip.static", {}, t))),
    h("canvas.wave", { "aria-hidden": "true" }),
    h("div.actions", { onclick: (e) => e.stopPropagation() },
      iconBtn("play", { label: `Play ${name}`, onclick: () => playVoice(v) }), h("span.grow"),
      iconBtn("star", { label: v.favourite ? "Remove from favourites" : "Add to favourites", on: v.favourite, onclick: () => toggleFav(v) }),
      iconBtn("compare", { label: "Compare", on: player.inTray(v.id), onclick: () => compareVoice(v) }),
      iconBtn("more", { label: "More", onclick: (e) => moreMenu(e, v) })));
  if (v.sample) miniWave(el.querySelector("canvas"), v.sample.url);
  return el;
}

function rowEl(v, i) {
  const name = v.display_name || v.name;
  return h("tr", { "data-voice": v.id, class: i === focused ? "focus" : "", tabindex: 0, onclick: () => openDetails(v), onkeydown: (e) => { if (e.key === "Enter") openDetails(v); } },
    h("td", {}, h("div.row", {}, iconBtn("play", { label: `Play ${name}`, cls: "sm", onclick: (e) => { e.stopPropagation(); playVoice(v); } }), h("b", {}, name))),
    h("td", {}, v.kind === "stock" ? `${v.gender === "F" ? "F" : "M"} · ${v.accent}` : h("span.badge" + (v.kind === "signature" ? ".accent" : ""), {}, v.kind)),
    h("td", {}, gradeBadge(v.grade, v.grade_note)), h("td.muted", {}, v.character || v.described || ""),
    h("td", {}, v.rating ? "★".repeat(v.rating) : ""), h("td", {}, h("div.chips", {}, (v.tags || []).map((t) => h("span.chip.static", {}, t)))),
    h("td", { onclick: (e) => e.stopPropagation() }, h("div.row", {}, iconBtn("star", { label: "Favourite", on: v.favourite, cls: "sm", onclick: () => toggleFav(v) }), iconBtn("compare", { label: "Compare", on: player.inTray(v.id), cls: "sm", onclick: () => compareVoice(v) }), iconBtn("more", { label: "More", cls: "sm", onclick: (e) => moreMenu(e, v) }))));
}

function render() {
  visible = filtered();
  const main = els.main;
  clear(main);
  if (!store.get("voices").length) { main.append(skeletons()); return; }
  if (!visible.length) { main.append(empty("No voices match these filters", { action: h("button.btn", { onclick: () => { readState({}); writeState(); mount(els.root, { query: {} }); } }, "Clear filters") })); return; }
  if (focused >= visible.length) focused = -1;
  if (state.view === "list") {
    main.append(h("div.card", { style: { padding: 0 } }, h("div.table-wrap", {}, h("table.table", {}, h("thead", {}, h("tr", {}, ...["Voice", "Kind", "Grade", "Character", "Rating", "Tags", ""].map((t) => h("th", {}, t)))), h("tbody", {}, visible.map(rowEl))))));
    return;
  }
  const groups = [["signature", "Your signatures"], ["stock", "Voices"], ["blend", "Preset blends"]];
  let i = 0;
  for (const [kind, title] of groups) {
    const vs = visible.filter((v) => v.kind === kind && !(kind === "stock" && v.accent === "Hindi"));
    const hindi = kind === "stock" ? visible.filter((v) => v.kind === "stock" && v.accent === "Hindi") : [];
    if (vs.length) { main.append(h("div.section-title", {}, h("h2", {}, title), h("span.muted.small", {}, `${vs.length}`)), h("div.grid", {}, vs.map((v) => card(v, i++)))); }
    if (hindi.length) { main.append(h("div.section-title", {}, h("h2", {}, "Hindi voices"), h("span.muted.small", {}, "the sample line is Hindi; English lines may sound odd")), h("div.grid", {}, hindi.map((v) => card(v, i++)))); }
  }
  visible = [...visible.filter((v) => v.kind === "signature"), ...visible.filter((v) => v.kind === "stock" && v.accent !== "Hindi"), ...visible.filter((v) => v.kind === "stock" && v.accent === "Hindi"), ...visible.filter((v) => v.kind === "blend")];
}

function openDetails(v) {
  els.drawerFor = v.id;
  const name = v.display_name || v.name;
  const tagInput = h("input.input", { placeholder: "Add a tag and press Enter", "aria-label": "Add tag", onkeydown: async (e) => { if (e.key === "Enter" && e.target.value.trim()) { e.preventDefault(); await patch(v, { tags: [...(v.tags || []), e.target.value.trim()] }); } } });
  const content = h("div.stack", {},
    h("h2", { tabindex: -1 }, name), h("div.row.wrap", {}, v.kind === "stock" ? [h("span", {}, v.accent), h("span", {}, v.gender === "F" ? "Female" : "Male"), gradeBadge(v.grade)] : h("span.badge" + (v.kind === "signature" ? ".accent" : ""), {}, v.kind), h("code.muted", {}, v.id)),
    h("div.row", {}, h("button.btn.primary", { onclick: () => playVoice(v) }, { __html: icon("play") }, "Play"), h("button.btn", { onclick: () => compareVoice(v) }, { __html: icon("compare") }, player.inTray(v.id) ? "In Compare" : "Compare"),
      h("button.btn", { onclick: () => go(`workbench?voice=${encodeURIComponent(v.id)}&text=${encodeURIComponent(lineFor())}`) }, "Workbench")),
    v.grade ? h("div.card", {}, h("b", {}, `Grade ${v.grade}`), h("p.muted.small", { style: { margin: "4px 0 0" } }, v.grade_note)) : null,
    v.described ? h("div", {}, h("div.label", {}, "Mix"), h("div", {}, v.described)) : null,
    v.character ? h("div", {}, h("div.label", {}, "Character"), h("div", {}, v.character)) : null,
    v.uses && v.uses.length ? h("div", {}, h("div.label", {}, "Good for"), h("div.chips", {}, v.uses.map((u) => chip(u, { on: state.uses === u, onclick: () => { state.uses = state.uses === u ? "" : u; writeState(); render(); } })))) : null,
    h("div", {}, h("div.label", {}, "Your rating"), h("div.row", {}, stars(v.rating || 0, (r) => patch(v, { rating: r || null }, r ? `Rated ${r}/5` : "Rating cleared")), h("button.btn.sm" + (v.favourite ? ".primary" : ""), { onclick: () => toggleFav(v) }, { __html: icon("star", "s") }, v.favourite ? "Favourite" : "Add to favourites"))),
    h("div", {}, h("div.label", {}, "Your tags"), h("div.chips", { style: { margin: "4px 0" } }, (v.tags || []).map((t) => h("span.chip.static", {}, t, h("button.icon-btn.sm", { "aria-label": `Remove tag ${t}`, html: icon("x", "s"), style: { width: "18px", height: "18px" }, onclick: () => patch(v, { tags: v.tags.filter((x) => x !== t) }) })))), tagInput),
    h("div", {}, h("div.label", {}, "Display name"), h("input.input", { value: v.display_name || "", placeholder: v.name, "aria-label": "Display name", onchange: (e) => patch(v, { display_name: e.target.value.trim() || null }, "Name saved") })),
    v.used_in && v.used_in.length ? h("div", {}, h("div.label", {}, "Used in"), h("div.chips", {}, v.used_in.map((p) => h("a.chip", { href: `#/projects/${p}` }, p)))) : null,
    h("div.row", {}, h("button.btn.ghost.sm", { onclick: () => copyText(v.id, "Voice id") }, { __html: icon("copy", "s") }, "Copy id"), v.kind === "stock" ? h("button.btn.ghost.sm", { onclick: () => go(`mixer?with=${encodeURIComponent(v.id)}`) }, { __html: icon("sliders", "s") }, "Mix with…") : null));
  openDrawer(content);
}

async function prerender() {
  const text = lineFor();
  const reqs = visible.map((v) => ({ text, voice: v.id, speed: v.speed || 1, pitch: v.pitch || 0 }));
  if (!reqs.length) return;
  const bar = h("div.bar", {}, h("span", { style: { width: "0%" } }));
  const label = h("span.small.muted", {}, `Rendering 0 of ${reqs.length}`);
  els.progress.append(h("div.row", { style: { gap: "12px", flex: 1 } }, label, h("div", { style: { flex: 1 } }, bar)));
  const { job_id } = await api.post("/api/speak/batch", reqs);
  const job = await api.job(job_id, (j) => { label.textContent = `Rendering ${j.done} of ${j.total}`; bar.firstChild.style.width = `${(100 * j.done) / j.total}%`; });
  clear(els.progress);
  job.urls.forEach((url, i) => { if (url) visible[i].sample = { url }; });
  toast(job.failed.length ? `${job.failed.length} voices failed` : `All ${job.total} voices rendered`, { kind: job.failed.length ? "error" : "ok" });
  render();
}

async function loadSamples() {
  const text = lineFor();
  if (text === lineText) return;
  lineText = text;
  try {
    const r = await api.get(`/api/voices?text=${encodeURIComponent(text)}`, { quiet: true });
    store.set("voicesEtag", r.etag); store.set("voices", r.voices);
  } catch { /* offline banner handles it */ }
  render();
}

export async function mount(root, { query }) {
  els.root = root;
  readState(query);
  focused = -1;
  const lines = store.get("sampleLines");
  const uses = [...new Set(store.get("voices").flatMap((v) => [...(v.uses || []), ...(v.tags || [])]))].sort();
  const search = h("input.input", { type: "search", placeholder: "Search voices, tags, character…", "aria-label": "Search voices", value: state.q, oninput: debounce((e) => { state.q = e.target.value; writeState(); render(); }, 120) });
  const customText = h("input.input", { placeholder: "Type your own line and press Enter", "aria-label": "Custom sample line", value: state.text, style: { display: state.line === "custom" ? "" : "none", flex: 1, minWidth: "240px" },
    onkeydown: (e) => { if (e.key === "Enter") { state.text = e.target.value.trim(); writeState(); loadSamples(); } } });
  const lineSel = h("select.select", { "aria-label": "Sample line", style: { width: "auto" }, onchange: (e) => { state.line = e.target.value; customText.style.display = state.line === "custom" ? "" : "none"; writeState(); if (state.line === "custom") customText.focus(); else loadSamples(); } },
    Object.keys(lines).map((k) => h("option", { value: k, selected: state.line === k }, k[0].toUpperCase() + k.slice(1))), h("option", { value: "custom", selected: state.line === "custom" }, "Custom…"));
  const toggleChip = (key, val, label) => chip(label, { on: state[key] === val, onclick: () => { state[key] = state[key] === val ? "" : val; writeState(); render(); refreshChips(); } });
  const chipsRow = h("div.chips");
  const refreshChips = () => { clear(chipsRow); chipsRow.append(
    toggleChip("gender", "F", "Female"), toggleChip("gender", "M", "Male"), toggleChip("accent", "US", "US"), toggleChip("accent", "UK", "UK"), toggleChip("accent", "Hindi", "Hindi"),
    toggleChip("grade", "A", "Grade A"), toggleChip("grade", "B", "Grade B+"), toggleChip("grade", "C", "Grade C+"),
    chip("★ Favourites", { on: state.fav, onclick: () => { state.fav = !state.fav; writeState(); render(); refreshChips(); } }),
    h("select.select", { "aria-label": "Good for", style: { width: "auto", minHeight: "26px", padding: "0 6px", fontSize: "13px" }, onchange: (e) => { state.uses = e.target.value; writeState(); render(); } }, h("option", { value: "" }, "Good for…"), uses.map((u) => h("option", { value: u, selected: state.uses === u }, u))),
    h("select.select", { "aria-label": "Minimum rating", style: { width: "auto", minHeight: "26px", padding: "0 6px", fontSize: "13px" }, onchange: (e) => { state.rating = +e.target.value; writeState(); render(); } }, h("option", { value: 0 }, "Any rating"), [3, 4, 5].map((r) => h("option", { value: r, selected: state.rating === r }, `★ ${r}+`)))); };
  refreshChips();
  els.progress = h("div", { style: { minHeight: "0" } });
  const toolbar = h("div.stack.tight", { style: { marginBottom: "16px" } },
    h("div.toolbar", { style: { marginBottom: 0 } }, h("div.search.grow", {}, { __html: icon("search") }, search),
      h("div.row", {}, h("span.label", {}, "Line"), lineSel), customText,
      h("select.select", { "aria-label": "Sort", style: { width: "auto" }, onchange: (e) => { state.sort = e.target.value; writeState(); render(); } }, [["grade", "Sort: grade"], ["name", "Sort: name"], ["rating", "Sort: my rating"], ["recent", "Sort: recently played"]].map(([v, l]) => h("option", { value: v, selected: state.sort === v }, l))),
      h("div.row", { style: { gap: "2px" } }, iconBtn("grid", { label: "Grid view", on: state.view === "grid", onclick: () => { state.view = "grid"; writeState(); mount(root, { query: state }); } }), iconBtn("list", { label: "List view", on: state.view === "list", onclick: () => { state.view = "list"; writeState(); mount(root, { query: state }); } })),
      h("button.btn", { onclick: prerender, title: "Render this line in every listed voice now, so flipping through them is instant" }, { __html: icon("wand") }, "Pre-render all")),
    chipsRow, els.progress);
  els.main = h("div");
  clear(root);
  root.append(h("div.page-inner", {}, toolbar, els.main));
  setTitle("Library");
  lineText = "";
  render();
  loadSamples();
  if (unkey) unkey();
  unkey = onKey((e) => {
    if (!visible.length) return false;
    const k = e.key.toLowerCase();
    if (k === "j" || k === "k") { focused = Math.min(visible.length - 1, Math.max(0, focused + (k === "j" ? 1 : -1))); render(); els.main.querySelector(`[data-voice="${CSS.escape(visible[focused].id)}"]`)?.scrollIntoView({ block: "nearest" }); return true; }
    if (focused < 0) return false;
    const v = visible[focused];
    if (k === "f") { toggleFav(v); return true; }
    if (k === "c") { compareVoice(v); return true; }
    if (k === "enter") { openDetails(v); return true; }
    if (k === "p") { playVoice(v); return true; }
    if ("12345".includes(k) && k) { patch(v, { rating: +k }, `Rated ${k}/5`); return true; }
    return false;
  });
}
export function unmount() { if (unkey) unkey(); unkey = null; closeDrawer(); }
