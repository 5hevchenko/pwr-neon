"use strict";
// ============================================================
//  «Ограбление сейфа» (server/heist.py): не заходишь — грабители ломают сейф, через неделю уносят звёзды, кроме купленных.
//  Здесь — что показать вернувшемуся игроку и строка с правилом в окне баланса.
// ============================================================
let HEIST = null;
const HEIST_STAGE = { 1: "присматривались к сейфу", 2: "подбирали отмычки", 3: "сверлили замок", 5: "почти вскрыли замок", 6: "были в шаге от взлома" };
(async function heistBoot() {
  for (let i = 0; i < 60 && !(typeof ME !== "undefined" && ME); i++) await sleep(500);
  if (!ME) return;
  HEIST = await api("heist", null, { quiet: true }).catch(() => null);
  const b = HEIST && HEIST.back; if (!b) return;
  await sleep(1200);
  if (b.burned) {
    H.err(); loadMe().catch(() => {});
    openSheet(`<h2 class="gtitle">Ограбление</h2>
      <div class="hs-box"><i>💥</i><b>Грабители унесли ⭐ ${fmt(b.loot)}</b>
        <p>Тебя не было ${b.days} ${plural(b.days, ["день", "дня", "дней"])}, и сейф не выдержал.${b.kept ? ` Купленные звёзды на месте: ⭐ ${fmt(b.kept)}.` : ""}</p>
        <p>Заходи хотя бы раз в ${HEIST.rule.days} дней — и грабители останутся ни с чем.</p></div>
      <div class="btns"><button class="btn cta" data-act="close">Понятно</button></div>`, "hs-s");
  } else {
    H.ok();
    openSheet(`<h2 class="gtitle">Сейф цел</h2>
      <div class="hs-box"><i>🏃</i><b>Грабители сбежали: ⭐ ${fmt(b.loot)} на месте</b>
        <p>Тебя не было ${b.days} ${plural(b.days, ["день", "дня", "дней"])} — они уже ${HEIST_STAGE[b.stage] || "крутились у сейфа"}. Ты вернулся вовремя.</p>
        <p>Если не заходить ${HEIST.rule.days} дней, сейф вскроют и унесут все звёзды, кроме купленных.</p></div>
      <div class="btns"><button class="btn cta" data-act="close">Отлично</button></div>`, "hs-s");
  }
})();
// правило — в окне баланса, рядом с пакетами звёзд
const _sfHeist = shopFill;
shopFill = async function () {
  await _sfHeist.apply(this, arguments);
  const box = $("#shop-box"), note = box && box.querySelector(".shop-note");
  if (!note || box.querySelector(".hs-rule") || !HEIST || !HEIST.rule.on) return;
  note.insertAdjacentHTML("afterend", `<div class="shop-note hs-rule">${ic("lock")}<span>Сейф под охраной, пока ты заходишь. Если не появляться ${HEIST.rule.days} дней, грабители унесут звёзды с баланса — все, кроме купленных.</span></div>`);
};
