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

import re
import sys
from datetime import date
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent.parent
PAGE = HERE / "dist" / "index.html"
SHOTS = HERE.parent / "shots"
DESK = {"width": 1440, "height": 900}
LIMIT = 1810
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
    maps = phone.locator('#days a.nm[href*="google.com/maps"]')
    # 54 из 98 — ровно те пункты, у которых в данных есть что искать на карте.
    # Остальные 44 это «обед», «выезд», «ужин и спать»: у них нет адреса, и
    # ссылка там была бы ссылкой в никуда. Число прибито нарочно: если оно
    # поедет, это либо новые места в плане, либо ссылки, потерявшиеся молча.
    want(maps.count() == 54, f"названия ведут на карту ({maps.count()} из 98)")
    want(maps.first.get_attribute("rel") == "noopener"
         and maps.first.get_attribute("target") == "_blank",
         "внешние ссылки открываются отдельно и без доступа к нашей странице")
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
