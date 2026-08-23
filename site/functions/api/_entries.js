/* Правила о том, что Ни вносит своими руками — и единственное место, где они
   записаны.

   `entries.js` — рукопожатие с хранилищем: прочитать ключ, применить одну из
   этих функций, положить обратно. Всё, что можно решить без сети и без KV,
   решается здесь, потому что проверять это должно быть можно без выкладки
   (`test/entries.test.mjs`).

   Три вида записей, и разница между ними не в оформлении:

   * **место** — «хочу сходить», висит на конкретном городе (на броне отеля,
     как и места из `trip.json`: Токио в поездке дважды, и матча-бар в Гиндзе
     нужен в первой половине, а не во второй);
   * **бронь** — то, что она купила отдельно: билет, поезд, экскурсия;
   * **пункт то-до** — виза, багаж между городами, дьюти-фри, регистрация.
     Цена здесь **необязательна**: «виза» бывает просто галочкой.

   Что общее у всех трёх: цена (или честная пустота) и состояние денег —
   `paid` / `upcoming` / `onsite`, те же три, что у броней отеля. Иначе итог
   пришлось бы складывать из двух разных языков.

   Ни одно поле не приезжает сюда доверенным: всё, что пришло телом запроса,
   обрезается по длине, чистится от управляющих символов и проверяется по
   списку допустимого. Не потому что за дверью чужие — а потому что запись,
   пришедшая с опечаткой, ляжет в хранилище надолго и переживёт сборку. */

export const KINDS = ["place", "booking", "todo"];
export const STATES = ["paid", "upcoming", "onsite"];
export const CURRENCIES = ["jpy", "usd"];

/* Пределы. Они не про безопасность хранилища, а про то, что значение в KV
   читается целиком на каждый показ страницы: разросшийся ключ — это медленная
   страница в дороге, на плохой связи. */
export const LIMITS = {
  title: 120,
  note: 300,
  group: 60,
  stay: 40,
  entries: 500,
  amount: 100_000_000,
};

/* Состояние по умолчанию — по виду записи. Купленный билет это уже
   потраченные деньги, место — деньги, которые достанутся кассе на месте,
   пункт списка — то, что ещё предстоит. Те же значения по умолчанию стоят в
   `money.js`; разъехаться им нельзя, и на это есть тест. */
export const DEFAULT_STATE = { booking: "paid", place: "onsite", todo: "upcoming" };

export class Rejected extends Error {}

function text(value, limit, what) {
  if (value === undefined || value === null) return "";
  if (typeof value !== "string") throw new Rejected(`${what}: ожидалась строка`);
  /* Управляющие символы (в том числе перевод строки) выкидываются: строка в
     одну линию — то, что страница умеет показать, а «\n» в заголовке
     превращается в дыру в вёрстке, которую никто не увидит в данных. */
  const clean = value.replace(/[\u0000-\u001f\u007f]/g, " ").replace(/\s+/g, " ").trim();
  if (clean.length > limit) throw new Rejected(`${what}: длиннее ${limit} знаков`);
  return clean;
}

function oneOf(value, allowed, fallback, what) {
  if (value === undefined || value === null || value === "") return fallback;
  if (typeof value !== "string" || !allowed.includes(value)) {
    throw new Rejected(`${what}: «${String(value).slice(0, 20)}» — так нельзя`);
  }
  return value;
}

/* Цена: число или честная пустота. Пустая строка, `null` и отсутствие поля —
   это «цены пока нет», и превратить их в ноль было бы враньём: ноль значит
   «бесплатно», а не «не знаю». */
