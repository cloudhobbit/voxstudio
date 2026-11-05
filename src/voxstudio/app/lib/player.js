// The global player: one <audio>, a canvas waveform, a compare tray. Whatever you click plays here.
import { icon } from "./icons.js";
import { h, clear, fmtTime, local } from "./store.js";
import { announce } from "./ui.js";

const peaksCache = new Map();
let ctx;

async function peaksFor(url, n = 160) {
  if (peaksCache.has(url)) return peaksCache.get(url);
  const p = (async () => {
    const buf = await (await fetch(url)).arrayBuffer();
    ctx = ctx || new (window.AudioContext || window.webkitAudioContext)();
    const audio = await ctx.decodeAudioData(buf);
    const data = audio.getChannelData(0);
    const step = Math.max(1, Math.floor(data.length / n));
    const peaks = [];
    for (let i = 0; i < n; i++) {
      let max = 0;
      for (let j = i * step; j < Math.min(data.length, (i + 1) * step); j += 4) max = Math.max(max, Math.abs(data[j]));
      peaks.push(max);
    }
    const top = Math.max(0.05, ...peaks);
    return { peaks: peaks.map((p) => p / top), duration: audio.duration };
  })();
  peaksCache.set(url, p);
  p.catch(() => peaksCache.delete(url));
  return p;
}

/** Draw peaks on a canvas; `progress` 0..1 colours the played part with the accent. */
export function drawWave(canvas, peaks, progress = 0, { line, accent } = {}) {
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth || 200, hgt = canvas.clientHeight || 40;
  if (canvas.width !== w * dpr || canvas.height !== hgt * dpr) { canvas.width = w * dpr; canvas.height = hgt * dpr; }
  const g = canvas.getContext("2d");
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, w, hgt);
  const css = getComputedStyle(document.documentElement);
  const cMuted = line || css.getPropertyValue("--line-strong").trim();
  const cAccent = accent || css.getPropertyValue("--accent").trim();
  const n = peaks.length, bw = w / n, gap = Math.min(2, bw * 0.3);
  for (let i = 0; i < n; i++) {
    const ph = Math.max(2, peaks[i] * (hgt - 4));
    g.fillStyle = i / n < progress ? cAccent : cMuted;
    g.fillRect(i * bw + gap / 2, (hgt - ph) / 2, Math.max(1, bw - gap), ph);
  }
}

export async function miniWave(canvas, url) {
  try { const { peaks } = await peaksFor(url, 60); drawWave(canvas, peaks); } catch { /* not decodable yet */ }
}

