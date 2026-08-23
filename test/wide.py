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
подробности проживания уехали под стрелку (1604), 1780 сейчас (1736), когда
страница перестала быть только чтением: появились кнопки «вносить своё», раздел
«куплено отдельно» и разбивка чека.

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

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent.parent
PAGE = HERE / "dist" / "index.html"
SHOTS = HERE.parent / "shots"
DESK = {"width": 1440, "height": 900}
LIMIT = 1780
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

    # ── подробности проживания: снаружи только то, что решает и стоит денег
    fine = page.locator(".city .stayfine")
    want(fine.count() == 4, f"стрелка «подробности» у каждого города ({fine.count()})")
    want(page.locator(".city .stayfine[open]").count() == 0,
         "все свёрнуты, пока их не открыли")
    # Разряды и даты разведены неразрывными пробелами — сравниваем по словам,
    # а не по тому, каким именно пробелом они разделены.
    outside = " ".join(page.locator(".city").first.inner_text().lower().split())
    for kept in ("5 — 9 января", "$362", "бесплатная отмена", "хочу сходить"):
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

    # И свёрнутое действительно разворачивается: шестнадцать дней на месте.
    phone.locator('summary:text-is("По дням")').click()
    phone.wait_for_timeout(150)
    days = phone.locator("#days > ol.days > li")
    want(days.count() == 16 and days.first.bounding_box() is not None,
         f"«По дням» разворачивается, дней {days.count()}")
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
