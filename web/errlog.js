"use strict";
// ошибки JS с устройства игрока — на сервер (журнал сервиса), чтобы чинить баги без доступа к телефону
(() => {
  let n = 0;
  const send = (m, s, l) => {
    if (++n > 15) return;
    try {
      const h = { "Content-Type": "application/json" };
      if (window.Telegram && Telegram.WebApp && Telegram.WebApp.initData) h["X-Init-Data"] = Telegram.WebApp.initData;
      fetch("api/clienterr", { method: "POST", headers: h, body: JSON.stringify({ m: String(m), s: String(s || ""), l, ua: navigator.userAgent }) }).catch(() => {});
    } catch (e) {}
  };
  addEventListener("error", e => {
    if (e.message === "Script error." && !e.filename) return;   // ошибка внутри колбэка telegram.org — браузер прячет детали; ловим её обёрткой ниже
    send(e.message + (e.error && e.error.stack ? " | " + String(e.error.stack).slice(0, 400) : ""), e.filename, e.lineno + ":" + e.colno);
  });
  // колбэки, которые вызывает скрипт Telegram (другой домен): заворачиваем, чтобы видеть настоящий текст и место ошибки
  const wrap = f => typeof f !== "function" || f._w ? f : Object.assign(function () {
    try { return f.apply(this, arguments); } catch (e) { send("tg-cb: " + (e && e.message) + (e && e.stack ? " | " + String(e.stack).slice(0, 400) : ""), "tg", 0); throw e; }
  }, { _w: 1 });
  const hook = (o, names) => names.forEach(k => {
    if (!o || typeof o[k] !== "function") return;
    const orig = o[k];
    o[k] = function () { return orig.apply(this, Array.from(arguments, wrap)); };
  });
  try {
    const W = window.Telegram && Telegram.WebApp;
    if (W) {
      hook(W, ["onEvent", "showScanQrPopup", "openInvoice", "showPopup", "showConfirm", "showAlert", "readTextFromClipboard", "requestContact", "requestWriteAccess"]);
      ["BackButton", "MainButton", "SecondaryButton", "SettingsButton"].forEach(b => hook(W[b], ["onClick"]));
    }
  } catch (e) {}
  addEventListener("unhandledrejection", e => { const r = e.reason; if (r && r.status) return; send(r && r.message ? r.message + (r.stack && !String(r.stack).includes(r.message) ? " | " + r.stack : "") : r && r.stack || r, "promise", 0); });   // Safari кладёт в stack только кадры, без текста
})();
