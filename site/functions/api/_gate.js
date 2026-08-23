/* Замок на входе — и единственное место, которое знает, как он устроен.

   Пароль здесь не живёт: он приезжает как JAPAN_PASSWORD, и ставит его на
   хост Блэйз. В файле только две операции — «это тот пароль?» и «эту печенье
   выдавали мы?» — обе за постоянное время, потому что ответ по скорости это
   тоже ответ.

   Печенье не несёт секрета: это `1.<срок>.<подпись>`, подписанная паролем.
   Смена пароля обесценивает все выданные печенья разом — это желаемое
   поведение, а не побочный эффект.

   Портировано с курса лекций (`lectures-site/functions/api/_gate.js`), который
   стоит перед живым сайтом с 9 августа 2026. Форма нарочно та же: если замок
   где-то неверен, чинить его в одном месте, а не искать разошедшиеся копии. */

export const COOKIE = "jp";
export const LOGIN_PATH = "/login";

/* Ни смотрит эту страницу со своего телефона, в том числе в дороге и в чужой
   сети, где переспрашивать пароль — худшее, что можно сделать. Печенье
   HttpOnly и Secure; красть в нём всё равно нечего. */
const LIFETIME_MS = 180 * 24 * 60 * 60 * 1000;

const bytes = new TextEncoder();

async function key(password) {
  return crypto.subtle.importKey(
    "raw",
    bytes.encode(password),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
}

function hex(buffer) {
  return Array.from(new Uint8Array(buffer))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

async function sign(payload, password) {
  return hex(await crypto.subtle.sign("HMAC", await key(password), bytes.encode(payload)));
}

/* Сравнить две строки, не рассказывая, на каком символе они разошлись.
   Обе стороны сначала хешируются, поэтому сравнение идёт по равной длине
   даже когда входы разной длины. */
async function sameSecret(a, b) {
  const [left, right] = await Promise.all([
    crypto.subtle.digest("SHA-256", bytes.encode(a)),
    crypto.subtle.digest("SHA-256", bytes.encode(b)),
  ]);
  const x = new Uint8Array(left);
  const y = new Uint8Array(right);
  let diff = 0;
  for (let i = 0; i < x.length; i += 1) diff |= x[i] ^ y[i];
  return diff === 0;
}

export async function passwordMatches(given, password) {
  if (!password || !given) return false;
  return sameSecret(given, password);
}

export function readCookie(header, name) {
  if (!header) return "";
  for (const part of header.split(";")) {
    const at = part.indexOf("=");
    if (at < 0) continue;
    if (part.slice(0, at).trim() === name) return part.slice(at + 1).trim();
  }
  return "";
}

export async function issueCookie(password, now = Date.now()) {
  const expiry = now + LIFETIME_MS;
  const payload = `1.${expiry}`;
  const value = `${payload}.${await sign(payload, password)}`;
  return (
    `${COOKIE}=${value}; Path=/; Max-Age=${Math.floor(LIFETIME_MS / 1000)}; ` +
    "HttpOnly; Secure; SameSite=Lax"
  );
}

export async function cookieValid(value, password, now = Date.now()) {
  if (!value || !password) return false;
  const parts = value.split(".");
  if (parts.length !== 3 || parts[0] !== "1") return false;
  const expiry = Number(parts[1]);
  if (!Number.isFinite(expiry) || expiry <= now) return false;
  return sameSecret(parts[2], await sign(`1.${parts[1]}`, password));
}

/* Куда отправить её после правильного пароля: по её же адресу или на главную.
   Только путь — «next=https://…» это начало открытого редиректа.

   Правило, которое эта функция однажды нарушила на курсе лекций: браузер
   причёсывает адрес *до* того, как его прочитает, поэтому проверка исходной
   строки — это проверка не того адреса, куда в итоге пойдут. Табуляция,
   перевод строки и возврат каретки удаляются целиком («/<tab>/evil.example»
   станет «//evil.example» ещё до перехода), и только после этого смотрим.

   Обе косые важны. «//evil.example» — это адрес без протокола, а «/\evil»
   браузеры выпрямляют в него же: одна ведущая косая ничего не доказывает. */
const HOME = "https://japan.invalid";

export function safeNext(raw) {
  if (typeof raw !== "string") return "/";
  const clean = raw.replace(/[\t\n\r]/g, "");
  if (!clean.startsWith("/") || /^\/[/\\]/.test(clean)) return "/";

  let here;
  try {
    here = new URL(clean, HOME);
  } catch {
    return "/";
  }
  if (here.origin !== HOME) return "/";

  /* И посмотреть на то, что вышло, а не только на то, что вошло: «/.//evil»
     на входе наш, а на выходе — «//evil», чужой. */
  const target = here.pathname + here.search + here.hash;
  return /^\/[/\\]/.test(target) ? "/" : target;
}
