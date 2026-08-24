#!/usr/bin/env python3
"""Померить главную на компьютере: два экрана, ничего не вылезло, всё читается.

    ../.venv-shot/bin/python3 test/wide.py

Меряется собранный `dist/index.html`, а не выложенное: тут вопрос не в двери,
а в вёрстке, и ждать выкладки, чтобы узнать высоту, незачем.

Порог — 1780 точек при ширине 1440, и он всегда ставится по последнему
измерению, а не по запасу: сетка, сквозь которую свободно пролезает двести
точек нового, ничего не ловит. Потолок «2 экрана это ок» (1800) — её слово
2026-08-23.

История порога — история страницы: 1800 у длинной версии, 1650 после того как
подробности проживания уехали под стрелку (1604), 1780 когда страница перестала
быть только чтением (1736): появились кнопки «вносить своё», раздел «куплено
отдельно» и разбивка чека. 1803 сейчас — выросло на 13 точек 24 августа,
когда у экспресса до Киносаки появилась цена-вилка вместо пустого поля:
Ни спросила «а посмотреть не можете что ли?», я посмотрел, и заполненная
клетка выше пустой. Её потолок — «2 экрана это ок».

Последние 54 точки стоили трёх вещей, и стоили по-разному. Ближайший срок
отмены в шапке — 2 точки: он встал в пустоту правого столбца, которая была
там и раньше. Переезды в нитке — 29: поезд, время и цена под каждой стрелкой.
Строка «чего в итоге нет» под суммой — 23.

Обратно нашлись 24: свёртки внизу («решить и забронировать», «по дням» и
остальные) держали 44 точки высоты на компьютере — это размер пальца, и он
нужен на телефоне, где теперь и стоит.

До её потолка в 1800 осталось 10 точек. Следующее, что вырастет, придётся
чем-то оплатить — или спросить у неё, поднимать ли потолок.

1804 с 24 августа: раздел дней стал тасуемым, и у его свёртки появилась
подпись «16 дней · 98 пунктов». Одна точка — цена того, чтобы не открывать
раздел ради вопроса, есть ли там что-нибудь. Сами дни высоты не стоят: они
лежат внутри свёрнутого и раскрываются по одному.

**2045 с 24 августа — и это самый дорогой шаг за всю историю порога.**
Справка внизу (виза, документы до вылета, такс-фри) стоит **237 точек**:
страница выросла с 1802 до 2039. Оценка была 1845 — она считала пятую свёртку
в общей стопке, то есть 44 точки, и оказалась неверной, потому что виза под
стрелкой стоять не может. Её нельзя свернуть наравне с такс-фри: это самый
срочный срок на странице (вылет 4 января, подача только очно, конец декабря
у японских учреждений нерабочий), а свёрнутая она читается как «ещё одна
справка» и открывается в феврале. Развёрнутая рамка визы — 117 точек, две
оставшиеся свёртки — 89.

Из этих 237 точек торговаться можно ровно об одном: четыре свёртки над
справкой («решить», «куплено», «по дням», «багаж») стоят 176 точек и держат
одну строку текста каждая в 1308 точках ширины. Поставить их в два столбца
вернуло бы 88. Это правка чужого раздела, и её решает не порог, а Ни.

Дата проверки справки стоит в подвале, а не под самой справкой: отдельной
строкой она стоила 37 точек, в подвале — ноль (см. `colophon`).

Порог — наш, потолок «2 экрана это ок» — её слово. 2039 это 2.27 экрана, и
про это разговор с ней, а не с сеткой: подгонять вёрстку под число, которое
мы сами назначили, значит прятать вопрос вместо того, чтобы его задать.

**1950 с 24 августа, вечер: страница похудела на 109 точек** (2056 → 1947), и
почти всё это — один блок. Ни: «блок **как задумано** убивай, он действует на
нервы и мешается». Спокойная заметка про ночь 14 → 15 стояла на первом экране
и рассказывала решённое; данные под ней остались, показ ушёл. Подпись свёртки
дней («16 дней · 98 пунктов») вернула ещё одну точку — ту самую, которой она
когда-то и стоила.

Сам раздел дней высоты страницы не касается — он внутри свёрнутого, — но
внутри стал вдвое короче. Два столбца, её слово «сделай дни в два столбца»:
раздел со свёрнутыми днями 1336 → 981, все шестнадцать дней развёрнутыми
7035 → 5079. Часы, снятые со строк, свою высоту при этом не отдали: строка
меряется по названию, а не по колонке времени.

Линейка «иены → доллары» 24 августа не стоила ни точки: средний столбец чека
был на 137 точек ниже левого, и она встала целиком в эту пустоту. Здесь это
сторожится отдельным правилом — средний столбец обязан остаться не выше
левого, — потому что высота документа заметит только тот день, когда он
перерастёт, а перерастёт он сразу на всю разницу.

Меряется страница **как она уезжает** — пустая. Её записи приходят из
хранилища и растят её дальше: это её список, и складывать его она может сама.

Осело меньше, чем кажется по карточке: высоту ряда задаёт самая длинная из
четырёх — Киносаки с двумя сроками отмены, — а свернули мы у всех поровну.

Высота документа ловит только переполнение наружу; внутри карточки содержимое
вылезает молча, а страница при этом остаётся ровно той же высоты — поэтому
каждая колонка меряется отдельно.

Контраст меряется здесь же, на каждой видимой строке. Причина: «сложно читать»
— это число, а не вкус, и «мне кажется, стало лучше» его не проверяет. Пороги
её: основной текст 7:1, подписи и мелочь 4.5:1.
"""

