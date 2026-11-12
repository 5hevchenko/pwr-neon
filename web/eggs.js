"use strict";
// ============================================================
//  Пасхалки. Звёзд не дают — находка уходит в коллекцию (POST egg),
//  за 7 находок — достижение «Охотник за пасхалками» (значок в профиль).
// ============================================================
const EGG = { seen: new Set(), taps: {} };
async function eggFound(id, hello) {   // hello — фраза пасхалки, показываем только при первой находке
  if (EGG.seen.has(id)) return;
  EGG.seen.add(id);
  try {
    const r = await post("egg", { id });
    if (r.new) { H.ok(); toast((hello ? hello + " · " : "") + `🥚 Пасхалка «${r.name}» · ${r.found} из ${r.total}`, "ok"); }
  } catch (e) { EGG.seen.delete(id); }
}
// n тапов подряд по одному месту (пауза больше 1.2 с — счёт заново)
function eggTaps(key, n) {
  const t = Date.now(), s = EGG.taps[key] || { c: 0, t: 0 };
  s.c = t - s.t < 1200 ? s.c + 1 : 1; s.t = t; EGG.taps[key] = s;
  if (s.c >= n) { s.c = 0; return true; }
  return false;
}
function eggRain() {
  const w = innerWidth, cols = ["#ffd76a", "#ffb800", "#fff3c4", "#ffe08a"];
  for (let i = 0; i < 6; i++) setTimeout(() => burst(w * (.1 + Math.random() * .8), -10, cols, 30), i * 160);
}
function eggNeedle() {
  const n = $("#u-needle"); if (!n || UP.busy) return;
  UP.busy = true;
  const a0 = UP.angle, a1 = a0 + 1080, t0 = performance.now(), d = 1400;
  (function f(t) {
    const k = Math.min(1, (t - t0) / d), e = 1 - Math.pow(1 - k, 3);
    n.style.transform = `rotate(${a0 + (a1 - a0) * e}deg)`;
    if (k < 1 && n.isConnected) requestAnimationFrame(f); else { UP.angle = a1; UP.busy = false; }
  })(t0);
}
document.addEventListener("click", e => {
  const t = e.target;
  if (!t || !t.closest) return;
  if (t.closest(".pay-num") && eggTaps("rain", 7)) { H.imp("heavy"); eggRain(); eggFound("rain"); }
  else if (t.closest(".pf-ava") && eggTaps("spin", 7)) {
    const a = t.closest(".pf-ava"); a.classList.remove("egg-roll"); void a.offsetWidth; a.classList.add("egg-roll");
    H.imp("medium"); eggFound("spin");
  }
  else if (t.closest("#u-center") && eggTaps("needle", 5) && !UP.busy) { H.imp("light"); eggNeedle(); eggFound("needle"); }
}, true);
document.addEventListener("input", e => {
  const t = e.target;
  if (t && t.classList && t.classList.contains("pay-q") && t.value.trim().toLowerCase() === "iddqd") {
    document.body.classList.remove("egg-god"); void document.body.offsetWidth; document.body.classList.add("egg-god");
    setTimeout(() => document.body.classList.remove("egg-god"), 1600);
    H.imp("heavy"); toast("😇 Режим бога включён… на секунду. Шансы, увы, всё те же", "ok");
    eggFound("iddqd");
  }
}, true);
// по времени захода: ждём, пока загрузится профиль
(function eggTime(n = 0) {
  if (typeof ME === "undefined" || !ME) { if (n < 40) setTimeout(() => eggTime(n + 1), 500); return; }
  const d = new Date(), h = d.getHours(), m = d.getMonth(), day = d.getDate();
  if (h >= 3 && h < 5) eggFound("owl", "🦉 Совы не спят. Ты тоже?");
  if (d.getDay() === 5 && day === 13) eggFound("fri13", "🖤 Пятница, 13-е. Удачи… она тебе пригодится");
  if ((m === 11 && day === 31) || (m === 0 && day === 1)) { setTimeout(() => burst(innerWidth / 2, innerHeight / 3, ["#ff5c5c", "#4cf0a0", "#ffd76a", "#7cc2ff", "#fff"], 140), 300); eggFound("ny"); }
})();
