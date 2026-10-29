import { h, clear } from "../lib/store.js";
import { setTitle } from "../app.js";

export function mount(el) {
  setTitle("Projects");
  clear(el);
  el.append(h("div.empty", {}, "Projects arrives with the next plan."));
}
