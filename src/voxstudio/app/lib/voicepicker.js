// A searchable voice picker: type to filter, arrow keys to move, Enter to choose. Value is a voice spec.
import { icon } from "./icons.js";
import { h, clear } from "./store.js";
import { gradeBadge } from "./ui.js";
import { store } from "../app.js";

export function voicePicker({ value = "af_heart", onchange, label = "Voice", id = "voice-picker", allowCustom = true }) {
  const input = h("input.input", { type: "text", id, role: "combobox", "aria-label": label, "aria-expanded": "false", "aria-autocomplete": "list", autocomplete: "off", spellcheck: false });
  const list = h("div.menu", { role: "listbox", style: { display: "none", position: "absolute", maxHeight: "320px", overflowY: "auto", minWidth: "320px" } });
  const wrap = h("div", { style: { position: "relative" } }, input, list);
  let current = value, active = -1, items = [];

  const nameOf = (v) => v.display_name || v.name;
  function show(v) { input.value = v ? `${nameOf(v)}` : current; input.title = current; }
  function setValue(spec) { current = spec; show(store.get("voices").find((x) => x.id === spec)); onchange && onchange(spec); }

  function open() {
    const q = input.value.trim().toLowerCase();
    const voices = store.get("voices");
    const match = (v) => !q || [v.id, v.name, v.display_name, v.character, ...(v.tags || []), ...(v.uses || [])].filter(Boolean).some((s) => String(s).toLowerCase().includes(q));
    items = [];
    clear(list);
    for (const [kind, title] of [["signature", "Signatures"], ["stock", "Voices"], ["blend", "Blends"]]) {
      const group = voices.filter((v) => v.kind === kind && match(v));
      if (!group.length) continue;
      list.append(h("div.nav-group", {}, title));
      for (const v of group) {
        const row = h("button", { type: "button", role: "option", "aria-selected": v.id === current ? "true" : "false", onmousedown: (e) => e.preventDefault(), onclick: () => { setValue(v.id); close(); } },
          h("span", { style: { flex: 1, display: "flex", alignItems: "center", gap: "6px", minWidth: 0 } }, h("b", { style: { fontWeight: 500 } }, nameOf(v)), v.grade ? gradeBadge(v.grade) : null, h("span.muted.small", { style: { overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" } }, v.kind === "stock" ? `${v.accent} · ${v.gender === "F" ? "female" : "male"} · ${v.character}` : v.kind === "signature" ? v.described : v.character)),
          v.favourite ? { __html: icon("star", "s") } : null);
        items.push({ el: row, v });
        list.append(row);
      }
    }
    if (allowCustom && q && /^[a-z@]/.test(q) && !items.some((i) => i.v.id === q)) {
      const row = h("button", { type: "button", role: "option", onmousedown: (e) => e.preventDefault(), onclick: () => { setValue(input.value.trim()); close(); } }, { __html: icon("wand", "s") }, h("span", {}, "Use ", h("code", {}, input.value.trim())));
      items.push({ el: row, v: { id: input.value.trim() } });
      list.append(row);
    }
    if (!items.length) list.append(h("div.muted.small", { style: { padding: "8px 10px" } }, "No voice matches"));
    list.style.display = "flex";
    input.setAttribute("aria-expanded", "true");
    active = -1;
  }
  function close() { list.style.display = "none"; input.setAttribute("aria-expanded", "false"); show(store.get("voices").find((x) => x.id === current)); }
  function move(d) { if (!items.length) return; items[active]?.el.classList.remove("on"); active = (active + d + items.length) % items.length; items[active].el.classList.add("on"); items[active].el.scrollIntoView({ block: "nearest" }); }

  input.addEventListener("focus", () => { input.select(); open(); });
  input.addEventListener("input", open);
  input.addEventListener("blur", () => setTimeout(close, 120));
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); if (list.style.display === "none") open(); move(1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); move(-1); }
    else if (e.key === "Enter") { e.preventDefault(); if (active >= 0) items[active].el.click(); else if (items.length) items[0].el.click(); }
    else if (e.key === "Escape") { close(); input.blur(); }
  });
  show(store.get("voices").find((x) => x.id === current));
  wrap.get = () => current;
  wrap.set = (spec) => { current = spec; show(store.get("voices").find((x) => x.id === spec)); };
  wrap.input = input;
  return wrap;
}
