"use strict";
// ============================================================
//  «Живая» игра: бегущая строка крупных выигрышей + онлайн, «играют N» на карточках игр, лента с реакциями.
//  Сезоны и титулы: вкладка «Сезон» в топе, выбор титула в профиле, рамки на аватарках.
// ============================================================
let LIVE = null, livePoll = null;
async function liveLoad() {
  try { LIVE = await api("live"); } catch (e) { return; }
  liveTicker(); livePlaying();
}
function liveTicker() {
  if (!LIVE) return;
  ["v-cases", "v-games"].forEach(id => {
    const v = document.getElementById(id); if (!v || !v.classList.contains("on")) return;
    let t = v.querySelector(".lv-tick");
    const items = LIVE.wins.map(w => `<span class="lv-it">${avaHTML(w.user, 18)}<b>${esc(w.user.name)}</b><i>${esc(w.game)}</i>${w.ok ? `<u class="lv-ok">${ic("check")}</u>` : ""}<em>+⭐ ${short(w.amount)}</em></span>`).join("");
    const html = `<span class="lv-on"><i></i>${LIVE.online} онлайн</span><div class="lv-track"><div class="lv-run">${items || `<span class="lv-it"><i>Крупные выигрыши появятся здесь</i></span>`}${items}</div></div>`;
    if (!t) {
      t = document.createElement("button"); t.className = "lv-tick"; t.dataset.act = "live";
      const hello = v.querySelector(".hello"); hello ? hello.after(t) : v.prepend(t);
    }
    if (t._h !== html) { t._h = html; t.innerHTML = html; starify(t); const run = t.querySelector(".lv-run"); run.style.animationDuration = Math.max(20, LIVE.wins.length * 4) + "s"; }
  });
}
function livePlaying() {
  if (!LIVE) return;
  document.querySelectorAll("#v-games .gcard[data-id]").forEach(c => {
    const n = LIVE.playing[{ duels: "duel", "101": "cards", rlt: "roulette", swap: "upgrade" }[c.dataset.id] || c.dataset.id] || 0;
    let b = c.querySelector(".gc-play");
    if (!n) { if (b) b.remove(); return; }
    if (!b) { b = document.createElement("span"); b.className = "gc-play"; c.appendChild(b); }
    b.innerHTML = `<i></i>играют ${n}`;
  });
}
const _setTabLive = setTab;
setTab = function (t) {
  _setTabLive(t);
  clearInterval(livePoll);
  if (t === "cases" || t === "games") { setTimeout(() => { liveTicker(); livePlaying(); }, 50); liveLoad(); livePoll = setInterval(() => bgOff() || liveLoad(), 15000); }
};
async function openLive() {
  const el = openSheet(emptyHTML("hourglass", "Загружаем…"), "lv-s");
  const draw = async () => {
    const d = await api("live?full=1").catch(() => null); if (!d || !el.isConnected) return;
    replaceSheet(el, `<h2 class="gtitle">Выигрыши</h2><div class="lv-head"><span class="lv-on"><i></i>${d.online} онлайн</span><span class="hint">выигрыши от ⭐ 3 000 во всех играх</span></div>
      <div class="box">${d.wins.map(w => `<div class="row lv-row tap" data-act="profile" data-id="${w.user.id}">${avaHTML(w.user, 36)}<div class="grow"><div class="t">${esc(w.user.name)}${w.user.title ? ` <span class="ttl">${esc(w.user.title)}</span>` : ""}</div>
        <div class="s">${esc(w.game)} · ${clockAgo(w.ts)}</div>
        <div class="lv-reacts">${d.reactsList.map(e => `<button data-act="lv-react" data-id="${w.id}" data-e="${e}" class="${w.mine === e ? "on" : ""}" ${w.user.id === ME.id ? "disabled" : ""}>${e}${w.reacts[e] ? `<b>${w.reacts[e]}</b>` : ""}</button>`).join("")}</div></div>
        ${w.ok ? `<button class="lv-okb" data-act="fair" aria-label="Проверено">${ic("check")}Проверено</button>` : ""}<b class="tw">+⭐ ${short(w.amount)}</b></div>`).join("") || `<div class="hint" style="padding:14px">Пока пусто</div>`}</div>`);
    starify(el);
  };
  el._redraw = draw; await draw();
}
const clockAgo = ts => { const s = Date.now() / 1000 - ts; return s < 60 ? "только что" : s < 3600 ? Math.floor(s / 60) + " мин назад" : s < 86400 ? Math.floor(s / 3600) + " ч назад" : Math.floor(s / 86400) + " д назад"; };

