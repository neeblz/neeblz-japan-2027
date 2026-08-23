/* Её записи и её чек — правила проверяются здесь, без сети и без выкладки.
 *
 *     node --test test/entries.test.mjs
 *
 * Две половины. Первая — `_entries.js`: что считается годной записью и что
 * отбивается словами. Вторая — `money.js`, тот самый файл, который целиком
 * уезжает внутрь страницы: он читается с диска и исполняется как есть, а не
 * пересказывается здесь похожим кодом. Пересказ сходился бы сам с собой, а
 * не с тем, что она видит на экране.
 *
 * Главная проверка одна и повторяется в трёх видах: **сумма разделов равна
 * итогу**, **сумма трёх состояний оплаты равна итогу**, **итог в долларах
 * равен столбику показанных долларов**. Число, которое нельзя сверить
 * глазами со страницей, — плохое число, и ловить его должен тест, а не Ни.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import test from "node:test";

import {
  DEFAULT_STATE,
  LIMITS,
  Rejected,
  amend,
  empty,
  make,
  normalise,
  replaceEntry,
  withEntry,
  withTick,
  withoutEntry,
} from "../site/functions/api/_entries.js";

const HERE = dirname(fileURLToPath(import.meta.url));

/* Ровно тот код, что уезжает на страницу: файл читается и исполняется, а
   `JapanMoney` забирается по имени — так же, как его увидит браузер. */
const MONEY_SOURCE = readFileSync(join(HERE, "..", "site", "money.js"), "utf8");
const Money = new Function(MONEY_SOURCE + "\nreturn JapanMoney;")();

const FX = { usd_per_jpy: 158.88, as_of: "2026-08-23" };
/* Жильё — настоящие числа из trip.json: их считает питон при сборке, и
   сложение с её записями обязано их не трогать. */
const HOUSING = {
  jpy: 297_912,
  usd: 1_876,
  paid: 12_010,
  upcoming: 109_790,
  onsite: 176_112,
  count: 5,
  nights: 14,
};

const STAYS = ["lyf", "omo5", "morizuya-1", "omo3"];

function entry(over = {}) {
  return make({ kind: "todo", title: "Виза", ...over }, { stays: STAYS });
}

// ─────────────────────────────────────────── что принимается

test("место, бронь и пункт списка — три вида, и вид обязателен", () => {
  assert.equal(make({ kind: "place", title: "HIIRAGI", stay: "lyf" }, { stays: STAYS }).kind, "place");
  assert.equal(make({ kind: "booking", title: "Синкансэн" }).kind, "booking");
  assert.equal(make({ kind: "todo", title: "Виза" }).kind, "todo");
  assert.throws(() => make({ title: "Никакая" }), Rejected);
  assert.throws(() => make({ kind: "мечта", title: "Никакая" }), Rejected);
});

test("без названия запись не заводится: показать её было бы нечем", () => {
  assert.throws(() => make({ kind: "todo", title: "   " }), Rejected);
  assert.throws(() => make({ kind: "todo" }), Rejected);
});

test("у места обязан быть город, и город — из тех, что есть на странице", () => {
  assert.throws(() => make({ kind: "place", title: "Кафе" }, { stays: STAYS }), Rejected);
  assert.throws(
    () => make({ kind: "place", title: "Кафе", stay: "omo7" }, { stays: STAYS }),
    /omo7/,
    "место, повешенное на несуществующий город, тихо не покажется — значит отказ",
  );
});

test("цена необязательна, и пустая цена — не ноль", () => {
  const visa = entry({ amount: "" });
  assert.equal(visa.amount, null, "пусто должно остаться пустым");
  assert.equal(Money.hasPrice(visa), false);
  assert.equal(Money.yenOf(visa, FX), 0, "в сумму пустая цена приносит ровно ничего");
  assert.equal(entry({ amount: undefined }).amount, null);
});

test("цена разбирается так, как её набирают: с пробелами и с запятой", () => {
  assert.equal(entry({ amount: "12 000" }).amount, 12_000);
  assert.equal(entry({ amount: "12 000" }).amount, 12_000);
  assert.equal(entry({ amount: 980, currency: "usd" }).amount, 980);
  assert.equal(entry({ amount: "12,5", currency: "usd" }).amount, 12.5);
  /* Иена копеек не имеет — округляется; доллар может быть с центами. */
  assert.equal(entry({ amount: "1200,4" }).amount, 1200);
  assert.throws(() => entry({ amount: "дорого" }), Rejected);
  assert.throws(() => entry({ amount: -5 }), Rejected);
  assert.throws(() => entry({ amount: 1e12 }), Rejected);
});

