#!/usr/bin/env python3
"""Собрать страницу Японии из data/trip.json.

    python3 build.py            # → dist/
    python3 build.py --check    # только проверки, ничего не пишет

Одна страница, всё внутри одного файла: в дороге телефон не должен ходить
за шрифтами и стилями по чужим адресам, а сроки отмены нужны и на плохой
связи. Функции двери копируются рядом — без них Pages выложит сайт нараспашку.

Числа на странице не пишутся руками ни в одном месте: суммы, ночи и
количество дней считаются здесь из броней. Расхождение между сложенным и
записанным — это ошибка сборки, а не мелочь: см. check().
"""

from __future__ import annotations

import html
import json
import re
import shutil
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data" / "trip.json"
SITE = HERE / "site"
DIST = HERE / "dist"

MONTHS = "января февраля марта апреля мая июня июля августа сентября октября ноября декабря".split()
WEEKDAYS = "пн вт ср чт пт сб вс".split()
WEEKDAYS_FULL = "понедельник вторник среда четверг пятница суббота воскресенье".split()

NBSP = " "
THIN = " "  # узкий неразрывный — разделитель разрядов


# ─────────────────────────────────────────── мелочи

def e(text) -> str:
    return html.escape(str(text), quote=True)


def d(iso: str) -> date:
    return date.fromisoformat(iso[:10])


def day_month(iso: str) -> str:
    x = d(iso)
    return f"{x.day}{NBSP}{MONTHS[x.month - 1]}"


def short(iso: str) -> str:
    x = d(iso)
    return f"{x.day}.{x.month:02d}"


def weekday(iso: str) -> str:
    return WEEKDAYS[d(iso).weekday()]


def plural(n: int, one: str, few: str, many: str) -> str:
    """Русское число словом: 1 бронь, 2 брони, 5 броней."""
    tens = abs(n) % 100
    unit = tens % 10
    if 10 < tens < 20:
        return many
    if 1 < unit < 5:
        return few
    return one if unit == 1 else many


def yen(amount: int) -> str:
    return "¥" + f"{amount:,}".replace(",", THIN)


# Курс живёт **одной константой в данных** (`data/trip.json`, ключ `fx`), а не
# размазан по разметке: обновить его должно быть одной правкой. Значение взято
# живым 23 августа 2026 (open.er-api.com), а не по памяти.
FX = {"usd_per_jpy": 158.88, "as_of": "2026-08-23"}   # запасное, если в данных нет


def fx_human_date() -> str:
    """«2026-08-23» → «23 августа 2026»: дату курса читает она, а не машина."""
    y, m, d = FX["as_of"].split("-")
    return f"{int(d)} {MONTHS[int(m) - 1]} {y}"


def load_fx(data) -> None:
    """Курс — из данных, а не из кода: одна правка в `trip.json` меняет всё."""
    block = (data or {}).get("fx") or {}
    if block.get("usd_per_jpy"):
        FX.update({"usd_per_jpy": block["usd_per_jpy"],
                   "as_of": block.get("as_of", FX["as_of"])})


def usd(amount: int) -> str:
    """Иены в доллары — как ориентир, а не как цена.

    Ни попросила 2026-08-23: «дублируй суммы в долларах тоже, йены пусть будут,
    но скорее справочно». Платит она в иенах, поэтому доллар округляется до
    целого и никогда не подаётся как точная сумма; дата курса стоит на странице
    рядом с итогом — без неё через месяц старая цифра читается как сегодняшняя.
    """
    return "$" + f"{round(amount / FX['usd_per_jpy']):,}".replace(",", THIN)


def money(amount: int) -> str:
    """Доллар крупно, иена рядом справочно — её порядок, не наш."""
    return (f'<b class="usd">{usd(amount)}</b>'
            f'<span class="jpy">{yen(amount)}</span>')


def maplink(address: str) -> str:
    from urllib.parse import quote
    return "https://www.google.com/maps/search/?api=1&query=" + quote(address)


def tellink(phone: str) -> str:
    return "tel:" + re.sub(r"[^\d+]", "", phone)


# ─────────────────────────────────────────── проверки

class Failed(Exception):
    pass


def check(trip: dict) -> list[str]:
    """Сверить то, что страница покажет, с тем, что в неё положено.

    Проверяется не оформление, а четыре вещи, в которых ошибка стоит денег:
    непрерывность дат, ночи против календаря, суммы против разбивки по оплате
    и то, что наложение 14-го никуда не делось.
    """
    said = []
    stays = sorted(trip["stays"], key=lambda s: (s["checkin"]["date"], s["checkout"]["date"]))

    # 1. Ночи в каждой броне совпадают с календарём.
    for s in stays:
        real = (d(s["checkout"]["date"]) - d(s["checkin"]["date"])).days
        if real != s["nights"]:
            raise Failed(f'{s["name"]}: записано {s["nights"]} ночей, по датам {real}')

    # 2. Каждая ночь поездки чем-то закрыта, и видно, где закрыта дважды.
    start, end = d(trip["trip"]["start"]), d(trip["trip"]["end"])
    nights = {}
    for s in stays:
        night = d(s["checkin"]["date"])
        while night < d(s["checkout"]["date"]):
            nights.setdefault(night, []).append(s)
            night += timedelta(days=1)

    # Ночь без отеля бывает законной — например, в самолёте. Но только та,
    # которую назвали вслух в `transit`: молча пропущенная ночь и ночь в
    # дороге в данных выглядят одинаково, а стоят по-разному.
    transit = {d(t["date"]): t for t in trip.get("transit", [])}
    for when, leg in transit.items():
        if not (start <= when < end):
            raise Failed(f'{when}: ночь в дороге вне поездки ({start} — {end})')
        if when in nights:
            raise Failed(
                f'{when}: «{leg["title"]}» помечена ночью в дороге, но на неё же '
                f'есть бронь — {nights[when][0]["name"]}'
            )

    night = start
    gaps, doubles = [], []
    while night < end:
        booked = nights.get(night, [])
        if not booked:
            if night not in transit:
                gaps.append(night)
        elif len(booked) > 1:
            doubles.append((night, booked))
        night += timedelta(days=1)

    if gaps:
        raise Failed("ночи без крыши: " + ", ".join(x.isoformat() for x in gaps))
    if transit:
        said.append(
            "ночей в дороге: "
            + ", ".join(f'{w.isoformat()} — {t["title"].lower()}' for w, t in sorted(transit.items()))
        )

    # 3. Наложение должно быть ровно то, о котором предупреждает страница,
    #    и оно обязано быть заявлено в alerts — иначе оно тихо исчезнет.
    flagged = {a["id"] for a in trip.get("alerts", [])}
    for night_at, booked in doubles:
        ids = {s.get("conflict") for s in booked} - {None}
        if not ids or not (ids & flagged):
            raise Failed(f"{night_at}: две брони на одну ночь, и ни одна не помечена в alerts")
        said.append(f'ночь {night_at.isoformat()} двойная — {", ".join(s["name"] for s in booked)}')
    # И обратное: блок про наложение, под которым наложения уже нет, — тоже
    # ошибка. Тон («calm» или «red») тут не при чём: устаревшая заметка врёт
    # ровно так же, как устаревшая тревога.
    live = {s.get("conflict") for _night, booked in doubles for s in booked} - {None}
    for a in trip.get("alerts", []):
        if a["id"].startswith("overlap") and a["id"] not in live:
            raise Failed(f'{a["id"]}: блок про наложение есть, а наложения в бронях нет')

    # 4. Деньги: сумма всех броней = уже списано + спишется + оплата на месте.
    total = sum(s["total_jpy"] for s in stays)
    paid = sum(s["payment"].get("paid_jpy", 0) for s in stays)
    upcoming = sum(s["payment"].get("upcoming_jpy", 0) for s in stays)
    at_property = sum(
        s["total_jpy"] for s in stays if s["payment"]["mode"] == "at_property"
    )
    if paid + upcoming + at_property != total:
        raise Failed(
            f"разбивка не сходится: {paid} + {upcoming} + {at_property} "
            f"= {paid + upcoming + at_property}, а всего {total}"
        )
    for s in stays:
        if s["payment"]["mode"] == "prepaid":
            part = s["payment"]["paid_jpy"] + s["payment"]["upcoming_jpy"]
            if part != s["total_jpy"]:
                raise Failed(f'{s["name"]}: {part} по частям против {s["total_jpy"]} всего')
    said.append(f"суммы сходятся: {yen(total)} = {yen(paid)} + {yen(upcoming)} + {yen(at_property)}")

    # 5. Сроки отмены — разбираемые даты, и ни один не в прошлом относительно
    #    сборки без пометки. Молча просроченный срок — худший вид молчания.
    today = date.today()
    for s in stays:
        cutoff = datetime.fromisoformat(s["cancel"]["free_until"])
        if cutoff.date() < today:
            said.append(f'⚠ {s["name"]}: бесплатная отмена уже прошла ({cutoff.date()})')
    # Ближайший срок называется вслух при каждой сборке: он стоит в шапке
    # страницы, и если шапка вдруг покажет не тот — это будет видно здесь же.
    soonest = min(stays, key=lambda s: s["cancel"]["free_until"])
    said.append(f'ближайший срок отмены: {soonest["cancel"]["free_until"][:10]} — '
                f'{soonest["name"]}, {yen(soonest["total_jpy"])}')

    # 6. Место из вишлиста висит на брони. Опечатка в «stay» — это место,
    #    которое молча не покажется: страница соберётся, а его на ней не будет.
    known = {s["id"] for s in stays}
    for p in trip.get("places", []):
        if p["stay"] not in known:
            raise Failed(f'место «{p["title"]}» висит на броне {p["stay"]!r}, а такой нет')
    if trip.get("places"):
        said.append(f'мест из вишлиста: {len(trip["places"])}')

    # 7. Переезд стоит на дне настоящего переезда и называет настоящие города.
    #    Дата мимо — переезд, который тихо не покажется в нитке (та же беда,
    #    что у правила №6). Города мимо — подпись, которая врёт рядом с верной
    #    картинкой, а это хуже, чем её отсутствие.
    hops = {}
    chain = legs(stays)
    for i, leg in enumerate(chain[1:], 1):
        hops[leg["sleep_from"].isoformat()] = (chain[i - 1]["city"], leg["city"])
    for t in trip.get("transfers", []):
        pair = hops.get(t["date"])
        if not pair:
            raise Failed(f'переезд {t["date"]}: в этот день по броням никто никуда не едет')
        if (t["from"], t["to"]) != pair:
            raise Failed(f'переезд {t["date"]}: записано {t["from"]} → {t["to"]}, '
                         f'а по броням {pair[0]} → {pair[1]}')
        said.append(f'переезд {t["date"]}: {t["from"]} → {t["to"]}, '
                    + (yen(t["jpy"]) if t.get("jpy") else "цены нет"))

    # 8. В строке «чего нет в итоге» чисел быть не должно. Число здесь — второй
    #    счёт рядом с первым, и разойтись они успеют молча.
    for x in trip.get("not_in_total", []):
        if re.search(r"\d", x):
            raise Failed(f'«{x}» в списке «чего нет в итоге»: числам там не место')

    # 9. Никаких секретов в данных. Ключи с подчёркивания — записки самому
    #    себе о том, чего сюда класть нельзя; они перечисляют запретные слова
    #    и поэтому в досмотр не идут, иначе инструкция запрещала бы сама себя.
    blob = json.dumps(
        {k: v for k, v in trip.items() if not k.startswith("_")}, ensure_ascii=False
    )
    for pattern, what in (
        (r"\b[\w.+-]+@[\w-]+\.[\w.]+\b", "почта"),
        (r"\b(?:\d[ -]?){13,19}\b", "похоже на номер карты"),
        (r"(?i)\b(pin|пин|password|пароль|booking\s*(no|number)|номер\s*брони)\b", "слово про доступ"),
    ):
        hit = re.search(pattern, blob)
        if hit:
            raise Failed(f"в данных {what}: {hit.group(0)!r} — это не должно попасть в git")

    said.append(f"броней {len(stays)}, ночей {len(nights)}, дней {(end - start).days + 1}")
    return said


# ─────────────────────────────────────────── цвета и отрезки

# Цвет — единственное, что здесь не из данных: индиго Гиндзы, хурма Киото,
# сосна Киносаки, глициния Асакусы. Новый город получит цвет из запаса, а не
# исчезнет с картинки.
#
# На каждом из них лежит белый текст — название города в шапке карточки и
# «4 ночи» в нитке, — поэтому тон подобран не на глаз: белое на нём держит
# 7:1. Хурма и сосна ради этого стали темнее прежнего (было 5.2 и 6.1).
TONES = {
    ("Токио", "Гиндза"): "#2F4B7C",     # 8.7:1
    ("Киото", "Сандзё"): "#904222",     # 7.0:1
    ("Киносаки", "онсэн"): "#35614F",   # 7.1:1
    ("Токио", "Асакуса"): "#6A4A7E",    # 7.3:1
}
SPARE = ["#2F4B7C", "#904222", "#35614F", "#6A4A7E", "#6E5326"]


def legs(stays: list) -> list:
    """Города поездки: соседние брони в одном месте — один отрезок.

    Две ночи в Киносаки куплены двумя бронями подряд. Для неё это один город и
    одна цена — поэтому в нитке и в карточке они слиты. Но сроки бесплатной
    отмены у этих броней **разные**, и вот это слить нельзя: каждая бронь
    остаётся внутри карточки отдельной строкой со своим сроком.

    Оплаченное и прожитое — тоже разные вещи: OMO3 оплачен с 14-го, а спит она
    там с 15-го. Отрезок рисуется по прожитому, оплаченное показано полосой.
    """
    out = []
    for s in stays:
        arrive = d(s["arriving"]["date"]) if s.get("arriving") else d(s["checkin"]["date"])
        same = (
            out
            and out[-1]["city"] == s["city"]
            and out[-1]["area"] == s["area"]
            and out[-1]["paid_to"] == d(s["checkin"]["date"])
        )
        if same:
            leg = out[-1]
            leg["stays"].append(s)
            leg["paid_to"] = d(s["checkout"]["date"])
            leg["jpy"] += s["total_jpy"]
        else:
            out.append({
                "city": s["city"], "area": s["area"],
                "paid_from": d(s["checkin"]["date"]),
                "paid_to": d(s["checkout"]["date"]),
                "sleep_from": arrive,
                "stays": [s], "jpy": s["total_jpy"],
            })

    for i, leg in enumerate(out):
        first, last = leg["stays"][0], leg["stays"][-1]
        leg["tone"] = TONES.get((leg["city"], leg["area"]), SPARE[i % len(SPARE)])
        leg["nights"] = (leg["paid_to"] - leg["sleep_from"]).days
        leg["paid_nights"] = (leg["paid_to"] - leg["paid_from"]).days
        leg["hotel"] = first["name"]
        leg["room"] = first["room"]
        leg["meals"] = first["meals"]
        leg["checkin"] = first["checkin"]["time"]
        leg["checkout"] = last["checkout"]["time"]
        leg["address"] = first["address"]
        leg["phone"] = first["phone"]
        leg["site"] = first.get("site")
    return out


