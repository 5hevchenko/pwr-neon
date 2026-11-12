"use strict";
// ============================================================
//  Игра дня (gameday.py): баннер в «Играх», значок на карточке и экран с рейтингом дня
// ============================================================
let GD = null;
const gdArt = (g, s = 128) => g && (g.imgUrl || (g.img && A.orig(g.img, s))) || "";
const gdGame = id => GAMES.find(x => x.id === id);

function gdMark() {   // значок на строке игры: разделы перерисовываются, поэтому ставим его заново
  if (!GD) return;
  document.querySelectorAll(`.gcard.gl[data-id="${GD.gid}"]`).forEach(c => {
    c.classList.add("gl-day");
    const t = c.querySelector(".gc-t");
    if (t && !t.querySelector(".gl-dayb")) t.insertAdjacentHTML("beforeend", `<i class="gl-dayb">ИГРА ДНЯ</i>`);
  });
}
const _gdSec = gDrawSections;
gDrawSections = function () { _gdSec(); gdMark(); };

const _rgGd = renderGames;
renderGames = function () {
  _rgGd();
  const v = $("#v-games"); if (!v) return;
  api("gameday").then(d => {
    GD = d; if (!v.isConnected || v.querySelector(".gd-bar:not(.ivb-bar)")) return;
    gdMark();
    const g = gdGame(d.gid); if (!g) return;
    const art = gdArt(g);
    const bar = `<button class="gd-bar" data-act="gameday" style="--k1:${g.k[0]};--k2:${g.k[1]}"><span class="gd-art">${art ? `<img src="${art}" alt="">` : ic("games")}</span>
      <span class="grow"><i class="gd-tag">${ic("flame")}Игра дня</i><b>${esc(g.t)}</b><span class="gd-sub">${d.pool ? `фонд ⭐ ${short(d.pool)} и растёт` : "фонд растёт с каждым раундом"}</span></span>
      <em class="gd-left" data-left="${Date.now() / 1000 + d.left}">${clock(d.left)}</em>${ic("chev")}</button>`;
    const before = v.querySelector(".tr-bar"), anchor = v.querySelector(".prib, .evrib");
    const inv = v.querySelector(".ivb-bar");   // баннер приглашений (growth.js) всегда после Игры дня
    if (inv) inv.insertAdjacentHTML("beforebegin", bar);
    else if (before) before.insertAdjacentHTML("beforebegin", bar);
    else if (anchor) anchor.insertAdjacentHTML("afterend", bar);
    else v.insertAdjacentHTML("afterbegin", bar);
    starify(v.querySelector(".gd-bar"));
    gdTick();
  }).catch(() => {});
};
let gdT = 0;
function gdTick() {   // один таймер на баннер и экран
  clearInterval(gdT);
  gdT = setInterval(() => {
    const items = document.querySelectorAll("[data-left]");
    if (!items.length) return clearInterval(gdT);
    items.forEach(e => { e.textContent = clock(Math.max(0, +e.dataset.left - Date.now() / 1000)); });
  }, 1000);
}

async function openGameDay() {
  const el = openSheet(emptyHTML("hourglass", "Загружаем…"), "gd-s");
  GD = await api("gameday").catch(() => GD);
  if (!el.isConnected) return;
  if (!GD) return replaceSheet(el, emptyHTML("games", "Не удалось загрузить, попробуй ещё раз"));
  gdPaint(el);
  const poll = setInterval(async () => {
    if (!el.isConnected) return clearInterval(poll);
    if (bgOff()) return;
    const d = await api("gameday").catch(() => null);
    if (!d || !el.isConnected) return;
    GD = d;
    const box = el.querySelector("#gd-live");
    if (box) { box.innerHTML = gdLive(d); starify(box); }
  }, 15000);
}

function gdPrizes(d) {
  const lbl = ["Победитель", "Второе место", "Третье место"];
  return `<div class="gd-prizes">${d.shares.map((s, i) => `<div class="gd-pz p${i + 1}"><span>${i + 1}</span><b>⭐ ${short(d.prizes[i])}</b><em>${lbl[i]}</em></div>`).join("")}</div>`;
}

