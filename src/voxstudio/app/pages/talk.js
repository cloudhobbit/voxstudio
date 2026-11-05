// Talk: a conversation with one of your voices. Microphone in, speech out, all through one WebSocket.
import { icon } from "../lib/icons.js";
import { PcmPlayer } from "../lib/pcm.js";
import { h, clear, local } from "../lib/store.js";
import { chip, toast } from "../lib/ui.js";
import { voicePicker } from "../lib/voicepicker.js";
import { player, refreshHealth, setTitle, store, voiceName } from "../app.js";

let ws = null, mic = null, pcm = null, els = {}, mode = "hands-free", holding = false, turn = null, voice = "af_heart";

const secs = (ms) => `${(ms / 1000).toFixed(1)} s`;

function setState(text, kind = "") { els.state.textContent = text; els.state.className = "badge " + kind; }

function bubble(who, text, cls) {
  const body = h("div", {}, text);
  const el = h("div.card", { style: { padding: "8px 12px", maxWidth: "80%", alignSelf: who === "you" ? "flex-end" : "flex-start", background: who === "you" ? "var(--accent-soft)" : "var(--surface)" } },
    h("div.small.muted", {}, who === "you" ? "You" : voiceName(voice)), body);
  if (cls) el.classList.add(cls);
  els.log.append(el);
  el.scrollIntoView({ block: "end" });
  return { el, body };
}

function onEvent(e) {
  if (e.type === "ready") { setState(mic ? (mode === "hands-free" ? "Listening" : "Hold the button to talk") : "Type to talk", "ok"); els.models.textContent = `Hears with ${e.stt}. Thinks with ${e.llm}.`; return; }
  if (e.type === "speech_start") { pcm.stop(); if (turn && !turn.done) turn.el.style.opacity = ".6"; setState("Hearing you…", "accent"); return; }
  if (e.type === "thinking") { setState("Thinking…", "warn"); return; }
  if (e.type === "final") { bubble("you", e.text); return; }
  if (e.type === "speaking") {
    if (!turn || turn.done) turn = { ...bubble("them", ""), done: false };
    turn.body.textContent += (turn.body.textContent ? " " : "") + e.text;
    turn.el.scrollIntoView({ block: "end" });
    setState("Speaking", "accent");
    return;
  }
  if (e.type === "interrupted") { pcm.stop(); if (turn) turn.body.append(h("span.muted", {}, " — interrupted")); return; }
  if (e.type === "metrics" && turn && e.voice_to_voice_ms !== undefined) {
    const parts = [`heard in ${secs(e.stt_ms)}`, `first words after ${secs(e.llm_first_piece_ms)}`, `voice in ${secs(e.tts_first_audio_ms)}`];
    turn.el.append(h("div.small.muted", { title: "From the end of your turn to the first sound, and where the time went" },
      `${secs(e.from_speech_end_ms)} to the first sound (${parts.join(", ")}${e.end_silence_ms ? `, ${secs(e.end_silence_ms)} of that is the pause that ends your turn` : ""})`));
    return;
  }
  if (e.type === "done") { if (turn) turn.done = true; setState(mic ? (mode === "hands-free" ? "Listening" : "Hold the button to talk") : "Type to talk", "ok"); return; }
  if (e.type === "listening") { setState(mic ? "Listening" : "Type to talk", "ok"); return; }
  if (e.type === "error") { toast(e.message, { kind: "error", ms: 9000 }); setState("Something went wrong", "danger"); }
}

async function openMic() {
  if (!navigator.mediaDevices || !window.AudioWorkletNode) throw new Error("This browser cannot capture the microphone");
  const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
  const ctx = new AudioContext({ sampleRate: 16000 });   // the browser resamples the microphone for us
  await ctx.audioWorklet.addModule("/lib/mic-worklet.js");
  const node = new AudioWorkletNode(ctx, "mic-frames");
  node.port.onmessage = (m) => {
    els.meter.firstChild.style.width = `${Math.min(100, Math.round(m.data.peak * 140))}%`;
    if (ws && ws.readyState === 1 && (mode === "hands-free" || holding)) ws.send(m.data.pcm);
  };
  ctx.createMediaStreamSource(stream).connect(node);
  return { stream, ctx, node };
}