def span_dates(a: date, b: date) -> str:
    """«5 — 9 января»: месяц называется один раз, если он один."""
    if a.month == b.month:
        return f"{a.day}{NBSP}—{NBSP}{b.day} {MONTHS[a.month - 1]}"
    return f"{a.day} {MONTHS[a.month - 1]} — {b.day} {MONTHS[b.month - 1]}"


# ─────────────────────────────────────────── куски страницы

def deadlines(stays: list) -> str:
    """Сроки бесплатной отмены — наверху, а не по одному внутри карточек.

    Это самые дорогие даты на странице: после них деньги не возвращают вовсе.
    Лежали они по карточкам городов, и вечером 23 августа половина карточки
    уехала под стрелку «подробности проживания» — сроки снаружи остались, но
    ответ на вопрос «что горит ближайшим» по-прежнему приходилось собирать,
    сравнивая четыре даты в четырёх разных местах.

    Ближайший стоит в шапке, остальные — под стрелкой. Место выбрано не только
    по важности: правый столбец шапки ниже заголовка, и строка встаёт в уже
    существующую пустоту, не удлиняя страницу. Потолок в два экрана — её слово,
    и новое важное не должно за него платить.

    Дни считает браузер (`data-deadline`, см. JS), а не сборка: «осталось 116
    дней» замерзает в момент сборки, а страница живёт неделями. В разметку
    уезжает только дата — она не стареет. Без JS страница показывает дату и
    молчит про остаток; молчание тут честно, а замороженное число — нет.

    Порядок — по дате, и это проверяется в check(): ближайшим обязан быть
    ближайший. Если он всё-таки успел пройти между сборкой и чтением, браузер
    гасит его и раскрывает список сам, чтобы живые сроки не оказались спрятаны
    за мёртвым.
    """
    order = sorted(stays, key=lambda s: s["cancel"]["free_until"])
    if not order:
        return ""

    def who(s: dict) -> str:
        return s.get("label") or f'{s["city"]} · {s["area"]}'

    def when(s: dict) -> str:
        iso = s["cancel"]["free_until"]
        return f'{day_month(iso)} {d(iso).year}'

    first, rest = order[0], order[1:]
    tail = "".join(
        f'<li data-deadline="{e(s["cancel"]["free_until"])}">'
        f'<b class="till">{when(s)}</b>'
        f'<span class="who">{e(who(s))}</span>'
        f'<span class="cost">{money(s["total_jpy"])}</span></li>'
        for s in rest
    )
    opens = (f'<span class="opens">ещё {len(rest)} '
             f'{plural(len(rest), "срок", "срока", "сроков")}</span>' if rest else "")

    return f"""
<details class="deadlines">
  <summary>
    <span class="cap">вернут деньги, если отменить до</span>
    <span class="one" data-deadline="{e(first["cancel"]["free_until"])}">
      <b class="till">{when(first)}</b>
      <span class="who">{e(who(first))}</span>
      <span class="cost">{money(first["total_jpy"])}</span>
    </span>{opens}
  </summary>
  <ol class="rest">{tail}</ol>
</details>"""


def masthead(trip: dict, stays: list, all_legs: list) -> str:
    t = trip["trip"]
    start, end = d(t["start"]), d(t["end"])
    days = (end - start).days + 1
    nights = sum(s["nights"] for s in stays)
    moves = len(all_legs)   # прилёт + переезды между городами

    return f"""
<header class="masthead">
  <div class="title">
    <p class="eyebrow">поездка</p>
    <h1>{e(t["title"])} <span class="year">{e(t["year"])}</span></h1>
  </div>
  <div class="side">
    <p class="when">
      <b>{e(t["subtitle"])} {e(t["year"])}</b>
      <span>{days} {plural(days, "день", "дня", "дней")}</span>
      <span>{nights} оплаченных {plural(nights, "ночь", "ночи", "ночей")}</span>
      <span>{moves} {plural(moves, "переезд", "переезда", "переездов")}</span>
    </p>
    {deadlines(stays)}
  </div>
</header>"""


def thread(trip: dict, all_legs: list) -> str:
    """Нитка: вся поездка одной линией, ширина отрезка — это ночи.

    Сетка — по ночам поездки: столбец на каждую ночь плюс последний, узкий,
    на день отъезда. Поэтому ничего не надо считать в пикселях: четыре ночи
    ровно вдвое шире двух, потому что занимают вдвое больше столбцов.
    """
    start, end = d(trip["trip"]["start"]), d(trip["trip"]["end"])
    total = (end - start).days          # ночей в поездке
    transit = trip.get("transit", [])

    def col(day: date, n: int = 1) -> str:
        return f"grid-column:{(day - start).days + 1}/span {n}"

    caps, bars = [], []
    for leg in transit:
        when = d(leg["date"])
        # «ночь в самолёте, отель не нужен» → подпись «ночь / в самолёте»:
        # слово «ночь» уже стоит заголовком, второй раз оно только мешает.
        where = leg["detail"].split(",")[0].removeprefix("ночь ")
        caps.append(
            f'<div class="cap" style="{col(when)}">'
            f'<span class="area">ночь</span>'
            f'<span class="hotel quiet">{e(where)}</span>'
            f'<span class="stem"></span></div>'
        )
        bars.append(
            f'<div class="bar air" style="{col(when)}"><span class="n">{e(leg["title"].lower())}</span></div>'
        )

    for leg in all_legs:
        n = leg["nights"]
        caps.append(
            f'<div class="cap" style="{col(leg["sleep_from"], n)}">'
            f'<span class="town">{e(leg["city"])}</span>'
            f'<span class="area">{e(leg["area"])}</span>'
            f'<span class="hotel">{e(leg["hotel"])}</span>'
            f'<span class="stem"></span></div>'
        )
        # На узком отрезке две метки времени слипаются — выезд там живёт
        # в карточке города, а не в нитке.
        checkout = (f'<span class="edge o">{e(leg["checkout"])}</span>' if n >= 3 else "")
        bars.append(
            f'<div class="bar" style="{col(leg["sleep_from"], n)};background:{leg["tone"]}">'
            f'<span class="edge i">{e(leg["checkin"].replace(" — ", "–"))}</span>{checkout}'
            f'<span class="who">{e(leg["city"])} · {e(leg["area"])}</span>'
            f'<span class="n">{n} {plural(n, "ночь", "ночи", "ночей")}</span></div>'
        )

    bars.append(
        f'<div class="home" style="grid-column:{total + 1}">'
        f'<b>{end.day}</b><span>домой</span></div>'
    )

    # Полоса «оплачено шире, чем прожито». Рисуется только там, где эти два
    # числа разошлись, и говорит словами из данных, а не из головы.
    paid = []
    for leg in all_legs:
        if leg["paid_from"] >= leg["sleep_from"]:
            continue
        why = leg["stays"][-1].get("arriving", {}).get("why", "")
        # Цвет тона идёт в `color`, а не в `background`: полоса рисуется косой
        # штриховкой по currentColor и обведена рамкой. Так «оплачено, но не
        # прожито» отличается от прожитого фактурой, а не оттенком — на плохом
        # экране оттенок первым и пропадает.
        paid.append(
            f'<div class="paidbar" style="{col(leg["paid_from"], leg["paid_nights"])};'
            f'color:{leg["tone"]}"><span>оплачено с {day_month(leg["paid_from"].isoformat())}'
            f'{f" · {e(why)}" if why else ""}</span></div>'
        )

    days = []
    for i in range(total + 1):
        day = start + timedelta(days=i)
        weekend = " we" if day.weekday() >= 5 else ""
        days.append(
            f'<div class="day{weekend}"><b>{day.day}</b>'
            f'<span>{WEEKDAYS[day.weekday()]}</span></div>'
        )

    # Переезды: между отрезками, из самих отрезков — отдельного списка,
    # который может разъехаться с бронями, для этого не заводим. Подпись тянется
    # до следующего переезда: иначе соседние наезжают друг на друга, сетка
    # разводит их по строкам, и тонкая полоса раздувается втрое.
    marks = [(leg["sleep_from"],
              f'прилёт в {leg["city"]}' if i == 0 else f'{all_legs[i - 1]["city"]} → {leg["city"]}')
             for i, leg in enumerate(all_legs)]
    marks.append((end, "домой"))

    # Чем именно едет переезд — из `transfers`, по дате. Раньше поезда лежали
    # только пунктами то-до: то-до говорит «купить билет», а нитка обязана
    # говорить «чем и сколько ехать» — иначе между двумя городами на картинке
    # пустота, а в ней два с половиной часа и четырнадцать тысяч иен.
    #
    # Цены нет — рисуется пустое поле с подписью, а не прочерк и не
    # правдоподобное число: экспресс до Киносаки мы не подтверждали.
    rides = {t["date"]: t for t in trip.get("transfers", [])}
    moves = []
    for i, (when, text) in enumerate(marks):
        room = ((marks[i + 1][0] - when).days if i + 1 < len(marks)
                else total + 1 - (when - start).days)
        ride = rides.get(when.isoformat())
        detail = ""
        if ride:
            # Цена и дыра в цене — рядом, а не вместо друг друга. 15 января мы
            # знаем синкансэн и не знаем экспресс до Киото: одно число без
            # пустого поля рядом прочиталось бы как цена всего переезда.
            money_bits = ""
            if ride.get("jpy"):
                money_bits += f'<span class="cost">{yen(ride["jpy"])}</span>'
                if ride.get("covers"):
                    money_bits += f'<span class="covers">{e(ride["covers"])}</span>'
            # Вилка вместо пустоты, если она у нас есть. 24 августа Ни
            # спросила «а посмотреть не можете что ли?» про цену экспресса до
            # Киносаки — посмотрел: источники расходятся (¥4 500–5 300 у
            # путеводителей против «от ¥7 350» у сервиса JR), и выдать одно
            # число за факт нельзя. Вилка честнее и пустоты, и выдумки, но
            # подписана «оценка», чтобы не читалась как цена билета.
            if ride.get("estimate_jpy") and not ride.get("jpy"):
                low, high = ride["estimate_jpy"]
                money_bits += (f'<span class="cost guess">≈{yen(low)}–{yen(high)}</span>')
            elif not ride.get("jpy") or ride.get("nocost"):
                money_bits += (f'<span class="cost none"><span class="slot"></span>'
                               f'{e(ride.get("nocost", "цена"))}</span>')
            elif ride.get("estimate_jpy"):
                low, high = ride["estimate_jpy"]
                money_bits += (f'<span class="cost guess">≈{yen(low)}–{yen(high)}</span>')
            detail = (f'<span class="ride"><span class="how">{e(ride["how"])}</span>'
                      f'<span class="hrs">{e(ride["hours"])}</span>{money_bits}</span>')
        moves.append(
            f'<div class="move{" has" if ride else ""}" style="{col(when, max(room, 1))}">'
            f'<span class="hd"><i></i><span class="dt">{day_month(when.isoformat())}</span>'
            f'{e(text)}</span>{detail}</div>'
        )

    return f"""
<section class="thread" aria-label="вся поездка одной линией">
  <div class="row caps">{"".join(caps)}</div>
  <div class="row bars">{"".join(bars)}</div>
  <div class="row paidrow">{"".join(paid)}</div>
  <div class="row dates">{"".join(days)}</div>
  <div class="row moves">{"".join(moves)}</div>
</section>"""


def alert_block(alerts: list) -> str:
    """Ночь, на которой сошлись две брони.

    Тон задаёт `level`. «red» — вопрос, на который она ещё не ответила: сирена
    и варианты. «calm» — она ответила, и тогда всё это превращается в
    подгоняние по решённому. Что не меняется от тона: блок есть, ночь названа,
    обе брони живы. Убрать его можно только вместе с наложением в данных —
    иначе сборка не пройдёт (см. check).
    """
    if not alerts:
        return ""
    out = []
    for a in alerts:
        red = a["level"] == "red"
        facts = "".join(f"<li>{e(x)}</li>" for x in a.get("facts", []))
        options = "".join(
            f"""<li class="opt"><h4>{e(o["title"])}</h4><p>{e(o["detail"])}</p>
                <p class="watch" data-deadline="{e(o.get("deadline", ""))}">{e(o["watch"])}</p></li>"""
            for o in a.get("options", [])
        )
        out.append(f"""
<section class="alert {e(a["level"])}" id="{e(a["id"])}">
  <div class="says">
    <p class="siren">{"нужно решение" if red else "как задумано"}</p>
    <h2>{e(a["title"])}</h2>
    <p class="lead">{e(a["lead"])}</p>
  </div>
  <ul class="facts">{facts}</ul>
  {f'<ol class="options">{options}</ol>' if options else ''}
  <p class="closing">{e(a["closing"])}</p>
</section>""")
    return "".join(out)


def places_block(leg: dict, places: list) -> str:
    """Куда она хочет сходить в этом городе.

    Два источника, один список. Записанное в `trip.json` приезжает сюда при
    сборке; то, что Ни вписала сама прямо на странице, приезжает из хранилища
    уже в браузере и ложится в `ul.mine` — поэтому мешок под её места стоит
    здесь всегда, даже когда он пуст.

    Разница между ними одна и она честная: у её записи может быть цена, и
    тогда эта цена идёт в общий чек. Места из файла цены не имеют вовсе —
    это желания, за которые ещё никто не платил.

    Список будет расти: первые четыре из файла видны всегда, остальные под
    строкой, чтобы десятое место не растянуло карточку на второй экран.
    """
    mine = [p for p in places if p["stay"] in {s["id"] for s in leg["stays"]}]
    home = leg["stays"][0]["id"]
    head = '<p class="wish-cap">хочу сходить <span>· желания, не бронь</span></p>'
    add = (f'<button type="button" class="tiny" data-add="place" data-stay="{e(home)}">'
           f'+ место</button>')
    # Пустой мешок и подпись «пусто» — разные вещи: подпись прячется, как
    # только в мешок что-то легло, а сам мешок остаётся на месте всегда.
    tail = (f'<ul class="mine" data-mine="{e(home)}"></ul>'
            f'<p class="none" data-none{" hidden" if mine else ""}>пока пусто — нажми '
            f'«+ место», чтобы записать сюда своё</p>{add}')

    def one(p):
        where = f'<span class="where">{e(p["where"])}</span>' if p.get("where") else ""
        # Название становится ссылкой, когда сайт места проверен открытием.
        # 24 августа Ни попросила ссылки: при планировании открывают именно их,
        # а адрес с телефоном нужны уже на месте. Ссылки нет — остаётся текст,
        # выдуманного адреса тут не появится.
        title = (f'<a href="{e(p["site"])}" target="_blank" rel="noreferrer noopener">'
                 f'{e(p["title"])}</a>') if p.get("site") else e(p["title"])
        return (f'<li><b>{title}</b>{where}'
                f'<span class="what">{e(p["what"])}</span></li>')

    if not mine:
        return f'<div class="wishes empty" data-city="{e(home)}">{head}{tail}</div>'

    shown = "".join(one(p) for p in mine[:4])
    rest = mine[4:]
    more = ""
    if rest:
        more = (f'<details class="wish-more"><summary>ещё {len(rest)} '
                f'{plural(len(rest), "место", "места", "мест")}</summary>'
                f'<ul>{"".join(one(p) for p in rest)}</ul></details>')
    return (f'<div class="wishes" data-city="{e(home)}">{head}<ul>{shown}</ul>'
            f'{more}{tail}</div>')


