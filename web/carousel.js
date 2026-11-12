"use strict";
// ============================================================
//  Карусель: общее колесо, ставки на секторы, три бонуса
// ============================================================
const CR_COL = { x2: "#4f8cff", x4: "#2fd08a", x8: "#ff8a3d", x16: "#ff4f7b", safe: "#ffc53d", ladder: "#9b6bff", bomb: "#e8e8ee" };
// колесо: 40 секторов, число каждого — по вероятности; порядок постоянный
const CR_WHEEL = (() => {
  const n = { x2: 15, x4: 9, x8: 5, x16: 2, safe: 4, ladder: 3, bomb: 2 }, out = [], left = { ...n }, keys = Object.keys(n);
  for (let i = 0; i < 40; i++) { const k = keys.slice().sort((a, b) => left[b] / n[b] - left[a] / n[a] || n[b] - n[a]).find(x => left[x] > 0 && x !== out[out.length - 1]) || keys.find(x => left[x] > 0); out.push(k); left[k]--; }
  return out;
})();
const CRS = { st: null, t: null, off: 0, angle: 0, lastSpin: 0, amt: 100 };
const CR_LBL = LANG === "en" ? { x2: "2.5", x4: "4", x8: "8", x16: "16", safe: "S", ladder: "L", bomb: "B" } : { x2: "2,5", x4: "4", x8: "8", x16: "16", safe: "С", ladder: "Л", bomb: "Б" };
const CR_DARK = { safe: 1, bomb: 1 };
function crSVG() {   // секторы с подписями; 0° — верх колеса
  const R = 100, pt = (a, r) => { const t = (a - 90) * Math.PI / 180; return `${(100 + r * Math.cos(t)).toFixed(2)} ${(100 + r * Math.sin(t)).toFixed(2)}`; };
  return `<svg viewBox="0 0 200 200" aria-hidden="true">${CR_WHEEL.map((k, i) => { const a = i * 9, m = a + 4.5;
    return `<path d="M100 100L${pt(a, R)}A${R} ${R} 0 0 1 ${pt(a + 9, R)}Z" fill="${CR_COL[k]}" stroke="#0b0b12" stroke-width=".5"/>
      <text transform="rotate(${m} 100 100)" x="100" y="11" text-anchor="middle" font-size="7.5" font-weight="800" fill="${CR_DARK[k] ? "#14141c" : "#fff"}">${CR_LBL[k]}</text>`; }).join("")}</svg>`;
}
async function openCarousel() {
  const el = openSheet(`<div class="ghead">${gpfBtn("carousel")}<img src="${CR_ICON}" alt=""><div><h2>Карусель</h2></div></div>
    <div class="cr-stage"><i class="cr-pin"></i><div class="cr-wheel" id="cr-wheel">${crSVG()}</div>
      <div class="cr-hub"><b id="cr-time">—</b><span id="cr-ph"></span></div></div>
    <div class="cr-hist" id="cr-hist"></div><div id="cr-bonus"></div>
    <div class="cr-grid" id="cr-grid"></div><div class="cr-grid b3" id="cr-grid2"></div>
    <div class="betp">${betHTML("cr-amt", CRS.amt)}</div>
    <details class="rules"><summary>${ic("award")}Как играть</summary><div>Раунд общий на всех. Ставь на один или несколько секторов: если колесо остановится на нём, получишь ставку × множитель. Бонусы: в «Сейфе» угадай цифру, в «Лестнице» и «Бомбе» выбери, насколько рискнуть. Чем выше риск, тем больше выигрыш, средний возврат одинаковый.</div></details>`, "cr-s");
  CRS.lastSpin = 0;
  await crPoll();
  clearInterval(CRS.t);
  CRS.t = setInterval(() => { if (!el.isConnected) return clearInterval(CRS.t); if (!bgOff()) crPoll(); crTick(); }, 1000);
}
async function crPoll() {
  try { CRS.st = await api("carousel"); CRS.off = CRS.st.now - Date.now() / 1000; } catch (e) { return; }
  crDraw();
}
const crLeft = () => Math.max(0, CRS.st.until - (Date.now() / 1000 + CRS.off));
function crTick() { const t = $("#cr-time"); if (t && CRS.st) t.textContent = Math.ceil(crLeft()); }
function crDraw() {
  const s = CRS.st, g = $("#cr-grid"); if (!g || !s) return;
  const PH = { bet: "ставки", spin: "крутим", bonus: "бонус", show: "итог" };
  $("#cr-ph").textContent = s.phase === "show" && s.delta != null ? (s.delta >= 0 ? "+" : "−") + short(Math.abs(s.delta)) : PH[s.phase];
  crTick();
  if (s.sector && CRS.lastSpin !== s.round) {   // колесо останавливается на секторе результата
    CRS.lastSpin = s.round;
    const idx = CR_WHEEL.map((k, i) => k === s.sector ? i : -1).filter(i => i >= 0), pick = idx[s.round % idx.length];
    CRS.angle += 360 * 5 + ((360 - pick * 9 - 4.5) - CRS.angle % 360 + 360) % 360;
    const w = $("#cr-wheel"); if (w) w.style.transform = `rotate(${CRS.angle}deg)`;
  }
  const can = s.phase === "bet";
  const secBtn = x => `<button class="cr-sec${s.sector === x.id && s.phase !== "bet" ? " hit" : ""}" style="--c:${CR_COL[x.id]}" data-act="cr-bet" data-v="${x.id}" ${can ? "" : "disabled"}>
      <b>${esc(x.title)}</b><small>${x.p}%</small>${s.mine[x.id] ? `<em>⭐ ${short(s.mine[x.id])}</em>` : ""}</button>`;
  g.innerHTML = s.sectors.filter(x => x.mult).map(secBtn).join("");
  const g2 = $("#cr-grid2"); if (g2) { g2.innerHTML = s.sectors.filter(x => !x.mult).map(secBtn).join(""); starify(g2); }
  $("#cr-hist").innerHTML = s.history.map(h => `<i style="--c:${CR_COL[h.sector]}"></i>`).join("");
  const bx = $("#cr-bonus"); if (bx) { const h = crBonusHTML(s); if (bx._h !== h) { bx._h = h; bx.innerHTML = h; starify(bx); } }
  starify(g);
}
function crBonusHTML(s) {
  const b = s.sector; if (!["safe", "ladder", "bomb"].includes(b) || s.phase === "bet" || s.phase === "spin") return "";
  const joined = s.mine[b], title = { safe: "Сейф", ladder: "Лестница", bomb: "Бомба" }[b];
  if (s.phase === "show") {
    const o = s.bonus || {};
    return `<div class="cr-bo"><b>${title}</b><p>${b === "safe" ? `Код: ${o.digit}` : b === "ladder" ? `Дошли до ступени ${o.top}` : `Взрыв на шаге ${o.at}`}</p></div>`;
  }
  if (!joined) return `<div class="cr-bo"><b>${title}</b><p>Бонус играют те, кто на него поставил.</p></div>`;
  const opt = b === "safe" ? [...Array(10).keys()] : b === "ladder" ? [1, 2, 3, 4, 5, 6] : [1, 2, 3, 4, 5, 6, 7, 8, 9];
  const hint = b === "safe" ? "Угадай цифру сейфа: угаданная платит в 5 раз больше." : b === "ladder" ? "До какой ступени идёшь? Выше риск и больше выплата." : "На каком шаге хватаешь бомбу? Не успел до взрыва — ставка сгорает.";
  return `<div class="cr-bo"><b>${title}</b><p>${hint}</p><div class="cr-opts">${opt.map(v => `<button data-act="cr-choice" data-v="${v}" class="${s.choice === v ? "on" : ""}">${v}</button>`).join("")}</div></div>`;
}
Object.assign(ACT, {
  "cr-bet": async el => {
    try { const r = await post("carousel/bet", { sector: el.dataset.v, amount: betVal("cr-amt") }); CRS.st = r; CRS.off = r.now - Date.now() / 1000; CRS.amt = betVal("cr-amt"); if (r.stars != null) setStars(r.stars); H.sel(); crDraw(); } catch (e) {}
  },
  "cr-choice": async el => { try { CRS.st = await post("carousel/choice", { value: +el.dataset.v }); H.sel(); const bx = $("#cr-bonus"); if (bx) bx._h = ""; crDraw(); } catch (e) {} },
});
GAME_OPEN.carousel = openCarousel;