// ---------------- сезоны ----------------
TOPK.splice(1, 0, ["season", "flame", "Сезон"]);
const _rtSeason = renderTop;
renderTop = async function () {
  if (topKind !== "season") return _rtSeason();
  const v = $("#v-top");
  v.innerHTML = `${topNavHTML()}<div id="ss-body">${emptyHTML("hourglass", "Загружаем…")}</div>`;
  const d = await api("season").catch(() => null); if (!d || TAB !== "top" || topKind !== "season") return;
  const left = Math.max(0, d.ends - Date.now() / 1000), dd = Math.floor(left / 86400), hh = Math.floor(left % 86400 / 3600);
  const t3 = [d.top[1], d.top[0], d.top[2]];
  $("#ss-body").innerHTML = `<div class="ss-hero"><span>Сезон</span><b>${esc(d.title)}</b><em>до конца ${dd} д ${hh} ч</em>
      <div class="ss-pr"><div><i class="fr gold"></i>1 место · ⭐ ${short(d.prizes[0])}</div><div><i class="fr silver"></i>2–3 · ⭐ ${short(d.prizes[1])}–${short(d.prizes[2])}</div><div><i class="fr bronze"></i>4–10 · до ⭐ ${short(d.prizes[3])}</div></div>
      <small>Топ-10 получает звёзды и рамку аватарки на весь следующий сезон, 1 место — титул «Чемпион сезона». Очки — за игру (не больше 100 очков с одной ставки).</small></div>
    <div class="ss-me"><span>Ты</span><b>${d.me.excluded ? "исключён из сезона" : d.me.place ? d.me.place + " место" : "вне рейтинга"}</b><em class="tw">${fmt(d.me.pts)} очк.</em></div>
    ${d.top.length ? `<div class="podium" style="margin-top:12px">${t3.map((r, i) => r ? `<div class="p${[2, 1, 3][i]}" data-act="profile" data-id="${r.id}">${avaHTML(r, 54, { lv: true })}
        <div class="nm">${nameHTML(r)}</div><div class="sc">${fmt(r.pts)} очк.</div><div class="pl"><span class="tw">⭐ ${short(r.prize)}</span></div><div class="ped">${[2, 1, 3][i]}</div></div>` : "<div></div>").join("")}</div>
      <div class="box">${d.top.slice(3).map((r, i) => `<div class="row tap" data-act="profile" data-id="${r.id}"><span class="place">${i + 4}</span>${avaHTML(r, 34)}
        <div class="grow"><div class="t">${nameHTML(r)}${r.title ? ` <span class="ttl">${esc(r.title)}</span>` : ""}</div>${r.prize ? `<div class="s tw">приз ⭐ ${short(r.prize)}</div>` : ""}</div><b class="num">${fmt(r.pts)}</b></div>`).join("")}</div>`
      : emptyHTML("flame", "Сезон только начался — займи первое место!")}
    <button class="ss-tt" data-act="titles">${ic("medal")}<span><b>Мои титулы</b>выбери, какой показывать под именем</span>${ic("chev")}</button>`;
  starify($("#ss-body"));
};

// ---------------- титулы ----------------
async function openTitles() {
  const el = openSheet(emptyHTML("hourglass", "Загружаем…"), "tt-s");
  const draw = async () => {
    const d = await api("titles").catch(() => null); if (!d || !el.isConnected) return;
    const got = d.titles.filter(t => t.got).length;
    replaceSheet(el, `<h2 class="gtitle">${ic("medal")} Титулы</h2><p class="hint" style="margin:-6px 0 12px">Открыто ${got} из ${d.titles.length}. Выбранный титул виден под именем в профиле, топах и ленте выигрышей.</p>
      <div class="tt-grid">${d.titles.map(t => `<button class="tt${t.got ? " got" : ""}${d.current === t.id ? " on" : ""}" ${t.got ? `data-act="tt-pick" data-id="${t.id}"` : "disabled"}>
        <b>${esc(t.name)}</b><span>${t.got ? (d.current === t.id ? "выбран" : "нажми, чтобы выбрать") : esc(t.how)}</span>${t.got ? "" : `<i>${ic("lock")}</i>`}</button>`).join("")}</div>
      ${d.current ? `<button class="btn ghost" data-act="tt-pick" data-id="" style="margin-top:12px">Не показывать титул</button>` : ""}`);
  };
  el._redraw = draw; await draw();
}
Object.assign(ACT, {
  live: () => openLive(),
  "lv-react": async el => { await post(`live/${el.dataset.id}/react`, { emoji: el.dataset.e }); H.sel(); topSheet()._redraw && topSheet()._redraw(); },
  titles: () => openTitles(),
  "tt-pick": async el => { await post("titles/select", { id: el.dataset.id }); H.ok(); toast(el.dataset.id ? "Титул выбран" : "Титул скрыт", "ok"); MYP = null; topSheet()._redraw && topSheet()._redraw(); },
});
