//  Сезоны-вайпы (wipe.py): отсчёт до вайпа на главной, плашка «Банк благодарит за игру» в начале сезона,
//  вкладка «Вайп» в админке — расписание, что сбрасывать, стартовый баланс, % благодарности, ручной запуск.
const wpMsk = ts => ts ? new Date((ts + 10800) * 1000).toISOString().slice(0, 16) : "";
const wpFromMsk = v => v ? Math.floor(Date.parse(v + ":00Z") / 1000) - 10800 : 0;
const wpLeft = s => { s = Math.max(0, s); const d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60);
  return d ? `${d} д ${h} ч` : h ? `${h} ч ${m} мин` : `${m} мин`; };

// ---------------- главная: отсчёт за неделю до вайпа ----------------
function wipeCard() {
  const w = ME && ME.wipe; if (!w || !w.next) return "";
  const left = w.next - Date.now() / 1000; if (left > 7 * 86400 || left < -600) return "";
  return `<button class="stc st-wipe" data-act="wipe-info"><span class="stc-i">${ic("refresh")}</span><span class="stc-t"><b>${w.frozen ? "Идёт вайп…" : `Вайп через ${wpLeft(left)}`}</b>
    <small>Начнётся сезон ${w.season + 1}: звёзды, подарки и бизнесы сбросятся, уровень останется. Банк вернёт часть того, что ты в него внёс</small></span>${ic("chev")}</button>`;
}
function wipeInfo() {
  const w = ME.wipe || {};
  modal(`<h3>Вайп и новый сезон</h3><p class="hint" style="margin:0 0 12px;line-height:1.45">${w.next ? `Вайп — <b>${admDate(w.next)}</b> (через ${wpLeft(w.next - Date.now() / 1000)}).<br>` : ""}
    Сбросится всё: звёзды, подарки, бизнесы, крипта, акции, кредиты, банк. <b>Уровень останется.</b><br>
    После вайпа у всех будет ⭐ ${fmt(w.start || 0)}, а банк поблагодарит каждого: вернёт часть того, что ты внёс в него за сезон.<br>
    За несколько минут до вайпа игры закроются.</p><div class="btns"><button class="btn" data-m="ok">Понятно</button></div>`);
}

