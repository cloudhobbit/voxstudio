// Shared UI pieces: toasts, dialogs, chips, sliders, menus, stars.
import { icon } from "./icons.js";
import { h, clear } from "./store.js";

let toastRoot;
export function toast(message, { kind = "", undo = null, ms = 5000, action = null } = {}) {
  toastRoot = toastRoot || document.querySelector(".toasts");
  const el = h("div.toast" + (kind ? "." + kind : ""), { role: "status" }, h("span", {}, message));
  if (undo) el.append(h("button", { onclick: () => { undo(); el.remove(); } }, "Undo"));
  if (action) el.append(h("button", { onclick: () => { action.fn(); el.remove(); } }, action.label));
  toastRoot.append(el);
  announce(message);
  setTimeout(() => el.remove(), undo || action ? Math.max(ms, 8000) : ms);
  return el;
}

export function announce(text) {
  const live = document.getElementById("live");
  if (live) { live.textContent = ""; setTimeout(() => (live.textContent = text), 30); }
}

/** confirm({title, body, ok, danger}) -> Promise<boolean>; prompt-style with fields: pass `form` (node) and read it in ok. */
export function dialog({ title, body, ok = "OK", cancel = "Cancel", danger = false, form = null, okDisabled = false }) {
  return new Promise((resolve) => {
    const dlg = document.getElementById("dialog");
    clear(dlg);
    const okBtn = h("button.btn" + (danger ? ".danger" : ".primary"), { onclick: () => { dlg.close(); resolve(true); }, disabled: okDisabled }, ok);
    const wrap = h("form.dlg", { method: "dialog", onsubmit: (e) => { e.preventDefault(); if (!okBtn.disabled) { dlg.close(); resolve(true); } } },
      h("h2", {}, title),
      typeof body === "string" ? h("p.muted", {}, body) : body,
      form,
      h("div.actions", {}, cancel && h("button.btn.ghost", { type: "button", onclick: () => { dlg.close(); resolve(false); } }, cancel), okBtn));
    dlg.append(wrap);
    dlg.onclose = () => resolve(false);
    dlg.showModal();
    const first = wrap.querySelector("input, textarea, select");
    if (first) first.focus(); else okBtn.focus();
  });
}

export function chip(label, { on = false, onclick, title, cls = "" } = {}) {
  return h("button.chip" + (cls ? "." + cls : ""), { type: "button", "aria-pressed": on ? "true" : "false", onclick, title }, label);
}

/** A labelled slider with a numeric input and a reset button. onchange fires on release; oninput on every move. */
export function slider({ label, min, max, step, value, def, format = (v) => v, onchange, oninput, id }) {
  const range = h("input", { type: "range", min, max, step, value, id, "aria-label": label });
  const num = h("input", { type: "number", min, max, step, value, "aria-label": label + " value" });
  const show = () => { num.value = range.value; };
  const reset = h("button.icon-btn.sm", { type: "button", title: "Reset", "aria-label": `Reset ${label}`, html: icon("refresh", "s"),
    onclick: () => { range.value = def; show(); onchange && onchange(+def); } });
  range.addEventListener("input", () => { show(); oninput && oninput(+range.value); });
  range.addEventListener("change", () => onchange && onchange(+range.value));
  num.addEventListener("change", () => { range.value = Math.min(max, Math.max(min, +num.value || 0)); show(); onchange && onchange(+range.value); });
  const el = h("div.slider", {}, h("label", { for: id, class: "label" }, label), range, h("div.val", {}, num), reset);
  el.set = (v) => { range.value = v; show(); };
  el.get = () => +range.value;
  el.disable = (on) => { range.disabled = on; num.disabled = on; reset.disabled = on; el.style.opacity = on ? ".5" : ""; };
  return el;
}

export function stars(value, onchange, { label = "Rating" } = {}) {
  const el = h("div.stars", { role: "radiogroup", "aria-label": label });
  const draw = (v) => { clear(el); for (let i = 1; i <= 5; i++) el.append(h("button", { type: "button", class: i <= v ? "on" : "", role: "radio",
    "aria-checked": i === v ? "true" : "false", "aria-label": `${i} star${i > 1 ? "s" : ""}`, html: icon("star", i <= v ? "s on" : "s"),
    onclick: (e) => { e.stopPropagation(); const nv = v === i ? 0 : i; draw(nv); onchange(nv); } })); };
  draw(value || 0);
  return el;
}

/** A small popover menu anchored to a button. items: [{label, icon, onclick, danger}, "-"] */
export function menu(anchor, items) {
  closeMenus();
  const el = h("div.menu", { role: "menu" });
  for (const it of items) {
    if (it === "-") { el.append(h("hr")); continue; }
    el.append(h("button", { role: "menuitem", class: it.danger ? "danger" : "", onclick: (e) => { e.stopPropagation(); closeMenus(); it.onclick(); } },
      it.icon ? { __html: icon(it.icon) } : null, it.label));
  }
  document.body.append(el);
  const r = anchor.getBoundingClientRect();
  el.style.top = `${Math.min(r.bottom + 4, window.innerHeight - el.offsetHeight - 8)}px`;
  el.style.left = `${Math.max(8, Math.min(r.right - el.offsetWidth, window.innerWidth - el.offsetWidth - 8))}px`;
  el.querySelector("button")?.focus();
  setTimeout(() => document.addEventListener("click", closeMenus, { once: true }), 0);
  return el;
}
export function closeMenus() { document.querySelectorAll(".menu, .popover").forEach((m) => m.remove()); }

export function popover(anchor, content) {
  closeMenus();
  const el = h("div.popover", { onclick: (e) => e.stopPropagation() }, content);
  document.body.append(el);
  const r = anchor.getBoundingClientRect();
  el.style.top = `${Math.min(r.bottom + 4, window.innerHeight - el.offsetHeight - 8)}px`;
  el.style.left = `${Math.max(8, Math.min(r.left, window.innerWidth - el.offsetWidth - 8))}px`;
  setTimeout(() => document.addEventListener("click", closeMenus, { once: true }), 0);
  return el;
}

export function empty(text, { icon: name = "library", action = null } = {}) {
  return h("div.empty", {}, { __html: icon(name) }, h("div", {}, text), action);
}

export function skeletons(n = 6) {
  return h("div.grid", {}, Array.from({ length: n }, () => h("div.card.stack.tight", {}, h("div.skeleton", { style: { width: "60%" } }),
    h("div.skeleton", { style: { width: "40%", minHeight: "12px" } }), h("div.skeleton", { style: { minHeight: "28px" } }))));
}

export function gradeBadge(grade, note) {
  if (!grade) return null;
  return h("span.badge.grade", { "data-g": grade, title: note || "" }, grade);
}

export function iconBtn(name, { label, onclick, on = false, cls = "" }) {
  return h("button.icon-btn" + (on ? ".on" : "") + (cls ? "." + cls : ""), { type: "button", "aria-label": label, title: label, html: icon(name), onclick });
}

export function copyText(text, what = "Copied") {
  navigator.clipboard?.writeText(text).then(() => toast(`${what}: ${text}`, { ms: 2500 }), () => toast("Clipboard not available", { kind: "error" }));
}
