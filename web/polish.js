"use strict";
// ============================================================
//  Полировка: «Старт новичка», компактный главный экран, кейсы по доступности,
//  разделы игр, быстрые действия с подарком
// ============================================================

// ------------------------------------------------------------ «Старт новичка»
let OB = null;
async function loadOB() {
  try { OB = await api("onboard"); } catch (e) { return; }
  const box = $("#ob"); if (!box) return;
  if (OB.all) return box.remove();
  const done = OB.steps.filter(s => s.claimed).length, ready = OB.steps.filter(s => s.done && !s.claimed);
  const next = ready[0] || OB.steps.find(s => !s.done);
  box.innerHTML = `<div class="ob-h"><b>Старт новичка</b><span>${done}/${OB.steps.length}${OB.steps.some(s => s.done && !s.claimed) ? ` · <em class="ob-rd">${OB.steps.filter(s => s.done && !s.claimed).length} к получению</em>` : ""}</span></div>
    <div class="ob-bar">${OB.steps.map(s => `<i class="${s.claimed ? "on" : s.done ? "rd" : ""}"></i>`).join("")}</div>
    ${next ? `<div class="ob-step"><span class="pic ${next.done ? "g" : "b"}">${ic(next.icon)}</span><div class="grow"><div class="t">${esc(next.t)}</div><div class="s">награда ⭐ ${fmt(next.reward)}</div></div>
      ${next.done ? `<button class="btn sm gold" data-act="ob-claim" data-id="${next.id}">Забрать</button>` : `<button class="btn sm" data-act="ob-go" data-go="${next.go}">Перейти</button>`}</div>` : ""}`;
}

// ------------------------------------------------------------ главный экран: компактные плашки + кейсы по доступности
let caseFilter = "all";
const CASE_TIERS = [["all", "Все"], ["cheap", "до 1K"], ["mid", "1K–10K"], ["top", "10K+"]];
const _rc3 = renderCases;
renderCases = async function () {
  await _rc3();
  const v = $("#v-cases"); if (!v) return;
  // «Старт новичка» — сразу под лентой
  if (!$("#ob")) { const p = v.querySelector(".promo"); if (p) p.insertAdjacentHTML("beforebegin", `<div class="ob" id="ob"></div>`); }
  loadOB();
  // доход и розыгрыш — в один ряд
  setTimeout(() => {
    const inc = v.querySelector(".incbar"), jp = v.querySelector(".jpbar");
    if (inc && jp && !v.querySelector(".dash2")) {
      const w = document.createElement("div"); w.className = "dash2";
      inc.before(w); w.append(inc, jp);
    }
  }, 50);
  // кейсы: сначала доступные, закрытые — свёрнутым блоком; фильтр по цене
  const grid = v.querySelector(".cases"); if (!grid || v.querySelector("#cases-locked")) return;   // фильтр по цене убран — все кейсы сразу
  const locked = [...grid.querySelectorAll(".case")].filter(c => c.querySelector(".lock"));
  if (locked.length) {
    const next = Math.min(...locked.map(c => (CASES.find(x => x.id === c.dataset.id) || {}).level || 99));
    grid.insertAdjacentHTML("afterend", `<details class="locked"><summary>${ic("lock")}Откроются с уровнем · ${locked.length} ${plural(locked.length, ["кейс", "кейса", "кейсов"])}
      <span>следующий на ${next} ур.</span></summary><div class="cases" id="cases-locked"></div></details>`);
    const lg = $("#cases-locked"); locked.forEach(c => lg.appendChild(c));
  }
  applyCaseFilter();
};
function applyCaseFilter() {
  document.querySelectorAll("#v-cases .case").forEach(el => {
    const c = CASES.find(x => x.id === el.dataset.id); if (!c) return;
    const p = c.price, ok = caseFilter === "all" || caseFilter === "cheap" && p < 1000 || caseFilter === "mid" && p >= 1000 && p < 10000 || caseFilter === "top" && p >= 10000;
    el.style.display = ok ? "" : "none";
  });
}

