"use strict";
// ============================================================
//  Арена (arena.py): общий раунд на звёзды. Ставка — сектор на кольце: больше ставка — шире сектор.
//  Время вышло — по кольцу катится мяч; на чьём секторе остановился, тот забирает банк.
// ============================================================
const AR_ICON = "data:image/svg+xml," + encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><circle cx="32" cy="32" r="24" fill="none" stroke="#4aa8ff" stroke-width="10" stroke-dasharray="60 91" transform="rotate(-90 32 32)"/><circle cx="32" cy="32" r="24" fill="none" stroke="#ff6fb5" stroke-width="10" stroke-dasharray="48 103" stroke-dashoffset="-62" transform="rotate(-90 32 32)"/><circle cx="32" cy="32" r="24" fill="none" stroke="#ffc53d" stroke-width="10" stroke-dasharray="37 114" stroke-dashoffset="-112" transform="rotate(-90 32 32)"/><circle cx="32" cy="8" r="6" fill="#fff"/></svg>`);
GAMES.splice(1, 0, { id: "arena", t: "Арена", s: "Общий банк: больше ставка — шире твой сектор. Мяч решит, кто заберёт всё", imgUrl: (window.GEN_ART || {}).game_arena || AR_ICON, k: ["#3c8dff", "#0a1a4a"], chips: ["все против всех", "PvP"] });
GCAT.arena = "top"; G_NEW.add("arena");
Object.assign(GAME_OPEN, { arena: () => openArena() });
let AR = null, arPoll = null, arSpun = 0, arShown = 0, arRound = 0, arBall = 0;
const AR_R = 84, AR_C = 2 * Math.PI * AR_R;
async function openArena() {
  const el = openSheet(`<div class="ghead">${gpfBtn("arena")}<img src="${(GAMES.find(g => g.id === "arena") || {}).imgUrl || AR_ICON}" alt=""><div><h2>Арена</h2><span>Больше ставка — шире сектор</span></div></div>
    <div class="ar-stage"><svg viewBox="0 0 200 200" id="ar-svg" aria-hidden="true"><circle cx="100" cy="100" r="${AR_R}" class="ar-track"/><g id="ar-secs"></g>
        <g id="ar-ball" style="transform:rotate(0deg)"><circle cx="100" cy="${100 - AR_R}" r="7.5" class="ar-b"/></g></svg>
      <div class="ar-hub" id="ar-hub"></div></div>
    <div class="ar-hist" id="ar-hist"></div>
    <div class="betp">${betHTML("ar-amt", 1000)}
      <div class="btns"><button class="btn cta gold" id="ar-go" data-act="ar-bet">Поставить</button></div>
      <div id="ar-cancel"></div></div>
    <div class="sec-t">Участники <span id="ar-n"></span></div><div id="ar-p"></div>
    <details class="rules"><summary>${ic("award")}Как играть</summary><div>Раунд общий на всех. Каждый ставит звёзды и получает сектор на кольце: его размер — твоя доля в банке. Можно ставить несколько раз, сектор будет расти. Когда в раунде двое, начинается отсчёт. Потом по кольцу катится мяч — на чьём секторе он остановился, тот забирает банк. Игра оставляет себе комиссию с банка. Пока ты в раунде один, ставку можно забрать.</div></details>`, "ar-s");
  el._onClose = () => clearInterval(arPoll);
  arSpun = 0; arShown = 0; arRound = 0; arBall = 0;
  await arLoad();
  clearInterval(arPoll); arPoll = setInterval(() => el.isConnected ? bgOff() || arLoad() : clearInterval(arPoll), 1000);
}
async function arLoad() {
  let d; try { d = await api("arena"); } catch (e) { return; }
  arTake(d);
}
function arTake(d) { AR = { history: AR && AR.history, ...d }; AR.off = AR.now - Date.now() / 1000; arDraw(); }
const arSet = (el, h) => { if (el && el._h !== h) { el._h = h; el.innerHTML = h; starify(el); } };
function arDraw() {
  const svg = $("#ar-svg"); if (!svg || !AR) return;
  const ps = AR.players, total = AR.total || 1, ball = $("#ar-ball");
  if (AR.id !== arRound) {   // новый раунд: мяч наверх без анимации
    arRound = AR.id; arBall = 0; ball.style.transition = "none"; ball.style.transform = "rotate(0deg)";
  }
  const spinning = AR.status !== "open";
  // сектора: дуги одного кольца, по порядку первой ставки, от верхней точки по часовой
  const key = AR.id + "|" + ps.map(p => p.id + ":" + p.amount).join(",") + "|" + (arShown === AR.id ? AR.winner : "");
  if (svg._k !== key) {
    svg._k = key;
    let acc = 0;
    $("#ar-secs").innerHTML = ps.map((p, i) => {
      const len = p.amount / total * AR_C, gap = ps.length > 1 ? Math.min(2.2, len * .25) : 0;
      const h = `<circle cx="100" cy="100" r="${AR_R}" class="ar-sec${arShown === AR.id ? (p.id === AR.winner ? " win" : " dim") : ""}" stroke="${SEG_COL[i % SEG_COL.length]}"
        stroke-dasharray="${Math.max(.5, len - gap).toFixed(2)} ${AR_C.toFixed(2)}" stroke-dashoffset="${(-acc - gap / 2).toFixed(2)}" transform="rotate(-90 100 100)"/>`;
      acc += len; return h;
    }).join("");
  }
  // мяч: билет 0..1 — это точка на кольце; катим несколько кругов и останавливаемся на ней
  if (spinning && arSpun !== AR.id && AR.ticket != null) {
    arSpun = AR.id;
    const t = Date.now() / 1000 + AR.off, left = Math.max(.3, AR.spinAt + AR.spin - t);
    const target = 360 * (left > 2 ? 5 : 0) + AR.ticket * 360;
    ball.style.transition = "none"; ball.style.transform = `rotate(${arBall % 360}deg)`; void ball.getBoundingClientRect();
    ball.style.transition = `transform ${left.toFixed(2)}s cubic-bezier(.1,.72,.16,1)`; ball.style.transform = `rotate(${target}deg)`;
    arBall = target;
    if (left > 2) { H.imp("medium"); if (typeof SND !== "undefined") SND.whoosh(); }
    const rid = AR.id;
    setTimeout(() => {
      if (!AR || AR.id !== rid || !$("#ar-svg")) return;
      arShown = rid;
      const me = AR.winner === ME.id;
      if (AR.mine) { me ? (H.ok(), toast(`Банк твой: +⭐ ${fmt(AR.paid)}`, "ok"), typeof coinShower === "function" && coinShower($("#ar-hub"), 30)) : H.err(); }
      loadMe().catch(() => {});
      arDraw();
    }, left * 1000 + 150);
  }
  const t = Date.now() / 1000 + AR.off;
  let hub;
  if (!spinning) {
    const left = AR.deadline ? Math.max(0, Math.ceil(AR.deadline - t)) : null;
    hub = `<small>в банке</small><b>⭐ ${short(AR.total)}</b><span>${left != null ? `ставки ещё ${left} с` : ps.length ? "ждём второго игрока" : "сделай первую ставку"}</span>`;
  } else if (arShown === AR.id) {
    const w = ps.find(p => p.id === AR.winner);
    hub = `<small>забрал банк</small><b>${esc(w ? w.name : "Игрок")}</b><span>⭐ ${short(AR.paid)}</span>`;
  } else hub = `<small>в банке</small><b>⭐ ${short(AR.total)}</b><span>мяч катится…</span>`;
  arSet($("#ar-hub"), hub);
  arSet($("#ar-n"), ps.length ? `· ${ps.length}` : "");
  arSet($("#ar-p"), ps.length ? `<div class="box">${ps.map((p, i) => `<div class="row ar-row${arShown === AR.id && p.id === AR.winner ? " win" : ""}">
      <i class="ar-dot" style="background:${SEG_COL[i % SEG_COL.length]}"></i>${avaHTML(p, 34)}<div class="grow"><div class="t">${esc(p.name)}${p.id === ME.id ? ` <span class="pill">ты</span>` : ""}</div>
      <div class="s">ставка ⭐ ${fmt(p.amount)}</div></div><b class="ar-ch">${String(p.chance).replace(".", ",")}%</b></div>`).join("")}</div>`
    : emptyHTML("users", "Пока никого. Первая ставка открывает раунд"));
  arSet($("#ar-hist"), (AR.history || []).map(h => `<span title="${esc(h.name)}">${avaHTML(h, 22)}<b>⭐ ${short(h.paid)}</b></span>`).join(""));
  const go = $("#ar-go"); if (go) { go.disabled = spinning; go.textContent = spinning ? "Раунд идёт" : AR.mine ? "Добавить к ставке" : "Поставить"; }
  arSet($("#ar-cancel"), !spinning && AR.mine && !AR.deadline ? `<button class="btn ghost ar-cb" data-act="ar-cancel">Забрать ставку ⭐ ${fmt(AR.mine)}</button>` : "");
}
Object.assign(ACT, {
  "ar-bet": async el => {
    const amount = betVal("ar-amt");
    if (!amount) return toast("Введи ставку");
    if (amount > ME.stars) { H.err(); return typeof openQuickBuy === "function" ? openQuickBuy(amount - ME.stars) : toast("Не хватает звёзд ⭐"); }
    el.disabled = true;
    try { const r = await post("arena/bet", { amount }); setStars(r.stars); H.ok(); arTake(r); } catch (e) {} finally { el.disabled = false; arDraw(); }
  },
  "ar-cancel": async el => {
    el.disabled = true;
    try { const r = await post("arena/cancel"); setStars(r.stars); H.sel(); toast("Ставка вернулась на баланс", "ok"); arTake(r); } catch (e) { el.disabled = false; }
  },
});