def stay_fine(leg: dict, extras: str, notes: str) -> str:
    """Подробности проживания — под стрелкой, одной штукой на карточку.

    Её слово 2026-08-23: «а подробности о проживании давайте сворачивать под
    стрелку». Снаружи остаётся то, что решает и стоит денег: город, даты, цена
    и срок бесплатной отмены. Комната, еда, часы, адрес и телефон — внутри.

    Прежние «ещё про отель» слиты сюда же: две стрелки подряд в одной карточке
    — это не выбор, а лишнее нажатие, и вторая всё равно про то же самое.

    Заголовок перечисляет, что внутри. Свёрнутое без подписи — это вопрос
    «а надо ли туда лезть», который приходится решать нажатием.
    """
    hint = "комната · еда · часы · адрес"
    if extras:
        hint += " · доплаты"
    return f"""
<details class="stayfine">
  <summary><span class="lbl">подробности проживания</span><span class="hint">{hint}</span></summary>
  <dl class="rows">
    <div><dt>комната</dt><dd>{e(leg["room"])}</dd></div>
    <div><dt>еда</dt><dd>{e(leg["meals"])}</dd></div>
    <div><dt>заезд</dt><dd class="num">{e(leg["checkin"])}</dd></div>
    <div><dt>выезд</dt><dd class="num">{e(leg["checkout"])}</dd></div>
    <div><dt>адрес</dt><dd>
      <a class="btn" href="{e(maplink(leg["address"]))}" target="_blank" rel="noreferrer noopener">{e(leg["address"])}</a>
      <a class="btn tel" href="{e(tellink(leg["phone"]))}">{e(leg["phone"])}</a>
      {f'<a class="btn site" href="{e(leg["site"])}" target="_blank" rel="noreferrer noopener">сайт отеля</a>' if leg.get("site") else ""}</dd></div>
  </dl>
  {f'<ul class="extras">{extras}</ul>' if extras else ''}
  {f'<ul class="fine">{notes}</ul>' if notes else ''}
</details>"""


def city_cards(all_legs: list, alerts: list, places: list, cancelled: list) -> str:
    """Карточка на город: всё, что превращается в деньги и в опоздания."""
    flagged = {a["id"]: a["level"] for a in alerts}
    cards = []

    for leg in all_legs:
        many = len(leg["stays"]) > 1
        brons = []
        for s in leg["stays"]:
            tone = flagged.get(s.get("conflict"))
            klass = "stay clash" if tone == "red" else "stay noted" if tone else "stay"
            label = (f'<p class="blabel">{e(s.get("label") or s["name"])}</p>'
                     if many and s.get("label") else "")
            arriving = ""
            if s.get("arriving"):
                arriving = (
                    f'<p class="arriving"><b>приезжаешь {day_month(s["arriving"]["date"])}</b>'
                    f'<span>{e(s["arriving"]["why"])} · ночь {short(s["checkin"]["date"])} '
                    f'оплачена и остаётся пустой</span></p>'
                )
            brons.append(f"""
<div class="{klass}" id="{e(s["id"])}">
  {label}
  {arriving}
  <p class="cancel" data-deadline="{e(s["cancel"]["free_until"])}">
    <span class="k">бесплатная отмена</span>
    <b>до {day_month(s["cancel"]["free_until"])} {d(s["cancel"]["free_until"]).year}, {e(s["cancel"]["free_until"][11:16])} JST</b>
    <span class="t">{e(s["cancel"]["note"])}</span>
  </p>
</div>""")

        pay = leg["stays"][0]["payment"]
        if pay["mode"] == "prepaid":
            how = (f'<span class="paid">списано {yen(pay["paid_jpy"])}</span>'
                   f'<span class="due">спишется {yen(pay["upcoming_jpy"])}</span>')
        else:
            how = '<span class="onsite">оплата на месте</span>'
        if many:
            how += (f'<span class="plain">{len(leg["stays"])} брони по '
                    f'{yen(leg["stays"][0]["total_jpy"])}</span>')

        # Налог на источники записан в обеих ночёвках Киносаки — в карточке
        # города он один и тот же и повторяться не должен.
        extras = "".join(f"<li>{e(x)}</li>" for x in dict.fromkeys(
            x for s in leg["stays"] for x in s.get("extras", [])))
        notes = "".join(f"<li>{e(x)}</li>" for s in leg["stays"] for x in s.get("notes", []))

        cards.append(f"""
<article class="city">
  <div class="cap" style="background:{leg["tone"]}">
    <p class="name">{e(leg["city"])}</p>
    <p class="area">{e(leg["area"])}</p>
  </div>
  <div class="inner">
    <p class="hotel">{e(leg["hotel"])}</p>
    <p class="span">{span_dates(leg["sleep_from"], leg["paid_to"])}
       <span>{leg["nights"]} {plural(leg["nights"], "ночь", "ночи", "ночей")}</span></p>
    <p class="price">{money(leg["jpy"])}<span class="how">{how}</span></p>

    {"".join(brons)}
    {stay_fine(leg, extras, notes)}
    {places_block(leg, places)}
  </div>
</article>""")

    gone = ""
    if cancelled:
        items = "".join(
            f'<li><b>{e(c["name"])}</b> — {money(c["total_jpy"])} <span>{e(c["note"])}</span></li>'
            for c in cancelled
        )
        gone = f'<ul class="cancelled">{items}</ul>'

    return f'<section class="cities">{"".join(cards)}</section>{gone}'


def adder(trip: dict, all_legs: list) -> str:
    """Три кнопки и одна форма — всё, чем Ни правит эту страницу.

    Одна форма на три вида записи, а не три формы: поля у них общие на
    четыре пятых (что это, подробность, цена, как с деньгами), и три почти
    одинаковых бланка рядом — это выбор, который приходится делать глазами
    каждый раз.

    Форма стоит здесь, между городами и деньгами, потому что отсюда видно
    оба берега: место уедет наверх в карточку города, бронь и пункт списка —
    вниз, в свои разделы, и чек под ней сойдётся на глазах.
    """
    cities = "".join(
        f'<option value="{e(leg["stays"][0]["id"])}">{e(leg["city"])} · {e(leg["area"])}'
        f' — {span_dates(leg["sleep_from"], leg["paid_to"])}</option>'
        for leg in all_legs
    )
    groups = "".join(
        f'<option value="{e(g["group"])}">{e(g["group"])}</option>' for g in trip["todo"]
    ) + '<option value="Ещё">Ещё</option>'

    return f"""
<section class="adder">
  <div class="knobs">
    <p class="cap">вносить своё</p>
    <button type="button" class="knob" data-add="place">+ место</button>
    <button type="button" class="knob" data-add="booking">+ бронь или билет</button>
    <button type="button" class="knob" data-add="todo">+ в то-до</button>
    <span class="storesays" data-store-says role="status"></span>
  </div>
  <form class="pane" data-form hidden>
    <p class="what" data-form-what>Новое место</p>
    <div class="f wide">
      <label for="f-title">что это</label>
      <input id="f-title" name="title" maxlength="120" required
             placeholder="например: билет Токио → Киото">
    </div>
    <div class="f wide">
      <label for="f-note">подробность</label>
      <input id="f-note" name="note" maxlength="300" placeholder="необязательно">
    </div>
    <div class="f" data-only="place">
      <label for="f-stay">город</label>
      <select id="f-stay" name="stay">{cities}</select>
    </div>
    <div class="f" data-only="booking todo">
      <label for="f-when">дата</label>
      <input id="f-when" name="when" type="date" min="2026-08-01" max="2027-12-31">
    </div>
    <div class="f" data-only="todo">
      <label for="f-group">раздел</label>
      <select id="f-group" name="group">{groups}</select>
    </div>
    <div class="f">
      <label for="f-amount">цена</label>
      <span class="pair">
        <input id="f-amount" name="amount" inputmode="decimal" placeholder="можно пусто">
        <select name="currency" aria-label="валюта">
          <option value="jpy">¥ иены</option>
          <option value="usd">$ доллары</option>
        </select>
      </span>
    </div>
    <div class="f">
      <label for="f-state">деньги</label>
      <select id="f-state" name="state">
        <option value="paid">уже оплачено</option>
        <option value="upcoming">предстоит</option>
        <option value="onsite">плачу на месте</option>
      </select>
    </div>
    <div class="go">
      <button type="submit" class="save">Сохранить</button>
      <button type="button" class="drop" data-cancel>Отмена</button>
      <span class="says" data-form-says role="status"></span>
    </div>
  </form>
  <!-- Место, привязанное к городу, которого на странице больше нет (город
       переименовали в trip.json, а запись осталась). Тихо пропасть оно не
       должно — это ровно та беда, от которой в check() стоит правило №6. -->
  <div class="orphans" data-orphans hidden>
    <p class="cap">эти места привязаны к городу, которого на странице нет</p>
    <ul class="mine" data-mine-orphan></ul>
  </div>
</section>"""


def ledger(trip: dict, stays: list, all_legs: list) -> str:
    """Деньги и честно пустые места рядом.

    Итог в долларах складывается из показанных долларов по городам, а не из
    общей иены: иначе четыре числа на экране в столбик дают на доллар больше,
    чем итог, и это первое, что бросается в глаза. В иенах всё точно.
    """
    total = sum(s["total_jpy"] for s in stays)
    usd_total = sum(round(leg["jpy"] / FX["usd_per_jpy"]) for leg in all_legs)
    slept = sum(leg["nights"] for leg in all_legs)
    paid = sum(s["payment"].get("paid_jpy", 0) for s in stays)
    upcoming = sum(s["payment"].get("upcoming_jpy", 0) for s in stays)
    onsite = sum(s["total_jpy"] for s in stays if s["payment"]["mode"] == "at_property")

    def part(x: int) -> str:
        return f"{x / total * 100:.1f}%"

    blanks = "".join(
        f'<div class="blank"><span class="slot"></span>'
        f'<b>{e(u["label"])}</b><span class="nt">{e(u["note"])}</span></div>'
        for u in trip.get("unknown", [])
    )
    caveats = "".join(f"<li>{e(x)}</li>" for x in trip["notes"])

    # Итог неполный, и сказать об этом обязана строка, стоящая вплотную к нему.
    # Крупное число само себя объявляет полной ценой поездки: подписи «жильё»
    # над ним хватает, только пока её читают. Чисел здесь нет нарочно — это был
    # бы второй счёт, который разойдётся с первым молча.
    missing = trip.get("not_in_total", [])
    notall = (f'<p class="notall">в это число не входит: '
              + ", ".join(f"<span>{e(x)}</span>" for x in missing) + "</p>") if missing else ""

    return f"""
<section class="ledger">
  <div class="total" id="check">
    <p class="cap" data-cap>жильё · {len(stays)} {plural(len(stays), "бронь", "брони", "броней")},
       {slept} {plural(slept, "ночь", "ночи", "ночей")}</p>
    <p class="sum"><b class="usd" data-usd>${f"{usd_total:,}".replace(",", THIN)}</b>
       <span class="jpy" data-jpy>{yen(total)}</span></p>
    <p class="fx">$1 = ¥{FX["usd_per_jpy"]} · курс на {fx_human_date()} · платится в иенах,
       доллары округлены</p>
    {notall}
    <div class="bar" role="img" aria-label="как разделена оплата">
      <span class="seg paid" data-seg="paid" style="width:{part(paid)}"></span>
      <span class="seg due" data-seg="upcoming" style="width:{part(upcoming)}"></span>
      <span class="seg onsite" data-seg="onsite" style="width:{part(onsite)}"></span>
    </div>
    <ul class="legend">
      <li class="paid"><b data-money="paid">{yen(paid)}</b><span>уже списано</span></li>
      <li class="due"><b data-money="upcoming">{yen(upcoming)}</b><span>спишется само</span></li>
      <li class="onsite"><b data-money="onsite">{yen(onsite)}</b><span>на месте, при заезде</span></li>
    </ul>
    <!-- Из чего сложился чек. Пока её записей нет, здесь пусто и заголовок
         честно говорит «жильё»: подпись всегда про то число, которое рядом,
         а не про то, каким оно станет, когда что-нибудь загрузится. -->
    <ul class="parts" data-parts hidden></ul>
    <p class="says" data-says role="status"></p>
  </div>
  <div class="beyond">
    <p class="cap">сверх этого — считается на месте</p>
    <ul class="caveats">{caveats}</ul>
  </div>
  <div class="unknown">
    <p class="cap">ещё не посчитано</p>
    <div class="slots">{blanks}</div>
  </div>
</section>"""


def checklist(trip: dict) -> str:
    """«Что не забыть» — и единственный список, который она правит сама.

    Два слоя в одном столбце. Пункты из `trip.json` собираются здесь, её
    собственные приезжают из хранилища в браузере и ложатся в `ul.mine` того
    же раздела. Галочка теперь тоже в хранилище, а не в памяти телефона:
    список, который забывает отмеченное при смене устройства, — это список,
    которому нельзя доверить визу.

    Хранится по-прежнему **отличие** от файла, а не состояние: `data-built`
    говорит, что записано в `trip.json`, и совпавшая с файлом галочка из
    хранилища стирается. Когда решение переедет в файл, отметка не начнёт
    спорить сама с собой.
    """
    groups = []
    for g in trip["todo"]:
        items = "".join(
            f"""<li>
              <label>
                <input type="checkbox" data-todo="{e(g["group"])}::{e(i["text"])}"
                       data-built="{'true' if i.get('done') else 'false'}" {'checked' if i.get('done') else ''}>
                <span class="tick" aria-hidden="true"></span>
                <span class="txt">{e(i["text"])}
                  {f'<em>{e(i["note"])}</em>' if i.get("note") else ''}
                </span>
              </label>
            </li>"""
            for i in g["items"]
        )
        groups.append(
            f'<div class="todo-group" data-group="{e(g["group"])}">'
            f'<h3>{e(g["group"])}</h3><ul>{items}</ul>'
            f'<ul class="mine" data-mine-todo="{e(g["group"])}"></ul></div>'
        )
    # Раздел для её пунктов, не попавших ни в один из наших: пустым не
    # показывается, чтобы не занимать колонку обещанием.
    groups.append('<div class="todo-group" data-group="Ещё" data-spare hidden>'
                  '<h3>Ещё</h3><ul class="mine" data-mine-todo="Ещё"></ul></div>')
    return f"""
<div id="todo">
  <p class="sec-note">Свои пункты добавляй кнопкой «+ в то-до» — они и галочки
     хранятся на сайте, а не в телефоне. Цена необязательна: «виза» может быть
     просто галочкой. Что решено окончательно — переносим в
     <code>trip.json</code>, чтобы жило рядом с бронями.</p>
  <div class="todo-cols">{"".join(groups)}</div>
  <button class="reset" type="button" data-reset>Снять все галочки</button>
</div>"""


