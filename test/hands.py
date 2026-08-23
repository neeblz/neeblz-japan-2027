#!/usr/bin/env python3
"""Пройти её путь руками: войти, вписать, увидеть, что чек сошёлся.

    ../.venv-shot/bin/python3 test/hands.py --url http://127.0.0.1:8973 --password …

Проверяет то, чего не видят ни `node --test` (там нет страницы), ни
`wide.py` (там нет хранилища): что запись, набранная в форме, доезжает до
карточки города, а итог под ней складывается из показанного.

Главная сверка — глазами теста, а не глазами человека: **сумма разделов,
показанных на экране, обязана совпасть с числом над ними**. Число, которое
нельзя проверить глазами, — плохое число; проверка, которая верит коду на
слово, — плохая проверка.

Убирает за собой: всё, что вписал, удаляет в конце.

**На боевой странице не работает и работать не должен.** 23 августа я прогнал
его на `japan-2027-eti.pages.dev` и он стёр всё хранилище — вместе с записью,
которую Ни внесла своей рукой десятью минутами раньше («тбилиси токио тбилиси»,
$1000). Запись я восстановил, но потерять её мог и не заметить: тест честно
«убирает за собой», а убирает он **всё, что видит**, а не только своё.

Поэтому здесь стоит отказ: боевой адрес — стоп, если только не сказано
`--yes-i-know-its-live` явно. Запускать надо на `wrangler pages dev` или на
превью-ветке. Проверка, способная стереть её данные, обязана спрашивать
разрешение, а не полагаться на то, что запускающий помнит.
"""

LIVE = ("japan-2027-eti.pages.dev",)

import argparse
import re
import sys

from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser()
parser.add_argument("--url", required=True)
parser.add_argument("--yes-i-know-its-live", action="store_true",
                    help="разрешить прогон на боевой — он сотрёт её записи")
parser.add_argument("--password", required=True)
parser.add_argument("--width", type=int, default=1440)
args = parser.parse_args()

# Отказ раньше всего остального: к этому месту ещё ничего не открыто и не
# записано. Проверка, которая умеет стереть её данные, обязана спрашивать
# разрешение, а не надеяться на память запускающего.
if any(host in args.url for host in LIVE) and not args.yes_i_know_its_live:
    sys.exit(
        f"✗ {args.url} — боевая страница Ни. Этот тест вписывает и удаляет "
        "записи, а удаляет он всё хранилище, а не только своё: 23 августа так "
        "исчезла её собственная запись.\n"
        "  Гоняй на `wrangler pages dev` или на превью-ветке. Если правда "
        "надо на боевой — `--yes-i-know-its-live`, и сначала сними копию "
        "записей через GET /api/entries."
    )

problems, notes = [], []


def want(ok: bool, said: str):
    (notes if ok else problems).append(("✓" if ok else "✗") + " " + said)


def digits(text: str) -> int:
    """«¥311 232» → 311232. Разряды разведены неразрывными пробелами."""
    found = re.sub(r"[^\d]", "", text or "")
    return int(found) if found else 0