// ---------------- письмо «Банк благодарит за игру» (итоги прошлого сезона + благодарность) ----------------
let WP_SHOWN = 0;
const wpDay = ts => new Date(ts * 1000).toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit" });
function wipeThanks() {
  const t = ME && ME.wipe && ME.wipe.thanks; if (!t || WP_SHOWN === t.wipe || document.querySelector(".wp-ov")) return;
  WP_SHOWN = t.wipe;
  const x = t.stats || {}, has = t.amount > 0, played = (x.rounds || 0) > 0 || (x.hours || 0) > 0;
  const what = t.kind === "buy" ? "купленных за сезон звёзд" : "того, что ты внёс в банк за сезон";
  const hrs = h => h < 1 ? "<1" : String(+(+h).toFixed(1)).replace(".", ",");
  const tile = (icon, v, label, cls = "") => `<div class="wp-t ${cls}"><i>${ic(icon)}</i><b>${v}</b><span>${label}</span></div>`;
  const maxG = Math.max(1, ...(x.games || []).map(g => g[1]));
  const ov = document.createElement("div");
  ov.className = "wp-ov";
  const tName = esc(t.name || ME.name || "игрок");
  ov.innerHTML = `<div class="wp-frame"><div class="wp-card">
      <div class="wp-sheen"></div><div class="wp-rays"></div><div class="wp-mono">NP</div>
      <div class="wp-top s1"><i></i><span>Итоги сезона ${t.ended}</span><i></i></div>
      ${t.from ? `<div class="wp-dates s1">${wpDay(t.from)} — ${wpDay(t.to)}</div>` : ""}
      <div class="wp-seal s2"><div>${ic("bank")}</div></div>
      <div class="wp-greet s3">Дорогой друг,</div>
      <h2 class="wp-name s3">${tName}</h2>
      <p class="wp-lead s4">${t.bad ? `Сезон ${t.ended} завершён. Вот каким получился твой сезон.` : played ? `Сезон ${t.ended} завершён. Благодарим тебя за игру — вот каким получился твой сезон.` : `Сезон ${t.ended} завершён. Благодарим, что ты с нами — новый сезон уже начался.`}</p>
      <div class="wp-orn s4"><i></i><b>✦</b><i></i></div>
      ${played ? `<div class="wp-grid s5">
        ${tile("clock", `${hrs(x.hours)} ч`, "в игре")}
        ${tile("games", fmt(x.rounds), "раундов сыграно")}
        ${tile("trend", `+${short(x.earned)}`, "заработано ⭐", "g")}
        ${tile("activity", `−${short(x.spent)}`, "потрачено ⭐", "r")}
        ${x.best ? tile("trophy", `+${short(x.best)}`, `лучший выигрыш · ${esc(x.bestGame)}`, "y") : ""}
        ${tile("bank", short(t.base), t.kind === "buy" ? "куплено ⭐" : "внесено в банк ⭐")}
      </div>
      ${(x.games || []).length ? `<div class="wp-fav s6"><div class="wp-h">Любимые игры</div>${x.games.map((g, i) => `<div class="wp-g"><span><em>${i + 1}</em>${esc(g[0])}</span>
        <i><u style="width:${Math.max(6, Math.round(g[1] / maxG * 100))}%"></u></i><b>${fmt(g[1])}</b></div>`).join("")}</div>` : ""}` : ""}
      ${t.bad ? `<div class="wp-gift wp-bad s7"><div class="wp-h">Благодарность банка</div>
        <div class="wp-sum"><b>0</b><span class="st">⭐</span></div>
        <small>Ты себя плохо вёл — <b>багоюзер</b>. В этом сезоне банк благодарность не выдаёт. Играй честно — и в следующий раз она будет твоей.</small></div>` : ""}
      ${has ? `<div class="wp-gift s7"><div class="wp-h">Банк GiftBot благодарит тебя</div>
        <div class="wp-sum"><span class="st">⭐</span><b id="wp-n">0</b></div>
        <small>Ты получаешь <b>${String(t.pct).replace(".", ",")}%</b> от ${what}. Звёзды уже на балансе.</small></div>` : ""}
      <div class="wp-next s8"><b>Сезон ${t.season} начался</b><span>Всё сброшено, уровень сохранён. Старт — ⭐ ${fmt(t.start)}${has ? " + благодарность" : ""}.
        ${t.days ? `Вайп — раз в ${t.days} дней.` : ""}${t.next ? ` Следующий — ${wpDay(t.next)}.` : ""}</span></div>
      <div class="wp-sign s8"><span>С уважением и благодарностью,</span><b>Банк GiftBot</b></div>
      <button class="wp-btn s9" data-wp="ok"><span>${t.bad ? "Понятно" : has ? "Забрать и играть" : "Начать сезон"}</span></button>
    </div></div>`;
  document.body.appendChild(ov);
  requestAnimationFrame(() => ov.classList.add("on"));
  if (has) {
    const n = ov.querySelector("#wp-n");
    const io = new IntersectionObserver(es => {   // считаем сумму, когда до неё долистали
      if (!es[0].isIntersecting) return; io.disconnect();
      const t0 = performance.now(), dur = 1400;
      const step = now => { const k = Math.min(1, (now - t0) / dur), e = 1 - Math.pow(1 - k, 3); n.textContent = fmt(Math.round(t.amount * e)); if (k < 1) requestAnimationFrame(step); };
      requestAnimationFrame(step);
      setTimeout(() => { try { H.ok(); const r = n.getBoundingClientRect(); burst(r.left + r.width / 2, r.top + r.height / 2, ["#ffd76a", "#ffb33d", "#fff", "#7cc2ff"]); } catch (e) {} }, 1200);
    }, { threshold: .6 });
    setTimeout(() => io.observe(n), 450);
  }
  ov.addEventListener("click", e => {
    if (!e.target.closest("[data-wp]")) return;
    ov.classList.remove("on"); setTimeout(() => ov.remove(), 350);
    post("wipe/seen", { wipe: t.wipe }).catch(() => {});
    ME.wipe.thanks = null;
  });
}
const _loadMeWp = loadMe;
loadMe = async function () { await _loadMeWp(); setTimeout(wipeThanks, 600); };