def by_day(trip: dict, stays: list, alerts: list) -> str:
    flagged = {a["id"]: a["level"] for a in alerts}
    start, end = d(trip["trip"]["start"]), d(trip["trip"]["end"])
    planned = trip.get("days", {})
    transit = {d(t["date"]): t for t in trip.get("transit", [])}

    rows = []
    day = start
    while day <= end:
        iso = day.isoformat()
        here = [s for s in stays if d(s["checkin"]["date"]) <= day < d(s["checkout"]["date"])]
        moving = [s for s in stays if d(s["checkin"]["date"]) == day]
        base = " / ".join(dict.fromkeys(f'{s["city"]} · {s["area"]}' for s in here))
        if not base:
            leg = transit.get(day)
            base = leg["detail"].capitalize() if leg else "—"

        p = planned.get(iso, {})
        items = "".join(f"<li>{e(x)}</li>" for x in p.get("items", []))
        tones = {flagged.get(s.get("conflict")) for s in here} - {None}
        clash = "red" if "red" in tones else "noted" if tones and len(here) > 1 else ""

        rows.append(f"""
<li class="{'move' if moving and day != start else ''} {clash}">
  <div class="date">
    <b>{day.day}</b><span>{WEEKDAYS[day.weekday()]}</span>
  </div>
  <div class="body">
    <p class="base">{e(base)}</p>
    {f'<p class="title">{e(p["title"])}</p>' if p.get("title") else ''}
    {f'<ul>{items}</ul>' if items else '<p class="empty">свободно</p>'}
  </div>
</li>""")
        day += timedelta(days=1)

    return f"""
<div id="days">
  <p class="sec-note">Города подставляются из броней. Планы на день —
     раздел <code>days</code> в <code>trip.json</code>.</p>
  <ol class="days">{"".join(rows)}</ol>
</div>"""


def luggage(trip: dict) -> str:
    lug = trip["luggage"]
    moves = "".join(
        f"""<li>
          <p class="when">{day_month(m["date"])}, {weekday(m["date"])}</p>
          <p class="path"><span>{e(m["from"])}</span><i aria-hidden="true">→</i><span>{e(m["to"])}</span></p>
          <p class="how">{e(m["how"])}</p>
          <p class="note">{e(m["note"])}</p>
        </li>"""
        for m in lug["moves"]
    )
    always = "".join(f"<li>{e(x)}</li>" for x in lug["always"])
    # Пересылка чемодана стоит денег и в чек не идёт — цена стоит рядом с самой
    # пересылкой, а не только в строке «чего в итоге нет».
    cost = f'<p class="cost">{e(lug["cost"])}</p>' if lug.get("cost") else ""
    return f"""
<div id="luggage">
  <p class="lead">{e(lug["lead"])}</p>
  {cost}
  <ol class="moves">{moves}</ol>
  <ul class="always">{always}</ul>
</div>"""


def bought() -> str:
    """Купленное отдельно: билеты, поезда, экскурсии.

    Пустой раздел — одна строка, а не пустая страница: место под её брони
    существует до первой брони, иначе кнопке «+ бронь» некуда класть.

    Заголовок несёт число и сумму (их подставляет браузер), потому что
    свёрнутое без подписи превращается в вопрос «а есть ли там что-нибудь»,
    который приходится решать нажатием.
    """
    return """
<div id="bought">
  <p class="sec-note">Всё, что куплено или будет куплено не через отель: билеты,
     поезда, экскурсии. Идёт в общий чек — «уже оплачено» или «предстоит».</p>
  <ul class="mine rows-list" data-mine-booking></ul>
  <p class="none" data-none-booking>пока пусто — нажми «+ бронь или билет» выше.</p>
</div>"""


def more_block(trip: dict, stays: list, alerts: list) -> str:
    """Списки, дни и багаж — свёрнуты, но никуда не делись.

    Ни сказала про длинную версию: «слишком много листать вниз». Выкидывать
    при этом нечего — поэтому длинное лежит здесь, за одним нажатием, а не
    на главном экране.

    Порядок не случайный: первым то, что она правит сама («не забыть» и
    «куплено»), потом то, что читается («по дням», «багаж»). Заголовки
    первых двух показывают счёт и сумму — свёрнутое должно говорить, что
    внутри, само.
    """
    parts = [
        ("todo", "Решить и забронировать", checklist(trip)),
        ("bought", "Куплено отдельно", bought()),
        ("days", "По дням", by_day(trip, stays, alerts)),
        ("luggage", "Багаж", luggage(trip)),
    ]
    return "".join(
        f'<details class="more" data-fold="{e(key)}"><summary>{e(name)}'
        f'<span class="tag" data-tag="{e(key)}"></span></summary>{body}</details>'
        for key, name, body in parts
    )


def island(trip: dict, stays: list, all_legs: list) -> str:
    """Всё, что странице нужно знать про уже посчитанное, — одним куском.

    Числа считает питон при сборке (и проверяет `check`), а браузер их только
    складывает с её записями. Второй раз пересчитывать брони в JS нельзя: два
    счёта одного и того же — это два разных числа с одним именем, и разойтись
    они успеют молча.

    Лежит в `application/json`, а не в переменной: содержимое не исполняется,
    и `</script>` внутри строки не может закрыть блок раньше времени —
    угловая скобка ниже экранируется на всякий случай.
    """
    total = sum(s["total_jpy"] for s in stays)
    payload = {
        "fx": {
            "usd_per_jpy": FX["usd_per_jpy"],
            "as_of": FX["as_of"],
            "human": fx_human_date(),
        },
        "housing": {
            "jpy": total,
            # Доллар итога — сумма показанных городских долларов, а не
            # пересчёт общей иены: столбик на экране обязан сойтись с числом
            # под ним (см. README).
            "usd": sum(round(leg["jpy"] / FX["usd_per_jpy"]) for leg in all_legs),
            "paid": sum(s["payment"].get("paid_jpy", 0) for s in stays),
            "upcoming": sum(s["payment"].get("upcoming_jpy", 0) for s in stays),
            "onsite": sum(s["total_jpy"] for s in stays
                          if s["payment"]["mode"] == "at_property"),
            "count": len(stays),
            "nights": sum(leg["nights"] for leg in all_legs),
        },
        "cities": [
            {"id": leg["stays"][0]["id"], "city": leg["city"], "area": leg["area"]}
            for leg in all_legs
        ],
        "groups": [g["group"] for g in trip["todo"]],
    }
    text = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
    return f'<script type="application/json" id="japan-data">{text}</script>'


def colophon(trip: dict) -> str:
    return f"""
<footer class="colophon">
  <span>Обновлено {day_month(trip["trip"]["updated"])} {d(trip["trip"]["updated"]).year}.</span>
  <span>Места, брони и пункты списка вписывай сама — они сохраняются здесь же
  и никуда не денутся. Отели, даты и сроки отмены вносит Блэйз.</span>
</footer>"""


# ─────────────────────────────────────────── стиль

