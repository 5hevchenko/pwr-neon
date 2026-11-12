"use strict";
// ============================================================
//  Ярлык на экран телефона (Telegram.WebApp.addToHomeScreen, Bot API 8.0+)
// ============================================================
ICONS.phone = '<rect x="6" y="2" width="12" height="20" rx="3"/><path d="M11 18h2"/>';
let HOME = "unknown";   // unsupported | unknown | added | missed
const homeOk = () => !!(tg && tg.addToHomeScreen && tg.isVersionAtLeast && tg.isVersionAtLeast("8.0"));
function homeCheck() {
  if (!homeOk()) { HOME = "unsupported"; return; }
  try { tg.checkHomeScreenStatus(s => { HOME = s; homePaint(); }); } catch (e) { HOME = "unsupported"; }
}
function homeAdd() {
  if (!homeOk()) return toast("Твой Telegram не умеет ярлыки — обнови приложение на телефоне");
  H.imp("light");
  try { tg.addToHomeScreen(); } catch (e) {}
}
if (tg && tg.onEvent) tg.onEvent("homeScreenAdded", () => { HOME = "added"; homePaint(); H.ok(); toast("Ярлык добавлен на экран", "ok"); });

const homeHidden = () => { try { return localStorage.getItem("np_home_x") === "1"; } catch (e) { return false; } };
const homeCardHTML = () => `<div class="homecard"><span class="hc-i">${ic("phone")}</span><span class="hc-t"><b>Gift Cases на экран телефона</b><small>Открывай игру в одно касание, как обычное приложение</small></span>
  <button class="btn sm" data-act="home-add">Добавить</button><button class="hc-x" data-act="home-x" aria-label="Скрыть">${ic("x")}</button></div>`;
function homePaint() {
  const v = $("#v-cases");
  if (!v) return;
  const card = v.querySelector(".homecard");
  const show = HOME === "missed" && !homeHidden();
  if (!show) { if (card) card.remove(); return; }
  if (card) return;
  const anchor = v.querySelector(".jpbar") || v.querySelector(".promo");
  if (anchor) anchor.insertAdjacentHTML("afterend", homeCardHTML());
}
Object.assign(ACT, {
  "home-add": () => homeAdd(),
  "home-x": () => { try { localStorage.setItem("np_home_x", "1"); } catch (e) {} homePaint(); H.sel(); },
});
const _rcH = renderCases;
renderCases = async function () { await _rcH(); homePaint(); };

// пункт в редакторе профиля — всегда доступен, даже если карточку скрыли
const _epH = editProfile;
editProfile = async function () {
  const r = await _epH.apply(this, arguments);
  const s = SHEETS[SHEETS.length - 1];
  const save = s && s.querySelector(".esave");
  if (save && homeOk() && HOME !== "added") save.insertAdjacentHTML("beforebegin", `<div class="sec-t">Ярлык</div><div class="box"><div class="row tap" data-act="home-add"><span class="pic b">${ic("phone")}</span>
    <div class="grow"><div class="t">Добавить на экран телефона</div><div class="s">запуск игры одним касанием</div></div>${ic("chev")}</div></div>`);
  return r;
};
homeCheck();
