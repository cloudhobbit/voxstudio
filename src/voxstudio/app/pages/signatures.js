import { h, clear } from "../lib/store.js";
import { setTitle } from "../app.js";

export function mount(el) {
  setTitle("Signatures");
  clear(el);
  el.append(h("div.empty", {}, "Signatures arrives with the next plan."));
}