CSS = """
/* Страница всегда светлая — её слово 2026-08-23: «а сделайте на светлом фоне,
   а то сложно читать». Тёмная тема тут не отключена «на всякий случай»: она
   включалась сама, по настройке телефона, и именно её Ни и увидела. Поэтому
   `color-scheme:light` стоит рядом — без него светлыми останутся только наши
   цвета, а поля ввода и полоса прокрутки браузер всё равно нарисует тёмными.

   Каждый цвет ниже подписан контрастом к бумаге (#f2eee7), потому что «сложно
   читать» — это измеримая величина, а не вкус. Основной текст держит 7:1,
   подписи и мелочь — 4.5:1; проверяется в test/wide.py на каждой видимой
   строке, а не глазами по памяти. */
:root{
  color-scheme:light;
  --paper:#f2eee7; --card:#fcfaf6; --sand:#f6f0e4;
  --ink:#1e1b18;            /* 14.8:1 — всё, что читается как текст */
  --deep:#564e43;           /*  7.1:1 — второй голос, но всё ещё текст */
  --quiet:#645d54;          /*  5.6:1 — подписи, мелочь, пояснения */
  --gold:#7c6138;           /*  5.0:1 — акцент и мелкие заголовки */
  --bronze:#5f4a2a;         /*  7.3:1 — тот же акцент там, где он от 14px и текст */
  --moss:#4a6546;           /*  5.6:1 — уже списано */
  --fire:#a83727;           /*  5.6:1 — спишется само, просроченное */
  --rule:#8f8677;           /*  3.1:1 — границы, которые что-то значат */
  --hair:#cec5b3;           /*  1.5:1 — разделители строк, чистое оформление */
  --serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,"Times New Roman",serif;
  --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
  --num:ui-monospace,SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace;
  --sheet:1340px;
  /* Три способа оплаты различаются не только цветом: заливка, косая штриховка
     вправо, косая штриховка влево. Плотность у всех трёх одинаковая нарочно —
     ставить её лесенкой значило бы рисовать самую крупную сумму самой бледной,
     а «на месте» здесь как раз крупнейшая доля. */
  --fill-paid:var(--moss);
  --fill-due:repeating-linear-gradient(45deg,var(--fire) 0 2px,rgba(255,255,255,.75) 2px 4.5px);
  --fill-onsite:repeating-linear-gradient(-45deg,var(--gold) 0 2px,rgba(255,255,255,.75) 2px 4.5px);
}
*{box-sizing:border-box}
/* `hidden` обязан выигрывать у наших `display`. Без этой строки `.pane{display:grid}`
   перебивает атрибут — и форма, объявленная спрятанной, стоит развёрнутой во
   весь экран. Так и случилось: страница выросла на 292 точки, а спрятанной
   форма при этом считалась. */
[hidden]{display:none !important}
html{-webkit-text-size-adjust:100%}
body{
  margin:0; background:var(--paper); color:var(--ink);
  font-family:var(--sans); font-size:15px; line-height:1.5;
  -webkit-font-smoothing:antialiased;
}
.sheet{max-width:var(--sheet); margin:0 auto; padding:22px 16px 34px}
h1,h2,h3,.city .name,.total .usd,.thread .town{font-family:var(--serif); font-weight:600; margin:0}
a{color:inherit}
code{font-size:.88em; background:var(--sand); padding:1px 5px; border-radius:4px}
.num{font-family:var(--num); font-variant-numeric:tabular-nums}

/* ── шапка */
.masthead{position:relative; display:flex; flex-wrap:wrap; align-items:flex-end;
  justify-content:space-between; gap:10px; padding:2px 0 14px; overflow:hidden}
.eyebrow{margin:0; font-size:10.5px; letter-spacing:.24em; text-transform:uppercase; color:var(--quiet)}
.masthead h1{font-size:44px; line-height:1; letter-spacing:-.01em; margin-top:4px}
.masthead h1 .year{color:var(--gold); font-size:24px; letter-spacing:.06em}
.masthead .side{display:flex; flex-direction:column; align-items:flex-end; gap:9px}
.masthead .when{margin:0; font-size:13px; color:var(--quiet); letter-spacing:.04em;
  display:flex; flex-wrap:wrap; gap:4px 14px; align-items:baseline}
.masthead .when b{color:var(--ink); font-size:15px; letter-spacing:.02em}
.masthead .when span::before{content:"·"; margin-right:14px; opacity:.5}

/* ── ближайший срок отмены: самая дорогая дата страницы, в шапке

   Стоит в правом столбце под датами поездки — там, где до сих пор была пустота
   ниже заголовка. Оттого блок и не удлиняет страницу: он занимает уже
   потраченную высоту, а потолок в два экрана — её слово.

   Остаток дней дописывает браузер в `.left` (см. JS). Без него видна только
   дата: она не стареет, а замороженное «осталось 116 дней» стареет каждые
   сутки. */
.deadlines{margin:0}
.deadlines > summary{cursor:pointer; list-style:none; display:flex; flex-wrap:wrap;
  align-items:baseline; justify-content:flex-end; gap:1px 10px; padding:4px 0 0}
.deadlines > summary::-webkit-details-marker{display:none}
.deadlines .one{display:flex; flex-wrap:wrap; align-items:baseline; gap:2px 9px;
  justify-content:flex-end}
/* Ромб — тот же знак, которым помечена спокойная заметка ниже: на странице
   он значит «это сказано нарочно, прочти». */
.deadlines .cap{flex:1 0 100%; text-align:right; font-size:9.5px; letter-spacing:.15em;
  text-transform:uppercase; color:var(--gold); font-weight:700}
.deadlines .cap::before{content:"◆"; margin-right:7px; font-size:8px; vertical-align:1px}
.deadlines .till{font-family:var(--serif); font-size:17px; font-weight:600;
  line-height:1.15; color:var(--ink)}
.deadlines .who{font-size:11.5px; color:var(--quiet)}
.deadlines .cost .usd{font-family:var(--num); font-size:12px; font-weight:600; color:var(--deep)}
.deadlines .cost .jpy{font-family:var(--num); font-size:10.5px; color:var(--quiet);
  margin-left:5px}
.deadlines .left{font-size:12px; font-weight:700; color:var(--bronze)}
.deadlines .soon > .left,.deadlines .soon .left{color:var(--fire)}
/* Срок, успевший пройти между сборкой и чтением: браузер гасит его и сам
   раскрывает список, чтобы живые сроки не остались за мёртвым. */
.deadlines .gone .till,.deadlines .gone .who,
.deadlines .gone .cost .usd,.deadlines .gone .cost .jpy{
  text-decoration:line-through; color:var(--quiet)}
.deadlines .opens{font-size:11px; color:var(--deep); border-bottom:1px dotted var(--rule);
  white-space:nowrap}
.deadlines[open] .opens::after{content:" ▴"}
.deadlines:not([open]) .opens::after{content:" ▾"}
.deadlines .rest{list-style:none; margin:7px 0 0; padding:0; display:grid; gap:2px;
  justify-items:end}
.deadlines .rest li{display:flex; flex-wrap:wrap; align-items:baseline; gap:2px 9px;
  justify-content:flex-end; font-size:11.5px; color:var(--quiet)}
.deadlines .rest .till{font-family:var(--num); font-size:12px; color:var(--ink)}

/* ── нитка */
.thread{border-top:1px solid var(--rule); padding-top:16px; margin-bottom:18px}
.thread .row{display:grid; grid-template-columns:repeat(var(--nights),1fr) 88px; gap:4px}
.thread .cap{padding-right:10px; align-self:end}
.thread .cap span{display:block}
.thread .cap .town{font-size:22px; line-height:1.05; display:block}
.thread .cap .area{font-size:10px; letter-spacing:.16em; text-transform:uppercase;
  color:var(--quiet); margin-top:3px}
.thread .cap .hotel{font-size:12.5px; font-weight:600; margin-top:6px; line-height:1.25;
  overflow:hidden; text-overflow:ellipsis; white-space:nowrap}
.thread .cap .hotel.quiet{color:var(--quiet); font-weight:500}
/* Ножка от подписи к отрезку. Класс не `tick` нарочно: так называется
   галочка чеклиста ниже, и одноимённый класс превращал ножку в плашку. */
.thread .cap .stem{height:9px; border-left:1px solid var(--rule); margin-top:7px}
.thread .bars{align-items:stretch; margin-top:2px}
.thread .bar{height:62px; border-radius:4px; position:relative; display:flex;
  align-items:flex-end; padding:0 12px 9px; color:#fff; overflow:hidden}
.thread .bar .n{font-size:12.5px; font-weight:600; letter-spacing:.01em}
.thread .bar .who{display:none}
.thread .bar .edge{position:absolute; top:9px; font-family:var(--num); font-size:10.5px;
  color:rgba(255,255,255,.9); white-space:nowrap}
.thread .bar .edge.i{left:12px}
.thread .bar .edge.o{right:12px}
.thread .bar.air{background:transparent; border:1px dashed var(--rule); color:var(--quiet);
  background-image:repeating-linear-gradient(45deg,rgba(139,130,117,.13) 0 5px,transparent 5px 10px)}
.thread .bar.air .n{color:var(--quiet); font-weight:500}
.thread .home{border-left:1px solid var(--rule); padding-left:11px; display:flex;
  flex-direction:column; justify-content:flex-end; height:62px}
.thread .home b{font-family:var(--serif); font-size:20px; line-height:1}
.thread .home span{font-size:9.5px; letter-spacing:.14em; text-transform:uppercase;
  color:var(--quiet); margin-top:4px}
.thread .paidrow{margin-top:4px; height:15px}
/* Оплачено сверх прожитого: обводка и штриховка, а не тот же цвет побледнее.
   Бледный оттенок — единственное, что не переживает плохой экран. */
.thread .paidbar{height:9px; border-radius:2px; position:relative;
  border:1px solid currentColor;
  background:repeating-linear-gradient(45deg,currentColor 0 2px,transparent 2px 5px)}
.thread .paidbar span{position:absolute; left:0; top:11px; white-space:nowrap;
  font-size:10.5px; color:var(--quiet)}
.thread .dates{margin-top:14px; border-top:1px solid var(--rule)}
.thread .day{text-align:center; padding-top:8px; position:relative}
.thread .day::before{content:""; position:absolute; left:50%; top:0; width:1px; height:4px;
  background:var(--rule)}
.thread .day b{font-family:var(--num); font-size:13px; font-weight:600}
.thread .day span{display:block; font-size:9.5px; color:var(--quiet); letter-spacing:.08em}
.thread .day.we b{color:var(--deep)}
.thread .moves{margin-top:9px; align-items:start}
.thread .move{display:flex; flex-direction:column; gap:1px; font-size:10.5px;
  color:var(--deep); margin-left:-3px; padding-right:9px}
.thread .move .hd{display:flex; align-items:center; gap:6px; white-space:nowrap}
/* Дата переезда нужна только там, где нет числовой оси, — на телефоне нитка
   встаёт столбиком и ось прячется. */
.thread .move .dt{display:none}
.thread .move i{width:0; height:0; border-left:5px solid var(--gold);
  border-top:3.5px solid transparent; border-bottom:3.5px solid transparent; flex:none}
/* Чем и сколько ехать. Строка узкая по столбцам сетки, поэтому переносится, а
   не обрезается: половина названия поезда хуже двух строк. */
.thread .move .ride{display:flex; flex-wrap:wrap; gap:0 8px; padding-left:11px;
  font-size:10px; line-height:1.35; color:var(--quiet)}
.thread .move .hrs{font-family:var(--num)}
.thread .move .cost{font-family:var(--num); color:var(--bronze); font-weight:600}
/* Цены нет — пустое поле с подписью, как в «ещё не посчитано» внизу. Прочерк
   читается как «бесплатно», выдуманное число — как подтверждённое. */
.thread .move .cost.none{color:var(--quiet); font-weight:400; font-family:var(--sans)}
.thread .move .slot{display:inline-block; width:26px; border-bottom:1px solid var(--rule);
  margin-right:5px; vertical-align:2px}
/* Что покрывает записанное число — рядом с ним, а не отдельной строкой:
   строка съедала бы высоту нитки втрое чаще, чем добавляла смысл. */
.thread .move .covers{font-size:9.5px}

/* ── заметка про ночь с двумя бронями */
.alert{border:1.5px solid var(--fire); background:var(--sand); border-radius:12px;
  padding:11px 16px; margin:0 0 18px; display:flex; flex-wrap:wrap; gap:6px 26px;
  align-items:baseline}
.alert.calm{border:1px solid var(--gold)}
.alert .says{flex:none; max-width:520px}
.alert .siren{margin:0; font-size:10px; letter-spacing:.2em; text-transform:uppercase;
  color:var(--fire); font-weight:700}
.alert.calm .siren{color:var(--gold)}
.alert .siren::before{content:"●"; margin-right:7px; font-size:8px; vertical-align:2px}
.alert.calm .siren::before{content:"◆"}
.alert h2{font-size:17px; margin-top:3px; color:var(--fire)}
.alert.calm h2{color:var(--ink)}
.alert .lead{margin:2px 0 0; font-size:13.5px; color:var(--deep)}
.alert .facts{list-style:none; margin:0; padding:0; display:flex; flex-wrap:wrap; gap:2px 22px;
  font-size:12px; color:var(--quiet); flex:1; min-width:260px}
.alert .facts li{padding-left:16px; position:relative}
.alert .facts li::before{content:"—"; position:absolute; left:0; color:var(--gold)}
.alert .closing{margin:0; font-size:12.5px; font-style:italic; color:var(--deep); flex:none}
.alert .options{list-style:none; margin:0; padding:0; display:grid; gap:9px}
.alert .opt h4{font-size:15px}
.alert .watch{color:var(--fire); font-weight:600; font-size:12.5px}
.alert .watch .left,.cancel .left{display:block; font-weight:400; color:var(--quiet)}

/* ── карточки городов */
.cities{display:grid; grid-template-columns:repeat(4,1fr); gap:16px; align-items:start}
.city{background:var(--card); border:1px solid var(--hair); border-radius:6px; overflow:hidden}
.city .cap{padding:12px 15px 11px; color:#fff}
.city .name{font-size:21px; line-height:1}
.city .area{margin:5px 0 0; font-size:9.5px; letter-spacing:.18em; text-transform:uppercase;
  opacity:.85}
.city .inner{padding:13px 15px 15px}
.city .hotel{margin:0; font-size:14.5px; font-weight:600; line-height:1.2}
.city .span{margin:9px 0 0; font-family:var(--num); font-size:13px; font-weight:500}
.city .span span{font-family:var(--sans); font-size:10.5px; color:var(--quiet); margin-left:6px}
.city .price{margin:9px 0 0; display:flex; flex-wrap:wrap; align-items:baseline; gap:0 9px}
.city .usd{font-family:var(--serif); font-size:27px; line-height:1; letter-spacing:-.01em}
.city .jpy{font-family:var(--num); font-size:11px; color:var(--quiet)}
/* Как платится — тремя способами сразу: словом, цветом и наполненностью
   квадратика. Штриховка на восьми пикселях превращается в штрих-код, поэтому
   здесь то же различие сказано наполненностью: полный → половина → пустой.
   Внизу, где места больше, ту же тройку разводит фактура полосы. */
.city .how{display:block; width:100%; font-size:11px; margin-top:6px}
.city .how span{margin-right:12px; padding-left:16px; position:relative}
.city .how span::before{content:""; position:absolute; left:0; top:3px; width:9px; height:9px;
  border-radius:2px; border:1.5px solid currentColor}
.city .paid::before{background:currentColor}
.city .due::before{box-shadow:inset 0 -3px 0 currentColor}
.city .paid{color:var(--moss)} .city .due{color:var(--fire)} .city .onsite{color:var(--gold)}
.city .plain{color:var(--quiet); padding-left:0}
.city .plain::before{display:none}

/* ── подробности проживания: одна стрелка на карточку */
.stayfine{margin-top:12px; border-top:1px solid var(--hair)}
.stayfine > summary{cursor:pointer; list-style:none; display:grid;
  grid-template-columns:13px 1fr; gap:1px 6px; align-items:start;
  padding:9px 0 8px; min-height:36px}
.stayfine > summary::-webkit-details-marker{display:none}
.stayfine > summary::before{content:""; grid-row:1; align-self:start; margin-top:4px;
  width:0; height:0; border-left:6px solid var(--gold);
  border-top:4.5px solid transparent; border-bottom:4.5px solid transparent}
.stayfine[open] > summary::before{border-left:4.5px solid transparent;
  border-right:4.5px solid transparent; border-top:6px solid var(--gold); border-bottom:0;
  margin-top:6px}
.stayfine .lbl{grid-column:2; font-size:12px; color:var(--deep); font-weight:600}
.stayfine .hint{grid-column:2; font-size:10.5px; color:var(--quiet); line-height:1.3}
.rows{margin:2px 0 0; border-top:1px solid var(--hair)}
.rows > div{display:flex; gap:10px; padding:6px 0; border-bottom:1px solid var(--hair)}
.rows dt{flex:none; width:58px; font-size:9.5px; letter-spacing:.1em; text-transform:uppercase;
  color:var(--quiet); padding-top:2px}
.rows dd{margin:0; font-size:12px; line-height:1.35}
.rows dd.num{font-family:var(--num)}
.btn{display:block; min-height:20px; text-decoration:none; color:var(--ink);
  border-bottom:1px dotted var(--rule); padding:1px 0}
.btn.tel{font-family:var(--num); color:var(--quiet); border:0}
/* Помеченная бронь отличается не только цветом полоски, но и её толщиной —
   и объясняет себя словами внутри, а не одним оттенком слева. */
.stay{margin-top:11px; padding:9px 11px; border-radius:8px; background:var(--sand);
  border-left:2px solid var(--hair)}
.stay.noted{border-left:4px solid var(--gold)}
.stay.clash{border-left:4px solid var(--fire)}
.stay .blabel{margin:0 0 4px; font-size:10.5px; color:var(--quiet); font-style:italic}
.stay .arriving{margin:0 0 7px; font-size:11.5px}
.stay .arriving b{display:block; font-size:12.5px}
.stay .arriving span{display:block; color:var(--quiet); font-size:11px; line-height:1.35}
.cancel{margin:0; font-size:11.5px}
.cancel .k{display:block; font-size:9.5px; letter-spacing:.11em; text-transform:uppercase;
  color:var(--quiet)}
.cancel b{display:block; font-size:11.5px; margin-top:1px}
.cancel .t{display:block; color:var(--quiet); font-size:11px}
.cancel .left{margin-top:2px; font-size:11px; font-weight:600; color:var(--gold)}
.cancel.soon .left{color:var(--fire)}
.extras{list-style:none; margin:9px 0 0; padding:0; font-size:11px; color:var(--quiet)}
.extras li{padding:1px 0 1px 11px; position:relative; line-height:1.4}
.extras li::before{content:"+"; position:absolute; left:0; color:var(--gold)}
.fine{list-style:none; margin:8px 0 0; padding:0; font-size:11px; color:var(--quiet)}
.fine li{padding:2px 0 2px 11px; position:relative; line-height:1.4}
.fine li::before{content:"·"; position:absolute; left:3px}

/* ── места из вишлиста: пунктир, потому что это желания, а не брони */
.wishes{margin-top:13px; border-top:1px dashed var(--rule); padding-top:10px}
.wish-cap{margin:0 0 7px; font-size:9.5px; letter-spacing:.14em; text-transform:uppercase;
  color:var(--gold); font-weight:700}
.wish-cap span{color:var(--quiet); font-weight:400; letter-spacing:.04em; text-transform:none;
  font-size:10px}
.wishes ul{list-style:none; margin:0; padding:0}
.wishes li{padding:4px 0 4px 14px; position:relative; line-height:1.3}
.wishes li::before{content:"◇"; position:absolute; left:0; top:4px; font-size:8.5px;
  color:var(--gold)}
.wishes b{font-size:12px; font-weight:600}
.wishes .where{font-size:10px; color:var(--quiet); margin-left:5px}
.wishes .what{display:block; font-size:11px; color:var(--quiet); line-height:1.35}
.wishes .none{margin:0; font-size:11px; color:var(--quiet); line-height:1.35;
  border:1px dashed var(--rule); border-radius:5px; padding:6px 8px}
.wish-more{margin-top:4px}
.wish-more summary{cursor:pointer; font-size:11px; color:var(--deep)}
.cancelled{list-style:none; margin:12px 0 0; padding:0; font-size:11.5px; color:var(--quiet)}
.cancelled li{display:flex; flex-wrap:wrap; gap:0 8px; align-items:baseline}
.cancelled b{text-decoration:line-through; font-weight:600}
.cancelled .usd{font-family:var(--sans); font-size:11.5px; font-weight:600}
.cancelled .jpy{font-family:var(--num); font-size:11px; margin-left:5px}

/* ── деньги и пустые места */
.ledger{display:flex; flex-wrap:wrap; gap:22px 40px; align-items:flex-start;
  margin-top:20px; padding-top:16px; border-top:1px solid var(--rule)}
.ledger .cap{margin:0; font-size:9.5px; letter-spacing:.17em; text-transform:uppercase;
  color:var(--quiet)}
.total{flex:1 1 340px; max-width:430px}
.total .sum{margin:6px 0 0; display:flex; align-items:baseline; gap:11px}
.total .usd{font-size:38px; line-height:1; letter-spacing:-.02em}
.total .jpy{font-family:var(--num); font-size:14px; color:var(--deep)}
.total .fx{margin:6px 0 0; font-size:10.5px; color:var(--quiet); line-height:1.5}
/* Три доли оплаты различаются заливкой, штриховкой и полосками — не только
   цветом. Тонкий просвет между кусками показывает границу даже там, где два
   соседних оттенка на плохом экране сливаются. */
.bar{display:flex; height:9px; border-radius:99px; overflow:hidden; margin:12px 0 10px;
  background:var(--hair)}
.seg.paid{background:var(--fill-paid)}
.seg.due{background:var(--fill-due)}
.seg.onsite{background:var(--fill-onsite)}
.seg + .seg{border-left:1.5px solid var(--card)}
.legend{list-style:none; margin:0; padding:0; display:flex; flex-wrap:wrap; gap:4px 18px;
  font-size:11.5px}
.legend li{padding-left:15px; position:relative; color:var(--quiet)}
.legend li::before{content:""; position:absolute; left:0; top:4px; width:9px; height:9px;
  border-radius:2px; border:1.5px solid currentColor}
.legend .paid{color:var(--moss)} .legend .due{color:var(--fire)} .legend .onsite{color:var(--gold)}
.legend .paid::before{background:currentColor}
.legend .due::before{box-shadow:inset 0 -3px 0 currentColor}
.legend b,.legend span{color:var(--quiet)}
.legend b{color:var(--ink)}
.legend b{font-family:var(--num); color:var(--ink); margin-right:5px}
.beyond{flex:1 1 250px; max-width:330px}
.caveats{list-style:none; margin:8px 0 0; padding:0; font-size:11.5px; color:var(--quiet)}
.caveats li{padding:2px 0 2px 12px; position:relative; line-height:1.45}
.caveats li::before{content:"+"; position:absolute; left:0; color:var(--gold)}
.unknown{margin-left:auto}
.unknown .slots{display:flex; gap:9px; margin-top:8px; flex-wrap:wrap}
.blank{width:132px; border:1px dashed var(--rule); border-radius:4px; padding:8px 10px 7px;
  background:rgba(255,255,255,.28)}
.blank .slot{display:block; height:14px; border-bottom:1px solid var(--rule)}
.blank b{display:block; font-size:11.5px; margin-top:6px; line-height:1.2}
.blank .nt{display:block; font-size:9.5px; color:var(--quiet); margin-top:2px}

/* ── то, что вносит она сама

   Её записи выглядят как записи, а не как брони: та же пунктирная логика, что
   у желаний, плюс чип с состоянием денег. Различие «оплачено / предстоит / на
   месте» держится словом и фактурой квадратика, а не оттенком: плохой экран
   первым съедает именно оттенок. */
.adder{margin-top:16px; padding-top:13px; border-top:1px solid var(--rule)}
.knobs{display:flex; flex-wrap:wrap; align-items:center; gap:8px 10px}
.knobs .cap{margin:0 4px 0 0; font-size:9.5px; letter-spacing:.17em;
  text-transform:uppercase; color:var(--quiet)}
.knob,.tiny{font-family:inherit; cursor:pointer; color:var(--ink); background:var(--card);
  border:1px solid var(--rule); border-radius:99px; padding:7px 13px; font-size:12.5px}
.knob:hover,.tiny:hover{background:var(--sand)}
.knob:focus-visible,.tiny:focus-visible,.save:focus-visible,.drop:focus-visible{
  outline:2px solid var(--gold); outline-offset:2px}
.tiny{margin-top:7px; padding:5px 11px; font-size:11.5px; color:var(--deep)}
.storesays{font-size:11.5px; color:var(--fire)}
.pane{margin-top:12px; padding:13px 15px 14px; background:var(--card);
  border:1px solid var(--hair); border-radius:10px;
  display:grid; grid-template-columns:repeat(auto-fit,minmax(168px,1fr)); gap:10px 14px;
  align-items:end}
.pane .what{grid-column:1/-1; margin:0; font-family:var(--serif); font-size:16px}
.pane .f{display:flex; flex-direction:column; gap:3px; min-width:0}
.pane .f.wide{grid-column:span 2}
.pane label{font-size:9.5px; letter-spacing:.12em; text-transform:uppercase; color:var(--quiet)}
.pane input,.pane select{font-family:inherit; font-size:14px; color:var(--ink);
  background:var(--paper); border:1px solid var(--rule); border-radius:7px;
  padding:8px 9px; min-height:38px; width:100%; min-width:0}
.pane .pair{display:flex; gap:6px}
.pane .pair input{flex:2 1 60px} .pane .pair select{flex:1 1 90px}
.pane .go{grid-column:1/-1; display:flex; flex-wrap:wrap; align-items:center; gap:9px 12px;
  margin-top:2px}
.save,.drop{font-family:inherit; font-size:13.5px; cursor:pointer; border-radius:8px;
  padding:10px 18px; min-height:40px; border:1px solid var(--deep);
  background:var(--deep); color:#fff}
.drop{background:none; color:var(--deep); border-color:var(--rule)}
.save[disabled]{opacity:1; background:var(--quiet); border-color:var(--quiet); cursor:default}
.pane .says{font-size:12px; color:var(--fire)}
.orphans{margin-top:12px; border:1px dashed var(--fire); border-radius:8px; padding:8px 11px}
.orphans .cap{margin:0 0 4px; font-size:10px; letter-spacing:.1em; text-transform:uppercase;
  color:var(--fire)}

/* Строка её записи — в карточке города, в «куплено» и в списке. */
.own{position:relative; padding:6px 0 7px 14px; line-height:1.35;
  border-bottom:1px solid var(--hair)}
.own::before{content:"◆"; position:absolute; left:0; top:7px; font-size:8.5px; color:var(--bronze)}
.own > b,.own .head b{font-size:12.5px; font-weight:600}
.own .head{display:flex; flex-wrap:wrap; gap:0 8px; align-items:baseline}
.own .when{font-family:var(--num); font-size:10.5px; color:var(--quiet)}
.own .what{display:block; font-size:11px; color:var(--quiet); line-height:1.35}
.own .tab{display:flex; flex-wrap:wrap; align-items:baseline; gap:2px 8px; margin-top:3px}
.own .usd{font-family:var(--serif); font-size:15px; font-weight:600}
.own .jpy{font-family:var(--num); font-size:10.5px; color:var(--quiet)}
.own .noprice{font-size:10.5px; color:var(--quiet); font-style:italic}
.chip{font-size:10px; letter-spacing:.04em; padding:1px 7px 2px 17px; border-radius:99px;
  border:1px solid currentColor; position:relative; white-space:nowrap}
.chip::before{content:""; position:absolute; left:5px; top:4px; width:7px; height:7px;
  border-radius:2px; border:1.5px solid currentColor}
.chip.paid{color:var(--moss)} .chip.paid::before{background:currentColor}
.chip.due{color:var(--fire)} .chip.due::before{box-shadow:inset 0 -2px 0 currentColor}
.chip.onsite{color:var(--gold)}
.tools{display:flex; gap:9px; margin-top:2px}
.ed,.rm{background:none; border:0; padding:2px 0; font-family:inherit; font-size:10.5px;
  color:var(--quiet); cursor:pointer; border-bottom:1px dotted var(--rule)}
.ed:hover,.rm:hover{color:var(--ink)}
.own.fresh{background:var(--sand); border-radius:6px}
.rows-list{list-style:none; margin:0; padding:0}
.todo-group .own{padding-left:0}
.todo-group .own::before{display:none}
.todo-group .own .tab,.todo-group .own .tools{margin-left:31px}
#bought .none,.wishes .none[hidden]{display:none}
#bought .none:not([hidden]){display:block; margin:0; font-size:12px; color:var(--quiet)}

/* Из чего сложился чек — под самим чеком, чтобы столбик можно было сверить
   глазами, не листая. */
.parts{list-style:none; margin:10px 0 0; padding:0; display:flex; flex-wrap:wrap;
  gap:2px 16px; font-size:11.5px}
.parts .part{color:var(--quiet)}
.parts .part .num{font-family:var(--num); color:var(--ink); margin-left:5px}
.parts .built .who{color:var(--deep)}
.total .says{display:block; margin:7px 0 0; font-size:11px; color:var(--quiet); line-height:1.45}
/* Чего в этом числе нет. Стоит между суммой и разбивкой оплаты — то есть в
   одном взгляде с цифрой, а не четырьмя строками ниже: подписи «жильё» над
   крупным числом хватает ровно до тех пор, пока её читают. Пунктир — тот же
   язык, что у желаний и пустых полей: «здесь ещё не всё». */
.notall{margin:8px 0 0; padding-top:7px; border-top:1px dashed var(--rule);
  font-size:11px; color:var(--quiet); line-height:1.45}
.notall span{color:var(--deep)}
.more > summary .tag{font-size:10px; letter-spacing:.06em; text-transform:none;
  color:var(--gold); font-weight:600}

/* ── свёрнутое: списки, дни, багаж */
.more{border-bottom:1px solid var(--hair)}
.more:first-of-type{border-top:1px solid var(--rule); margin-top:26px}
/* 38px, а не 44: 44 — размер пальца, и он нужен на телефоне, где и стоит
   (см. запрос по max-width:700px ниже). На компьютере это четыре свёртки
   подряд, то есть 24 точки высоты, потраченные на промах мышью. */
.more > summary{cursor:pointer; list-style:none; padding:10px 2px; font-size:13px;
  letter-spacing:.14em; text-transform:uppercase; color:var(--quiet); font-weight:700;
  display:flex; align-items:center; gap:10px; min-height:38px}
.more > summary::-webkit-details-marker{display:none}
.more > summary::before{content:"+"; font-size:15px; color:var(--gold); width:12px}
.more[open] > summary::before{content:"–"}
.more > div{padding:0 2px 22px}
.sec-note{font-size:12px; color:var(--quiet); margin:0 0 14px}
.todo-cols{display:grid; gap:0 30px}
.todo-group{margin:0 0 16px}
.todo-group h3{font-size:14px; margin-bottom:5px; color:var(--bronze)}
.todo-group ul{list-style:none; margin:0; padding:0}
.todo-group li{border-bottom:1px solid var(--hair)}
.todo-group label{display:flex; gap:11px; align-items:flex-start; padding:10px 2px; cursor:pointer}
.todo-group input{position:absolute; opacity:0; width:0; height:0}
.tick{flex:none; width:20px; height:20px; margin-top:1px; border-radius:6px;
  border:1.5px solid var(--rule); background:var(--card); position:relative}
input:checked + .tick{background:var(--moss); border-color:var(--moss)}
input:checked + .tick::after{content:""; position:absolute; left:6px; top:2px; width:5px;
  height:10px; border:solid #fff; border-width:0 2px 2px 0; transform:rotate(42deg)}
input:focus-visible + .tick{outline:2px solid var(--gold); outline-offset:2px}
.txt{font-size:14px}
input:checked ~ .txt{color:var(--deep); text-decoration:line-through}
.txt em{display:block; font-size:12px; color:var(--quiet); font-style:normal; text-decoration:none}
.reset{margin-top:6px; background:none; border:1px solid var(--rule); border-radius:8px;
  padding:10px 14px; font-size:12.5px; color:var(--quiet); font-family:inherit; cursor:pointer}
.days{list-style:none; margin:0; padding:0; columns:1}
.days li{display:flex; gap:13px; padding:9px 0; border-bottom:1px solid var(--hair);
  break-inside:avoid}
.days .date{width:34px; flex:none; text-align:center}
.days .date b{display:block; font-family:var(--serif); font-size:19px; line-height:1}
.days .date span{font-size:10px; color:var(--quiet)}
.days .base{margin:0; font-size:13.5px; font-weight:600}
.days .title{margin:1px 0 0; font-size:12px; color:var(--gold); font-weight:600}
.days .body ul{list-style:none; margin:4px 0 0; padding:0}
.days .body li{display:block; border:0; padding:1px 0 1px 12px; font-size:12px;
  color:var(--quiet); position:relative}
.days .body li::before{content:"·"; position:absolute; left:3px}
/* Прозрачность съедает контраст молча: 5.6:1 при opacity .6 превращается в
   2.9:1, и меряется уже не то, что записано в переменной. Поэтому «свободно»
   приглушено курсивом, а не прозрачностью. */
.days .empty{margin:2px 0 0; font-size:11.5px; color:var(--quiet); font-style:italic}
.days .move .date b{color:var(--gold)}
.days .clash .date b{color:var(--fire)}
/* `#luggage` в начале не для красоты: без него правило доставало и ряд
   переездов в нитке, у которого тот же класс. Высоты это не меняло (нижний
   отступ там схлопывался с отступом самой нитки — проверено измерением, а не
   рассуждением), но раскладку ряда правило задавало через раз, по случайному
   порядку строк в файле. */
#luggage .moves{list-style:none; margin:0 0 14px; padding:0; display:grid; gap:10px}
#luggage .moves li{background:var(--card); border:1px solid var(--hair); border-radius:10px;
  padding:12px 14px}
#luggage .when{margin:0; font-size:10px; letter-spacing:.12em; text-transform:uppercase;
  color:var(--gold)}
#luggage .path{margin:5px 0 0; font-size:14.5px; font-family:var(--serif); display:flex;
  gap:8px; flex-wrap:wrap; align-items:baseline}
#luggage .path i{color:var(--bronze); font-style:normal}
#luggage .how{margin:4px 0 0; font-size:12.5px; font-weight:600}
#luggage .note{margin:1px 0 0; font-size:11.5px; color:var(--quiet)}
#luggage .lead{margin:0 0 12px; font-size:14px}
#luggage .cost{margin:-8px 0 12px; font-family:var(--num); font-size:12.5px;
  color:var(--bronze); font-weight:600}
.always{list-style:none; margin:0; padding:0; font-size:12.5px; color:var(--quiet)}
.always li{padding:3px 0 3px 17px; position:relative}
.always li::before{content:"✓"; position:absolute; left:0; color:var(--moss); font-size:11px}

.colophon{margin-top:22px; padding-top:14px; border-top:1px solid var(--hair);
  font-size:11px; color:var(--quiet); display:flex; flex-wrap:wrap; gap:4px 10px}

/* ── экраны поуже: нитка встаёт столбиком, карточки в один ряд */
@media (min-width:560px){
  .sheet{padding:26px 22px 40px}
  .masthead h1{font-size:52px}
  .todo-cols{grid-template-columns:1fr 1fr}
}
@media (min-width:1000px){
  .masthead h1{font-size:58px}
  .days{columns:2; column-gap:34px}
  .todo-cols{grid-template-columns:repeat(4,1fr)}
}
@media (max-width:1000px){
  .cities{grid-template-columns:1fr 1fr}
}
@media (max-width:700px){
  .cities{grid-template-columns:1fr}
  .thread .row{display:block}
  .thread .row > *{grid-column:auto !important}
  .thread .caps{display:none}
  .thread .bar{height:auto; padding:10px 13px; margin-bottom:5px; align-items:baseline;
    flex-wrap:wrap; gap:2px 10px}
  .thread .bar .who{display:block; order:-2; flex:1 1 100%; font-size:13.5px; font-weight:600}
  .thread .bar .edge{position:static; color:rgba(255,255,255,.9); font-size:11px}
  .thread .bar .edge.o{display:none}
  .thread .bar .n{order:-1; flex:none}
  .thread .home{flex-direction:row; align-items:baseline; gap:8px; height:auto;
    border-left:0; padding:6px 0 0}
  .thread .dates{display:none}
  /* Числовой оси на телефоне нет, поэтому «прилёт» и «домой» без неё — просто
     стрелки в никуда. А вот переезд с поездом и ценой нужен в дороге больше
     всего: его оставляем, отдельным блоком, со своей датой. */
  .thread .move:not(.has){display:none}
  /* Столбец, а не сетка: базовое правило `.row` задаёт шестнадцать колонок по
     ночам, и без сброса шаблона переезды встают тремя узкими башнями. */
  .thread .moves{margin-top:11px; display:grid; grid-template-columns:1fr; gap:7px}
  .thread .move{margin-left:0; padding:9px 12px; border:1px dashed var(--rule);
    border-radius:8px; background:rgba(255,255,255,.34)}
  .thread .move .hd{flex-wrap:wrap; white-space:normal; font-size:12.5px; font-weight:600}
  .thread .move .dt{display:inline; font-family:var(--num); font-weight:400;
    color:var(--quiet); font-size:11px}
  .thread .move .ride{font-size:11px; padding-left:11px}
  .thread .paidrow{height:auto}
  .thread .paidbar{height:auto; background:none; border:0; margin-top:4px}
  .thread .paidbar span{position:static; white-space:normal; display:block}
  .alert{display:block}
  .alert .facts{display:block; margin-top:8px}
  .unknown{margin-left:0}
  .blank{flex:1 1 100px; width:auto}
  /* Пальцем попадать: карта, телефон, все свёртки и всё, чем она правит
     страницу, — не мельче 36px. Проверяется в test/wide.py по этому же
     списку: обещание, которое никто не меряет, живёт ровно до первой правки. */
  /* Шапка на телефоне встаёт столбиком — вместе с ней и сроки: прижимать их
     к правому краю в один столбец с заголовком значит рвать чтение надвое. */
  .masthead .side{align-items:flex-start; width:100%}
  .deadlines > summary{justify-content:flex-start; min-height:36px; align-items:center}
  .deadlines .one{justify-content:flex-start}
  .deadlines .cap{text-align:left}
  .deadlines .rest{justify-items:start}
  .deadlines .rest li{justify-content:flex-start}
  .btn,.wish-more summary{min-height:36px; display:flex; align-items:center}
  .knob,.tiny,.ed,.rm,.save,.drop{min-height:36px; display:inline-flex; align-items:center}
  .pane{grid-template-columns:1fr}
  .pane .f.wide{grid-column:span 1}
  .stayfine > summary{min-height:44px; align-content:center}
  .more > summary{min-height:44px; padding:13px 2px}
  .rows dd{font-size:12.5px}
  .city .inner,.city .cap{padding-left:16px; padding-right:16px}
}
@media (prefers-reduced-motion:no-preference){
  html{scroll-behavior:smooth}
}
"""

