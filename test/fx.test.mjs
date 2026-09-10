/* Курс на сегодня — правила без сети.
 *
 *     node --test test/fx.test.mjs
 *
 * Ручка `/api/fx` ходит к чужому сервису, и это единственное место на
 * странице, где число приходит **не от нас и не от Ни**. Значит проверять
 * надо не «умеем ли мы разобрать хороший ответ» — это скучная половина, — а
 * что мы делаем с плохим: с пустым, с нулём, со строкой вместо числа, с
 * успехом, внутри которого ошибка.
 *
 * Каждый такой ответ выглядит снаружи как удача. Непроверенный, он молча
 * превращает ¥292 805 в бессмыслицу на её экране — и заметить это будет
 * некому, потому что доллар на странице всегда «примерно».
 */

import assert from "node:assert/strict";
import test from "node:test";

import { CEILING, FLOOR, Rejected, dateOf, fresh, human, plausible, readRate }
  from "../site/functions/api/_fx.js";

const GOOD = {
  result: "success",
  time_last_update_utc: "Thu, 10 Sep 2026 00:02:31 +0000",
  rates: { JPY: 153.594001 },
};

test("хороший ответ разбирается и округляется до двух знаков", () => {
  const rate = readRate(GOOD, "2026-09-10");
  assert.equal(rate.usd_per_jpy, 153.59);
  assert.equal(rate.as_of, "2026-09-10");
});

test("шестой знак не доезжает до подписи", () => {
  /* Доллар на странице округляется до целого; лишние знаки в подписи
     обещали бы точность, которой у мерки нет. */
  const rate = readRate({ ...GOOD, rates: { JPY: 153.594001 } }, "2026-09-10");
  assert.equal(String(rate.usd_per_jpy).split(".")[1].length, 2);
});

test("успех, внутри которого ошибка, не считается успехом", () => {
  assert.throws(() => readRate({ result: "error", rates: { JPY: 153 } }), Rejected);
});

test("пустой ответ, пустые курсы и не-объект отбиваются словами", () => {
  for (const bad of [null, undefined, "153.59", 153.59, {}, { rates: null }, { rates: {} }]) {
    assert.throws(() => readRate(bad, "2026-09-10"), Rejected, JSON.stringify(bad));
  }
});

test("курс, не похожий на курс, не проходит", () => {
  /* Ноль и единица — самые опасные: они выглядят как число и молча делают
     доллар равным иене или бесконечности. */
  for (const bad of [0, 1, -153, NaN, Infinity, "153.59", null, FLOOR, CEILING, 1e6]) {
    assert.equal(plausible(bad), false, String(bad));
    assert.throws(() => readRate({ ...GOOD, rates: { JPY: bad } }, "2026-09-10"), Rejected);
  }
});

test("вилка широкая нарочно — настоящий курс внутри неё", () => {
  /* Узкая вилка вокруг сегодняшнего значения сломала бы страницу ровно в тот
     день, когда курс действительно уехал. */
  for (const real of [75.5, 100, 153.59, 158.88, 250, 359]) {
    assert.equal(plausible(real), true, String(real));
  }
});

test("дата берётся из ответа, а не из нашего «сегодня»", () => {
  /* Между обновлением на той стороне и нашим запросом проходит время;
     подписать чужое число своей датой значит соврать на несколько часов. */
  assert.equal(dateOf(GOOD, "2026-12-31"), "2026-09-10");
});

test("если даты в ответе нет, берётся наша — но только правильной формы", () => {
  assert.equal(dateOf({}, "2026-09-10"), "2026-09-10");
  assert.equal(dateOf({ time_last_update_unix: 1789084951 }, null).length, 10);
  assert.throws(() => dateOf({}, "вчера"), Rejected);
  assert.throws(() => dateOf({}, null), Rejected);
});

test("битая дата в ответе не превращается в Invalid Date", () => {
  assert.equal(dateOf({ time_last_update_utc: "когда-то" }, "2026-09-10"), "2026-09-10");
  assert.equal(dateOf({ time_last_update_unix: 0 }, "2026-09-10"), "2026-09-10");
});

test("свежим считается только сегодняшний кэш", () => {
  const kept = { usd_per_jpy: 153.59, as_of: "2026-09-10", fetched: "2026-09-10" };
  assert.equal(fresh(kept, "2026-09-10"), true);
  assert.equal(fresh(kept, "2026-09-11"), false, "вчерашний кэш не свежий");
  assert.equal(fresh(null, "2026-09-10"), false);
  assert.equal(fresh({ ...kept, fetched: undefined }, "2026-09-10"), false);
});

test("кэш с негодным курсом не считается свежим, даже сегодняшний", () => {
  /* Иначе один плохой ответ, однажды легший в хранилище, живёт сутки. */
  assert.equal(fresh({ usd_per_jpy: 0, fetched: "2026-09-10" }, "2026-09-10"), false);
  assert.equal(fresh({ usd_per_jpy: "153", fetched: "2026-09-10" }, "2026-09-10"), false);
});

test("человеческая дата пишется так же, как её печатает сборка", () => {
  assert.equal(human("2026-09-10"), "10 сентября 2026");
  assert.equal(human("2026-08-23"), "23 августа 2026");
  assert.equal(human("2027-01-04"), "4 января 2027");
  assert.equal(human("2026-9-10"), "", "полуформат не выдаём за дату");
  assert.equal(human(null), "");
});
