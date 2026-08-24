/* Порядок дней — то, что Ни тасует руками, и единственное место, где записаны
   правила этой тасовки.

   `days.js` — рукопожатие с хранилищем: прочитать ключ, применить одну из этих
   функций, положить обратно. Всё, что решается без сети, решается здесь,
   потому что проверять это должно быть можно без выкладки
   (`test/days.test.mjs`).

   ## Кто здесь хозяин

   Текст пунктов — её, разобранный в `data/days-plan.json`, и он остаётся в
   файле. В хранилище живёт **только расстановка**: в каком дне пункт лежит и
   в каком порядке, что она дописала своей рукой, что убрала, что переписала.
   Файл при этом не хозяин порядку: пересборка не имеет права вернуть пункт
   туда, откуда она его унесла.

   Разделение это не про экономию места, а про то, чей текст побеждает. Блэйз
   поправит опечатку в названии — она увидит поправку, потому что название
   приезжает из файла по вечному id. Она передвинет пункт — файл этого не
   отменит, потому что порядок приезжает из хранилища.

   ## Четыре мешка

   * `order` — расстановка целиком: дата → список id в её порядке. Хранится
     **вся**, а не отличие от файла. Отличие пришлось бы считать в двух местах
     (здесь и в браузере), а два счёта одного и того же — это два разных
     ответа с одним именем.
   * `own` — пункты, которых в файле нет: она их завела сама.
   * `edits` — переписанное поверх файлового пункта, по id.
   * `gone` — убранное из файлового плана. Без этого мешка каждая пересборка
     воскрешала бы удалённое, и удаление было бы не удалением, а морганием.

   ## Засев

   Пусто в хранилище — расстановка берётся из файла как есть (`arrange` с
   пустым состоянием возвращает файловый порядок). Ключ появляется в KV только
   в тот миг, когда она что-то сдвинула: до этого хранить нечего, а лишняя
   запись при каждом чтении — это гонка на ровном месте.

   Новый пункт, дописанный в файл после того, как она уже тасовала, попадает в
   свой день на своё файловое место: «не упомянут ни в одном дне и не убран» —
   это и есть определение нового. */

export class Rejected extends Error {}

/* Пределы. Они не про безопасность, а про то, что значение читается целиком
   на каждый показ страницы: разросшийся ключ — это медленная страница в
   дороге, на плохой связи. */
export const LIMITS = {
  time: 40,
  title: 120,
  note: 200,
  map: 120,
  own: 200,
  perDay: 60,
};

function text(value, limit, what) {
  if (value === undefined || value === null) return "";
  if (typeof value !== "string") throw new Rejected(`${what}: ожидалась строка`);
  /* Управляющие символы выкидываются: строка в одну линию — то, что день
     умеет показать, а «\n» в названии превращается в дыру в вёрстке, которую
     никто не увидит в данных. */
  const clean = value.replace(/[\u0000-\u001f\u007f]/g, " ").replace(/\s+/g, " ").trim();
  if (clean.length > limit) throw new Rejected(`${what}: длиннее ${limit} знаков`);
  return clean;
}

export function newId() {
  /* `crypto.randomUUID` есть и в Workers, и в Node. Приставка «x» отличает её
     пункт от файлового (`d07-2`) с одного взгляда — и в данных, и в разметке. */
  return "x" + crypto.randomUUID().slice(0, 8);
}

export function empty() {
  return { order: {}, own: {}, edits: {}, gone: [], rev: 0 };
}

export function normalise(raw) {
  const state = empty();
  if (!raw || typeof raw !== "object") return state;

  if (raw.order && typeof raw.order === "object") {
    for (const [date, ids] of Object.entries(raw.order)) {
      if (!isDate(date) || !Array.isArray(ids)) continue;
      state.order[date] = ids.filter((x) => typeof x === "string" && x.length <= 40);
    }
  }
  if (raw.own && typeof raw.own === "object") {
    for (const [id, item] of Object.entries(raw.own)) {
      if (typeof id !== "string" || !item || typeof item !== "object") continue;
      state.own[id] = {
        id,
        mine: true,
        date: isDate(item.date) ? item.date : "",
        time: String(item.time || "").slice(0, LIMITS.time),
        title: String(item.title || "").slice(0, LIMITS.title),
        note: String(item.note || "").slice(0, LIMITS.note),
        map: String(item.map || "").slice(0, LIMITS.map),
      };
    }
  }
  if (raw.edits && typeof raw.edits === "object") {
    for (const [id, patch] of Object.entries(raw.edits)) {
      if (typeof id !== "string" || !patch || typeof patch !== "object") continue;
      const kept = {};
      for (const key of ["time", "title", "note", "map"]) {
        if (typeof patch[key] === "string") kept[key] = patch[key].slice(0, LIMITS.title);
      }
      if (Object.keys(kept).length) state.edits[id] = kept;
    }
  }
  if (Array.isArray(raw.gone)) {
    state.gone = raw.gone.filter((x) => typeof x === "string" && x.length <= 40);
  }
  state.rev = Number.isFinite(raw.rev) ? raw.rev : 0;
  return state;
}

