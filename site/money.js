/* Чек поездки: единственное место, где складываются деньги.

   Файл лежит отдельно и целиком, байт в байт, уезжает внутрь страницы —
   `build.py` вклеивает его в `<script>`, а `test/entries.test.mjs` читает с
   диска и гоняет ровно те же строки. Так проверяется не похожая копия, а тот
   код, который считает у неё на экране: сумма, посчитанная в тесте одним
   способом, а на странице другим — это два разных числа с одним именем.

   Правила, из которых всё остальное следует:

   * **Иена точная, доллар — мерка.** Платит Ни в иенах. Складывается всё в
     иенах, целыми; доллар получается делением и округляется до целого.
   * **Итог в долларах — сумма показанных долларов, а не пересчёт общей иены.**
     Иначе столбик на экране не сходится с числом под ним: из ¥297 912 выходит
     $1 875, а из четырёх городских чисел — $1 876. Это уже было решено для
     жилья (см. README), и её записи считаются так же.
   * **Пустая цена — не ноль.** Запись без суммы прибавляет ровно ничего и
     считается отдельно, чтобы страница могла сказать «и ещё три пункта, у
     которых цены нет», а не сделать вид, что их нет вовсе.

   Здесь нет ни одного обращения к DOM, к сети и к хранилищу: только числа
   на входе и числа на выходе. */

var JapanMoney = (function () {
  "use strict";

  /* Три состояния денег — те же, что у броней отеля: списано, спишется,
     платится на месте. Четвёртого не бывает, и запись с чужим словом в этом
     поле не должна тихо утечь в «предстоит»: см. `stateOf`. */
  var STATES = ["paid", "upcoming", "onsite"];

  function isNumber(x) {
    return typeof x === "number" && isFinite(x);
  }

  /* Сколько это в иенах. Доллар, введённый ею, — тоже деньги: билет за $980
     существует, и заставлять её пересчитывать в уме значит получить
     пересчитанное с ошибкой. */
  function yenOf(entry, fx) {
    if (!entry || !isNumber(entry.amount)) return 0;
    if (entry.currency === "usd") return Math.round(entry.amount * rate(fx));
    return Math.round(entry.amount);
  }

  /* Сколько это в долларах — то самое число, которое стоит у записи на
     экране. Для введённого в долларах это ровно то, что она набрала: пересчёт
     туда и обратно превратил бы её $980 в $979. */
  function usdOf(entry, fx) {
    if (!entry || !isNumber(entry.amount)) return 0;
    if (entry.currency === "usd") return Math.round(entry.amount);
    return Math.round(entry.amount / rate(fx));
  }

  function rate(fx) {
    var r = fx && fx.usd_per_jpy;
    if (!isNumber(r) || r <= 0) throw new Error("нет курса: считать доллары не из чего");
    return r;
  }

  function toUsd(jpy, fx) {
    return Math.round(jpy / rate(fx));
  }

  function hasPrice(entry) {
    return !!entry && isNumber(entry.amount);
  }

  /* Состояние по умолчанию зависит от вида записи, и это не косметика:
     купленный билет — уже потраченные деньги, место — деньги, которые
     достанутся кассе на месте, пункт списка — то, что ещё предстоит. */
  function stateOf(entry) {
    var given = entry && entry.state;
    if (STATES.indexOf(given) >= 0) return given;
    if (entry && entry.kind === "booking") return "paid";
    if (entry && entry.kind === "place") return "onsite";
    return "upcoming";
  }

  /* Весь чек. `housing` приезжает из сборки — это брони отелей из
     `trip.json`, посчитанные питоном при сборке страницы; трогать их отсюда
     нельзя, это её деньги и они уже показаны по городам.

     Возвращается всё, что страница потом покажет, и ничего сверх: каждое
     число здесь обязано быть видимым на экране, иначе его нельзя проверить
     глазами — а непроверяемое число хуже отсутствующего. */
  function tally(input) {
    var fx = input.fx;
    var housing = input.housing;
    /* Курс спрашивается сразу, даже когда складывать нечего: страница без
       курса обязана сказать «не могу посчитать», а не показать жильё под
       заголовком «вся поездка». Отказ, замеченный только на записи с ценой,
       — это отказ, который дождётся худшего момента. */
    rate(fx);
    var entries = (input.entries || []).filter(Boolean);

    var kinds = ["booking", "place", "todo"];
    var sections = [{
      key: "housing",
      title: "жильё",
      jpy: housing.jpy,
      usd: housing.usd,           /* сумма городских долларов, а не пересчёт */
      count: housing.count,
      priceless: 0,
    }];

    kinds.forEach(function (kind) {
      var mine = entries.filter(function (x) { return x.kind === kind; });
      sections.push({
        key: kind,
        title: { booking: "брони и билеты", place: "места", todo: "то-до" }[kind],
        jpy: mine.reduce(function (sum, x) { return sum + yenOf(x, fx); }, 0),
        usd: mine.reduce(function (sum, x) { return sum + usdOf(x, fx); }, 0),
        count: mine.length,
        priceless: mine.filter(function (x) { return !hasPrice(x); }).length,
      });
    });

    var states = { paid: housing.paid, upcoming: housing.upcoming, onsite: housing.onsite };
    entries.forEach(function (x) {
      states[stateOf(x)] += yenOf(x, fx);
    });

    var jpy = sections.reduce(function (sum, s) { return sum + s.jpy; }, 0);
    var usd = sections.reduce(function (sum, s) { return sum + s.usd; }, 0);

    return {
      sections: sections,
      states: states,
      jpy: jpy,
      usd: usd,
      /* Записей без цены. Страница называет это число вслух — «и ещё N без
         цены», — потому что итог без них верен ровно настолько, насколько
         пусты эти поля. */
      priceless: sections.reduce(function (sum, s) { return sum + s.priceless; }, 0),
      count: entries.length,
    };
  }

  return {
    STATES: STATES,
    tally: tally,
    yenOf: yenOf,
    usdOf: usdOf,
    toUsd: toUsd,
    hasPrice: hasPrice,
    stateOf: stateOf,
  };
})();

/* Node видит файл через `new Function(...)` и забирает `JapanMoney` по имени;
   браузер получает ту же переменную в глобальной области. Ни `export`, ни
   `module.exports` здесь нет нарочно: и то и другое сломало бы вклейку в
   страницу, где нет ни сборщика, ни модульной системы. */
