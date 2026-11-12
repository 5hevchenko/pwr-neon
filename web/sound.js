"use strict";
// ============================================================
//  Звуки без файлов: синтез через WebAudio. Привязаны к вибро-откликам H.* (тик, клик, выигрыш, проигрыш),
//  плюс монеты и фанфары большого выигрыша. Выключаются в Настройках (PREF.noSound).
// ============================================================
const SND = (() => {
  let ctx = null, master = null, lastTick = 0;
  const on = () => !(typeof PREF !== "undefined" && PREF.noSound);
  function init() {
    if (ctx) return ctx;
    try {
      ctx = new (window.AudioContext || window.webkitAudioContext)();
      master = ctx.createGain(); master.gain.value = .55; master.connect(ctx.destination);
    } catch (e) { ctx = null; }
    return ctx;
  }
  // браузеры разрешают звук только после касания — будим контекст на первом тапе
  addEventListener("pointerdown", () => { const c = init(); if (c && c.state === "suspended") c.resume(); }, { passive: true });
  function tone(freq, dur, { type = "sine", gain = .08, at = 0, slide = 0, attack = .004 } = {}) {
    if (!on() || !init() || ctx.state !== "running") return;
    const t = ctx.currentTime + at, o = ctx.createOscillator(), g = ctx.createGain();
    o.type = type; o.frequency.setValueAtTime(freq, t);
    if (slide) o.frequency.exponentialRampToValueAtTime(Math.max(30, freq * slide), t + dur);
    g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(gain, t + attack); g.gain.exponentialRampToValueAtTime(.0001, t + dur);
    o.connect(g); g.connect(master); o.start(t); o.stop(t + dur + .02);
  }
  // шум (взрывы, всплески, шипение): буфер белого шума через фильтр
  let nbuf = null;
  function noise(dur, { gain = .1, at = 0, type = "lowpass", freq = 1200, q = .7, sweep = 0, attack = .003 } = {}) {
    if (!on() || !init() || ctx.state !== "running") return;
    if (!nbuf) { nbuf = ctx.createBuffer(1, ctx.sampleRate * 1.5, ctx.sampleRate); const d = nbuf.getChannelData(0); for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1; }
    const t = ctx.currentTime + at, s = ctx.createBufferSource(), f = ctx.createBiquadFilter(), g = ctx.createGain();
    s.buffer = nbuf; s.loop = true; f.type = type; f.frequency.setValueAtTime(freq, t); f.Q.value = q;
    if (sweep) f.frequency.exponentialRampToValueAtTime(Math.max(40, freq * sweep), t + dur);
    g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(gain, t + attack); g.gain.exponentialRampToValueAtTime(.0001, t + dur);
    s.connect(f); f.connect(g); g.connect(master); s.start(t); s.stop(t + dur + .02);
  }
  return {
    // новые игры: шар, бур, дартс, рыбалка
    pump(k = 0) { noise(.22, { gain: .05, type: "bandpass", freq: 900 + k * 60, q: 1.2, sweep: 1.6, attack: .05 }); tone(140 + k * 9, .12, { gain: .05, slide: 1.3 }); },
    pop() { noise(.35, { gain: .32, freq: 3200, sweep: .2 }); tone(120, .25, { gain: .2, slide: .4 }); noise(.08, { gain: .2, type: "highpass", freq: 4000 }); },
    float() { [784, 988, 1175, 1568].forEach((f, i) => tone(f, .35, { type: "triangle", gain: .04, at: i * .06, slide: 1.02 })); },
    drill(dur = 1) { noise(dur, { gain: .06, type: "bandpass", freq: 260, q: 3, attack: .08 }); tone(55, dur, { type: "sawtooth", gain: .025, attack: .08 }); },
    // кено и пенальти
    ball(k = 0) { tone(520 + k * 40, .09, { type: "triangle", gain: .05 }); noise(.05, { gain: .05, type: "bandpass", freq: 1800, q: 3 }); },
    gem(k = 0) { [1, 1.5, 2].forEach((m, i) => tone((880 + k * 70) * m, .22, { type: "triangle", gain: .04, at: i * .05 })); },
    kick() { tone(110, .14, { gain: .3, slide: .5 }); noise(.08, { gain: .2, freq: 900, sweep: .4 }); noise(.35, { gain: .04, type: "bandpass", freq: 1200, q: 1.5, sweep: 3, at: .04, attack: .05 }); },
    net() { noise(.4, { gain: .1, type: "bandpass", freq: 700, q: .8, sweep: .5, attack: .01 }); },
    crowd(big) { noise(big ? 2.2 : 1.4, { gain: big ? .14 : .09, type: "bandpass", freq: 900, q: .5, attack: .25 }); noise(big ? 1.8 : 1.1, { gain: .05, type: "bandpass", freq: 2400, q: .7, attack: .3, at: .1 }); },
    save() { tone(180, .2, { gain: .18, slide: .6 }); noise(.15, { gain: .12, freq: 600, sweep: .4 }); noise(.9, { gain: .06, type: "bandpass", freq: 500, q: .6, attack: .2, at: .1 }); },
    crack() { noise(.18, { gain: .2, type: "highpass", freq: 1800, sweep: .5 }); tone(90, .3, { gain: .12, slide: .5 }); },
    whiz() { noise(.32, { gain: .06, type: "bandpass", freq: 900, q: 2, sweep: 4, attack: .06 }); },
    thunk() { tone(160, .16, { gain: .22, slide: .45 }); noise(.06, { gain: .14, freq: 2500 }); tone(1300, .05, { type: "triangle", gain: .03, at: .01 }); },
    cast() { noise(.5, { gain: .05, type: "bandpass", freq: 500, q: 1.5, sweep: 6, attack: .1 }); },
    splash(big) { noise(big ? .7 : .4, { gain: big ? .22 : .12, freq: 2200, sweep: .25, attack: .01 }); noise(.25, { gain: .06, type: "highpass", freq: 3500, at: .05 }); },
    bite() { tone(660, .08, { type: "square", gain: .04 }); tone(990, .1, { type: "square", gain: .04, at: .09 }); },
    reel() { const n = performance.now(); if (n - lastTick < 55) return; lastTick = n; tone(2600 + Math.random() * 300, .02, { type: "square", gain: .012 }); },
    snap() { noise(.12, { gain: .25, type: "highpass", freq: 2500 }); tone(1800, .18, { type: "triangle", gain: .06, slide: .3 }); },
    tick() { const n = performance.now(); if (n - lastTick < 40) return; lastTick = n; tone(1900, .03, { type: "triangle", gain: .035 }); },
    click(s) { const f = { light: 1100, medium: 700, heavy: 180, rigid: 900, soft: 600 }[s] || 800; tone(f, s === "heavy" ? .14 : .05, { type: s === "heavy" ? "sine" : "triangle", gain: s === "heavy" ? .16 : .05, slide: s === "heavy" ? .5 : 1 }); },
    win() { [1047, 1319, 1568].forEach((f, i) => tone(f, .22, { type: "triangle", gain: .07, at: i * .07 })); tone(2093, .35, { gain: .04, at: .21 }); },
    lose() { tone(330, .28, { type: "sawtooth", gain: .035, slide: .45 }); tone(220, .3, { type: "sine", gain: .06, at: .05, slide: .5 }); },
    coins(n = 6) { for (let i = 0; i < Math.min(n, 14); i++) { const at = i * (.045 + Math.random() * .04); tone(2400 + Math.random() * 900, .09, { gain: .03, at }); tone(3600 + Math.random() * 600, .06, { gain: .015, at: at + .01 }); } },
    fanfare() { [523, 659, 784, 1047, 1319, 1568, 2093].forEach((f, i) => tone(f, .5, { type: "triangle", gain: .06, at: i * .085 })); [1047, 1319, 1568].forEach(f => tone(f, 1.2, { gain: .035, at: .62 })); },
    near() { tone(880, .12, { type: "square", gain: .03 }); tone(830, .25, { type: "square", gain: .03, at: .12, slide: .9 }); },
    whoosh() { tone(400, .35, { type: "sawtooth", gain: .02, slide: 3 }); },
  };
})();
// вибро-отклики → звуки
{
  const imp = H.imp, sel = H.sel, ok = H.ok, err = H.err;
  H.imp = s => { imp(s); SND.click(s); };
  H.sel = () => { sel(); SND.tick(); };
  H.ok = () => { ok(); SND.win(); };
  H.err = () => { err(); SND.lose(); };
}
// монеты и большой выигрыш
{
  const cs = coinShower, bw = bigWin;
  coinShower = (el, n = 40) => { SND.coins(Math.round(n / 5)); return cs(el, n); };
  bigWin = (pay, x, tierX) => { if (x >= 5 || (tierX || 0) >= 5) SND.fanfare(); return bw(pay, x, tierX); };
}
// волна от касания на кнопках
document.addEventListener("pointerdown", e => {
  const b = e.target.closest(".btn,.quick button,.seg button,.mk2-tabs button,.shop-row,.al-t .btn"); if (!b || b.disabled || window.LITE) return;
  const r = b.getBoundingClientRect(), s = Math.max(r.width, r.height) * 2.2, w = document.createElement("i");
  w.className = "ripple"; w.style.cssText = `width:${s}px;height:${s}px;left:${e.clientX - r.left - s / 2}px;top:${e.clientY - r.top - s / 2}px`;
  if (getComputedStyle(b).position === "static") b.style.position = "relative";
  b.style.overflow = "hidden"; b.appendChild(w); setTimeout(() => w.remove(), 600);
}, { passive: true });
