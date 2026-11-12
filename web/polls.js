//  Опросы (polls.py): плашка с вопросом у всех в игре (всплывает при входе, пока не ответил, + карточка на главной),
//  вкладка «Опросы» в админке — создать опрос, живая статистика (обновляется сама), закончить досрочно.
const plStrip = s => String(s || "").replace(/<[^>]+>/g, "");
const plTitle = p => plStrip(p.text.split("\n")[0]).replace(/^📊\s*/, "");
const plBody = p => esc(plStrip(p.text.split("\n").slice(1).join("\n")).trim()).replace(/\n/g, "<br>");
const plPct = (a, t) => t ? Math.round(a * 100 / t) : 0;
const plLeft = s => { s = Math.max(0, s); const d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.ceil(s % 3600 / 60);
  return d ? `${d} д ${h} ч` : h ? `${h} ч ${m} мин` : `${m} мин`; };

function plBars(p) {
  const t = (p.y || 0) + (p.n || 0), py = plPct(p.y || 0, t), pn = t ? 100 - py : 0;
  const bar = (ch, label, v, pc) => `<div class="pl-bar${ch === "n" ? " no" : ""}${p.my === ch ? " my" : ""}"><i style="width:${pc}%"></i><span>${esc(label)}${p.my === ch ? " · твой голос" : ""}</span><b>${pc}% · ${fmt(v)}</b></div>`;
  return bar("y", p.yes, p.y || 0, py) + bar("n", p.no, p.n || 0, pn) + `<div class="pl-tot">Проголосовали ${fmt(t)} · до конца ${plLeft(p.ends - Date.now() / 1000)}</div>`;
}
function plInner(p) {
  return `<div class="pl-q">${esc(plTitle(p))}</div>${plBody(p) ? `<div class="pl-d">${plBody(p)}</div>` : ""}
    ${p.my ? plBars(p) + `<button class="pl-ch" data-act="pl-vote" data-id="${p.id}" data-ch="${p.my === "y" ? "n" : "y"}">Передумал — ${esc(p.my === "y" ? p.no : p.yes)}</button>`
      : `<div class="pl-btns"><button class="btn pl-y" data-act="pl-vote" data-id="${p.id}" data-ch="y">${esc(p.yes)}</button><button class="btn ghost pl-n" data-act="pl-vote" data-id="${p.id}" data-ch="n">${esc(p.no)}</button></div>`}`;
}

// ---------------- главная: карточка опроса ----------------
function pollCard() {
  const p = ME && (ME.polls || [])[0]; if (!p) return "";
  return `<button class="stc st-poll" data-act="pl-open" data-id="${p.id}"><span class="stc-i">${ic("activity")}</span><span class="stc-t"><b>Опрос: ${esc(plTitle(p))}</b>
    <small>${p.my ? `Твой голос: ${esc(p.my === "y" ? p.yes : p.no)} · ${fmt((p.y || 0) + (p.n || 0))} голосов — посмотри итоги` : "Нажми и проголосуй — это займёт секунду"}</small></span>${ic("chev")}</button>`;
}

// ---------------- плашка-окно с вопросом ----------------
const PL_SKIP = new Set();
function pollShow(p, force) {
  if (!p || document.querySelector(".pl-ov") || document.querySelector(".wp-ov")) return;
  if (!force && (p.my || (!p.must && PL_SKIP.has(p.id)))) return;
  const ov = document.createElement("div");
  ov.className = "pl-ov" + (p.must && !p.my ? " must" : "");
  ov.innerHTML = `<div class="pl-card" data-id="${p.id}">${p.must && !p.my ? "" : `<button class="pl-x" data-act="pl-close" aria-label="Закрыть">${ic("x")}</button>`}
    <div class="pl-badge">${ic("activity")}<span>${p.must ? "Важное голосование" : "Голосование"}</span></div><div class="pl-in">${plInner(p)}</div>
    <div class="pl-foot">🔒 Анонимно — никто не увидит, кто как голосовал</div></div>`;
  ov.addEventListener("click", e => { if (e.target === ov && !ov.classList.contains("must")) pollClose(); });
  document.body.appendChild(ov);
  requestAnimationFrame(() => ov.classList.add("on"));
}
function pollClose() {
  const ov = document.querySelector(".pl-ov"); if (!ov || ov.classList.contains("must")) return;
  PL_SKIP.add(+ov.querySelector(".pl-card").dataset.id);
  ov.classList.remove("on"); setTimeout(() => ov.remove(), 250);
}
// раз в минуту — новый опрос всплывёт сразу, без перезахода; обязательный, если его как-то убрали, вернётся
setInterval(async () => {
  if (!ME || document.hidden) return;
  try { const d = await api("poll/active"); ME.polls = d.polls; } catch (e) { return; }
  pollShow((ME.polls || []).find(p => !p.my));
}, 60000);
const _loadMePl = loadMe;
loadMe = async function () { await _loadMePl(); setTimeout(() => pollShow((ME.polls || []).find(p => !p.my)), 1400); };