# Математика чека лежит отдельным файлом и уезжает на страницу байт в байт:
# `test/entries.test.mjs` читает тот же файл и гоняет те же строки. Считать
# деньги копией кода, похожей на ту, что у неё на экране, — это два разных
# числа с одним именем.
MONEY_JS = (SITE / "money.js").read_text(encoding="utf-8")


JS = """
(function(){
  "use strict";

  /* Сколько осталось до срока. Считается в браузере, потому что страница
     собирается редко, а «осталось 3 дня» стареет каждые сутки. */
  var DAY = 864e5;
  function plural(n, one, few, many){
    var a = Math.abs(n) % 100, b = a % 10;
    if (a > 10 && a < 20) return many;
    if (b > 1 && b < 5) return few;
    if (b === 1) return one;
    return many;
  }
  /* Номер суток по японскому календарю. Сроки объявлены в JST, и считать их
     надо в нём же: в Европе ещё вечер 24-го, а в Японии уже 25-е. */
  function jstDay(ms){ return Math.floor((ms + 9 * 36e5) / DAY); }

  function leftText(iso){
    /* Срок объявлен по японскому времени; сравниваем в UTC, добавив +09:00. */
    var when = new Date(iso + ":00+09:00");
    if (isNaN(when)) return null;
    /* Прошёл ли срок — по мгновению, точно. А вот «сколько осталось» — по
       календарю, целыми сутками. Раньше здесь стоял `Math.ceil` от разницы
       мгновений, и он давал лишний день: 24 августа до 18 декабря 116 дней,
       а страница говорила 117. Ошибка была в её пользу — то есть в ту
       сторону, в которую на денежном сроке ошибаться нельзя. */
    if (when - Date.now() < 0) return { text: "срок прошёл", soon: true, gone: true };
    var days = jstDay(when.getTime()) - jstDay(Date.now());
    if (days <= 0) return { text: "сегодня последний день", soon: true };
    return {
      text: "осталось " + days + " " + plural(days, "день", "дня", "дней"),
      soon: days <= 30
    };
  }
  Array.prototype.forEach.call(document.querySelectorAll("[data-deadline]"), function(node){
    var iso = node.getAttribute("data-deadline");
    if (!iso) return;
    var left = leftText(iso);
    if (!left) return;
    var tag = document.createElement("span");
    tag.className = "left";
    tag.textContent = left.text;
    node.appendChild(tag);
    if (left.soon) node.classList.add("soon");
    if (left.gone) node.classList.add("gone");
  });

  /* Ближайший срок выбран при сборке, а страница живёт неделями: он может
     пройти раньше, чем её пересоберут. Тогда живые сроки оказались бы спрятаны
     под мёртвым — поэтому мёртвый зачёркивается (класс выше), а список
     раскрывается сам. Ничего не переставляем: подмена самого важного числа на
     глазах хуже, чем открытый список. */
  var head = document.querySelector(".deadlines");
  if (head && head.querySelector("summary .gone")) head.open = true;

  /* Галочки переехали отсюда в хранилище (см. ниже, «её страница»): список,
     который забывает отмеченное при смене телефона, — это список, которому
     нельзя доверить визу. Ключ `japan2027.todo.v1` в localStorage больше не
     пишется и не читается; старое значение, если оно там осталось, просто
     лежит мёртвым грузом и ни на что не влияет. */
})();
"""


