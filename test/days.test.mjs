/* Правила расстановки дней — без сети, без KV, без страницы.
 *
 *     node --test test/days.test.mjs
 *
 * Проверяется здесь одна вещь, ради которой всё и затевалось: **её порядок
 * переживает пересборку**. Настоящий круг с настоящим рантайком и настоящей
 * KV стоит в `test/round.sh`; тут — то же самое утверждение, разобранное на
 * случаи, которых в круге не воспроизвести: файл поправили, пункт дописали,
 * пункт убрали, id съехал.
 *
 * Половина файла — нарочно сломанные запросы. Причина та же, что и у
 * `test_data.py`: проверка, которая ни разу не падала, и отсутствие проверки
 * выглядят снаружи одинаково.
 */

import test from "node:test";
import assert from "node:assert/strict";

import {
  LIMITS,
  Rejected,
  add,
  arrange,
  drop,
  edit,
  empty,
  move,
  normalise,
} from "../site/functions/api/_days.js";

/* Маленький план вместо настоящего: шестнадцать дней тут ничего не докажут
   сверх трёх, а читать сломавшийся случай в трёх днях можно глазами. */
const PLAN = [
  { date: "2027-01-05", items: ["a1", "a2", "a3"] },
  { date: "2027-01-06", items: ["b1", "b2"] },
  { date: "2027-01-07", items: ["c1"] },
];

const ids = (order) => JSON.stringify(order);

test("пусто в хранилище — порядок берётся из файла", () => {
  const order = arrange(PLAN, empty());
  assert.deepEqual(order["2027-01-05"], ["a1", "a2", "a3"]);
  assert.deepEqual(order["2027-01-06"], ["b1", "b2"]);
  assert.deepEqual(order["2027-01-07"], ["c1"]);
});

test("перестановка внутри дня переживает пересборку файла", () => {
  const moved = move(PLAN, empty(), "a3", "2027-01-05", 0);
  assert.deepEqual(arrange(PLAN, moved)["2027-01-05"], ["a3", "a1", "a2"]);

  /* Пересборка — это тот же файл, прочитанный заново. Ей нечего сказать
     против уже сделанной перестановки. */
  const again = arrange(PLAN, normalise(JSON.parse(JSON.stringify(moved))));
  assert.deepEqual(again["2027-01-05"], ["a3", "a1", "a2"]);
});

test("перенос в другой день уносит пункт целиком", () => {
  const moved = move(PLAN, empty(), "a1", "2027-01-07", 0);
  const order = arrange(PLAN, moved);
  assert.deepEqual(order["2027-01-05"], ["a2", "a3"]);
  assert.deepEqual(order["2027-01-07"], ["a1", "c1"]);
});

test("перенос без места кладёт в конец дня", () => {
  const moved = move(PLAN, empty(), "a1", "2027-01-06", null);
  assert.deepEqual(arrange(PLAN, moved)["2027-01-06"], ["b1", "b2", "a1"]);
});

test("в несуществующий день не переносится", () => {
  assert.throws(() => move(PLAN, empty(), "a1", "2027-02-30", 0), Rejected);
  assert.throws(() => move(PLAN, empty(), "нет-такого", "2027-01-06", 0), Rejected);
});

test("дописанный в файл пункт встаёт на своё файловое место", () => {
  const moved = move(PLAN, empty(), "a3", "2027-01-05", 0);   // она уже тасовала
  const grown = [
    { date: "2027-01-05", items: ["a1", "a1b", "a2", "a3"] },  // Блэйз дописал a1b
    { date: "2027-01-06", items: ["b1", "b2"] },
    { date: "2027-01-07", items: ["c1"] },
  ];
  const order = arrange(grown, moved);
  assert.deepEqual(order["2027-01-05"], ["a3", "a1b", "a1", "a2"],
    "новый пункт встал на своё файловое место, а её перестановка цела");
});

test("убранный пункт не воскресает пересборкой", () => {
  const gone = drop(PLAN, empty(), "a2");
  assert.deepEqual(arrange(PLAN, gone)["2027-01-05"], ["a1", "a3"]);
  const again = arrange(PLAN, normalise(JSON.parse(JSON.stringify(gone))));
  assert.deepEqual(again["2027-01-05"], ["a1", "a3"], "и после пересборки тоже");
});