// ---------------- админка: вкладка «Опросы» ----------------
let PL_T = 0;
async function admPolls(body) {
  const d = await api("admin/polls"), t = d.now;
  const row = p => {
    const tot = p.y + p.n, py = plPct(p.y, tot), turn = p.reach ? Math.round(tot * 100 / p.reach) : 0;
    const where = [p.ingame ? (p.must ? "в игре (обязательно)" : "в игре") : "", p.bot ? "в боте" : ""].filter(Boolean).join(" + ");
    const maxH = Math.max(1, ...p.hours.map(h => h.y + h.n));
    return `<div class="box pl-adm${p.active ? " on" : ""}">
      <div class="pl-ah"><b>${esc(p.title)}</b><span class="adm-tag">${p.active ? `идёт · ещё ${plLeft(p.ends - t)}` : "закончен"}</span></div>
      <div class="pl-am">${admDate(p.created)} · ${where}</div>
      <div class="pl-bar big"><i style="width:${py}%"></i><span>${esc(p.yes)}</span><b>${py}% · ${fmt(p.y)}</b></div>
      <div class="pl-bar big no"><i style="width:${tot ? 100 - py : 0}%"></i><span>${esc(p.no)}</span><b>${tot ? 100 - py : 0}% · ${fmt(p.n)}</b></div>
      <div class="pl-stats"><div><b>${fmt(tot)}</b><span>голосов</span></div><div><b>${fmt(p.reach)}</b><span>${p.ingame ? "заходили" : "получили"}</span></div><div><b>${turn}%</b><span>явка</span></div></div>
      ${p.hours.length > 1 ? `<div class="pl-hist">${p.hours.map(h => `<i title="${h.h} ч: ${h.y}/${h.n}" style="height:${Math.max(4, (h.y + h.n) * 100 / maxH)}%"><u style="height:${plPct(h.y, h.y + h.n)}%"></u></i>`).join("")}</div><div class="pl-am">голоса по часам (жёлтое — «${esc(p.yes)}»)</div>` : ""}
      ${p.last.length ? `<details class="pl-last"><summary>Последние голоса</summary>${p.last.map(v => `<div class="row kv"><div class="grow"><div class="t">${esc(v.name || "игрок")}</div><div class="s">${admDate(v.ts)}</div></div><b class="${v.choice === "y" ? "tw" : ""}">${esc(v.choice === "y" ? p.yes : p.no)}</b></div>`).join("")}</details>` : ""}
      ${p.active ? `<button class="btn ghost sm" data-act="pl-end" data-id="${p.id}" style="margin-top:10px;width:100%">Закончить сейчас и прислать итоги</button>` : ""}
    </div>`;
  };
  body.innerHTML = `<div class="sec-t">Новый опрос</div>
    <div class="box pl-new">
      <input class="adm-oi" id="pl-title" maxlength="150" placeholder="Вопрос, например: Делать вайп прямо сейчас?">
      <textarea class="adm-oi" id="pl-desc" rows="3" maxlength="800" placeholder="Пояснение (необязательно)"></textarea>
      <div class="pl-2"><input class="adm-oi" id="pl-yes" maxlength="30" value="Да" placeholder="Кнопка 1"><input class="adm-oi" id="pl-no" maxlength="30" value="Нет" placeholder="Кнопка 2"></div>
      <div class="pl-2"><label>Длится, часов<input class="adm-oi" id="pl-h" inputmode="decimal" value="6"></label></div>
      <div class="row kv"><div class="grow"><div class="t">Плашка в игре</div><div class="s">всплывает у всех при входе, пока не ответят</div></div><button class="sw on" id="pl-ig" data-act="pl-tg"></button></div>
      <div class="row kv"><div class="grow"><div class="t">Важное — нельзя закрыть</div><div class="s">плашка висит поверх игры, пока игрок не проголосует</div></div><button class="sw on" id="pl-mu" data-act="pl-tg"></button></div>
      <div class="row kv"><div class="grow"><div class="t">Сообщение в боте</div><div class="s">с кнопками, всем игрокам</div></div><button class="sw" id="pl-bt" data-act="pl-tg"></button></div>
      <button class="btn" data-act="pl-new" style="width:100%;margin-top:8px">Запустить опрос</button>
    </div>
    <div class="sec-t">Опросы · обновляется само</div>
    ${d.polls.map(row).join("") || `<div class="box"><div class="hint" style="padding:14px">Опросов пока не было</div></div>`}`;
  clearTimeout(PL_T);
  PL_T = setTimeout(() => { if (ADM.tab === "polls" && body.isConnected && !body.querySelector(".pl-new :focus") && !body.querySelector(".pl-last[open]")) admPolls(body).catch(() => {}); }, 5000);
}

