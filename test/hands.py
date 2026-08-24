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
    #
    # Отказаться тоже надо уметь: у пункта дня удаление необратимо (файловый
    # пункт ложится в «убранное» и назад из браузера не достаётся), и
    # проверить там можно только одно — что вопрос задан, а «нет» слушают.
    asked = []
    agree = {"yes": True}

    def answer(dialog):
        asked.append(dialog.message)
        dialog.accept() if agree["yes"] else dialog.dismiss()

    page.on("dialog", answer)

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
    # ¥290 675, а не ¥297 912: 23 августа Ни прислала новое подтверждение по
    # lyf Ginza — тариф ASR Advanced Purchase, ¥50 205 вместо ¥57 442. Число
    # прибито нарочно, чтобы тихая правка её денег краснела; здесь оно просто
    # осталось от старой брони, и об этом никто не узнал, потому что этот тест
    # с тех пор не гоняли.
    want(housing_jpy == 290_675, f"жильё на месте: ¥{housing_jpy}")
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

    # ── дни: тасовать руками и увидеть, что это осталось
    #
    # Ни 2026-08-24: «мне нужно сделать так, чтобы можно было места тасовать и
    # переносить из дня в день». Круг в `round.sh` доказывает то же самое через
    # ручку; здесь — через её руки, потому что между ручкой и руками лежит вся
    # страница, и сломаться может именно она.
    #
    # Убирается за собой всё: пункты возвращаются на свои места, дописанное
    # удаляется, правка снимается. Необратимое (удаление файлового пункта) тут
    # не проверяется совсем — только то, что вопрос задают и «нет» слушают.
    unfold()
    day6 = page.locator('#days details.day[data-day="2027-01-06"]')
    items6 = page.locator('[data-day-items="2027-01-06"] > li')
    order6 = [x.get_attribute("data-item") for x in items6.all()]
    want(order6[:2] == ["d06-1", "d06-2"], f"день приезжает в файловом порядке: {order6[:3]}")
    want(day6.locator(".acts").count() == len(order6),
         "ручки появились у каждого пункта — значит хранилище ответило")

    # ── ручки: не в глаза, но в досягаемости
    #
    # Ни 2026-08-24: «подпись к блоку и все кнопки убивай, они только
    # мусорность создают и место занимают». Стрелки «↑ / ↓» убраны совсем —
    # перетаскивание она освоила; остальное спрятано до наведения.
    #
    # Проверяется настоящей прозрачностью на экране, а не правилом в CSS: у
    # `display:none` и `visibility:hidden` вид тот же, но из обхода клавиатурой
    # они элемент выкидывают, и «спрятано от мыши» молча стало бы
    # «недостижимо без мыши». Поэтому три разных вопроса подряд: не видно
    # спокойной, видно под мышью, видно под клавиатурой.
    want(day6.locator(".acts .step").count() == 0, "стрелок «↑ / ↓» больше нет")
    seen = page.evaluate("""() => {
      const li = document.querySelector('[data-day-items="2027-01-06"] > li');
      return getComputedStyle(li.querySelector('.acts')).opacity;
    }""")
    want(seen == "0", f"спокойная строка ручек не показывает (прозрачность {seen})")

    items6.first.hover()
    page.wait_for_timeout(200)
    seen = page.evaluate("""() => {
      const li = document.querySelector('[data-day-items="2027-01-06"] > li');
      return getComputedStyle(li.querySelector('.acts')).opacity;
    }""")
    want(seen == "1", f"под мышью ручки появились (прозрачность {seen})")

    # Клавиатура: `Tab` доходит до списка дат внутри строки, и вместе с
    # фокусом обязана появиться вся тройка ручек.
    keyed = page.evaluate("""() => {
      const li = document.querySelector('[data-day-items="2027-01-06"] > li');
      const pick = li.querySelector('.acts select');
      pick.focus();
      return { got: document.activeElement === pick,
               shown: getComputedStyle(li.querySelector('.acts')).opacity,
               cross: li.querySelector('.acts .rm').getAttribute('aria-label') };
    }""")
    want(keyed["got"] and keyed["shown"] == "1",
         f'с клавиатуры ручки достижимы и видны (фокус {keyed["got"]}, {keyed["shown"]})')
    want(keyed["cross"] == "убрать пункт",
         f'крестик назван словами для голоса и клавиатуры: {keyed["cross"]!r}')
    cross = " ".join(items6.first.locator(".acts .rm").inner_text().split())
    want(cross == "✕", f"«убрать» стало просто крестиком: «{cross}»")
    page.evaluate("() => document.activeElement.blur()")

    # Куда именно бросать — считается от края строки, а не от её центра.
    #
    # Место определяется серединой строки под курсором, и центр — ровно эта
    # середина: какая сторона победит, решает округление координат мыши до
    # целых. Раньше это сходило с рук случайно, а после снятия колонки часов
    # строки стали ниже, и «в середину» начало читаться как «перед».
    # Проверка, зависящая от округления, проверяет округление.
    def drop_on(item, target, side):
        box = page.locator(f'[data-item="{target}"]').bounding_box()
        page.drag_and_drop(
            f'[data-item="{item}"]', f'[data-item="{target}"]',
            target_position={"x": min(40, box["width"] - 4),
                             "y": 2 if side == "before" else box["height"] - 2})
        page.wait_for_timeout(800)

    # 1. Вниз на одну строку — перетаскиванием, потому что другого способа
    #    больше нет.
    drop_on("d06-1", "d06-2", "after")
    page.reload(wait_until="load")
    page.wait_for_timeout(900)
    unfold()
    moved = [x.get_attribute("data-item")
             for x in page.locator('[data-day-items="2027-01-06"] > li').all()]
    want(moved[:2] == ["d06-2", "d06-1"],
         f"пункт съехал на строку вниз и остался там после перезагрузки: {moved[:3]}")

    # 2. Перенос в другой день списком дат — тот способ, который работает
    #    всегда: перетащить с 6 января на 17-е нельзя, между ними два экрана.
    page.locator('[data-item="d06-1"] .acts select').select_option("2027-01-17")
    page.wait_for_timeout(800)
    want(page.locator('[data-day-items="2027-01-06"] [data-item="d06-1"]').count() == 0,
         "пункт ушёл из старого дня")
    want(page.locator('[data-day-items="2027-01-17"] [data-item="d06-1"]').count() == 1,
         "и приехал в 17 января")
    counted = page.locator('#days details.day[data-day="2027-01-17"] [data-count]').inner_text()
    want(counted == "10", f"счётчик дня пересчитался ({counted})")

    # 3. Перетаскивание — приятное поверх надёжного.
    #
    # Брошено в нижний край первой строки — значит «после неё». Место
    # считается по середине строки под курсором: выше середины — перед ней,
    # ниже — за ней.
    drop_on("d17-9", "d17-1", "after")
    dragged = [x.get_attribute("data-item")
               for x in page.locator('[data-day-items="2027-01-17"] > li').all()]
    want(dragged[:2] == ["d17-1", "d17-9"],
         f"перетащенный мышью пункт уехал из конца дня в начало: {dragged[:3]}")
    page.reload(wait_until="load")
    page.wait_for_timeout(900)
    unfold()
    dragged = [x.get_attribute("data-item")
               for x in page.locator('[data-day-items="2027-01-17"] > li').all()]
    want(dragged[:2] == ["d17-1", "d17-9"], "и перетаскивание тоже пережило перезагрузку")

    # 4. Свой пункт: дописать, увидеть ссылку на карту, убрать.
    page.locator('#days details.day[data-day="2027-01-11"] .addday').click()
    page.fill('.itemform input[name="title"]', "Проба руками")
    page.fill('.itemform input[name="time"]', "вечер")
    page.fill('.itemform input[name="map"]', "Nara Park")
    page.click(".itemform .save")
    page.wait_for_timeout(900)
    mine = page.locator('[data-day-items="2027-01-11"] .it.mine')
    want(mine.count() == 1, f"свой пункт дописан в день ({mine.count()})")
    href = mine.first.locator("a.nm").get_attribute("href")
    want("Nara+Park" in href or "Nara%20Park" in href,
         f"её пункт тоже ведёт на карту: {href}")

    # 5. Правка файлового пункта ложится поверх, а не вместо.
    page.locator('[data-item="d11-6"] .acts .ed').click()
    page.fill('.itemform input[name="title"]', "Обед в Наре")
    page.click(".itemform .save")
    page.wait_for_timeout(900)
    want("Обед в Наре" in page.locator('[data-item="d11-6"]').inner_text(),
         "переписанное название видно на месте пункта")

    # 5б. Строка, разрезанная по местам, переживает и правку, и её отмену.
    #
    # Это самое хрупкое место всей затеи. Расстановка приезжает из хранилища и
    # перерисовывает каждую строку — а «Yasaka Shrine, Maruyama Park,
    # Chion-in» собрано питоном тремя ссылками, и собрать их в браузере
    # заново значило бы держать второе описание одной вещи. Поэтому браузер
    # разбивку **не трогает**, пока она не тронула текст; тронула — разбивка
    # снимается, потому что где в её новой строке какие места, мы не знаем.
    want(page.locator('[data-item="d12-7"] .nm a').count() == 3,
         "три места в строке остались тремя ссылками после ответа хранилища")
    page.locator('[data-item="d12-7"] .acts .ed').click()
    page.fill('.itemform input[name="title"]', "Ясака, Маруяма, Тионъин")
    page.click(".itemform .save")
    page.wait_for_timeout(900)
    want(page.locator('[data-item="d12-7"] .nm a').count() == 0,
         "её текст разбивку снял — угаданная ссылка увела бы не туда")
    page.locator('[data-item="d12-7"] .acts .ed').click()
    page.fill('.itemform input[name="title"]', "")
    page.click(".itemform .save")
    page.wait_for_timeout(900)
    want(page.locator('[data-item="d12-7"] .nm a').count() == 3,
         "снятая правка вернула все три ссылки, а не одну строку текста")

    # 6. Удаление спрашивает — и «нет» слушают.
    agree["yes"] = False
    asked.clear()
    page.locator('[data-item="d11-5"] .acts .rm').click()
    page.wait_for_timeout(700)
    want(len(asked) == 1, f"удаление спросило подтверждение ({len(asked)})")
    want(page.locator('[data-item="d11-5"]').count() == 1,
         "и на «нет» пункт остался на месте — молча ничего не стёрлось")
    agree["yes"] = True

    # ── вернуть дни как были
    #
    # Возвращается всё теми же движениями, которыми двигали: кнопки «наверх»
    # тут нет, и заводить её ради уборки за собой значило бы проверять не ту
    # страницу, которой она пользуется.
    def rows_of(date):
        return [x.get_attribute("data-item")
                for x in page.locator(f'[data-day-items="{date}"] > li').all()]

    def put_after(item, target, date):
        drop_on(item, target, "after")
        rows = rows_of(date)
        return rows.index(item) == rows.index(target) + 1

    def put_before(item, target, date):
        drop_on(item, target, "before")
        rows = rows_of(date)
        return rows.index(item) == rows.index(target) - 1

    # Перенос списком дат кладёт пункт в конец дня — обратно наверх его
    # поднимает то же перетаскивание, которым он оттуда и уехал.
    page.locator('[data-item="d06-1"] .acts select').select_option("2027-01-06")
    page.wait_for_timeout(700)
    want(put_before("d06-1", "d06-2", "2027-01-06"), "пункт поднят обратно наверх дня")
    want(put_after("d17-9", "d17-8", "2027-01-17"),
         "перетащенный пункт возвращён в конец дня")
    page.locator('[data-item="d11-6"] .acts .ed').click()
    page.fill('.itemform input[name="title"]', "")
    page.click(".itemform .save")
    page.wait_for_timeout(700)
    page.locator('[data-day-items="2027-01-11"] .it.mine .acts .rm').click()
    page.wait_for_timeout(700)
    page.reload(wait_until="load")
    page.wait_for_timeout(900)
    unfold()
    back6 = [x.get_attribute("data-item")
             for x in page.locator('[data-day-items="2027-01-06"] > li').all()]
    want(back6 == ["d06-1", "d06-2", "d06-3", "d06-4", "d06-5", "d06-6", "d06-7"],
         f"6 января вернулось в файловый порядок: {back6}")
    want(page.locator('[data-day-items="2027-01-11"] .it.mine').count() == 0,
         "дописанный пункт убран")
    want("Обед" == page.locator('[data-item="d11-6"] .nm').inner_text(),
         "снятая правка вернула файловый текст, а не пустоту")

    # ── и убрать за собой
    #
    # Счёт вопросов начинается заново: дни свои подтверждения уже спросили, и
    # смешивать их с записями значит проверять сумму вместо утверждения.
    unfold()
    asked.clear()
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
