/* Третья ручка: курс на сегодня.

   `/api/fx` — отдать курс доллара к иене, привязанный к дате, а не к моменту
   сборки. Правила разбора живут в `_fx.js` и проверяются без сети; здесь —
   разговор с чужим сервисом и с хранилищем.

   **Дверь закрывает и эту ручку тоже** — `_middleware.js` стоит перед каждым
   запросом. Отдельного пароля нет по той же причине, что у записей и дней.

   **Ходим наружу не чаще раза в сутки.** Курс обновляется раз в день, а
   страница открывается сколько угодно раз; кэш в KV — не про экономию, а про
   то, чтобы её открытие страницы не зависело от того, отвечает ли сейчас
   чужой сервер.

   **Отказ здесь не ломает страницу.** Если сеть молчит или ответ не похож на
   курс, ручка так и говорит, а страница остаётся на том курсе, который
   впечатан сборкой, — со своей честной датой. Показать вчерашнее число с
   вчерашней подписью можно; показать вчерашнее число с сегодняшней — нет. */

import { Rejected, fresh, human, plausible, readRate } from "./_fx.js";

const KEY = "japan.fx.v1";
const SOURCE = "https://open.er-api.com/v6/latest/USD";

/* Ответ живёт минуту в кэше края: страница спрашивает курс один раз за
   открытие, но открытий подряд бывает несколько (она листает и возвращается). */
function json(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "private, max-age=60",
    },
  });
}

function said(rate) {
  return json({
    ok: true,
    fx: {
      usd_per_jpy: rate.usd_per_jpy,
      as_of: rate.as_of,
      human: human(rate.as_of),
    },
  });
}

function today() {
  return new Date().toISOString().slice(0, 10);
}

async function ask(now) {
  const answer = await fetch(SOURCE, {
    headers: { accept: "application/json" },
    /* Чужой сервис не повод держать её страницу: ответ либо есть быстро,
       либо мы обходимся впечатанным курсом. */
    cf: { cacheTtl: 300, cacheEverything: true },
  });
  if (!answer.ok) throw new Rejected(`сервис курса ответил ${answer.status}`);
  return readRate(await answer.json(), now);
}

export async function onRequest(context) {
  const request = context.request;
  if (request.method.toUpperCase() !== "GET") {
    return json({ ok: false, why: "у этой ручки есть только GET" }, 405);
  }

  const kv = context.env.JAPAN_KV;
  const usable = kv && typeof kv.get === "function" && typeof kv.put === "function";
  const now = today();

  /* Лежит сегодняшний — отдаём его и наружу не ходим. */
  if (usable) {
    let cached = null;
    try {
      cached = await kv.get(KEY, "json");
    } catch {
      cached = null;
    }
    if (fresh(cached, now)) return said(cached);
  }

  let rate;
  try {
    rate = await ask(now);
  } catch (error) {
    /* Курс не приехал. Отдаём отказ словами и — если есть — вчерашнее число
       **с его собственной датой**: страница сама решит, показывать ли его.
       Даже протухший кэш здесь честнее выдумки, потому что он подписан. */
    let stale = null;
    if (usable) {
      try {
        const kept = await kv.get(KEY, "json");
        if (kept && plausible(kept.usd_per_jpy)) stale = kept;
      } catch {
        stale = null;
      }
    }
    const why = error instanceof Rejected
      ? error.message
      : "курс не спросить — сеть молчит";
    return json({
      ok: false,
      why,
      ...(stale ? { fx: { usd_per_jpy: stale.usd_per_jpy, as_of: stale.as_of, human: human(stale.as_of) } } : {}),
    }, 503);
  }

  if (usable) {
    /* `fetched` — когда мы спросили, `as_of` — к какому дню относится сам
       курс. Это разные даты, и путать их нельзя: свежесть кэша считается по
       первой, а подпись под числом печатается по второй. */
    try {
      await kv.put(KEY, JSON.stringify({ ...rate, fetched: now }));
    } catch {
      /* Не легло в хранилище — не повод не отдать ей курс. */
    }
  }
  return said(rate);
}
