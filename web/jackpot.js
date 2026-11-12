"use strict";
// ============================================================
//  Розыгрыш банка: баннер на главной и в играх + шторка с билетами
// ============================================================
ICONS.ticket = '<path d="M3 7a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v2a2 2 0 0 0 0 4v2a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-2a2 2 0 0 0 0-4z"/><path d="M13 5v2M13 11v2M13 17v2"/>';
let JP = null;
async function loadJP() {
  try { JP = await api("jackpot"); } catch (e) { return; }
  document.querySelectorAll(".jpbar").forEach(paintJP);
}
const jpBarHTML = () => `<button class="jpbar" data-act="jp"></button>`;
function paintJP(el) {
  if (!JP) return;
  const h = Math.floor(JP.endsIn / 3600), m = Math.floor(JP.endsIn % 3600 / 60);
  el.innerHTML = `<span class="jp-i">${ic("ticket")}</span><span class="jp-t"><b>Розыгрыш банка · ⭐ ${short(JP.pool)}</b>
    <small>${JP.mine ? `твоих билетов: ${JP.mine} · шанс ${JP.chance}%` : "получи билет — сыграй 10 раундов"} · через ${h}ч ${m}м</small></span>${ic("chev")}`;
}
async function openJP() {
  H.imp("light");
  const el = openSheet(`<div id="jp-body">${emptyHTML("hourglass", "Загружаем…")}</div>`, "jp-s");
  el._jp = true;
  await loadJP(); fillJP(el);
}
function fillJP(el) {
  if (!JP || !el.isConnected) return;
  const h = Math.floor(JP.endsIn / 3600), m = Math.floor(JP.endsIn % 3600 / 60);
  el.querySelector("#jp-body").innerHTML = `
    <div class="jphero"><span class="jp-big">${ic("ticket")}</span><span>Призовой фонд сегодня</span><b>⭐ ${fmt(JP.pool)}</b>
      <em>${ic("clock")}розыгрыш через ${h}ч ${m}м</em></div>
    <div class="jpprize">${JP.split.map((s, i) => `<div class="p${i + 1}"><span>${i + 1} место</span><b>⭐ ${short(JP.pool * s)}</b></div>`).join("")}</div>
    <div class="jpme"><div><span>Твои билеты</span><b>${JP.mine}</b></div><div><span>Шанс на приз</span><b>${JP.chance}%</b></div><div><span>Участников</span><b>${JP.players}</b></div></div>
    <div class="betp">
      <div class="jpbuy">${[1, 5, 10, 25].map(n => `<button data-act="jp-buy" data-v="${n}"><b>+${n}</b><span>⭐ ${fmt(n * JP.ticket)}</span></button>`).join("")}</div>
      <div class="hint" style="font-size:12.5px;text-align:center;margin-top:10px">${JP.nextFree != null ? `Бесплатный билет через ${JP.nextFree} ${plural(JP.nextFree, ["раунд", "раунда", "раундов"])} в любых играх` : `Лимит бесплатных билетов на сегодня (${JP.freeCap}) набран`}</div>
    </div>
    ${JP.last && JP.last.winners.length ? `<div class="sec-t">${ic("trophy")}Прошлый розыгрыш · ⭐ ${fmt(JP.last.pool)}</div>
      <div class="box">${JP.last.winners.map((w, i) => `<div class="row tap" data-act="profile" data-id="${w.id}"><span class="place p${i + 1}">${i + 1}</span>${avaHTML(w, 36)}
        <div class="grow"><div class="t">${esc(w.name)}</div><div class="s">${w.tickets} ${plural(w.tickets, ["билет", "билета", "билетов"])}</div></div><b class="tw">+⭐ ${short(w.amount)}</b></div>`).join("") || `<div class="hint dempty">Победителей не было</div>`}</div>` : ""}
    <div class="disc">Каждый день банк отдаёт 10% своей прибыли (минимум ⭐ 10 000) и все купленные билеты в фонд. Розыгрыш в 00:00 UTC (11:00 по Сахалину): 3 победителя, шанс пропорционален числу билетов. ${esc(ME.disclaimer)}</div>`;
}
Object.assign(ACT, {
  jp: () => openJP(),
  "jp-buy": async el => {
    const n = +el.dataset.v;
    if (n * JP.ticket > ME.stars) return toast("Не хватает звёзд ⭐");
    const r = await post("jackpot/buy", { n }); setStars(r.stars); H.ok(); toast(`+${n} ${plural(n, ["билет", "билета", "билетов"])}`);
    await loadJP(); for (const s of SHEETS) if (s._jp) fillJP(s);
  },
});
// баннер — на главной (кейсы) и в хабе игр
const _rc = renderCases;
renderCases = async function () { await _rc(); const v = $("#v-cases"), p = v && v.querySelector(".promo"); if (p && !v.querySelector(".jpbar")) p.insertAdjacentHTML("afterend", jpBarHTML()); loadJP(); };
const _rg = renderGames;
renderGames = function () { _rg(); const b = $("#v-games .bankbar"); if (b) b.insertAdjacentHTML("afterend", jpBarHTML()); loadJP(); };
setInterval(() => { if (JP && JP.endsIn > 0) { JP.endsIn -= 30; document.querySelectorAll(".jpbar").forEach(paintJP); } }, 30000);
