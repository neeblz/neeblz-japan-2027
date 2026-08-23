#!/usr/bin/env python3
"""Померить главную на компьютере: два экрана, и ничего не вылезло.

    ../.venv-shot/bin/python3 test/wide.py

Меряется собранный `dist/index.html`, а не выложенное: тут вопрос не в двери,
а в вёрстке, и ждать выкладки, чтобы узнать высоту, незачем.

Порог — 1800 точек при ширине 1440. Это её слово 2026-08-23: «2 экрана это
ок». То есть цель не «влезть любой ценой», а «не листать бесконечно».

Высота документа ловит только переполнение наружу; внутри карточки содержимое
вылезает молча, а страница при этом остаётся ровно той же высоты — поэтому
каждая колонка меряется отдельно.
"""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent.parent
PAGE = HERE / "dist" / "index.html"
SHOTS = HERE.parent / "shots"
DESK = {"width": 1440, "height": 900}
LIMIT = 1800

problems, notes = [], []


def want(ok: bool, said: str):
    (notes if ok else problems).append(("✓" if ok else "✗") + " " + said)


with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(viewport=DESK, device_scale_factor=2)
    page.goto(PAGE.as_uri(), wait_until="load")
    page.wait_for_timeout(300)

    size = page.evaluate("""() => {
      const doc = document.documentElement;
      const over = [];
      for (const el of document.querySelectorAll('.city,.city .inner,.thread,.alert,.ledger,.blank')) {
        const d = el.scrollHeight - el.clientHeight;
        const w = el.scrollWidth - el.clientWidth;
        if (d > 1 || w > 1) over.push((el.className || el.tagName) + ' +' + d + '/' + w);
      }
      return { h: doc.scrollHeight, w: doc.scrollWidth, client: doc.clientWidth, over };
    }""")
    want(size["h"] <= LIMIT, f'высота {size["h"]}px при пороге {LIMIT}px')
    want(size["w"] <= size["client"] + 1,
         f'страница не едет вбок ({size["w"]}px в {size["client"]}px)')
    want(not size["over"], "внутри колонок ничего не вылезает"
         + (" — " + ", ".join(size["over"][:4]) if size["over"] else ""))

    # ── нитка: ширина отрезка это ночи, а не глазомер
    bars = page.evaluate("""() => [...document.querySelectorAll('.thread .bar:not(.air)')]
        .map(el => ({ n: el.querySelector('.n').textContent.trim(),
                      w: Math.round(el.getBoundingClientRect().width) })) """)
    want(len(bars) == 4, f"отрезков в нитке {len(bars)}")
    if len(bars) >= 2:
        four = [b["w"] for b in bars if b["n"].startswith("4")]
        two = [b["w"] for b in bars if b["n"].startswith("2")]
        if four and two:
            ratio = four[0] / two[0]
            want(1.8 < ratio < 2.2,
                 f"четыре ночи вдвое шире двух ({four[0]}px против {two[0]}px)")

    # ── карточки городов: четыре в ряд, все одной высоты сверху
    cards = page.evaluate("""() => [...document.querySelectorAll('.city')]
        .map(el => { const r = el.getBoundingClientRect();
                     return { top: Math.round(r.top), h: Math.round(r.height) }; })""")
    want(len(cards) == 4, f"карточек городов {len(cards)}")
    want(len({c["top"] for c in cards}) == 1, "все четыре в одном ряду")

    # ── места из вишлиста помечены как желания, а не как брони
    wishes = page.locator(".wishes li")
    want(wishes.count() >= 4, f"мест из вишлиста на странице {wishes.count()}")
    caps = page.locator(".wish-cap").all_inner_texts()
    want(all("не бронь" in c for c in caps),
         f"у каждого города сказано, что это не бронь ({len(caps)})")

    # ── деньги: доллар крупно, иена рядом, курс подписан датой
    total = page.locator(".total").inner_text()
    want("$" in total and "¥297" in total.replace(" ", " ").replace(" ", " "),
         "итог показан в долларах и иенах")
    want("курс на" in total, "курс подписан датой")

    # ── ночь 14 → 15: видна, спокойная, ничего не требует
    alert = page.locator("#overlap-14")
    want(alert.count() == 1, "заметка про ночь 14 → 15 на странице одна")
    want(alert.bounding_box()["y"] < 900, "она на первом экране")
    body = page.inner_text("body").lower()
    want("нужно решение" not in body and "требует решения" not in body,
         "ничего не требует решения")

    # ── пустые поля с подписью: ни одного выдуманного числа
    blanks = page.locator(".blank b").all_inner_texts()
    want(len(blanks) == 3, f"пустых полей с подписью {len(blanks)}: {', '.join(blanks)}")

    SHOTS.mkdir(exist_ok=True)
    page.screenshot(path=str(SHOTS / "japan-wide-top.png"))
    page.screenshot(path=str(SHOTS / "japan-wide-full.png"), full_page=True)

    # ── и то же самое на телефоне: ничего не торчит вбок
    phone = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
    phone.goto(PAGE.as_uri(), wait_until="load")
    phone.wait_for_timeout(200)
    side = phone.evaluate("""() => {
      const doc = document.documentElement;
      const wide = [...document.querySelectorAll('*')]
        .filter(el => el.getBoundingClientRect().right > doc.clientWidth + 1)
        .map(el => el.tagName + '.' + (el.className || '').toString().slice(0, 24));
      return { scroll: doc.scrollWidth, client: doc.clientWidth, wide: wide.slice(0, 5) };
    }""")
    want(side["scroll"] <= side["client"] + 1,
         f'на телефоне не едет вбок ({side["scroll"]}px в {side["client"]}px)'
         + (f' — торчит: {side["wide"]}' if side["wide"] else ""))

    # По видимым целям надо попадать пальцем. Считаются только видимые:
    # списки лежат в свёрнутых <details> и высоту имеют нулевую.
    small = phone.evaluate("""() => [...document.querySelectorAll('.btn, .todo-group label, summary')]
        .filter(el => el.offsetParent !== null)
        .map(el => ({ t: (el.className || el.tagName).toString().slice(0, 20),
                      h: Math.round(el.getBoundingClientRect().height) }))
        .filter(x => x.h < 36)""")
    want(not small, f"по видимым целям можно попасть пальцем (мелких: {len(small)})"
         + (f" — {small[:3]}" if small else ""))

    # И свёрнутое действительно разворачивается: шестнадцать дней на месте.
    phone.locator('summary:text-is("По дням")').click()
    phone.wait_for_timeout(150)
    days = phone.locator("#days > ol.days > li")
    want(days.count() == 16 and days.first.bounding_box() is not None,
         f"«По дням» разворачивается, дней {days.count()}")
    phone.screenshot(path=str(SHOTS / "japan-phone-new.png"), full_page=True)
    browser.close()

for line in notes + problems:
    print(line)
print(f"\nкадры: {SHOTS}/japan-wide-top.png, japan-wide-full.png, japan-phone-new.png")
sys.exit(1 if problems else 0)