import json
import re
import sys
from datetime import date
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent.parent
PAGE = HERE / "dist" / "index.html"
SHOTS = HERE.parent / "shots"
DESK = {"width": 1440, "height": 900}
LIMIT = 1950
MAIN, SMALL = 7.0, 4.5

problems, notes = [], []


def want(ok: bool, said: str):
    (notes if ok else problems).append(("✓" if ok else "✗") + " " + said)


# Пробегает каждый видимый кусок текста и считает его контраст к тому фону,
# который под ним реально оказался, — включая прозрачность родителей. Считать
# по переменным в `:root` бесполезно: `opacity:.6` на предке превращает
# записанные 5.6:1 в 2.9:1, и переменная об этом не знает.
CONTRAST = """
(floors) => {
  const lin = c => (c /= 255) <= 0.04045 ? c / 12.92 : Math.pow((c + .055) / 1.055, 2.4);
  const lum = c => .2126 * lin(c[0]) + .7152 * lin(c[1]) + .0722 * lin(c[2]);
  const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
                            return (x + .05) / (y + .05); };
  const rgba = s => { const m = (s || '').match(/[\\d.]+/g);
                      return m ? [+m[0], +m[1], +m[2], m.length > 3 ? +m[3] : 1] : null; };
  const over = (f, b) => [0, 1, 2].map(i => f[i] * f[3] + b[i] * (1 - f[3]));

  /* Фон под элементом: вверх по предкам, пока не встретится непрозрачный. */
  function under(el) {
    const stack = [];
    for (let n = el; n; n = n.parentElement) {
      const c = rgba(getComputedStyle(n).backgroundColor);
      if (c && c[3] > 0) { stack.push(c); if (c[3] === 1) break; }
    }
    let bg = [255, 255, 255];
    for (let i = stack.length - 1; i >= 0; i--) bg = over(stack[i], bg);
    return bg;
  }

  const bad = [];
  for (const el of document.querySelectorAll('body *')) {
    if (el.closest('[aria-hidden="true"]')) continue;      /* оформление, не текст */
    const own = [...el.childNodes]
      .filter(n => n.nodeType === 3 && n.textContent.trim())
      .map(n => n.textContent.trim()).join(' ');
    if (!own) continue;
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    const s = getComputedStyle(el);
    if (s.visibility === 'hidden') continue;

    let alpha = 1;
    for (let n = el; n && n !== document.body; n = n.parentElement)
      alpha *= parseFloat(getComputedStyle(n).opacity);
    const fg = rgba(s.color); fg[3] *= alpha;
    const bg = under(el);
    const c = ratio(over(fg, bg), bg);

    const size = parseFloat(s.fontSize);
    const weight = parseInt(s.fontWeight, 10) || 400;
    /* Крупная надпись читается и на меньшем контрасте — это определение WCAG,
       а не поблажка себе: 24px или 18.66px жирным. */
    const large = size >= 24 || (size >= 18.66 && weight >= 700);
    const floor = (large || size < 14) ? floors.small : floors.main;
    if (c + 0.005 < floor)
      bad.push({ what: own.slice(0, 30), cls: (el.className || el.tagName).toString().slice(0, 26),
                 size, got: Math.round(c * 100) / 100, need: floor });
  }
  return bad;
}
"""


