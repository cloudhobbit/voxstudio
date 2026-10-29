// Every component in one place, for visual checks in light and dark.
import { icon } from "../lib/icons.js";
import { h, clear } from "../lib/store.js";
import { chip, dialog, gradeBadge, menu, slider, stars, toast, empty, skeletons } from "../lib/ui.js";
import { setTitle } from "../app.js";

export function mount(el) {
  setTitle("Kitchen sink");
  clear(el);
  const sw = (name) => h("div.swatch", { style: { background: `var(--${name})` } }, name);
  el.append(h("div.page-inner.stack", {},
    h("div.card", {}, h("h2", {}, "Colours"), h("div.swatches", {}, ["bg", "surface", "surface-2", "surface-3", "line", "line-strong", "accent", "accent-soft", "ok", "warn", "danger", "ok-soft", "warn-soft", "danger-soft"].map(sw))),
    h("div.card.stack", {}, h("h2", {}, "Type"), h("h1", {}, "Title 20/28"), h("h2", {}, "Heading 16/24"), h("p", {}, "Body 14/20. The quick brown fox jumps over the lazy dog."), h("p.small.muted", {}, "Small muted 13/18"), h("code", {}, "af_heart:0.60,bf_emma:0.40")),
    h("div.card.stack", {}, h("h2", {}, "Buttons"), h("div.row.wrap", {}, h("button.btn.primary", {}, "Primary"), h("button.btn", {}, "Secondary"), h("button.btn.ghost", {}, "Ghost"), h("button.btn.danger", {}, "Danger"), h("button.btn", { disabled: true }, "Disabled"), h("button.btn.sm", {}, "Small"),
      h("button.icon-btn", { "aria-label": "Play", html: icon("play") }), h("button.icon-btn.on", { "aria-label": "Favourite", html: icon("star") }),
      h("button.btn", { onclick: (e) => menu(e.currentTarget, [{ label: "Edit", icon: "sliders", onclick: () => toast("Edit") }, "-", { label: "Delete", icon: "trash", danger: true, onclick: () => toast("Deleted", { undo: () => toast("Restored") }) }]) }, "Menu ▾"))),
    h("div.card.stack", {}, h("h2", {}, "Chips, badges, stars"), h("div.chips", {}, chip("Female", { on: true }), chip("Male"), chip("US"), chip("UK"), chip("Favourites ★")),
      h("div.row.wrap", {}, gradeBadge("A", "Trained on many hours"), gradeBadge("B-"), gradeBadge("C+"), gradeBadge("D"), gradeBadge("F+"), h("span.badge", {}, "neutral"), h("span.badge.ok", {}, "ready"), h("span.badge.warn", {}, "loading"), h("span.badge.danger", {}, "failed"), h("span.badge.accent", {}, "signature")),
      stars(3, (v) => toast(`Rated ${v}`)), h("div", {}, h("kbd.kbd", {}, "Space"), " ", h("kbd.kbd", {}, "J"))),
    h("div.card.stack", {}, h("h2", {}, "Fields and sliders"),
      h("div.field", {}, h("label", { for: "ks-text" }, "Text"), h("textarea.textarea", { id: "ks-text" }, "Seventy-two hours earlier…"), h("div.counter", {}, "24 / 2000")),
      h("div.search", {}, { __html: icon("search") }, h("input.input", { type: "search", placeholder: "Search voices", "aria-label": "Search" })),
      h("div.row", {}, h("select.select", { "aria-label": "Select" }, h("option", {}, "Heart"), h("option", {}, "Emma"))),
      slider({ label: "Speed", min: 0.5, max: 2, step: 0.05, value: 1, def: 1, id: "ks-speed", onchange: (v) => toast(`Speed ${v}`) }),
      slider({ label: "Pitch", min: -12, max: 12, step: 1, value: -2, def: 0, id: "ks-pitch" }),
      h("div.bar", {}, h("span", { style: { width: "40%" } })), h("div.share-bar", {}, h("span", { style: { width: "60%", background: "var(--accent)" } }), h("span", { style: { width: "25%", background: "var(--ok)" } }), h("span", { style: { width: "15%", background: "var(--warn)" } }))),
    h("div.card.stack", {}, h("h2", {}, "Feedback"), h("div.row.wrap", {},
      h("button.btn", { onclick: () => toast("Saved to signatures.yaml", { undo: () => toast("Undone") }) }, "Toast with undo"),
      h("button.btn", { onclick: () => toast("The engine is still warming up, try again in a few seconds", { kind: "error" }) }, "Error toast"),
      h("button.btn", { onclick: () => dialog({ title: "Delete @narrator?", body: "Projects using it will stop rendering until you pick another voice.", ok: "Delete", danger: true }) }, "Dialog")),
      h("div.table-wrap", {}, h("table.table", {}, h("thead", {}, h("tr", {}, h("th", {}, "Name"), h("th", {}, "Mix"), h("th", {}, "Used in"))), h("tbody", {}, h("tr", {}, h("td", {}, "narrator"), h("td", {}, h("code", {}, "af_heart:0.6,bf_emma:0.4")), h("td", {}, h("span.badge", {}, "chapter-one")))))),
      skeletons(3), empty("No voices match these filters", { action: h("button.btn", {}, "Clear filters") })),
    h("div.card.stack", {}, h("h2", {}, "Voice card"), h("div.grid", {}, ...[["Heart", "A"], ["Emma", "B-"], ["Onyx", "D"]].map(([n, g]) => h("article.vcard.card", {},
      h("div.head", {}, h("span.name", {}, n), gradeBadge(g)), h("div.meta", {}, h("span", {}, "US"), "·", h("span", {}, "Female"), "·", h("span.badge.accent", {}, "narrator")),
      h("div.char", {}, "warm, clear, friendly"), h("canvas.wave"), h("div.actions", {}, h("button.icon-btn", { "aria-label": "Play", html: icon("play") }), h("span.grow"), h("button.icon-btn", { "aria-label": "Favourite", html: icon("star") }), h("button.icon-btn", { "aria-label": "Compare", html: icon("compare") }), h("button.icon-btn", { "aria-label": "More", html: icon("more") }))))))));
}