async function start() {
  if (ws) return stop();
  player.audio.pause();
  pcm = new PcmPlayer(24000);
  await pcm.resume();
  clear(els.log);
  turn = null;
  try { mic = await openMic(); }
  catch (e) { mic = null; toast(`No microphone (${e.message}). You can still type.`, { ms: 6000 }); }
  ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/talk`);
  ws.binaryType = "arraybuffer";
  ws.onopen = () => ws.send(JSON.stringify({ type: "start", persona: { voice, system: els.system.value.trim(), greeting: els.greeting.value.trim() }, end_silence_ms: +els.silence.value }));
  ws.onmessage = (m) => { if (typeof m.data === "string") onEvent(JSON.parse(m.data)); else pcm.enqueue(m.data); };
  ws.onclose = () => { if (ws) { ws = null; stop(); } };
  ws.onerror = () => toast("The conversation could not connect. Is the Talk extra installed?  pip install 'voxstudio[talk]'", { kind: "error", ms: 9000 });
  local.set("talk.persona", { voice, system: els.system.value, greeting: els.greeting.value, silence: els.silence.value });
  render();
}

function stop() {
  const sock = ws; ws = null;
  if (sock && sock.readyState <= 1) sock.close();
  if (mic) { mic.stream.getTracks().forEach((t) => t.stop()); mic.ctx.close(); mic = null; }
  if (pcm) pcm.stop();
  holding = false;
  if (els.state) { setState("Not connected"); render(); }
}

function send(obj) { if (ws && ws.readyState === 1) ws.send(JSON.stringify(obj)); }
function hold(on) {
  if (!ws || !mic || mode !== "hold" || holding === on) return;
  holding = on;
  send({ type: on ? "begin_turn" : "end_turn" });
  els.holdBtn.classList.toggle("primary", on);
  if (on) pcm.stop();
}

function render() {
  const on = !!ws;
  els.startBtn.textContent = on ? "End conversation" : "Start conversation";
  els.startBtn.classList.toggle("primary", !on);
  els.holdBtn.style.display = on && mic && mode === "hold" ? "" : "none";
  els.typed.disabled = !on; els.sendBtn.disabled = !on;
  for (const el of [els.system, els.greeting, els.silence]) el.disabled = on;
  clear(els.modes);
  els.modes.append(chip("Hands-free", { on: mode === "hands-free", title: "It listens all the time and answers when you pause. Use headphones, or it may hear itself.", onclick: () => setMode("hands-free") }),
    chip("Hold to talk", { on: mode === "hold", title: "It listens only while you hold the button (or the space bar).", onclick: () => setMode("hold") }));
}
function setMode(m) { mode = m; local.set("talk.mode", m); holding = false; render(); if (ws) setState(mic ? (m === "hands-free" ? "Listening" : "Hold the button to talk") : "Type to talk", "ok"); }

export async function mount(root) {
  setTitle("Talk");
  const hlth = (await refreshHealth()) || store.get("health") || {};
  const t = hlth.talk || {};
  const saved = local.get("talk.persona", {});
  voice = saved.voice || "af_heart"; mode = local.get("talk.mode", "hands-free");
  els.system = h("textarea.textarea", { rows: 3, "aria-label": "How it should behave", id: "talk-system" }, saved.system || t.default_system || "");
  els.greeting = h("input.input", { placeholder: "Optional: what it says first", "aria-label": "Greeting", value: saved.greeting || "" });
  els.silence = h("select.select", { "aria-label": "Pause that ends your turn", style: { width: "auto" } }, [[350, "Quick (0.35 s)"], [500, "Normal (0.5 s)"], [800, "Patient (0.8 s)"]].map(([v, l]) => h("option", { value: v, selected: String(saved.silence || 500) === String(v) }, l)));
  els.state = h("span.badge", {}, "Not connected");
  els.models = h("span.muted.small", {}, t.llm ? `Hears with ${t.stt || "nothing yet"}. Thinks with ${t.llm}.` : "");
  els.meter = h("div.bar", { style: { width: "80px" }, title: "Microphone level" }, h("span", { style: { width: "0%", transition: "none" } }));
  els.modes = h("div.chips");
  els.startBtn = h("button.btn.primary", { onclick: start }, "Start conversation");
  els.holdBtn = h("button.btn", { style: { display: "none" }, onmousedown: () => hold(true), onmouseup: () => hold(false), onmouseleave: () => hold(false), ontouchstart: (e) => { e.preventDefault(); hold(true); }, ontouchend: () => hold(false) }, { __html: icon("mic") }, "Hold to talk");
  els.log = h("div.stack.tight", { style: { minHeight: "160px" }, "aria-live": "polite" });
  els.typed = h("input.input", { placeholder: "Or type what you would say, and press Enter", "aria-label": "Type a turn", disabled: true, onkeydown: (e) => { if (e.key === "Enter" && els.typed.value.trim()) { send({ type: "text", text: els.typed.value.trim() }); els.typed.value = ""; } } });
  els.sendBtn = h("button.btn", { disabled: true, onclick: () => { if (els.typed.value.trim()) { send({ type: "text", text: els.typed.value.trim() }); els.typed.value = ""; } } }, "Send");
  const picker = voicePicker({ value: voice, id: "talk-voice", onchange: (v) => { voice = v; } });
  const notices = [];
  if (t.available === false) notices.push(h("div.card", { style: { borderColor: "var(--warn)" } }, h("b", {}, "The Talk extra is not installed. "), "Install it and restart: ", h("code", {}, "pip install 'voxstudio[talk]'")));
  if (t.llm === null || t.llm === "(no model set)") notices.push(h("div.card", { style: { borderColor: "var(--warn)" } }, h("b", {}, "No language model was found. "), t.llm_error || "Start one on this machine (for example ", h("code", {}, "ollama run qwen3:4b"), ") or set ", h("code", {}, "VOXSTUDIO_LLM_URL"), " and ", h("code", {}, "VOXSTUDIO_LLM_MODEL"), ", then restart."));
  if (t.stt === null) notices.push(h("div.card", { style: { borderColor: "var(--warn)" } }, h("b", {}, "No speech-to-text is installed. "), t.stt_error || ""));
  const where = t.llm ? (t.llm_local ? h("span.badge.ok", { title: t.llm_url || "" }, "Everything stays on this machine") : h("span.badge.warn", { title: t.llm_url || "" }, "Your words are sent to the language model at " + (t.llm_url || "another machine"))) : null;
  clear(root);
  root.append(h("div.page-inner.stack", {}, ...notices,
    h("div.card.stack", {},
      h("div.row.wrap", {}, h("div.field", { style: { flex: 1, minWidth: "220px" } }, h("label", { for: "talk-voice" }, "Voice"), picker), h("div.field", {}, h("label", {}, "Pause that ends your turn"), els.silence)),
      h("div.field", {}, h("label", { for: "talk-system" }, "How it should behave"), els.system),
      h("div.field", {}, h("label", {}, "Greeting"), els.greeting),
      h("div.row.wrap", {}, els.startBtn, els.modes, els.holdBtn, h("span.grow"), els.meter, els.state),
      h("div.row.wrap", {}, where, els.models)),
    h("div.card.stack", {}, els.log, h("div.row", {}, els.typed, els.sendBtn)),
    h("p.muted.small", {}, "Talk over it to interrupt. In hands-free mode use headphones, or it may hear its own voice. The time under each reply runs from the end of your turn to the first sound.")));
  render();
  document.addEventListener("keydown", spaceDown);
  document.addEventListener("keyup", spaceUp);
}
const typing = (e) => ["INPUT", "TEXTAREA", "SELECT"].includes(e.target.tagName);
function spaceDown(e) { if (e.code === "Space" && ws && mode === "hold" && !typing(e)) { e.preventDefault(); e.stopImmediatePropagation(); if (!e.repeat) hold(true); } }
function spaceUp(e) { if (e.code === "Space" && ws && mode === "hold" && !typing(e)) { e.preventDefault(); hold(false); } }
export function unmount() { document.removeEventListener("keydown", spaceDown); document.removeEventListener("keyup", spaceUp); stop(); els = {}; }
