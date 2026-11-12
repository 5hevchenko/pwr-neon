"use strict";
// ============================================================
//  Мелочи для «вау»: живой баланс, «+N» под балансом, удачный момент, приветствие, яркий новый уровень
// ============================================================
// --- живой баланс: цифры прокручиваются к новому значению, под плашкой всплывает разница ---
let balAnim = null, balShown = null, meSoon = null;
setStars = function (s) {
  if (s == null || !ME) return;
  const old = ME.stars; ME.stars = s;
  const from = balShown ?? old, diff = s - old;
  cancelAnimationFrame(balAnim);
  const t0 = performance.now(), dur = Math.min(900, 300 + Math.abs(diff) / 50);
  (function step(t) {
    const k = Math.min(1, (t - t0) / dur), v = from + (s - from) * (1 - Math.pow(1 - k, 3));
    balShown = v; const n = $("#bal-n"); if (n) n.textContent = fmt(v);
    document.querySelectorAll(".bal-live").forEach(e => e.textContent = fmt(v));
    if (k < 1) balAnim = requestAnimationFrame(step); else balShown = null;
  })(t0);
  paintBalance(diff > 0 ? "up" : diff < 0 ? "down" : "");
  if (diff) { balFloat(diff); clearTimeout(meSoon); meSoon = setTimeout(() => loadMe().catch(() => {}), 2500); }   // заодно проверим «удачный момент»
};
function balFloat(d) {
  const b = $("#bal"); if (!b) return;
  const r = b.getBoundingClientRect(), f = document.createElement("b");
  f.className = "bal-float " + (d > 0 ? "up" : "dn"); f.textContent = (d > 0 ? "+" : "−") + short(Math.abs(d));
  f.style.left = r.left + r.width / 2 + "px"; f.style.top = r.bottom + 2 + "px";
  document.body.appendChild(f); setTimeout(() => f.remove(), 1100);
}
// --- «удачный момент»: сюрприз от казино приходит в /me ---
const _loadMeD = loadMe;
loadMe = async function () {
  await _loadMeD();
  if (ME && ME.surprise > 0 && !document.querySelector(".lucky")) luckyShow(ME.surprise);
};
async function luckyShow(amount) {
  post("surprise/ack").catch(() => {});
  ME.surprise = 0;
  const el = document.createElement("div");
  el.className = "lucky";
  el.innerHTML = `<div class="lucky-card"><div class="lucky-rays"></div><img src="${A.orig("Lucky Locket", 256)}" alt="" onerror="this.src='${A.orig("Clover Pin", 256)}'">
    <span>Удачный момент!</span><b>+⭐ ${fmt(amount)}</b><em>Игра дарит сюрприз — так бывает примерно раз в 170 раундов</em></div>`;
  document.body.appendChild(el); starify(el);
  requestAnimationFrame(() => el.classList.add("on"));
  H.ok(); setTimeout(() => coinShower(el.querySelector(".lucky-card"), 50), 250);
  const close = () => { el.classList.remove("on"); setTimeout(() => el.remove(), 350); };
  el.onclick = close; setTimeout(close, 3600);
}
// --- приветствие на главной ---
const _rcD = renderCases;
renderCases = async function () {
  await _rcD();
  return;   // приветствие убрано: дублировало плитки и перегружало главный экран
  const v = $("#v-cases"); if (!v || !ME || v.querySelector(".hello")) return;
  const h = new Date().getHours(), part = h < 5 ? "Доброй ночи" : h < 12 ? "Доброе утро" : h < 18 ? "Добрый день" : "Добрый вечер";
  const name = (ME.name || "").split(" ")[0];
  const tip = !ME.freeIn ? ["gift", "Бесплатный кейс уже ждёт", "case", "free"] : !ME.dailyIn ? ["calendar", "Бонус дня готов — забери", "daily", ""]
    : ME.keys ? ["lock", `У тебя ${ME.keys} ${plural(ME.keys, ["ключ", "ключа", "ключей"])} от кейсов`, "", ""]
    : ME.streak > 1 ? ["flame", `Серия ${ME.streak} ${plural(ME.streak, ["день", "дня", "дней"])} — не прерывай`, "daily", ""] : null;
  v.insertAdjacentHTML("afterbegin", `<div class="hello"><b>${part}${name ? ", " + esc(name) : ""}</b>${tip ? (tip[2] ? `<button data-act="${tip[2]}" ${tip[3] ? `data-id="${tip[3]}"` : ""}>${ic(tip[0])}${tip[1]}</button>` : `<span class="hello-t">${ic(tip[0])}${tip[1]}</span>`) : ""}</div>`);
};
// --- новый уровень: большое число, лучи и что открылось ---
afterLevelUp = async function (lv) {
  if (!lv) return;
  H.ok(); burst(innerWidth / 2, innerHeight / 3, ["#ffd76a", "#ffab2e", "#fff", "#ff6fb5"]);
  setTimeout(() => burst(innerWidth / 2, innerHeight / 3, ["#ffd76a", "#7cc2ff", "#fff"]), 300);
  const opened = (CASES || []).filter(c => c.level === lv.level);
  await modal(`<div class="lvup2"><div class="lv-rays"></div><span>Новый уровень</span><b>${lv.level}</b>
    <p>Бонус: <span class="star">+${fmt(lv.bonus)} ⭐</span></p>
    ${opened.length ? `<div class="lv-new">${opened.map(c => `<div><img src="${A.orig(c.cover, 128)}" alt=""><span>Открыт кейс «${esc(c.title)}»</span></div>`).join("")}</div>` : ""}
    <button class="btn gold" data-m="ok">Круто!</button></div>`);
  loadMe();
};
