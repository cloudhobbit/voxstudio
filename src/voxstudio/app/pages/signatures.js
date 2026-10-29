// Signatures: your saved voice mixes, where they are used, rename and delete safely.
import { api, speak } from "../lib/api.js";
import { icon } from "../lib/icons.js";
import { fromSpec } from "../lib/mixmath.js";
import { go } from "../lib/router.js";
import { h, clear } from "../lib/store.js";
import { dialog, empty, iconBtn, menu, toast } from "../lib/ui.js";
import { player, refreshVoices, setTitle, store } from "../app.js";

const COLOURS = ["var(--accent)", "var(--ok)", "var(--warn)", "var(--danger)"];
let root;

function shareBar(mix) {
  try { return h("div.share-bar", { title: mix, style: { width: "120px", flex: "none" } }, fromSpec(mix).map((p, i) => h("span", { style: { width: `${p.w * 100}%`, background: COLOURS[i] } }))); }
  catch { return h("code", {}, mix); }
}

async function rename(sig, etag) {
  const input = h("input.input", { value: sig.name, "aria-label": "New name", pattern: "[a-z0-9][-a-z0-9_]*" });
  const used = sig.used_in.length ? ` The ${sig.used_in.length} project${sig.used_in.length > 1 ? "s" : ""} using it (${sig.used_in.join(", ")}) will be updated too.` : "";
  if (!(await dialog({ title: `Rename @${sig.name}`, body: `Lowercase letters, digits, - and _.${used}`, form: input, ok: "Rename" }))) return;
  const name = input.value.trim().toLowerCase();
  if (!name || name === sig.name) return;
  try {
    const r = await api.post(`/api/signatures/${encodeURIComponent(sig.name)}/rename`, { new_name: name, etag }, { quiet: true });
    toast(`Renamed to @${name}${r.updated_projects.length ? `; updated ${r.updated_projects.join(", ")}` : ""}`, { kind: "ok" });
  } catch (e) { toast(e.status === 409 ? "signatures.yaml changed on disk; reloaded" : e.message, { kind: "error" }); }
  await refreshVoices(); mount(root, {});
}

async function remove(sig, etag) {
  if (sig.used_in.length) { toast(`@${sig.name} is used by ${sig.used_in.join(", ")}: change those projects first`, { kind: "error", ms: 7000 }); return; }
  if (!(await dialog({ title: `Delete @${sig.name}?`, body: `${sig.described}. This cannot be undone.`, ok: "Delete", danger: true }))) return;
  try { await api.del(`/api/signatures/${encodeURIComponent(sig.name)}?etag=${encodeURIComponent(etag)}`); toast(`Deleted @${sig.name}`); }
  catch { /* toasted */ }
  await refreshVoices(); mount(root, {});
}

async function duplicate(sig) {
  const input = h("input.input", { value: `${sig.name}-2`, "aria-label": "Name", pattern: "[a-z0-9][-a-z0-9_]*" });
  if (!(await dialog({ title: `Duplicate @${sig.name}`, form: input, ok: "Duplicate" }))) return;
  try { await api.put(`/api/signatures/${encodeURIComponent(input.value.trim().toLowerCase())}`, { mix: sig.mix, speed: sig.speed, pitch: sig.pitch, note: sig.note }); toast("Duplicated", { kind: "ok" }); }
  catch { return; }
  await refreshVoices(); mount(root, {});
}

export async function mount(el) {
  root = el;
  setTitle("Signatures", [h("button.btn.primary", { onclick: () => go("mixer") }, { __html: icon("sliders") }, "New in Mixer")]);
  clear(el);
  let data;
  try { data = await api.get("/api/signatures"); } catch { return; }
  const { signatures, etag } = data;
  const line = store.get("sampleLines").narration;
  if (!signatures.length) {
    el.append(h("div.page-inner", {}, empty("No signature voices yet. Blend voices in the Mixer and save the result; use it anywhere as @name.", { icon: "signature", action: h("button.btn.primary", { onclick: () => go("mixer") }, "Open the Mixer") })));
    return;
  }
  el.append(h("div.page-inner", {}, h("div.card", { style: { padding: 0 } }, h("div.table-wrap", {}, h("table.table", {},
    h("thead", {}, h("tr", {}, ...["", "Name", "Mix", "Speed", "Pitch", "Note", "Used in", ""].map((t) => h("th", {}, t)))),
    h("tbody", {}, signatures.map((sig) => h("tr", {},
      h("td", {}, iconBtn("play", { label: `Play @${sig.name}`, cls: "sm", onclick: async () => { const r = await speak({ text: line, voice: `@${sig.name}`, speed: sig.speed, pitch: sig.pitch }); player.play({ id: `@${sig.name}`, url: r.url, title: `@${sig.name}`, subtitle: line }); } })),
      h("td", {}, h("b", {}, `@${sig.name}`)),
      h("td", {}, h("div.row", {}, shareBar(sig.mix), h("span.muted.small", {}, sig.described))),
      h("td.mono", {}, `${sig.speed}×`), h("td.mono", {}, `${sig.pitch > 0 ? "+" : ""}${sig.pitch} st`), h("td.muted", {}, sig.note),
      h("td", {}, h("div.chips", {}, sig.used_in.map((p) => h("a.chip", { href: `#/projects/${p}` }, p)))),
      h("td", {}, iconBtn("more", { label: "More", cls: "sm", onclick: (e) => menu(e.currentTarget, [
        { label: "Edit in Mixer", icon: "sliders", onclick: () => go(`mixer?from=${encodeURIComponent("@" + sig.name)}`) },
        { label: "Open in Workbench", icon: "mic", onclick: () => go(`workbench?voice=${encodeURIComponent("@" + sig.name)}`) },
        { label: "Rename", icon: "spell", onclick: () => rename(sig, etag) },
        { label: "Duplicate", icon: "copy", onclick: () => duplicate(sig) }, "-",
        { label: "Delete", icon: "trash", danger: true, onclick: () => remove(sig, etag) }]) }))))))))));
}
