// Microphone capture → 16 kHz mono PCM16 WAV (max 15 s) with a live level meter.
// AudioWorklet where available, ScriptProcessor as the fallback. Also wraps the browser's speech recognition
// for AUDIO_MODE=browser_stt (Chrome/Edge).

const TARGET_RATE = 16000;

export function downsample(input, inRate, outRate = TARGET_RATE) {
  if (inRate === outRate) return input;
  const ratio = inRate / outRate;
  const outLength = Math.floor(input.length / ratio);
  const out = new Float32Array(outLength);
  for (let i = 0; i < outLength; i++) {
    // Average the source samples that fall into this output sample (simple anti-aliasing).
    const start = Math.floor(i * ratio);
    const end = Math.min(input.length, Math.floor((i + 1) * ratio));
    let sum = 0;
    for (let j = start; j < end; j++) sum += input[j];
    out[i] = end > start ? sum / (end - start) : input[start] || 0;
  }
  return out;
}

export function encodeWav(samples, sampleRate = TARGET_RATE) {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const writeString = (offset, s) => { for (let i = 0; i < s.length; i++) view.setUint8(offset + i, s.charCodeAt(i)); };
  writeString(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  writeString(8, "WAVE");
  writeString(12, "fmt ");
  view.setUint32(16, 16, true);       // PCM chunk size
  view.setUint16(20, 1, true);        // PCM
  view.setUint16(22, 1, true);        // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeString(36, "data");
  view.setUint32(40, samples.length * 2, true);
  let offset = 44;
  for (let i = 0; i < samples.length; i++, offset += 2) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Blob([view], { type: "audio/wav" });
}

export class Recorder {
  constructor({ maxSeconds = 15, onLevel = () => {}, onAutoStop = () => {} } = {}) {
    this.maxSeconds = maxSeconds;
    this.onLevel = onLevel;
    this.onAutoStop = onAutoStop;
    this.chunks = [];
    this.recording = false;
    this.ctx = null;
    this.stream = null;
    this.node = null;
    this.source = null;
    this.timer = null;
  }

  static supported() {
    return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && (window.AudioContext || window.webkitAudioContext));
  }

  async start() {
    if (this.recording) return;
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
    });
    const Ctx = window.AudioContext || window.webkitAudioContext;
    this.ctx = new Ctx();
    if (this.ctx.state === "suspended") await this.ctx.resume();
    this.source = this.ctx.createMediaStreamSource(this.stream);
    this.chunks = [];
    const handle = (data) => {
      this.chunks.push(new Float32Array(data));
      let sum = 0;
      for (let i = 0; i < data.length; i++) sum += data[i] * data[i];
      this.onLevel(Math.min(1, Math.sqrt(sum / data.length) * 4));
    };
    try {
      await this.ctx.audioWorklet.addModule("/static/js/recorder-worklet.js");
      this.node = new AudioWorkletNode(this.ctx, "polarity-recorder");
      this.node.port.onmessage = (e) => handle(e.data);
    } catch (err) {
      // Older Safari / blocked worklets: ScriptProcessor still works everywhere.
      this.node = this.ctx.createScriptProcessor(4096, 1, 1);
      this.node.onaudioprocess = (e) => handle(e.inputBuffer.getChannelData(0));
    }
    this.source.connect(this.node);
    this.node.connect(this.ctx.destination);
    this.recording = true;
    this.timer = setTimeout(() => this.onAutoStop(), this.maxSeconds * 1000);
  }

  async stop() {
    if (!this.recording) return null;
    this.recording = false;
    clearTimeout(this.timer);
    const rate = this.ctx.sampleRate;
    this._teardown();
    const total = this.chunks.reduce((n, c) => n + c.length, 0);
    if (total < rate * 0.25) return null; // under a quarter second: treat as an accidental tap
    const merged = new Float32Array(total);
    let offset = 0;
    for (const c of this.chunks) { merged.set(c, offset); offset += c.length; }
    const capped = merged.subarray(0, Math.min(merged.length, Math.floor(rate * this.maxSeconds)));
    this.onLevel(0);
    return encodeWav(downsample(capped, rate), TARGET_RATE);
  }

  cancel() {
    this.recording = false;
    clearTimeout(this.timer);
    this._teardown();
    this.onLevel(0);
  }

  _teardown() {
    try { this.source && this.source.disconnect(); } catch (e) { /* already disconnected */ }
    try { this.node && this.node.disconnect(); } catch (e) { /* already disconnected */ }
    if (this.stream) this.stream.getTracks().forEach((t) => t.stop());
    if (this.ctx) this.ctx.close().catch(() => {});
    this.source = this.node = this.stream = this.ctx = null;
  }
}

// Browser speech recognition (AUDIO_MODE=browser_stt). Chrome/Edge; returns null where unsupported.
export function createRecognizer({ lang = "en-US", onResult = () => {}, onEnd = () => {}, onError = () => {} } = {}) {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return null;
  const rec = new SR();
  rec.lang = lang;
  rec.interimResults = true;
  rec.continuous = false;
  let finalText = "";
  rec.onresult = (e) => {
    let interim = "";
    for (let i = e.resultIndex; i < e.results.length; i++) {
      if (e.results[i].isFinal) finalText += e.results[i][0].transcript;
      else interim += e.results[i][0].transcript;
    }
    onResult(finalText || interim, !!finalText);
  };
  rec.onerror = (e) => onError(e.error || "speech recognition error");
  rec.onend = () => onEnd(finalText.trim());
  return {
    start() { finalText = ""; rec.start(); },
    stop() { try { rec.stop(); } catch (e) { /* not started */ } },
  };
}