// ------------------------------------------------------------ хаб игр по разделам
const GAME_SECTIONS = [
  ["Хиты", "flame", ["crash", "dogs", "slots", "jroul"]],
  ["С друзьями", "users", ["duels", "101", "blackjack"]],
  ["Подарки", "gift", ["upgrade", "swap"]],
  ["Классика", "coins", ["rlt", "tower", "mines", "wheel", "dice", "limbo"]],
];
const _rg2 = renderGames;
renderGames = function () {
  _rg2();
  if (typeof GCAT !== "undefined") return;   // разделы, поиск и избранное теперь строит хаб (games.js)
  const hub = $("#v-games .ghub"); if (!hub) return;
  const cards = Object.fromEntries([...hub.querySelectorAll(".gcard")].map(c => [c.dataset.id, c]));
  const frag = document.createDocumentFragment();
  for (const [title, icon, ids] of GAME_SECTIONS) {
    const list = ids.filter(id => cards[id]); if (!list.length) continue;
    const h = document.createElement("div"); h.className = "sec-t gsec"; h.innerHTML = `${ic(icon)}${title}`; frag.appendChild(h);
    const g = document.createElement("div"); g.className = "ghub";
    list.forEach((id, i) => {
      const c = cards[id]; delete cards[id];
      // первая карточка раздела — широкая; в паре, если осталась одна — тоже широкая, чтобы не было дыр
      const rest = list.length - 1;
      c.classList.toggle("wide", i === 0 || (i === list.length - 1 && rest % 2 === 1));
      g.appendChild(c);
    });
    frag.appendChild(g);
  }
  Object.values(cards).forEach(c => { hub.appendChild(c); });   // новые игры, не попавшие в разделы
  hub.before(frag);
  if (!hub.children.length) hub.remove();
};

// ------------------------------------------------------------ быстрые действия с подарком
const _gsh = giftSheetHTML;
giftSheetHTML = function (o, mine) {
  let h = _gsh(o, mine);
  if (mine && o.g.price == null) {
    const k = reg(o.g);
    h = h.replace('<div class="disc">', `<div class="gq">
      <button data-act="q-upg" data-k="${k}">${ic("trend")}<span>Апгрейд</span></button>
      <button data-act="q-vault" data-k="${k}">${ic("lock")}<span>В сейф</span></button>
      <button data-act="q-swap" data-k="${k}">${ic("swap")}<span>Обменять</span></button></div><div class="disc">`);
  }
  return h;
};

Object.assign(ACT, {
  "ob-claim": async el => { const r = await post(`onboard/${el.dataset.id}/claim`); setStars(r.stars); H.ok(); toast(`+⭐ ${fmt(r.reward)}`, "ok"); burstAt(el); loadOB(); },
  "ob-go": el => {
    const g = el.dataset.go;
    if (g === "case-free") return openCase("free");
    if (g === "tab-games") return setTab("games");
    if (g === "inc") return openInc();
    if (g === "edit-profile") return editProfile();
    if (g === "friends") return openFriends();
    if (g === "clans") { topKind = "clans"; return setTab("top"); }
    if (g === "tab-inv") { setTab("inv"); return toast("Открой подарок и нажми «Подарить другу»"); }
  },
  cf: el => { caseFilter = el.dataset.v; H.sel(); el.parentElement.querySelectorAll("button").forEach(b => b.classList.toggle("on", b === el)); applyCaseFilter(); },
  "q-upg": el => { const g = REG.get(el.dataset.k); closeSheet(); openUpgrade(); UP.gs = [g]; UP.ts = []; upgDraw(); upgLoad(); },
  "q-swap": el => { const g = REG.get(el.dataset.k); closeSheet(); openSwap(); swapChoose(g); },
  "q-vault": async el => {
    const g = REG.get(el.dataset.k);
    const d = await modal(`<h3>В сейф на сколько?</h3><p class="hint" style="margin:0 0 12px">${esc(g.col)} вернётся к тебе с наградой</p>
      <div class="vplans">${[[1, 2], [3, 7], [7, 18]].map(([days, pct]) => `<button data-m="ok" data-days="${days}"><b>+⭐ ${fmt(Math.round(g.value * pct / 100))}</b><span>${days} ${plural(days, ["день", "дня", "дней"])} · +${pct}%</span></button>`).join("")}</div>`);
    if (!d || !window._vaultDays) return;
    await post("vault/put", { gifts: [g.id], days: window._vaultDays }); H.ok(); toast("Подарок в сейфе", "ok"); giftChanged();
  },
});
document.addEventListener("click", e => { const b = e.target.closest("[data-days]"); if (b) window._vaultDays = +b.dataset.days; }, true);
