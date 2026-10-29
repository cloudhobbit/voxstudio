import { h, clear } from "../lib/store.js";
import { setTitle } from "../app.js";

export function mount(el) {
  setTitle("Mixer");
  clear(el);
  el.append(h("div.empty", {}, "Mixer arrives with the next plan."));
}
