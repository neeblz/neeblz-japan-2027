/* Единственная ручка, которой Ни пишет на своей странице.

   `/api/entries` — прочитать всё, добавить, поправить, удалить. Все правила
   о том, что считается годной записью, живут в `_entries.js` и проверяются
   без сети; здесь остаётся только разговор с хранилищем.

   **Дверь эту ручку закрывает сама.** `_middleware.js` стоит перед *каждым*
   запросом (`_routes.json`: `include: ["/*"]`), поэтому без печенья сюда не
   попадает никто — ни браузер, ни curl. Отдельного пароля у ручки нет
   нарочно: второй замок на той же двери означает второе место, где его можно
   забыть запереть.

   **Одно значение под одним ключом.** Её записи и галочки — один объект в KV;
   каждая правка читает его целиком и кладёт целиком обратно. Для страницы,
   которую открывает один человек с одного телефона, это самый простой способ
   не получить полсостояния: две вкладки, правящие одновременно, потеряют
   правку той, что нажала раньше, — и это единственная цена, которую здесь
   платят. Она названа в README, а не спрятана.

   **Хранилища может не быть** — привязку `JAPAN_KV` ставит Блэйз в панели
   Cloudflare, и до этого момента страница обязана честно сказать «не
   сохранилось», а не проглотить набранное. Отказ 503 с этими словами и есть
   это «честно». */

import {
  Rejected,
  amend,
  make,
  normalise,
  replaceEntry,
  withEntry,
  withTick,
  withoutEntry,
} from "./_entries.js";
import { STAYS } from "./_stays.js";

/* Версия в имени ключа: старое значение переживёт смену формы записи, а не
   будет молча прочитано новым кодом как что-то другое. */
const KEY = "japan.v1";

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

async function save(kv, state) {
  await kv.put(KEY, JSON.stringify(state));
  return state;
}

/* Ответ на любую удавшуюся правку — всё состояние целиком, а не «ок».

   Причина не в удобстве: KV догоняет сама себя не мгновенно, и страница,
   которая после записи пошла бы перечитывать список, имеет шанс получить
   вчерашний. Отдавая то, что только что положили, мы показываем ей ровно то,
   что она сделала. */
function whole(state) {
  return json({ ok: true, entries: state.entries, ticks: state.ticks, rev: state.rev });
}

export async function onRequest(context) {
  const kv = context.env.JAPAN_KV;
  /* Привязка узнаётся по форме, а не по имени: имя у неё уже есть, а вот
     объект с `get` — это то, чем она обязана быть на самом деле. */
  if (!kv || typeof kv.get !== "function" || typeof kv.put !== "function") {
    return json({
      ok: false,
      why: "хранилище не настроено — записи некуда положить, скажи Блэйзу",
    }, 503);
  }

  const request = context.request;
  const method = request.method.toUpperCase();

  try {
    if (method === "GET") return whole(await read(kv));

    const sent = await body(request);
    if (!sent) return json({ ok: false, why: "жду JSON в теле запроса" }, 400);

    if (method === "POST") {
      const state = await read(kv);
      const entry = make(sent, { stays: STAYS });
      return whole(await save(kv, withEntry(state, entry)));
    }

    if (method === "PATCH") {
      const state = await read(kv);

      /* Галочка на пункте из `trip.json` — не запись, а отличие от файла.
         `built` говорит, что стоит в файле: одинаковое с файлом отличие
         стирается, а не копится. */
      if (typeof sent.tick === "string") {
        const on = sent.done === true || sent.done === "true";
        const built = sent.built === true || sent.built === "true";
        return whole(await save(kv, withTick(state, sent.tick, on, built)));
      }

      const id = typeof sent.id === "string" ? sent.id : "";
      const current = state.entries.find((x) => x.id === id);
      if (!current) return json({ ok: false, why: "такой записи нет" }, 404);
      const patched = amend(current, sent, { stays: STAYS });
      return whole(await save(kv, replaceEntry(state, id, patched)));
    }

    if (method === "DELETE") {
      const state = await read(kv);
      const id = typeof sent.id === "string" ? sent.id : "";
      return whole(await save(kv, withoutEntry(state, id)));
    }

    return json({ ok: false, why: `${method} этой ручке не подходит` }, 405);
  } catch (error) {
    /* Отказ по правилам — это разговор с ней («без названия запись не
       показать»), и он обязан доехать до экрана словами. Всё остальное —
       поломка на нашей стороне, и её нельзя выдавать за её ошибку. */
    if (error instanceof Rejected) return json({ ok: false, why: error.message }, 422);
    return json({ ok: false, why: "не сохранилось — скажи Блэйзу" }, 500);
  }
}