export function createPlayer(root) {
  const audio = new Audio();
  audio.preload = "auto";
  let current = null;          // {url, title, subtitle, id}
  let peaks = [];
  let rate = local.get("player.rate", 1);
  audio.playbackRate = rate;

  const playBtn = h("button.play", { "aria-label": "Play", disabled: true, html: icon("play", "l") });
  const info = h("div.info", {}, h("b", {}, "Nothing playing"), h("span", {}, "Click any ▶ to hear it here"));
  const canvas = h("canvas");
  const waveWrap = h("div.wave-wrap", { "aria-hidden": "true" }, canvas);
  const time = h("span.time", {}, "0:00 / 0:00");
  const rateSel = h("select.select", { "aria-label": "Playback speed", onchange: (e) => { rate = +e.target.value; audio.playbackRate = rate; local.set("player.rate", rate); } },
    [0.75, 1, 1.25, 1.5].map((r) => h("option", { value: r, selected: r === rate }, `${r}×`)));
  const trayBtn = h("button.btn.ghost", { "aria-label": "Compare tray", onclick: () => toggleTray() }, { __html: icon("compare") }, h("span.tray-count", {}, "Compare"));
  root.append(playBtn, info, waveWrap, time, rateSel, trayBtn);

  const tray = h("div.tray", { role: "region", "aria-label": "Compare tray" });
  root.parentElement.append(tray);
  let trayItems = [];
  let trayIndex = -1;

  function render() {
    drawWave(canvas, peaks, audio.duration ? audio.currentTime / audio.duration : 0);
    time.textContent = `${fmtTime(audio.currentTime)} / ${fmtTime(audio.duration)}`;
    const sounding = live || !audio.paused;
    playBtn.innerHTML = icon(sounding ? "pause" : "play", "l");
    playBtn.setAttribute("aria-label", live ? "Stop" : audio.paused ? "Play" : "Pause");
    document.querySelectorAll("[data-play-url]").forEach((el) => el.classList.toggle("playing", !audio.paused && el.dataset.playUrl === (current && current.url)));
  }
  audio.addEventListener("timeupdate", render);
  audio.addEventListener("play", render);
  audio.addEventListener("pause", render);
  audio.addEventListener("ended", () => { render(); document.dispatchEvent(new CustomEvent("vox:ended", { detail: current })); });
  playBtn.addEventListener("click", () => toggle());
  waveWrap.addEventListener("click", (e) => { const r = waveWrap.getBoundingClientRect(); if (audio.duration) audio.currentTime = ((e.clientX - r.left) / r.width) * audio.duration; });
  window.addEventListener("resize", render);

  // ---- live playback: raw audio is played as it arrives, then the finished file takes over ----
  let live = null;   // {ctrl, sources} while a stream is sounding
  function stopStream() {
    if (!live) return;
    const was = live;
    live = null;
    was.ctrl.abort();
    was.sources.forEach((s) => { try { s.stop(); } catch { /* already ended */ } });
    render();
  }

  /** POST `req` to /api/speak/stream and play the audio while it is still being made.
   *  Resolves once the whole line has arrived (and is cached): {key, url, cached, firstSoundMs, stopped}. */
  async function playStream(req, item) {
    stopStream();
    audio.pause();
    const ctrl = new AbortController();
    const started = performance.now();
    const res = await fetch("/api/speak/stream", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(req), signal: ctrl.signal });
    if (!res.ok) {
      let detail = `${res.status} ${res.statusText}`;
      try { const j = await res.json(); detail = Array.isArray(j.detail) ? j.detail.map((d) => d.msg).join("; ") : j.detail || detail; } catch { /* not JSON */ }
      throw new Error(detail);
    }
    const key = res.headers.get("X-Voxstudio-Key"), url = `/audio/${key}.wav`;
    if (res.headers.get("X-Voxstudio-Cached") === "true") { ctrl.abort(); await play({ ...item, url }); return { key, url, cached: true, firstSoundMs: 0 }; }
    const rate = +res.headers.get("X-Voxstudio-Sample-Rate") || 24000;
    ctx = ctx || new (window.AudioContext || window.webkitAudioContext)();
    if (ctx.state === "suspended") { try { await ctx.resume(); } catch { /* needs a click first */ } }
    const mine = (live = { ctrl, sources: [] });
    current = { ...item, url };
    clear(info);
    info.append(h("b", {}, item.title || ""), h("span", {}, item.subtitle || ""));
    playBtn.disabled = false;
    peaks = [];
    audio.removeAttribute("src");
    render();
    announce(`Playing ${item.title || ""}: ${item.subtitle || ""}`);
    const reader = res.body.getReader();
    let carry = new Uint8Array(0), at = 0, first = null;
    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        if (live !== mine) return { key, url, cached: false, stopped: true };
        const bytes = new Uint8Array(carry.length + value.length);
        bytes.set(carry); bytes.set(value, carry.length);
        const n = bytes.length >> 1;
        carry = bytes.slice(n * 2);
        if (!n) continue;
        const pcm = new Int16Array(bytes.buffer, 0, n);
        const buf = ctx.createBuffer(1, n, rate);
        const ch = buf.getChannelData(0);
        for (let i = 0; i < n; i++) ch[i] = pcm[i] / 32768;
        const src = ctx.createBufferSource();
        src.buffer = buf; src.connect(ctx.destination);
        at = Math.max(at, ctx.currentTime + 0.03);
        src.start(at);
        at += buf.duration;
        mine.sources.push(src);
        if (first === null) first = Math.round(performance.now() - started);
      }
    } catch (e) {
      if (live !== mine) return { key, url, cached: false, stopped: true };   // stopped by the listener
      stopStream();
      throw e;
    }
    // Everything has arrived, so the server has the finished file: load it for replay, scrubbing and the waveform.
    audio.src = url;
    peaksFor(url).then((p) => { if (current && current.url === url) { peaks = p.peaks; render(); } }, () => {});
    setTimeout(() => { if (live === mine) { live = null; render(); document.dispatchEvent(new CustomEvent("vox:ended", { detail: current })); } }, Math.max(0, at - ctx.currentTime) * 1000 + 60);
    return { key, url, cached: false, firstSoundMs: first };
  }

  async function play(item) {
    stopStream();
    current = item;
    clear(info);
    info.append(h("b", {}, item.title || ""), h("span", {}, item.subtitle || ""));
    playBtn.disabled = false;
    audio.src = item.url;
    audio.playbackRate = rate;
    peaks = [];
    render();
    try { await audio.play(); } catch { /* autoplay blocked: the user can press play */ }
    announce(`Playing ${item.title || ""}: ${item.subtitle || ""}`);
    try { peaks = (await peaksFor(item.url)).peaks; render(); } catch { /* fine */ }
  }

  function toggle() { if (live) return stopStream(); if (!current) return; audio.paused ? audio.play() : audio.pause(); }

  // ---- compare tray ----
  function renderTray() {
    clear(tray);
    trayBtn.querySelector(".tray-count").textContent = trayItems.length ? `Compare (${trayItems.length})` : "Compare";
    tray.append(h("div.row.between", {}, h("b", {}, "Compare"), h("span.muted.small", {}, trayItems.length ? "Space plays the next one" : "")));
    if (!trayItems.length) tray.append(h("p.muted.small", { style: { margin: "8px 0 0" } }, "Add voices with ⇄ to hear them back to back on the same line."));
    trayItems.forEach((it, i) => tray.append(h("div.item" + (i === trayIndex ? ".on" : ""), {},
      h("button.icon-btn.sm", { "aria-label": `Play ${it.title}`, html: icon("play", "s"), onclick: () => playTray(i) }),
      h("b", {}, it.title), h("span.muted.small", {}, it.subtitle || ""),
      h("button.icon-btn.sm", { "aria-label": `Remove ${it.title}`, html: icon("x", "s"), onclick: () => { trayItems.splice(i, 1); if (trayIndex >= trayItems.length) trayIndex = -1; renderTray(); } }))));
    if (trayItems.length) tray.append(h("div.row", { style: { marginTop: "8px" } },
      h("button.btn.sm", { onclick: () => playTray(0) }, "Play all"),
      h("button.btn.sm.ghost", { onclick: () => document.dispatchEvent(new CustomEvent("vox:mix-tray", { detail: trayItems.slice() })) }, "Mix these"),
      h("span.grow"), h("button.btn.sm.ghost", { onclick: () => { trayItems = []; trayIndex = -1; renderTray(); } }, "Clear")));
  }
  async function playTray(i) {
    if (!trayItems.length) return;
    trayIndex = (i + trayItems.length) % trayItems.length;
    renderTray();
    const it = trayItems[trayIndex];
    const resolved = it.resolve ? await it.resolve() : it;
    await play({ ...it, ...resolved });
  }
  function toggleTray(on) { tray.classList.toggle("on", on === undefined ? !tray.classList.contains("on") : on); }
  renderTray();

  return {
    play, playStream, stopStream, toggle, audio,
    get streaming() { return !!live; },
    get current() { return current; },
    get tray() { return trayItems; },
    addToTray(item) {
      if (trayItems.some((t) => t.id === item.id)) { trayItems = trayItems.filter((t) => t.id !== item.id); renderTray(); return false; }
      if (trayItems.length >= 4) { trayItems.shift(); }
      trayItems.push(item); renderTray(); toggleTray(true); return true;
    },
    inTray: (id) => trayItems.some((t) => t.id === id),
    nextInTray: () => playTray(trayIndex + 1),
    prevInTray: () => playTray(trayIndex - 1),
    toggleTray, closeTray: () => toggleTray(false), isTrayOpen: () => tray.classList.contains("on"),
  };
}