function isDate(value) {
  return typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value);
}

/* Расстановка целиком: дата → список id в том порядке, в каком она их
   оставила.

   Три вещи происходят здесь и больше нигде:

   1. **её порядок побеждает файловый** — если по дате что-то записано, оно и
      берётся;
   2. **убранное не воскресает** — `gone` вычитается на каждом проходе, а не
      только в момент удаления;
   3. **дописанное в файл появляется** — пункт, не упомянутый ни в одном дне и
      не убранный, встаёт на своё файловое место.

   Мусор молча выбрасывается: id, которого нет ни в файле, ни в её мешке, —
   это след старого плана, и показать его всё равно нечем. */
export function arrange(plan, state) {
  const seedDay = new Map();      // id → дата, где он лежит в файле
  const seedAt = new Map();       // id → место в файловом дне
  for (const day of plan) {
    day.items.forEach((id, i) => {
      seedDay.set(id, day.date);
      seedAt.set(id, i);
    });
  }
  const gone = new Set(state.gone);
  const known = (id) => (seedDay.has(id) || state.own[id]) && !gone.has(id);

  const mentioned = new Set();
  for (const ids of Object.values(state.order)) for (const id of ids) mentioned.add(id);
  const arranged = Object.keys(state.order).length > 0;

  const out = {};
  for (const day of plan) {
    let ids = arranged
      ? (state.order[day.date] || []).filter(known)
      : day.items.filter(known);

    if (arranged) {
      /* Новое из файла встаёт на своё файловое место, а не в хвост: пункт,
         дописанный между завтраком и музеем, там и должен оказаться. */
      const fresh = day.items.filter((id) => !mentioned.has(id) && !gone.has(id));
      for (const id of fresh) {
        const at = Math.min(seedAt.get(id), ids.length);
        ids = ids.slice(0, at).concat([id], ids.slice(at));
      }
    }
    out[day.date] = ids;
  }

  /* Её собственный пункт, потерявший свой день (день исчез из файла, или
     запись в `order` побилась), дописывается в конец того дня, который у него
     записан. Пропажу её записи никто не заметит — а это её запись. */
  const placed = new Set();
  for (const ids of Object.values(out)) for (const id of ids) placed.add(id);
  for (const [id, item] of Object.entries(state.own)) {
    if (placed.has(id) || gone.has(id)) continue;
    const home = out[item.date] ? item.date : plan.length ? plan[0].date : null;
    if (home) out[home].push(id);
  }
  return out;
}

function bump(state, order) {
  const own = {};
  for (const ids of Object.values(order)) {
    for (const id of ids) if (state.own[id]) own[id] = state.own[id];
  }
  /* Хвосты подчищаются на каждой правке: правка поверх пункта, которого уже
     нет, — это память о вещи, которой не существует. */
  const live = new Set(Object.values(order).flat());
  const edits = {};
  for (const [id, patch] of Object.entries(state.edits)) if (live.has(id)) edits[id] = patch;
  return { ...state, order, own, edits, rev: state.rev + 1 };
}

/* Куда пункт переехал. Одна ручка на оба движения: перетаскивание внутри дня и
   бросок на заголовок свёрнутого дня — это одно и то же, отличается только
   тем, откуда взялось число `at` (у броска его нет вовсе — значит в конец). */
export function move(plan, state, id, toDate, at) {
  const order = arrange(plan, state);
  if (!Object.prototype.hasOwnProperty.call(order, toDate)) {
    throw new Rejected(`${toDate}: такого дня в поездке нет`);
  }
  let found = false;
  for (const date of Object.keys(order)) {
    const was = order[date].length;
    order[date] = order[date].filter((x) => x !== id);
    if (order[date].length !== was) found = true;
  }
  if (!found) throw new Rejected("такого пункта нет");
  if (order[toDate].length >= LIMITS.perDay) {
    throw new Rejected(`в одном дне уже ${LIMITS.perDay} пунктов — больше не влезет`);
  }

  const where = Number.isFinite(at) && at >= 0
    ? Math.min(Math.floor(at), order[toDate].length)
    : order[toDate].length;
  order[toDate].splice(where, 0, id);

  const next = bump(state, order);
  if (next.own[id]) next.own[id] = { ...next.own[id], date: toDate };
  return next;
}