function price(value, currency) {
  if (value === undefined || value === null || value === "") return null;
  const raw = typeof value === "string"
    ? value.replace(/[\s\u00a0\u202f']/g, "").replace(",", ".")
    : value;
  const amount = Number(raw);
  if (!Number.isFinite(amount)) throw new Rejected("цена: это не число");
  if (amount < 0) throw new Rejected("цена: меньше нуля не бывает");
  if (amount > LIMITS.amount) throw new Rejected("цена: слишком много, проверь порядок");
  /* Иена копеек не имеет — округляем; доллар может быть с центами, и это её
     дело, а не наше. */
  return currency === "usd" ? Math.round(amount * 100) / 100 : Math.round(amount);
}

function when(value) {
  const clean = text(value, 10, "дата");
  if (!clean) return "";
  if (!/^\d{4}-\d{2}-\d{2}$/.test(clean)) throw new Rejected("дата: нужен вид ГГГГ-ММ-ДД");
  const parsed = new Date(clean + "T00:00:00Z");
  if (Number.isNaN(parsed.getTime()) || !parsed.toISOString().startsWith(clean)) {
    throw new Rejected(`дата: ${clean} не существует`);
  }
  return clean;
}

/* Новая запись из того, что пришло телом запроса.

   `stays` — список броней из последней сборки (`_stays.js`). Место, повешенное
   на несуществующий город, на странице просто не появится: ровно та беда, от
   которой в `build.py` стоит проверка №6. Здесь она превращается в отказ с
   объяснением, а не в тихую пропажу. */
export function make(body, options = {}) {
  const stays = options.stays || [];
  const now = options.now || Date.now();
  const id = options.id || newId();

  if (!body || typeof body !== "object") throw new Rejected("пустой запрос");
  const kind = oneOf(body.kind, KINDS, null, "вид записи");
  if (!kind) throw new Rejected("вид записи не назван");

  const title = text(body.title, LIMITS.title, "название");
  if (!title) throw new Rejected("без названия запись не показать");

  const currency = oneOf(body.currency, CURRENCIES, "jpy", "валюта");
  const entry = {
    id,
    kind,
    title,
    note: text(body.note, LIMITS.note, "заметка"),
    amount: price(body.amount, currency),
    currency,
    state: oneOf(body.state, STATES, DEFAULT_STATE[kind], "состояние оплаты"),
    at: new Date(now).toISOString(),
  };
  if (entry.amount === null) delete entry.currency;

  if (kind === "place") {
    const stay = text(body.stay, LIMITS.stay, "город");
    if (!stay) throw new Rejected("у места должен быть город");
    if (stays.length && !stays.includes(stay)) {
      throw new Rejected(`города «${stay}» на странице нет`);
    }
    entry.stay = stay;
  } else {
    const at = when(body.when);
    if (at) entry.when = at;
  }

  if (kind === "todo") {
    const group = text(body.group, LIMITS.group, "раздел");
    if (group) entry.group = group;
    entry.done = body.done === true || body.done === "true";
  }

  return entry;
}

export function newId() {
  /* `crypto.randomUUID` есть и в Workers, и в Node — а самодельный счётчик
     сломался бы ровно там, где две вкладки открыты одновременно. */
  return "e" + crypto.randomUUID().slice(0, 8);
}

/* Правка. Меняются только те поля, что пришли: страница шлёт целую запись при
   правке формой и одно поле при щелчке по галочке или по чипу оплаты. Вид
   записи и её id не меняются никогда — иначе «правка» стала бы способом
   тихо превратить место в бронь и увести деньги в другой раздел. */
export function amend(current, body, options = {}) {
  if (!current) throw new Rejected("такой записи нет");
  const patch = { ...current };

  if ("title" in body) {
    const title = text(body.title, LIMITS.title, "название");
    if (!title) throw new Rejected("без названия запись не показать");
    patch.title = title;
  }
  if ("note" in body) patch.note = text(body.note, LIMITS.note, "заметка");
  if ("state" in body) patch.state = oneOf(body.state, STATES, DEFAULT_STATE[current.kind], "состояние оплаты");
  if ("done" in body && current.kind === "todo") patch.done = body.done === true || body.done === "true";
  if ("group" in body && current.kind === "todo") {
    const group = text(body.group, LIMITS.group, "раздел");
    if (group) patch.group = group; else delete patch.group;
  }
  if ("when" in body && current.kind !== "place") {
    const at = when(body.when);
    if (at) patch.when = at; else delete patch.when;
  }
  if ("stay" in body && current.kind === "place") {
    const stays = options.stays || [];
    const stay = text(body.stay, LIMITS.stay, "город");
    if (!stay) throw new Rejected("у места должен быть город");
    if (stays.length && !stays.includes(stay)) throw new Rejected(`города «${stay}» на странице нет`);
    patch.stay = stay;
  }
  if ("amount" in body || "currency" in body) {
    const currency = "currency" in body
      ? oneOf(body.currency, CURRENCIES, "jpy", "валюта")
      : (current.currency || "jpy");
    const amount = price("amount" in body ? body.amount : current.amount, currency);
    patch.amount = amount;
    if (amount === null) delete patch.currency;
    else patch.currency = currency;
  }
  return patch;
}

/* Всё состояние, которое живёт в хранилище, — один объект: её записи и
   галочки на пунктах из `trip.json`. Один ключ, одно чтение, одна запись:
   два ключа рано или поздно разъезжаются, а показываются они всегда вместе. */
export function empty() {
  return { entries: [], ticks: {}, rev: 0 };
}

export function normalise(raw) {
  const state = empty();
  if (!raw || typeof raw !== "object") return state;
  if (Array.isArray(raw.entries)) {
    state.entries = raw.entries.filter((x) => x && typeof x === "object" && KINDS.includes(x.kind));
  }
  if (raw.ticks && typeof raw.ticks === "object") {
    for (const [key, value] of Object.entries(raw.ticks)) {
      if (typeof key === "string" && key.length <= 200) state.ticks[key] = value === true;
    }
  }
  state.rev = Number.isFinite(raw.rev) ? raw.rev : 0;
  return state;
}

export function withEntry(state, entry) {
  if (state.entries.length >= LIMITS.entries) {
    throw new Rejected(`записей уже ${LIMITS.entries} — больше в одну страницу не влезет`);
  }
  return { ...state, entries: [...state.entries, entry], rev: state.rev + 1 };
}

export function replaceEntry(state, id, entry) {
  const at = state.entries.findIndex((x) => x.id === id);
  if (at < 0) throw new Rejected("такой записи нет");
  const entries = state.entries.slice();
  entries[at] = entry;
  return { ...state, entries, rev: state.rev + 1 };
}

export function withoutEntry(state, id) {
  const entries = state.entries.filter((x) => x.id !== id);
  if (entries.length === state.entries.length) throw new Rejected("такой записи нет");
  return { ...state, entries, rev: state.rev + 1 };
}

/* Галочка на пункте из `trip.json`. Хранится только **отличие** от того, что
   записано в файле: когда решение переедет в `trip.json`, галочка не начнёт
   спорить сама с собой. Ровно та же мысль была в `localStorage` — она
   переехала в хранилище, чтобы не теряться при смене телефона. */
export function withTick(state, key, on, built) {
  const name = text(key, 200, "пункт");
  if (!name) throw new Rejected("пункт не назван");
  const ticks = { ...state.ticks };
  if (on === built) delete ticks[name];
  else ticks[name] = on === true;
  return { ...state, ticks, rev: state.rev + 1 };
}
