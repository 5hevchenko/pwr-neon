"use strict";
// ============================================================
//  Админка → вкладка «Кран»: набор множителей, сколько призов, лимиты ставки, шанс главного приза, статистика
// ============================================================
const _admRClaw = admRender;
admRender = async function (el = topSheet()) {
  if (ADM.tab !== "claw") return _admRClaw(el);
  const body = el.querySelector("#adm-body"); if (!body) return;
  const d = await api("admin/claw"), c = d.cfg, s = d.stats, ro = d.canEdit ? "" : "disabled";
  const maxH = Math.max(1, ...s.days.map(x => Math.abs(x.house)));
  const num = v => String(v).replace(".", ",");
  body.innerHTML = `
    <div class="ca-hero"><div><span>Возврат игроку</span><b>${num(d.rtp)}%</b><small>меняется во вкладке «Шансы»</small></div>
      <div><span>Раундов за 7 дней</span><b>${fmt(s.rounds)}</b><small>${fmt(s.players)} ${plural(s.players, ["игрок", "игрока", "игроков"])}</small></div>
      <div><span>Казино за 7 дней</span><b class="${s.house >= 0 ? "tw" : "tl"}">${s.house >= 0 ? "+" : "−"}⭐ ${short(Math.abs(s.house))}</b><small>${s.best ? `рекорд: ${esc(s.best.name)} +⭐ ${short(s.best.win)}` : "крупных выигрышей нет"}</small></div></div>
    <div class="ca-bars">${s.days.map(x => `<div title="${new Date(x.day * 1000).toLocaleDateString("ru")}: ${x.house}"><i class="${x.house >= 0 ? "up" : "dn"}" style="height:${Math.max(3, Math.abs(x.house) / maxH * 100)}%"></i></div>`).join("")}</div>

    <div class="sec-t">${ic("gift")}Призы в автомате</div>
    <div class="box ca-form">
      <label>Множители призов <small>через пробел, 3–20 штук, от 1,05 до 1000. Крупные (×10 и выше) выпадают по одному.</small>
        <input id="ca-m" ${ro} value="${c.mults.map(num).join("  ")}"></label>
      <div class="ca-row">
        <label>Призов в автомате <small>3–8</small><input id="ca-size" ${ro} inputmode="numeric" value="${c.size}"></label>
        <label>Шанс главного приза <small>% раундов, где в автомате самый большой икс</small><input id="ca-jp" ${ro} inputmode="decimal" value="${num(Math.round(c.jackpot * 100))}"></label></div>
      <div class="ca-row">
        <label>Мин. ставка<input id="ca-min" ${ro} inputmode="numeric" value="${c.min_bet}"></label>
        <label>Макс. ставка<input id="ca-max" ${ro} inputmode="numeric" value="${c.max_bet}"></label></div>
      ${d.canEdit ? `<div class="ca-btns"><button class="btn gold" data-act="ca-save">${ic("check")}Сохранить</button><button class="btn ghost" data-act="ca-reset">${ic("refresh")}По умолчанию</button></div>`
        : `<div class="hint" style="font-size:12.5px">Менять автомат может только владелец.</div>`}</div>

    <div class="sec-t">${ic("trend")}Шанс удержать каждый приз</div>
    <div class="ca-odds">${d.odds.map(o => `<div class="${o.m >= 10 ? "big" : ""}"><b>x${num(o.m)}</b><span>${num(o.p)}%</span></div>`).join("")}</div>
    <div class="disc">Шанс = возврат ÷ множитель (не выше ${Math.round(d.cap * 100)}%), поэтому на любой цели игроку в среднем возвращается ${num(d.rtp)}% ставок. После сохранения автоматы у всех игроков пересобираются по новым правилам. Закрыть или скрыть игру — вкладка «Игры».</div>`;
};
Object.assign(ACT, {
  "ca-save": async () => {
    const v = id => document.getElementById(id).value.replace(",", ".");
    const mults = v("ca-m").replace(/,(?=\d)/g, ".").split(/[\s;]+/).map(Number).filter(x => x > 0);
    await post("admin/claw", { mults, size: +v("ca-size"), jackpot: +v("ca-jp") / 100, min_bet: +v("ca-min"), max_bet: +v("ca-max") });
    H.ok(); toast("Автомат обновлён", "ok"); admRender();
  },
  "ca-reset": async () => {
    if (!await confirmM("Вернуть настройки по умолчанию?", "Множители, лимиты и шанс главного приза станут как при запуске.", "Сбросить")) return;
    await post("admin/claw", { reset: true }); H.ok(); toast("Сброшено", "ok"); admRender();
  },
});
