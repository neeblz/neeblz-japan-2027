/* Дверь проверяется здесь, без выкладки.
 *
 *     node --test test/
 *
 * Правило, из-за которого этот файл существует: замок, который ни разу не
 * отказывал в тесте, и замок, которого нет, снаружи выглядят одинаково.
 * Поэтому проверяется не только «правильный пароль пускает», но и каждый
 * способ пройти мимо, который мы знаем.
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import { answer } from "../site/functions/api/_door.js";
import { COOKIE, cookieValid, issueCookie, safeNext } from "../site/functions/api/_gate.js";

const ENV = { JAPAN_PASSWORD: "открой-сезам" };
const HOST = "https://japan.example";

function get(path = "/", { cookie = "" } = {}) {
  return new Request(HOST + path, cookie ? { headers: { cookie } } : undefined);
}

function post(path, body, { cookie = "" } = {}) {
  const form = new FormData();
  for (const [k, v] of Object.entries(body)) form.append(k, v);
  return new Request(HOST + path, {
    method: "POST",
    body: form,
    ...(cookie ? { headers: { cookie } } : {}),
  });
}

async function cookieFor(now = Date.now()) {
  const raw = await issueCookie(ENV.JAPAN_PASSWORD, now);
  return raw.split(";")[0];
}

// ── закрыто по умолчанию ───────────────────────────────────────────────

test("без печенья главная не отдаётся", async () => {
  const verdict = await answer(get("/"), ENV);
  assert.equal(verdict.pass, false);
  assert.equal(verdict.response.status, 401);
  const body = await verdict.response.text();
  assert.match(body, /Пароль/);
  assert.doesNotMatch(body, /Моридзуя|OMO3|¥/, "за 401 не должно быть данных поездки");
});

test("без пароля в окружении закрыто всё, даже вход", async () => {
  for (const path of ["/", "/login", "/404.html"]) {
    const verdict = await answer(get(path), {});
    assert.equal(verdict.pass, false, path);
    assert.equal(verdict.response.status, 503, path);
  }
});

test("отказ не индексируется и не кэшируется", async () => {
  const verdict = await answer(get("/"), ENV);
  assert.match(verdict.response.headers.get("x-robots-tag"), /noindex/);
  assert.match(verdict.response.headers.get("cache-control"), /no-store/);
});

// ── вход ───────────────────────────────────────────────────────────────

test("правильный пароль выдаёт печенье и возвращает на её адрес", async () => {
  const verdict = await answer(
    post("/login", { password: ENV.JAPAN_PASSWORD, next: "/#stays" }),
    ENV
  );
  assert.equal(verdict.response.status, 303);
  assert.equal(verdict.response.headers.get("location"), "/#stays");
  const set = verdict.response.headers.get("set-cookie");
  assert.match(set, new RegExp(`^${COOKIE}=`));
  assert.match(set, /HttpOnly/);
  assert.match(set, /Secure/);
  assert.match(set, /SameSite=Lax/);
});

test("выданное печенье пускает", async () => {
  const verdict = await answer(get("/", { cookie: await cookieFor() }), ENV);
  assert.equal(verdict.pass, true);
  assert.match(verdict.headers["x-robots-tag"], /noindex/);
});

test("неправильный пароль — 401 и никакого печенья", async () => {
  const verdict = await answer(post("/login", { password: "не-он", next: "/" }), ENV);
  assert.equal(verdict.response.status, 401);
  assert.equal(verdict.response.headers.get("set-cookie"), null);
  assert.match(await verdict.response.text(), /не подошёл/);
});

test("пустой пароль не проходит", async () => {
  const verdict = await answer(post("/login", { password: "", next: "/" }), ENV);
  assert.equal(verdict.response.status, 401);
});

test("POST не-формой отвечает, а не падает", async () => {
  const request = new Request(HOST + "/login", {
    method: "POST",
    body: JSON.stringify({ password: "открой-сезам" }),
    headers: { "content-type": "application/json" },
  });
  const verdict = await answer(request, ENV);
  assert.equal(verdict.response.status, 401);
});

test("вошедшая на /login уезжает на главную", async () => {
  const verdict = await answer(get("/login", { cookie: await cookieFor() }), ENV);
  assert.equal(verdict.response.status, 303);
  assert.equal(verdict.response.headers.get("location"), "/");
});

// ── подделка печенья ───────────────────────────────────────────────────

test("печенье, подписанное другим паролем, не пускает", async () => {
  const alien = (await issueCookie("другой-пароль")).split(";")[0];
  const verdict = await answer(get("/", { cookie: alien }), ENV);
  assert.equal(verdict.pass, false);
});

test("просроченное печенье не пускает", async () => {
  const old = await cookieFor(Date.now() - 400 * 24 * 3600 * 1000);
  const verdict = await answer(get("/", { cookie: old }), ENV);
  assert.equal(verdict.pass, false);
});

test("срок в печенье нельзя продлить руками — подпись накрывает его", async () => {
  const raw = (await cookieFor()).slice(COOKIE.length + 1);
  const [v, expiry, sig] = raw.split(".");
  const stretched = `${COOKIE}=${v}.${Number(expiry) + 9e9}.${sig}`;
  assert.equal((await answer(get("/", { cookie: stretched }), ENV)).pass, false);
});

test("мусор вместо печенья не пускает", async () => {
  for (const junk of ["", "х", "1.2.3", "1..", "1.abc.def", "....", `${COOKIE}=`]) {
    assert.equal(await cookieValid(junk, ENV.JAPAN_PASSWORD), false, junk);
  }
});

test("печенье читается из середины списка", async () => {
  const mine = await cookieFor();
  const verdict = await answer(get("/", { cookie: `a=1; ${mine}; b=2` }), ENV);
  assert.equal(verdict.pass, true);
});

// ── открытый редирект ──────────────────────────────────────────────────

test("next не уводит на чужой сайт", async () => {
  const bad = [
    "https://evil.example",
    "//evil.example",
    "/\\evil.example",
    "/\tevil.example",
    "/\t/evil.example",
    "/\n//evil.example",
    "/.//evil.example",
    "javascript:alert(1)",
    "",
    null,
    undefined,
  ];
  for (const raw of bad) {
    const to = safeNext(raw);
    assert.ok(to.startsWith("/"), `${JSON.stringify(raw)} → ${to}`);
    assert.ok(!/^\/[/\\]/.test(to), `${JSON.stringify(raw)} → ${to}`);
  }
});

test("свои адреса next сохраняет", () => {
  assert.equal(safeNext("/"), "/");
  assert.equal(safeNext("/#budget"), "/#budget");
  assert.equal(safeNext("/?x=1"), "/?x=1");
});

test("чужой next не доезжает до Location даже при верном пароле", async () => {
  const verdict = await answer(
    post("/login", { password: ENV.JAPAN_PASSWORD, next: "//evil.example" }),
    ENV
  );
  assert.equal(verdict.response.headers.get("location"), "/");
});
