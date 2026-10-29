import { h, clear } from "../lib/store.js";
import { setTitle } from "../app.js";

export function mount(el) {
  setTitle("Pronunciations");
  clear(el);
  el.append(h("div.empty", {}, "Pronunciations arrives with the next plan."));
}
