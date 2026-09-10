/* Курс доллара к иене: правила без сети.

   Ни, 10 сентября: «конвертер сделай так, чтобы он был привязан к дате
   конвертации, сейчас там за август стоит». До этого курс замерзал в момент
   сборки — страница живёт неделями, и через месяц августовское число читалось
   как сегодняшнее.

   Здесь только разбор и проверка ответа. Сама ходьба в сеть и хранилище —
   в `fx.js`, чтобы всё, что можно проверить без интернета, проверялось без
   интернета.

   **Почему курс вообще проверяется, а не берётся как есть.** Ответ чужого
   сервиса — это не наша величина. Пустой `rates`, строка вместо числа, ноль,
   единица после смены базовой валюты — всё это выглядит как успех и молча
   превращает ¥292 805 в бессмыслицу на её экране. Число, которому мы не
   поверили, честнее числа, которое мы не посмотрели. */

/* Отказ по правилам — это разговор, а не поломка: такую причину можно
   показать словами. */
export class Rejected extends Error {}

/* Границы здравого смысла, а не точность. За последние полвека доллар стоил
   от ~75 до ~360 иен; всё, что вне этого, — не курс, а сбой на той стороне.
   Узкая вилка вокруг сегодняшнего значения была бы хуже: она сломала бы
   страницу ровно в тот день, когда курс действительно уехал. */
export const FLOOR = 50;
export const CEILING = 500;

export function plausible(rate) {
  return typeof rate === "number" && isFinite(rate) && rate > FLOOR && rate < CEILING;
}

/* Дата, к которой привязан курс, — из ответа сервиса, а не наша «сегодня».
   Между его обновлением и нашим запросом проходит время, и подписать чужое
   число своей датой значит соврать на несколько часов в её пользу. */
export function dateOf(payload, fallbackIso) {
  const stamp = payload && payload.time_last_update_utc;
  if (typeof stamp === "string") {
    const when = new Date(stamp);
    if (!isNaN(when.getTime())) return when.toISOString().slice(0, 10);
  }
  const unix = payload && payload.time_last_update_unix;
  if (typeof unix === "number" && isFinite(unix) && unix > 0) {
    return new Date(unix * 1000).toISOString().slice(0, 10);
  }
  if (typeof fallbackIso === "string" && /^\d{4}-\d{2}-\d{2}$/.test(fallbackIso)) {
    return fallbackIso;
  }
  throw new Rejected("в ответе о курсе нет даты");
}

/* Разбор ответа open.er-api.com. Сначала — сказал ли он сам, что всё хорошо:
   у него есть `result: "error"` с телом, которое иначе прочиталось бы как
   пустой успех. */
export function readRate(payload, fallbackIso) {
  if (!payload || typeof payload !== "object") {
    throw new Rejected("ответ о курсе не разобрать");
  }
  if (payload.result && payload.result !== "success") {
    throw new Rejected(`сервис курса ответил «${payload.result}»`);
  }
  const rates = payload.rates;
  if (!rates || typeof rates !== "object") throw new Rejected("в ответе нет курсов");

  const raw = rates.JPY;
  if (!plausible(raw)) throw new Rejected("курс иены не похож на курс");

  /* Два знака после запятой — столько же, сколько стоит в данных. Больше
     означало бы точность, которой у мерки нет: доллар на этой странице
     округляется до целого, и шестой знак в подписи только шумел бы. */
  return { usd_per_jpy: Math.round(raw * 100) / 100, as_of: dateOf(payload, fallbackIso) };
}

/* Свежесть считается по календарному дню UTC, а не по «прошло 24 часа».
   Сервис обновляется раз в сутки в полночь UTC; выдержка в часах означала бы,
   что полдня страница показывает вчерашнее, хотя новое уже лежит. */
export function fresh(cached, todayIso) {
  if (!cached || typeof cached !== "object") return false;
  if (!plausible(cached.usd_per_jpy)) return false;
  return typeof cached.fetched === "string" && cached.fetched === todayIso;
}

/* Человеческая дата — та же, что печатает сборка. Дублируется здесь нарочно:
   на Cloudflare питона нет, а два разных написания одной даты на одной
   странице читаются как два разных курса. */
const MONTHS = [
  "января", "февраля", "марта", "апреля", "мая", "июня",
  "июля", "августа", "сентября", "октября", "ноября", "декабря",
];

export function human(iso) {
  if (typeof iso !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(iso)) return "";
  const [y, m, d] = iso.split("-");
  return `${Number(d)} ${MONTHS[Number(m) - 1]} ${y}`;
}
