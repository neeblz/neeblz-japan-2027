/* Единственная страница, которую видно без пароля.

   Отдаётся вместо того, что попросили, по тому же адресу — чтобы ссылка,
   по которой Ни пришла, продолжила работать после ввода пароля. Стиль
   встроен нарочно: всё остальное за замком, а вход, приехавший без
   оформления, выглядит как сломанный сайт.

   Цвета — те же три, что на самой странице: васи, тушь и киноварь. */

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
<meta name="theme-color" content="#f7f3ec">
<title>Япония 2027</title>
<style>
  :root{ --paper:#f7f3ec; --ink:#1e2329; --quiet:#5d6570; --rule:rgba(30,35,41,.16);
         --deep:#2f4a5c; --gold:#a8834b;
         --serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;
         --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
  @media (prefers-color-scheme:dark){
    :root{ --paper:#14181c; --ink:#e8e4dc; --quiet:#9aa3ad;
           --rule:rgba(232,228,220,.2); --deep:#8fb6cc; --gold:#c9a874; }
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
  .year{ display:block; font-size:18px; color:var(--gold); letter-spacing:.16em;
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
  .wrong{ margin-top:16px; font-size:14px; color:var(--quiet); }
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
