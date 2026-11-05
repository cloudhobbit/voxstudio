// Runs on the audio thread: hands the microphone's samples to the page in 20 ms frames (320 samples at 16 kHz).
class MicFrames extends AudioWorkletProcessor {
  constructor() { super(); this.frame = new Float32Array(320); this.filled = 0; }
  process(inputs) {
    const input = inputs[0] && inputs[0][0];
    if (!input) return true;
    for (let i = 0; i < input.length; i++) {
      this.frame[this.filled++] = input[i];
      if (this.filled === this.frame.length) {
        const pcm = new Int16Array(this.frame.length);
        let peak = 0;
        for (let j = 0; j < pcm.length; j++) { const v = Math.max(-1, Math.min(1, this.frame[j])); pcm[j] = v * 32767; peak = Math.max(peak, Math.abs(v)); }
        this.port.postMessage({ pcm: pcm.buffer, peak }, [pcm.buffer]);
        this.filled = 0;
      }
    }
    return true;
  }
}
registerProcessor("mic-frames", MicFrames);
