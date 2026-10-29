import { h, clear } from "../lib/store.js";
import { setTitle } from "../app.js";

export function mount(el) {
  setTitle("Library");
  clear(el);
  el.append(h("div.empty", {}, "Library arrives with the next plan."));
}