test("дата — только настоящая, и только в виде ГГГГ-ММ-ДД", () => {
  assert.equal(make({ kind: "booking", title: "Поезд", when: "2027-01-09" }).when, "2027-01-09");
  assert.throws(() => make({ kind: "booking", title: "Поезд", when: "9 января" }), Rejected);
  assert.throws(() => make({ kind: "booking", title: "Поезд", when: "2027-02-31" }), /не существует/);
});

test("состояние денег по умолчанию зависит от вида, и оба файла говорят одно", () => {
  assert.equal(make({ kind: "booking", title: "Билет" }).state, "paid");
  assert.equal(make({ kind: "place", title: "Кафе", stay: "lyf" }, { stays: STAYS }).state, "onsite");
  assert.equal(make({ kind: "todo", title: "Виза" }).state, "upcoming");
  for (const kind of ["booking", "place", "todo"]) {
    assert.equal(Money.stateOf({ kind }), DEFAULT_STATE[kind],
      "money.js и _entries.js обязаны выбирать одно и то же по умолчанию");
  }
  assert.throws(() => make({ kind: "todo", title: "Виза", state: "потом" }), Rejected);
});

test("строки чистятся и обрезаются по длине, а не молча приезжают целиком", () => {
  assert.equal(entry({ title: "  Виза   в   Японию  " }).title, "Виза в Японию");
  assert.equal(entry({ title: "Виза\nв Японию" }).title, "Виза в Японию");
  assert.throws(() => entry({ title: "я".repeat(LIMITS.title + 1) }), Rejected);
  assert.throws(() => entry({ note: "я".repeat(LIMITS.note + 1) }), Rejected);
});

// ─────────────────────────────────────────── правка и хранилище

test("правка меняет только присланное и никогда — вид записи", () => {
  const was = make({ kind: "todo", title: "Билеты", amount: 500, currency: "usd" });
  const now = amend(was, { done: true, kind: "booking" });
  assert.equal(now.kind, "todo", "«правка» не должна быть способом сменить раздел денег");
  assert.equal(now.done, true);
  assert.equal(now.title, "Билеты");
  assert.equal(now.amount, 500);
});

test("цену можно стереть обратно в пустоту", () => {
  const was = entry({ amount: 12_000 });
  const now = amend(was, { amount: "" });
  assert.equal(now.amount, null);
  assert.equal("currency" in now, false, "валюта без цены — мусор, который потом соврёт");
});

test("список переживает мусор в хранилище, а не падает об него", () => {
  const state = normalise({ entries: [null, { kind: "выдумка" }, { kind: "todo", title: "Виза" }],
                            ticks: { "Дорога::Билеты": true, "плохой": "да" }, rev: 4 });
  assert.equal(state.entries.length, 1);
  assert.equal(state.ticks["Дорога::Билеты"], true);
  assert.equal(state.ticks["плохой"], false);
  assert.equal(state.rev, 4);
  assert.deepEqual(normalise(null), empty());
});

test("добавить, поправить, убрать — и rev растёт на каждой правке", () => {
  let state = empty();
  const one = entry({ title: "Виза" });
  state = withEntry(state, one);
  assert.equal(state.entries.length, 1);
  assert.equal(state.rev, 1);
  state = replaceEntry(state, one.id, amend(one, { title: "Виза в Японию" }));
  assert.equal(state.entries[0].title, "Виза в Японию");
  assert.equal(state.rev, 2);
  state = withoutEntry(state, one.id);
  assert.equal(state.entries.length, 0);
  assert.throws(() => withoutEntry(state, one.id), Rejected);
});