# ─────────────────────────────────────────── её страница
#
# Всё, что Ни вписывает сама, живёт в хранилище на сайте, а не в этих файлах:
# сборка стирает `dist/` целиком, и запись, оказавшаяся в собранной странице,
# исчезла бы при первой же пересборке. Поэтому страница приезжает пустой, а
# записи и галочки забирает у `/api/entries` — за той же дверью, тем же
# паролем.
#
# Числа по броням сюда не пересчитываются: они приехали посчитанными в
# `#japan-data`. Здесь только сложение её записей с ними — тем самым
# `money.js`, который лежит выше в этом же теге и проверен тестом.
APP_JS = """
(function(){
  "use strict";
  var box = document.getElementById("japan-data");
  if (!box || !window.JapanMoney) return;
  var data = JSON.parse(box.textContent);
  var API = "/api/entries";
  var THIN = "\\u202f";

  /* «live» — доехали ли до нас её записи. Пока не доехали, страница обязана
     показывать жильё и говорить об этом словами: подпись под числом всегда
     про то число, которое рядом, а не про то, каким оно станет. */
  var state = { entries: [], ticks: {}, live: false, why: "" };
  var editing = null;

  var form = document.querySelector("[data-form]");
  /* Поля берутся только через `elements`: у формы есть собственное свойство
     `title` (это атрибут, а не поле ввода), и `form.title` молча вернул бы
     пустую строку вместо того, что она набрала. */
  function field(name){ return form ? form.elements[name] : null; }
  var says = document.querySelector("[data-form-says]");
  var storeSays = document.querySelector("[data-store-says]");
  var check = document.getElementById("check");
  var capWas = check ? check.querySelector("[data-cap]").textContent : "";

  function el(tag, cls, text){
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }
  function group(n){
    return String(Math.round(Math.abs(n))).replace(/\\B(?=(\\d{3})+(?!\\d))/g, THIN);
  }
  function yen(n){ return "\\u00a5" + group(n); }
  function dollars(n){ return "$" + group(n); }
  /* Введённое ею в долларах показывается ровно так, как введено: пересчёт
     туда и обратно превратил бы её $12,5 в $13, а это её число, не наше. */
  function shownUsd(entry){
    if (entry.currency === "usd") {
      return "$" + String(entry.amount).replace(".", ",");
    }
    return dollars(JapanMoney.usdOf(entry, data.fx));
  }

  var STATE_WORDS = { paid: "уже оплачено", upcoming: "предстоит", onsite: "плачу на месте" };
  var STATE_CLASS = { paid: "paid", upcoming: "due", onsite: "onsite" };
  var MONTHS = ["января","февраля","марта","апреля","мая","июня","июля","августа",
                "сентября","октября","ноября","декабря"];
  function human(iso){
    var bits = /^(\\d{4})-(\\d{2})-(\\d{2})$/.exec(iso || "");
    if (!bits) return "";
    return Number(bits[3]) + "\\u00a0" + MONTHS[Number(bits[2]) - 1];
  }

  /* ── разговор с хранилищем */

  function ask(method, body){
    var init = { method: method, credentials: "same-origin", cache: "no-store" };
    if (body) {
      init.headers = { "content-type": "application/json" };
      init.body = JSON.stringify(body);
    }
    return fetch(API, init).then(function(response){
      return response.json().then(function(said){ return { response: response, said: said }; },
        function(){ return { response: response, said: {} }; });
    }).then(function(got){
      if (!got.response.ok || got.said.ok === false) {
        throw new Error(got.said.why || ("не получилось (" + got.response.status + ")"));
      }
      return got.said;
    });
  }

  /* Ответ на правку — всё состояние целиком, и рисуем мы именно его, а не
     перечитываем список следом: KV догоняет себя не мгновенно, и перечитанное
     может оказаться вчерашним. */
  function adopt(said){
    state.entries = Array.isArray(said.entries) ? said.entries : [];
    state.ticks = said.ticks || {};
    state.live = true;
    state.why = "";
    paint();
  }

  function offline(error){
    state.live = false;
    state.why = error && error.message ? error.message : "нет связи с сайтом";
    paint();
  }

  /* ── рисование */

  function priceTag(entry){
    var tag = el("span", "tab");
    if (JapanMoney.hasPrice(entry)) {
      tag.appendChild(el("b", "usd", shownUsd(entry)));
      tag.appendChild(el("span", "jpy", yen(JapanMoney.yenOf(entry, data.fx))));
    } else {
      /* Пустая цена — подпись, а не ноль: ноль значит «бесплатно». */
      tag.appendChild(el("span", "noprice", "цены нет"));
    }
    var mark = el("span", "chip " + STATE_CLASS[JapanMoney.stateOf(entry)],
                  STATE_WORDS[JapanMoney.stateOf(entry)]);
    tag.appendChild(mark);
    return tag;
  }

  function tools(entry){
    var wrap = el("span", "tools");
    var edit = el("button", "ed", "правка");
    edit.type = "button";
    edit.addEventListener("click", function(){ openForm(entry.kind, entry); });
    var drop = el("button", "rm", "убрать");
    drop.type = "button";
    drop.addEventListener("click", function(){
      if (!window.confirm("Убрать «" + entry.title + "»?")) return;
      ask("DELETE", { id: entry.id }).then(adopt).catch(function(error){
        tell(storeSays, "не убралось: " + error.message);
      });
    });
    wrap.appendChild(edit);
    wrap.appendChild(drop);
    return wrap;
  }

  function placeLine(entry){
    var li = el("li", "own");
    li.setAttribute("data-id", entry.id);
    li.appendChild(el("b", null, entry.title));
    if (entry.note) li.appendChild(el("span", "what", entry.note));
    li.appendChild(priceTag(entry));
    li.appendChild(tools(entry));
    return li;
  }

  function boughtLine(entry){
    var li = el("li", "own");
    li.setAttribute("data-id", entry.id);
    var head = el("span", "head");
    head.appendChild(el("b", null, entry.title));
    if (entry.when) head.appendChild(el("span", "when", human(entry.when)));
    li.appendChild(head);
    if (entry.note) li.appendChild(el("span", "what", entry.note));
    li.appendChild(priceTag(entry));
    li.appendChild(tools(entry));
    return li;
  }

  function todoLine(entry){
    var li = el("li", "own");
    li.setAttribute("data-id", entry.id);
    var label = document.createElement("label");
    var input = document.createElement("input");
    input.type = "checkbox";
    input.checked = entry.done === true;
    input.addEventListener("change", function(){
      ask("PATCH", { id: entry.id, done: input.checked }).then(adopt).catch(function(error){
        input.checked = !input.checked;
        tell(storeSays, "галочка не сохранилась: " + error.message);
      });
    });
    label.appendChild(input);
    label.appendChild(el("span", "tick"));
    var text = el("span", "txt", entry.title);
    if (entry.note || entry.when) {
      var extra = entry.note || "";
      if (entry.when) extra = (extra ? extra + " · " : "") + human(entry.when);
      text.appendChild(el("em", null, extra));
    }
    label.appendChild(text);
    li.appendChild(label);
    li.appendChild(priceTag(entry));
    li.appendChild(tools(entry));
    return li;
  }

  function empty(node){ while (node && node.firstChild) node.removeChild(node.firstChild); }

  function paintEntries(){
    var known = {};
    Array.prototype.forEach.call(document.querySelectorAll("[data-mine]"), function(node){
      empty(node);
      var name = node.getAttribute("data-mine");
      if (name) known[name] = node;
    });

    var orphans = [];
    var byGroup = {};
    Array.prototype.forEach.call(document.querySelectorAll("[data-mine-todo]"), function(node){
      empty(node);
      byGroup[node.getAttribute("data-mine-todo")] = node;
    });
    var boughtList = document.querySelector("[data-mine-booking]");
    empty(boughtList);

    state.entries.forEach(function(entry){
      if (entry.kind === "place") {
        var home = known[entry.stay];
        if (home) home.appendChild(placeLine(entry));
        else orphans.push(entry);
      } else if (entry.kind === "booking") {
        if (boughtList) boughtList.appendChild(boughtLine(entry));
      } else {
        var where = byGroup[entry.group] || byGroup["Ещё"];
        if (where) where.appendChild(todoLine(entry));
      }
    });

    /* Место, чей город исчез из trip.json, показывается отдельно, а не
       пропадает: пропажу никто не заметит, а это её запись. */
    var orphanBox = document.querySelector("[data-orphans]");
    var orphanList = document.querySelector("[data-mine-orphan]");
    if (orphanBox && orphanList) {
      empty(orphanList);
      orphans.forEach(function(entry){ orphanList.appendChild(placeLine(entry)); });
      orphanBox.hidden = orphans.length === 0;
    }

    var spare = document.querySelector("[data-spare]");
    if (spare) spare.hidden = !spare.querySelector("li");

    Array.prototype.forEach.call(document.querySelectorAll("[data-none]"), function(node){
      var card = node.closest(".wishes");
      var mine = card ? card.querySelector("[data-mine]") : null;
      var built = card ? card.querySelector("ul:not(.mine) li") : null;
      node.hidden = !!built || !!(mine && mine.firstChild);
    });
    var noneBought = document.querySelector("[data-none-booking]");
    if (noneBought) noneBought.hidden = !!(boughtList && boughtList.firstChild);
  }

  function paintTicks(){
    Array.prototype.forEach.call(document.querySelectorAll("[data-todo]"), function(input){
      var name = input.getAttribute("data-todo");
      var built = input.getAttribute("data-built") === "true";
      input.checked = Object.prototype.hasOwnProperty.call(state.ticks, name)
        ? state.ticks[name] === true : built;
    });
  }

  function paintFolds(){
    var left = 0;
    Array.prototype.forEach.call(document.querySelectorAll("[data-todo]"), function(input){
      if (!input.checked) left += 1;
    });
    state.entries.forEach(function(entry){
      if (entry.kind === "todo" && entry.done !== true) left += 1;
    });
    var todoTag = document.querySelector('[data-tag="todo"]');
    if (todoTag) todoTag.textContent = left ? left + " не сделано" : "всё отмечено";

    var boughtTag = document.querySelector('[data-tag="bought"]');
    if (boughtTag) {
      var mine = state.entries.filter(function(x){ return x.kind === "booking"; });
      var sum = mine.reduce(function(acc, x){ return acc + JapanMoney.yenOf(x, data.fx); }, 0);
      boughtTag.textContent = mine.length ? mine.length + " · " + yen(sum) : "пусто";
    }
  }

  function tell(node, words){
    if (!node) return;
    node.textContent = words || "";
    node.hidden = !words;
  }

  /* Чек. Пока её записей нет или они не доехали — заголовок говорит «жильё» и
     показывает жильё. Как только записи есть, то же место становится чеком
     всей поездки, и под ним появляется, из чего он сложился: число, которое
     нельзя проверить глазами, — плохое число. */
  function paintCheck(){
    if (!check) return;
    var cap = check.querySelector("[data-cap]");
    var usdNode = check.querySelector("[data-usd]");
    var jpyNode = check.querySelector("[data-jpy]");
    var parts = check.querySelector("[data-parts]");
    var line = check.querySelector("[data-says]");
    var sums = JapanMoney.tally({ fx: data.fx, housing: data.housing, entries: state.entries });
    var mine = state.entries.length;

    empty(parts);
    if (!state.live) {
      cap.textContent = capWas;
      usdNode.textContent = dollars(data.housing.usd);
      jpyNode.textContent = yen(data.housing.jpy);
      paintBar(data.housing);
      parts.hidden = true;
      tell(line, "твои записи не загрузились (" + state.why + ") — здесь только жильё");
      return;
    }
    if (!mine) {
      cap.textContent = capWas;
      usdNode.textContent = dollars(data.housing.usd);
      jpyNode.textContent = yen(data.housing.jpy);
      paintBar(data.housing);
      parts.hidden = true;
      tell(line, "добавь место, бронь или пункт списка — они сразу попадут в этот чек");
      return;
    }

    cap.textContent = "вся поездка · жильё и твои записи";
    usdNode.textContent = dollars(sums.usd);
    jpyNode.textContent = yen(sums.jpy);
    paintBar(sums.states);

    sums.sections.forEach(function(section){
      if (!section.count) return;
      var li = el("li", section.key === "housing" ? "part built" : "part");
      li.appendChild(el("span", "who", section.title));
      li.appendChild(el("b", "num", yen(section.jpy)));
      parts.appendChild(li);
    });
    parts.hidden = false;

    var words = [];
    if (sums.priceless) {
      words.push(sums.priceless + " "
        + (sums.priceless === 1 ? "запись" : (sums.priceless < 5 ? "записи" : "записей"))
        + " без цены — в сумму не входят");
    }
    words.push("сложено из показанного: " + yen(data.housing.jpy) + " жильё и твои записи");
    tell(line, words.join(" · "));
  }

  function paintBar(states){
    var total = states.paid + states.upcoming + states.onsite;
    ["paid", "upcoming", "onsite"].forEach(function(name){
      var seg = check.querySelector('[data-seg="' + name + '"]');
      var num = check.querySelector('[data-money="' + name + '"]');
      if (seg) seg.style.width = total ? (states[name] / total * 100).toFixed(1) + "%" : "0";
      if (num) num.textContent = yen(states[name]);
    });
  }

  function paint(){
    paintEntries();
    paintTicks();
    paintFolds();
    paintCheck();
    if (state.live) tell(storeSays, "");
  }

  /* ── форма */

  function fields(kind){
    Array.prototype.forEach.call(form.querySelectorAll("[data-only]"), function(node){
      node.hidden = node.getAttribute("data-only").split(" ").indexOf(kind) < 0;
    });
  }

  function openForm(kind, entry){
    if (!form) return;
    editing = entry ? entry.id : null;
    form.hidden = false;
    form.setAttribute("data-kind", kind);
    fields(kind);
    var what = { place: "место", booking: "бронь или билет", todo: "пункт списка" }[kind];
    form.querySelector("[data-form-what]").textContent =
      (entry ? "Правка: " : "Новое — ") + what;
    field("title").value = entry ? entry.title : "";
    field("note").value = entry && entry.note ? entry.note : "";
    field("amount").value = entry && JapanMoney.hasPrice(entry) ? String(entry.amount) : "";
    field("currency").value = entry && entry.currency ? entry.currency : "jpy";
    field("state").value = entry ? JapanMoney.stateOf(entry) : JapanMoney.stateOf({ kind: kind });
    if (kind === "place" && field("stay")) {
      field("stay").value = entry && entry.stay ? entry.stay : field("stay").options[0].value;
    }
    if (field("when")) field("when").value = entry && entry.when ? entry.when : "";
    if (field("group")) field("group").value = (entry && entry.group) || "Ещё";
    tell(says, "");
    field("title").focus();
  }

  function closeForm(){
    editing = null;
    if (form) { form.hidden = true; form.reset(); }
  }

  Array.prototype.forEach.call(document.querySelectorAll("[data-add]"), function(button){
    button.addEventListener("click", function(){
      var kind = button.getAttribute("data-add");
      openForm(kind, null);
      if (kind === "place" && button.getAttribute("data-stay") && field("stay")) {
        field("stay").value = button.getAttribute("data-stay");
      }
      form.scrollIntoView({ block: "center", behavior: "smooth" });
    });
  });

  var cancel = form ? form.querySelector("[data-cancel]") : null;
  if (cancel) cancel.addEventListener("click", closeForm);

  if (form) form.addEventListener("submit", function(event){
    event.preventDefault();
    var kind = form.getAttribute("data-kind");
    var body = {
      kind: kind,
      title: field("title").value,
      note: field("note").value,
      amount: field("amount").value,
      currency: field("currency").value,
      state: field("state").value
    };
    if (kind === "place") body.stay = field("stay").value;
    else body.when = field("when").value;
    if (kind === "todo") body.group = field("group").value;

    var save = form.querySelector(".save");
    var was = editing;
    save.disabled = true;
    tell(says, "сохраняю…");
    var sending = was ? ask("PATCH", Object.assign({ id: was }, body)) : ask("POST", body);
    sending.then(function(said){
      adopt(said);
      closeForm();
      var fold = document.querySelector('[data-fold="' + (kind === "booking" ? "bought" : "todo") + '"]');
      if (kind !== "place" && fold) fold.open = true;
      var fresh = document.querySelector('[data-id="' + (was || freshest(said, kind)) + '"]');
      if (fresh) {
        fresh.classList.add("fresh");
        fresh.scrollIntoView({ block: "center", behavior: "smooth" });
        window.setTimeout(function(){ fresh.classList.remove("fresh"); }, 2000);
      }
    }).catch(function(error){
      tell(says, error.message);
    }).then(function(){ save.disabled = false; });
  });

  function freshest(said, kind){
    var mine = (said.entries || []).filter(function(x){ return x.kind === kind; });
    return mine.length ? mine[mine.length - 1].id : "";
  }

  /* ── галочки на пунктах из trip.json */

  Array.prototype.forEach.call(document.querySelectorAll("[data-todo]"), function(input){
    input.addEventListener("change", function(){
      ask("PATCH", {
        tick: input.getAttribute("data-todo"),
        done: input.checked,
        built: input.getAttribute("data-built") === "true"
      }).then(adopt).catch(function(error){
        input.checked = !input.checked;
        tell(storeSays, "галочка не сохранилась: " + error.message);
      });
    });
  });

  var reset = document.querySelector("[data-reset]");
  if (reset) reset.addEventListener("click", function(){
    var names = Object.keys(state.ticks);
    if (!names.length) return;
    if (!window.confirm("Снять все отмеченные галочки? Это видно на всех устройствах.")) return;
    var chain = Promise.resolve();
    names.forEach(function(name){
      var input = document.querySelector('[data-todo="' + name.replace(/"/g, '\\\\"') + '"]');
      var built = input ? input.getAttribute("data-built") === "true" : false;
      chain = chain.then(function(){
        return ask("PATCH", { tick: name, done: built, built: built });
      });
    });
    chain.then(adopt).catch(function(error){
      tell(storeSays, "не сбросилось: " + error.message);
    });
  });

  /* ── первый вдох */

  paint();
  ask("GET").then(adopt).catch(function(error){
    offline(error);
    tell(storeSays, "записи не загрузились: " + error.message);
  });
})();
"""