function gdLive(d) {
  const pct = d.cap ? Math.min(100, d.pool / d.cap * 100) : 0;
  const elig = d.me.pts >= d.minPts;
  return `<div class="gd-fund"><div class="gd-fund-h"><span>Призовой фонд</span><b>⭐ ${fmt(d.pool)}</b></div>
      <div class="gd-track"><i style="width:${Math.max(pct, d.pool ? 2 : 0)}%"></i></div>
      <div class="gd-fund-f"><span>${d.players ? `${fmt(d.players)} ${plural(d.players, ["игрок", "игрока", "игроков"])} сегодня` : "Пока никто не играл"}</span><span>до ⭐ ${short(d.cap)}</span></div></div>
    ${gdPrizes(d)}
    ${d.top.length ? `<div class="sec-t">${ic("trophy")}Рейтинг дня</div><div class="box gd-rows gd-top">${d.top.map(r => `<div class="row tap${r.id === ME.id ? " me" : ""}" data-act="profile" data-id="${r.id}"><span class="place gd-p${r.place}">${r.place}</span>${avaHTML(r, 34)}
        <div class="grow"><div class="t">${nameHTML(r)}</div>${r.prize ? `<div class="s tw">приз ⭐ ${short(r.prize)}</div>` : ""}</div><b class="num">${fmt(r.pts)}<small> очк.</small></b></div>`).join("")}</div>`
      : emptyHTML("trophy", "Рейтинг пуст, первое место свободно")}
    <div class="tr-me gd-me"><span>Ты</span><b>${d.me.place ? d.me.place + " место" : "вне рейтинга"}</b><em>${fmt(d.me.pts)} очк.</em></div>
    ${elig ? "" : `<div class="gd-need">${ic("target")}<span>До приза нужно минимум ${fmt(d.minPts)} ${plural(d.minPts, ["очко", "очка", "очков"])}, у тебя ${fmt(d.me.pts)}</span></div>`}`;
}

function gdPaint(el) {
  const d = GD, g = gdGame(d.gid) || { t: d.title, k: ["#7b5cff", "#130b33"] }, art = gdArt(g, 256), l = d.last, lg = l && gdGame(l.gid);
  replaceSheet(el, `<div class="gd-hero" style="--k1:${g.k[0]};--k2:${g.k[1]}">
      <div class="gd-rays"></div>
      <span class="gd-bigart">${art ? `<img src="${art}" alt="">` : ic("games")}</span>
      <i class="gd-tag">${ic("flame")}Игра дня</i>
      <h2>${esc(g.t)}</h2>
      <div class="gd-time">${ic("clock")}до итогов <b data-left="${Date.now() / 1000 + d.left}">${clock(d.left)}</b></div>
    </div>
    <button class="btn gold gd-play" data-act="gd-play" data-id="${d.gid}">${ic("games")}Играть</button>
    <div id="gd-live">${gdLive(d)}</div>
    ${l && l.top.length ? `<div class="sec-t">${ic("award")}<span>Прошлая Игра дня</span>&nbsp;·&nbsp;<span>${esc(lg ? lg.t : l.title)}</span></div><div class="box gd-rows">${l.top.map(r => `<div class="row tap" data-act="profile" data-id="${r.id}"><span class="place gd-p${r.place}">${r.place}</span>${avaHTML(r, 34)}
        <div class="grow"><div class="t">${nameHTML(r)}</div></div><b class="num star">+⭐ ${short(r.prize)}</b></div>`).join("")}</div>` : ""}
    <div class="disc">Каждый день одна из редких игр получает свой рейтинг. Очко даётся за каждые ⭐ 100 выигрыша или проигрыша в раунде, один раунд приносит не больше 100 очков: решает активность, а не одна крупная ставка. Фонд растёт от того, сколько сыграно в эту игру сегодня, призы начисляются после полуночи по Москве. Победитель получает титул «Игрок дня» и золотую рамку на сутки.</div>`);
  starify(el); gdTick();
}
Object.assign(ACT, {
  gameday: () => openGameDay(),
  "gd-play": el => { closeSheet(); ACT.game(el); },
});