test("галочка хранит отличие от trip.json, а не состояние", () => {
  let state = empty();
  /* Отмеченный пункт, который в файле не отмечен, — отличие и хранится. */
  state = withTick(state, "Дорога::Билеты", true, false);
  assert.equal(state.ticks["Дорога::Билеты"], true);
  /* Снятый обратно — отличия больше нет, и ключ уходит: иначе, когда решение
     переедет в trip.json, галочка начнёт спорить сама с собой. */
  state = withTick(state, "Дорога::Билеты", false, false);
  assert.equal("Дорога::Билеты" in state.ticks, false);
  /* И наоборот: снятая с того, что в файле отмечено, — тоже отличие. */
  state = withTick(state, "Дорога::Виза", false, true);
  assert.equal(state.ticks["Дорога::Виза"], false);
});

// ─────────────────────────────────────────── чек

test("без её записей чек — это ровно жильё, ни иеной больше", () => {
  const sums = Money.tally({ fx: FX, housing: HOUSING, entries: [] });
  assert.equal(sums.jpy, HOUSING.jpy);
  assert.equal(sums.usd, HOUSING.usd);
  assert.equal(sums.states.paid, HOUSING.paid);
  assert.equal(sums.priceless, 0);
});

test("сумма разделов равна итогу, и сумма состояний оплаты — тоже", () => {
  const entries = [
    make({ kind: "booking", title: "Синкансэн", amount: 13_320, state: "paid" }),
    make({ kind: "booking", title: "Перелёт", amount: 980, currency: "usd", state: "paid" }),
    make({ kind: "place", title: "Кафе", stay: "omo5", amount: 3_000 }, { stays: STAYS }),
    make({ kind: "todo", title: "Виза", amount: 8_000, state: "upcoming" }),
    make({ kind: "todo", title: "Дьюти-фри" }),
  ];
  const sums = Money.tally({ fx: FX, housing: HOUSING, entries });

  const bySection = sums.sections.reduce((all, s) => all + s.jpy, 0);
  const byState = sums.states.paid + sums.states.upcoming + sums.states.onsite;
  assert.equal(bySection, sums.jpy, "столбик разделов обязан сойтись с итогом");
  assert.equal(byState, sums.jpy, "оплачено + предстоит + на месте обязано быть всем итогом");

  const dollars = sums.sections.reduce((all, s) => all + s.usd, 0);
  assert.equal(dollars, sums.usd, "итог в долларах — сумма показанных долларов");

  /* И то же самое числами, чтобы поломка была видна глазом, а не только
     равенством: $980 по курсу 158.88 — это ¥155 702. */
  assert.equal(sums.jpy, HOUSING.jpy + 13_320 + Math.round(980 * 158.88) + 3_000 + 8_000);
  assert.equal(sums.priceless, 1, "«дьюти-фри» без цены обязан быть назван вслух");
});

test("запись без цены не превращается в ноль и не портит итог", () => {
  const withNothing = [entry({ title: "Виза" }), entry({ title: "Багаж" })];
  const sums = Money.tally({ fx: FX, housing: HOUSING, entries: withNothing });
  assert.equal(sums.jpy, HOUSING.jpy, "две записи без цены не сдвинули итог ни на иену");
  assert.equal(sums.priceless, 2);
  assert.equal(sums.sections.find((s) => s.key === "todo").count, 2,
    "но сами записи не исчезли: их видно и их посчитали");
});

test("доллар, введённый ею, остаётся её числом", () => {
  const ticket = make({ kind: "booking", title: "Перелёт", amount: 980, currency: "usd" });
  assert.equal(Money.usdOf(ticket, FX), 980, "пересчёт туда-обратно превратил бы $980 в $979");
  assert.equal(Money.yenOf(ticket, FX), Math.round(980 * 158.88));
  const inYen = make({ kind: "booking", title: "Поезд", amount: 13_320 });
  assert.equal(Money.yenOf(inYen, FX), 13_320);
  assert.equal(Money.usdOf(inYen, FX), Math.round(13_320 / 158.88));
});

test("без курса деньги не считаются, а говорят об этом", () => {
  assert.throws(() => Money.tally({ fx: {}, housing: HOUSING, entries: [] }), /курс/);
});

test("состояние по умолчанию доезжает до чека: место платится на месте", () => {
  const place = make({ kind: "place", title: "Онсэн", stay: "morizuya-1", amount: 800 },
                     { stays: STAYS });
  const sums = Money.tally({ fx: FX, housing: HOUSING, entries: [place] });
  assert.equal(sums.states.onsite, HOUSING.onsite + 800);
  assert.equal(sums.states.paid, HOUSING.paid);
});
