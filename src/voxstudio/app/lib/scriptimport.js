// Paste or upload a script; see how it will be split, and give each speaker a voice.
import { api } from "./api.js";
import { icon } from "./icons.js";
import { h, clear, debounce, local } from "./store.js";
import { voicePicker } from "./voicepicker.js";

const ROTATION = ["bm_george", "af_bella", "am_michael", "bf_emma", "am_puck", "af_nicole", "bm_fable", "af_sarah"];
const LABELS = { text: "Plain text", markdown: "Markdown", srt: "Captions", dialogue: "Dialogue" };

export function scriptImport({ defaultVoice = "af_heart", id = "si", rows = 8 } = {}) {
  let parsed = { format: "text", blocks: [], speakers: [] };
  let pending = Promise.resolve();
  const pickers = new Map();   // speaker -> picker
  const remembered = local.get("import.voices", {});

  const ta = h("textarea.textarea", { rows, "aria-label": "Script", placeholder: "Paste a script, or choose a file.\nBlank lines separate blocks.  NAME: line  gives each speaker a voice.  Markdown and SRT work too." });
  const file = h("input", { type: "file", accept: ".txt,.md,.markdown,.srt,.vtt,text/plain,text/markdown", style: { display: "none" }, "aria-label": "Script file" });
  const status = h("span.muted.small", { "aria-live": "polite" }, "Nothing pasted yet.");
  const format = h("select.select", { "aria-label": "Read it as", style: { width: "auto", minHeight: "26px", padding: "0 6px", fontSize: "13px" } },
    h("option", { value: "auto" }, "Detect format"), ...Object.entries(LABELS).map(([v, l]) => h("option", { value: v }, l)));
  const main = voicePicker({ value: defaultVoice, id: `${id}-voice` });
  const mainLabel = h("label", { for: `${id}-voice` }, "Voice for every block");
  const cast = h("div.stack.tight");

  function renderCast() {
    clear(cast);
    pickers.clear();
    mainLabel.textContent = parsed.speakers.length ? "Voice for lines without a speaker" : "Voice for every block";
    if (!parsed.speakers.length) return;
    cast.append(h("div.label", {}, "Speakers"));
    parsed.speakers.forEach((name, i) => {
      const lines = parsed.blocks.filter((b) => b.speaker === name).length;
      const picker = voicePicker({ value: remembered[name.toLowerCase()] || (i === 0 ? main.get() : ROTATION[(i - 1) % ROTATION.length]), id: `${id}-sp-${i}` });
      pickers.set(name, picker);
      cast.append(h("div.row", {}, h("label", { for: `${id}-sp-${i}`, style: { width: "130px", flex: "none", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" } }, h("b", {}, name), h("span.muted.small", {}, ` ${lines} line${lines === 1 ? "" : "s"}`)), h("div", { style: { flex: 1 } }, picker)));
    });
  }

  async function parse() {
    const text = ta.value;
    if (!text.trim()) { parsed = { format: "text", blocks: [], speakers: [] }; status.textContent = "Nothing pasted yet."; renderCast(); return; }
    try {
      parsed = await api.post("/api/import/parse", { text, format: format.value }, { quiet: true });
      const n = parsed.blocks.length, sp = parsed.speakers.length;
      status.textContent = `${LABELS[parsed.format]}: ${n} block${n === 1 ? "" : "s"}${sp ? `, ${sp} speaker${sp === 1 ? "" : "s"}` : ""}.`;
      status.style.color = "";
    } catch (e) { status.textContent = e.message; status.style.color = "var(--danger)"; parsed = { format: "text", blocks: [], speakers: [] }; }
    renderCast();
  }
  const later = debounce(() => { pending = parse(); }, 300);
  ta.addEventListener("input", later);
  format.addEventListener("change", () => { pending = parse(); });
  file.addEventListener("change", async () => {
    const f = file.files[0];
    if (!f) return;
    if (f.size > 200000) { status.textContent = "That file is over 200 KB; paste a part of it instead."; status.style.color = "var(--danger)"; return; }
    ta.value = await f.text();
    pending = parse();
  });

  const el = h("div.stack.tight", {},
    h("div.row.wrap", {}, h("button.btn.sm", { type: "button", onclick: () => file.click() }, { __html: icon("folder", "s") }, "Choose a file…"), file, format, status),
    ta, h("div.field", {}, mainLabel, main), cast);

  /** Wait for the latest parse, then return what to send and the blocks with their voices. */
  el.result = async () => {
    await pending;
    if (ta.value.trim() && !parsed.blocks.length) await parse();
    const voices = Object.fromEntries([...pickers].map(([name, picker]) => [name, picker.get()]));
    local.set("import.voices", { ...remembered, ...Object.fromEntries(Object.entries(voices).map(([k, v]) => [k.toLowerCase(), v])) });
    return { script: ta.value, format: parsed.format, voice: main.get(), voices,
             blocks: parsed.blocks.map((b) => ({ text: b.text, voice: (b.speaker && voices[b.speaker]) || main.get(), ...(b.speaker ? { speaker: b.speaker } : {}) })) };
  };
  el.focus = () => ta.focus();
  return el;
}