// ---------------- админка: вкладка «Вайп» ----------------
async function admWipe(body) {
  const d = await api("admin/wipe"), c = d.cfg, ed = d.canEdit, n = d.now, now = Date.now() / 1000;
  const sw = (k, title, hint) => `<div class="row kv"><div class="grow"><div class="t">${title}</div>${hint ? `<div class="s" style="white-space:normal">${hint}</div>` : ""}</div>
    ${ed ? `<button class="sw${c[k] ? " on" : ""}" data-act="wp-sw" data-k="${k}" data-v="${c[k] ? 0 : 1}"></button>` : `<b>${c[k] ? "да" : "нет"}</b>`}</div>`;
  const field = (k, title, hint, unit, mode = "numeric") => `<div class="adm-odd"><div class="adm-oh"><b>${title}</b></div>${hint ? `<div class="adm-os">${hint}</div>` : ""}
    ${ed ? `<div class="adm-oc"><input class="adm-oi" inputmode="${mode}" data-k="${k}" value="${esc(Array.isArray(c[k]) ? c[k].join(", ") : String(c[k]).replace(".", ","))}"><span class="adm-op">${unit}</span>
      <button class="btn sm gold" data-act="wp-f" data-k="${k}">${ic("check")}</button></div>` : `<div class="adm-oc"><b>${esc(String(c[k]))} ${unit}</b></div>`}</div>`;
  body.innerHTML = `<div class="box">
      ${admKv("Сейчас", `<b>Сезон ${d.season}</b>`)}
      ${admKv("Начался", d.since ? admDate(d.since) : "с запуска игры")}
      ${admKv("Следующий вайп", c.on && c.next ? `<b>${admDate(c.next)}</b> · через ${wpLeft(c.next - now)}` : `<span class="hint">не запланирован</span>`)}
      ${d.running || d.frozen ? admKv("Статус", `<b class="tw">${d.running ? "идёт вайп" : "игры закрыты перед вайпом"}</b>`) : ""}</div>

    <div class="sec-t">Если вайп будет сейчас</div>
    <div class="box">${admKv("Игроков", fmt(n.players))}${admKv("Звёзд на балансах", `⭐ ${fmt(n.stars)}`)}${admKv("Подарков", fmt(n.gifts))}
      ${admKv("Бизнесов", fmt(n.biz))}${admKv("В казне кланов", `⭐ ${fmt(n.treasury)}`)}
      ${admKv("Благодарность банка", `<b class="tw">⭐ ${fmt(d.thanks.total)}</b> · ${fmt(d.thanks.players)} игр.`)}</div>
    ${d.thanks.top.length ? `<div class="box">${d.thanks.top.map(u => `<div class="row kv">${avaHTML(u, 30)}<div class="grow"><div class="t">${esc(u.name)}</div>
      <div class="s">внёс ⭐ ${fmt(u.base)}</div></div><b>+⭐ ${fmt(u.amount)}</b></div>`).join("")}</div>` : ""}

    <div class="sec-t">Расписание</div>
    <div class="box">
      ${sw("on", "Вайпы по расписанию", "Выключено — вайп только кнопкой ниже")}
      <div class="adm-odd"><div class="adm-oh"><b>Дата следующего вайпа</b></div><div class="adm-os">по Москве</div>
        ${ed ? `<div class="adm-oc"><input class="adm-oi" type="datetime-local" id="wp-next" value="${wpMsk(c.next)}" style="flex:1">
          <button class="btn sm gold" data-act="wp-next">${ic("check")}</button></div>` : `<div class="adm-oc"><b>${admDate(c.next)}</b></div>`}</div>
      ${field("days", "Длина сезона", "после вайпа следующий назначается сам через столько дней; 0 — только вручную", "дн")}
      ${field("warn", "Предупредить игроков за", "через запятую, например 24, 3, 1", "ч", "text")}
      ${field("freeze", "Закрыть игры за", "чтобы не успели поставить старые звёзды и вывести выигрыш после вайпа", "мин")}
    </div>

    <div class="sec-t">После вайпа</div>
    <div class="box">
      ${field("start", "Стартовый баланс", "у всех одинаковый", "⭐")}
      ${field("thanks_pct", "Благодарность банка", "сколько % вернуть каждому в начале нового сезона; 0 — выключено", "%", "decimal")}
      ${field("thanks_cap", "Потолок благодарности", "не больше столько одному игроку; 0 — без потолка", "⭐")}
      ${field("deny", "Без благодарности в этот вайп", "id игроков через запятую — багоюзеры; в письме им напишет «ты себя плохо вёл». После вайпа список очищается", "", "text")}
      ${d.deny.length ? `<div class="adm-os" style="padding:0 14px 10px">${d.deny.map(u => `${esc(u.name)} (${u.id})`).join(", ")}</div>` : ""}
      <div class="adm-odd"><div class="adm-oh"><b>От чего считать</b></div>
        <div class="seg" style="margin-top:6px">${Object.entries(d.bases).map(([k, t]) => `<button ${ed ? `data-act="wp-base" data-v="${k}"` : "disabled"} class="${c.thanks_base === k ? "on" : ""}">${k === "bank" ? "Вклад в банк" : "Покупки звёзд"}</button>`).join("")}</div>
        <div class="adm-os" style="margin-top:6px">${esc(d.bases[c.thanks_base])}</div></div>
    </div>

    <div class="sec-t">Что сбрасывать</div>
    <div class="box">
      ${admKv("Звёзды на балансе", "<b>всегда</b>")}
      ${Object.entries(d.parts).map(([k, t]) => sw(k, esc(t), "")).join("")}
      ${admKv("Уровень и опыт", `<b class="tw">остаются</b>`)}
    </div>
    <div class="disc">Всегда отменяются открытые обмены, дуэли, столы и ставки в незаконченных играх. Остаются профиль, титулы, друзья, рефералы, кланы (без казны), боты и история.</div>

    ${ed ? `<button class="btn ghost" data-act="wp-ann" style="margin-top:14px">${ic("megaphone")}Разослать условия сезона всем</button>` : ""}
    ${ed ? `<button class="btn red" data-act="wp-now" style="margin-top:14px"${d.running ? " disabled" : ""}>${ic("refresh")}Вайп сейчас</button>` : ""}

    ${d.last.length ? `<div class="sec-t">Прошлые вайпы</div><div class="box">${d.last.map(w => `<div class="row kv"><div class="grow"><div class="t">Сезон ${w.season || "?"} → ${(w.season || 0) + 1} · ${admDate(w.ts)}${w.by ? "" : " · авто"}</div>
      <div class="s">${fmt(w.players)} игр. · ⭐ ${fmt(w.stars)} · подарков ${fmt(w.gifts)} · бизнесов ${fmt(w.biz)}</div></div><b>+⭐ ${fmt(w.thanks || 0)}</b></div>`).join("")}</div>` : ""}`;
  starify(body);
}
const wpSave = async (o, msg = "Сохранено") => { await post("admin/wipe", o); H.ok(); toast(msg, "ok"); admRender(); loadMe().catch(() => {}); };

