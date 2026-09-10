#!/usr/bin/env python3
"""Свежий курс доезжает до её экрана — проверка настоящим браузером.

    ../.venv-shot/bin/python3 test/fx-live.py

Разбор ответа проверен без сети (`test/fx.test.mjs`), разметка — сборкой
(`test/test_data.py`). Непроверенным остаётся ровно то, что между ними:
доехало ли новое число до экрана и **все ли** доллары оно переписало.

Поэтому здесь ручке подсовывается заведомо другой курс, и смотрится, что
изменилось на выложенной странице. Ниже три вопроса, и все три задаются
браузером, а не расчётом:

  1. без подмены страница показывает впечатанный курс и не мигает;
  2. с подменой все доллары пересчитаны из иены, а иены не тронуты;
  3. ручка молчит (503) — страница остаётся на впечатанном курсе со своей
     подписью, а не показывает пустоту.

Третий вопрос и есть главный: отказ чужого сервиса не должен выглядеть как
поломка её страницы.
"""

import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent.parent
SITE = "https://japan-2027-eti.pages.dev"
PHONE = {"width": 390, "height": 844}

password = (HERE.parent / ".japan-password").read_text().strip()
built = json.loads((HERE / "data" / "trip.json").read_text(encoding="utf-8"))["fx"]

# Курс нарочно далёкий от настоящего: если что-то не пересчиталось, разница
# будет видна сразу, а не потонет в округлении.
FAKE = {"usd_per_jpy": 100.0, "as_of": "2027-03-01", "human": "1 марта 2027"}

problems: list[str] = []
notes: list[str] = []


def want(ok: bool, said: str):
    (notes if ok else problems).append(("✓" if ok else "✗") + " " + said)


def dollars(page):
    """Что показано долларами и из какой иены оно посчитано."""
    return page.evaluate("""() => [...document.querySelectorAll('[data-yen]')].map(n => ({
      yen: Number(n.getAttribute('data-yen')),
      usd: Number(n.textContent.replace(/[^\\d]/g, '')),
      price: n.parentNode && n.parentNode.className === 'price',
    }))""")


def captions(page):
    return page.evaluate(
        "() => [...document.querySelectorAll('[data-fx]')].map(n => n.textContent.trim())")


def enter(page):
    page.goto(SITE + "/", wait_until="domcontentloaded")
    if "Пароль" in page.content():
        page.fill('input[name="password"]', password)
        page.click('button[type="submit"]')
    page.wait_for_load_state("networkidle")


with sync_playwright() as pw:
    browser = pw.chromium.launch()

    # ── 1. как есть
    page = browser.new_page(viewport=PHONE)
    enter(page)
    page.wait_for_timeout(1500)
    shown = dollars(page)
    want(bool(shown), f"пар «доллар из иены» на странице: {len(shown)}")
    rate = built["usd_per_jpy"]
    want(all(d["usd"] == round(d["yen"] / rate) for d in shown),
         f"без подмены всё посчитано впечатанным курсом ¥{rate}")
    said = captions(page)
    want(all(str(rate) in c for c in said), f"подписи называют его же: {len(said)} шт.")
    page.close()

    # ── 2. ручка отдаёт другой курс
    page = browser.new_page(viewport=PHONE)
    page.route("**/api/fx", lambda route: route.fulfill(
        status=200,
        content_type="application/json; charset=utf-8",
        body=json.dumps({"ok": True, "fx": FAKE}),
    ))
    enter(page)
    page.wait_for_timeout(1500)
    after = dollars(page)

    want(len(after) == len(shown), "ни одна пара не потерялась при пересчёте")
    want(all(d["usd"] == round(d["yen"] / FAKE["usd_per_jpy"]) for d in after),
         "все доллары пересчитаны новым курсом — ни одного забытого")
    want([d["yen"] for d in after] == [d["yen"] for d in shown],
         "иены не тронуты: настоящая цена не зависит от курса")

    said = captions(page)
    want(all(FAKE["human"] in c for c in said),
         f"подписи назвали новую дату: {said[0] if said else '—'}")
    want(all(str(built["usd_per_jpy"]) not in c for c in said),
         "старый курс не остался в подписи рядом с новым числом")

    # Итог под чеком складывается из показанных городских долларов, а не из
    # пересчёта общей иены: иначе столбик даёт на доллар больше, чем итог.
    #
    # Но чек — это вся поездка: как только у Ни появляется хоть одна своя
    # запись, к жилью прибавляется она. Первый прогон этой проверки требовал
    # равенства «итог = города» и покраснел на живой странице, где её запись
    # уже лежит, — сломанной оказалась сама проверка, а не страница.
    check = page.evaluate("""() => ({
      usd: Number(document.querySelector('[data-usd]').textContent.replace(/[^\\d]/g,'')),
      jpy: Number(document.querySelector('[data-jpy]').textContent.replace(/[^\\d]/g,'')),
      mine: !document.querySelector('[data-parts]').hidden,
      parts: [...document.querySelectorAll('[data-parts] .num')]
        .map(n => Number(n.textContent.replace(/[^\\d]/g,''))),
      housing: (() => {
        const built = document.querySelector('[data-parts] .part.built .num');
        return built ? Number(built.textContent.replace(/[^\\d]/g,'')) : null;
      })(),
    })""")
    cities_usd = sum(d["usd"] for d in after if d["price"])
    cities_jpy = sum(d["yen"] for d in after if d["price"])

    if not check["mine"]:
        want(check["usd"] == cities_usd,
             f"итог ${check['usd']} равен столбику городов ${cities_usd}")
    else:
        want(check["housing"] == cities_jpy,
             f"жильё в чеке ¥{check['housing']} равно сумме городов ¥{cities_jpy}")
        want(check["jpy"] == sum(check["parts"]),
             f"итог ¥{check['jpy']} равен сумме разделов ¥{sum(check['parts'])}")
        want(check["usd"] >= cities_usd,
             f"итог ${check['usd']} не меньше жилья ${cities_usd} — в нём ещё её записи")

    # Линейка считает тем же курсом, что и всё остальное.
    page.fill('[data-conv="jpy"]', "10000")
    page.wait_for_timeout(300)
    ruler = page.evaluate(
        """() => Number(document.querySelector('[data-conv="usd"]').value.replace(/[^\\d]/g,''))""")
    want(ruler == round(10000 / FAKE["usd_per_jpy"]),
         f"линейка пересчитала ¥10 000 в ${ruler} тем же курсом")
    page.close()

    # ── 3. ручка отказала
    page = browser.new_page(viewport=PHONE)
    page.route("**/api/fx", lambda route: route.fulfill(
        status=503,
        content_type="application/json; charset=utf-8",
        body=json.dumps({"ok": False, "why": "сеть молчит"}),
    ))
    enter(page)
    page.wait_for_timeout(1500)
    quiet = dollars(page)
    want([d["usd"] for d in quiet] == [d["usd"] for d in shown],
         "отказ ручки ничего не изменил — остался впечатанный курс")
    said = captions(page)
    want(all(str(built["usd_per_jpy"]) in c for c in said),
         "подпись по-прежнему называет впечатанный курс и его дату")
    page.close()

    browser.close()

for line in notes + problems:
    print(line)
print()
print(f"{len(notes)} сошлось, {len(problems)} нет")
sys.exit(1 if problems else 0)