test("убрать можно только то, что есть", () => {
  const gone = drop(PLAN, empty(), "a2");
  assert.throws(() => drop(PLAN, gone, "a2"), Rejected);
  assert.throws(() => drop(PLAN, empty(), "нет-такого"), Rejected);
});

test("свой пункт живёт в хранилище целиком и там, куда положен", () => {
  const made = add(PLAN, empty(), {
    date: "2027-01-06",
    title: "Кофейня у реки",
    time: "утро",
    map: "Blue Bottle Kyoto",
    at: 0,
  });
  assert.match(made.item.id, /^x/);
  assert.deepEqual(arrange(PLAN, made.state)["2027-01-06"], [made.item.id, "b1", "b2"]);
  assert.equal(made.state.own[made.item.id].title, "Кофейня у реки");
  assert.equal(made.state.own[made.item.id].map, "Blue Bottle Kyoto");

  /* Свой пункт тоже тасуется — и остаётся своим после переезда. */
  const moved = move(PLAN, made.state, made.item.id, "2027-01-07", 0);
  assert.deepEqual(arrange(PLAN, moved)["2027-01-07"], [made.item.id, "c1"]);
  assert.equal(moved.own[made.item.id].date, "2027-01-07");
});

test("свой пункт без названия и в несуществующий день не заводится", () => {
  assert.throws(() => add(PLAN, empty(), { date: "2027-01-06", title: "   " }), Rejected);
  assert.throws(() => add(PLAN, empty(), { date: "2027-03-01", title: "Кофе" }), Rejected);
  assert.throws(
    () => add(PLAN, empty(), { date: "2027-01-06", title: "х".repeat(LIMITS.title + 1) }),
    Rejected,
  );
});

test("свой пункт убирается насовсем, а файловый — только из показа", () => {
  const made = add(PLAN, empty(), { date: "2027-01-06", title: "Кофейня" });
  const gone = drop(PLAN, made.state, made.item.id);
  assert.equal(gone.own[made.item.id], undefined, "своё удаляется целиком");
  assert.equal(gone.gone.includes(made.item.id), false, "и не копится в списке убранного");

  const dropped = drop(PLAN, empty(), "b1");
  assert.deepEqual(dropped.gone, ["b1"], "файловый помнится убранным — иначе вернётся");
});

test("правка файлового пункта ложится накладкой по вечному id", () => {
  const patched = edit(PLAN, empty(), "b2", { title: "Ужин пораньше", time: "18:00" });
  assert.deepEqual(patched.edits.b2, { title: "Ужин пораньше", time: "18:00" });

  /* Правка держится за id, а не за место: пункт переехал — правка с ним. */
  const moved = move(PLAN, patched, "b2", "2027-01-05", 0);
  assert.deepEqual(moved.edits.b2, { title: "Ужин пораньше", time: "18:00" });
});

test("пустое поле снимает её правку, а не ставит пустоту", () => {
  const patched = edit(PLAN, empty(), "b2", { time: "18:00" });
  const cleared = edit(PLAN, patched, "b2", { time: "" });
  assert.equal(cleared.edits.b2, undefined,
    "снятая правка исчезает — иначе поправка в файле до неё не доедет");
});

test("правка своего пункта меняет сам пункт", () => {
  const made = add(PLAN, empty(), { date: "2027-01-06", title: "Кофейня" });
  const patched = edit(PLAN, made.state, made.item.id, { title: "Кофейня у реки", note: "с террасой" });
  assert.equal(patched.own[made.item.id].title, "Кофейня у реки");
  assert.equal(patched.own[made.item.id].note, "с террасой");
  assert.equal(patched.edits[made.item.id], undefined, "своё правится на месте, а не накладкой");
});

test("свой пункт без названия не остаётся, а файловый возвращает своё", () => {
  const made = add(PLAN, empty(), { date: "2027-01-06", title: "Кофейня" });
  assert.throws(() => edit(PLAN, made.state, made.item.id, { title: "  " }), Rejected,
    "у её собственного пункта названия взять неоткуда");

  /* А у файлового есть: пустое поле там значит «верни как в файле». Отказать
     здесь значило бы запереть её правку навсегда — снять её было бы нечем. */
  const patched = edit(PLAN, empty(), "b2", { title: "Ужин пораньше" });
  const back = edit(PLAN, patched, "b2", { title: "  " });
  assert.equal(back.edits.b2, undefined);

  assert.throws(() => edit(PLAN, empty(), "нет-такого", { title: "Что-то" }), Rejected);
});

