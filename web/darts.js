"use strict";
// ============================================================
//  «Дартс» — бросок в мишень: зона попадания решает множитель, риск меняет таблицу (низкий — часто и понемногу, высокий — ради яблочка)
// ============================================================
const DT_ORDER = [20, 1, 18, 4, 13, 6, 10, 15, 2, 17, 3, 19, 7, 16, 8, 11, 14, 9, 12, 5];
const DT_RISK = [["low", "Низкий", "#35d07f"], ["mid", "Средний", "#ffc53d"], ["high", "Высокий", "#ff4d5e"]];
// зона → цвет в легенде и подсветке, радиусы (доли радиуса игрового поля)
const DT_Z = {
  bull: ["#ff3b4e", 0, .037, "Яблочко"], obull: ["#25c46b", .037, .094, "Внешнее яблочко"], treble: ["#ffc53d", .582, .629, "Утроение"],
  double: ["#ff6fb5", .953, 1, "Удвоение"], inner: ["#e9dcc0", .094, .582, "Ближний сектор"], outer: ["#9aa0b2", .629, .953, "Дальний сектор"], miss: ["#55596a", 1, 1.2, "Мимо"],
};
const DT_ZORD = ["bull", "obull", "treble", "double", "inner", "outer", "miss"];
const dtP = (r, a) => [r * Math.sin(a * Math.PI / 180), -r * Math.cos(a * Math.PI / 180)];
// сектор кольца r0..r1 между углами a0..a1 (от верха по часовой)
function dtArc(r0, r1, a0, a1) {
  const [x0, y0] = dtP(r1, a0), [x1, y1] = dtP(r1, a1), [x2, y2] = dtP(r0, a1), [x3, y3] = dtP(r0, a0), big = a1 - a0 > 180 ? 1 : 0;
  return `M${x0.toFixed(2)} ${y0.toFixed(2)}A${r1} ${r1} 0 ${big} 1 ${x1.toFixed(2)} ${y1.toFixed(2)}L${x2.toFixed(2)} ${y2.toFixed(2)}A${r0} ${r0} 0 ${big} 0 ${x3.toFixed(2)} ${y3.toFixed(2)}Z`;
}
// мишень: R = 100 — игровое поле, дальше кольцо с номерами и деревянный обод
function dtBoard(id = "b") {
  const R = 100, seg = [];
  for (let i = 0; i < 20; i++) {
    const a0 = i * 18 - 9, a1 = a0 + 18, dark = i % 2 === 0;
    const s = dark ? "#1b1a1d" : "#efe1c0", d = dark ? "#d2232f" : "#168a46";
    seg.push(`<path d="${dtArc(.094 * R, .582 * R, a0, a1)}" fill="${s}"/><path d="${dtArc(.629 * R, .953 * R, a0, a1)}" fill="${s}"/>`,
      `<path d="${dtArc(.582 * R, .629 * R, a0, a1)}" fill="${d}"/><path d="${dtArc(.953 * R, R, a0, a1)}" fill="${d}"/>`);
  }
  const wires = Array.from({ length: 20 }, (_, i) => { const [x0, y0] = dtP(.094 * R, i * 18 - 9), [x1, y1] = dtP(R, i * 18 - 9); return `M${x0.toFixed(2)} ${y0.toFixed(2)}L${x1.toFixed(2)} ${y1.toFixed(2)}`; }).join("");
  const nums = DT_ORDER.map((n, i) => { const [x, y] = dtP(110, i * 18); return `<text x="${x.toFixed(1)}" y="${(y + 4.2).toFixed(1)}">${n}</text>`; }).join("");
  return `<svg viewBox="-132 -132 264 264" class="dt-bsvg"><defs>
    <radialGradient id="dtw${id}" cx=".45" cy=".4" r=".65"><stop offset="0" stop-color="#6b4325"/><stop offset=".8" stop-color="#3b2312"/><stop offset="1" stop-color="#1f1208"/></radialGradient>
    <radialGradient id="dtl${id}" cx=".38" cy=".3" r=".8"><stop offset="0" stop-color="#fff" stop-opacity=".22"/><stop offset=".55" stop-color="#fff" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".35"/></radialGradient>
    <filter id="dtf${id}" x="0" y="0" width="1" height="1"><feTurbulence type="fractalNoise" baseFrequency="1.6" numOctaves="2" result="n"/><feColorMatrix in="n" values="0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 .35 0"/><feComposite in2="SourceGraphic" operator="in"/><feBlend in="SourceGraphic" mode="multiply"/></filter></defs>
    <circle r="131" fill="url(#dtw${id})"/><circle r="128" fill="none" stroke="rgba(255,255,255,.12)" stroke-width="1.5"/>
    <circle r="119" fill="#141316"/>
    <g filter="url(#dtf${id})">${seg.join("")}<circle r="${.094 * R}" fill="#168a46"/><circle r="${.037 * R}" fill="#d2232f"/></g>
    <g fill="none" stroke="#c9ced8" stroke-width=".7" opacity=".85"><path d="${wires}"/>${[.037, .094, .582, .629, .953, 1].map(k => `<circle r="${k * R}"/>`).join("")}</g>
    <g class="dt-num" fill="#f4f4f6" font-size="12" font-weight="800" text-anchor="middle" font-family="-apple-system,Roboto,Segoe UI,sans-serif">${nums}</g>
    <circle r="131" fill="url(#dtl${id})" pointer-events="none"/></svg>`;
}
// дротик: острие в (0,0), хвост уходит вниз-вправо (бросок снизу)
const DT_DART = `<svg viewBox="-6 -4 40 92" class="dt-dsvg"><defs>
  <linearGradient id="dtbar" x1="0" x2="1"><stop offset="0" stop-color="#3c404c"/><stop offset=".45" stop-color="#f1f3f8"/><stop offset="1" stop-color="#5a5f6e"/></linearGradient>
  <linearGradient id="dtfl" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ff5aa0"/><stop offset="1" stop-color="#8a2be2"/></linearGradient></defs>
  <g transform="rotate(-18 0 0)"><path d="M0 0l-1.1 14h2.2Z" fill="#d7dbe4"/><rect x="-3.2" y="14" width="6.4" height="24" rx="3" fill="url(#dtbar)"/>
  <g stroke="rgba(0,0,0,.35)" stroke-width="1"><path d="M-3 19h6M-3 23h6M-3 27h6M-3 31h6"/></g>
  <rect x="-1.6" y="38" width="3.2" height="16" fill="#2a2d38"/>
  <path d="M0 50 -11 78 -2 74 0 84 2 74 11 78Z" fill="url(#dtfl)"/><path d="M0 52v30" stroke="rgba(255,255,255,.5)" stroke-width="1.2"/></g></svg>`;
