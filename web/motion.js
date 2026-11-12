"use strict";
// ============================================================
//  Плавный переход между вкладками: View Transitions (где есть) или CSS-анимация вкладки.
//  Направление — в сторону нажатой кнопки нижнего меню.
// ============================================================
const _stMotion = setTab;
setTab = function (t) {
  const prev = TAB, pv = $("#v-" + prev);
  const calm = window.LITE || matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (t === prev || calm || !pv || !pv.innerHTML) return _stMotion(t);
  const order = [...document.querySelectorAll("nav.tabs button")].map(b => b.dataset.tab);
  const dir = order.indexOf(t) >= order.indexOf(prev) ? 1 : -1;
  document.documentElement.style.setProperty("--vdir", dir);
  if (document.startViewTransition && !document.querySelector(".sheet.on")) {
    document.documentElement.classList.add("vt-tab");
    try {
      const tr = document.startViewTransition(() => { _stMotion(t); });
      tr.finished.finally(() => document.documentElement.classList.remove("vt-tab"));
      return;
    } catch (e) { document.documentElement.classList.remove("vt-tab"); }
  }
  _stMotion(t);
  const v = $("#v-" + t); if (!v) return;
  v.classList.remove("v-in"); void v.offsetWidth; v.classList.add("v-in");
  clearTimeout(v._vin); v._vin = setTimeout(() => v.classList.remove("v-in"), 400);
};

// карточки кейсов и игр за экраном ставят анимации на паузу (лучи, мерцание) — меньше работы видеокарте при прокрутке
(() => {
  if (!("IntersectionObserver" in window)) return;
  const io = new IntersectionObserver(es => es.forEach(e => e.target.classList.toggle("off", !e.isIntersecting)), { rootMargin: "120px 0px" });
  let queued = false;
  const scan = () => { queued = false; document.querySelectorAll(".case:not([data-io]),.gcard:not([data-io])").forEach(c => { c.dataset.io = "1"; io.observe(c); }); };
  new MutationObserver(() => { if (!queued) { queued = true; requestAnimationFrame(scan); } }).observe(document.querySelector("main") || document.body, { childList: true, subtree: true });
  scan();
})();
