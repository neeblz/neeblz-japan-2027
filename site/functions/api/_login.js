/* Единственная страница, которую видно без пароля.

   Отдаётся вместо того, что попросили, по тому же адресу — чтобы ссылка,
   по которой Ни пришла, продолжила работать после ввода пароля. Стиль
   встроен нарочно: всё остальное за замком, а вход, приехавший без
   оформления, выглядит как сломанный сайт.

   Цвета — те же, что на самой странице. 24 августа они сменились там целиком
   (Ни: «фон нужен холоднее сильно, ближе к розовым голубым пастельным»), и
   дверь пришлось перекрасить следом: страница за ней холодная голубая, а
   вход, оставшийся тёплым бежевым, читался бы как чужой сайт — то есть ровно
   как поломка, от которой этот файл и написан. Меняется только `:root`;
   ничего, кроме цвета, здесь не тронуто. */

function esc(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function loginPage({ next = "/", wrong = false } = {}) {
  return `<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<meta name="theme-color" content="#e8eef7">
<title>Япония 2027</title>
<style>
  :root{ --paper:#e8eef7; --ink:#161b29; --quiet:#4e5871; --rule:rgba(22,27,41,.18);
         /* Тёмный вариант яркого, а не тот, что на самой странице: год здесь
            набран 18px обычным начертанием, то есть по WCAG это ещё «мелкий
            текст» и ему нужно 7:1. Светлый #c01048 даёт 5.3. */
         --deep:#27437f; --hot:#9c0a3a;
         --serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;
         --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
  @media (prefers-color-scheme:dark){
    :root{ --paper:#141926; --ink:#e6ecf7; --quiet:#9aa5bd;
           --rule:rgba(230,236,247,.2); --deep:#9fc0ea; --hot:#ff87ac; }
  }
  *{ box-sizing:border-box; }
  html,body{ margin:0; height:100%; }
  body{ background:var(--paper); color:var(--ink); font-family:var(--sans);
        -webkit-font-smoothing:antialiased;
        display:flex; align-items:center; justify-content:center; }
  .box{ width:320px; max-width:calc(100vw - 40px); padding:0 20px; position:relative; }
  .kanji{ position:absolute; right:0; top:-96px; font-family:var(--serif);
          font-size:104px; line-height:1; opacity:.06; user-select:none; }
  .brand{ font-family:var(--serif); font-size:38px; line-height:1.05;
          letter-spacing:-.01em; }
  .year{ display:block; font-size:18px; color:var(--hot); letter-spacing:.16em;
         margin-top:4px; }
  .sub{ font-size:12px; letter-spacing:.16em; text-transform:uppercase;
        color:var(--quiet); margin:14px 0 30px; }
  form{ display:flex; gap:10px; }
  input{ flex:1; min-width:0; height:44px; padding:0 4px; background:none;
         border:0; border-bottom:1px solid var(--rule); color:var(--ink);
         font-size:16px; font-family:inherit; border-radius:0; }
  input:focus{ outline:none; border-bottom-color:var(--deep); }
  button{ height:44px; padding:0 20px; border:0; border-radius:9px;
          background:var(--deep); color:var(--paper); font-size:15px;
          font-weight:700; font-family:inherit; cursor:pointer; }
  /* Приглушённым это стояло на 6.1:1, а 14px обычным начертанием требует 7:1.
     Заодно ошибка теперь говорит цветом ошибки, а не цветом подписи. */
  .wrong{ margin-top:16px; font-size:14px; color:var(--hot); }
</style></head>
<body><div class="box">
  <div class="kanji" aria-hidden="true">日本</div>
  <div class="brand">Япония<span class="year">2027</span></div>
  <div class="sub">5 — 19 января</div>
  <form method="post" action="/login">
    <input type="hidden" name="next" value="${esc(next)}">
    <input type="password" name="password" autofocus required
           placeholder="Пароль" aria-label="Пароль" autocomplete="current-password">
    <button type="submit">Войти</button>
  </form>
  ${wrong ? '<div class="wrong">Пароль не подошёл.</div>' : ""}
</div></body></html>`;
}
