"use strict";
// ============================================================
//  Настройки устройства: режим оптимизации (для слабых телефонов), вибрация, уведомления от бота.
//  Хранятся в localStorage — у каждого телефона свои.
// ============================================================
ICONS.gear = '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>';
const PREF = (() => { try { return JSON.parse(localStorage.getItem("prefs") || "{}"); } catch (e) { return {}; } })();
// слабый телефон: Telegram на Android пишет класс производительности в конце user-agent (… ; LOW|AVERAGE|HIGH),
// плюс мало памяти. Тогда режим оптимизации включён по умолчанию; если игрок переключил его сам — решает он.
const WEAK_DEVICE = /;\s*LOW\)\s*$/.test(navigator.userAgent) || (navigator.deviceMemory > 0 && navigator.deviceMemory <= 2);
function prefApply() {
  window.LITE = PREF.lite != null ? !!PREF.lite : WEAK_DEVICE;
  window.NO_VIBRO = !!PREF.noVibro;
  document.documentElement.classList.toggle("lite", window.LITE);
}
function prefSave() { try { localStorage.setItem("prefs", JSON.stringify(PREF)); } catch (e) {} prefApply(); }
prefApply();
// слабый телефон (≤4 ядер и мало памяти) — предлагаем оптимизацию сами один раз
setTimeout(() => {
  try {
    if (PREF.asked || window.LITE) return;   // уже включён (вручную или сам на слабом телефоне)
    const weak = (navigator.hardwareConcurrency || 8) <= 4 || (navigator.deviceMemory || 8) <= 3;
    if (!weak) return;
    PREF.asked = true; prefSave();
    confirmM("Включить режим оптимизации?", "Похоже, телефон не самый мощный. Режим уберёт тяжёлые украшения — игра станет плавнее, а всё игровое останется. Поменять можно в профиле → Настройки.", "Включить")
      .then(ok => { PREF.lite = !!ok; prefSave(); if (ok) toast("Режим оптимизации включён", "ok"); });
  } catch (e) {}
}, 6000);

const LOOK_AC = ["#ffc53d", "#4f8cff", "#9b6bff", "#29c5e6", "#2fd08a", "#ff5f9e", "#ff6b4a"];
const lookOn = c => { const n = parseInt(c.slice(1), 16), l = .299 * (n >> 16) + .587 * (n >> 8 & 255) + .114 * (n & 255); return l > 165 ? "#2a1c00" : "#ffffff"; };
const lookGet = (k, d) => { try { const v = localStorage.getItem(k); return v === null ? d : v; } catch (e) { return d; } };
const lookAc = () => lookGet("ac", LOOK_AC[0]);
const lookGp = () => +lookGet("glass", 60);
function lookGlass(v) {
  document.documentElement.style.setProperty("--gp", v);
  try { localStorage.setItem("glass", v); } catch (e) {}
  const l = $("#look-gv"); if (l) l.textContent = v + "%";
}
function openSettings() {
  const row = (k, t, s, on) => `<div class="row kv"><div class="grow"><div class="t">${t}</div><div class="s" style="white-space:normal">${s}</div></div><button class="sw${on ? " on" : ""}" data-act="pref" data-k="${k}"></button></div>`;
  openSheet(`<h2 class="gtitle">${ic("gear")} Настройки</h2>
    <div class="box">
      ${row("lite", "Режим оптимизации", `Для слабых телефонов: без размытий, фоновых эффектов, бесконечных анимаций и анимированных подарков, меньше монет и конфетти${PREF.lite == null && WEAK_DEVICE ? " · включён сам: телефон слабый" : ""}`, window.LITE)}
      ${row("sound", "Звук", "Тики рулеток, звон монет, фанфары на крупном выигрыше", !PREF.noSound)}
      ${row("vibro", "Вибрация", "Отклик телефона на нажатия, выигрыши и проигрыши", !PREF.noVibro)}
      ${row("notif", "Уведомления от бота", "Бесплатный кейс, серия бонусов, твой ход за столом, дивиденды", ME.notif !== false)}
    </div>
    <div class="box lookb"><div class="t">Цвет акцента</div>
      <div class="swatches">${LOOK_AC.map(c => `<button data-act="look-ac" data-v="${c}" style="--c:${c}" class="${lookAc() === c ? "on" : ""}" aria-label="${c}"></button>`).join("")}</div>
      <div class="lookr"><span class="t">Прозрачность</span><b id="look-gv">${lookGp()}%</b></div>
      <input type="range" class="drange" id="look-g" min="0" max="100" step="5" value="${lookGp()}" oninput="lookGlass(this.value)"></div>
    <div class="box"><div class="row kv"><div class="grow"><div class="t">Язык</div>${LANG === "en" ? `<div class="s">Часть текста пока на русском</div>` : ""}</div>
      <div class="chips" style="margin:0"><button data-act="set-lang" data-v="ru" class="${LANG === "ru" ? "on" : ""}">RU</button><button data-act="set-lang" data-v="en" class="${LANG === "en" ? "on" : ""}">EN</button></div></div></div>
    <div class="box">
      <div class="row tap" data-act="fair"><span class="pic g">${ic("shield")}</span><div class="grow"><div class="t">Честность</div><div class="s">Provably fair: сиды, хэши и проверка каждой ставки прямо здесь</div></div>${ic("chev")}</div>
      <div class="row tap" data-act="limits"><span class="pic b">${ic("clock")}</span><div class="grow"><div class="t">Лимиты и перерыв</div><div class="s">Дневной лимит проигрыша и перерыв от суток</div></div>${ic("chev")}</div>
    </div>
    <div class="disc">Сборка ${(document.querySelector('script[src*="bundle.js"]') || { src: "" }).src.split("v=")[1] || "dev"}</div>`);
}
Object.assign(ACT, {
  "look-ac": el => {
    document.documentElement.style.setProperty("--ac", el.dataset.v);
    document.documentElement.style.setProperty("--ac-on", lookOn(el.dataset.v));
    try { localStorage.setItem("ac", el.dataset.v); } catch (e) {}
    document.querySelectorAll(".swatches button").forEach(b => b.classList.toggle("on", b === el)); H.sel();
  },
  "set-lang": el => { if (el.dataset.v === LANG) return; try { localStorage.setItem("lang", el.dataset.v); } catch (e) {} location.reload(); },
  settings: () => openSettings(),
  pref: async el => {
    const k = el.dataset.k, on = !el.classList.contains("on");
    el.classList.toggle("on", on);
    if (k === "lite") { PREF.lite = on; prefSave(); }
    else if (k === "vibro") { PREF.noVibro = !on; prefSave(); }
    else if (k === "sound") { PREF.noSound = !on; prefSave(); }
    else if (k === "notif") { await post("settings", { notif: on }); ME.notif = on; }
    H.sel();
  },
});