def contrast(page, where: str):
    """Померить контраст и сказать, где именно он просел."""
    bad = page.evaluate(CONTRAST, {"main": MAIN, "small": SMALL})
    want(not bad, f"контраст держит {MAIN}/{SMALL} — {where} (просевших: {len(bad)})"
         + ("" if not bad else " — " + "; ".join(
             f'{x["cls"]} {x["size"]}px «{x["what"]}» {x["got"]} < {x["need"]}'
             for x in bad[:5])))


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

    # ── ближайший срок отмены: в шапке, на первом экране, с обратным счётом
    #
    # Меряется браузером, а не разметкой, нарочно: разметка знает только дату,
    # а дни считаются на месте. «Осталось N дней», написанное сборкой, было бы
    # верным ровно сутки.
    head = page.locator(".deadlines > summary")
    want(head.count() == 1, "ближайший срок отмены в шапке один")
    lead = " ".join(head.inner_text().split())
    # 18 декабря 2026 — OMO5 Киото, ¥64 350. Дата прибита нарочно: если срок
    # в шапке вдруг станет не ближайшим, это должно краснеть, а не пройти.
    want("18 декабря 2026" in lead, f"ближайший срок — 18 декабря 2026: «{lead}»")
    want(head.bounding_box()["y"] < 220, "срок виден до первой прокрутки")
    days = re.search(r"осталось (\d+)", lead)
    want(days is not None, f"обратный счёт дописан браузером: «{lead}»")
    if days:
        real = (date(2026, 12, 18) - date.today()).days
        want(int(days.group(1)) == real,
             f"дни считаются от сегодня: на странице {days.group(1)}, по календарю {real}")
    want(not page.locator(".deadlines .rest").is_visible(),
         "остальные сроки лежат под стрелкой, пока её не открыли")
    head.click()
    page.wait_for_timeout(150)
    want(page.locator(".deadlines .rest li").count() == 4,
         f'по стрелке открылись остальные ({page.locator(".deadlines .rest li").count()})')
    head.click()
    page.wait_for_timeout(120)

    # ── переезды: чем и сколько ехать — в нитке, а не только пунктом то-до
    rides = page.locator(".thread .move.has")
    want(rides.count() == 3, f"переездов в нитке {rides.count()}")
    nine = " ".join(rides.first.inner_text().split())
    want("синкансэн" in nine, f"9 января назван поезд: «{nine}»")
    want("13 970" in nine.replace(" ", " ").replace(" ", " "),
         f"9 января стоит цена: «{nine}»")
    # 24 августа у экспресса появилась цена — но вилкой и со знаком ≈, а не
    # одним числом: путеводители дают ¥4 500–5 300, сервис JR «от ¥7 350», и
    # выдать одно за факт нельзя. Проверяем именно вилку: одно точное число
    # здесь означало бы, что мы выбрали удобное.
    kino = " ".join(rides.nth(1).inner_text().split())
    plain = kino.replace(" ", " ").replace(" ", " ")
    want("≈" in kino and "–" in kino and "5 000" in plain and "7 350" in plain,
         f"13 января: цена вилкой и помечена как оценка — «{kino}»")
    want(kino.count("¥") == 2,
         "вилка показана обеими границами, а не одной")
    # 15 января знаем половину: синкансэн есть, экспресс до Киото — нет. Одно
    # число без пустого поля рядом прочиталось бы как цена всего переезда.
    back = " ".join(rides.nth(2).inner_text().split())
    # С 24 августа неизвестного здесь нет: у экспресса появилась вилка. Рядом
    # стоят точное число синкансэна и оценка экспресса — и видно, что это
    # разные вещи (одно с ¥, другое с ≈).
    want("13 970" in back.replace(" ", " ").replace(" ", " ") and "≈" in back,
         f"15 января: известное и неизвестное стоят рядом — «{back}»")

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
    # ¥290 675 с 23 августа: новое подтверждение lyf Ginza (¥50 205 вместо
    # ¥57 442). Число прибито нарочно — тихая правка её денег обязана краснеть.
    want("$" in total and "¥290" in total.replace(" ", " ").replace(" ", " "),
         "итог показан в долларах и иенах")
    want("курс на" in total, "курс подписан датой")

    # ── ночь 14 → 15: со страницы ушла совсем
    #
    # Здесь до 24 августа проверялось обратное: что спокойная заметка стоит на
    # первом экране. Ни сняла это сама — «блок **как задумано** убивай, он
    # действует на нервы и мешается»: страница повторяла ей решённое при
    # каждом заходе. Проверка перевёрнута, а не удалена, потому что пропажа
    # блока обязана остаться решением, а не случайностью следующей правки.
    # Данные не тронуты: наложение по-прежнему помечено в `trip.json`, и
    # убрать его молча не даёт `check` (см. `test_data.py`).
    alert = page.locator("#overlap-14")
    want(alert.count() == 0, f"заметки «как задумано» на странице нет ({alert.count()})")
    body = page.inner_text("body").lower()
    want("как задумано" not in body, "и слов «как задумано» на странице нет")
    want("нужно решение" not in body and "требует решения" not in body,
         "ничего не требует решения")

    # ── пустые поля с подписью: ни одного выдуманного числа
    blanks = page.locator(".blank b").all_inner_texts()
    want(len(blanks) == 3, f"пустых полей с подписью {len(blanks)}: {', '.join(blanks)}")

    # ── подробности проживания: снаружи только то, что решает и стоит денег
    fine = page.locator(".city .stayfine")
    want(fine.count() == 4, f"стрелка «подробности» у каждого города ({fine.count()})")
    want(page.locator(".city .stayfine[open]").count() == 0,
         "все свёрнуты, пока их не открыли")
    # Разряды и даты разведены неразрывными пробелами — сравниваем по словам,
    # а не по тому, каким именно пробелом они разделены.
    outside = " ".join(page.locator(".city").first.inner_text().lower().split())
    # «$316» вместо «$362» — та же новая бронь lyf: 50 205 ¥ по курсу 158.88.
    for kept in ("5 — 9 января", "$316", "бесплатная отмена", "хочу сходить"):
        want(" ".join(kept.lower().split()) in outside, f'снаружи осталось «{kept}»')
    for hidden in ("Studio Single", "Kyobashi", "+81 3-3528-6505", "с 15:00"):
        want(" ".join(hidden.lower().split()) not in outside, f'под стрелку ушло «{hidden}»')

    # ── и открывается на месте, без перезагрузки
    was = page.evaluate("() => document.documentElement.scrollHeight")
    page.locator(".city .stayfine > summary").first.click()
    page.wait_for_timeout(120)
    opened = page.locator(".city").first.inner_text()
    want("Kyobashi" in opened, "по стрелке подробности появились")
    want(page.evaluate("() => document.documentElement.scrollHeight") > was,
         "страница раздвинулась на месте, а не уехала")

    # ── вносить своё: три кнопки видны, форма спрятана, пока её не позвали
    #
    # Спрятанность проверяется нажатием, а не чтением разметки: `hidden` —
    # атрибут, который любой наш `display` в CSS перебивает молча. Ровно так
    # форма однажды и стояла развёрнутой во весь экран, считаясь спрятанной,
    # и страница выросла на 292 точки.
    knobs = page.locator(".knobs .knob")
    want(knobs.count() == 3, f"кнопок «вносить своё» {knobs.count()}: место, бронь, то-до")
    want(not page.locator(".pane").is_visible(), "форма спрятана, пока её не позвали")

    page.locator('.knob[data-add="booking"]').click()
    page.wait_for_timeout(150)
    want(page.locator(".pane").is_visible(), "по кнопке форма открылась")
    want(not page.locator('.pane [data-only="place"]').is_visible(),
         "у брони не спрашивают город")
    want(page.locator('.pane [data-only="booking todo"]').is_visible(),
         "у брони спрашивают дату")
    page.locator(".pane [data-cancel]").click()
    page.wait_for_timeout(120)
    want(not page.locator(".pane").is_visible(), "«Отмена» закрывает форму обратно")

    # ── чек говорит ровно про то число, которое показывает
    #
    # Файл открыт с диска, хранилища рядом нет — и это как раз тот случай,
    # когда врать легче всего: показать жильё под заголовком «вся поездка».
    check = page.locator("#check")
    want("жильё" in check.inner_text(), "пока записей нет, чек назван жильём")
    want("вся поездка" not in check.inner_text(),
         "заголовок «вся поездка» не появляется раньше самих записей")
    want("не загрузились" in check.inner_text(),
         "страница говорит вслух, что её записей тут нет")

    # ── и вслух же — что этот итог неполный
    #
    # Крупное число само себя объявляет полной ценой поездки. Строка стоит
    # между суммой и разбивкой оплаты, то есть в одном взгляде с цифрой.
    notall = " ".join(page.locator(".notall").inner_text().split())
    want("не входит" in notall, f"под суммой сказано, чего в ней нет: «{notall}»")
    want(not re.search(r"\d", notall),
         f"чисел в этой строке нет — второй счёт разошёлся бы с первым: «{notall}»")
    for named in ("перелёт", "поезда", "чемодан", "еда", "метро", "сувениры"):
        want(named in notall.lower(), f'«{named}» назван среди того, чего в итоге нет')
    want(page.locator(".notall").bounding_box()["y"]
         < page.locator(".total .bar").bounding_box()["y"],
         "строка стоит вплотную к сумме, а не в подвале чека")

    # ── линейка: иены в доллары и обратно
    #
    # Считается здесь, а не в разметке, потому что тут и есть вся вещь: два
    # поля, которые заполняют друг друга. Курс прибит числом нарочно — тихая
    # правка курса обязана краснеть, а не пересчитать её деньги молча.
    RATE = 158.88
    ruler = page.locator(".convert")
    want(ruler.count() == 1 and ruler.is_visible(),
         "линейка на виду, а не под стрелкой")
    want("¥" in ruler.inner_text() and "$" in ruler.inner_text(),
         "у полей подписаны обе валюты")

    jpy, usd = page.locator('[data-conv="jpy"]'), page.locator('[data-conv="usd"]')
    jpy.fill("10 000")
    page.wait_for_timeout(60)
    want(usd.input_value().replace(" ", "") == str(round(10_000 / RATE)),
         f'¥10 000 → ${usd.input_value()} (по курсу {round(10_000 / RATE)})')
    usd.fill("100")
    page.wait_for_timeout(60)
    want(jpy.input_value().replace(" ", "") == str(round(100 * RATE)),
         f'$100 → ¥{jpy.input_value()} (по курсу {round(100 * RATE)})')
    # Пустое поле — не ноль: ноль на этой странице значит «бесплатно».
    usd.fill("")
    page.wait_for_timeout(60)
    want(jpy.input_value() == "", "стёрла у себя — стёрлось и напротив")
    jpy.fill("не число")
    page.wait_for_timeout(60)
    want(usd.input_value() == "", "из букв доллары не получаются")
    jpy.fill("")

    said = " ".join(page.locator(".convert .fx").inner_text().split())
    want(str(RATE) in said and "2026" in said, f"под полями курс с датой: «{said}»")
    want("иенах" in said and "округлен" in said,
         f"сказано, чем она платит и что доллар — мерка: «{said}»")

    # Место линейки: она встала в пустоту среднего столбца чека, и страница от
    # неё не выросла ни на точку. Правило сторожит именно это — вырастет
    # столбец выше левого, и высота уедет в потолок следом.
    col = page.locator(".ledger .col").bounding_box()["height"]
    left = page.locator(".total").bounding_box()["height"]
    want(col <= left,
         f"линейка живёт в пустоте среднего столбца ({col:.0f}px против {left:.0f}px)")

    # ── багаж: кто везёт, куда нажимать и почём — одним куском
    #
    # Ни 2026-08-24: «в трёх местах пишем про багаж и нигде не указываем сайт».
    fold = page.locator('details.more[data-fold="luggage"]')
    tag = " ".join(fold.locator("summary .tag").inner_text().split())
    want("Yamato" in tag and "¥" in tag,
         f"кто везёт и почём видно, не открывая: «{tag}»")
    fold.locator("summary").click()
    page.wait_for_timeout(150)
    who = " ".join(page.locator("#luggage .who").inner_text().split())
    want("TA-Q-BIN" in who, f"услуга названа: «{who[:60]}…»")
    want("стойке отеля" in who, "сказано, что заказывается на стойке, а не кнопкой")
    want("4 600" in who.replace(" ", " ").replace("\xa0", " "),
         "цена стоит там же")
    site = page.locator("#luggage .who a.btn.site")
    # Сначала счёт, потом всё остальное: у пустого места нет ни адреса, ни
    # размера, и спрашивать их — это тридцать секунд ожидания вместо «✗».
    want(site.count() == 1, f"ссылка на службу — рядом с ценой ({site.count()})")
    if site.count() == 1:
        want("kuronekoyamato" in site.get_attribute("href"),
             f'ведёт к службе: {site.get_attribute("href")}')
        want(site.bounding_box()["height"] >= 20, "по ссылке можно попасть")
    fold.locator("summary").click()
    page.wait_for_timeout(120)

    # ── дни: два столбца и одна кнопка на весь раздел
    #
    # Ни 2026-08-24: «сделай дни в два столбца» и «подпись к блоку и все
    # кнопки убивай, они только мусорность создают и место занимают».
    #
    # Столбцы меряются левым краем настоящих дней, а не чтением CSS: правило
    # `grid-template-columns` в файле и две колонки на экране — разные
    # утверждения, и спорить они умеют молча (перенос, ширина, вложенность).
    #
    # Ручек здесь нет и быть не может: страница открыта с диска, хранилище не
    # ответило. Что они спрятаны до наведения и достижимы с клавиатуры,
    # проверяется там, где они существуют, — `test/hands.py`.
    # Заголовок берётся прямым потомком: внутри раздела ещё двадцать одна
    # свёртка — города и дни, — и «любой summary внутри» тут значит «любой из
    # двадцати двух».
    days_head = page.locator('details.more[data-fold="days"] > summary')
    want(days_head.locator(".tag").count() == 0,
         "у свёртки дней подписи нет — «16 дней · 98 пунктов» убрано")
    days_head.click()
    page.wait_for_timeout(200)

    lefts = page.evaluate("""() => {
      const run = document.querySelectorAll('#days .run')[1];
      return [...run.querySelectorAll('.day')].map(d => Math.round(d.getBoundingClientRect().x));
    }""")
    want(len(set(lefts)) == 2, f"дни города стоят в два столбца (краёв: {sorted(set(lefts))})")

    knob = page.locator("[data-fold-all]")
    want(knob.count() == 1, "кнопка на весь раздел одна")
    want("развернуть" in knob.inner_text(), f"и говорит, что сделает: «{knob.inner_text()}»")
    knob.click()
    page.wait_for_timeout(250)
    want(page.locator("#days details.day[open]").count() == 16,
         "по кнопке раскрылись все шестнадцать дней")
    want("свернуть" in knob.inner_text(),
         f"и надпись переключилась: «{knob.inner_text()}»")
    # Развёрнутая сотня пунктов в два столбца — 5079 против 7035 в один.
    tall = page.evaluate("() => document.documentElement.scrollHeight")
    want(tall < 5600, f"раздел целиком укладывается в {tall}px (в один столбец было 7035)")
    knob.click()
    page.wait_for_timeout(250)
    want(page.locator("#days details.day[open]").count() == 0,
         "и та же кнопка свернула их обратно")
    days_head.click()
    page.wait_for_timeout(120)

    # ── справка внизу: виза, документы до вылета, такс-фри
    #
    # Её просьба 24 августа: «внизу мне нужна справочная информация по визе для
    # граждан грузии… как легко оформлять дьюти фри покупки». «Внизу» здесь
    # проверяется буквально — раздел стоит после чека, а не строчкой в то-до.
    ref = page.locator(".ref")
    want(ref.count() == 1 and ref.is_visible(), "справка на странице одна")
    want(ref.bounding_box()["y"] > page.locator(".ledger").bounding_box()["y"],
         "справка стоит внизу, ниже чека")

    # Виза — самый срочный срок на странице, и это должно быть видно, не
    # открывая ничего. Меряется не разметкой, а тем, что читается на экране:
    # `open` в разметке и видимый глазом текст — разные утверждения.
    visa = page.locator(".ref .visa")
    want(visa.is_visible(), "виза не под стрелкой")
    said = " ".join(visa.inner_text().split())
    want("самое срочное" in said.lower(), f"виза названа самым срочным: «{said[:40]}…»")
    for must in ("только очно", "4 января", "до новогодних каникул"):
        want(must in said, f'снаружи, не открывая, сказано «{must}»')
    # Соображение помечено как соображение и снаружи тоже: «вылет 4 января,
    # подавать до каникул» — наш вывод, а не правило посольства.
    want("наше соображение" in said.lower(),
         "мысль снаружи помечена как мысль, а не как правило")

    # Такс-фри: с 1 ноября 2026 система перевернулась, и человек, который помнит
    # старые правила, ничего открывать не станет — он же «знает, как это
    # работает». Поэтому переворот обязан стоять в строке, видной закрытой.
    # Сравнивается в нижнем регистре: заголовки свёрток нарисованы прописными
    # средствами CSS, и `inner_text()` отдаёт их уже такими. Сверять регистр
    # значило бы проверять `text-transform`, а не то, что там написано.
    tax = page.locator('[data-ref="taxfree"]')
    head = " ".join(tax.locator("summary").inner_text().split()).lower()
    want("наоборот" in head and "1 ноября 2026" in head,
         f"переворот такс-фри виден, не открывая: «{head}»")
    want("аэропорт" in head,
         f"и сказано, где теперь возвращают: «{head}»")

    # ── и главное: непроверенное не может выглядеть фактом
    #
    # Это ровно та ошибка, которой мы боимся, и сторожится она не чтением
    # разметки, а сверкой экрана с данными. Три пункта про визу взяты из
    # вторичных источников (сайт посольства Японии в Грузии отвечает нашему
    # серверу 403 на все страницы) — и если они однажды тихо станут обычными
    # строками, покраснеть должно здесь.
    data = json.loads((HERE / "data" / "reference.json").read_text(encoding="utf-8"))
    for block in data["blocks"]:
        box = page.locator(f'[data-ref="{block["id"]}"]')
        box.locator("summary").first.click()
        page.wait_for_timeout(150)
        for item in block["items"]:
            head = " ".join(item["text"].split())[:42]
            row = box.locator(".facts li", has_text=head)
            want(row.count() == 1, f'пункт на странице один: «{head}…» ({row.count()})')
            if row.count() != 1:
                continue
            cls = (row.get_attribute("class") or "").split()
            seen = " ".join(row.inner_text().split()).lower()
            if item.get("verified") is False:
                want("unsure" in cls and "не подтверждено" in seen,
                     f'непроверенное названо непроверенным: «{head}…» ({cls})')
                # Рядом с пометкой — что именно с этим делать. Сноской внизу
                # это читают уже после того, как поверили.
                want(" ".join(item["how"].split()).lower() in seen,
                     f'сказано, что спросить: «{head}…»')
            elif item.get("mine") is True:
                want("think" in cls and "наше соображение" in seen,
                     f'наша мысль помечена как наша: «{head}…» ({cls})')
            else:
                want("fact" in cls and "не подтверждено" not in seen,
                     f'подтверждённое стоит без пометки: «{head}…» ({cls})')
        box.locator("summary").first.click()
        page.wait_for_timeout(120)

    # Счёт непроверенного — в подписи свёртки: иначе «не подтверждено» увидит
    # только тот, кто открыл, а не пролистал.
    tag = " ".join(page.locator('[data-ref-tag="visa"]').inner_text().split()).lower()
    unsure = sum(1 for i in data["blocks"][0]["items"] if i.get("verified") is False)
    want(str(unsure) in tag and "подтвержден" in tag,
         f"сколько пунктов без подтверждения, видно закрытой свёрткой: «{tag}»")

    # Единственная ссылка справки — открыта руками 24 августа (200, английская
    # страница Visit Japan Web про прилёт и такс-фри).
    vjw = page.locator('.ref a.btn[href*="visit-japan-web"]')
    want(vjw.count() == 1, f"ссылка на Visit Japan Web одна ({vjw.count()})")
    if vjw.count() == 1:
        want(vjw.get_attribute("rel") == "noreferrer noopener"
             and vjw.get_attribute("target") == "_blank",
             "внешняя ссылка открывается отдельно и без доступа к нашей странице")

    # ── контраст: сначала как она увидит, потом со всем развёрнутым
    contrast(page, "1440, свёрнуто")
    page.evaluate("() => document.querySelectorAll('details').forEach(d => d.open = true)")
    page.wait_for_timeout(150)
    contrast(page, "1440, всё развёрнуто")
    page.evaluate("() => document.querySelectorAll('details').forEach(d => d.open = false)")

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
    small = phone.evaluate("""() => [...document.querySelectorAll(
        '.btn, .todo-group label, summary, .knob, .tiny, .ed, .rm, .save, .drop')]
        .filter(el => el.offsetParent !== null)
        .map(el => ({ t: (el.className || el.tagName).toString().slice(0, 20),
                      h: Math.round(el.getBoundingClientRect().height) }))
        .filter(x => x.h < 36)""")
    want(not small, f"по видимым целям можно попасть пальцем (мелких: {len(small)})"
         + (f" — {small[:3]}" if small else ""))

    # Переезд нужен в дороге больше всего — на телефоне он остаётся, хотя
    # числовая ось и стрелки «прилёт / домой» без неё прячутся.
    seen = phone.locator(".thread .move.has")
    want(seen.count() == 3 and seen.first.bounding_box() is not None,
         f"переезды видны и на телефоне ({seen.count()})")
    want(phone.locator(".thread .move:not(.has)").first.bounding_box() is None,
         "стрелка без переезда на телефоне спрятана")
    want("13 970" in " ".join(seen.first.inner_text().split())
         .replace(" ", " ").replace(" ", " "),
         "цена переезда доехала до телефона")

    # И свёрнутое действительно разворачивается: шестнадцать дней на месте.
    #
    # С 24 августа день — сам свёртка: Ни попросила тасовать пункты и
    # переносить их из дня в день, и сотня пунктов, вываленная разом, это та
    # самая простыня, про которую было «слишком много листать вниз».
    # Раскрытым приезжает отрезок города, свёрнутым — день.
    phone.locator('summary:text-is("По дням")').click()
    phone.wait_for_timeout(150)
    days = phone.locator("#days details.day")
    want(days.count() == 16 and days.first.bounding_box() is not None,
         f"«По дням» разворачивается, дней {days.count()}")

    # Пункты лежат внутри дня и открываются нажатием — а не стоят открытыми.
    # Меряется высотой, а не разметкой: `open` в разметке и видимый на экране
    # пункт — разные утверждения, и путать их мы уже научились на форме.
    first = phone.locator("#days details.day").first
    shown = phone.locator("#days .it").filter(visible=True)
    want(shown.count() <= 12,
         f"дни приезжают свёрнутыми, видно {shown.count()} пунктов из 98")
    first.locator("summary").click()
    phone.wait_for_timeout(150)
    want(first.locator(".it").first.bounding_box() is not None,
         "день открывается нажатием и показывает свои пункты")
    # Название ведёт на карту — это и есть её «ссылки на них нужны».
    #
    # С 24 августа строка, называющая несколько мест, разрезана: «Yasaka
    # Shrine, Maruyama Park, Chion-in» было одной ссылкой на три места и
    # открывалось на первом. Её слово: «залинковывай каждую локацию отдельно,
    # чтобы я не гадала, что же по ссылке откроется».
    #
    # 64 карты вместо прежних 54: 38 целых названий плюс 26 мест внутри
    # разрезанных строк. Ещё три места ведут на свой сайт (KUMONOCHA дважды и
    # AGE.3 — они проверены в `places`, карты у них нет), поэтому карт 64, а
    # ссылок в названиях 67. Числа прибиты нарочно: если они поедут, это либо
    # новые места в плане, либо ссылки, потерявшиеся молча.
    maps = phone.locator('#days a[href*="google.com/maps"]')
    want(maps.count() == 64, f"названия ведут на карту ({maps.count()})")
    links = phone.locator("#days .nm a, #days a.nm")
    want(links.count() == 67, f"всего ссылок в названиях {links.count()}")
    want(maps.first.get_attribute("rel") == "noopener"
         and maps.first.get_attribute("target") == "_blank",
         "внешние ссылки открываются отдельно и без доступа к нашей странице")
    # Каждое место — своей ссылкой, а не строка целиком одной.
    split = phone.locator("#days .nm[data-spots]")
    want(split.count() == 16, f"строк, разрезанных по местам, {split.count()}")
    three = phone.locator('#days [data-item="d12-7"] .nm a')
    want(three.count() == 3,
         f"«Yasaka Shrine, Maruyama Park, Chion-in» — три ссылки ({three.count()})")
    first.locator("summary").click()
    phone.wait_for_timeout(120)
    contrast(phone, "390")
    phone.screenshot(path=str(SHOTS / "japan-phone-new.png"), full_page=True)

    # ── страница светлая при любой настройке телефона.
    #
    # Это не перестраховка: тёмная тема тут была, включалась сама по настройке
    # устройства, и ровно её Ни и увидела словами «сложно читать». Проверять
    # это глазами бесполезно — на нашей машине светло всегда. Поэтому браузер
    # открывается с включённым тёмным режимом и меряется настоящий цвет фона.
    night = browser.new_page(viewport=DESK, color_scheme="dark")
    night.goto(PAGE.as_uri(), wait_until="load")
    night.wait_for_timeout(150)
    paint = night.evaluate("""() => {
      const s = getComputedStyle(document.body);
      return { bg: s.backgroundColor, ink: s.color,
               scheme: getComputedStyle(document.documentElement).colorScheme };
    }""")
    want(paint["bg"] == "rgb(242, 238, 231)",
         f'фон остаётся светлым при тёмной настройке устройства ({paint["bg"]})')
    want("light" in paint["scheme"],
         f'браузеру сказано рисовать светло ({paint["scheme"]})')
    contrast(night, "тёмная настройка устройства")
    browser.close()

for line in notes + problems:
    print(line)
print(f"\nкадры: {SHOTS}/japan-wide-top.png, japan-wide-full.png, japan-phone-new.png")
sys.exit(1 if problems else 0)