/* Её собственный пункт. Времени может не быть — «зайти в книжный» это тоже
   пункт дня, и требовать от него часа значило бы требовать плана там, где
   она хочет напоминание. */
export function add(plan, state, body) {
  if (!body || typeof body !== "object") throw new Rejected("пустой запрос");
  const date = text(body.date, 10, "день");
  if (!isDate(date) || !plan.some((x) => x.date === date)) {
    throw new Rejected(`${date || "день"}: такого дня в поездке нет`);
  }
  const title = text(body.title, LIMITS.title, "что это");
  if (!title) throw new Rejected("без названия пункт не показать");
  if (Object.keys(state.own).length >= LIMITS.own) {
    throw new Rejected(`своих пунктов уже ${LIMITS.own} — больше в один день не влезет`);
  }

  const item = {
    id: newId(),
    mine: true,
    date,
    time: text(body.time, LIMITS.time, "время"),
    title,
    note: text(body.note, LIMITS.note, "подробность"),
    map: text(body.map, LIMITS.map, "как искать на карте"),
  };

  const order = arrange(plan, state);
  if (order[date].length >= LIMITS.perDay) {
    throw new Rejected(`в одном дне уже ${LIMITS.perDay} пунктов — больше не влезет`);
  }
  const at = Number.isFinite(body.at) && body.at >= 0
    ? Math.min(Math.floor(body.at), order[date].length)
    : order[date].length;
  order[date].splice(at, 0, item.id);

  return { state: bump({ ...state, own: { ...state.own, [item.id]: item } }, order), item };
}

/* Правка текста. Свой пункт правится на месте, файловый — накладкой поверх:
   id вечный, и по нему накладка находит свой пункт после любой пересборки.
   Пустое поле у файлового пункта — это «стереть моё, вернуть файловое», а не
   «поставить пустоту»: иначе поправка Блэйза не смогла бы до неё доехать. */
export function edit(plan, state, id, body) {
  if (!body || typeof body !== "object") throw new Rejected("пустой запрос");
  const order = arrange(plan, state);
  const live = new Set(Object.values(order).flat());
  if (!live.has(id)) throw new Rejected("такого пункта нет");

  if (state.own[id]) {
    const was = state.own[id];
    const item = { ...was };
    if ("time" in body) item.time = text(body.time, LIMITS.time, "время");
    if ("map" in body) item.map = text(body.map, LIMITS.map, "как искать на карте");
    if ("note" in body) item.note = text(body.note, LIMITS.note, "подробность");
    if ("title" in body) {
      const title = text(body.title, LIMITS.title, "что это");
      if (!title) throw new Rejected("без названия пункт не показать");
      item.title = title;
    }
    return bump({ ...state, own: { ...state.own, [id]: item } }, order);
  }

  const patch = { ...(state.edits[id] || {}) };
  const limits = { time: LIMITS.time, title: LIMITS.title, note: LIMITS.note, map: LIMITS.map };
  const names = { time: "время", title: "что это", note: "подробность", map: "как искать на карте" };
  for (const key of ["time", "title", "note", "map"]) {
    if (!(key in body)) continue;
    const clean = text(body[key], limits[key], names[key]);
    if (clean) patch[key] = clean;
    else delete patch[key];
  }
  const edits = { ...state.edits };
  if (Object.keys(patch).length) edits[id] = patch;
  else delete edits[id];
  return bump({ ...state, edits }, order);
}

/* Убрать. Свой пункт исчезает целиком, файловый ложится в `gone` — иначе
   пересборка вернула бы его назад, и удаление читалось бы как сбой. */
export function drop(plan, state, id) {
  const order = arrange(plan, state);
  const live = new Set(Object.values(order).flat());
  if (!live.has(id)) throw new Rejected("такого пункта нет");

  for (const date of Object.keys(order)) order[date] = order[date].filter((x) => x !== id);

  const own = { ...state.own };
  const gone = state.gone.slice();
  if (own[id]) delete own[id];
  else if (!gone.includes(id)) gone.push(id);

  const edits = { ...state.edits };
  delete edits[id];
  return bump({ ...state, own, gone, edits }, order);
}
