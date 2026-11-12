"use strict";
// ============================================================
//  Личные рекорды (records.py): всплывашка «Новый рекорд», блок рекордов в профиле
// ============================================================
const REC_FMT = r => r.kind === "x" ? "x" + (+r.value).toFixed(2).replace(/\.?0+$/, "") : "⭐ " + fmt(r.value);
let recT = 0, recBusy = false;
function recSoon() {   // вызывается из apiFetch, когда сервер прислал X-Rec; таймер не сбрасываем, иначе частые запросы игры его откладывают бесконечно
  if (!recT) recT = setTimeout(recShow, 2600);
}
async function recShow() {
  recT = 0;
  if (recBusy) return;
  if (document.querySelector(".bw-ov") || document.querySelector("#modal.on")) { recT = setTimeout(recShow, 1500); return; }   // ждём, пока закроют большой выигрыш
  recBusy = true;
  try {
    const d = await api("records/new").catch(() => null);
    if (!d || !d.rec) return;
    const r = d.rec, old = document.querySelector(".rec-pop"); if (old) old.remove();
    const canShare = r.kind === "gift" ? !!r.gift : r.pay > 0;
    const el = document.createElement("div");
    el.className = "rec-pop";
    el.innerHTML = `<span class="rec-ic">${ic("trophy")}</span><div class="grow"><i>Новый рекорд</i><b>${esc(r.title)}</b>
        <span class="rec-v">${REC_FMT(r)}</span><span class="rec-was"><span>было</span> ${REC_FMT({ kind: r.kind, value: r.prev })}</span></div>
      <div class="rec-acts">${canShare ? `<button class="btn sm gold" data-rec="share">${ic("send")}Поделиться</button>` : ""}<button class="rec-x" data-rec="x">${ic("x")}</button></div>`;
    document.body.appendChild(el);
    starify(el);
    H.ok(); requestAnimationFrame(() => el.classList.add("on"));
    let hide = setTimeout(close, 9000);
    function close() { el.classList.remove("on"); setTimeout(() => el.remove(), 350); }
    el.addEventListener("click", e => {
      const b = e.target.closest("[data-rec]"); if (!b) return;
      if (b.dataset.rec === "x") return close();
      clearTimeout(hide);
      shareWin("chat", r.kind === "gift" ? { gift: r.gift.id, pay: 0 } : { pay: r.pay }, b).finally(() => { hide = setTimeout(close, 3000); });
    });
  } finally { recBusy = false; }
}

// блок рекордов во вкладке «Статистика» профиля
const _profileRec = profileHTML;
profileHTML = function (p, tab = "show") {
  let h = _profileRec(p, tab);
  if (tab === "stats") { h = h.replace('<div class="pst">', `<div class="p-recs" data-id="${p.id}"></div><div class="pst">`); setTimeout(recFill, 0); }
  return h;
};
async function recFill() {
  for (const box of document.querySelectorAll(".p-recs:not([data-done])")) {
    box.dataset.done = "1";
    const d = await api("records/" + box.dataset.id).catch(() => null);
    if (!d || !d.items.length || !box.isConnected) continue;
    box.innerHTML = `<div class="sec-t">${ic("trophy")}Рекорды</div><div class="rec-grid">${d.items.map(r => `<div class="rec-c">
      ${r.gift ? `<img src="${A.model(r.gift.col, r.gift.model, 64)}" alt="">` : `<span class="rec-ci">${ic(r.kind === "x" ? "trend" : "coins")}</span>`}
      <b>${REC_FMT(r)}</b><span>${esc(r.title)}</span></div>`).join("")}</div>`;
    starify(box);
  }
}

// кнопка на открытую страницу банка (web/bank.html) внизу экрана банка
const _fillBKPub = fillBK;
fillBK = function (el) {
  _fillBKPub(el);
  const body = el && el.querySelector("#bk-body");
  if (!body || body.querySelector(".bk-pub") || (typeof BK_TAB !== "undefined" && BK_TAB !== "bank")) return;
  body.insertAdjacentHTML("beforeend", `<button class="ideabtn bk-pub" data-act="bank-pub">${ic("eye")}<span><b>Открытая страница банка</b>цифры банка и возврат по играм, видны всем без входа</span>${ic("chev")}</button>`);
};
ACT["bank-pub"] = () => {
  const url = new URL("bank.html?lang=" + (typeof LANG === "string" && LANG === "en" ? "en" : "ru"), location.href.split("?")[0]).href;
  if (inTg && tg.openLink) tg.openLink(url); else window.open(url, "_blank");
};