with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={"width": args.width, "height": 900})
    # Удаление спрашивает подтверждение — соглашаемся, но только тогда, когда
    # спросили: молчаливое согласие на всё скрыло бы пропавший вопрос.
    asked = []
    page.on("dialog", lambda d: (asked.append(d.message), d.accept()))

    page.goto(args.url + "/", wait_until="load")
    page.fill('input[name="password"]', args.password)
    page.click('button[type="submit"]')
    page.wait_for_selector("#check", timeout=15000)
    page.wait_for_timeout(600)

    # Круг начинается с чистого списка: прошлый прогон мог упасть на середине
    # и оставить своё. Иначе «место легло в карточку» сойдётся на чужой
    # записи, а не на той, которую вписали сейчас.
    def unfold():
        """Развернуть всё свёрнутое: после перезагрузки стрелки снова закрыты,
        а нажать кнопку внутри закрытой стрелки нельзя — ни тесту, ни ей."""
        page.evaluate("() => document.querySelectorAll('details').forEach(d => d.open = true)")
        page.wait_for_timeout(150)

    def wipe():
        """Убрать все её записи. Свёрнутое сначала разворачивается: кнопка
        внутри закрытой стрелки существует, но нажать её нельзя — ровно как
        и ей."""
        unfold()
        while page.locator(".own .rm").count():
            page.locator(".own .rm").first.click()
            page.wait_for_timeout(500)

    wipe()
    asked.clear()

    check = page.locator("#check")
    housing_jpy = digits(check.locator("[data-jpy]").inner_text())
    housing_usd = digits(check.locator("[data-usd]").inner_text())
    want(housing_jpy == 297_912, f"жильё на месте: ¥{housing_jpy}")
    # `inner_text` отдаёт то, что нарисовано, а подпись рисуется прописными
    # (`text-transform`), — сравниваем без учёта регистра.
    want("жильё" in check.locator("[data-cap]").inner_text().lower(),
         "пока записей нет, чек назван жильём")

    # ── бронь с ценой
    page.click('.knob[data-add="booking"]')
    page.fill("#f-title", "Синкансэн Токио → Киото")
    page.fill("#f-amount", "13 320")
    page.select_option('.pane select[name="state"]', "paid")
    page.click(".pane .save")
    page.wait_for_timeout(900)

    fold = page.locator('[data-fold="bought"]')
    want(fold.get_attribute("open") is not None, "раздел «куплено отдельно» раскрылся сам")
    lines = page.locator("[data-mine-booking] .own")
    want(lines.count() == 1, f"броней в разделе {lines.count()} (ждали одну)")
    said = lines.first.inner_text()
    want("Синкансэн" in said, "бронь появилась в разделе")
    want("уже оплачено" in said, "и помечена как оплаченная")

    cap = check.locator("[data-cap]").inner_text()
    want("вся поездка" in cap.lower(), f"чек стал чеком всей поездки: «{cap}»")
    total_jpy = digits(check.locator("[data-jpy]").inner_text())
    want(total_jpy == housing_jpy + 13_320,
         f"итог вырос ровно на цену брони: ¥{total_jpy}")

    parts = [digits(x) for x in check.locator(".parts .num").all_inner_texts()]
    want(sum(parts) == total_jpy,
         f"сумма разделов = итог ({' + '.join(str(p) for p in parts)} = {total_jpy})")
    states = [digits(x) for x in check.locator(".legend b").all_inner_texts()]
    want(sum(states) == total_jpy,
         f"оплачено + предстоит + на месте = итог ({sum(states)} = {total_jpy})")

    # ── место в городе, с ценой в долларах
    page.click('.city:last-child .tiny[data-add="place"]')
    page.fill("#f-title", "Лавка сэндвичей")
    page.fill("#f-amount", "12")
    page.select_option('.pane select[name="currency"]', "usd")
    page.click(".pane .save")
    page.wait_for_timeout(900)

    where = page.locator('[data-mine="omo3"] .own')
    want(where.count() == 1, f"мест в карточке Асакусы {where.count()} (ждали одно)")
    said = where.first.inner_text()
    want("$12" in said, "доллар показан её числом, а не пересчитанным обратно")
    want("плачу на месте" in said, "у места по умолчанию — оплата на месте")

    # ── пункт без цены: в чек не идёт, но назван вслух
    page.click('.knob[data-add="todo"]')
    page.fill("#f-title", "Виза")
    page.click(".pane .save")
    page.wait_for_timeout(900)

    was = digits(check.locator("[data-jpy]").inner_text())
    page.click('.knob[data-add="todo"]')
    page.fill("#f-title", "Дьюти-фри")
    page.click(".pane .save")
    page.wait_for_timeout(900)
    now = digits(check.locator("[data-jpy]").inner_text())
    want(was == now, f"запись без цены не сдвинула итог (¥{was} → ¥{now})")
    says = check.locator("[data-says]").inner_text()
    want("без цены" in says, f"и названа вслух: «{says}»")

    parts = [digits(x) for x in check.locator(".parts .num").all_inner_texts()]
    states = [digits(x) for x in check.locator(".legend b").all_inner_texts()]
    want(sum(parts) == now and sum(states) == now,
         f"после четырёх записей столбики всё ещё сходятся ({sum(parts)}/{sum(states)}/{now})")

    # ── правка: цена появилась у того, у чего её не было
    page.locator('[data-mine-todo="Ещё"] .own', has_text="Виза").locator(".ed").click()
    page.fill("#f-amount", "8000")
    page.select_option('.pane select[name="state"]', "upcoming")
    page.click(".pane .save")
    page.wait_for_timeout(900)
    after = digits(check.locator("[data-jpy]").inner_text())
    want(after == now + 8_000, f"правка цены доехала до итога (¥{now} → ¥{after})")

    # ── галочка переживает перезагрузку страницы
    #
    # Нажимается подпись, а не сам квадратик: настоящий `input` спрятан
    # (`opacity:0`), видимая цель — нарисованная галочка внутри label. Именно
    # по ней попадает пальцем Ни.
    page.locator('[data-mine-todo="Ещё"] .own', has_text="Виза").locator("label").click()
    page.wait_for_timeout(700)
    page.reload(wait_until="load")
    page.wait_for_timeout(900)
    unfold()
    ticked = page.locator('[data-mine-todo="Ещё"] .own', has_text="Виза").locator(
        'input[type="checkbox"]').is_checked()
    want(ticked, "галочка пережила перезагрузку страницы")

    built = 'Багаж::Собрать маленькую сумку на Киносаки'
    unfold()
    page.locator(f'label:has([data-todo="{built}"])').click()
    page.wait_for_timeout(700)
    page.reload(wait_until="load")
    page.wait_for_timeout(900)
    unfold()
    want(page.locator(f'[data-todo="{built}"]').is_checked(),
         "галочка на пункте из trip.json тоже пережила перезагрузку")

    # ── и убрать за собой
    unfold()
    count = page.locator(".own").count()
    wipe()
    page.locator(f'label:has([data-todo="{built}"])').click()
    page.wait_for_timeout(600)
    page.reload(wait_until="load")
    page.wait_for_timeout(900)
    unfold()
    want(page.locator(".own").count() == 0, "всё внесённое убрано")
    want(len(asked) == count, f"каждое удаление спросило подтверждение ({len(asked)} из {count})")
    back = digits(page.locator("#check [data-jpy]").inner_text())
    want(back == housing_jpy, f"чек вернулся к жилью: ¥{back}")

    browser.close()

for line in notes + problems:
    print(line)
sys.exit(1 if problems else 0)
