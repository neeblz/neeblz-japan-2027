/* Япония 2027 — тот же замок, другой хозяин. Cloudflare Pages Functions.

   Pages запускает это впереди каждого запроса. Все правила о том, кого
   пускать, живут в `api/_door.js`; здесь только рукопожатие.

   Три отличия от такого же файла на Vercel, все они в этом файле:

   * запрос и окружение приезжают на `context`, а не в `process.env`;
   * «пропустить» — это `context.next()`, который забирает статический файл;
   * заголовки вердикта ставятся на ответ здесь, потому что `next({ headers })`
     на Pages нет, а `_headers` до ответа функции не доходит вовсе.

   Чего здесь нарочно нет, в отличие от курса лекций: обхода кириллических
   адресов папок. Все адреса этой страницы — `/`, `/login`, `/404.html` — ASCII,
   а ветка, которая не может выполниться, это ветка, которую никто не чинит. */

import { answer } from "./api/_door.js";

export async function onRequest(context) {
  const verdict = await answer(context.request, context.env);
  if (!verdict.pass) return verdict.response;

  const asset = await context.next();
  /* Заголовки у ответа Pages неизменяемые; у его копии — нет. */
  const served = new Response(asset.body, asset);
  for (const [name, value] of Object.entries(verdict.headers || {})) {
    served.headers.set(name, value);
  }
  return served;
}