# ─────────────────────────────────────────── страница

def render(trip: dict) -> str:
    stays = sorted(trip["stays"], key=lambda s: (s["checkin"]["date"], s["checkout"]["date"]))
    alerts = trip.get("alerts", [])
    places = trip.get("places", [])
    all_legs = legs(stays)
    t = trip["trip"]
    nights = (d(t["end"]) - d(t["start"])).days

    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex, nofollow, noarchive">
<meta name="theme-color" content="#f2eee7">
<title>{e(t["title"])} {e(t["year"])} — {e(t["subtitle"])}</title>
<style>{CSS}</style>
</head>
<body style="--nights:{nights}">
<div class="sheet">
  {masthead(trip, stays, all_legs)}
  {thread(trip, all_legs)}
  {alert_block(alerts)}
  {city_cards(all_legs, alerts, places, trip.get("cancelled", []))}
  {adder(trip, all_legs)}
  {ledger(trip, stays, all_legs)}
  {more_block(trip, stays, alerts)}
  {colophon(trip)}
</div>
{island(trip, stays, all_legs)}
<script>{MONEY_JS}
{JS}
{APP_JS}</script>
</body>
</html>
"""


NOT_FOUND = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow"><title>Не туда</title>
<style>:root{color-scheme:light}
body{margin:0;height:100vh;display:grid;place-items:center;background:#f7f3ec;
color:#1e1b18;font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;text-align:center}
a{color:#2f4b7c}
</style></head><body><div><p style="font-size:44px;margin:0;font-family:Georgia,serif">迷</p>
<p>Такой страницы здесь нет.</p><p><a href="/">На главную</a></p></div></body></html>
"""


def write_stays(all_legs: list) -> list[str]:
    """Список городов, к которым можно привязать место, — для двери.

    Ручка `/api/entries` обязана уметь отказать месту, повешенному на город,
    которого на странице нет: иначе запись ляжет в хранилище и **тихо не
    покажется** — ровно то, от чего в `check()` стоит правило №6.

    Проверять это по `trip.json` ручка не может: на Cloudflare рядом с ней
    нет ни файла с данными, ни питона. Поэтому список выкладывается сюда
    сборкой — как `_cards.js` у вишлиста — и лежит в git видимым куском, а не
    угадывается в рантайме.

    Здесь ровно те же ключи, что и у мешков `data-mine` на странице: город
    сливает соседние брони в один отрезок, и место цепляется к первой из них.
    Совпадение этих двух списков — не совпадение, а условие: принятая запись
    обязана иметь, куда показаться.
    """
    ids = [leg["stays"][0]["id"] for leg in all_legs]
    body = json.dumps(ids, ensure_ascii=False)
    (SITE / "functions" / "api" / "_stays.js").write_text(
        "/* Собирается `build.py` — руками не править.\n"
        "\n"
        "   Города, к которым можно привязать место. Список тот же, что у мешков\n"
        "   `data-mine` на собранной странице: запись, принятая ручкой, обязана\n"
        "   иметь, куда показаться. */\n"
        f"\nexport const STAYS = {body};\n",
        encoding="utf-8",
    )
    return ids


def main() -> int:
    trip = json.loads(DATA.read_text(encoding="utf-8"))
    load_fx(trip)

    try:
        said = check(trip)
    except Failed as err:
        print(f"✗ проверка не прошла: {err}", file=sys.stderr)
        return 1
    for line in said:
        print("·", line)

    if "--check" in sys.argv:
        print("✓ только проверка, ничего не собрано")
        return 0

    # Список городов для двери — до копирования функций: иначе в выложенную
    # папку уедет вчерашний, и место, привязанное к новому городу, будет
    # отбито ручкой как несуществующее.
    ids = write_stays(legs(sorted(trip["stays"],
                                  key=lambda s: (s["checkin"]["date"], s["checkout"]["date"]))))
    print("· города, к которым можно привязать место: " + ", ".join(ids))

    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)

    (DIST / "index.html").write_text(render(trip), encoding="utf-8")
    (DIST / "404.html").write_text(NOT_FOUND, encoding="utf-8")

    # Дверь и заголовки едут внутрь выкладываемой папки: wrangler собирает
    # functions/ из текущего каталога, а не из проекта. Забыть это — значит
    # выложить страницу без замка (см. deploy.sh).
    shutil.copytree(SITE / "functions", DIST / "functions")
    for name in ("_routes.json", "_headers", "robots.txt"):
        shutil.copy(SITE / name, DIST / name)

    # Три вида, по которым Ни выбирала главную, живут по адресу /vidy/. Сборка
    # стирает dist/ целиком, поэтому положенное туда руками исчезает молча —
    # и ссылка, уже отданная ей, ломается следующей же выкладкой. Их место —
    # в site/, рядом с дверью и заголовками.
    if (SITE / "vidy").is_dir():
        shutil.copytree(SITE / "vidy", DIST / "vidy")

    size = sum(f.stat().st_size for f in DIST.rglob("*") if f.is_file())
    pages = len(list(DIST.rglob("*.html")))
    print(f"✓ собрано в dist/ — {pages} страницы, {size / 1024:.0f} КБ, "
          f"дверь на месте ({len(list((DIST / 'functions').rglob('*.js')))} файла)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