test("правка поверх убранного пункта не копится", () => {
  const patched = edit(PLAN, empty(), "b2", { title: "Ужин пораньше" });
  const gone = drop(PLAN, patched, "b2");
  assert.equal(gone.edits.b2, undefined, "память о вещи, которой нет, — это мусор");
});

test("пункт, исчезнувший из файла, тихо уходит со страницы", () => {
  const moved = move(PLAN, empty(), "a3", "2027-01-05", 0);
  const shrunk = [
    { date: "2027-01-05", items: ["a1", "a2"] },   // a3 убрали из файла
    { date: "2027-01-06", items: ["b1", "b2"] },
    { date: "2027-01-07", items: ["c1"] },
  ];
  assert.deepEqual(arrange(shrunk, moved)["2027-01-05"], ["a1", "a2"]);
});

test("свой пункт не теряется, даже если запись о порядке побилась", () => {
  const made = add(PLAN, empty(), { date: "2027-01-06", title: "Кофейня" });
  const broken = normalise({ ...made.state, order: { "2027-01-05": ["a1"] } });
  const order = arrange(PLAN, broken);
  assert.ok(order["2027-01-06"].includes(made.item.id),
    "её запись дописывается в свой день, а не пропадает молча");
});

test("мусор из хранилища не доезжает до страницы", () => {
  const state = normalise({
    order: { "2027-01-05": ["a1", 7, "чужое"], "не-дата": ["a2"] },
    own: { x1: "строка вместо пункта" },
    edits: { b1: { title: "Ужин", лишнее: 1 } },
    gone: ["a3", 12],
    rev: "много",
  });
  assert.deepEqual(state.order["2027-01-05"], ["a1", "чужое"]);
  assert.equal(state.order["не-дата"], undefined);
  assert.deepEqual(state.own, {});
  assert.deepEqual(state.edits.b1, { title: "Ужин" });
  assert.deepEqual(state.gone, ["a3"]);
  assert.equal(state.rev, 0);

  const order = arrange(PLAN, state);
  /* «Чужое» показать нечем — его выбрасывают. А вот `a2`, о котором в
     побившейся записи не сказано ничего, возвращается на своё файловое место:
     «не упомянут и не убран» — это определение нового пункта, и оно же
     страхует от потери. Спрятать его молча было бы дороже. */
  assert.deepEqual(order["2027-01-05"], ["a1", "a2"]);
});

test("день не растёт бесконечно", () => {
  let state = empty();
  const room = LIMITS.perDay - PLAN[2].items.length;
  for (let i = 0; i < room; i++) {
    state = add(PLAN, state, { date: "2027-01-07", title: "пункт " + i }).state;
  }
  assert.equal(arrange(PLAN, state)["2027-01-07"].length, LIMITS.perDay);
  assert.throws(() => add(PLAN, state, { date: "2027-01-07", title: "ещё один" }), Rejected);
  assert.throws(() => move(PLAN, state, "a1", "2027-01-07", 0), Rejected);
});

test("управляющие символы в названии не доезжают до вёрстки", () => {
  const made = add(PLAN, empty(), {
    date: "2027-01-06",
    title: "Кофейня\nу\tреки",
  });
  assert.equal(made.item.title, "Кофейня у реки");
});

test("каждая правка двигает счётчик — по нему видно, что состояние новое", () => {
  const one = move(PLAN, empty(), "a1", "2027-01-06", 0);
  const two = drop(PLAN, one, "b1");
  assert.equal(one.rev, 1);
  assert.equal(two.rev, 2);
});

test("расстановка не зависит от того, сколько раз её разложили", () => {
  const moved = move(PLAN, empty(), "a1", "2027-01-07", 0);
  const once = arrange(PLAN, moved);
  const twice = arrange(PLAN, normalise({ ...moved, order: once }));
  assert.equal(ids(once), ids(twice));
});
