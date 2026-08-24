/* Вторая ручка, которой Ни правит свою страницу: порядок дней.

   `/api/days` — прочитать расстановку, передвинуть пункт, дописать свой,
   переписать текст, убрать. Правила о том, что считается годной расстановкой,
   живут в `_days.js` и проверяются без сети; здесь остаётся только разговор с
   хранилищем.

   **Дверь эту ручку закрывает сама** — `_middleware.js` стоит перед каждым
   запросом (`_routes.json`: `include: ["/*"]`). Отдельного пароля тут нет по
   той же причине, что и у записей: второй замок на той же двери означает
   второе место, где его можно забыть запереть.

   **Отдельный ключ, а не общий с записями.** Записи и расстановка меняются
   разными руками в разное время: она вписывает место в карточку города и
   отдельно тасует день. Один ключ на двоих означал бы, что перетаскивание
   пункта переписывает и её записи целиком — то есть ставит под удар вещи,
   которых оно не касалось. Цена разделения — два чтения вместо одного, и она
   меньше.

   **План приезжает сборкой** (`_plan.js`), а не читается из `trip.json`:
   рядом с ручкой на Cloudflare нет ни файла с данными, ни питона. План здесь
   нужен ровно для двух вещей — знать список дней (в несуществующий день пункт
   не переносится) и знать файловый порядок, чтобы дописанное в файл встало на
   своё место. */

import { Rejected, add, arrange, drop, edit, move, normalise } from "./_days.js";
import { PLAN } from "./_plan.js";

/* Версия в имени ключа: старая расстановка переживёт смену формы, а не будет
   молча прочитана новым кодом как что-то другое. */
const KEY = "japan.days.v1";

function json(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "private, no-store",
    },
  });
}

async function body(request) {
  const kind = (request.headers.get("content-type") || "").split(";")[0].trim();
  if (kind !== "application/json") return null;
  try {
    const parsed = await request.json();
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch {
    return null;
  }
}

async function read(kv) {
  return normalise(await kv.get(KEY, "json"));
}

/* Ответ на любую удавшуюся правку — вся расстановка целиком, а не «ок».

   Причина та же, что у записей: KV догоняет себя не мгновенно, и страница,
   которая после записи пошла бы перечитывать порядок, имеет шанс получить
   вчерашний. Отдавая то, что только что положили, мы показываем ей ровно то,
   что она сделала.

   `order` здесь уже разложенный — тот самый, что лёг в хранилище. Считать его
   второй раз в браузере нельзя: два способа разложить одно и то же дадут два
   разных порядка с одним именем. */
function whole(state, extra) {
  return json({
    ok: true,
    order: arrange(PLAN, state),
    own: state.own,
    edits: state.edits,
    gone: state.gone,
    rev: state.rev,
    ...(extra || {}),
  });
}

async function save(kv, state) {
  /* В хранилище ложится уже разложенный порядок: он и есть то, что она видит.
     Хранить «отличие от файла» пришлось бы считать в двух местах. */
  const laid = { ...state, order: arrange(PLAN, state) };
  await kv.put(KEY, JSON.stringify(laid));
  return laid;
}

export async function onRequest(context) {
  const kv = context.env.JAPAN_KV;
  /* Привязка узнаётся по форме, а не по имени: имя у неё уже есть, а вот
     объект с `get` — это то, чем она обязана быть на самом деле. */
  if (!kv || typeof kv.get !== "function" || typeof kv.put !== "function") {
    return json({
      ok: false,
      why: "хранилище не настроено — порядок дней некуда положить, скажи Блэйзу",
    }, 503);
  }

  const request = context.request;
  const method = request.method.toUpperCase();

  try {
    /* Пусто в хранилище — отвечаем файловым порядком и ничего не пишем.
       Засев здесь и есть: показать план как он лежит в файле. Ключ появится
       в тот миг, когда она первый раз что-то сдвинет. */
    if (method === "GET") return whole(await read(kv));

    const sent = await body(request);
    if (!sent) return json({ ok: false, why: "жду JSON в теле запроса" }, 400);

    if (method === "POST") {
      const made = add(PLAN, await read(kv), sent);
      return whole(await save(kv, made.state), { added: made.item.id });
    }

    if (method === "PATCH") {
      const state = await read(kv);
      const id = typeof sent.id === "string" ? sent.id : "";
      if (!id) return json({ ok: false, why: "пункт не назван" }, 400);

      /* Переезд пункта и правка текста — разные глаголы на одной ручке:
         `to` называет день, всё остальное — поля. Смешать их в одном запросе
         нельзя нарочно, иначе «перенести» тихо переписывало бы название. */
      if (typeof sent.to === "string") {
        const at = Number.isFinite(sent.at) ? sent.at : null;
        return whole(await save(kv, move(PLAN, state, id, sent.to, at)));
      }
      return whole(await save(kv, edit(PLAN, state, id, sent)));
    }

    if (method === "DELETE") {
      const state = await read(kv);
      const id = typeof sent.id === "string" ? sent.id : "";
      return whole(await save(kv, drop(PLAN, state, id)));
    }

    return json({ ok: false, why: `${method} этой ручке не подходит` }, 405);
  } catch (error) {
    /* Отказ по правилам — это разговор с ней («такого дня в поездке нет»), и
       он обязан доехать до экрана словами. Всё остальное — поломка на нашей
       стороне, и её нельзя выдавать за её ошибку. */
    if (error instanceof Rejected) return json({ ok: false, why: error.message }, 422);
    return json({ ok: false, why: "не сохранилось — скажи Блэйзу" }, 500);
  }
}
