// Play raw 16-bit mono PCM as it arrives, gaplessly, and stop it at once when asked.
export class PcmPlayer {
  constructor(rate = 24000) { this.rate = rate; this.ctx = null; this.sources = new Set(); this.at = 0; this.carry = new Uint8Array(0); }
  async resume() {
    this.ctx = this.ctx || new (window.AudioContext || window.webkitAudioContext)();
    if (this.ctx.state === "suspended") { try { await this.ctx.resume(); } catch { /* needs a click first */ } }
  }
  /** Seconds of audio still to be heard. */
  get pending() { return this.ctx ? Math.max(0, this.at - this.ctx.currentTime) : 0; }
  enqueue(chunk) {
    if (!this.ctx) return;
    const bytes = new Uint8Array(this.carry.length + chunk.byteLength);
    bytes.set(this.carry); bytes.set(new Uint8Array(chunk), this.carry.length);
    const n = bytes.length >> 1;
    this.carry = bytes.slice(n * 2);
    if (!n) return;
    const pcm = new Int16Array(bytes.buffer, 0, n);
    const buf = this.ctx.createBuffer(1, n, this.rate);
    const ch = buf.getChannelData(0);
    for (let i = 0; i < n; i++) ch[i] = pcm[i] / 32768;
    const src = this.ctx.createBufferSource();
    src.buffer = buf; src.connect(this.ctx.destination);
    this.at = Math.max(this.at, this.ctx.currentTime + 0.03);
    src.start(this.at);
    this.at += buf.duration;
    this.sources.add(src);
    src.onended = () => this.sources.delete(src);
  }
  stop() {
    for (const s of this.sources) { try { s.stop(); } catch { /* already ended */ } }
    this.sources.clear(); this.at = 0; this.carry = new Uint8Array(0);
  }
}
