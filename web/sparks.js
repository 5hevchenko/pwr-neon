"use strict";
// ============================================================
//  Огоньки с друзьями (как в TikTok): серия дней, тип огонька растёт с длиной серии
// ============================================================
let SPK = null;
// пламя: оболочка + пламя + сердцевина, цвета — градиентами по типу (defs вставляем один раз)
const FL_O = "M12 1.6c.7 3.4 3.4 5.3 4.9 7.9 2.2 3.7 1.4 8.6-1.9 11.1-1 .8-2.2 1.2-3.4 1.3 1.3-1.2 1.8-3 1.2-4.7-.5-1.4-1.6-2.4-2.1-3.8-.6 1.2-.5 2.6.1 3.8-1.6-.7-2.7-2.3-2.8-4-1.6 1.7-2.2 4.2-1.4 6.4C4.2 18.4 3.3 14.6 4.6 11.4c1.2-3 3.9-4.9 5.5-7.6.5-.8 1.1-1.5 1.9-2.2z";
const FL_M = "M12.2 9.6c.4 2 2.1 3.2 2.8 5 .9 2.4-.3 5.2-2.7 6.1-2.2.8-4.6-.4-5.2-2.6-.4-1.5.1-3.1 1.1-4.2 0 1 .5 1.9 1.3 2.4-.4-2.6.9-4.9 2.7-6.7z";
const FL_C = "M12 15.4c.3 1 1.2 1.6 1.3 2.7.1 1.1-.7 2-1.6 2.1-1 .1-1.8-.6-1.9-1.6 0-.7.3-1.3.8-1.8 0 .4.2.8.5 1 .1-.9.4-1.7.9-2.4z";
(() => {
  const T = { spark: ["#ff9d2e", "#ffe27a"], orange: ["#ff6a00", "#ffc04d"], red: ["#ff2d3d", "#ff9a3d"], violet: ["#8a3dff", "#ff6ad5"], blue: ["#1f6bff", "#6ff2ff"], none: ["#6b6b78", "#9a9aa8"] };
  const g = Object.entries(T).map(([k, [a, b]]) => `<linearGradient id="flg-o-${k}" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="${a}"/><stop offset="1" stop-color="${b}"/></linearGradient>
    <linearGradient id="flg-m-${k}" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="${b}"/><stop offset="1" stop-color="#fff3c4"/></linearGradient>`).join("");
  document.body.insertAdjacentHTML("beforeend", `<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs>${g}</defs></svg>`);
})();
function flameHTML(s, big) {
  const k = s && s.count ? s.tier : "none", dim = s && s.count && !s.done;
  return `<span class="fl fl-${k}${dim ? " dim" : ""}${big ? " big" : ""}"><svg viewBox="0 0 24 24"><path class="o" fill="url(#flg-o-${k})" d="${FL_O}"/><path class="m" fill="url(#flg-m-${k})" d="${FL_M}"/><path class="c" d="${FL_C}"/></svg>${s && s.count ? `<b>${s.count}</b>` : ""}</span>`;
}
function sparkCell(fid) {
  const s = SPK && SPK.map[fid];
  if (!s) return "";
  const k = s.count ? s.tier : "none";
  const cell = s.count ? `<span class="sp-cell fl-${k}" data-act="spark-info" data-id="${fid}">${flameHTML(s)}</span>` : "";
  const btn = s.mine ? `<span class="sp-ok">${ic("check")}${s.done ? "Засчитан" : "Отправлен"}</span>`
    : `<button class="sp-btn${s.theirs ? " wait" : ""}" data-act="spark" data-id="${fid}">${flameHTML({ count: 0 })}${s.theirs ? "Ответить" : "Огонёк"}</button>`;
  return cell + btn;
}
async function loadSparks() {
  try { const d = await api("sparks"); d.map = {}; d.items.forEach(x => d.map[x.user.id] = x); SPK = d; } catch (e) {}
  return SPK;
}
function sparksIntro() {
  if (!SPK || !SPK.items.length) return "";
  const wait = SPK.items.filter(x => x.theirs && !x.mine).length, risk = SPK.items.filter(x => x.risk && !x.mine).length;
  const h = Math.floor(SPK.endsIn / 3600), m = Math.floor(SPK.endsIn % 3600 / 60);
  return `<div class="sp-intro" data-act="spark-help">${flameHTML({ count: 1, tier: "red", done: true }, true)}<div class="grow"><b>Огоньки</b>
    <span>${wait ? `${wait} ${plural(wait, ["друг ждёт", "друга ждут", "друзей ждут"])} твой огонёк` : risk ? `${risk} ${plural(risk, ["серия сгорит", "серии сгорят", "серий сгорят"])} в полночь` : "Отправляйте друг другу огонёк каждый день — серия растёт"}
    · до конца дня ${h} ч ${m} мин${SPK.played ? "" : " · сначала сыграй раунд"}</span></div>${ic("info")}</div>`;
}
// друзья: огоньки в каждой строке
const _ffSp = fillFriends;
fillFriends = async function (el) {
  await Promise.all([_ffSp(el), loadSparks()]);
  if (!el.isConnected || !SPK) return;
  const body = el.querySelector("#fr-body"); if (!body) return;
  body.querySelectorAll(".sec-t").forEach(t => {
    if (!/^Друзья/.test(t.textContent)) return;
    const box = t.nextElementSibling; if (!box || !box.classList.contains("box")) return;
    if (!body.querySelector(".sp-intro")) t.insertAdjacentHTML("beforebegin", sparksIntro());
    box.querySelectorAll(".row[data-id]").forEach(r => {
      const s = SPK.map[+r.dataset.id]; if (!s) return;
      r.classList.add("sp-row"); r.classList.toggle("sp-wait", s.theirs && !s.mine);
      r.querySelector(".sp-right")?.remove();
      r.insertAdjacentHTML("beforeend", `<span class="sp-right">${sparkCell(+r.dataset.id)}</span>`);
      const sub = r.querySelector(".s");
      if (sub && s.count) sub.innerHTML = `${esc(s.tierName)} · ${s.done ? "сегодня засчитан" : s.theirs ? "друг уже отправил — твоя очередь" : s.mine ? "ждём огонёк друга" : "отправьте друг другу до полуночи"}`;
      else if (sub && s.theirs && !s.mine) sub.textContent = "огонёк уже у тебя — ответь";
    });
  });
};
// счётчик на кнопке друзей в шапке
const _rhSp = renderHeader;
renderHeader = function () {
  _rhSp.apply(this, arguments);
  const b = $("#fr-btn"); if (!b || !ME) return;
  const base = ME.friendReq + ME.trades + (ME.duels || 0) + (ME.rooms || 0), n = base + (ME.sparks || 0);
  b.innerHTML = ic("users") + (n ? `<span class="badge-dot${!base ? " fire" : ""}">${n}</span>` : "");
};
function sparkHelp() {
  const M = SPK ? SPK.milestones : {};
  modal(`<div style="text-align:center">${flameHTML({ count: 7, tier: "red", done: true }, true)}</div><h3 style="text-align:center">Огоньки</h3>
    <p class="hint" style="margin:0 0 12px;text-align:center">Каждый день отправляйте друг другу огонёк — если оба успели до полуночи (по Москве), серия растёт. Пропустили день — серия сгорает. Отправить огонёк можно, сыграв сегодня хотя бы раунд.</p>
    <div class="sp-tiers">${[["spark", 1, "Искра"], ["orange", 3, "Огонёк"], ["red", 7, "Пламя"], ["violet", 30, "Фиолетовое"], ["blue", 100, "Синее"]].map(([k, n, t]) =>
      `<div>${flameHTML({ count: n, tier: k, done: true })}<span>${t}</span></div>`).join("")}</div>
    <div class="box" style="margin:12px 0 14px">${Object.entries(M).map(([d, r]) => `<div class="row kv"><span class="pill">${d} ${plural(+d, ["день", "дня", "дней"])}</span><div class="grow"></div><b class="star">+${fmt(r)} ⭐ каждому</b></div>`).join("")}</div>
    <button class="btn gold" data-m="ok">Понятно</button>`);
}
Object.assign(ACT, {
  spark: async el => {
    if (SPK && !SPK.played && !(await loadSparks()).played)   // сервер всё равно откажет — объясняем без красной ошибки
      return toast("Сначала сыграй сегодня любой раунд — потом можно отправить огонёк");
    const r = await post(`sparks/${el.dataset.id}`); H.ok();
    burstAt(el, null);
    toast(r.done ? (r.reward ? `Серия ${r.count}! +${fmt(r.reward)} ⭐ каждому` : `Серия ${r.count} — день засчитан`) : "Огонёк отправлен — ждём ответа друга", "ok");
    if (r.reward) coinShower(el, 30);
    ME.sparks = Math.max(0, (ME.sparks || 0) - 1); renderHeader();
    refreshFriends();
  },
  "spark-info": el => { const s = SPK && SPK.map[+el.dataset.id]; if (!s) return;
    toast(s.count ? `${s.tierName}: ${s.count} ${plural(s.count, ["день", "дня", "дней"])}${s.next ? ` · до награды ${s.next - s.count} ${plural(s.next - s.count, ["день", "дня", "дней"])}` : ""}` : "Серии пока нет — отправьте друг другу огонёк"); },
  "spark-help": () => sparkHelp(),
});