GAMES.push({ id: "darts", t: "Дартс", s: "Попади в яблочко — множитель до x20", imgUrl: "", k: ["#d2232f", "#160608"], chips: ["новинка", "3 риска"] });
GAMES[GAMES.length - 1].imgUrl = "data:image/svg+xml," + encodeURIComponent(dtBoard("c").replace('class="dt-bsvg"', 'xmlns="http://www.w3.org/2000/svg"'));
WIDE_GAMES.add("darts");
GAME_OPEN.darts = () => openDarts();
AR_NEW.push("darts");
GAME_NAMES.darts = ["crosshair", "Дартс"];

let DTS = null, dtRisk = "mid", dtBusy = false;
async function openDarts() {
  dtBusy = false;
  const el = openSheet(`<div class="ghead">${gpfBtn("darts")}<img src="${GAMES.find(g => g.id === "darts").imgUrl}" alt=""><div><h2>Дартс</h2><span>Один бросок — и всё решено</span></div></div>
    <div class="ar-stage dt-stage" id="dt-stage">
      <div class="dt-wall"></div><div class="dt-spot"></div>
      <div class="dt-board" id="dt-board">${dtBoard()}<svg viewBox="-132 -132 264 264" class="dt-fx" id="dt-fx"></svg><div class="dt-darts" id="dt-darts"></div>
        <div class="dt-aim" id="dt-aim"><i></i></div></div>
      <div class="ar-hud dt-hud"><div class="ar-sub" id="dt-sub"></div></div>
    </div>
    <div class="ar-legend" id="dt-leg"></div>
    <div class="betp">
      <div class="seg ar-seg" id="dt-risk">${DT_RISK.map(([k, t, c]) => `<button data-act="dt-risk" data-v="${k}" style="--c:${c}" class="${dtRisk === k ? "on" : ""}"><i></i>${t}</button>`).join("")}</div>
      ${betHTML("dt-amt")}
      <button class="btn cta gold" id="dt-btn" data-act="dt-throw">${ic("crosshair")} Бросить</button>
    </div>
    <details class="rules" style="margin-top:12px"><summary>${ic("award")}Как играть</summary><div id="dt-rules"></div></details>`, "dt-s");
  el._onClose = () => { dtBusy = false; };
  DTS = await api("darts").catch(() => null);
  if (!DTS || !$("#dt-stage")) return;
  $("#dt-rules").innerHTML = `Делаешь ставку и бросаешь дротик. Куда попал — такой и множитель. Шансы зон: ${DT_ZORD.map(z => `${DT_Z[z][3].toLowerCase()} — ${Math.round(DTS.chances[z] * 100)}%`).join(", ")}.
    Риск меняет таблицу выплат: низкий платит почти за всё, высокий — только за утроение и яблочко, зато много. Возврат игроку — ${String(DTS.rtp).replace(".", ",")}%.`;
  dtLegend();
}
function dtLegend(hit) {
  const t = DTS.tables[dtRisk];
  $("#dt-leg").innerHTML = DT_ZORD.map(z => `<span style="--c:${DT_Z[z][0]}" class="${hit === z ? "hit" : ""}"><i></i>${{ obull: "Кольцо 25", inner: "Ближний", outer: "Дальний" }[z] || DT_Z[z][3]}<b>${t[z] ? arX(t[z]) : "—"}</b></span>`).join("");
  $("#dt-sub").innerHTML = `<span class="ar-pill">${ic("crosshair")}Яблочко <b>${arX(t.bull)}</b></span><span class="ar-pill">${ic("target")}Утроение <b>${t.treble ? arX(t.treble) : "—"}</b></span>`;
}
async function dtThrow() {
  if (dtBusy || !DTS) return;
  const bet = betVal("dt-amt");
  if (bet > ME.stars) return toast("Не хватает звёзд ⭐");
  dtBusy = true; $("#dt-btn").disabled = true;
  let r;
  try { r = await post("darts/throw", { bet, risk: dtRisk }); } catch (e) { dtBusy = false; $("#dt-btn").disabled = false; return; }
  setStars(r.stars - r.pay); afterLevelUp(r.levelup);
  const st = $("#dt-stage"); if (!st) { dtBusy = false; setStars(r.stars); return; }
  st.querySelectorAll(".ar-banner").forEach(b => b.remove());
  await dtFly(r);
  if (!$("#dt-stage")) { dtBusy = false; setStars(r.stars); return; }
  setStars(r.stars);
  dtLegend(r.zone);
  dtFlash(r);
  const label = r.zone === "miss" ? "Мимо мишени" : r.zone === "bull" ? "Яблочко!" : r.zone === "obull" ? "Внешнее яблочко" :
    `${{ treble: "Утроение", double: "Удвоение", inner: "Сектор", outer: "Сектор" }[r.zone]} ${r.zone === "treble" ? r.score / 3 : r.zone === "double" ? r.score / 2 : r.score}`;
  if (r.pay > r.bet) { H.ok(); arBanner(st, "win", label, `+⭐ ${fmt(r.pay)}`, arX(r.mult)); coinShower(st, Math.min(70, 10 + r.mult * 5)); if (r.mult >= 5) await bigWin(r.pay, r.mult); }
  else if (r.pay > 0) { H.imp("light"); arBanner(st, "", label, `⭐ ${fmt(r.pay)}`, `${arX(r.mult)} — часть ставки вернулась`); }
  else { H.err(); arBanner(st, "lose", label, `−⭐ ${fmt(r.bet)}`); }
  dtBusy = false; if ($("#dt-btn")) $("#dt-btn").disabled = false;
}
// полёт: из-под низа экрана к точке, дротик уменьшается (уходит вдаль), в конце — удар и дрожь
async function dtFly(r) {
  const board = $("#dt-board"), box = $("#dt-darts"), aim = $("#dt-aim");
  const old = [...box.children]; if (old.length >= 3) { old[0].classList.add("out"); setTimeout(() => old[0].remove(), 300); }
  const sz = board.clientWidth, k = sz / 264, [px, py] = dtP(r.r * 100, r.a);
  const x = sz / 2 + px * k, y = sz / 2 + py * k;
  aim.classList.add("lock"); aim.style.left = x + "px"; aim.style.top = y + "px";
  SND.whiz(); H.imp("light");
  await sleep(220);
  const d = document.createElement("div"); d.className = "dt-dart fly"; d.innerHTML = DT_DART;
  d.style.cssText = `left:${x}px;top:${y}px;--fx:${sz * .25 - x * .3}px;--fy:${sz * 1.1}px`;
  box.appendChild(d);
  await sleep(430);
  if (!$("#dt-board")) return;
  d.classList.remove("fly"); d.classList.add("hit");
  aim.classList.remove("lock");
  SND.thunk(); H.imp(r.zone === "bull" ? "heavy" : "medium");
  board.classList.remove("thud"); void board.offsetWidth; board.classList.add("thud");
  if (r.zone !== "miss") arSparks($("#dt-stage"), board.offsetLeft + x, board.offsetTop + y, r.zone === "bull" ? 26 : 10, [DT_Z[r.zone][0], "#fff"], r.zone === "bull" ? 110 : 50);
  await sleep(260);
}
// подсветка зоны попадания на мишени
function dtFlash(r) {
  const fx = $("#dt-fx"); if (!fx) return;
  const [c, r0, r1] = DT_Z[r.zone]; if (r.zone === "miss") { fx.innerHTML = ""; return; }
  let d;
  if (r.zone === "bull") d = `<circle r="${r1 * 100}" fill="${c}"/>`;
  else if (r.zone === "obull") d = `<path d="${dtArc(r0 * 100, r1 * 100, 0, 359.9)}" fill="${c}"/>`;
  else { const seg = Math.round(((r.a % 360) + 360) % 360 / 18) % 20, a0 = seg * 18 - 9; d = `<path d="${dtArc(r0 * 100, r1 * 100, a0, a0 + 18)}" fill="${c}"/>`; }
  fx.innerHTML = `<g class="dt-glow" style="color:${c}">${d}</g>`;
}
Object.assign(ACT, {
  "dt-risk": el => { if (dtBusy) return; dtRisk = el.dataset.v; H.sel(); el.parentElement.querySelectorAll("button").forEach(b => b.classList.toggle("on", b === el)); if (DTS) dtLegend(); },
  "dt-throw": () => dtThrow(),
});
