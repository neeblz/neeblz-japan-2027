/* Что дверь делает с запросом — решается здесь, чтобы это можно было
   проверить без выкладки.

   `_middleware.js` — две строки, которые передают этот вердикт Cloudflare;
   все правила о том, кого пускать, живут в этом файле, и каждое из них
   прогоняется `test/door.test.mjs` без деплоя.

   Дверь закрывается при отказе. С незаданным JAPAN_PASSWORD ответ на всё —
   503. Отказ, который мы можем себе позволить, — «Ни не может войти и пишет
   Блэйзу»; тот, который не можем, — «её брони и деньги уехали в открытый
   доступ». */

import {
  COOKIE,
  LOGIN_PATH,
  cookieValid,
  issueCookie,
  passwordMatches,
  readCookie,
  safeNext,
} from "./_gate.js";
import { loginPage } from "./_login.js";

const PRIVATE = {
  "x-robots-tag": "noindex, nofollow, noarchive",
  "cache-control": "private, no-store",
  "referrer-policy": "no-referrer",
  "x-content-type-options": "nosniff",
};

/* POST на адрес входа, который не форма, — это не попытка войти, и на него
   надо ответить, а не упасть: `request.formData()` бросает на JSON-теле, а
   непойманный бросок на краю — это 500 на единственном адресе, который обязан
   отвечать даже когда всё остальное закрыто. Пустая форма проваливается в
   «пароль не подошёл», чем она и является. */
async function fields(request) {
  try {
    return await request.formData();
  } catch {
    return new FormData();
  }
}

function html(body, status) {
  return {
    pass: false,
    response: new Response(body, {
      status,
      headers: { ...PRIVATE, "content-type": "text/html; charset=utf-8" },
    }),
  };
}

export async function answer(request, env = {}, now = Date.now()) {
  const url = new URL(request.url);
  const password = env.JAPAN_PASSWORD || "";

  if (!password) {
    return {
      pass: false,
      response: new Response("Япония 2027: пароль не настроен, страница закрыта.", {
        status: 503,
        headers: { ...PRIVATE, "content-type": "text/plain; charset=utf-8" },
      }),
    };
  }

  const allowed = await cookieValid(
    readCookie(request.headers.get("cookie"), COOKIE),
    password,
    now
  );

  if (url.pathname === LOGIN_PATH) {
    if (request.method !== "POST") {
      if (allowed) {
        return {
          pass: false,
          response: new Response(null, {
            status: 303,
            headers: { ...PRIVATE, location: "/" },
          }),
        };
      }
      return html(loginPage({ next: safeNext(url.searchParams.get("next")) }), 200);
    }
    const form = await fields(request);
    const back = safeNext(form.get("next"));
    if (await passwordMatches(String(form.get("password") || ""), password)) {
      const headers = new Headers({ ...PRIVATE, location: back });
      headers.append("set-cookie", await issueCookie(password, now));
      return { pass: false, response: new Response(null, { status: 303, headers }) };
    }
    /* Ни намёка на то, какая половина была неверна, и ни грамма разницы во
       времени для почти угаданного — `passwordMatches` сравнивает ровно. */
    return html(loginPage({ next: back, wrong: true }), 401);
  }

  if (allowed) return { pass: true, headers: PRIVATE };

  /* Её адрес сохраняется, чтобы ссылка, по которой она пришла, довела туда,
     куда вела. */
  return html(loginPage({ next: url.pathname + url.search }), 401);
}
