"use strict";
// ============================================================
//  Наследие (legacy.py): итоги прошлых сезонов в профиле и зал славы. Вайп их не трогает.
// ============================================================
const LG = new Map();
const lgDate = ts => { const d = new Date(ts * 1000); return String(d.getDate()).padStart(2, "0") + "." + String(d.getMonth() + 1).padStart(2, "0"); };   // числами: не зависит от языка
const lgTier = p => p === 1 ? "t1" : p === 2 ? "t2" : p === 3 ? "t3" : p && p <= 10 ? "t10" : "";

function lgBody(p) {
  const hit = LG.get(p.id);
  if (hit && Date.now() - hit.at < 60000) return `<div id="lg-body">${lgPaint(hit.d, p)}</div>`;
  api("legacy/" + p.id).then(d => {
    LG.set(p.id, { d, at: Date.now() });
    const el = $("#lg-body");
    if (el && el.closest(".sheet")._p === p) { el.innerHTML = lgPaint(d, p); starify(el); }
  }).catch(() => { const el = $("#lg-body"); if (el) el.innerHTML = emptyHTML("crown", "Не удалось загрузить, попробуй ещё раз"); });
  return `<div id="lg-body">${emptyHTML("hourglass", "Загружаем…")}</div>`;
}

function lgMedal(place) {
  return `<div class="leg-medal"><span>${place ? (place <= 3 ? ic("crown") : "") : ic("flame")}</span><b>${place || "—"}</b><em>${place ? "место" : "сезон"}</em></div>`;
}

function lgSeason(s) {
  const turn = s.won + s.lost;
  return `<div class="leg-card ${lgTier(s.place)}">
    <div class="leg-top">${lgMedal(s.place)}
      <div class="grow"><h4>Сезон ${s.season}</h4><div class="leg-d">${lgDate(s.from || s.to)} — ${lgDate(s.to)} · из ${fmt(s.players)} ${plural(s.players, ["игрока", "игроков", "игроков"])}</div>
        ${s.bestGame ? `<div class="leg-fav">${ic("heart")}${esc(s.bestGame)}</div>` : ""}</div>
      ${s.gift ? `<div class="leg-gift">${giftHTML(s.gift, { lite: true, plain: true })}</div>` : ""}</div>
    <div class="leg-stats">
      <div><span>Раундов</span><b>${short(s.rounds)}</b></div>
      <div><span>Оборот</span><b>⭐ ${short(turn)}</b></div>
      <div><span>Лучший выигрыш</span><b class="star">⭐ ${short(s.best)}</b></div>
      <div><span>В игре</span><b>${s.hours >= 1 ? Math.round(s.hours) + " ч" : "&lt;1 ч"}</b></div>
    </div></div>`;
}

function lgPaint(d, p) {
  const c = d.current, m = d.summary, isMe = p.id === ME.id;
  const tile = (i, t, v) => `<div class="leg-t"><span>${ic(i)}</span><b>${v}</b><em>${t}</em></div>`;
  const summary = `<div class="leg-sum">${tile("calendar", "Сезонов", fmt(m.count))}${tile("crown", "Лучшее место", m.bestPlace || "—")}${tile("coins", "Лучший выигрыш", m.bestWin ? "⭐ " + short(m.bestWin) : "—")}${tile("trophy", "Побед в Игре дня", fmt(m.dayWins))}</div>`;
  const now = `<div class="leg-card leg-now">
    <div class="leg-top">${lgMedal(c.place)}
      <div class="grow"><h4>Сезон ${c.season}<i class="leg-live">идёт сейчас</i></h4>
        <div class="leg-d">${c.place ? `из ${fmt(c.players)} ${plural(c.players, ["игрока", "игроков", "игроков"])}` : (isMe ? "Сыграй раунд, чтобы попасть в рейтинг" : "В этом сезоне ещё не играл")}</div></div></div>
    ${c.place ? `<div class="leg-stats two"><div><span>Раундов</span><b>${short(c.rounds)}</b></div><div><span>Лучший выигрыш</span><b class="star">⭐ ${short(c.best)}</b></div></div>` : ""}</div>`;
  return `${summary}${now}
    ${d.seasons.length ? d.seasons.map(lgSeason).join("") : `<div class="leg-empty">${isMe ? "Твой первый сезон ещё идёт. Когда он завершится, итоги останутся здесь навсегда." : "Завершённых сезонов пока нет."}</div>`}
    <button class="leg-hall" data-act="lg-hall">${ic("trophy")}<span class="grow">Зал славы</span>${ic("chev")}</button>
    <div class="disc">Вайп обнуляет балансы, но не память: итоги сезона остаются в профиле навсегда. Место считается по обороту в играх.</div>`;
}

async function openHall() {
  const el = openSheet(emptyHTML("hourglass", "Загружаем…"), "leg-s");
  const d = await api("legacy/hall").catch(() => null);
  if (!el.isConnected) return;
  if (!d) return replaceSheet(el, emptyHTML("trophy", "Не удалось загрузить, попробуй ещё раз"));
  replaceSheet(el, `<div class="leg-hero"><span>${ic("trophy")}</span><h2>Зал славы</h2><p>Лучшие игроки каждого сезона. Эти имена не стираются никаким вайпом.</p></div>
    ${d.seasons.filter(s => s.top.length).length ? d.seasons.filter(s => s.top.length).map(s => `<div class="leg-hs"><div class="leg-hs-t"><b>Сезон ${s.season}</b><span>завершён ${lgDate(s.to)} · ${fmt(s.players)} ${plural(s.players, ["игрок", "игрока", "игроков"])}</span></div>
      ${s.top.map(r => `<div class="leg-hr p${r.place}" data-act="profile" data-id="${r.id}"><span class="leg-pl">${r.place}</span>${avaHTML(r, 38)}
        <div class="grow"><div class="t">${nameHTML(r)}</div><div class="s">лучший выигрыш ⭐ ${short(r.best)}</div></div><div class="leg-turn"><b>⭐ ${short(r.turn)}</b><em>оборот</em></div></div>`).join("")}</div>`).join("")
      : emptyHTML("trophy", "Первый сезон ещё идёт")}
    <div class="disc">Место считается по обороту в играх: сумма выигранного и проигранного за сезон.</div>`);
  starify(el);
}
Object.assign(ACT, { "lg-hall": () => openHall() });
