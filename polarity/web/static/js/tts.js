// Spoken feedback via the browser's speechSynthesis. Captions are always shown on screen, so voice is never the
// only channel. Safari needs one user click before audio can play: call tts.unlock() from a click handler.

const store = {
  get(key, fallback) { try { const v = localStorage.getItem(key); return v === null ? fallback : v; } catch (e) { return fallback; } },
  set(key, value) { try { localStorage.setItem(key, value); } catch (e) { /* private mode */ } },
};

export const tts = {
  supported: typeof window !== "undefined" && "speechSynthesis" in window,
  muted: store.get("polarity.muted", "0") === "1",
  voiceURI: store.get("polarity.voice", ""),
  unlocked: false,

  voices() {
    if (!this.supported) return [];
    return window.speechSynthesis.getVoices().filter((v) => v.lang && v.lang.toLowerCase().startsWith("en"));
  },

  unlock() {
    if (!this.supported || this.unlocked) return;
    const u = new SpeechSynthesisUtterance(" ");
    u.volume = 0;
    window.speechSynthesis.speak(u);
    this.unlocked = true;
  },

  setMuted(muted) {
    this.muted = !!muted;
    store.set("polarity.muted", this.muted ? "1" : "0");
    if (this.muted) this.stop();
  },

  setVoice(uri) {
    this.voiceURI = uri || "";
    store.set("polarity.voice", this.voiceURI);
  },

  speak(text) {
    if (!this.supported || this.muted || !text) return;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    const voice = this.voices().find((v) => v.voiceURI === this.voiceURI);
    if (voice) u.voice = voice;
    u.rate = 1.0;
    u.pitch = 1.0;
    window.speechSynthesis.speak(u);
  },

  stop() {
    if (this.supported) window.speechSynthesis.cancel();
  },
};
