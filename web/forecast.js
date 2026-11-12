"use strict";
// ============================================================
//  Прогноз дня: тотализатор на итоги следующих суток
// ============================================================
GAMES.push({ id: "forecast", t: "Прогноз дня", s: "", img: "Crystal Ball", k: ["#6f7bff", "#171a55"], chips: [] });
GCAT.forecast = "fast"; G_NEW.add("forecast");
const FC_T = {
  crash: { t: "Самый большой икс краша", s: "за сутки, иксы заданы цепочкой хэшей", up: "Выше", down: "Ниже" },
  carousel: { t: "Бонусы на Карусели", s: "сколько раз выпадут за сутки", up: "Больше", down: "Меньше" },
  bank: { t: "Банк за сутки", s: "без операций участников рынка", up: "Вырастет", down: "Упадёт" },
};
let FC = null, fcSel = null, fcAmt = null, fcClock = null;
const fcDate = ts => new Date(ts * 1000).toLocaleDateString(LANG === "en" ? "en-GB" : "ru-RU", { day: "numeric", month: "long", timeZone: "Europe/Moscow" });
const fcVal = (key, v) => v == null ? "—" : key === "crash" ? "×" + fmt(v) : key === "bank" ? (v > 0 ? "+" : v < 0 ? "−" : "") + short(Math.abs(v)) : fmt(v);
const fcLine = m => m.key === "bank" ? "0" : fcVal(m.key, m.line);
async function openForecast() {
  openSheet(`${gameHead("Crystal Ball", "Прогноз дня", "", "forecast")}<div id="fc-body">${emptyHTML("hourglass", "Загружаем…")}</div>`, "fc-s");
  fcSel = null; fcAmt = null;
  try { FC = await api("forecast"); } catch (e) { return; }
  fcDraw();
}
function fcMarket(m, d) {
  const T = FC_T[m.key], sel = fcSel && fcSel.key === m.key ? fcSel.side : null, side = m.mine ? m.mine.side : sel;
  const k = (me, other) => me && other ? "x" + (1 + other / me * (1 - d.rake)).toFixed(2) : "—";
  const card = (v, pool, x) => `<button class="bb-card ${v}${side === v ? " on" : ""}" data-act="fc-side" data-k="${m.key}" data-v="${v}" ${m.mine && m.mine.side !== v ? "disabled" : ""}>
      <span class="bb-ic">${BB_ARROW[v]}</span><b>${T[v]}</b><strong>${x}</strong><small>в пуле ⭐ ${short(pool)}</small></button>`;
  return `<div class="fc-m"><div class="fc-mh"><div class="grow"><b>${T.t}</b><span>${T.s}</span></div>${m.key === "bank" ? "" : `<i>линия <u>${fcLine(m)}</u></i>`}</div>
    <div class="bb-sides">${card("up", m.up, k(m.up, m.down))}${card("down", m.down, k(m.down, m.up))}</div>
    ${m.mine ? `<div class="bb-mine">Твоя ставка ⭐ ${fmt(m.mine.amount)} на «${T[m.mine.side]}»</div>` : ""}</div>`;
}
function fcDraw() {
  const b = $("#fc-body"), d = FC; if (!b || !d) return;
  if ($("#fc-amt")) fcAmt = betVal("fc-amt");
  const s = d.stats, cur = fcSel && d.open.find(x => x.key === fcSel.key), has = cur && (cur.mine ? cur.mine.side : fcSel.side);
  const res = m => !m.side ? "возврат" : !m.mine ? "" : m.mine.side === m.side ? "угадал" : "не угадал";
  b.innerHTML = `<div class="bb-round"><span>Ставки на ${fcDate(d.dayTs)}</span><b id="fc-clock">${clock(d.closesIn)}</b><small>до закрытия</small></div>
    <div class="fc-stats"><div><b>${fmt(s.streak)}</b><span>серия</span></div><div><b>${fmt(s.best)}</b><span>рекорд</span></div><div><b>${s.total ? Math.round(s.won / s.total * 100) + "%" : "—"}</b><span>точность</span></div></div>
    ${d.open.map(m => fcMarket(m, d)).join("")}
    <div class="betp">${betHTML("fc-amt", fcAmt || d.min)}
      <button class="btn cta" data-act="fc-bet" ${has ? "" : "disabled"}>${has ? `Поставить на «${FC_T[cur.key][has]}»` : "Выбери исход"}</button></div>
    ${d.live.length ? `<div class="sec-t">${ic("hourglass")}Идут сегодня</div><div class="box">${d.live.map(m => `<div class="row"><div class="grow"><div class="t">${FC_T[m.key].t}</div>
      <div class="s">сейчас ${fcVal(m.key, m.now)}${m.key === "bank" ? "" : ` · линия ${fcLine(m)}`}${m.mine ? ` · твоя ставка ⭐ ${short(m.mine.amount)} на «${FC_T[m.key][m.mine.side]}»` : ""}</div></div></div>`).join("")}</div>` : ""}
    ${d.past.length ? `<div class="sec-t">${ic("award")}Итоги</div><div class="box">${d.past.map(m => `<div class="row"><div class="grow"><div class="t">${FC_T[m.key].t}</div>
      <div class="s">${fcDate(m.dayTs)} · итог ${fcVal(m.key, m.value)}${m.key === "bank" ? "" : ` · линия ${fcLine(m)}`}${res(m) ? ` · ${res(m)}` : ""}</div></div></div>`).join("")}</div>` : ""}
    <details class="rules"><summary>${ic("award")}Как играть</summary><div>Ставки на новые сутки по Москве принимаются до полуночи. Победители делят ставки проигравших, банк берёт ${Math.round(d.rake * 100)}%. На каждый рынок один исход, до ⭐ ${short(d.max)}. Линия зафиксирована до приёма ставок: это медиана прошлых суток. Иксы краша и бонусы Карусели заданы цепочками хэшей и не зависят от ставок. Банк считается без операций участников рынка. Нет соперника, итог совпал с линией или сервер долго не работал: ставка возвращается без комиссии.</div></details>`;
  starify(b);
  clearInterval(fcClock);
  const t0 = Date.now(), left = d.closesIn;
  fcClock = setInterval(() => { const c = $("#fc-clock"); if (!c) return clearInterval(fcClock); const v = left - (Date.now() - t0) / 1000; if (v <= 0) { clearInterval(fcClock); fcReload(); } else c.textContent = clock(v); }, 1000);
}
async function fcReload() { try { FC = await api("forecast"); fcSel = null; fcDraw(); } catch (e) {} }
Object.assign(GAME_OPEN, { forecast: openForecast });
Object.assign(ACT, {
  "fc-side": el => { fcSel = { key: el.dataset.k, side: el.dataset.v }; H.sel(); fcDraw(); },
  "fc-bet": async () => {
    const m = fcSel && FC.open.find(x => x.key === fcSel.key); if (!m) return;
    const side = m.mine ? m.mine.side : fcSel.side;
    try { FC = await post("forecast/bet", { key: m.key, side, amount: betVal("fc-amt") }); if (FC.stars != null) setStars(FC.stars); H.ok(); toast("Ставка принята", "ok"); fcDraw(); } catch (e) {}
  },
});