Object.assign(ACT, {
  "pl-open": el => pollShow((ME.polls || []).find(p => p.id === +el.dataset.id), true),
  "pl-close": () => pollClose(),
  "pl-vote": async el => {
    const id = +el.dataset.id, r = await post("poll/vote", { id, ch: el.dataset.ch });
    H.ok();
    const p = (ME.polls || []).find(x => x.id === id);
    if (p) Object.assign(p, r);
    const card = document.querySelector(`.pl-card[data-id="${id}"]`), box = card && card.querySelector(".pl-in");
    if (box && p) box.innerHTML = plInner(p);
    const ov = card && card.closest(".pl-ov");
    if (ov && ov.classList.contains("must")) {   // проголосовал — можно закрыть
      ov.classList.remove("must");
      card.insertAdjacentHTML("afterbegin", `<button class="pl-x" data-act="pl-close" aria-label="Закрыть">${ic("x")}</button>`);
      card.querySelector(".pl-foot").insertAdjacentHTML("beforebegin", `<button class="btn" data-act="pl-close" style="width:100%;margin-top:14px">Спасибо, продолжить</button>`);
    }
    if (typeof casesTidy === "function") casesTidy();
  },
  "pl-tg": el => el.classList.toggle("on"),
  "pl-new": async () => {
    const s = topSheet(), v = id => s.querySelector("#" + id).value;
    const b = { title: v("pl-title"), desc: v("pl-desc"), yes: v("pl-yes"), no: v("pl-no"), hours: parseFloat(v("pl-h").replace(",", ".")) || 6,
      ingame: s.querySelector("#pl-ig").classList.contains("on"), bot: s.querySelector("#pl-bt").classList.contains("on"), must: s.querySelector("#pl-mu").classList.contains("on") };
    if (!await modal(`<h3>Запустить опрос?</h3><p class="hint" style="margin:0 0 12px">«${esc(b.title)}» — ${esc(b.yes)} / ${esc(b.no)}, ${String(b.hours).replace(".", ",")} ч${b.ingame ? (b.must ? ", плашка поверх игры у всех — не закрыть, пока не проголосуют" : ", плашка у всех в игре") : ""}${b.bot ? ", сообщение в бот всем" : ""}.</p>
      <div class="btns"><button class="btn ghost" data-m="no">Отмена</button><button class="btn" data-m="ok">Запустить</button></div>`)) return;
    await post("admin/polls", b); H.ok(); toast("Опрос запущен", "ok"); admRender(); loadMe().catch(() => {});
  },
  "pl-end": async el => {
    if (!await modal(`<h3>Закончить опрос?</h3><p class="hint" style="margin:0 0 12px">Голосование закроется, итоги придут админам в бота.</p><div class="btns"><button class="btn ghost" data-m="no">Отмена</button><button class="btn" data-m="ok">Закончить</button></div>`)) return;
    await post(`admin/polls/${el.dataset.id}/end`); H.ok(); toast("Опрос закончен", "ok"); admRender(); loadMe().catch(() => {});
  },
});
