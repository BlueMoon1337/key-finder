"use strict";

// ---------------------------------------------------------------- music helpers

const SHARP = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
const FLAT = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"];
const MAJOR_TONIC = ["C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"];
const MINOR_TONIC = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "G#", "A", "Bb", "B"];
const FLAT_MAJOR = new Set([1, 3, 5, 8, 10]);
const FLAT_MINOR = new Set([0, 2, 3, 5, 7, 10]);
const SUFFIX = { maj: "", min: "m", "7": "7", maj7: "maj7", min7: "m7", dim: "dim", aug: "aug", sus2: "sus2", sus4: "sus4" };

const mod12 = (n) => ((n % 12) + 12) % 12;
const keyName = (tonic, mode) => `${(mode === "major" ? MAJOR_TONIC : MINOR_TONIC)[mod12(tonic)]} ${mode}`;
const keyUsesFlats = (tonic, mode) => (mode === "major" ? FLAT_MAJOR : FLAT_MINOR).has(mod12(tonic));
function camelot(tonic, mode) {
  const relMajor = mode === "major" ? mod12(tonic) : mod12(tonic + 3);
  return `${(8 + 7 * relMajor) % 12 || 12}${mode === "major" ? "B" : "A"}`;
}
function chordLabel(chord, shift, flats) {
  if (chord.root === null || chord.root === undefined) return "N.C.";
  return (flats ? FLAT : SHARP)[mod12(chord.root + shift)] + SUFFIX[chord.quality];
}
function fmtTime(s) {
  if (!Number.isFinite(s)) s = 0;
  const m = Math.floor(s / 60);
  return `${m}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
}

// ---------------------------------------------------------------- api

async function api(path, options = {}) {
  const res = await fetch(path, options);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch { /* not json */ }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.status === 204 ? null : res.json();
}

const $ = (id) => document.getElementById(id);

let toastTimer;
function toast(message, isError = false) {
  const el = $("toast");
  el.textContent = message;
  el.classList.toggle("error", isError);
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, isError ? 6000 : 3000);
}

function storageGet(key, fallback) {
  try { return localStorage.getItem(key) ?? fallback; } catch { return fallback; }
}
function storageSet(key, value) {
  try { localStorage.setItem(key, value); } catch { /* private mode */ }
}

// ---------------------------------------------------------------- library

const library = {
  pollTimer: null,
  capabilities: null,

  async init() {
    const input = $("file-input");
    const zone = $("dropzone");
    input.addEventListener("change", () => { this.upload([...input.files]); input.value = ""; });
    zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("drag"); });
    zone.addEventListener("dragleave", () => zone.classList.remove("drag"));
    zone.addEventListener("drop", (e) => {
      e.preventDefault();
      zone.classList.remove("drag");
      this.upload([...e.dataTransfer.files]);
    });
    $("mode-select").value = storageGet("kf.mode", "4stems");
    $("backend-select").value = storageGet("kf.backend", "auto");
    $("mode-select").addEventListener("change", (e) => { storageSet("kf.mode", e.target.value); this.updateHint(); });
    $("backend-select").addEventListener("change", (e) => { storageSet("kf.backend", e.target.value); this.updateHint(); });
    try {
      this.capabilities = await api("/api/capabilities");
    } catch (err) {
      toast(`Server unavailable: ${err.message}`, true);
    }
    this.updateHint();
    await this.refresh();
  },

  updateHint() {
    const caps = this.capabilities;
    if (!caps) return;
    const hasDemucs = caps.backends.includes("demucs");
    const backend = $("backend-select").value;
    const mode = $("mode-select").value;
    $("backend-select").querySelector('[value="demucs"]').disabled = !hasDemucs;
    let hint = hasDemucs
      ? "Neural separation (Demucs) is installed."
      : "Demucs is not installed, so stems use the fast DSP separator (rough). Install the [ml] extra for studio-quality stems.";
    if (mode === "6stems" && (backend === "dsp" || !hasDemucs)) hint += " 6 stems needs Demucs; the DSP engine will produce 4.";
    $("backend-hint").textContent = hint;
  },

  async upload(files) {
    const mode = $("mode-select").value;
    let backend = $("backend-select").value;
    const hasDemucs = this.capabilities?.backends.includes("demucs");
    if (mode === "6stems" && !hasDemucs) backend = "auto";
    for (const file of files) {
      const form = new FormData();
      form.append("file", file);
      form.append("mode", mode === "6stems" && !hasDemucs ? "4stems" : mode);
      form.append("backend", backend);
      try {
        await api("/api/songs", { method: "POST", body: form });
        toast(`Uploaded “${file.name}”`);
      } catch (err) {
        toast(`${file.name}: ${err.message}`, true);
      }
      await this.refresh();
    }
  },

  async refresh() {
    let songs = [];
    try { songs = await api("/api/songs"); } catch { return; }
    this.render(songs);
    clearTimeout(this.pollTimer);
    if (songs.some((s) => s.status === "queued" || s.status === "processing")) {
      this.pollTimer = setTimeout(() => this.refresh(), 1500);
    }
  },

  render(songs) {
    const list = $("song-list");
    $("library-empty").hidden = songs.length > 0;
    list.replaceChildren(...songs.map((song) => {
      const li = document.createElement("li");
      li.className = `song ${song.status}`;
      const info = document.createElement("div");
      const title = document.createElement("div");
      title.className = "title";
      title.textContent = song.title;
      const meta = document.createElement("div");
      meta.className = "meta";
      if (song.status === "ready" || song.key) {
        meta.innerHTML = `<span>Key <b></b></span><span><b></b> BPM</span><span></span><span></span>`;
        const spans = meta.querySelectorAll("span");
        spans[0].querySelector("b").textContent = `${song.key} (${song.camelot})`;
        spans[1].querySelector("b").textContent = song.bpm;
        spans[2].textContent = fmtTime(song.duration);
        spans[3].textContent = song.status === "ready"
          ? `${Math.max(0, song.stems.length - 1) || "no"} stems${song.backend ? ` · ${song.backend}` : ""}`
          : song.stage;
      } else {
        meta.textContent = song.status === "error" ? "Failed" : song.stage;
      }
      info.append(title, meta);
      if (song.error) {
        const err = document.createElement("div");
        err.className = "error";
        err.textContent = song.error;
        info.append(err);
      }
      const del = document.createElement("button");
      del.className = "ghost small";
      del.textContent = "Delete";
      del.addEventListener("click", async (e) => {
        e.stopPropagation();
        if (!confirm(`Delete “${song.title}”?`)) return;
        try { await api(`/api/songs/${song.id}`, { method: "DELETE" }); } catch (err) { toast(err.message, true); }
        this.refresh();
      });
      li.append(info, del);
      if (song.status === "queued" || song.status === "processing") {
        const bar = document.createElement("div");
        bar.className = "progress";
        bar.innerHTML = "<i></i>";
        bar.firstChild.style.width = `${Math.round(song.progress * 100)}%`;
        li.append(bar);
      }
      if (song.status === "ready") {
        li.tabIndex = 0;
        li.addEventListener("click", () => router.go(song.id));
        li.addEventListener("keydown", (e) => { if (e.key === "Enter") router.go(song.id); });
      }
      return li;
    }));
  },
};

// ---------------------------------------------------------------- player

const player = {
  song: null,
  ctx: null,
  master: null,
  tracks: [],           // {name, el, gain, volume, muted, solo}
  semitones: 0,
  speed: 1,
  level: storageGet("kf.level", "intermediate"),
  playing: false,
  loop: { a: null, b: null, on: false },
  metronome: { on: false, volume: 0.6, nextBeat: 0 },
  countIn: false,
  countInTimer: null,
  raf: null,
  schedulerTimer: null,
  lastChordIndex: -1,
  pxPerSecond: 70,
  drag: null,

  init() {
    $("play-btn").addEventListener("click", () => this.toggle());
    $("rewind-btn").addEventListener("click", () => this.seek(this.time() - 5));
    $("forward-btn").addEventListener("click", () => this.seek(this.time() + 5));
    $("pitch-down").addEventListener("click", () => this.setPitch(this.semitones - 1));
    $("pitch-up").addEventListener("click", () => this.setPitch(this.semitones + 1));
    $("pitch-reset").addEventListener("click", () => this.setPitch(0));
    $("speed").addEventListener("input", (e) => this.setSpeed(parseFloat(e.target.value)));
    $("metronome").addEventListener("change", (e) => { this.metronome.on = e.target.checked; this.resetMetronome(); });
    $("metronome-volume").addEventListener("input", (e) => { this.metronome.volume = parseFloat(e.target.value); });
    $("count-in").addEventListener("change", (e) => { this.countIn = e.target.checked; });
    $("loop-a").addEventListener("click", () => this.setLoopPoint("a"));
    $("loop-b").addEventListener("click", () => this.setLoopPoint("b"));
    $("loop-on").addEventListener("change", (e) => { this.loop.on = e.target.checked; this.renderLoop(); });
    $("loop-clear").addEventListener("click", () => { this.loop = { a: null, b: null, on: false }; this.renderLoop(); });
    $("export-btn").addEventListener("click", () => this.export());
    for (const btn of $("level-select").querySelectorAll("button")) {
      btn.addEventListener("click", () => this.setLevel(btn.dataset.level));
    }
    const canvas = $("waveform");
    canvas.addEventListener("pointerdown", (e) => this.onPointerDown(e));
    canvas.addEventListener("pointermove", (e) => this.onPointerMove(e));
    canvas.addEventListener("pointerup", (e) => this.onPointerUp(e));
    window.addEventListener("resize", () => { if (this.song) { this.drawWaveform(); this.buildTicker(); } });
    document.addEventListener("keydown", (e) => this.onKey(e));
  },

  // --------------------------------------------------------- loading

  async open(id) {
    this.close();
    let song;
    try {
      song = await api(`/api/songs/${id}`);
    } catch (err) {
      toast(err.message, true);
      router.go(null);
      return;
    }
    if (song.status !== "ready") {
      toast("This song is still processing.");
      router.go(null);
      return;
    }
    this.song = song;
    this.semitones = 0;
    this.loop = { a: null, b: null, on: false };
    this.ensureContext();
    const stems = song.stems.filter((s) => s !== "original");
    const names = stems.length ? stems : ["original"];
    this.tracks = names.map((name) => {
      const el = new Audio();
      el.preload = "auto";
      el.src = this.stemUrl(name);
      const gain = this.ctx.createGain();
      this.ctx.createMediaElementSource(el).connect(gain).connect(this.ctx.destination);
      return { name, el, gain, volume: 1, muted: false, solo: false };
    });
    this.master = this.tracks[0].el;
    this.master.addEventListener("ended", () => this.pause());
    this.setSpeed(this.speed);
    this.renderHeader();
    this.renderMixer();
    this.setLevel(this.level);
    this.renderLoop();
    this.drawWaveform();
    this.updateTime(0);
    this.loopFrame();
    this.schedulerTimer = setInterval(() => this.scheduleClicks(), 25);
  },

  close() {
    this.pause();
    cancelAnimationFrame(this.raf);
    clearInterval(this.schedulerTimer);
    for (const t of this.tracks) {
      t.el.pause();
      t.el.removeAttribute("src");
      t.el.load();
      t.gain.disconnect();
    }
    this.tracks = [];
    this.master = null;
    this.song = null;
  },

  ensureContext() {
    if (!this.ctx) this.ctx = new (window.AudioContext || window.webkitAudioContext)();
  },

  stemUrl(name) {
    const q = this.semitones ? `?semitones=${this.semitones}` : "";
    return `/api/songs/${this.song.id}/stems/${encodeURIComponent(name)}${q}`;
  },

  // --------------------------------------------------------- transport

  time() { return this.master ? this.master.currentTime : 0; },
  duration() { return this.song?.analysis.duration || this.master?.duration || 0; },

  async toggle() { this.playing || this.countInTimer ? this.pause() : await this.play(); },

  async play() {
    if (!this.master) return;
    await this.ctx.resume();
    if (this.loop.on && this.loop.a !== null && this.loop.b !== null) {
      const t = this.time();
      if (t < this.loop.a || t >= this.loop.b) this.seek(this.loop.a);
    }
    if (this.countIn) {
      const beat = 60 / (this.song.analysis.bpm * this.speed);
      const start = this.ctx.currentTime + 0.05;
      for (let i = 0; i < 4; i++) this.click(start + i * beat, i === 0, true);
      $("play-btn").textContent = "❚❚";
      this.countInTimer = setTimeout(() => { this.countInTimer = null; this.startTracks(); }, (0.05 + 4 * beat) * 1000);
      return;
    }
    this.startTracks();
  },

  async startTracks() {
    const t = this.time();
    for (const tr of this.tracks) tr.el.currentTime = t;
    this.resetMetronome();
    try {
      await Promise.all(this.tracks.map((tr) => tr.el.play()));
      this.playing = true;
      $("play-btn").textContent = "❚❚";
    } catch (err) {
      toast(`Playback failed: ${err.message}`, true);
      this.pause();
    }
  },

  pause() {
    clearTimeout(this.countInTimer);
    this.countInTimer = null;
    for (const tr of this.tracks) tr.el.pause();
    this.playing = false;
    $("play-btn").textContent = "▶";
  },

  seek(t) {
    if (!this.master) return;
    t = Math.max(0, Math.min(t, this.duration() - 0.05));
    for (const tr of this.tracks) tr.el.currentTime = t;
    this.resetMetronome();
    this.updateTime(t);
  },

  setSpeed(rate) {
    this.speed = rate;
    for (const tr of this.tracks) {
      tr.el.playbackRate = rate;
      tr.el.preservesPitch = true;
      tr.el.mozPreservesPitch = true;
      tr.el.webkitPreservesPitch = true;
    }
    $("speed").value = rate;
    $("speed-value").textContent = `${Math.round(rate * 100)}%`;
    if (this.song) this.renderHeader();
    this.resetMetronome();
  },

  async setPitch(semitones) {
    semitones = Math.max(-12, Math.min(12, semitones));
    if (!this.song || semitones === this.semitones) return;
    // A click during an earlier pitch reload must resume from where playback
    // was before that reload, not from the half-loaded element.
    if (!this.pitchPending) this.pitchPending = { t: this.time(), wasPlaying: this.playing };
    const { t, wasPlaying } = this.pitchPending;
    this.pause();
    this.semitones = semitones;
    $("pitch-value").textContent = semitones > 0 ? `+${semitones}` : String(semitones);
    this.renderHeader();
    this.renderChords();
    $("loading").hidden = false;
    try {
      // Pitch-shifted stems are rendered on the server on first request.
      await Promise.all(this.tracks.map((tr) => new Promise((resolve, reject) => {
        const onReady = () => { cleanup(); resolve(); };
        const onError = () => { cleanup(); reject(new Error(`could not load ${tr.name}`)); };
        const cleanup = () => { tr.el.removeEventListener("canplay", onReady); tr.el.removeEventListener("error", onError); };
        tr.el.addEventListener("canplay", onReady);
        tr.el.addEventListener("error", onError);
        tr.el.src = this.stemUrl(tr.name);
        tr.el.load();
      })));
      if (this.semitones !== semitones) return;  // superseded by a later click
      this.pitchPending = null;
      this.setSpeed(this.speed);  // a new source resets playbackRate
      this.seek(t);
      $("loading").hidden = true;
      if (wasPlaying) await this.play();
    } catch (err) {
      if (this.semitones !== semitones) return;
      this.pitchPending = null;
      $("loading").hidden = true;
      toast(err.message, true);
    }
  },

  // --------------------------------------------------------- mixer

  renderMixer() {
    const box = $("mixer");
    box.replaceChildren(...this.tracks.map((tr) => {
      const row = document.createElement("div");
      row.className = "stem";
      const name = document.createElement("span");
      name.className = "name";
      name.textContent = tr.name;
      const mute = document.createElement("button");
      mute.className = "mute";
      mute.textContent = "M";
      mute.title = `Mute ${tr.name}`;
      const solo = document.createElement("button");
      solo.className = "solo";
      solo.textContent = "S";
      solo.title = `Solo ${tr.name}`;
      const vol = document.createElement("input");
      vol.type = "range";
      vol.min = "0";
      vol.max = "1.5";
      vol.step = "0.01";
      vol.value = String(tr.volume);
      vol.setAttribute("aria-label", `${tr.name} volume`);
      mute.addEventListener("click", () => { tr.muted = !tr.muted; mute.classList.toggle("active", tr.muted); this.applyGains(); });
      solo.addEventListener("click", () => { tr.solo = !tr.solo; solo.classList.toggle("active", tr.solo); this.applyGains(); });
      vol.addEventListener("input", () => { tr.volume = parseFloat(vol.value); this.applyGains(); });
      row.append(name, mute, solo, vol);
      return row;
    }));
    this.applyGains();
  },

  effectiveGain(tr) {
    const anySolo = this.tracks.some((t) => t.solo);
    if (anySolo) return tr.solo ? tr.volume : 0;
    return tr.muted ? 0 : tr.volume;
  },

  applyGains() {
    for (const tr of this.tracks) tr.gain.gain.setTargetAtTime(this.effectiveGain(tr), this.ctx.currentTime, 0.015);
  },

  // --------------------------------------------------------- header & chords

  renderHeader() {
    const a = this.song.analysis;
    const k = a.key;
    $("song-title").textContent = this.song.title;
    const tonic = k.tonic + this.semitones;
    $("stat-key").textContent = keyName(tonic, k.mode);
    $("stat-key-sub").textContent = this.semitones
      ? `original ${k.name}`
      : `${Math.round(k.confidence * 100)}% confidence`;
    $("stat-camelot").textContent = camelot(tonic, k.mode);
    const rel = k.mode === "major" ? keyName(tonic + 9, "minor") : keyName(tonic + 3, "major");
    $("stat-relative").textContent = `relative ${rel}`;
    $("stat-bpm").textContent = (a.bpm * this.speed).toFixed(this.speed === 1 ? 1 : 0);
    $("stat-bpm-sub").textContent = this.speed === 1 ? "BPM" : `BPM (original ${a.bpm})`;
    $("stat-tuning").textContent = `${a.tuning_cents > 0 ? "+" : ""}${Math.round(a.tuning_cents)}`;
    $("time-total").textContent = fmtTime(this.duration());
  },

  chords() { return this.song.analysis.chords[this.level] || []; },

  flats() {
    const k = this.song.analysis.key;
    return keyUsesFlats(k.tonic + this.semitones, k.mode);
  },

  setLevel(level) {
    this.level = level;
    storageSet("kf.level", level);
    for (const btn of $("level-select").querySelectorAll("button")) btn.classList.toggle("active", btn.dataset.level === level);
    if (this.song) this.renderChords();
  },

  renderChords() {
    this.lastChordIndex = -1;
    this.buildTicker();
    this.updateChordDisplay(this.time());
  },

  buildTicker() {
    const track = $("ticker-track");
    const flats = this.flats();
    const px = this.pxPerSecond;
    track.style.width = `${this.duration() * px}px`;
    track.replaceChildren(...this.chords().map((c, i) => {
      const div = document.createElement("div");
      div.className = `chord${c.root === null ? " nc" : ""}`;
      div.style.left = `${c.start * px}px`;
      div.style.width = `${Math.max(2, (c.end - c.start) * px - 3)}px`;
      div.textContent = chordLabel(c, this.semitones, flats);
      div.dataset.index = i;
      div.addEventListener("click", () => this.seek(c.start));
      return div;
    }));
    this.lastChordIndex = -1;
  },

  chordIndexAt(t) {
    const chords = this.chords();
    let lo = 0;
    let hi = chords.length - 1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (chords[mid].end <= t) lo = mid + 1;
      else if (chords[mid].start > t) hi = mid - 1;
      else return mid;
    }
    return -1;
  },

  updateChordDisplay(t) {
    const chords = this.chords();
    const i = this.chordIndexAt(t);
    const track = $("ticker-track");
    const width = $("ticker").clientWidth;
    track.style.transform = `translateX(${width * 0.3 - t * this.pxPerSecond}px)`;
    if (i === this.lastChordIndex) return;
    track.querySelector(".chord.current")?.classList.remove("current");
    track.querySelector(`[data-index="${i}"]`)?.classList.add("current");
    this.lastChordIndex = i;
    const flats = this.flats();
    $("chord-now").textContent = i >= 0 ? chordLabel(chords[i], this.semitones, flats) : "–";
    const next = chords.slice(i + 1).find((c) => c.root !== null);
    $("chord-next").textContent = next ? chordLabel(next, this.semitones, flats) : "–";
  },

  updateBeatDots(t) {
    const a = this.song.analysis;
    const beats = a.beats;
    let lo = 0;
    let hi = beats.length;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (beats[mid] <= t) lo = mid + 1; else hi = mid;
    }
    const idx = lo - 1;
    const firstDown = a.downbeats.length ? beats.indexOf(a.downbeats[0]) : 0;
    const pos = idx >= 0 ? mod12(idx - firstDown) % 4 : -1;
    const fresh = idx >= 0 && t - beats[idx] < 0.15;
    $("beat-dots").querySelectorAll("i").forEach((dot, n) => {
      dot.classList.toggle("on", fresh && n === pos);
      dot.classList.toggle("down", n === 0);
    });
  },

  // --------------------------------------------------------- frame loop

  loopFrame() {
    const step = () => {
      if (!this.master) return;
      const t = this.time();
      if (this.playing) {
        // Keep stems in sync with the first one; media elements drift slightly.
        for (const tr of this.tracks) {
          if (tr.el !== this.master && Math.abs(tr.el.currentTime - t) > 0.05) tr.el.currentTime = t;
        }
        if (this.loop.on && this.loop.a !== null && this.loop.b !== null && t >= this.loop.b) this.seek(this.loop.a);
      }
      this.updateTime(t);
      this.raf = requestAnimationFrame(step);
    };
    this.raf = requestAnimationFrame(step);
  },

  updateTime(t) {
    $("time-now").textContent = fmtTime(t);
    this.updateChordDisplay(t);
    this.updateBeatDots(t);
    this.drawWaveform(t);
  },

  // --------------------------------------------------------- metronome

  resetMetronome() {
    const beats = this.song?.analysis.beats || [];
    const t = this.time();
    let i = 0;
    while (i < beats.length && beats[i] < t - 0.01) i++;
    this.metronome.nextBeat = i;
  },

  scheduleClicks() {
    if (!this.playing || !this.metronome.on || !this.song) return;
    const a = this.song.analysis;
    const t = this.time();
    const lookahead = 0.15;
    const downbeats = new Set(a.downbeats);
    while (this.metronome.nextBeat < a.beats.length) {
      const beat = a.beats[this.metronome.nextBeat];
      if (beat > t + lookahead * this.speed) break;
      const when = this.ctx.currentTime + (beat - t) / this.speed;
      if (when >= this.ctx.currentTime - 0.01) this.click(Math.max(when, this.ctx.currentTime), downbeats.has(beat));
      this.metronome.nextBeat++;
    }
  },

  click(when, accent, force = false) {
    const volume = force ? Math.max(this.metronome.volume, 0.5) : this.metronome.volume;
    const osc = this.ctx.createOscillator();
    const env = this.ctx.createGain();
    osc.frequency.value = accent ? 1760 : 1175;
    env.gain.setValueAtTime(0, when);
    env.gain.linearRampToValueAtTime(volume, when + 0.002);
    env.gain.exponentialRampToValueAtTime(0.0001, when + 0.06);
    osc.connect(env).connect(this.ctx.destination);
    osc.start(when);
    osc.stop(when + 0.08);
  },

  // --------------------------------------------------------- waveform & loop

  drawWaveform(t = this.time()) {
    const canvas = $("waveform");
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    if (!w || !this.song) return;
    if (canvas.width !== Math.round(w * dpr)) {
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
    }
    const g = canvas.getContext("2d");
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);
    const dur = this.duration() || 1;
    const css = getComputedStyle(document.documentElement);
    const accent = css.getPropertyValue("--accent").trim();
    const muted = css.getPropertyValue("--border").trim();
    const violet = css.getPropertyValue("--violet").trim();

    const { a, b } = this.loop;
    if (a !== null) {
      const x0 = (a / dur) * w;
      const x1 = b !== null ? (b / dur) * w : x0 + 2;
      g.fillStyle = this.loop.on ? "rgba(167,139,250,.25)" : "rgba(167,139,250,.12)";
      g.fillRect(x0, 0, Math.max(2, x1 - x0), h);
    }
    const peaks = this.song.analysis.waveform;
    const playedX = (t / dur) * w;
    const barW = w / peaks.length;
    for (let i = 0; i < peaks.length; i++) {
      const x = i * barW;
      const ph = Math.max(1, peaks[i] * (h - 8));
      g.fillStyle = x < playedX ? accent : muted;
      g.fillRect(x, (h - ph) / 2, Math.max(1, barW - 0.5), ph);
    }
    g.fillStyle = violet;
    g.fillRect(playedX - 1, 0, 2, h);
  },

  canvasTime(e) {
    const rect = $("waveform").getBoundingClientRect();
    return Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width)) * this.duration();
  },

  onPointerDown(e) {
    if (!this.song) return;
    $("waveform").setPointerCapture(e.pointerId);
    this.drag = { start: this.canvasTime(e), moved: false };
  },

  onPointerMove(e) {
    if (!this.drag) return;
    const t = this.canvasTime(e);
    if (Math.abs(t - this.drag.start) > this.duration() * 0.005) {
      this.drag.moved = true;
      this.loop.a = Math.min(this.drag.start, t);
      this.loop.b = Math.max(this.drag.start, t);
      this.renderLoop();
    }
  },

  onPointerUp(e) {
    if (!this.drag) return;
    const { moved, start } = this.drag;
    this.drag = null;
    if (moved) {
      this.loop.a = this.snapToBeat(this.loop.a);
      this.loop.b = this.snapToBeat(this.loop.b);
      this.loop.on = true;
      this.renderLoop();
      this.seek(this.loop.a);
    } else {
      this.seek(start);
    }
  },

  snapToBeat(t) {
    const beats = this.song.analysis.beats;
    if (!beats.length) return t;
    let best = beats[0];
    for (const b of beats) if (Math.abs(b - t) < Math.abs(best - t)) best = b;
    return Math.abs(best - t) < 0.25 ? best : t;
  },

  setLoopPoint(which) {
    this.loop[which] = this.time();
    if (this.loop.a !== null && this.loop.b !== null && this.loop.b < this.loop.a) {
      [this.loop.a, this.loop.b] = [this.loop.b, this.loop.a];
    }
    if (this.loop.a !== null && this.loop.b !== null) this.loop.on = true;
    this.renderLoop();
  },

  renderLoop() {
    const { a, b, on } = this.loop;
    $("loop-on").checked = on;
    $("loop-on").disabled = a === null || b === null;
    $("loop-info").textContent = a === null && b === null
      ? "Or drag across the waveform."
      : `A ${a === null ? "–" : fmtTime(a)} → B ${b === null ? "–" : fmtTime(b)}`;
    this.drawWaveform();
  },

  // --------------------------------------------------------- export

  export() {
    if (!this.song) return;
    const params = new URLSearchParams({
      semitones: String(this.semitones),
      speed: String(this.speed),
      format: $("export-format").value,
      volumes: this.tracks.map((tr) => `${tr.name}:${this.effectiveGain(tr).toFixed(3)}`).join(","),
    });
    const a = document.createElement("a");
    a.href = `/api/songs/${this.song.id}/export?${params}`;
    a.download = "";
    document.body.append(a);
    a.click();
    a.remove();
    toast("Rendering your mix… the download starts when it is ready.");
  },

  // --------------------------------------------------------- keyboard

  onKey(e) {
    if (!this.song || $("player").hidden) return;
    if (e.target.matches("input, select, textarea") && e.key !== " ") return;
    if (e.target.matches("button") && e.key === " ") return;
    switch (e.key) {
      case " ": e.preventDefault(); this.toggle(); break;
      case "ArrowLeft": this.seek(this.time() - 5); break;
      case "ArrowRight": this.seek(this.time() + 5); break;
      case "[": this.setPitch(this.semitones - 1); break;
      case "]": this.setPitch(this.semitones + 1); break;
      case "l": case "L":
        if (this.loop.a !== null && this.loop.b !== null) { this.loop.on = !this.loop.on; this.renderLoop(); }
        break;
      case "m": case "M":
        this.metronome.on = !this.metronome.on;
        $("metronome").checked = this.metronome.on;
        this.resetMetronome();
        break;
      default: return;
    }
  },
};

// ---------------------------------------------------------------- routing

const router = {
  go(id) {
    location.hash = id ? `#/song/${id}` : "#";
  },
  async apply() {
    const match = location.hash.match(/^#\/song\/([0-9a-f]{32})$/);
    $("library").hidden = Boolean(match);
    $("player").hidden = !match;
    if (match) {
      await player.open(match[1]);
    } else {
      player.close();
      library.refresh();
    }
  },
};

$("back-btn").addEventListener("click", () => router.go(null));
$("home-link").addEventListener("click", (e) => { e.preventDefault(); router.go(null); });
window.addEventListener("hashchange", () => router.apply());
player.init();
library.init().then(() => router.apply());
