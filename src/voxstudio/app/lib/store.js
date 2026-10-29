// A tiny observable store and a DOM helper. That is the whole "framework".
export function createStore(initial = {}) {
  const state = { ...initial };
  const subs = new Map();  // key -> Set<fn>
  return {
    get: (k) => state[k],
    set(k, v) { state[k] = v; (subs.get(k) || []).forEach((fn) => fn(v)); (subs.get("*") || []).forEach((fn) => fn(k, v)); },
    update(k, fn) { this.set(k, fn(state[k])); },
    on(k, fn) { if (!subs.has(k)) subs.set(k, new Set()); subs.get(k).add(fn); return () => subs.get(k).delete(fn); },
    state,
  };
}

// h("div.card", {onclick, "aria-label": ...}, child, [children], "text", rawHtml`...`)
export function h(tag, attrs = {}, ...children) {
  const [name, ...classes] = tag.split(".");
  const el = document.createElement(name || "div");
  if (classes.length) el.className = classes.join(" ");
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === "html") el.innerHTML = v;
    else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
    else if (k === "dataset") Object.assign(el.dataset, v);
    else if (k === "value" || k === "checked" || k === "disabled" || k === "selected") el[k] = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  append(el, children);
  return el;
}

export function append(el, children) {
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    if (c instanceof Node) el.appendChild(c);
    else if (c && c.__html) { const t = document.createElement("template"); t.innerHTML = c.__html; el.append(t.content); }
    else el.appendChild(document.createTextNode(String(c)));
  }
  return el;
}

export const raw = (html) => ({ __html: html });
export const clear = (el) => { while (el.firstChild) el.removeChild(el.firstChild); return el; };
export const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
export const fmtTime = (s) => { s = Math.max(0, s || 0); const m = Math.floor(s / 60); return `${m}:${String(Math.floor(s % 60)).padStart(2, "0")}`; };
export const local = {
  get(k, d) { try { const v = localStorage.getItem("vox." + k); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem("vox." + k, JSON.stringify(v)); } catch { /* private mode */ } },
};
