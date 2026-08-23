#!/usr/bin/env python3
"""Посмотреть на выложенную страницу глазами, а не по расчёту.

    ../.venv-shot/bin/python3 test/look.py

Проверяется **выложенная** версия, а не сборка на ходу: иначе это движущаяся
мишень. Геометрия меряется реальным getBoundingClientRect(), потому что
посчитанное по CSS и увиденное браузером — разные вещи.

Кадры кладутся в ../shots/ — они для Блэйза, а не для Ни: ей идёт ссылка.
"""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent.parent
SITE = "https://japan-2027-eti.pages.dev"
SHOTS = HERE.parent / "shots"
PHONE = {"width": 390, "height": 844}  # iPhone 14

password = (HERE.parent / ".japan-password").read_text().strip()

problems = []
notes = []


def want(ok: bool, said: str):
    (notes if ok else problems).append(("✓" if ok else "✗") + " " + said)


with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(viewport=PHONE, device_scale_factor=2)

    page.goto(SITE + "/", wait_until="domcontentloaded")
    want("Пароль" in page.content(), "закрытая страница просит пароль")

    page.fill('input[name="password"]', password)
    page.click('button[type="submit"]')
    page.wait_for_load_state("networkidle")

    want("Япония" in page.title(), f"вошли: {page.title()}")

    # ── ничего не торчит вбок: горизонтальную полосу телефон не прощает
    overflow = page.evaluate("""() => {
      const doc = document.documentElement;
      const wide = [...document.querySelectorAll('*')]
        .filter(el => el.getBoundingClientRect().right > doc.clientWidth + 1)
        .filter(el => !el.closest('nav.jump'))
        .map(el => el.tagName + '.' + (el.className || '').toString().slice(0, 30));
      return { scroll: doc.scrollWidth, client: doc.clientWidth, wide: wide.slice(0, 5) };
    }""")
    want(
        overflow["scroll"] <= overflow["client"] + 1,
        f'страница не едет вбок ({overflow["scroll"]}px в {overflow["client"]}px)'
        + (f' — торчит: {overflow["wide"]}' if overflow["wide"] else ""),
    )

    # ── заметка про 14-е: видна, спокойная, ничего не требует
    alert = page.locator("#overlap-14")
    want(alert.count() == 1, "блок про ночь 14-го на странице один")
    box = alert.bounding_box()
    want(box is not None and box["y"] < 1400, f'он в начале страницы (y={box["y"]:.0f}px)')
    colour = alert.evaluate("el => getComputedStyle(el).borderTopColor")
    want("168, 131, 75" in colour, f"рамка песочная, не тревожная ({colour})")
    said = alert.inner_text()
    want("14 → 15 января" in said, "названа именно та ночь")
    want("ночуешь в Киносаки" in said, "сказано, где она спит")
    want("заезд 15-го" in said, "сказано, что в OMO3 она заезжает 15-го")

    body = page.inner_text("body").lower()
    want("нужно решение" not in body, "со страницы ушло «нужно решение»")
    want("требует решения" not in body, "со страницы ушло «требует решения»")

    # ── обе оплаченные брони на месте, ни одна не вычеркнута
    for card in ("morizuya-2", "omo3"):
        el = page.locator(f"#{card}")
        want(el.count() == 1, f"карточка {card} на месте")
        klass = el.get_attribute("class") or ""
        want("noted" in klass, f"{card} помечена спокойно")
        want("clash" not in klass, f"{card} без тревожной пометки")

    # ── и видно, что заезд в OMO3 — 15-го, а ночь 14-го оплачена
    omo3 = page.locator("#omo3").inner_text()
    want("приезжаешь" in omo3.lower(), "в карточке OMO3 названа дата приезда")
    want("остаётся пустой" in omo3, "и сказано, что оплаченная ночь пустая")

    # ── сроки посчитаны в браузере, а не оставлены пустыми
    left = page.locator(".cancel .left")
    want(left.count() == 5, f"обратный счёт стоит у всех пяти броней ({left.count()})")

    # ── пальцем попадать: у ссылок, галочек и свёрток высота не меньше 36px.
    #    Считаются только видимые: списки и дни лежат в свёрнутых <details>,
    #    у них высота нулевая, и мерить её значит ловить не ту рыбу.
    small = page.evaluate("""() => {
      const targets = [...document.querySelectorAll('.btn, .todo-group label, summary')];
      return targets
        .filter(el => el.offsetParent !== null)
        .map(el => ({ t: el.className || el.tagName, h: Math.round(el.getBoundingClientRect().height) }))
        .filter(x => x.h < 36);
    }""")
    want(not small, f"по видимым целям можно попасть пальцем (мелких: {len(small)})"
         + (f" — {small[:3]}" if small else ""))

    # ── свёрнутое разворачивается и внутри всё на месте
    for name in ("Решить и забронировать", "По дням", "Багаж"):
        want(page.locator(f'summary:text-is("{name}")').count() == 1, f"свёрток «{name}» на месте")
    page.locator('summary:text-is("По дням")').click()
    page.wait_for_timeout(150)

    # ── даты: поездка начинается 4-го
    days = page.locator("#days > ol.days > li")
    want(days.count() == 16, f"дней в списке {days.count()}")
    want("4" == days.first.locator(".date b").inner_text().strip(), "первый день — 4-е")
    want(days.first.bounding_box() is not None, "развёрнутое видно, а не спрятано")

    # ── города и места из вишлиста
    cities = page.locator(".city")
    want(cities.count() == 4, f"карточек городов {cities.count()}")
    wishes = page.locator(".wishes li")
    want(wishes.count() >= 4, f"мест из вишлиста {wishes.count()}")
    want(all("не бронь" in c for c in page.locator(".wish-cap").all_inner_texts()),
         "у мест написано, что это не бронь")

    SHOTS.mkdir(exist_ok=True)
    page.screenshot(path=str(SHOTS / "japan-phone-full.png"), full_page=True)
    page.screenshot(path=str(SHOTS / "japan-phone-top.png"))
    browser.close()

for line in notes:
    print(line)
for line in problems:
    print(line)
print(f"\nкадры: {SHOTS}/japan-phone-full.png, japan-phone-top.png")
sys.exit(1 if problems else 0)