Object.assign(ACT, {
  "wipe-info": () => wipeInfo(),
  "wp-sw": el => wpSave({ [el.dataset.k]: el.dataset.v === "1" }, el.dataset.v === "1" ? "Включено" : "Выключено"),
  "wp-f": el => { const k = el.dataset.k; return wpSave({ [k]: topSheet().querySelector(`.adm-oi[data-k="${k}"]`).value }); },
  "wp-base": el => wpSave({ thanks_base: el.dataset.v }),
  "wp-next": () => { const v = topSheet().querySelector("#wp-next").value; return wpSave({ next: wpFromMsk(v) }, v ? "Дата сохранена" : "Дата убрана"); },
  "wp-ann": async () => {
    const d = await api("admin/wipe/announce");
    const html = esc(d.text.replace(/<[^>]+>/g, "")).replace(/\n/g, "<br>");
    if (!await modal(`<h3>Разослать всем?</h3><div class="hint" style="max-height:50vh;overflow:auto;text-align:left;font-size:12.5px;line-height:1.45;margin:0 0 14px">${html}</div>
      <div class="btns"><button class="btn ghost" data-m="no">Отмена</button><button class="btn" data-m="ok">Разослать</button></div>`)) return;
    await post("admin/wipe/announce"); H.ok(); toast("Рассылка пошла — уйдёт за пару минут", "ok");
  },
  "wp-now": async () => {
    const v = await modal(`<h3>Вайп сейчас?</h3><p class="hint" style="margin:0 0 12px">Сбросятся звёзды, подарки, бизнесы и всё, что включено. Отменить нельзя. Всем игрокам придёт сообщение. Введи <b>ВАЙП</b>:</p>
      <input value=""><div class="btns"><button class="btn ghost" data-m="no">Отмена</button><button class="btn red" data-m="ok">Сбросить</button></div>`);
    if (!v) return;
    await post("admin/wipe/now", { confirm: v }); H.ok(); toast("Вайп запущен", "ok"); setTimeout(() => { admRender(); loadMe().catch(() => {}); }, 6000);
  },
});
