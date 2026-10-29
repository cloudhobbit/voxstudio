import { h, clear } from "../lib/store.js";
import { setTitle } from "../app.js";

export function mount(el) {
  setTitle("Workbench");
  clear(el);
  el.append(h("div.empty", {}, "Workbench arrives with the next plan."));
}
