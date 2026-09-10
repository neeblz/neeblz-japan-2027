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
# План по дням лежит отдельным файлом, а не разделом `trip.json`, потому что у
# него другой хозяин. В `trip.json` — брони, деньги и сроки: их вносит Блэйз, и
# страница их только показывает. Здесь — засев расстановки: первое наполнение
# хранилища, после которого порядок принадлежит Ни и живёт в KV. Держать рядом
# то, что она двигает, и то, чего ей двигать нельзя, — значит рано или поздно
# перепутать, кто чей текст переписал.
PLAN_DATA = HERE / "data" / "days-plan.json"
# Справка внизу — виза, документы, такс-фри. Отдельный файл по той же причине,
# что и план: другой хозяин и другая природа. В `trip.json` — её брони и её
# деньги; здесь — внешние правила, которые никто из нас не назначает и которые
# устаревают сами. У каждого пункта записано, откуда он взят, и страница обязана
# это показать: см. `ref_item`.
REF_DATA = HERE / "data" / "reference.json"
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
    """Доллар крупно, иена рядом справочно — её порядок, не наш.

    `data-yen` — та же сумма в иенах числом. Она нужна браузеру, когда курс
    приезжает свежим: пересчитать доллар из иены он может, а вытащить иену
    обратно из «$807» — нет. Иена здесь и есть настоящая цена, доллар всегда
    производный.
    """
    return (f'<b class="usd" data-yen="{amount}">{usd(amount)}</b>'
            f'<span class="jpy">{yen(amount)}</span>')


def maplink(address: str) -> str:
    from urllib.parse import quote
    return "https://www.google.com/maps/search/?api=1&query=" + quote(address)


def tellink(phone: str) -> str:
    return "tel:" + re.sub(r"[^\d+]", "", phone)


def load_plan() -> list:
    """Дни из `days-plan.json` — только сами дни, без записок самому себе.

    Ключи с подчёркивания в этом файле — объяснения полей, а `book_list` — её
    собственный список «что обязательно бронировать», нужный сборке для сверки
    полноты, а не странице. Наружу отсюда уходит один список дней.
    """
    return json.loads(PLAN_DATA.read_text(encoding="utf-8"))["days"]


def load_reference() -> dict:
    """Справка целиком: блоки и дата проверки.

    Ключи с подчёркивания здесь — записки самим себе, как и в плане по дням.
    Наружу уходит весь словарь: странице нужны и блоки, и `checked` — правила
    меняются, а страница живёт месяцами, и цифра без даты через полгода
    читается как сегодняшняя.
    """
    return json.loads(REF_DATA.read_text(encoding="utf-8"))


# ─────────────────────────────────────────── проверки

class Failed(Exception):
    pass


def check(trip: dict, plan: list | None = None) -> list[str]:
    """Сверить то, что страница покажет, с тем, что в неё положено.

    Проверяется не оформление, а четыре вещи, в которых ошибка стоит денег:
    непрерывность дат, ночи против календаря, суммы против разбивки по оплате
    и то, что наложение 14-го никуда не делось.

    План по дням проверяется здесь же (правила 11–14), а не отдельным
    инструментом: его id — ключи, по которым хранилище узнаёт передвинутое, и
    сломанный id стоит дороже сломанной вёрстки. Молчаливая пропажа пункта
    выглядит на странице ровно как пункт, который она сама убрала.
    """
    said = []
    plan = load_plan() if plan is None else plan
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
    #    Срок может отсутствовать вовсе: 10 сентября Ни велела убрать условия
    #    отмены OMO3 — «она мне больше не нужна». Бронь без срока не молчит по
    #    ошибке, она названа вслух отдельной строкой.
    today = date.today()
    dated = [s for s in stays if s.get("cancel")]
    for s in dated:
        cutoff = datetime.fromisoformat(s["cancel"]["free_until"])
        if cutoff.date() < today:
            said.append(f'⚠ {s["name"]}: бесплатная отмена уже прошла ({cutoff.date()})')
    for s in stays:
        if not s.get("cancel"):
            said.append(f'срок отмены не показываем: {s["name"]} — так решила Ни')
    # Ближайший срок называется вслух при каждой сборке: он стоит в шапке
    # страницы, и если шапка вдруг покажет не тот — это будет видно здесь же.
    if dated:
        soonest = min(dated, key=lambda s: s["cancel"]["free_until"])
        said.append(f'ближайший срок отмены: {soonest["cancel"]["free_until"][:10]} — '
                    f'{soonest["name"]}, {yen(soonest["total_jpy"])}')
    else:
        said.append("сроков отмены на странице нет ни у одной брони")

    # 6. Место из вишлиста висит на брони. Опечатка в «stay» — это место,
    #    привязанное к городу, которого в поездке нет.
    #
    #    24 августа правило перестало сторожить показ: блок «хочу сходить» ушёл
    #    из карточек городов, и `places` рисуется теперь только в днях, по имени.
    #    `stay` осталось единственной строчкой, связывающей место с городом, и
    #    её никто не читает — а значит сломаться она может молча и лежать
    #    сломанной до того дня, когда её снова начнут читать. Правило стоит
    #    ровно за этим и стоит дёшево; тихой пропажей на странице заведует
    #    теперь `placeLine`, который пишет «город не найден» прямо в строке.
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

    # 9. Служба доставки названа ровно один раз — в `luggage.service`.
    #
    #    Ни 2026-08-24: «мы в трёх местах пишем про багаж и нигде не указываем
    #    сайт». Собрать это в один блок — работа на полчаса; удержать собранным
    #    — работа навсегда, потому что следующая правка так же естественно
    #    допишет «Yamato» в подробности отеля, как естественно оно там и
    #    появилось. Дублируется при этом не слово, а цена и условия: расходятся
    #    они молча, а замечаются в чужой стране на стойке.
    #
    #    Ссылка проверяется по форме, а не по доброте: без https и без подписи
    #    она превращается в ту самую ссылку, которая ничего не называет.
    svc = trip["luggage"]["service"]
    if not svc.get("site", "").startswith("https://") or not svc.get("site_label"):
        raise Failed("у службы доставки должна быть https-ссылка и подпись к ней")
    elsewhere = json.dumps(
        {k: (v if k != "luggage" else {x: y for x, y in v.items() if x != "service"})
         for k, v in trip.items() if not k.startswith("_")},
        ensure_ascii=False,
    )
    for word in (svc["name"].split()[0], "TA-Q-BIN", "宅急便"):
        if re.search(re.escape(word), elsewhere, re.I):
            raise Failed(f'«{word}» названо не только в `luggage.service` — '
                         "про багаж мы уже писали в трёх местах")
    said.append(f'чемодан везёт {svc["name"]}, {svc["product"]} — '
                f'{trip["luggage"]["cost"]}')

    # 10. Никаких секретов в данных. Ключи с подчёркивания — записки самому
    #    себе о том, чего сюда класть нельзя; они перечисляют запретные слова
    #    и поэтому в досмотр не идут, иначе инструкция запрещала бы сама себя.
    #
    #    План по дням досматривается вместе с бронями: он такой же git-файл и
    #    такая же выкладываемая страница, а «личного на странице нет» — правило
    #    про страницу целиком, а не про один её файл.
    blob = json.dumps(
        [{k: v for k, v in trip.items() if not k.startswith("_")}, plan], ensure_ascii=False
    )
    for pattern, what in (
        (r"\b[\w.+-]+@[\w-]+\.[\w.]+\b", "почта"),
        (r"\b(?:\d[ -]?){13,19}\b", "похоже на номер карты"),
        (r"(?i)\b(pin|пин|password|пароль|booking\s*(no|number)|номер\s*брони)\b", "слово про доступ"),
    ):
        hit = re.search(pattern, blob)
        if hit:
            raise Failed(f"в данных {what}: {hit.group(0)!r} — это не должно попасть в git")

    # 11. Раздела `days` в `trip.json` больше нет и заводить его заново нельзя.
    #    Два заголовка на одну дату в двух файлах — это второй экземпляр той же
    #    вещи; расходятся такие молча, а замечаются в чужой стране.
    if "days" in trip:
        raise Failed("в trip.json снова завёлся раздел `days` — план по дням "
                     "живёт в data/days-plan.json, а порядок пунктов в хранилище")

    # 12. Каждый день плана — настоящий день поездки, и каждый день поездки в
    #    плане есть. День, которого нет в плане, — это дырка, которую нечем
    #    показать; день мимо поездки — пункт, который она не найдёт нигде.
    want = []
    day = start
    while day <= end:
        want.append(day.isoformat())
        day += timedelta(days=1)
    got = [x["date"] for x in plan]
    if got != want:
        raise Failed(f"дни плана не совпали с днями поездки: {len(got)} против {len(want)}, "
                     f"первое расхождение {next((a for a, b in zip(got + [None] * len(want), want) if a != b), '—')}")

    # 13. id пунктов вечные и потому обязаны быть неповторимыми: по ним
    #    хранилище узнаёт передвинутое. Два пункта с одним id — это два пункта,
    #    которые ходят парой и удаляются вместе, причём молча.
    seen, count = {}, 0
    for day_plan in plan:
        for item in day_plan["items"]:
            count += 1
            if not item.get("id"):
                raise Failed(f'{day_plan["date"]}: пункт «{item.get("title", "?")}» без id')
            if item["id"] in seen:
                raise Failed(f'id {item["id"]} встречается дважды — '
                             f'{seen[item["id"]]} и {day_plan["date"]}')
            seen[item["id"]] = day_plan["date"]
            if not item.get("title", "").strip():
                raise Failed(f'{day_plan["date"]}: пункт {item["id"]} без названия')

    # 14. Ссылки и отсылки. Сайт — только https и только у того, у кого он
    #    правда есть; место — из `places`, чтобы адрес жил в одном месте, а не
    #    в двух; переезд — на дне, где по броням действительно едут.
    known_places = {p["title"]: p for p in trip.get("places", [])}
    slugs = {"Токио": "tokyo", "Киото": "kyoto", "Киносаки": "kinosaki"}
    hop_dates = {t["date"] for t in trip.get("transfers", [])}
    sites, linked, spots = 0, 0, 0
    for day_plan in plan:
        for item in day_plan["items"]:
            if item.get("site"):
                if not item["site"].startswith("https://"):
                    raise Failed(f'{item["id"]}: сайт «{item["site"]}» не https')
                sites += 1
            if item.get("place"):
                place = known_places.get(item["place"])
                if not place:
                    raise Failed(f'{item["id"]}: места «{item["place"]}» нет в `places` — '
                                 "ссылку взять неоткуда")
                if item.get("site"):
                    raise Failed(f'{item["id"]}: и `place`, и свой `site` — '
                                 "адрес обязан жить в одном месте")
                linked += 1
            if item.get("transfer"):
                parts = item["transfer"].split("-")
                if len(parts) != 2 or not all(p in slugs.values() for p in parts):
                    raise Failed(f'{item["id"]}: переезд «{item["transfer"]}» '
                                 "называет город, которого в поездке нет")
                if day_plan["date"] not in hop_dates:
                    raise Failed(f'{item["id"]}: переезд стоит на {day_plan["date"]}, '
                                 "а по броням в этот день никто никуда не едет")

            # 15. Разбивка названия по местам. Ссылка вешается на кусок самого
            #    названия — значит каждое имя обязано в нём найтись, и найтись
            #    по порядку. Имя мимо строки не покраснело бы нигде: место
            #    просто осталось бы без ссылки, а это ровно та тихая пропажа,
            #    от которой стоит правило №6.
            at = 0
            for spot in item.get("spots", []):
                name = (spot.get("name") or "").strip()
                if not name:
                    raise Failed(f'{item["id"]}: место в разбивке без названия')
                found = item["title"].find(name, at)
                if found < 0:
                    raise Failed(f'{item["id"]}: места «{name}» нет в названии '
                                 f'«{item["title"]}» — или оно стоит там раньше '
                                 "предыдущего")
                at = found + len(name)
                if spot.get("map") and spot.get("place"):
                    raise Failed(f'{item["id"]}: у места «{name}» и карта, и `place` — '
                                 "адрес обязан жить в одном месте")
                if spot.get("place"):
                    known = known_places.get(spot["place"])
                    if not known:
                        raise Failed(f'{item["id"]}: места «{spot["place"]}» нет в '
                                     "`places` — ссылку взять неоткуда")
                    if not known.get("site"):
                        raise Failed(f'{item["id"]}: у места «{spot["place"]}» в '
                                     "`places` нет сайта — ссылке некуда вести")
                elif not spot.get("map"):
                    raise Failed(f'{item["id"]}: у места «{name}» нечего открыть — '
                                 "ни карты, ни `place`")
                spots += 1

    # Её собственный список «что бронировать» — сверка полноты: пункт из него,
    # потерявший свой id при разборе, иначе исчез бы молча.
    for line in json.loads(PLAN_DATA.read_text(encoding="utf-8")).get("book_list", []):
        for key in ("item", "also"):
            if line.get(key) and line[key] not in seen:
                raise Failed(f'в списке «что бронировать» указан пункт {line[key]}, '
                             f'а такого в плане нет — «{line["what"]}» потерялось при разборе')

    said.append(f"план по дням: {len(plan)} дней, {count} пунктов, "
                f'{sites} {plural(sites, "свой сайт", "своих сайта", "своих сайтов")} '
                f'и {linked} {plural(linked, "ссылка", "ссылки", "ссылок")} из `places`; '
                f'{spots} {plural(spots, "место разбито", "места разбиты", "мест разбито")} '
                "по строкам")

    # 16. Перелёт посчитан ровно один раз — её записью в чеке.
    #
    #     Это единственное на странице, что умеет испортить её деньги молча.
    #     Билет куплен и стоит в чеке записью «Перелёт, $1 222,10, оплачено»;
    #     сборка его не складывает и сложить не может — но она может показать
    #     его ещё раз словом. «Перелёт» в списке «ещё не посчитано» или в
    #     строке «чего в итоге нет» — это второй счёт того же билета, только
    #     с обратным знаком: одно место говорит «заплачено», другое «впереди».
    #
    #     Проверяется поэтому не сложение (складывать нечего), а именно слово:
    #     ошибиться здесь можно только в данных, и стоит эта ошибка ровно
    #     столько же, сколько ошибка в сложении.
    fly = trip.get("flights")
    if fly:
        out, back = flight_legs(trip)
        if not out or not back:
            raise Failed("у перелёта должны быть оба плеча — «туда» и «обратно»")
        if d(out["date"]) != start:
            raise Failed(f'вылет {out["date"]}, а поездка начинается {start}')
        if d(back["date"]) != end:
            raise Failed(f'обратный рейс {back["date"]}, а поездка кончается {end}')
        for leg in (out, back):
            if not leg.get("hops"):
                raise Failed(f'плечо «{leg["dir"]}»: нет ни одного рейса')
        if fly.get("rules", {}).get("free_cancel") is not False:
            raise Failed("у билета появилась бесплатная отмена — тогда ей нужен срок, "
                         "и он обязан встать к срокам отелей, а не остаться словом")
        counted = [x for x in trip.get("not_in_total", [])
                   + [u["label"] for u in trip.get("unknown", [])]
                   if "перелёт" in x.lower() or "перелет" in x.lower()]
        if counted:
            raise Failed(f'перелёт посчитан её записью в чеке, а «{counted[0]}» говорит '
                         "обратное — это то же число второй раз, только с другим знаком")
        said.append(f'перелёт: {port(out, "from")} → {port(out, "to")} {out["date"]}, '
                    f'{port(back, "from")} → {port(back, "to")} {back["date"]}; '
                    f'{fly["carrier"]}, в чеке — её записью, сборка его не складывает')

    said.append(f"броней {len(stays)}, ночей {len(nights)}, дней {(end - start).days + 1}")
    return said


def check_reference(ref: dict | None = None) -> list[str]:
    """Пересчитать справку вслух: сколько фактов, сколько догадок, чьих.

    Само правило «непроверенное не рисуется как факт» живёт не здесь, а в
    `ref_item`: проверка, которую можно забыть позвать, и отсутствие проверки
    выглядят снаружи одинаково, а рендер забыть нельзя. Здесь — счёт, который
    печатается при сборке, чтобы догадка, тихо ставшая фактом, была видна в
    выводе, а не только в тесте.

    Заодно ловится обратное: раздел, где не подтверждено вообще ничего.
    Три непроверенных пункта про визу — не оговорка на всякий случай, а
    следствие того, что сайт посольства отвечает нашему серверу 403; день,
    когда они молча станут фактами, обязан быть заметен.
    """
    ref = load_reference() if ref is None else ref
    said, total = [], 0
    for block in ref["blocks"]:
        facts = sum(1 for i in block["items"] if i.get("verified") is True)
        unsure = sum(1 for i in block["items"] if i.get("verified") is False)
        mine = sum(1 for i in block["items"] if i.get("mine") is True)
        if facts + unsure + mine != len(block["items"]):
            raise Failed(f'справка, блок «{block["id"]}»: у пункта нет происхождения')
        total += len(block["items"])
        said.append(f'справка, {block["title"].lower()}: {facts} подтверждено, '
                    f"{unsure} нет, {mine} от нас")
    # Дата проверки — не украшение: правила меняются, а страница живёт
    # месяцами, и цифра без даты через полгода читается как сегодняшняя.
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", ref.get("checked", "")):
        raise Failed("у справки нет даты проверки")
    said.append(f'справка: {total} пунктов, проверена {ref["checked"]}')
    return said


# ─────────────────────────────────────────── цвета и отрезки

# Цвет — единственное, что здесь не из данных: незабудка Гиндзы, слива Киото,
# вода Киносаки, глициния Асакусы. Новый город получит цвет из запаса, а не
# исчезнет с картинки.
#
# У города здесь **пара**, а не цвет: тон — светлая плоскость, чернила — тот
# же оттенок, доведённый до темноты. Так вышло из просьбы Ни 24 августа
# сделать тона пастельными, «чтобы чуть мимимишнее». Одной заменой цвета это
# не делается: на тонах лежал белый текст — название города в шапке карточки и
# «4 ночи» в нитке, — а пастель белое не держит физически, светлое на светлом.
# Значит меняется пара: плоскость посветлела, текст на ней стал тёмным.
# Белого на тонах не осталось нигде.
#
# Число рядом — контраст чернил к своему тону, и он посчитан для новой пары, а
# не унаследован от прежней. Порог здесь 7:1: самый строгий текст на тоне —
# название города в карточке, 21px, то есть ещё не «крупный» по WCAG и живёт
# под общим потолком, а не под поблажкой.
#
# Там, где цвет города рисует не плоскость, а линию — полоса «оплачено с…» и
# полоска слева в разделе дней, — берутся **чернила**: пастельная линия на
# светлой бумаге пропадает совсем (1.2:1 к бумаге против 10.5:1 у чернил).
#
# Четыре тона — четыре разных тона, а не четыре оттенка одного розового: их
# цветовые углы разведены (214°, 325°, 164°, 256°), и по цвету опознаётся и
# карточка, и отрезок нитки. Все они холоднее и бледнее, чем `--hot`: яркое на
# странице носит смысл — горящий срок, неоплаченное, «бронировать», — и
# города не должны к нему подбираться.
TONES = {
    ("Токио", "Гиндза"): ("#C1D5F0", "#1A355B"),    # 8.2:1 — незабудка
    ("Киото", "Сандзё"): ("#F1C8E0", "#5D1D42"),    # 8.2:1 — цветущая слива
    ("Киносаки", "онсэн"): ("#B7E4D8", "#0E3C35"),  # 8.8:1 — вода
    ("Токио", "Асакуса"): ("#D8CEF3", "#3A296B"),   # 8.2:1 — глициния
}
# Запас на пятый город — в той же пастели. Последняя пара нарочно почти без
# цвета: ею красится отрезок «в воздухе», у которого города нет.
SPARE = [
    ("#C1D5F0", "#1A355B"), ("#F1C8E0", "#5D1D42"),
    ("#B7E4D8", "#0E3C35"), ("#D8CEF3", "#3A296B"),
    ("#CDD3E1", "#253553"),  # 8.2:1 — пасмурный, без города
]


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
        leg["tone"], leg["ink"] = TONES.get((leg["city"], leg["area"]),
                                            SPARE[i % len(SPARE)])
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


def flight_legs(trip: dict) -> tuple[dict | None, dict | None]:
    """Два плеча перелёта — туда и обратно, по слову в самих данных.

    Возвращается пара, а не список: страница спрашивает у неё разные вещи в
    разных местах (вылет — в начале нитки, аэропорт возвращения — в её конце),
    и перебирать список ради «того, который туда» пришлось бы четырежды.
    """
    fly = trip.get("flights") or {}
    by_dir = {leg.get("dir"): leg for leg in fly.get("legs", [])}
    return by_dir.get("туда"), by_dir.get("обратно")


def port(leg: dict, side: str) -> str:
    """Аэропорт плеча, если он назван, иначе город.

    Названия аэропортов стоят в данных только там, где они что-то решают:
    Нарита и Ханэда — это два разных конца Токио, и путать их дорого. У
    Тбилиси аэропорт один, и звать его по имени значило бы заставлять её
    вспоминать, тот ли это, из которого она летит.
    """
    return leg.get(f"{side}_airport") or leg[side]


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
    # Бронь без `cancel` в этот список не попадает вовсе: Ни убрала условия
    # отмены OMO3, и «срока нет» не должно читаться как «срок сегодня».
    order = sorted((s for s in stays if s.get("cancel")),
                   key=lambda s: s["cancel"]["free_until"])
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
    out, back = flight_legs(trip)

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
        # Час вылета — на самом отрезке, той же меткой, что часы заезда у
        # городов: ночь в воздухе начинается не в полночь.
        clock = (f'<span class="edge i">{e(out["dep"])}</span>'
                 if out and d(out["date"]) == when else "")
        bars.append(
            f'<div class="bar air" style="{col(when)}">{clock}'
            f'<span class="n">{e(leg["title"].lower())}</span></div>'
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
            f'<div class="bar" style="{col(leg["sleep_from"], n)};'
            f'background:{leg["tone"]};color:{leg["ink"]}">'
            f'<span class="edge i">{e(leg["checkin"].replace(" — ", "–"))}</span>{checkout}'
            f'<span class="who">{e(leg["city"])} · {e(leg["area"])}</span>'
            f'<span class="n">{n} {plural(n, "ночь", "ночи", "ночей")}</span></div>'
        )

    # Последний столбец — день отъезда. Аэропорт вылета стоит прямо на нём:
    # прилетает она в Нариту, а улетает из Ханэды, и в последний день это не
    # мелочь, а разница в дороге из Асакусы.
    home_air = (f'<span class="air">{e(back.get("from_airport") or back["from"])} '
                f'{e(back["dep"])}</span>' if back else "")
    bars.append(
        f'<div class="home" style="grid-column:{total + 1}">'
        f'<b>{end.day}</b><span>домой</span>{home_air}</div>'
    )

    # Полоса «оплачено шире, чем прожито». Рисуется только там, где эти два
    # числа разошлись, и говорит словами из данных, а не из головы.
    paid = []
    for leg in all_legs:
        if leg["paid_from"] >= leg["sleep_from"]:
            continue
        why = leg["stays"][-1].get("arriving", {}).get("why", "")
        # Цвет города идёт в `color`, а не в `background`: полоса рисуется косой
        # штриховкой по currentColor и обведена рамкой. Так «оплачено, но не
        # прожито» отличается от прожитого фактурой, а не оттенком — на плохом
        # экране оттенок первым и пропадает.
        #
        # Здесь берутся чернила, а не тон: тон стал пастельным, а пастельная
        # штриховка на светлой бумаге — 1.2:1, то есть полосы не видно вовсе.
        paid.append(
            f'<div class="paidbar" style="{col(leg["paid_from"], leg["paid_nights"])};'
            f'color:{leg["ink"]}"><span>оплачено с {day_month(leg["paid_from"].isoformat())}'
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

    # Перелёт — первой и последней меткой нитки. До этого линия начиналась
    # прямо с города: она возникала в Токио, а домой уезжала в пустоту за
    # правым краем. Плечо названо аэропортами, а не городом, потому что они
    # разные — Нарита туда, Ханэда обратно, — и видно это должно быть без
    # раскрытия. Подробности рейсов живут ниже, под стрелкой.
    flights_at = {}
    for leg in (out, back):
        if not leg:
            continue
        when = d(leg["date"])
        flights_at[when] = leg
        text = f'{port(leg, "from")} → {port(leg, "to")}'
        if when == end:
            marks[-1] = (when, text)
        else:
            marks.insert(0, (when, text))

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
        # Перелёт в нитке говорит только «сколько лететь и с пересадкой ли»:
        # столбец здесь шириной в один день, а номера рейсов, самолёты и багаж
        # ждут под стрелкой ниже. Цены нет нарочно — она стоит в чеке её
        # записью, и второе число рядом с первым читалось бы как ещё одна трата.
        air = flights_at.get(when)
        if air:
            detail = f'<span class="ride"><span class="hrs">{e(air["hours"])}</span></span>'
        klass = "move has fly" if air else ("move has" if ride else "move")
        moves.append(
            f'<div class="{klass}" style="{col(when, max(room, 1))}">'
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
    """Ночь, на которой сошлись две брони, — и только пока это вопрос.

    Тон задаёт `level`. «red» — вопрос, на который она ещё не ответила: сирена
    и варианты. «calm» — она уже ответила, и блок превращается в напоминание
    по решённому: Ни 2026-08-24, «блок **как задумано** убивай, он действует
    на нервы и мешается». Спокойный блок больше не рисуется вовсе — ни под
    стрелкой, ни мелким шрифтом.

    Убран **показ, а не данные**. Наложение по-прежнему обязано быть помечено
    в `trip.json`, и сборка падает, если его убрать (см. check, правила 3–5):
    молчаливая пропажа оплаченной ночи стоит денег, а спокойная заметка про
    неё не стоила ничего, кроме её нервов. Красный блок остаётся — прятать
    вопрос, на который она не ответила, значит прятать его от неё же.
    """
    if not alerts:
        return ""
    out = []
    for a in alerts:
        red = a["level"] == "red"
        if not red:
            continue
        facts = "".join(f"<li>{e(x)}</li>" for x in a.get("facts", []))
        options = "".join(
            f"""<li class="opt"><h4>{e(o["title"])}</h4><p>{e(o["detail"])}</p>
                <p class="watch" data-deadline="{e(o.get("deadline", ""))}">{e(o["watch"])}</p></li>"""
            for o in a.get("options", [])
        )
        out.append(f"""
<section class="alert {e(a["level"])}" id="{e(a["id"])}">
  <div class="says">
    <p class="siren">нужно решение</p>
    <h2>{e(a["title"])}</h2>
    <p class="lead">{e(a["lead"])}</p>
  </div>
  <ul class="facts">{facts}</ul>
  {f'<ol class="options">{options}</ol>' if options else ''}
  <p class="closing">{e(a["closing"])}</p>
</section>""")
    return "".join(out)


def flights_block(trip: dict) -> str:
    """Перелёт: два плеча снаружи, подробности рейсов под стрелкой.

    Снаружи ровно то, что решает: откуда, куда, во сколько и сколько лететь.
    Аэропорты названы своими именами, потому что они разные — прилёт в Нариту,
    вылет из Ханэды, — и в последний день это разница в час дороги из Асакусы.
    Прочитаться это должно, ничего не открывая: под стрелкой лежат номера
    рейсов, самолёты, пересадки и багаж — то, что нужно в день вылета, а не при
    планировании.

    **Цены здесь нет ни одной, и это не забывчивость.** Билет уже стоит в чеке
    её записью — $1 222,10, «оплачено», — а второе такое же число рядом
    читалось бы как ещё одна трата. Правило то же, что у жилья: одно число
    живёт в одном месте, иначе расходятся они молча (см. `check`, правило 16).

    Срока бесплатной отмены у билета нет вовсе, поэтому наверх, к срокам
    отелей, перелёт не идёт: выдуманная там дата была бы худшим видом
    подсказки. Говорить об этом словом Ни перестала просить 24 августа
    (`say_no_free_cancel`) — остались правила обмена и возврата, а
    несуществующий срок остался несуществующим и молча.
    """
    fly = trip.get("flights")
    if not fly:
        return ""

    def leg_card(leg: dict) -> str:
        when = d(leg["date"])
        lands = d(leg["arr_date"]) if leg.get("arr_date") else when
        # Снаружи — только то, что решает: день, сколько лететь и то, что
        # прилёт уже назавтра. Пересадка стоит внутри, между своими рейсами:
        # там она объясняет разрыв в часах, а в подписи была бы четвёртым
        # числом, из-за которого строка переносится на вторую.
        meta = [f'{day_month(leg["date"])}, {weekday(leg["date"])}']
        if lands != when:
            meta.append(f'прилёт {day_month(leg["arr_date"])}')
        meta.append(leg["hours"])

        rows = []
        for i, hop in enumerate(leg.get("hops", [])):
            if i and leg.get("layover"):
                rows.append(f'<li class="wait">пересадка {e(leg["layover"])}</li>')
            rows.append(
                f'<li><b>{e(hop["flight"])}</b>'
                f'<span class="way">{e(hop["from"])} {e(hop["dep"])} → '
                f'{e(hop["to"])} {e(hop["arr"])}</span>'
                f'<span class="plane">{e(hop["plane"])}</span></li>'
            )
        return f"""
<details class="fly-fold">
  <summary>
    <b class="path"><span class="dir">{e(leg["dir"])}</span>{e(port(leg, "from"))} <i>{e(leg["dep"])}</i>
       → {e(port(leg, "to"))} <i>{e(leg["arr"])}</i></b>
    <span class="meta">{e(" · ".join(meta))}</span>
  </summary>
  <ol class="hops">{"".join(rows)}</ol>
</details>"""

    bag = fly.get("baggage", {})
    rules = fly.get("rules", {})
    fine = [rules[k] for k in ("change", "refund") if rules.get(k)]
    # Срок отмены — единственное место, где сборка говорит своими словами, а не
    # словами данных: сказать нечего, и сказать это надо вслух. Дата тут была бы
    # выдумкой, прочерк — обещанием.
    #
    # Сказать вслух — с 24 августа её решение: Ни вычеркнула эту фразу
    # (`say_no_free_cancel: false`). Само правило осталось на месте и осталось
    # правилом: `free_cancel` по-прежнему обязан быть `false` (см. `check`,
    # правило 16), и появившийся у билета срок так же остановит сборку. Молчим
    # мы только об отсутствии срока — выдумать его по-прежнему нельзя.
    if rules.get("free_cancel") is False and fly.get("say_no_free_cancel", True):
        fine.append('<span class="nofree">бесплатной отмены нет</span>: срока, '
                    "до которого деньги вернут, у билета не существует")

    ticket = f"""
<details class="fly-fold tkt">
  <summary>
    <b class="path"><span class="dir">билет</span>{e(fly["carrier"])}
       {'<span class="ok">оплачен</span>' if fly.get("paid") else ""}</b>
    <span class="meta">{e(fly.get("cabin", ""))} · багаж и правила обмена</span>
  </summary>
  <dl class="rows">
    <div><dt>в трюм</dt><dd>{e(bag.get("checked", ""))}</dd></div>
    <div><dt>в салон</dt><dd>{e(bag.get("cabin", ""))}</dd></div>
  </dl>
  <ul class="fine">{"".join(f"<li>{x}</li>" for x in fine)}</ul>
</details>"""

    # Примечания стоят открытыми нарочно: они не про билет, а про планирование
    # — какой аэропорт ближе. Под стрелкой их прочтёт только тот, кто уже знает,
    # что они там есть. Их было три; два Ни вычеркнула 24 августа из данных.
    mind = "".join(f"<li>{e(x)}</li>" for x in fly.get("notes", []))

    return f"""
<section class="flights" aria-label="перелёт">
  <div class="row">{"".join(leg_card(x) for x in flight_legs(trip) if x)}{ticket}</div>
  {f'<ul class="mind">{mind}</ul>' if mind else ''}
</section>"""


# Блока «хочу сходить» в карточке города больше нет — Ни 2026-08-24: «из
# карточек города Хочу сходить уходят». Места из `trip.json` при этом никуда не
# делись: они переехали в дни и стоят там ссылками (`spots[].place`, `place` у
# пунктов), а `places` остался единственным местом, где живёт проверенный адрес.
# Поэтому раздел данных не тронут, а вместе с блоком ушла и возможность
# вписывать место со страницы: вписывать она будет в днях.


def stay_fine(leg: dict, how: str, brons: str, extras: str, notes: str) -> str:
    """Всё, что в карточке идёт после цены, — под одной стрелкой.

    Её слово 2026-08-24: «все что после ценника в долларах на карточках городов
    убрать под кат». Снаружи остаётся ровно то, по чему она узнаёт карточку:
    город, отель, даты, ночи и цена. Внутри — как платится, сроки бесплатной
    отмены, комната, еда, часы заезда, адрес, телефон и доплаты.

    До этого дня стрелка прятала половину: сроки отмены и способ оплаты стояли
    снаружи, и ряд карточек занимал 491 точку при 1440 — теперь 236, и все
    четыре одной высоты, потому что снаружи у них осталось одно и то же.
    Прежнее «ещё про отель» слито сюда же ещё 23 августа — две стрелки подряд
    в одной карточке это не выбор, а лишнее нажатие.

    **Сроки отмены из шапки при этом никуда не уходят.** Ближайший стоит там же,
    где стоял, остальные — под стрелкой рядом с ним (см. `deadlines`): это самые
    дорогие даты страницы, и сложить их в четыре свёрнутые карточки значило бы
    убрать их со страницы совсем.

    Заголовок перечисляет, что внутри. Свёрнутое без подписи — это вопрос
    «а надо ли туда лезть», который приходится решать нажатием; отмена названа
    первой, потому что за ней деньги.
    """
    hint = "отмена · оплата · комната · адрес"
    if extras:
        hint += " · доплаты"
    return f"""
<details class="stayfine">
  <summary><span class="lbl">подробности проживания</span><span class="hint">{hint}</span></summary>
  <p class="how">{how}</p>
  {brons}
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


def city_cards(all_legs: list, alerts: list, cancelled: list) -> str:
    """Карточка на город: всё, что превращается в деньги и в опоздания.

    Снаружи — пять строк и ни одной больше: город, район, отель, даты с ночами
    и цена. Всё, что идёт после цены, лежит под стрелкой (`stay_fine`) — её
    слово 2026-08-24, «все что после ценника в долларах убрать под кат».
    Ряд карточек читается теперь как один взгляд по четырём числам, а не как
    четыре столбика мелкого текста.
    """
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
            cancel_block = ""
            if s.get("cancel"):
                cancel_block = f"""
  <p class="cancel" data-deadline="{e(s["cancel"]["free_until"])}">
    <span class="k">бесплатная отмена</span>
    <b>до {day_month(s["cancel"]["free_until"])} {d(s["cancel"]["free_until"]).year}, {e(s["cancel"]["free_until"][11:16])} JST</b>
    <span class="t">{e(s["cancel"]["note"])}</span>
  </p>"""
            brons.append(f"""
<div class="{klass}" id="{e(s["id"])}">
  {label}
  {arriving}{cancel_block}
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
  <div class="cap" style="background:{leg["tone"]};color:{leg["ink"]}">
    <p class="name">{e(leg["city"])}</p>
    <p class="area">{e(leg["area"])}</p>
  </div>
  <div class="inner">
    <p class="hotel">{e(leg["hotel"])}</p>
    <p class="span">{span_dates(leg["sleep_from"], leg["paid_to"])}
       <span>{leg["nights"]} {plural(leg["nights"], "ночь", "ночи", "ночей")}</span></p>
    <p class="price">{money(leg["jpy"])}</p>
    {stay_fine(leg, how, "".join(brons), extras, notes)}
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
    """Две кнопки и одна форма — всё, чем Ни правит эту страницу.

    Одна форма на два вида записи, а не две формы: поля у них общие на
    четыре пятых (что это, подробность, цена, как с деньгами), и два почти
    одинаковых бланка рядом — это выбор, который приходится делать глазами
    каждый раз.

    Форма стоит здесь, между городами и деньгами, потому что отсюда видно
    оба берега: бронь и пункт списка уедут вниз, в свои разделы, и чек под
    ней сойдётся на глазах.

    **Кнопки «+ место» здесь больше нет** — Ни 2026-08-24 убрала «хочу
    сходить» из карточек городов и сказала, что места будет вписывать в днях.
    Форма при этом умеет `place` по-прежнему: старая запись открывается на
    правку отсюда же, и город у неё выбирается тем же списком. Убрать поле
    вместе с кнопкой значило бы, что правка старого места отправит запись без
    города и ручка её отвергнет.
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
</section>"""


def converter() -> str:
    """Счётная линейка: иены в доллары и обратно, два поля и всё.

    Её слово 2026-08-24: «мне нужен конвертер из йен в доллары и обратно.
    небольшой, где-нибудь». «Небольшой» здесь не про место на экране, а про
    список того, чего тут нет: ни истории, ни второй валюты, ни кнопки
    «посчитать». Вписала — увидела.

    **Курс не свой.** Числа тут нигде в разметке нет: браузер берёт его из
    того же `#japan-data`, из которого чек считает её записи. Второй курс на
    странице — это два числа с одним именем, и разойтись они обязаны в самый
    неподходящий момент. Подпись под полями напечатана из того же `fx`
    сборкой, поэтому спорить ей не с чем.

    **Считается тем же `money.js`**, что и весь чек: иена → доллар делением с
    округлением, доллар → иена умножением. Своя арифметика здесь была бы
    третьим способом посчитать одно и то же.

    Ничего не сохраняется и никуда не ходит: набранное живёт до перезагрузки.
    Это линейка, а не запись, — записи у неё есть отдельно и с кнопкой.
    """
    return f"""
<div class="convert">
  <p class="cap">пересчитать</p>
  <div class="pair">
    <span class="fld"><i aria-hidden="true">¥</i><input type="text" inputmode="numeric"
       data-conv="jpy" aria-label="сумма в иенах" placeholder="0" autocomplete="off"></span>
    <i class="swap" aria-hidden="true">⇄</i>
    <span class="fld"><i aria-hidden="true">$</i><input type="text" inputmode="decimal"
       data-conv="usd" aria-label="сумма в долларах" placeholder="0" autocomplete="off"></span>
  </div>
  <p class="fx" data-fx="$1 = ¥{{rate}} на {{date}} · платится в иенах, округлено">$1 = ¥{FX["usd_per_jpy"]} на {fx_human_date()} · платится в иенах, округлено</p>
</div>"""


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
    #
    # Показ выключен 24 августа: Ни вычеркнула строку целиком. Список при этом
    # остался в данных и по-прежнему досматривается (правила 8 и 16) — вернуть
    # его она может одним `not_in_total_show`, а не пересборкой списка заново.
    # Флаг читается здесь, а не вырезается из данных, ровно за этим.
    missing = trip.get("not_in_total", []) if trip.get("not_in_total_show", True) else []
    notall = (f'<p class="notall">в это число не входит: '
              + ", ".join(f"<span>{e(x)}</span>" for x in missing) + "</p>") if missing else ""

    return f"""
<section class="ledger">
  <div class="total" id="check">
    <p class="cap" data-cap>жильё · {len(stays)} {plural(len(stays), "бронь", "брони", "броней")},
       {slept} {plural(slept, "ночь", "ночи", "ночей")}</p>
    <p class="sum"><b class="usd" data-usd>${f"{usd_total:,}".replace(",", THIN)}</b>
       <span class="jpy" data-jpy>{yen(total)}</span></p>
    <p class="fx" data-fx="$1 = ¥{{rate}} · курс на {{date}} · платится в иенах, доллары округлены">$1 = ¥{FX["usd_per_jpy"]} · курс на {fx_human_date()} · платится в иенах,
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
  <!-- Средний столбец чека был на 137 точек ниже левого — эта пустота и есть
       всё место, которое понадобилось линейке. Стоять ей больше негде: под
       суммой она вытолкнула бы страницу за её потолок, а «где-нибудь ещё» на
       странице про деньги значит «подальше от денег». -->
  <div class="col">
    <div class="beyond">
      <p class="cap">сверх этого — считается на месте</p>
      <ul class="caveats">{caveats}</ul>
    </div>
    {converter()}
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


def runs_of(plan: list, all_legs: list) -> list:
    """Дни, сбитые в отрезки по городам — теми же отрезками, что и нитка.

    Группировка идёт по полю `city` самого плана, а не по броням: она называет
    город в дне, и её слово тут первое. Но названные ею города обязаны совпасть
    с бронями по порядку — иначе раздел дней рассказывал бы про один маршрут, а
    нитка и деньги про другой, и заметить это было бы нечем.

    День без города — самолёт: 4 января она ещё летит, 19-го уже уезжает. Такой
    день прилипает к соседнему отрезку, а не заводит свой: отрезок «Дорога» из
    одного дня — это заголовок, повторяющий свой единственный пункт.
    """
    runs = []
    for day in plan:
        city = day.get("city")
        if runs and (city is None or city == runs[-1]["city"]):
            runs[-1]["days"].append(day)
        else:
            runs.append({"city": city, "days": [day]})

    # Отрезки с городом и отрезки нитки идут в одном порядке и обязаны совпасть
    # именами: Токио в поездке дважды, и второй раз — уже Асакуса, а не Гиндза.
    named = [r for r in runs if r["city"]]
    if [r["city"] for r in named] != [leg["city"] for leg in all_legs]:
        raise Failed(
            "города в плане по дням и в бронях разошлись: "
            f'{[r["city"] for r in named]} против {[leg["city"] for leg in all_legs]}'
        )
    for run, leg in zip(named, all_legs):
        run["area"], run["ink"] = leg["area"], leg["ink"]
    for run in runs:
        if not run["city"]:
            # Отрезок без города бывает только первым (вылет): всё остальное
            # прилипло выше. Название берём у единственного дня.
            run["area"], run["ink"] = "", SPARE[-1][1]
    return runs


def spot_link(spot: dict, sites: dict) -> str:
    """Одно место внутри названия — своей ссылкой.

    Ни 2026-08-24: «там где ты залинковываешь текст, залинковывай **каждую
    локацию отдельно**, а не строку целиком, чтобы я не гадала, что же по
    ссылке откроется». «Yasaka Shrine, Maruyama Park, Chion-in» было одной
    ссылкой на три места, и открывалась она на первом.

    Куда ведёт — написано на самой ссылке (`title`), а не угадывается по виду:
    у большинства мест это карта, у проверенных в `places` — их официальный
    сайт, и снаружи эти две ссылки выглядят одинаково.

    Ни карты, ни `place` тут быть не может — это ловит `check` (правило 15);
    голое имя здесь остаётся честным ответом, а не тихой заглушкой.
    """
    name = e(spot["name"])
    if spot.get("map"):
        return (f'<a class="sp" href="{e(maplink(spot["map"]))}" target="_blank"'
                f' rel="noopener" title="на карте">{name}</a>')
    site = sites.get(spot.get("place", ""))
    if site:
        return (f'<a class="sp" href="{e(site)}" target="_blank"'
                f' rel="noopener" title="официальный сайт">{name}</a>')
    return name


def day_title(item: dict, sites: dict) -> str:
    """Название пункта: одной ссылкой или разрезанное по местам.

    Ссылка ведёт **на карту**, а не на сайт: в поездке от названия нужно «где
    это», а не «что про это пишут». Поисковая строка лежит в данных (`map`), и
    у бытовых пунктов её нет — «обед» и «выезд» ссылками не притворяются.

    Есть `spots` — ссылкой становится каждое имя внутри строки, а союзы и
    стрелки между ними остаются текстом. Порядок мест обязан совпасть с
    порядком в названии; сторожит это `check`, потому что здесь несовпадение
    вылезло бы исключением посреди сборки, а не понятной строкой.

    `data-map` на разрезанном названии — поисковая строка всей строки целиком.
    Ссылкой она больше не становится, но её правка обязана видеть тот же
    адрес, что лежит в файле: пустое поле «как искать на карте» в форме
    прочиталось бы как «адреса нет», а он есть.
    """
    spots = item.get("spots")
    if not spots:
        name = e(item["title"])
        if item.get("map"):
            return (f'<a class="nm" data-part="title" href="{e(maplink(item["map"]))}"'
                    f' target="_blank" rel="noopener">{name}</a>')
        return f'<span class="nm" data-part="title">{name}</span>'

    text, parts, at = item["title"], [], 0
    for spot in spots:
        found = text.index(spot["name"], at)
        parts.append(e(text[at:found]))
        parts.append(spot_link(spot, sites))
        at = found + len(spot["name"])
    parts.append(e(text[at:]))
    return (f'<span class="nm" data-part="title" data-spots'
            f' data-map="{e(item.get("map", ""))}">{"".join(parts)}</span>')


def day_item(item: dict, sites: dict) -> str:
    """Один пункт дня.

    **Часов здесь нет.** Ни 2026-08-24: «часы убей, они ломаются при
    перетаскивании и в целом лишние, **не хочу жить по расписанию**. а если
    где-то важно время — пометь, что к примеру только до 15». Поле `time` из
    данных не выброшено — оно просто не рисуется; вместо него `when`, короткая
    пометка там, где время действительно связывает: заезд, выезд, слот,
    расписание поезда. Пусто — не рисуется ничего, иначе мы поменяли бы часы
    на пустое место под часы.

    Пометка живёт в размеченном узле даже пустой: дописать её она может прямо
    на странице, и узел, которого нет, пришлось бы создавать вторым способом.
    Спрятан он `hidden`, а `.mk[hidden]` погашен в CSS отдельным правилом —
    `display:inline-block` перебивает `hidden` молча, и пустая пометка стала
    бы пустой пилюлей на каждой строке.

    **Адрес уезжает в слово «бронировать».** Ни: «там, где надо бронировать
    проставь ссылки на сайт прямо в надписи бронировать, **не придумывай
    новую**» — отдельной метки «сайт» больше нет. Где бронировать надо, а
    адреса нет (поезда), пометка остаётся текстом и ссылкой не притворяется.

    Части подписаны `data-part`, потому что переписывать их будет браузер: её
    правка ложится поверх файлового текста по вечному id, и находить, что
    именно менять, по классу оформления было бы способом однажды не найти.
    """
    title = day_title(item, sites)

    when = e(item.get("when", ""))
    marks = [f'<span class="mk wn" data-part="time"{"" if when else " hidden"}>{when}</span>']
    if item.get("book"):
        site = item.get("site") or sites.get(item.get("place", ""))
        if site:
            marks.append(f'<a class="mk bk" href="{e(site)}" target="_blank"'
                         f' rel="noopener">бронировать</a>')
        else:
            marks.append('<span class="mk bk">бронировать</span>')
    # Переезд уже посчитан в «Переездах» — здесь только пометка и отсылка.
    # Второе число рядом с первым расходится молча, а замечается на кассе.
    if item.get("transfer"):
        marks.append('<span class="mk tr">переезд · время и цена в «Переездах»</span>')

    note = e(item.get("note", ""))
    return (
        f'<li class="it" data-item="{e(item["id"])}">'
        f'<span class="wh">{title}'
        f'<span class="marks">{"".join(marks)}</span>'
        f'<em class="nt" data-part="note"{"" if note else " hidden"}>{note}</em>'
        f"</span></li>"
    )


def by_day(trip: dict, stays: list, alerts: list, plan: list, all_legs: list) -> str:
    """Шестнадцать дней, которые она тасует руками.

    **Порядок здесь принадлежит ей, а не файлу.** Собранная страница показывает
    план так, как он лежит в `days-plan.json`, — это засев и это же честный
    ответ, когда хранилище не отвечает. Как только её расстановка доезжает,
    браузер переставляет уже существующие строки в её порядок: не рисует
    заново, а двигает. Поэтому ссылки, метки и сайты живут в одном месте — в
    этой функции, — и второго способа нарисовать пункт на странице нет.

    **Свёрнуто по умолчанию.** Её слово про длинную версию: «слишком много
    листать вниз». Раскрыт отрезок города, свёрнут день; ближайший день
    открывает браузер, потому что «ближайший» стареет каждые сутки, а страница
    собирается редко.

    **Свёрнутый день — мишень для броска, и это единственный дальний перенос.**
    Ни 2026-08-24, про список дат у каждой строки: «поэтому я попросила сделать
    дни в два столбца, а не колбасой вниз». Два столбца держат все шестнадцать
    свёрнутых дней на одном экране, и 6 января с 17-м видны одновременно —
    значит утащить одно к другому можно мышью, а список дат был обходом
    проблемы, которой нет.

    Ручек (двинуть, перенести, дописать, убрать) в собранной разметке нет
    нарочно: все они ходят в хранилище, и нарисованная кнопка, которой некуда
    нажать, — обещание, которого страница не может сдержать.

    «Развернуть все дни» — исключение, и именно потому, что она ни в какое
    хранилище не ходит: свёртка это чистая разметка, и кнопка работает даже
    тогда, когда расстановка не доехала. Стоит она в собранной странице, а не
    рисуется скриптом, чтобы не мигать при загрузке.
    """
    flagged = {a["id"]: a["level"] for a in alerts}
    sites = {p["title"]: p["site"] for p in trip.get("places", []) if p.get("site")}
    start = d(trip["trip"]["start"])
    total = sum(len(x["items"]) for x in plan)

    blocks = []
    for run in runs_of(plan, all_legs):
        days = []
        for day_plan in run["days"]:
            when = d(day_plan["date"])
            here = [s for s in stays
                    if d(s["checkin"]["date"]) <= when < d(s["checkout"]["date"])]
            moving = [s for s in stays if d(s["checkin"]["date"]) == when]
            tones = {flagged.get(s.get("conflict")) for s in here} - {None}
            clash = "red" if "red" in tones else "noted" if tones and len(here) > 1 else ""
            note = day_plan.get("day_note", "")
            items = "".join(day_item(x, sites) for x in day_plan["items"])

            days.append(f"""
<details class="day {'move' if moving and when != start else ''} {clash}" data-day="{e(day_plan["date"])}">
  <summary>
    <span class="dt"><b>{when.day}</b><i>{WEEKDAYS[when.weekday()]}</i></span>
    <span class="ttl">{e(day_plan["title"])}</span>
    <span class="cnt" data-count>{len(day_plan["items"])}</span>
  </summary>
  <div class="dbody">
    <p class="dnote"{"" if note else " hidden"}>{e(note)}</p>
    <ol class="items" data-day-items="{e(day_plan["date"])}">{items}</ol>
  </div>
</details>""")

        first, last = d(run["days"][0]["date"]), d(run["days"][-1]["date"])
        label = f'{run["city"]} · {run["area"]}' if run["city"] else run["days"][0]["title"]
        blocks.append(f"""
<details class="run" open data-run="{e(label)}" style="--city-line:{run["ink"]}">
  <summary>
    <span class="ct">{e(label)}</span>
    <span class="sp">{span_dates(first, last)}</span>
    <span class="n">{len(run["days"])} {plural(len(run["days"]), "день", "дня", "дней")}</span>
  </summary>
  <div class="rdays">{"".join(days)}</div>
</details>""")

    return f"""
<div id="days">
  <p class="sec-note">Пункты можно таскать мышью — внутри дня, между открытыми
     днями и на заголовок свёрнутого дня: брошенный на заголовок встаёт в конец
     того дня. Ручки появляются, когда наводишь на строку. Порядок хранится на
     сайте, а не в телефоне, и пересборка страницы его не трогает. Каждое место
     в названии ведёт на свою карту.</p>
  <p class="sec-note daysays" data-days-says role="status" hidden></p>
  <button type="button" class="foldall" data-fold-all aria-expanded="false">развернуть все дни</button>
  <div class="plan" data-plan data-total="{total}">{"".join(blocks)}</div>
</div>"""


def luggage(trip: dict) -> str:
    """Чемодан — одним куском: кто везёт, куда нажимать, сколько стоит, когда едет.

    Её слово 2026-08-24: «мы в трёх местах пишем про багаж и нигде не указываем
    сайт, откуда вызывать доставку». Три места были — то-до, подробности OMO3 и
    этот блок; в каждом стояло по половине «как», и ни в одном — имя службы со
    ссылкой и цена рядом.

    Первое, что говорит блок теперь, — что нажимать негде: TA-Q-BIN
    заказывается на стойке отеля. Ссылка ведёт не на главную компании (она
    называет три вида бизнеса и ни одного слова про чемодан гостя), а на
    страницу самой услуги — правило то же, что у отелей: ссылка, которая не
    называет вещь, хуже отсутствующей.
    """
    lug = trip["luggage"]
    moves = "".join(
        f"""<li>
          <p class="when">{day_month(m["date"])}, {weekday(m["date"])}</p>
          <p class="path"><span>{e(m["from"])}</span><i aria-hidden="true">→</i><span>{e(m["to"])}</span></p>
          <p class="note">{e(m["note"])}</p>
        </li>"""
        for m in lug["moves"]
    )
    always = "".join(f"<li>{e(x)}</li>" for x in lug["always"])
    svc = lug["service"]
    # Пересылка чемодана стоит денег и в чек не идёт — цена стоит рядом с самой
    # пересылкой, а не только в строке «чего в итоге нет».
    cost = (f'<p class="cost"><b>{e(lug["cost"])}</b>'
            f'<span>{e(svc["size"])}</span></p>') if lug.get("cost") else ""
    return f"""
<div id="luggage">
  {f'<p class="lead">{e(lug["lead"])}</p>' if lug.get("lead") else ""}
  <div class="who">
    <p class="name">{e(svc["name"])}<i aria-hidden="true">·</i>{e(svc["product"])}</p>
    <p class="order">{e(svc["order"])}</p>
    {cost}
    <a class="btn site" href="{e(svc["site"])}"
       target="_blank" rel="noreferrer noopener">{e(svc["site_label"])}</a>
  </div>
  <ol class="moves">{moves}</ol>
  <ul class="always">{always}</ul>
</div>"""


def bought() -> str:
    """Купленное отдельно: билеты, поезда, экскурсии. И её места — здесь же.

    Пустой раздел — одна строка, а не пустая страница: место под её брони
    существует до первой брони, иначе кнопке «+ бронь» некуда класть.

    Заголовок несёт число и сумму (их подставляет браузер), потому что
    свёрнутое без подписи превращается в вопрос «а есть ли там что-нибудь»,
    который приходится решать нажатием.

    **Мешок под её места стоит здесь с 24 августа.** Раньше он стоял в
    карточке города, а карточки лишились блока «хочу сходить» — и запись вида
    `place` осталась бы без единого места на странице, продолжая при этом
    считаться в чеке. Запись, которая берёт деньги и не показывается, хуже
    лишнего блока: сумма растёт, а спросить с неё нечего.

    Мешок пустой и спрятанный: показывает его браузер и только когда такая
    запись правда есть. Заводить видимую подпись под то, чего у неё нет
    (новых мест отсюда больше не добавить), значило бы поставить на страницу
    пустую карточку-призрак.
    """
    return """
<div id="bought">
  <p class="sec-note">Всё, что куплено или будет куплено не через отель: билеты,
     поезда, экскурсии. Идёт в общий чек — «уже оплачено» или «предстоит».</p>
  <ul class="mine rows-list" data-mine-booking></ul>
  <p class="none" data-none-booking>пока пусто — нажми «+ бронь или билет» выше.</p>
  <div class="kept-places" data-places hidden>
    <p class="cap">места, записанные раньше</p>
    <ul class="mine rows-list" data-mine-place></ul>
    <p class="sec-note">Новые места теперь вписываются в днях. Эти можно
       поправить или убрать — они по-прежнему в общем чеке.</p>
  </div>
</div>"""


def more_block(trip: dict, stays: list, alerts: list, plan: list, all_legs: list) -> str:
    """Списки, дни и багаж — свёрнуты, но никуда не делись.

    Ни сказала про длинную версию: «слишком много листать вниз». Выкидывать
    при этом нечего — поэтому длинное лежит здесь, за одним нажатием, а не
    на главном экране.

    Порядок не случайный: первым то, что она правит сама («не забыть» и
    «куплено»), потом то, что читается («по дням», «багаж»). Заголовки
    первых двух показывают счёт и сумму — свёрнутое должно говорить, что
    внутри, само.

    У багажа подпись стоит прямо в разметке, а не подставляется браузером:
    имя службы и цена не зависят ни от её записей, ни от хранилища. Смысл тот
    же — «кто везёт и почём» видно, не открывая; свёрнутое без подписи
    превращается в вопрос, который приходится решать нажатием.

    **У дней подписи больше нет.** «16 дней · 98 пунктов» отвечало на вопрос,
    которого она не задавала: Ни 2026-08-24, «подпись к блоку и все кнопки
    убивай, они только мусорность создают и место занимают». Счёт пунктов
    остался там, где он что-то значит, — на самом дне.

    **Четыре свёртки лежат на одной плоскости** (`.folds`), а не стоят четырьмя
    полосами, разделёнными линиями. «Эксель» Ни помянула третий раз, и линии
    здесь были буквально им: пять горизонталей на четыре строки. Стопка от
    этого не рассыпалась — её держит общая карточка под всеми четырьмя.
    """
    svc = trip["luggage"]["service"]
    tags = {
        "luggage": f'{svc["name"]} · {trip["luggage"]["cost"].split(" за ")[0]}',
    }
    parts = [
        ("todo", "Решить и забронировать", checklist(trip)),
        ("bought", "Куплено отдельно", bought()),
        ("days", "По дням", by_day(trip, stays, alerts, plan, all_legs)),
        ("luggage", "Багаж", luggage(trip)),
    ]
    folds = "".join(
        f'<details class="more" data-fold="{e(key)}"><summary>{e(name)}'
        + (f'<span class="tag" data-tag="{e(key)}">{e(tags[key])}</span>'
           if key in tags else "")
        + f'</summary>{body}</details>'
        for key, name, body in parts
    )
    return f'<div class="folds">{folds}</div>'


def ref_item(item: dict, extra: tuple = ()) -> str:
    """Один пункт справки — и его происхождение, написанное на нём же.

    Здесь и стоит вся защита от той ошибки, которой мы боимся: непроверенное,
    нарисованное как факт. Она не проверяется отдельным инструментом, который
    можно забыть позвать, — пункт без происхождения просто не рисуется, и
    сборка падает на месте.

    Три вида, и они выглядят по-разному нарочно:

    * `verified: true` — подтверждено двумя независимыми источниками. Обычная
      строка, без пометки: пометка на факте обесценила бы пометку на догадке.
    * `verified: false` + `how` — **не подтверждено**, и это написано словом,
      а рядом стоит `how`: что и когда спросить. Сайт посольства Японии в
      Грузии отвечает нашему серверу 403 на все страницы, включая главную,
      поэтому эти три пункта и взяты из вторичных источников.
    * `mine: true` — наше соображение, а не внешнее правило. Тоже помечено, и
      другим словом: спутать «так устроено» и «мы так думаем» дороже всего.

    Пункт, у которого происхождения нет или их два, — это пункт, про который
    мы сами не знаем, факт он или нет. Такой не показывается вовсе.

    Сверх происхождения у пункта бывают две пометки о **весе**, и обе пришли
    из её правок 24 августа.

    `lead: true` — то, что надо сделать заранее, а не прочитать. Такой пункт
    рисуется советом на своей плоскости, с подписью «стоит сделать заранее», а
    не строкой списка. Её слова про Visit Japan Web: «наоборот выделить. и
    написать что лучше сделать» — то есть вес тут не в важности факта, а в
    том, что за ним стоит действие.

    `group: "…"` — пункты, которые читаются вместе. Первый в группе несёт
    подпись, остальные — по ссылке; на экране они стоят подряд, без воздуха
    между собой, и две ссылки читаются парой, а не двумя отдельными фактами.
    Её слова: «страховки без подробностей оставь ссылки».

    **Пункт, у которого текст равен подписи ссылки, рисуется одной ссылкой.**
    Так устроены GPI и TBC: подробностей она не хочет, и весь пункт — это имя
    страховой. Подпись плюс ссылка напечатали бы имя дважды.
    """
    kinds = [
        bool(item.get("verified") is True),
        bool(item.get("verified") is False),
        bool(item.get("mine") is True),
    ]
    if sum(kinds) != 1:
        raise Failed(f'пункт справки без ясного происхождения: «{item["text"][:60]}…»')

    # Ссылка ставится только та, что открыта своими руками; выдуманного адреса
    # здесь не появится, как и у мест в карточках городов.
    link = ""
    if item.get("link"):
        link = (f'<a class="btn" href="{e(item["link"])}" target="_blank"'
                f' rel="noreferrer noopener">{e(item.get("link_label") or item["link"])}</a>')

    # Пункт, весь смысл которого — имя со ссылкой (GPI, TBC): подпись ссылки
    # равна тексту, и печатать оба значит написать имя дважды.
    only_link = bool(link) and item.get("link_label", "").strip() == item["text"].strip()
    say = "" if only_link else f'<span class="say">{e(item["text"])}</span>'
    if only_link:
        extra = (*extra, "only")

    if item.get("lead") is True:
        # Единственное в блоке, за чем стоит действие, а не чтение. Подпись
        # говорит именно это — «стоит сделать заранее», — а не «важно»:
        # важность пункта здесь ничего не меняет, а срок и место действия —
        # меняют. Происхождение при этом остаётся первым классом: вид пункта
        # не должен зависеть от того, выделен он или нет.
        extra = (*extra, "ahead")

    cls = " ".join(("fact", *extra))
    if item.get("mine") is True:
        cls = " ".join(("think", *extra))
        return (f'<li class="{cls}"><span class="mark">наше соображение</span>'
                f'{say}{link}</li>')
    if item.get("verified") is False:
        how = (item.get("how") or "").strip()
        if not how:
            raise Failed(f'непроверенный пункт молчит, что с ним делать: «{item["text"][:60]}…»')
        # Стрелку рисует страница (`.ref .unsure .how::before`), а не текст.
        # В правках 24 августа каждое «что спросить» начинается со стрелки — и
        # на экране их стало две подряд: «→ → спросить в своём банке». Правится
        # здесь, а не в данных: глиф — оформление, и владеть им должно одно
        # место. Само указание при этом остаётся дословно тем, что написано.
        how = how.lstrip("→⟶->—– ").strip()
        cls = " ".join(("unsure", *extra))
        return (f'<li class="{cls}"><span class="mark">не подтверждено</span>'
                f'{say}'
                f'<span class="how">{e(how)}</span>{link}</li>')
    if item.get("lead") is True:
        # Совет отличается от строки списка не только плоскостью, но и словом:
        # видно, не читая пункт целиком, что за ним стоит действие.
        return (f'<li class="{cls}"><span class="mark">стоит сделать заранее</span>'
                f'{say}{link}</li>')
    return f'<li class="{cls}">{say}{link}</li>'


def ref_items(block: dict) -> str:
    """Список пунктов блока — и метки того, что читается вместе.

    Группу (`group`) размечает не сам пункт, а его соседи: первый в группе
    несёт подпись, последний закрывает её. Знать это в одиночку пункт не может,
    поэтому границы считаются здесь, а в `ref_item` уезжают готовыми классами.
    """
    items = block["items"]
    out, pack = [], []

    def close_pack():
        # Группа лежит в своём списке внутри одного места общего: соседство
        # здесь — не оформление, а условие. В общей сетке справки колонки шире
        # трёхсот точек, и две ссылки, попав каждая в свою, оказываются в
        # полуметре друг от друга — то есть ровно двумя отдельными фактами,
        # против чего группа и заведена.
        if pack:
            out.append(f'<li class="pack"><ul class="pair">{"".join(pack)}</ul></li>')
            pack.clear()

    for n, item in enumerate(items):
        g = item.get("group")
        if not g:
            close_pack()
            out.append(ref_item(item))
            continue
        before = items[n - 1].get("group") if n else None
        after = items[n + 1].get("group") if n + 1 < len(items) else None
        if g != before:
            close_pack()
        extra = ("grp",)
        if g != before:
            extra += ("grp-head",)
        if g != after:
            extra += ("grp-tail",)
        pack.append(ref_item(item, extra))
        if g != after:
            close_pack()
    close_pack()
    return f'<ul class="facts">{"".join(out)}</ul>'


# Тон свёрнутой строки и подсказка под заголовком — единственное, что у блоков
# справки разное, и единственное, чего нет в данных. Порядок здесь тоже свой:
# он у неё по времени (до вылета → деньги → такс-фри), а в файле блоки лежат
# так, как их дописывали.
#
# **Отбора по этому списку нет.** Перебор идёт по данным; блок, которого здесь
# не оказалось, рисуется тихим, встаёт в конец и берёт вместо подсказки счёт
# своих пунктов. Раньше блоки были перечислены поимённо в самой разметке — и
# пятый, «приложения», пролежал в данных невидимым: на странице его не было
# вовсе. Вещь, которая есть в данных и не видна на экране, хуже отсутствующей,
# поэтому теперь новый блок появляется сам, а этот словарь только уточняет вид
# (`test_data.py`, «блок из данных, о котором сборка не знала»).
REF_LOOK = {
    "documents": ("quietly", "Visit Japan Web, три страховые"),
    "money": ("quietly", "наличные, банкоматы, IC-карта"),
    "taxfree": ("flip", "платишь в магазине, возвращаешь в аэропорту"),
    "apps": ("quietly", "переводчик, такси, Suica в кошельке"),
}

# Блок, который не под стрелкой. Один и по имени — не ради красоты перебора:
# у визы свой вид (рамка, «самое срочное», соображение снаружи), и достаётся
# он ей не потому, что она первая в файле, а потому, что это единственный
# срок, который горит. Встань завтра в начале данных другой блок — сиреной он
# от этого не станет.
REF_SIREN = "visa"


def reference() -> str:
    """Справка внизу: виза, до вылета, деньги, такс-фри, приложения.

    Ни 24 августа: «внизу мне нужна справочная информация по визе для граждан
    грузии, как и когда оформлять, по еще каким-то документам, которые нужно
    оформить до. как легко оформлять дьюти фри покупки и что-то еще полезное».
    «Внизу» здесь буквально: отдельным разделом в конце, а не строчкой внутри
    «Решить и забронировать» — это не пункт её списка, а внешние правила.

    Блоков пять, и стоят они по-разному, а разница не оформительская.
    Перечислять их здесь поимённо больше нельзя: именно так пятый и пролежал
    в данных невидимым — см. `REF_LOOK` выше.

    **Виза не под стрелкой.** Это самый срочный срок на всей странице: вылет
    4 января, подача только очно, а конец декабря у японских учреждений
    нерабочий. Свёрнутая наравне с такс-фри, она читалась бы как «ещё одна
    справка», и открыть её можно было бы в феврале. Поэтому у визы вид
    заметки о наложении ночей — рамка, которой на этой странице помечено
    дорогое, — и снаружи сказано то, из-за чего надо шевелиться. Под стрелкой
    остаются подробности, а не повод.

    **У такс-фри повод написан в самом заголовке.** С 1 ноября 2026 система
    перевернулась: раньше налог не брали в магазине, теперь платишь и
    возвращаешь в аэропорту. Её поездка — январь 2027, то есть уже по новым
    правилам, и человек, который помнит старые, ничего открывать не станет —
    он же «знает, как это работает». Поэтому «работает наоборот» стоит в
    строке, которую видно не открывая.

    Заголовки «до вылета», «деньги» и «приложения» намеренно тихие: там нет ни
    срока, ни ловушки — только то, что понадобится, когда дойдут руки.

    **Приложения стоят последними, и это не «в конец, куда влезло».** Скачать
    их надо дома, то есть по времени они рядом с «до вылета», — но это самый
    длинный блок из всех и самый необязательный: без Visit Japan Web её
    развернут на границе, без Tabelog она просто поужинает хуже. Вторым сверху
    он отодвинул бы вниз три свёртки, которые она сегодня вечером сама
    расставила, ничего не выиграв взамен.

    Внутри блока порядок другой — не по времени, а по весу: Suica помечена
    советом (`lead`), потому что айфон умеет японский бесконтактный чип и
    карта заводится прямо в кошельке. Это единственная строка списка, которая
    закрывает половину блока про деньги, и выглядеть она обязана поступком, а
    не десятым пунктом перечня.

    **Закрытыми свёртки стоят друг под другом.** Это её правка 24 августа,
    вечером: «до вылета, деньги и таксфри не нравится как разворачиваются.
    пусть стоят друг под другом». Ряд карточек я ставила ради 44 точек высоты —
    но раскрывался он вбок и через раз перекладывал соседей, а читать их она
    собирается подряд, а не выбирать одну из трёх. Высота вернулась (число — в
    шапке `test/wide.py`), порядок прежний: до вылета → деньги → такс-фри, по
    времени, и следом приложения. Раскладку держит CSS (`.ref-rows`).
    """
    ref = load_reference()
    blocks = {b["id"]: b for b in ref["blocks"]}
    if REF_SIREN not in blocks:
        raise Failed(f"в справке нет блока «{REF_SIREN}» — некому стоять первым, не под стрелкой")
    visa = blocks[REF_SIREN]

    # Счёт непроверенного — в подписи свёртки. Свёрнутое должно говорить, что
    # внутри, само; а здесь оно должно говорить ещё и то, чему внутри верить
    # нельзя, — иначе «не подтверждено» увидит только тот, кто открыл.
    #
    # С 24 августа это считается у каждого блока, а не у одной визы: пунктов
    # стало 24 против 16, и непроверенное разъехалось по всем четырём. Пока
    # счёт стоял только у визы, «здесь не всё проверено» у остальных трёх
    # было видно лишь тому, кто открыл, — то есть работало наполовину.
    #
    # Отсюда же и запасная подпись у блока, которого нет в `REF_LOOK`: пустая
    # `note` — это не «без подписи», а счёт пунктов. Свёрнутая строка обязана
    # сказать, что под ней, даже если подсказку ей никто не написал.
    def unsure_tag(block: dict, note: str = "") -> str:
        n = sum(1 for i in block["items"] if i.get("verified") is False)
        said = note or (f'{len(block["items"])} '
                        f'{plural(len(block["items"]), "пункт", "пункта", "пунктов")}')
        return f"{said} · {n} без подтверждения" if n else said

    tag = unsure_tag(visa)

    warn = visa.get("warning")
    think = ""
    if warn:
        think = (f'<p class="think"><span class="mark">наше соображение</span>'
                 f'{e(warn["text"])}</p>')

    def fold(block: dict) -> str:
        cls, note = REF_LOOK.get(block["id"], ("quietly", ""))
        lead = f'<p class="lead">{e(block["lead"])}</p>' if block.get("lead") else ""
        # Заголовок — в своём элементе, а не голым текстом рядом с плюсом.
        # Голый текст внутри флексового `summary` становится безымянной
        # ячейкой, и на телефоне длинный заголовок такс-фри уносило целиком на
        # следующую строку, оставляя плюс стоять в одиночестве.
        return (f'<details class="more ref-row {cls}" data-ref="{e(block["id"])}">'
                f'<summary><span class="ttl">{e(block["title"])}</span>'
                f'<span class="tag" data-ref-tag="{e(block["id"])}">'
                f'{e(unsure_tag(block, note))}</span>'
                f'</summary><div class="ref-body">{lead}{ref_items(block)}</div></details>')

    # Порядок: сначала те, кому он назначен (`REF_LOOK`), потом всё остальное
    # из данных — в том порядке, в каком лежит в файле. Ключ здесь один и тот
    # же список, поэтому «добавить блок» и «поставить его на место» — это два
    # разных действия, и первое работает без второго.
    rest = [blocks[i] for i in REF_LOOK if i in blocks and i != REF_SIREN]
    rest += [b for b in ref["blocks"]
             if b["id"] not in REF_LOOK and b["id"] != REF_SIREN]

    return f"""
<section class="ref" id="ref">
  <div class="visa">
    <div class="says">
      <p class="siren">самое срочное</p>
      <h3>{e(visa["title"])}</h3>
      <p class="lead">{e(visa["lead"])}</p>
    </div>
    {think}
    <details class="visa-more" data-ref="visa">
      <summary>Что нужно знать<span class="tag" data-ref-tag="visa">{e(tag)}</span></summary>
      {ref_items(visa)}
    </details>
  </div>
  <div class="ref-rows">
    {"".join(fold(b) for b in rest)}
  </div>
</section>"""


def island(trip: dict, stays: list, all_legs: list, plan: list) -> str:
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
        # Дни — порядок расстановки и то, какой из них раскрыть первым. Подписи
        # («6 января, ср — …») тут больше нет: её единственным читателем был
        # список «перенести в день →», а его Ни убрала 24 августа — «поэтому я
        # попросила сделать дни в два столбца, а не колбасой вниз». Данные,
        # которые никто не читает, — это второй русский календарь, ждущий
        # случая разойтись с первым.
        "days": [{"date": x["date"]} for x in plan],
    }
    text = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
    return f'<script type="application/json" id="japan-data">{text}</script>'


def colophon(trip: dict) -> str:
    """Кто что вносит — и по состоянию на когда.

    Дата проверки справки стоит здесь, а не под самой справкой, по двум
    причинам сразу. Смысловая: «обновлено» и «проверено» — оба про возраст
    страницы, и врозь они читаются как разные вещи. Считанная: отдельной
    строкой под справкой она стоила 37 точек высоты, а здесь встала в уже
    потраченную строку подвала и не стоит ничего.
    """
    ref = load_reference()
    return f"""
<footer class="colophon">
  <span>Обновлено {day_month(trip["trip"]["updated"])} {d(trip["trip"]["updated"]).year}.</span>
  <span class="ref-checked">Справка внизу проверена
  {day_month(ref["checked"])} {d(ref["checked"]).year}.</span>
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

   Каждый цвет ниже подписан контрастом к бумаге (#e8eef7), потому что «сложно
   читать» — это измеримая величина, а не вкус. Основной текст держит 7:1,
   подписи и мелочь — 4.5:1; проверяется в test/wide.py на каждой видимой
   строке, а не глазами по памяти.

   ── гамма, 24 августа ─────────────────────────────────────────────────────

   Было тёплое бежевое (#f2eee7) с золотом и бронзой. Ни: «эта прям очень
   эксель. фон нужен холоднее сильно. цвета ближе к моим любимым розовым
   голубым пастельным с яркими акцентами».

   «Эксель» — это половина про цвет и половина про то, сколько всего обведено
   в рамку; лечится и то и другое (рамки — ниже по файлу, там где сняты).
   Бумага стала холодной пастельной голубой, плоскости — голубая и розовая,
   а яркий цвет отдан **малому и важному**: сроку, который горит, деньгам,
   которые ещё не заплачены, и кнопке «бронировать». Яркого на экране должно
   быть мало — иначе оно перестаёт быть акцентом, ровно как случилось с
   жирным шрифтом.

   Имена переменных сменились вместе с цветом нарочно: `--gold`, хранящее
   синий, — мина для следующего, кто сюда придёт. Теперь имена говорят про
   роль (`--calm`, `--hot`), а не про материал.

   ── конфетковая бумага, 24 августа, вечер ─────────────────────────────────

   Ни: «сделайте градиентом фон на мотив как у нас онбординг. пусть будет сайт
   конфетковый такой красивый, девчачий. и можно фон сделать менее синим,
   более белым. чтобы не было ощущения экселя».

   У онбординга взят **приём, а не палитра**: там фон — несколько больших
   мягких пятен `radial-gradient`, каждое уходит в свою же прозрачность, и всё
   это лежит на ровной заливке. Цвета здесь свои, пастельные, той же семьи,
   что и тона городов.

   «Менее синим, более белым» — про заливку: #e8eef7 сменилась почти белой
   #faf5f9, а цвет переехал в перелив. Пятен четыре: розовое сверху слева,
   голубое сверху справа, второе розовое пониже и сиреневое внизу. Розового
   больше всех — это и есть «конфетковый».

   Чего пятнам делать нельзя: доходить до яркости `--hot`. Яркое на этой
   странице носит смысл — горящий срок, неоплаченное, «бронировать», рамка
   визы, — и фон, дошедший до их насыщенности, растворяет акцент. Поэтому
   пятна держатся в пастели, а насколько — не на глаз: самая тёмная точка
   перелива светлее прежней ровной бумаги (0.86 против 0.85 по яркости), то
   есть контраст всей страницы от градиента не упал нигде.

   Прежде здесь стояло «градиента не будет: проверка контраста читает
   `background-color`, а градиент в нём не виден». Это была правда про
   проверку, а не про страницу, и решать ей вёрстку было не по чину. Проверка
   переписана (`test/wide.py`): она снимает кадр страницы с погашенным текстом
   и читает **настоящий пиксель** под каждой строкой, в пяти точках её
   прямоугольника, беря худшую. Перелив она теперь видит честно. */
:root{
  color-scheme:light;
  /* Пятна перелива записаны тройками чисел, а не хексом: тот же цвет нужен и
     в прозрачном крае (`rgb(var(--rose) / 0)`), а второй хекс рядом с первым
     разъедется при первой же правке. */
  --rose:252 228 240;       /* конфетковое розовое пятно */
  --sky:230 238 253;        /* пастельное голубое пятно */
  --lilac:242 231 251;      /* сиреневое пятно внизу */
  --paper:#faf5f9;          /* почти белая бумага с розовым подшёрстком */
  --card:#ffffff;           /* поднятая плоскость: карточки, поля, свёртки */
  /* Белое на почти белой бумаге само по себе уже не плоскость: разница
     упала с 1.17 до 1.08. Возвращает её не обводка (она и есть «эксель»), а
     мягкая тень — та же, что у конфетной коробки. */
  --lift:0 1px 2px rgba(93,63,101,.06), 0 10px 24px rgba(93,63,101,.05);
  --mist:#dce6f4;           /* пастельная голубая плоскость */
  --blush:#fbe3ec;          /* пастельная розовая: дорогое и её собственное */
  --ink:#161b29;            /* 14.7:1 — всё, что читается как текст */
  --deep:#3a455e;           /*  8.2:1 — второй голос, но всё ещё текст */
  --quiet:#4e5871;          /*  6.1:1 — подписи, мелочь, пояснения */
  --calm:#3055a6;           /*  6.1:1 — спокойный акцент: пометки и стрелки */
  --calm-ink:#27437f;       /*  8.2:1 — тот же акцент там, где он от 14px и текст */
  --done:#14655a;           /*  5.9:1 — уже списано */
  --hot:#c01048;           /*  5.3:1 — яркое: горящий срок, неоплаченное, «бронировать» */
  --hot-ink:#9c0a3a;        /*  7.2:1 — то же яркое там, где оно от 14px и текст */
  --rule:#92a0bc;           /*  2.3:1 — границы, которые что-то значат */
  --hair:#cfd9ea;           /*  1.2:1 — разделители строк, чистое оформление */
  --serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,"Times New Roman",serif;
  --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
  --num:ui-monospace,SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace;
  --sheet:1340px;
  /* Три способа оплаты различаются не только цветом: заливка, косая штриховка
     вправо, косая штриховка влево. Плотность у всех трёх одинаковая нарочно —
     ставить её лесенкой значило бы рисовать самую крупную сумму самой бледной,
     а «на месте» здесь как раз крупнейшая доля. */
  --fill-paid:var(--done);
  --fill-due:repeating-linear-gradient(45deg,var(--hot) 0 2px,rgba(255,255,255,.75) 2px 4.5px);
  --fill-onsite:repeating-linear-gradient(-45deg,var(--calm) 0 2px,rgba(255,255,255,.75) 2px 4.5px);
}
*{box-sizing:border-box}
/* `hidden` обязан выигрывать у наших `display`. Без этой строки `.pane{display:grid}`
   перебивает атрибут — и форма, объявленная спрятанной, стоит развёрнутой во
   весь экран. Так и случилось: страница выросла на 292 точки, а спрятанной
   форма при этом считалась. */
[hidden]{display:none !important}
/* Перелив лежит на `html`, а не на `body`, и это не вкус. Фон `body`
   всплывает на холст сам, но область, по которой считаются проценты пятен,
   браузер при этом берёт от корня — то есть от `html`. Написать там же, где
   он и считается, дешевле, чем помнить про это правило. `body` за это обязан
   стать прозрачным: непрозрачная заливка на нём закрыла бы перелив целиком,
   она ведь ровно во всю страницу. */
html{
  -webkit-text-size-adjust:100%;
  min-height:100%;
  background-color:var(--paper);
  background-image:
    radial-gradient(62% 36% at 6% 1%,   rgb(var(--rose) / .95) 0%, rgb(var(--rose) / 0) 70%),
    radial-gradient(56% 30% at 97% 11%, rgb(var(--sky) / .95) 0%,  rgb(var(--sky) / 0) 72%),
    radial-gradient(72% 32% at 88% 55%, rgb(var(--rose) / .8) 0%,  rgb(var(--rose) / 0) 70%),
    radial-gradient(84% 36% at 8% 97%,  rgb(var(--lilac) / .9) 0%, rgb(var(--lilac) / 0) 72%);
  background-repeat:no-repeat;
}
body{
  margin:0; background:transparent; color:var(--ink);
  font-family:var(--sans); font-size:15px; line-height:1.5;
  -webkit-font-smoothing:antialiased;
}
.sheet{max-width:var(--sheet); margin:0 auto; padding:22px 16px 34px}
h1,h2,h3,.city .name,.total .usd,.thread .town{font-family:var(--serif); font-weight:600; margin:0}
a{color:inherit}
code{font-size:.88em; background:var(--mist); padding:1px 5px; border-radius:4px}
.num{font-family:var(--num); font-variant-numeric:tabular-nums}

/* ── шапка */
.masthead{position:relative; display:flex; flex-wrap:wrap; align-items:flex-end;
  justify-content:space-between; gap:10px; padding:2px 0 14px; overflow:hidden}
.eyebrow{margin:0; font-size:10.5px; letter-spacing:.24em; text-transform:uppercase; color:var(--quiet)}
.masthead h1{font-size:44px; line-height:1; letter-spacing:-.01em; margin-top:4px}
/* Единственное яркое, которое ничего не значит, — год в заголовке. Это имя
   страницы, а не её состояние: «2027» никто не прочтёт как горящий срок, и
   правило «яркое = важное» оно не размывает. Зато розовое рядом с холодным
   синим появляется там, где на страницу смотрят первым делом. */
.masthead h1 .year{color:var(--hot); font-size:24px; letter-spacing:.06em}
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
  text-transform:uppercase; color:var(--hot); font-weight:700}
.deadlines .cap::before{content:"◆"; margin-right:7px; font-size:8px; vertical-align:1px}
.deadlines .till{font-family:var(--serif); font-size:17px; font-weight:600;
  line-height:1.15; color:var(--ink)}
.deadlines .who{font-size:11.5px; color:var(--quiet)}
/* Сумма, которая сгорит, если пропустить срок, — единственное яркое число в
   шапке. Остальные деньги страницы тёмные и крупные; это — мелкое и красное,
   потому что важна не величина, а то, что у неё есть дата. */
.deadlines .cost .usd{font-family:var(--num); font-size:12px; font-weight:600; color:var(--hot)}
.deadlines .cost .jpy{font-family:var(--num); font-size:10.5px; color:var(--quiet);
  margin-left:5px}
.deadlines .left{font-size:12px; font-weight:700; color:var(--calm-ink)}
.deadlines .soon > .left,.deadlines .soon .left{color:var(--hot)}
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

/* ── нитка

   Линии во всю ширину над ниткой, над чеком, над «вписать своё» и над
   подвалом сняты 24 августа вечером. «Эксель» Ни помянула третий раз, и это
   не только про цвет: четыре горизонтали, режущие страницу поперёк, — и есть
   разлиновка. Разделяют разделы теперь воздух и перелив под ними; отступ,
   который держала линия, остался на месте, поэтому высота от снятия не
   поехала. Осталась ровно одна горизонталь — числовая ось нитки: там линия не
   разделяет, а сама и есть шкала, на ней стоят засечки дней. */
.thread{padding-top:16px; margin-bottom:18px}
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
/* Цвет текста приходит из разметки вместе с заливкой — это чернила города, а
   не общий `--ink`: у каждого тона свои, и держат они 8:1 именно к своему
   тону. Раньше здесь стояло `color:#fff`, и пастель его убила бы. */
.thread .bar{height:62px; border-radius:4px; position:relative; display:flex;
  align-items:flex-end; padding:0 12px 9px; overflow:hidden}
.thread .bar .n{font-size:12.5px; font-weight:600; letter-spacing:.01em}
.thread .bar .who{display:none}
/* Часы заезда и выезда были белыми на 90% — приглушением через прозрачность.
   На тёмных чернилах так делать нечем: прозрачность съедает контраст молча.
   Второстепенность сказана кеглем и весом, цвет тот же. */
.thread .bar .edge{position:absolute; top:9px; font-family:var(--num); font-size:10.5px;
  color:inherit; white-space:nowrap}
.thread .bar .edge.i{left:12px}
.thread .bar .edge.o{right:12px}
.thread .bar.air{background:transparent; border:1px dashed var(--rule); color:var(--quiet);
  background-image:repeating-linear-gradient(45deg,rgba(146,160,188,.16) 0 5px,transparent 5px 10px)}
.thread .bar.air .n{color:var(--quiet); font-weight:500}
/* Отрезок в воздухе прозрачный, и белые часы на нём не видны вовсе — их
   контраст к бумаге 1.15. Час вылета читается тем же тоном, что и подпись. */
.thread .bar.air .edge{color:var(--quiet)}
.thread .home{border-left:1px solid var(--rule); padding-left:11px; display:flex;
  flex-direction:column; justify-content:flex-end; height:62px}
.thread .home b{font-family:var(--serif); font-size:20px; line-height:1}
.thread .home span{font-size:9.5px; letter-spacing:.14em; text-transform:uppercase;
  color:var(--quiet); margin-top:4px}
/* Аэропорт возвращения — на самом последнем столбце: улетает она из Ханэды, а
   прилетала в Нариту, и в день отъезда это разница в дороге, а не буква. */
.thread .home .air{font-size:10px; font-family:var(--num); letter-spacing:0;
  text-transform:none; margin-top:2px}
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
.thread .move i{width:0; height:0; border-left:5px solid var(--calm);
  border-top:3.5px solid transparent; border-bottom:3.5px solid transparent; flex:none}
/* Чем и сколько ехать. Строка узкая по столбцам сетки, поэтому переносится, а
   не обрезается: половина названия поезда хуже двух строк. */
.thread .move .ride{display:flex; flex-wrap:wrap; gap:0 8px; padding-left:11px;
  font-size:10px; line-height:1.35; color:var(--quiet)}
.thread .move .hrs{font-family:var(--num)}
.thread .move .cost{font-family:var(--num); color:var(--calm-ink); font-weight:600}
/* Цены нет — пустое поле с подписью, как в «ещё не посчитано» внизу. Прочерк
   читается как «бесплатно», выдуманное число — как подтверждённое. */
.thread .move .cost.none{color:var(--quiet); font-weight:400; font-family:var(--sans)}
.thread .move .slot{display:inline-block; width:26px; border-bottom:1px solid var(--rule);
  margin-right:5px; vertical-align:2px}
/* Что покрывает записанное число — рядом с ним, а не отдельной строкой:
   строка съедала бы высоту нитки втрое чаще, чем добавляла смысл. */
.thread .move .covers{font-size:9.5px}
/* Перелёт стоит на столбце шириной в один день, а «Тбилиси → Нарита» в него
   не влезает строкой. Переносится, а не обрезается: половина названия
   аэропорта — это ровно та подпись, из-за которой едут не туда.
   Стрелка при переносе прижимается к первой строке: по центру двух строк она
   встаёт напротив второго слова и показывает не туда, куда указывает. */
.thread .move.fly .hd{white-space:normal; align-items:flex-start}
.thread .move.fly .hd i{margin-top:4px}
.thread .move.fly .ride{padding-left:0}

/* ── перелёт: два плеча и билет, три карточки в ряд

   Ряд, а не стопка, по той же причине, по которой в ряд поставлены свёртки
   справки: три полосы во всю ширину под ниткой — это три экрана прокрутки за
   тем, что читается одной строкой каждое. Закрытыми они держат две строки:
   куда-откуда-во сколько и подпись помельче.

   Стрелка нарисована той же треугольной меткой, что у подробностей
   проживания: на этой странице она значит «здесь есть что открыть», и второй
   знак для того же означал бы, что знаки надо запоминать. */
.flights{margin:0 0 18px}
.flights .row{display:grid; grid-template-columns:repeat(3,1fr); gap:9px}
.fly-fold{background:var(--card); border-radius:10px; padding:9px 13px 9px 11px}
.fly-fold > summary{cursor:pointer; list-style:none; display:grid;
  grid-template-columns:13px 1fr; gap:1px 5px; align-items:start}
.fly-fold > summary::-webkit-details-marker{display:none}
.fly-fold > summary::before{content:""; grid-row:1; align-self:start; margin-top:5px;
  width:0; height:0; border-left:6px solid var(--calm);
  border-top:4.5px solid transparent; border-bottom:4.5px solid transparent}
.fly-fold[open] > summary::before{border-left:4.5px solid transparent;
  border-right:4.5px solid transparent; border-top:6px solid var(--calm); border-bottom:0;
  margin-top:7px}
.fly-fold .path{grid-column:2; font-size:13.5px; font-weight:600; line-height:1.3}
/* Часы — тем же моноширинным, что и всюду на странице: время читается
   числом, а не словом, и в столбик оно должно вставать ровно. */
.fly-fold .path i{font-style:normal; font-family:var(--num); font-size:12.5px;
  font-weight:500; color:var(--deep)}
/* «туда» стоит в той же строке, что и сам путь, а не над ним: отдельной
   строкой этот ярлык стоил бы 25 точек высоты на всю страницу и ни одного
   слова смысла — направление и так читается по городам. */
.fly-fold .dir{font-size:9.5px; letter-spacing:.16em; margin-right:8px;
  text-transform:uppercase; color:var(--quiet); font-weight:700}
.fly-fold .ok{font-size:10.5px; font-weight:600; color:var(--done); letter-spacing:.02em}
.fly-fold .meta{grid-column:2; font-size:10.5px; color:var(--quiet); line-height:1.35}
.fly-fold .hops{list-style:none; margin:8px 0 0; padding:0; display:grid; gap:3px;
  font-size:11.5px}
.fly-fold .hops li{display:flex; flex-wrap:wrap; align-items:baseline; gap:0 8px}
.fly-fold .hops b{font-family:var(--num); font-size:11.5px; color:var(--calm-ink)}
.fly-fold .hops .way{font-family:var(--num); font-size:11px}
.fly-fold .hops .plane{font-size:10.5px; color:var(--quiet)}
/* Пересадка — не рейс, а пауза между ними: своей строкой, отступом и без
   номера. Иначе два рейса и полтора часа между ними читаются одним списком. */
.fly-fold .hops .wait{color:var(--quiet); font-size:10.5px; padding-left:13px;
  position:relative}
.fly-fold .hops .wait::before{content:"⟳"; position:absolute; left:0; font-size:9px}
.fly-fold .rows{margin:7px 0 0}
.fly-fold .fine{margin-top:6px}
/* Единственное яркое в блоке — то, чего у билета нет. Отмена без срока стоит
   дороже всех остальных штрафов вместе, и красное здесь именно поэтому. */
.fly-fold .nofree{color:var(--hot-ink); font-weight:700}
/* Примечания — не про билет, а про планирование, поэтому лежат открытыми и
   строкой, а не столбиком: три коротких мысли в ряд стоят одну высоту вместо
   трёх. */
.flights .mind{list-style:none; margin:8px 0 0; padding:0; display:flex;
  flex-wrap:wrap; gap:2px 22px; font-size:11px; color:var(--quiet)}
.flights .mind li{flex:1 1 300px; padding-left:14px; position:relative; line-height:1.35}
.flights .mind li::before{content:"◆"; position:absolute; left:0; top:1px; font-size:8px;
  color:var(--calm)}

/* ── заметка про ночь с двумя бронями */
.alert{border:1.5px solid var(--hot); background:var(--blush); border-radius:12px;
  padding:11px 16px; margin:0 0 18px; display:flex; flex-wrap:wrap; gap:6px 26px;
  align-items:baseline}
.alert.calm{border:1px solid var(--calm)}
.alert .says{flex:none; max-width:520px}
.alert .siren{margin:0; font-size:10px; letter-spacing:.2em; text-transform:uppercase;
  color:var(--hot); font-weight:700}
.alert.calm .siren{color:var(--calm)}
.alert .siren::before{content:"●"; margin-right:7px; font-size:8px; vertical-align:2px}
.alert.calm .siren::before{content:"◆"}
/* 17px — это уже текст, а не пометка: здесь яркое обязано быть тёмным своим
   вариантом, иначе 5.3:1 встанет там, где нужно 7:1. */
.alert h2{font-size:17px; margin-top:3px; color:var(--hot-ink)}
.alert.calm h2{color:var(--ink)}
.alert .lead{margin:2px 0 0; font-size:13.5px; color:var(--deep)}
.alert .facts{list-style:none; margin:0; padding:0; display:flex; flex-wrap:wrap; gap:2px 22px;
  font-size:12px; color:var(--quiet); flex:1; min-width:260px}
.alert .facts li{padding-left:16px; position:relative}
.alert .facts li::before{content:"—"; position:absolute; left:0; color:var(--calm)}
.alert .closing{margin:0; font-size:12.5px; font-style:italic; color:var(--deep); flex:none}
.alert .options{list-style:none; margin:0; padding:0; display:grid; gap:9px}
.alert .opt h4{font-size:15px}
.alert .watch{color:var(--hot); font-weight:600; font-size:12.5px}
.alert .watch .left,.cancel .left{display:block; font-weight:400; color:var(--quiet)}

/* ── карточки городов */
.cities{display:grid; grid-template-columns:repeat(4,1fr); gap:16px; align-items:start}
/* Рамки у карточки нет: белая плоскость на холодной бумаге отделяет себя
   сама, а обводка вокруг каждой из четырёх — половина того, из-за чего
   страница читалась таблицей. Радиус вырос с 6 до 10 по той же причине. */
.city{background:var(--card); border-radius:10px; overflow:hidden}
/* Цвет надписи — из разметки, чернилами города: см. `.thread .bar`. */
.city .cap{padding:12px 15px 11px}
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
   Внизу, где места больше, ту же тройку разводит фактура полосы.

   С 24 августа строка стоит не под ценой, а первой под стрелкой: снаружи
   карточки после цены не осталось ничего (её слово). Правило то же — сменился
   только родитель, поэтому у него теперь свой верхний отступ. */
.city .how{display:block; width:100%; font-size:11px; margin:2px 0 0}
.city .how span{margin-right:12px; padding-left:16px; position:relative}
.city .how span::before{content:""; position:absolute; left:0; top:3px; width:9px; height:9px;
  border-radius:2px; border:1.5px solid currentColor}
.city .paid::before{background:currentColor}
.city .due::before{box-shadow:inset 0 -3px 0 currentColor}
.city .paid{color:var(--done)} .city .due{color:var(--hot)} .city .onsite{color:var(--calm)}
.city .plain{color:var(--quiet); padding-left:0}
.city .plain::before{display:none}

/* ── подробности проживания: одна стрелка на карточку */
.stayfine{margin-top:12px; border-top:1px solid var(--hair)}
.stayfine > summary{cursor:pointer; list-style:none; display:grid;
  grid-template-columns:13px 1fr; gap:1px 6px; align-items:start;
  padding:9px 0 8px; min-height:36px}
.stayfine > summary::-webkit-details-marker{display:none}
.stayfine > summary::before{content:""; grid-row:1; align-self:start; margin-top:4px;
  width:0; height:0; border-left:6px solid var(--calm);
  border-top:4.5px solid transparent; border-bottom:4.5px solid transparent}
.stayfine[open] > summary::before{border-left:4.5px solid transparent;
  border-right:4.5px solid transparent; border-top:6px solid var(--calm); border-bottom:0;
  margin-top:6px}
.stayfine .lbl{grid-column:2; font-size:12px; color:var(--deep); font-weight:600}
.stayfine .hint{grid-column:2; font-size:10.5px; color:var(--quiet); line-height:1.3}
/* Заезд, выезд, адрес, телефон — разлинованы были каждой строкой, и это
   самое настоящее «эксель» на странице. Ключи набраны прописными в 9.5px и
   стоят своей колонкой: строки различимы и без линеек, а линейки только
   рисовали сетку. */
.rows{margin:2px 0 0}
.rows > div{display:flex; gap:10px; padding:5px 0}
.rows dt{flex:none; width:58px; font-size:9.5px; letter-spacing:.1em; text-transform:uppercase;
  color:var(--quiet); padding-top:2px}
.rows dd{margin:0; font-size:12px; line-height:1.35}
.rows dd.num{font-family:var(--num)}
.btn{display:block; min-height:20px; text-decoration:none; color:var(--ink);
  border-bottom:1px dotted var(--rule); padding:1px 0}
.btn.tel{font-family:var(--num); color:var(--quiet); border:0}
/* Помеченная бронь отличается не только цветом полоски, но и её толщиной —
   и объясняет себя словами внутри, а не одним оттенком слева.

   Обычная бронь полоски слева не носит вовсе: пока её носили все, толщина и
   цвет ничего не отличали — они лишь добавляли ещё одну вертикаль в столбик.
   Полоска появляется там, где есть что сказать.

   Лишний хвост комментария — звёздочка со слэшем — в середине этого же места
   (24 августа) закрывал его на три строки раньше, и всё, что ниже, до первой
   же скобки, браузер съедал как испорченное правило. Съедало ровно `.stay`:
   брони внутри карточек стояли без плоскости, без полей и без скруглений, а
   стиль в файле при этом был. Ни один тест этого не увидел — они читают
   разметку и высоту документа, а потерянная заливка не меняет ни того, ни
   другого. Поэтому проверка на плоскость брони теперь есть в `wide.py`, и она
   читает `getComputedStyle`.

   Написать этот хвост словами, а не знаками, пришлось по той же причине: в
   первый раз я объяснила поломку, повторив её, — и правило исчезло снова,
   ровно так же молча. Нашла его та самая новая проверка. */
.stay{margin-top:11px; padding:9px 11px; border-radius:8px; background:var(--mist)}
.stay.noted{border-left:4px solid var(--calm)}
.stay.clash{border-left:4px solid var(--hot)}
.stay .blabel{margin:0 0 4px; font-size:10.5px; color:var(--quiet); font-style:italic}
.stay .arriving{margin:0 0 7px; font-size:11.5px}
.stay .arriving b{display:block; font-size:12.5px}
.stay .arriving span{display:block; color:var(--quiet); font-size:11px; line-height:1.35}
.cancel{margin:0; font-size:11.5px}
.cancel .k{display:block; font-size:9.5px; letter-spacing:.11em; text-transform:uppercase;
  color:var(--quiet)}
.cancel b{display:block; font-size:11.5px; margin-top:1px}
.cancel .t{display:block; color:var(--quiet); font-size:11px}
.cancel .left{margin-top:2px; font-size:11px; font-weight:600; color:var(--calm)}
.cancel.soon .left{color:var(--hot)}
.extras{list-style:none; margin:9px 0 0; padding:0; font-size:11px; color:var(--quiet)}
.extras li{padding:1px 0 1px 11px; position:relative; line-height:1.4}
.extras li::before{content:"+"; position:absolute; left:0; color:var(--calm)}
.fine{list-style:none; margin:8px 0 0; padding:0; font-size:11px; color:var(--quiet)}
.fine li{padding:2px 0 2px 11px; position:relative; line-height:1.4}
.fine li::before{content:"·"; position:absolute; left:3px}

/* Стилей блока «хочу сходить» (`.wishes`, `.wish-cap`, `.wish-more`) здесь
   больше нет: сам блок ушёл из карточек городов 24 августа. Её записи-места
   переехали в «куплено отдельно» и рисуются общим `.own`, как брони. */
.cancelled{list-style:none; margin:12px 0 0; padding:0; font-size:11.5px; color:var(--quiet)}
.cancelled li{display:flex; flex-wrap:wrap; gap:0 8px; align-items:baseline}
.cancelled b{text-decoration:line-through; font-weight:600}
.cancelled .usd{font-family:var(--sans); font-size:11.5px; font-weight:600}
.cancelled .jpy{font-family:var(--num); font-size:11px; margin-left:5px}

/* ── деньги и пустые места */
.ledger{display:flex; flex-wrap:wrap; gap:22px 40px; align-items:flex-start;
  margin-top:20px; padding-top:16px}
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
.legend .paid{color:var(--done)} .legend .due{color:var(--hot)} .legend .onsite{color:var(--calm)}
.legend .paid::before{background:currentColor}
.legend .due::before{box-shadow:inset 0 -3px 0 currentColor}
.legend b,.legend span{color:var(--quiet)}
.legend b{color:var(--ink)}
.legend b{font-family:var(--num); color:var(--ink); margin-right:5px}
/* Средний столбец чека: «сверх этого» и линейка одна под другой. Ширину
   держит он, а не они, — иначе линейка при пустом списке оговорок расползлась
   бы на всю строку. */
.ledger .col{flex:1 1 250px; max-width:330px}
.beyond{max-width:330px}
.caveats{list-style:none; margin:8px 0 0; padding:0; font-size:11.5px; color:var(--quiet)}
.caveats li{padding:2px 0 2px 12px; position:relative; line-height:1.45}
.caveats li::before{content:"+"; position:absolute; left:0; color:var(--calm)}

/* ── линейка: иены в доллары и обратно

   Два поля и знак между ними. Рамка пунктирная — та же, которой на этой
   странице помечено «это не деньги в чеке»: у желаний и у пустых полей. Иначе
   набранная тысяча читалась бы как ещё одна сумма поездки.
   Поля ростом 38 точек: на телефоне в них надо попадать пальцем. */
.convert{margin-top:14px; border-top:1px dashed var(--rule); padding-top:10px}
.convert .pair{display:flex; align-items:center; gap:8px; margin-top:8px}
.convert .fld{flex:1 1 0; min-width:0; display:flex; align-items:center; gap:5px;
  background:var(--card); border:1px solid var(--rule); border-radius:7px; padding:0 9px;
  height:38px}
.convert .fld:focus-within{border-color:var(--calm); box-shadow:0 0 0 2px rgba(48,85,166,.18)}
.convert .fld i{font-style:normal; font-size:13px; color:var(--calm); font-weight:700}
.convert input{flex:1 1 0; min-width:0; width:100%; border:0; background:none; padding:0;
  font-family:var(--num); font-size:14px; color:var(--ink); height:100%}
.convert input:focus{outline:none}
.convert input::placeholder{color:var(--quiet); opacity:1}
.convert .swap{font-style:normal; font-size:13px; color:var(--quiet); flex:none}
.convert .fx{margin:7px 0 0; font-size:10.5px; color:var(--quiet); line-height:1.5}
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
.adder{margin-top:16px; padding-top:13px}
.knobs{display:flex; flex-wrap:wrap; align-items:center; gap:8px 10px}
.knobs .cap{margin:0 4px 0 0; font-size:9.5px; letter-spacing:.17em;
  text-transform:uppercase; color:var(--quiet)}
.knob{font-family:inherit; cursor:pointer; color:var(--ink); background:var(--card);
  border:1px solid var(--rule); border-radius:99px; padding:7px 13px; font-size:12.5px}
.knob:hover{background:var(--mist)}
.knob:focus-visible,.save:focus-visible,.drop:focus-visible{
  outline:2px solid var(--calm); outline-offset:2px}
.storesays{font-size:11.5px; color:var(--hot)}
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
.pane .says{font-size:12px; color:var(--hot)}
/* Её места — под бронями, за своей чертой: цену они дают в тот же чек, но
   куплено это ещё не значит. */
.kept-places{margin-top:12px; border-top:1px dashed var(--rule); padding-top:9px}
.kept-places .cap{margin:0 0 4px; font-size:10px; letter-spacing:.1em; text-transform:uppercase;
  color:var(--calm)}
.kept-places .sec-note{margin-top:6px}
.own .town{font-size:10.5px; color:var(--quiet); margin-left:6px}
.own .town.lost{color:var(--hot)}

/* Строка её записи — в «куплено» и в списке. */
.own{position:relative; padding:6px 0 7px 14px; line-height:1.35;
  border-bottom:1px solid var(--hair)}
.own::before{content:"◆"; position:absolute; left:0; top:7px; font-size:8.5px; color:var(--calm-ink)}
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
.chip.paid{color:var(--done)} .chip.paid::before{background:currentColor}
.chip.due{color:var(--hot)} .chip.due::before{box-shadow:inset 0 -2px 0 currentColor}
.chip.onsite{color:var(--calm)}
.tools{display:flex; gap:9px; margin-top:2px}
.ed,.rm{background:none; border:0; padding:2px 0; font-family:inherit; font-size:10.5px;
  color:var(--quiet); cursor:pointer; border-bottom:1px dotted var(--rule)}
.ed:hover,.rm:hover{color:var(--ink)}
/* Только что вписанное ею — розовым: на этой странице розовая плоскость
   значит «это её», и она же под визой, где дорого ошибиться. */
.own.fresh{background:var(--blush); border-radius:6px}
.rows-list{list-style:none; margin:0; padding:0}
.todo-group .own{padding-left:0}
.todo-group .own::before{display:none}
.todo-group .own .tab,.todo-group .own .tools{margin-left:31px}
#bought .none{display:none}
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
  color:var(--calm); font-weight:600}

/* ── свёрнутое: списки, дни, багаж

   Четыре свёртки лежат на одной конфетной плоскости, а не стоят четырьмя
   полосами в линейку. Прежде у каждой была своя нижняя линия и у первой
   верхняя — пять горизонталей на четыре строки, то есть буквально таблица, и
   ровно её Ни звала «экселем». Различает строки теперь воздух между ними, а
   всю стопку — плоскость под ней. Высоты это не стоило: пять снятых линий
   вернули столько же, сколько взяли поля коробки. */
.folds{margin-top:26px; background:var(--card); border-radius:12px;
  padding:2px 15px; box-shadow:var(--lift)}
.more{border:0}
/* 38px, а не 44: 44 — размер пальца, и он нужен на телефоне, где и стоит
   (см. запрос по max-width:700px ниже). На компьютере это четыре свёртки
   подряд, то есть 24 точки высоты, потраченные на промах мышью. */
.more > summary{cursor:pointer; list-style:none; padding:10px 2px; font-size:13px;
  letter-spacing:.14em; text-transform:uppercase; color:var(--quiet); font-weight:700;
  display:flex; align-items:center; gap:10px; min-height:38px}
.more > summary::-webkit-details-marker{display:none}
.more > summary::before{content:"+"; font-size:15px; color:var(--calm); width:12px}
.more[open] > summary::before{content:"–"}
.more > div{padding:0 2px 22px}
.sec-note{font-size:12px; color:var(--quiet); margin:0 0 14px}
.todo-cols{display:grid; gap:0 30px}
.todo-group{margin:0 0 16px}
.todo-group h3{font-size:14px; margin-bottom:5px; color:var(--calm-ink)}
.todo-group ul{list-style:none; margin:0; padding:0}
.todo-group li{border-bottom:1px solid var(--hair)}
.todo-group label{display:flex; gap:11px; align-items:flex-start; padding:10px 2px; cursor:pointer}
.todo-group input{position:absolute; opacity:0; width:0; height:0}
.tick{flex:none; width:20px; height:20px; margin-top:1px; border-radius:6px;
  border:1.5px solid var(--rule); background:var(--card); position:relative}
input:checked + .tick{background:var(--done); border-color:var(--done)}
input:checked + .tick::after{content:""; position:absolute; left:6px; top:2px; width:5px;
  height:10px; border:solid #fff; border-width:0 2px 2px 0; transform:rotate(42deg)}
input:focus-visible + .tick{outline:2px solid var(--calm); outline-offset:2px}
.txt{font-size:14px}
input:checked ~ .txt{color:var(--deep); text-decoration:line-through}
.txt em{display:block; font-size:12px; color:var(--quiet); font-style:normal; text-decoration:none}
.reset{margin-top:6px; background:none; border:1px solid var(--rule); border-radius:8px;
  padding:10px 14px; font-size:12.5px; color:var(--quiet); font-family:inherit; cursor:pointer}
/* ── дни: отрезок города развёрнут, день свёрнут
   ────────────────────────────────────────────────────────────────────
   Шестнадцать дней и сотня пунктов — самый длинный раздел страницы, и он
   единственный, у которого две ступени свёртки. Причина её: «слишком много
   листать вниз». Открытый отрезок города стоит шестнадцать строк, открытые
   дни — сто.

   Прозрачность здесь не используется нигде: `opacity` съедает контраст молча,
   и 5.6:1 из переменной превращается в 2.9:1 на экране. Приглушённое
   приглушено цветом и кеглем, а не прозрачностью.

   **Раздел идёт во всю полосу макета** — её слово 24 августа: «по дням
   расположите по ширине макета, а не по левой стороне». До этого дня план
   держал 940 точек внутри полосы 1266 и стоял у левого края, пока подпись над
   ним, справка и чек шли во всю ширину: раздел читался как недорисованный, а
   не как более узкий нарочно. Своего максимума у плана больше нет — ширину
   ему задаёт полоса страницы, как и остальным разделам. */
.run{border-top:1px solid var(--hair)}
.run:first-child{border-top:0}
.run > summary{cursor:pointer; list-style:none; display:flex; flex-wrap:wrap;
  align-items:baseline; gap:4px 10px; padding:9px 0 8px; min-height:34px}
.run > summary::-webkit-details-marker{display:none}
/* Цвет города — тот же, что в нитке и в карточке: полоска слева, а не заливка
   под текстом, иначе контраст пришлось бы мерить у каждого тона отдельно.
   Полоска рисуется чернилами, а не тоном: три пикселя пастели на белой
   карточке — 1.3:1, то есть полоски просто нет. */
.run > summary .ct{font-size:13px; font-weight:700; color:var(--calm-ink);
  border-left:3px solid var(--city-line); padding-left:8px}
.run > summary .sp{font-size:11.5px; color:var(--quiet)}
.run > summary .n{font-size:10px; letter-spacing:.08em; color:var(--quiet); margin-left:auto}
.rdays{padding:0 0 10px 11px}
/* Два столбца — её слово 24 августа: «сделай дни в два столбца». Сеткой, а не
   `column-count`: свёртка, разрезанная колоночным переносом, открывается
   половинками в двух колонках сразу, и день перестаёт быть одной вещью.
   `align-items:start` — чтобы открытый день не растягивал соседний пустотой.

   Столбцов ровно два и при полной ширине: лишняя ширина ушла им (452 → 608),
   а не третьей колонке. Третья разрезала бы день на 390 точек — это ширина
   телефона, где дни как раз идут в одну колонку, потому что уже не помещаются.

   `minmax(0,1fr)`, а не `1fr`: `1fr` не даёт колонке стать уже своего
   содержимого, и одна длинная ссылка без пробелов растянула бы сетку за край
   полосы вместо переноса. */
@media (min-width:820px){
  .rdays{display:grid; grid-template-columns:repeat(2,minmax(0,1fr));
    gap:0 34px; align-items:start}
}
.day{border-bottom:1px solid var(--hair)}
.day:last-child{border-bottom:0}
.day > summary{cursor:pointer; list-style:none; display:flex; align-items:center;
  gap:11px; padding:7px 2px; min-height:34px}
.day > summary::-webkit-details-marker{display:none}
.day > summary:hover .ttl{color:var(--calm-ink)}
.dt{width:30px; flex:none; text-align:center}
.dt b{display:block; font-family:var(--serif); font-size:19px; line-height:1; color:var(--ink)}
.dt i{font-style:normal; font-size:10px; color:var(--quiet)}
.day > summary .ttl{font-size:13.5px; font-weight:600; flex:1 1 auto; min-width:0}
.day > summary .cnt{flex:none; font-size:10px; color:var(--quiet);
  border:1px solid var(--hair); border-radius:20px; padding:2px 7px}
.day.move .dt b{color:var(--calm)}
.day.clash .dt b,.day.noted .dt b{color:var(--hot)}
/* Заголовок дня под грузом. С 24 августа это единственный способ унести пункт
   далеко — список дат Ни убрала, — и мишень обязана называть себя, пока над
   ней держат: без отклика бросок вслепую отличается от промаха только тем, что
   потом видно в дне. Тот же язык, что у открытого дня (`.items.over`): песок и
   пунктир, а не новый цвет. */
.day > summary.over{background:var(--mist); border-radius:6px;
  outline:1px dashed var(--rule)}
.dbody{padding:2px 0 12px 41px}
.dnote{margin:0 0 8px; font-size:12px; color:var(--deep); font-style:italic}
.items{list-style:none; margin:0; padding:0}
/* `position:relative` — под ручки: на компьютере они уезжают из потока совсем,
   см. правило про наведение ниже. */
.it{position:relative; display:flex; gap:11px; align-items:baseline; padding:5px 0;
  border-bottom:1px solid var(--hair)}
.it:last-child{border-bottom:0}
/* Полоса чтения строки — 72 знака, и это единственное, что не выросло вместе с
   разделом. Сегодняшние пункты до неё не достают (самый длинный — 264 точки
   при столбце 608), так что на её планах правило не видно вовсе; оно ловит то,
   что она впишет сама: заметка в 63 знака у нас уже есть, а строка во весь
   столбец читалась бы хуже короткой. Ширины столбца это не трогает — граница
   строки и линейка под пунктом остаются на месте. */
.it .wh{flex:1 1 auto; min-width:0; max-width:72ch}
.it .nm{font-size:13.5px; color:var(--ink)}
a.nm,.nm a.sp{color:var(--calm-ink); text-decoration:underline;
  text-decoration-color:var(--hair); text-underline-offset:2px}
.it .marks{display:inline}
.mk{display:inline-block; margin-left:7px; font-size:10px; letter-spacing:.06em;
  border-radius:20px; padding:1px 7px; white-space:nowrap}
/* `hidden` без этого правила не работает: `display:inline-block` выше
   перебивает его молча, и пустая пометка времени стала бы пустой пилюлей на
   каждой из 98 строк. Ровно этот капкан уже стоял на форме — «спрятано» в
   разметке и развёрнуто на экране. */
.it .mk[hidden],.it .nt[hidden]{display:none}
/* Пометка времени — не расписание, а связка: «заезд с 15:00», «заложить
   2 часа». Тише брони и без рамки: рамка сделала бы из неё требование. */
.mk.wn{color:var(--quiet); background:var(--mist); white-space:normal}
/* «Бронировать» — единственная пометка дня, зовущая что-то сделать, и
   единственная яркая: девять штук на шестнадцать свёрнутых дней. Розовая
   плоскость и красная рамка вместо прежней песочно-золотой — цвет сменился,
   устройство пометки нет. */
.mk.bk{background:var(--blush); color:var(--hot); border:1px solid var(--hair);
  text-decoration:none}
a.mk.bk{border-color:var(--hot)}
.mk.tr{color:var(--quiet); border:1px dashed var(--rule); white-space:normal}
.it .nt{display:block; font-size:11.5px; color:var(--quiet); font-style:normal}
/* Её пункт помечен ромбом — тем же, что и её записи в карточках городов:
   один язык для «это вписала я» во всех разделах. */
.it.mine .nm::before{content:"◆ "; font-size:8.5px; color:var(--calm-ink)}
.it.dragging{opacity:1; background:var(--mist); border-radius:6px}
.items.over{background:var(--mist); border-radius:6px; outline:1px dashed var(--rule)}
.it.fresh{background:var(--mist); border-radius:6px}
/* Пустой день обязан оставаться мишенью: список нулевой высоты поймать мышью
   нельзя, и «перенести сюда» превратилось бы в «перенести почти сюда». */
.items:empty{min-height:28px; border:1px dashed var(--hair); border-radius:6px}
.grip{flex:none; cursor:grab; color:var(--rule); font-size:12px; line-height:1;
  padding:0 1px; user-select:none}
.acts{flex:none; display:flex; align-items:center; gap:4px; margin-left:auto}
.acts button{font-family:inherit; font-size:11px; color:var(--quiet);
  background:none; border:1px solid var(--hair); border-radius:6px; padding:3px 7px;
  cursor:pointer; min-height:26px}
.acts button:hover{color:var(--ink); border-color:var(--rule)}
.acts .rm{font-size:12px; line-height:1; padding:3px 7px}
.addday{margin-top:9px; background:none; border:1px dashed var(--rule); border-radius:8px;
  padding:7px 12px; font-size:12px; color:var(--quiet); font-family:inherit; cursor:pointer;
  min-height:32px}
.foldall{margin:0 0 10px; background:none; border:1px solid var(--hair); border-radius:8px;
  padding:5px 11px; font-size:11.5px; color:var(--quiet); font-family:inherit;
  cursor:pointer; min-height:28px}
.foldall:hover{color:var(--ink); border-color:var(--rule)}
/* ── ручки: не в глаза, но в досягаемости

   Ни 2026-08-24: «подпись к блоку и все кнопки убивай, они только мусорность
   создают и место занимают». Осталось две — «правка» и крестик, — и обе уходят
   из спокойного вида, а не со страницы. Списка дат тут больше нет вовсе:
   дальний перенос делается броском на заголовок свёрнутого дня.

   Спрятано **прозрачностью**, а не `display:none` или `visibility:hidden`:
   оба выкидывают элемент из обхода клавиатурой, и «спрятано от мыши» молча
   стало бы «недостижимо без мыши». Из потока ручки при этом вынуты совсем —
   иначе место они занимали бы ровно так же, как и раньше.

   Нажатия ручки ловят всегда, даже невидимые, и это не недосмотр: гасить
   `pointer-events` вместе с прозрачностью означало бы состояние, в котором
   до кнопки нельзя дотянуться, пока не наведёшь, — а прицелиться без
   наведения нельзя ни мышью, ни проверкой. Мышь всё равно проходит над
   строкой первой и ручки показывает: невидимого нажатия не бывает. Названию
   это не мешает — под ручками оно закрыто непрозрачным фоном, то есть его
   не видно ровно тогда, когда по нему нельзя попасть.

   И всё это — только там, где мышь вообще есть. На телефоне наведения не
   бывает, и спрятать под него значит спрятать навсегда; узкое окно на
   компьютере тоже отдаём телефонной раскладке, чтобы два правила не спорили
   за одну строку. */
@media (hover:hover) and (min-width:701px){
  .it .grip{position:absolute; left:-15px; top:6px; opacity:0; transition:opacity .12s}
  .it .acts{position:absolute; right:0; top:50%; transform:translateY(-50%); margin:0;
    opacity:0; transition:opacity .12s;
    background:var(--paper); border-radius:8px; padding:2px 0 2px 14px}
  .it:hover .grip,.it:focus-within .grip,.it.dragging .grip{opacity:1}
  .it:hover .acts,.it:focus-within .acts{opacity:1}
  .addday{opacity:0; transition:opacity .12s}
  .day:hover .addday,.day:focus-within .addday{opacity:1}
}
.daysays{color:var(--hot); margin:-8px 0 12px}
/* Форма пункта — та же, что у записей, но своя: у пункта дня нет ни цены, ни
   состояния оплаты, и показывать ей пустые поля «сколько стоит» значило бы
   спрашивать про деньги там, где их нет. */
.itemform{margin:9px 0 0; padding:11px 13px; background:var(--card);
  border:1px solid var(--hair); border-radius:10px;
  display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:9px 12px}
.itemform .what{grid-column:1/-1; margin:0; font-family:var(--serif); font-size:15px}
.itemform .f{display:flex; flex-direction:column; gap:3px; min-width:0}
.itemform .f.wide{grid-column:1/-1}
.itemform label{font-size:9.5px; letter-spacing:.12em; text-transform:uppercase;
  color:var(--quiet)}
.itemform input{font-family:inherit; font-size:14px; color:var(--ink);
  background:var(--paper); border:1px solid var(--rule); border-radius:7px;
  padding:8px 9px; min-height:38px; width:100%; min-width:0}
.itemform .go{grid-column:1/-1; display:flex; flex-wrap:wrap; align-items:center; gap:9px 12px}
.itemform .says{font-size:12px; color:var(--hot)}
/* `#luggage` в начале не для красоты: без него правило доставало и ряд
   переездов в нитке, у которого тот же класс. Высоты это не меняло (нижний
   отступ там схлопывался с отступом самой нитки — проверено измерением, а не
   рассуждением), но раскладку ряда правило задавало через раз, по случайному
   порядку строк в файле. */
#luggage .moves{list-style:none; margin:0 0 14px; padding:0; display:grid; gap:10px}
#luggage .moves li{background:var(--card); border-radius:10px; padding:12px 14px}
#luggage .when{margin:0; font-size:10px; letter-spacing:.12em; text-transform:uppercase;
  color:var(--calm)}
#luggage .path{margin:5px 0 0; font-size:14.5px; font-family:var(--serif); display:flex;
  gap:8px; flex-wrap:wrap; align-items:baseline}
#luggage .path i{color:var(--calm-ink); font-style:normal}
#luggage .note{margin:1px 0 0; font-size:11.5px; color:var(--quiet)}
#luggage .lead{margin:0 0 12px; font-size:14px}
/* Кто везёт — первым и рамкой: до 24 августа имя службы и цена лежали порознь,
   а ссылки не было вовсе. Ссылка стоит внутри той же рамки, что и цена, чтобы
   «сколько» и «где смотреть» не приходилось искать по разным углам. */
#luggage .who{background:var(--mist); border-radius:10px;
  padding:12px 14px; margin:0 0 14px}
#luggage .name{margin:0; font-family:var(--serif); font-size:15px; font-weight:600}
#luggage .name i{font-style:normal; color:var(--calm-ink); margin:0 7px}
#luggage .order{margin:5px 0 0; font-size:12.5px; color:var(--deep); line-height:1.45}
#luggage .cost{margin:8px 0 0; font-size:12.5px; display:flex; flex-wrap:wrap;
  gap:2px 9px; align-items:baseline}
/* Строка цены — это число вперемешку со словами («за обе пересылки»), а
   моноширинный шрифт страницы стоит на числах. Целиком в нём она читается как
   код, поэтому здесь только жирный бронзовый. */
#luggage .cost b{color:var(--calm-ink); font-weight:700}
#luggage .cost span{color:var(--quiet); font-size:11.5px}
#luggage .who .btn{margin-top:9px}
.always{list-style:none; margin:0; padding:0; font-size:12.5px; color:var(--quiet)}
.always li{padding:3px 0 3px 17px; position:relative}
.always li::before{content:"✓"; position:absolute; left:0; color:var(--done); font-size:11px}

/* ── справка внизу: виза, до вылета, деньги, такс-фри
   ────────────────────────────────────────────────────────────────────
   Единственный раздел страницы, где написанное не про её поездку, а про
   внешние правила. Отсюда и вся его особенность: у каждой строки видно,
   откуда она взялась. Три вида, три разных знака, и ни один из них не
   держится на одном цвете — цвет читается не у всех и не на всяком экране.

   * факт — просто строка;
   * не подтверждено — пунктирная рамка, красная пометка словом и рядом то,
     что с этим делать («уточнить при записи»);
   * наше соображение — сплошная тонкая линия слева и своя пометка.

   Прозрачности здесь нет ни в одном правиле: `opacity` съедает контраст
   молча, а половина этого раздела — как раз мелкие пометки, которым просесть
   легче всего. */
.ref{margin-top:20px}
/* Виза стоит в той же рамке, что заметка про ночь с двумя бронями. На этой
   странице такая рамка значит одно: здесь дорого ошибиться. Виза — самый
   срочный срок из всех (вылет 4 января, подача только очно, конец декабря
   у японских учреждений нерабочий), поэтому она и не под стрелкой. */
.ref .visa{border:1.5px solid var(--hot); background:var(--blush); border-radius:12px;
  padding:11px 16px 9px; display:flex; flex-wrap:wrap; gap:4px 26px; align-items:baseline}
.ref .visa .says{flex:none; max-width:430px}
.ref .siren{margin:0; font-size:10px; letter-spacing:.2em; text-transform:uppercase;
  color:var(--hot); font-weight:700}
.ref .siren::before{content:"●"; margin-right:7px; font-size:8px; vertical-align:2px}
.ref .visa h3{font-size:17px; margin-top:3px; color:var(--ink)}
.ref .visa .lead{margin:2px 0 0; font-size:13.5px; color:var(--deep)}
/* Соображение, а не правило. Мысль, выданная за факт, — самая дорогая ошибка
   этого раздела, поэтому она помечена и снаружи, и внутри списка, одним и тем
   же словом: «наше соображение». */
.ref .think{margin:0; font-size:12.5px; color:var(--deep); line-height:1.45;
  flex:1 1 300px; min-width:260px; border-left:2px solid var(--calm); padding-left:11px}
.ref .think .mark{display:block; font-size:9.5px; letter-spacing:.12em;
  text-transform:uppercase; color:var(--calm); font-weight:700}
.ref .visa-more{flex:none; margin-left:auto}
.ref .visa-more > summary{cursor:pointer; list-style:none; display:flex; align-items:center;
  gap:9px; min-height:30px; font-size:11.5px; letter-spacing:.1em; text-transform:uppercase;
  color:var(--deep); font-weight:700; white-space:nowrap}
.ref .visa-more > summary::-webkit-details-marker{display:none}
.ref .visa-more > summary::before{content:"+"; font-size:15px; color:var(--hot); width:11px}
.ref .visa-more[open] > summary::before{content:"–"}
.ref .visa-more[open]{flex:1 1 100%; margin-left:0}
.ref .visa-more .facts{margin-top:4px}

/* Остальные — друг под другом.
   ────────────────────────────────────────────────────────────────────
   Ряд карточек 24 августа днём был поставлен ради высоты: три коротких
   предмета вместо трёх длинных полос, минус 44 точки. Вечером Ни сказала про
   него прямо: «до вылета, деньги и таксфри не нравится как разворачиваются.
   пусть стоят друг под другом». И это не вкусовая правка: ряд раскрывался
   вбок, открытая карточка занимала всю строку и толкала соседей вниз, а
   читаются они подряд — не «выбери одну из трёх», а «прочти три».

   Стопка от этого не стала «экселем»: полос в ряд нет, потому что нет ни
   линий между ними, ни обводок — белые плоскости на переливе, разделённые
   воздухом. Порядок прежний, по времени: до вылета → деньги → такс-фри, и
   следом приложения. Виза стоит выше всех и не под стрелкой: у неё срок.

   Стопка растяжимая нарочно (`grid` без счёта строк): пятый блок в данных
   встаёт в неё сам, ничего не отбирая у соседей. Раньше блоки были
   перечислены поимённо в разметке, и «приложения» так и лежали в данных
   невидимыми. */
.ref .ref-rows{display:grid; gap:10px; margin-top:12px}
/* Карточка вместо строки со шва́ми: белая плоскость, как у городов, — и
   ни одной обводки. Рамка вокруг каждой вернула бы ту же сетку, ради ухода
   от которой всё и затевалось. */
/* `border:0` и `margin-top:0` здесь не для красоты: класс `more` тащит с
   собой разделители общей стопки свёрток («решить», «куплено», «по дням»,
   «багаж») — и первая карточка получила бы её верхнюю линию и её отступ
   в 26 точек, стоя при этом в ряду. */
.ref .ref-row{background:var(--card); border:0; margin-top:0;
  border-radius:10px; padding:2px 14px}
/* Заголовок карточки — строчными, а не прописными вразрядку, как у свёрток
   выше. Причина не вкусовая: «ТАКС-ФРИ — С 1 НОЯБРЯ 2026 НАОБОРОТ» в 13px с
   разрядкой .14em просит около семисот точек и в трети экрана ломается на три
   строки. Карточка от этого выросла до 161 точки — то есть ряд, затеянный
   ради высоты, съедал больше, чем стопка, которую он заменил. */
/* `flex-wrap:wrap` — не украшение: подпись объявлена во всю строку
   (`flex:1 0 100%`), и без переноса она отбирает эту строку у заголовка,
   ужимая его до нулевой ширины. Заголовок такс-фри тогда переносится по
   букве в столбик высотой 140 точек. */
.ref .ref-row > summary{padding:11px 0 9px; align-items:flex-start; flex-wrap:wrap;
  text-transform:none; letter-spacing:0; font-size:13.5px; color:var(--ink);
  line-height:1.3; min-height:0}
.ref .ref-row > summary .ttl{flex:1 1 auto; min-width:0}
/* Подпись — на своей строке под заголовком: в трети экрана рядом с ним она
   не живёт. Отступ равен ширине плюса с зазором, чтобы висеть под словом. */
.ref .ref-row > summary .tag{flex:1 0 100%; padding-left:22px; margin-top:3px;
  text-transform:none; letter-spacing:0; line-height:1.4}
/* Ряд стал столбиком (см. `.ref-rows`), и ширины у заголовка теперь целая
   страница, а не треть. Подпись возвращается на строку заголовка — там, где
   она и жила до ряда: три свёртки по две строки вместо трёх по одной стоят 51
   точку высоты ни за что. */
@media (min-width:700px){
  /* Заголовок берёт ширину по себе, а не всю строку: иначе подпись улетает к
     правому краю страницы и между ними встаёт пустой коридор в полтысячи
     точек — та самая табличная строка с невидимой линейкой, от которой мы и
     уходим. Подпись — продолжение заголовка, а не второй столбец. */
  .ref .ref-row > summary .ttl{flex:0 1 auto}
  .ref .ref-row > summary .tag{flex:0 1 auto; padding-left:0; margin-top:0}
}
.ref .flip > summary{color:var(--calm-ink)}
.ref .flip > summary::before{color:var(--hot)}
.ref .flip > summary .tag{color:var(--hot)}
.ref .ref-body{padding:0 0 14px}
.ref .ref-body > .lead{margin:0 0 10px; font-size:13px; color:var(--deep); max-width:760px}

.ref .facts{list-style:none; margin:0; padding:0; display:grid; gap:7px 26px;
  grid-template-columns:repeat(auto-fit,minmax(330px,1fr)); align-items:start}
/* Полоски слева у факта больше нет, и это не потеря, а возврат к тому, что
   написано выше в этом же комментарии: «факт — просто строка». Пока полоску
   носили все двадцать четыре пункта, она ничего не различала — она рисовала
   решётку, а два помеченных вида тонули в ней наравне с остальными.
   Отступ слева остался: помеченные и непомеченные стоят по одной вертикали. */
.ref .facts li{font-size:13px; line-height:1.45; color:var(--ink); padding:5px 0 5px 15px;
  max-width:600px}
.ref .facts .say{display:block}
.ref .facts .mark{display:block; font-size:9.5px; letter-spacing:.12em;
  text-transform:uppercase; font-weight:700; margin-bottom:2px}
/* Непроверенное отличается от факта не оттенком, а рамкой и словом: пунктир —
   тот же язык, что у пустых полей и у строки «чего в итоге нет», и значит на
   этой странице ровно это — «здесь ещё не всё». */
.ref .unsure{border-left:2px dashed var(--hot); background:rgba(192,16,72,.05);
  border-radius:0 6px 6px 0; padding-right:10px}
.ref .unsure .mark{color:var(--hot)}
/* Что именно спросить в посольстве — рядом с самим пунктом, а не сноской
   внизу: сноску читают после того, как поверили. */
.ref .unsure .how{display:block; margin-top:3px; font-size:11px; color:var(--deep);
  font-style:italic}
.ref .unsure .how::before{content:"→"; margin-right:6px; font-style:normal; color:var(--hot)}
.ref .think-item,.ref .facts .think{border-left:2px solid var(--calm)}
.ref .facts .think .mark{color:var(--calm)}
/* Подчёркивание ссылки — линией под буквами, а не нижней границей коробки.
   Разница видна на телефоне: коробка ссылки держит 44 точки под палец, и
   `border-bottom` уезжает на самое её дно — под текстом повисает пунктирная
   линейка длиной в полстроки и в стороне от него. Это и есть та самая лишняя
   горизонталь, которую мы весь вечер снимаем; палец при этом никуда не
   девается, коробка остаётся прежней. */
.ref .facts .btn{display:inline-block; margin-top:4px; font-size:12px; color:var(--calm-ink);
  border-bottom:0; text-decoration:underline dotted; text-underline-offset:3px}

/* Совет: то, за чем стоит действие, а не чтение.
   ────────────────────────────────────────────────────────────────────
   Ни про Visit Japan Web: «наоборот выделить. и написать что лучше сделать».
   Выделен он не размером и не цветом текста — оба уже заняты происхождением
   пункта, — а тем, что лежит на своей плоскости и во всю ширину списка, а не
   в колонке наравне со страховками. Плоскость голубая, как у пометок: синий
   на этой странице значит «указание», а розовое (`--hot`, `--blush`) — «здесь
   дорого ошибиться», и совет не то и не другое. */
.ref .facts .ahead{grid-column:1/-1; background:var(--mist); border-radius:9px;
  padding:9px 13px; max-width:none}
.ref .facts .ahead .mark{color:var(--calm-ink)}
.ref .facts .ahead .say{max-width:760px}

/* Пара страховых: подпись и две ссылки под ней.
   ────────────────────────────────────────────────────────────────────
   Её слова: «страховки без подробностей оставь ссылки». Значит пункт здесь —
   это имя страховой и всё; условия, лимиты и цены она вычеркнула. Подпись
   («страховка на поездку — 16 дней») стоит во всю ширину, а под ней рядом
   две кнопки — так они читаются парой: одно решение с двумя вариантами, а не
   два отдельных факта. Разделяющей линии между ними нет и не будет: пара
   держится соседством, а не разлиновкой. */
.ref .facts .pack{grid-column:1/-1; padding:0}
.ref .facts .pair{list-style:none; margin:0; padding:0;
  display:flex; flex-wrap:wrap; align-items:baseline; gap:2px 10px}
.ref .facts .grp-head{flex:1 0 100%; padding-bottom:2px}
.ref .facts .only{padding:0 0 0 15px}
.ref .facts .only .btn{margin-top:0; padding:5px 13px; border-radius:999px;
  border-bottom:0; text-decoration:none; background:var(--card); box-shadow:var(--lift);
  font-size:12.5px}
/* Внутри свёртки плоскость уже белая — кнопка на белом теряется, и ей нужна
   своя. Голубая, а не розовая: это ссылка, то есть указание. */
.ref .ref-row .facts .only .btn,.ref .visa-more .facts .only .btn{background:var(--mist);
  box-shadow:none}

.colophon{margin-top:22px; padding-top:14px;
  font-size:11px; color:var(--quiet); display:flex; flex-wrap:wrap; gap:4px 10px}

/* ── экраны поуже: нитка встаёт столбиком, карточки в один ряд */
@media (min-width:560px){
  .sheet{padding:26px 22px 40px}
  .masthead h1{font-size:52px}
  .todo-cols{grid-template-columns:1fr 1fr}
}
@media (min-width:1000px){
  .masthead h1{font-size:58px}
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
  .thread .bar .edge{position:static; color:inherit; font-size:11px}
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
  /* `width:auto` тут не косметика, а починка. Класс `.dt` носит ещё и клетка
     с числом дня в разделе «по дням», а у неё `width:30px; flex:none` — и оно
     доставало сюда: «9 января» ужималось до тридцати точек и печаталось
     поверх «Токио → Киото». На компьютере этого не видно вовсе — там дата
     спрятана, — поэтому дожило до телефона, где нитка только из этих строк и
     состоит. Ширину задаём своей, чужую не трогаем: у клетки дня она нужна. */
  .thread .move .dt{display:inline; width:auto; text-align:left;
    font-family:var(--num); font-weight:400; color:var(--quiet); font-size:11px}
  .thread .move .ride{font-size:11px; padding-left:11px}
  .thread .paidrow{height:auto}
  .thread .paidbar{height:auto; background:none; border:0; margin-top:4px}
  .thread .paidbar span{position:static; white-space:normal; display:block}
  /* Три карточки перелёта в 390 точек — это три полосы по слову в строке.
     Столбиком: их всего три, и каждая закрытой держит две строки. */
  .flights .row{grid-template-columns:1fr}
  /* В стрелку надо попадать пальцем — 36 точек. На компьютере эти три точки
     платит вся страница высотой, а мышью хватает и тридцати трёх. */
  .fly-fold > summary{min-height:36px}
  .alert{display:block}
  .alert .facts{display:block; margin-top:8px}
  /* Справка на телефоне встаёт столбиком: у визы три части (что это, наше
     соображение, стрелка на подробности), и в 390 точек они рядом не живут. */
  .ref .visa{display:block}
  .ref .think{margin-top:9px; min-width:0}
  .ref .visa-more{margin-left:0; margin-top:6px}
  /* Подпись свёртки — на свою строку, под заголовок. Рядом в 390 точек они
     встают двумя узкими столбцами, и оба переносятся посередине слова:
     «ЧТО НУЖНО | 7 ПУНКТОВ · 3 БЕЗ» читается как одна фраза, которой нет.
     Отступ равен ширине плюса с зазором — подпись висит под своим словом. */
  .ref .visa-more > summary{min-height:44px; white-space:normal; flex-wrap:wrap}
  /* Отступ внутренний, а не внешний: ячейка шириной в целую строку плюс
     внешние 22 точки — это строка шириной 100% + 22, и страница уезжает
     вбок ровно на них. Внутренний отступ при `border-box` живёт внутри. */
  .ref .visa-more > summary .tag{flex:1 0 100%; padding-left:20px}
  .ref .ref-row > summary{flex-wrap:wrap}
  /* Основа 0, а не auto: перенос по строкам считается по желаемой ширине
     ячейки, а не по ужатой. С `auto` заголовок такс-фри просит 600 точек,
     не влезает рядом с плюсом и уезжает на строку ниже целиком — сжиматься
     он начал бы уже потом, когда переносить поздно. */
  .ref .ref-row > summary .ttl{flex:1 1 0; min-width:0}
  .ref .ref-row > summary .tag{flex:1 0 100%; padding-left:22px}
  .ref .facts{grid-template-columns:1fr}
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
  .btn{min-height:36px; display:flex; align-items:center}
  .knob,.ed,.rm,.save,.drop{min-height:36px; display:inline-flex; align-items:center}
  .pane{grid-template-columns:1fr}
  .pane .f.wide{grid-column:span 1}
  .stayfine > summary{min-height:44px; align-content:center}
  .more > summary{min-height:44px; padding:13px 2px}
  /* Дни на телефоне: свёртки и ручки — под палец. Переставлять пункты тут
     нечем совсем: перетаскивание пальцем браузер не отдаёт, а список дат
     Ни убрала 24 августа. Правка, «+ пункт» и крестик работают; порядок она
     собирает с компьютера, где два столбца держат все дни на одном экране. */
  .run > summary,.day > summary{min-height:44px; padding:11px 2px}
  .rdays{padding-left:4px}
  .dbody{padding-left:14px}
  .it{flex-wrap:wrap}
  .acts{margin-left:0; flex:1 1 100%; flex-wrap:wrap}
  .acts button{min-height:36px; display:inline-flex; align-items:center}
  .grip{display:none}
  .addday,.foldall{min-height:36px}
  .itemform{grid-template-columns:1fr}
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

  /* То же и в карточке города. С 24 августа срок отмены лежит под стрелкой —
     её слово, «всё после ценника под кат», — и прошедший срок оказался бы
     спрятан вдвойне: снаружи не видно ни даты, ни того, что она сгорела.
     Стрелка раскрывается сама ровно в этом случае и только в нём: карточка,
     у которой всё в порядке, остаётся свёрнутой, как она и просила. */
  Array.prototype.forEach.call(document.querySelectorAll(".city .stayfine"), function(fold){
    if (fold.querySelector(".cancel.gone")) fold.open = true;
  });

  /* Галочки переехали отсюда в хранилище (см. ниже, «её страница»): список,
     который забывает отмеченное при смене телефона, — это список, которому
     нельзя доверить визу. Ключ `japan2027.todo.v1` в localStorage больше не
     пишется и не читается; старое значение, если оно там осталось, просто
     лежит мёртвым грузом и ни на что не влияет. */

  /* ── линейка: иены в доллары и обратно
     ────────────────────────────────────────────────────────────────────
     Стоит здесь, а не в «её странице», нарочно: линейка обязана считать при
     мёртвом хранилище и без сети. Ни хранилища, ни сети она не касается —
     набранное живёт до перезагрузки и никуда не уезжает.

     Курс берётся из того же `#japan-data`, что и чек, и считается тем же
     `money.js`. Своего числа и своей арифметики у линейки нет: два способа
     посчитать одно и то же — это два разных числа с одним именем.

     Заполняется всегда **другое** поле, а не то, в котором печатают: иначе
     «1 000» превращалось бы в «1000» под пальцем, а курсор прыгал бы в конец
     на каждом знаке. */
  var ruler = document.querySelector(".convert");
  var island = document.getElementById("japan-data");
  if (ruler && island && window.JapanMoney) {
    /* Курс не запоминается разово: он может приехать свежим уже после того,
       как страница нарисовалась (см. `FX_JS`). Поэтому берётся каждый раз
       заново из одного общего места — иначе линейка считала бы по
       вчерашнему, пока чек рядом показывает сегодняшний. */
    window.JapanFx = window.JapanFx || JSON.parse(island.textContent).fx;
    function fxNow(){ return window.JapanFx; }
    var THIN = "\\u202f";
    var jpyBox = ruler.querySelector('[data-conv="jpy"]');
    var usdBox = ruler.querySelector('[data-conv="usd"]');

    function group(n){
      return String(n).replace(/\\B(?=(\\d{3})+(?!\\d))/g, THIN);
    }
    /* Она пишет так, как удобно: «1 000», «1,000», «1000». Разделителем
       считаем всё, что не цифра и не точка с запятой; запятая в дробной части
       — это та же точка. Пустое и «просто минус» — не число, а не ноль:
       ноль на этой странице значит «бесплатно». */
    function num(raw){
      var s = raw.replace(/[^\\d.,-]/g, "").replace(",", ".");
      if (!/\\d/.test(s)) return null;
      var v = parseFloat(s);
      return isFinite(v) && v >= 0 ? v : null;
    }
    function link(from, to, convert){
      from.addEventListener("input", function(){
        var v = num(from.value);
        to.value = v === null ? "" : group(convert(v));
      });
    }
    link(jpyBox, usdBox, function(v){ return JapanMoney.toUsd(v, fxNow()); });
    link(usdBox, jpyBox, function(v){
      return JapanMoney.yenOf({ amount: v, currency: "usd" }, fxNow());
    });
  }
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

  /* Место рисуется с именем города рядом. Раньше город был очевиден — строка
     лежала в его карточке; теперь все места лежат одной стопкой, и без имени
     запись не отвечает на вопрос «где это». Города, которого на странице нет,
     строка не скрывает, а называет вслух: молчаливая пропажа — ровно та беда,
     от которой в check() стоит правило №6. */
  function placeLine(entry){
    var li = el("li", "own");
    li.setAttribute("data-id", entry.id);
    var head = el("span", "head");
    head.appendChild(el("b", null, entry.title));
    var town = null;
    (data.cities || []).forEach(function(x){ if (x.id === entry.stay) town = x.city; });
    head.appendChild(town ? el("span", "town", town)
                          : el("span", "town lost", "город не найден"));
    li.appendChild(head);
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
    var byGroup = {};
    Array.prototype.forEach.call(document.querySelectorAll("[data-mine-todo]"), function(node){
      empty(node);
      byGroup[node.getAttribute("data-mine-todo")] = node;
    });
    var boughtList = document.querySelector("[data-mine-booking]");
    empty(boughtList);
    /* Один мешок на все её места. Мешков по городам больше нет — «хочу
       сходить» ушло из карточек, — и раскладывать места по городам стало не
       по чему. Зато и потеряться им негде: город, которого нет, теперь не
       прячет строку, а пишется на ней (см. placeLine). */
    var placeList = document.querySelector("[data-mine-place]");
    empty(placeList);

    state.entries.forEach(function(entry){
      if (entry.kind === "place") {
        if (placeList) placeList.appendChild(placeLine(entry));
      } else if (entry.kind === "booking") {
        if (boughtList) boughtList.appendChild(boughtLine(entry));
      } else {
        var where = byGroup[entry.group] || byGroup["Ещё"];
        if (where) where.appendChild(todoLine(entry));
      }
    });

    /* Подпись «места, записанные раньше» появляется вместе с первым местом:
       новых отсюда не добавить, и пустая рамка была бы карточкой-призраком. */
    var placeBox = document.querySelector("[data-places]");
    if (placeBox) placeBox.hidden = !(placeList && placeList.firstChild);

    var spare = document.querySelector("[data-spare]");
    if (spare) spare.hidden = !spare.querySelector("li");

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

    /* Подписи у «куплено отдельно» сейчас нет вовсе — из четырёх свёрток её
       носит только «Багаж», — и этот кусок работает вхолостую. Он всё же
       считает и брони, и её места: вернётся подпись — она обязана называть
       всё, что лежит внутри. Написать «пусто» над разделом, где лежит место с
       ценой, значило бы уверять, что открывать нечего, пока цена идёт в чек. */
    var boughtTag = document.querySelector('[data-tag="bought"]');
    if (boughtTag) {
      var mine = state.entries.filter(function(x){
        return x.kind === "booking" || x.kind === "place";
      });
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
    /* Здесь стояла строка «сложено из показанного: ¥… — жильё и твои записи».
       Ни вычеркнула её 24 августа, и вычеркнула именно **разговор о сумме**, а
       не саму сверку: итог по-прежнему обязан сходиться со столбиком разделов
       (`.parts`) и с разбивкой оплаты, и это по-прежнему проверяется — в
       `hands.py` числами со страницы и в `entries.test.mjs` на самом `tally`.
       Строка их только пересказывала вслух.

       Что тут когда-то сломалось, стоит помнить и без строки: она называла
       `data.housing.jpy` вместо итога и потому доказывала не ту сумму — ¥290 675
       при итоге ¥518 042. Молча, потому что жильё никуда не делось, а цифра
       выглядела правдоподобной. Вернётся строка — вернётся и эта ловушка. */
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

  /* Курс приехал свежим уже после отрисовки. Чек считается из `data.fx`, так
     что достаточно подменить его и перерисовать: своей арифметики здесь нет.

     `housing.usd` пересчитывает не этот кусок, а `FX_JS` — и не из общей
     иены, а сложением показанных городских долларов. Причина записана у
     `ledger`: иначе четыре числа в столбик дают на доллар больше, чем итог
     под ними, и это первое, что бросается в глаза. */
  window.addEventListener("japan-fx", function(event){
    var fresh = event.detail;
    if (!fresh || !fresh.fx) return;
    data.fx = fresh.fx;
    if (typeof fresh.housingUsd === "number") data.housing.usd = fresh.housingUsd;
    paint();
  });

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

  /* Кнопок теперь две — «бронь или билет» и «в то-до». Место отсюда больше не
     заводится: Ни 2026-08-24 убрала «хочу сходить» из карточек и вписывает
     места в днях. `openForm("place", …)` при этом жив и зовётся правкой из
     самой строки — старая запись обязана открываться. */
  Array.prototype.forEach.call(document.querySelectorAll("[data-add]"), function(button){
    button.addEventListener("click", function(){
      openForm(button.getAttribute("data-add"), null);
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
      /* Правленое место лежит в «куплено отдельно» рядом с бронями — туда же
         и раскрываем, иначе подсветка сработает внутри закрытой свёртки и
         сохранённое будет выглядеть пропавшим. */
      var fold = document.querySelector('[data-fold="' + (kind === "todo" ? "todo" : "bought") + '"]');
      if (fold) fold.open = true;
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


# ─────────────────────────────────────────── её дни

# Курс на сегодня. Страница нарисована с курсом, впечатанным сборкой, и это
# честное число со своей датой. Здесь она спрашивает свежий и, если он приехал,
# переписывает доллары — все сразу, из иены, тем же `money.js`.
#
# Ни, 10 сентября: «конвертер сделай так, чтобы он был привязан к дате
# конвертации, сейчас там за август стоит».
#
# Ничего не спросилось — ничего и не меняется: остаётся впечатанный курс со
# своей подписью. Показать вчерашнее число с вчерашней датой можно, с
# сегодняшней — нет.
FX_JS = """
(function(){
  "use strict";
  var box = document.getElementById("japan-data");
  if (!box || !window.JapanMoney || !window.fetch) return;
  window.JapanFx = window.JapanFx || JSON.parse(box.textContent).fx;

  var THIN = "\u202f";
  function group(n){
    return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, THIN);
  }

  /* Доллар пересчитывается из иены, а не из доллара: обратный пересчёт
     «$807 → ¥ → $» на другом курсе даёт третье число, не равное ни одному
     из двух. Иена рядом — настоящая цена, она не трогается вовсе. */
  function repaint(fx){
    var cities = 0;
    Array.prototype.forEach.call(document.querySelectorAll("[data-yen]"), function(node){
      var yen = Number(node.getAttribute("data-yen"));
      if (!isFinite(yen)) return;
      node.textContent = "$" + group(JapanMoney.toUsd(yen, fx));
      if (node.parentNode && node.parentNode.className === "price") {
        cities += JapanMoney.toUsd(yen, fx);
      }
    });
    return cities;
  }

  /* Подпись печатается по образцу из разметки, а не собирается здесь заново:
     слова про «платится в иенах» живут в сборке, и второе их написание
     разошлось бы с первым в первый же день. */
  function caption(fx){
    Array.prototype.forEach.call(document.querySelectorAll("[data-fx]"), function(node){
      var pattern = node.getAttribute("data-fx");
      if (!pattern) return;
      node.textContent = pattern
        .replace("{rate}", String(fx.usd_per_jpy))
        .replace("{date}", fx.human || fx.as_of || "");
    });
  }

  fetch("/api/fx", { headers: { accept: "application/json" } })
    .then(function(answer){ return answer.json(); })
    .then(function(said){
      if (!said || !said.ok || !said.fx) return;
      var fresh = said.fx;
      if (!(fresh.usd_per_jpy > 0)) return;
      /* Тот же курс, что уже стоит, — это не новость: перерисовывать нечего,
         и лишняя перерисовка чека сбросила бы её раскрытые «подробнее». */
      if (fresh.usd_per_jpy === window.JapanFx.usd_per_jpy
          && fresh.as_of === window.JapanFx.as_of) return;
      window.JapanFx = fresh;
      var cities = repaint(fresh);
      caption(fresh);
      window.dispatchEvent(new CustomEvent("japan-fx", {
        detail: { fx: fresh, housingUsd: cities },
      }));
    })
    .catch(function(){ /* курс не приехал — страница остаётся на впечатанном */ });
})();
"""


DAYS_JS = """
(function(){
  "use strict";

  /* Раздел дней: тасовать, переносить, дописывать, убирать.

     **Строки не рисуются заново — они двигаются.** Всё, что видно в пункте
     (ссылка на карту, метка «бронировать», сайт, отсылка к переездам), уже
     собрано питоном в `by_day`. Нарисовать то же самое второй раз здесь
     значило бы завести два описания одной вещи, и разойтись они успели бы
     молча: питон бы поправили, а браузер нет. Поэтому расстановка — это
     `appendChild` уже существующего узла, а не разметка строкой.

     Своё она рисует только там, где питону нечего было рисовать: её
     собственные пункты и её правки поверх файлового текста.

     **Название, разрезанное по местам, браузер не пересобирает.** «Yasaka
     Shrine, Maruyama Park, Chion-in» — три ссылки внутри одной строки, и
     собрать их здесь второй раз значило бы завести второе описание. Пока она
     не тронула ни название, ни поисковую строку, сборочная разметка просто
     остаётся на месте; тронула — разбивка снимается, потому что где в её
     новом тексте какие места, мы не знаем, а угадать значит увести ссылку не
     туда.

     **Ручек нет, пока хранилище не ответило.** Кнопка «убрать», которой некуда
     нажать, — обещание, которого страница не может сдержать; а «убрал, но не
     сохранилось» на её плане стоит дороже, чем отсутствие кнопки. Пока
     расстановка не доехала, раздел остаётся тем, что собрано: планом из файла
     со ссылками, и строкой о том, почему он такой.

     **Ручки заводятся на день при первом открытии.** Кнопки, ручка для мыши и
     `draggable` на каждый из сотни пунктов — это работа, проделанная ради дня,
     в который она, может, и не заглянет.

     **Между днями пункт ездит только мышью.** Список дат у каждой строки убран
     24 августа — её слово: «поэтому я попросила сделать дни в два столбца, а
     не колбасой вниз». Дальний перенос — бросок на заголовок свёрнутого дня;
     свёрнутые дни в два столбца помещаются на один экран, и целиться есть во
     что. Клавиатурой пункт между днями больше не переносится: список был
     единственным таким способом, а у перетаскивания клавиатурной пары нет.
     Правка, «+ пункт» и крестик с клавиатуры работают по-прежнему. */

  var box = document.getElementById("japan-data");
  var plan = document.querySelector("[data-plan]");
  if (!box || !plan) return;

  var DAYS = JSON.parse(box.textContent).days || [];
  var API = "/api/days";
  var MAPS = "https://www.google.com/maps/search/?api=1&query=";

  var says = document.querySelector("[data-days-says]");
  var state = { order: {}, own: {}, edits: {}, live: false };
  /* Каким пункт приехал из файла. Снимается один раз, до первой правки:
     читать «как было» из уже переписанной строки — это способ потерять
     файловый текст в тот момент, когда она снимет свою правку. */
  var seed = {};
  /* Сборочные названия, разрезанные по местам, — снятые до первой правки.
     Из них же восстанавливается разбивка, когда она снимает свою правку. */
  var built = {};
  var nodes = {};
  var editing = null;

  function el(name, cls, text){
    var node = document.createElement(name);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }
  function plural(n, one, few, many){
    var a = Math.abs(n) % 100, b = a % 10;
    if (a > 10 && a < 20) return many;
    if (b > 1 && b < 5) return few;
    if (b === 1) return one;
    return many;
  }
  function tell(words){
    if (!says) return;
    says.textContent = words || "";
    says.hidden = !words;
  }

  /* ── чтение и рисование строки */

  /* Поисковая строка пункта. У разрезанного по местам названия она лежит
     отдельным `data-map`: ссылкой такая строка целиком не становится, но
     адрес у неё есть, и форма правки обязана показать его, а не пустое поле. */
  function mapOf(node){
    if (!node || !node.getAttribute) return "";
    if (node.hasAttribute("data-map")) return node.getAttribute("data-map");
    var href = node.getAttribute("href");
    if (!href) return "";
    var at = href.indexOf("query=");
    if (at < 0) return "";
    try { return decodeURIComponent(href.slice(at + 6).replace(/\\+/g, " ")); }
    catch (e) { return ""; }
  }

  function readItem(li){
    var title = li.querySelector('[data-part="title"]');
    var time = li.querySelector('[data-part="time"]');
    var note = li.querySelector('[data-part="note"]');
    return {
      id: li.getAttribute("data-item"),
      time: time && !time.hidden ? time.textContent : "",
      title: title ? title.textContent : "",
      note: note && !note.hidden ? note.textContent : "",
      map: mapOf(title),
      spots: !!(title && title.hasAttribute("data-spots"))
    };
  }

  /* Название — ссылка ровно тогда, когда есть что искать на карте. Она
     дописала поисковую строку — строка становится ссылкой; стёрла — перестаёт.
     Подменять сам узел приходится потому, что «а» и «span» это разные теги, а
     ссылка без адреса — самая тихая из поломок: выглядит как ссылка, ведёт в
     никуда. */
  function setTitle(li, title, map){
    var wh = li.querySelector(".wh");
    var was = li.querySelector('[data-part="title"]');
    var want = map ? "A" : "SPAN";
    var node = was;
    if (!was || was.tagName !== want) {
      node = document.createElement(map ? "a" : "span");
      node.className = "nm";
      node.setAttribute("data-part", "title");
      if (was) wh.replaceChild(node, was);
      else wh.insertBefore(node, wh.firstChild);
    }
    node.textContent = title;
    if (map) {
      node.setAttribute("href", MAPS + encodeURIComponent(map));
      node.setAttribute("target", "_blank");
      node.setAttribute("rel", "noopener");
    } else {
      node.removeAttribute("href");
      node.removeAttribute("target");
      node.removeAttribute("rel");
    }
  }

  /* Вернуть сборочное название на место — тем самым узлом, каким его собрал
     питон. Клон, а не разметка строкой: собирать три ссылки здесь заново
     значило бы держать второе описание одной вещи. */
  function keepTitle(li, id){
    var was = li.querySelector('[data-part="title"]');
    if (was && was.hasAttribute("data-spots")) return;
    var fresh = built[id] ? built[id].cloneNode(true) : null;
    if (!fresh) return;
    var wh = li.querySelector(".wh");
    if (was) wh.replaceChild(fresh, was);
    else wh.insertBefore(fresh, wh.firstChild);
  }

  function paintItem(li, item){
    var time = li.querySelector('[data-part="time"]');
    if (time) {
      time.textContent = item.time || "";
      time.hidden = !item.time;
    }
    if (item.spots) keepTitle(li, item.id);
    else setTitle(li, item.title || "", item.map || "");
    var note = li.querySelector('[data-part="note"]');
    if (note) {
      note.textContent = item.note || "";
      note.hidden = !item.note;
    }
  }

  function shell(id){
    var li = el("li", "it mine");
    li.setAttribute("data-item", id);
    var wh = el("span", "wh");
    var marks = el("span", "marks");
    /* Пометка времени лежит там же, где у собранного пункта, и так же
       прячется пустой: два разных места для одной вещи — это два разных
       способа её потерять. */
    var time = el("span", "mk wn");
    time.setAttribute("data-part", "time");
    time.hidden = true;
    marks.appendChild(time);
    wh.appendChild(marks);
    var note = el("em", "nt");
    note.setAttribute("data-part", "note");
    note.hidden = true;
    wh.appendChild(note);
    li.appendChild(wh);
    return li;
  }

  Array.prototype.forEach.call(plan.querySelectorAll(".it"), function(li){
    var id = li.getAttribute("data-item");
    nodes[id] = li;
    seed[id] = readItem(li);
    var title = li.querySelector('[data-part="title"]');
    if (title && title.hasAttribute("data-spots")) built[id] = title.cloneNode(true);
  });

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

  /* Ответ на правку — вся расстановка целиком, и раскладываем мы именно её.
     Считать порядок второй раз здесь нельзя: два способа разложить одно и то
     же дадут два разных порядка с одним именем. */
  function adopt(said){
    state.order = said.order || {};
    state.own = said.own || {};
    state.edits = said.edits || {};
    state.live = true;
    tell("");
    lay();
  }

  function lay(){
    var placed = {};
    DAYS.forEach(function(day){
      var list = plan.querySelector('[data-day-items="' + day.date + '"]');
      if (!list) return;
      (state.order[day.date] || []).forEach(function(id){
        var mine = state.own[id];
        var li = nodes[id];
        if (!li) {
          if (!mine) return;              /* ни файлового пункта, ни её — нечего показать */
          li = nodes[id] = shell(id);
        }
        paintItem(li, mine || merged(id));
        list.appendChild(li);             /* appendChild переносит, а не копирует */
        placed[id] = true;
      });
      /* Ручки заводятся только в уже открытых днях: дописанный пункт обязан
         иметь их сразу, а закрытый день по-прежнему не платит за то, во что
         она не заглядывала. */
      var fold = plan.querySelector('[data-day="' + day.date + '"]');
      if (state.live && fold && fold.open) wireDay(fold);
    });

    /* Убранное уходит со страницы, но остаётся в нашей памяти: она может
       вернуть его правкой файла, и тогда узел уже есть. */
    Object.keys(nodes).forEach(function(id){
      if (!placed[id] && nodes[id].parentNode) nodes[id].parentNode.removeChild(nodes[id]);
    });
    counts();
  }

  function merged(id){
    var base = seed[id] || { id: id, time: "", title: "", note: "", map: "", spots: false };
    var patch = state.edits[id];
    if (!patch) return base;
    var out = { id: id, time: base.time, title: base.title, note: base.note,
                map: base.map, spots: base.spots };
    ["time", "title", "note", "map"].forEach(function(key){
      if (typeof patch[key] === "string") out[key] = patch[key];
    });
    /* Разбивка по местам — про тот текст, что пришёл из файла. Она переписала
       название или поисковую строку — где в новой строке какие места, мы не
       знаем, и притворяться, что знаем, значит вести ссылку не туда.

       Сравниваются значения, а не наличие ключа: форма отправляет все четыре
       поля разом, поэтому правка одной подробности кладёт в хранилище и
       название — то же самое, буква в букву. Считать это переписыванием
       значило бы снять разбивку навсегда с первой же правки чего угодно. */
    if ((typeof patch.title === "string" && patch.title !== base.title)
        || (typeof patch.map === "string" && patch.map !== base.map)) out.spots = false;
    return out;
  }

  function counts(){
    Array.prototype.forEach.call(plan.querySelectorAll("[data-day-items]"), function(list){
      var day = list.closest(".day");
      var badge = day ? day.querySelector("[data-count]") : null;
      if (badge) badge.textContent = list.children.length;
    });
  }

  function fail(error){
    tell("не сохранилось: " + error.message);
  }

  function send(method, body, andThen){
    return ask(method, body).then(function(said){
      adopt(said);
      if (andThen) andThen(said);
    }).catch(fail);
  }

  /* ── ручки: правка, крестик и сама строка как груз */

  function dayOf(li){
    var list = li.closest("[data-day-items]");
    return list ? list.getAttribute("data-day-items") : "";
  }

  function wireItem(li){
    if (li.getAttribute("data-wired") === "yes") return;
    li.setAttribute("data-wired", "yes");

    var grip = el("span", "grip", "\\u2059");
    grip.setAttribute("aria-hidden", "true");
    li.insertBefore(grip, li.firstChild);
    li.setAttribute("draggable", "true");

    var acts = el("span", "acts");

    var edit = el("button", "ed", "правка");
    edit.type = "button";
    edit.addEventListener("click", function(){ openForm(dayOf(li), li); });

    /* Ни 2026-08-24: «убрать проставь крестиком просто». Слово ушло из
       кнопки, но не из подписи: крестик без имени — единственная ручка,
       которую нельзя прочитать ни глазами, ни голосом. */
    var drop = el("button", "rm", "\\u2715");
    drop.type = "button";
    drop.title = "убрать пункт";
    drop.setAttribute("aria-label", "убрать пункт");
    drop.addEventListener("click", function(){
      var item = state.own[li.getAttribute("data-item")] || merged(li.getAttribute("data-item"));
      if (!window.confirm("Убрать «" + item.title + "» из этого дня?")) return;
      send("DELETE", { id: li.getAttribute("data-item") });
    });

    acts.appendChild(edit);
    acts.appendChild(drop);
    li.appendChild(acts);

    li.addEventListener("dragstart", function(event){
      dragging = li;
      li.classList.add("dragging");
      if (event.dataTransfer) {
        event.dataTransfer.effectAllowed = "move";
        try { event.dataTransfer.setData("text/plain", li.getAttribute("data-item")); }
        catch (e) { /* Safari бывает против — на перенос это не влияет */ }
      }
    });
    li.addEventListener("dragend", function(){
      li.classList.remove("dragging");
      dragging = null;
      Array.prototype.forEach.call(plan.querySelectorAll(".over"), function(x){
        x.classList.remove("over");
      });
    });
  }

  /* ── перетаскивание: приятное поверх надёжного */

  var dragging = null;

  function spotIn(list, y){
    var kids = Array.prototype.filter.call(list.children, function(x){ return x !== dragging; });
    for (var i = 0; i < kids.length; i++) {
      var box = kids[i].getBoundingClientRect();
      if (y < box.top + box.height / 2) return i;
    }
    return kids.length;
  }

  plan.addEventListener("dragover", function(event){
    if (!dragging) return;
    var list = event.target.closest ? event.target.closest("[data-day-items]") : null;
    var head = event.target.closest ? event.target.closest(".day > summary") : null;
    if (!list && !head) return;
    event.preventDefault();
    if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
    var mark = list || head;
    if (!mark.classList.contains("over")) mark.classList.add("over");
  });
  plan.addEventListener("dragleave", function(event){
    var mark = event.target.closest
      ? (event.target.closest("[data-day-items]") || event.target.closest(".day > summary"))
      : null;
    if (mark) mark.classList.remove("over");
  });
  plan.addEventListener("drop", function(event){
    if (!dragging) return;
    var list = event.target.closest ? event.target.closest("[data-day-items]") : null;
    var head = event.target.closest ? event.target.closest(".day > summary") : null;
    if (!list && !head) return;
    event.preventDefault();
    var id = dragging.getAttribute("data-item");
    if (list) {
      send("PATCH", { id: id, to: list.getAttribute("data-day-items"), at: spotIn(list, event.clientY) });
    } else {
      /* Брошено на заголовок дня — значит «в конец этого дня»: внутрь
         закрытого дня прицелиться нечем. С 24 августа это и есть дальний
         перенос: список дат убран, а два столбца держат все шестнадцать
         свёрнутых дней на одном экране. День открывается сразу после броска —
         иначе пункт уезжает в закрытую свёртку, и «доехал ли» приходится
         проверять нажатием. */
      var day = head.closest(".day");
      send("PATCH", { id: id, to: day.getAttribute("data-day") });
      day.open = true;
    }
  });

  /* ── форма пункта */

  var form = null;
  function makeForm(){
    form = document.createElement("form");
    form.className = "itemform";
    form.innerHTML =
      '<p class="what" data-what></p>'
      /* `required` тут нет нарочно. У пункта из плана пустое название значит
         «вернуть как в плане» — это единственный способ снять свою правку, и
         браузерная проверка «поле обязательно» заперла бы её навсегда. Пустое
         название у её собственного пункта отбивает хранилище, и говорит оно
         это словами, а не всплывающей подсказкой поверх поля. */
      + '<div class="f wide"><label data-title-label>что это</label>'
      + '<input name="title" maxlength="120" placeholder="например: кофейня у реки"></div>'
      /* Не «во сколько», а пометка: часов на странице больше нет, и поле,
         спрашивающее время, вернуло бы их её же руками. */
      + '<div class="f"><label>пометка времени</label>'
      + '<input name="time" maxlength="40" placeholder="например: заложить 2 часа"></div>'
      + '<div class="f"><label>подробность</label>'
      + '<input name="note" maxlength="200" placeholder="необязательно"></div>'
      + '<div class="f wide"><label>как искать на карте</label>'
      + '<input name="map" maxlength="120" placeholder="точное название — станет ссылкой"></div>'
      + '<div class="go"><button type="submit" class="save">Сохранить</button>'
      + '<button type="button" class="drop" data-cancel>Отмена</button>'
      + '<span class="says" data-says role="status"></span></div>';
    form.querySelector("[data-cancel]").addEventListener("click", closeForm);
    form.addEventListener("submit", submit);
    return form;
  }

  function field(name){ return form.elements[name]; }

  function openForm(date, li){
    if (!form) makeForm();
    var day = plan.querySelector('[data-day="' + date + '"]');
    if (!day) return;
    day.open = true;
    day.querySelector(".dbody").appendChild(form);
    editing = li ? { id: li.getAttribute("data-item"), date: date } : { id: null, date: date };
    var item = li
      ? (state.own[editing.id] || merged(editing.id))
      : { time: "", title: "", note: "", map: "" };
    /* Пункт из плана можно вернуть как был — и она должна об этом узнать из
       формы, а не догадаться. Свой возвращать не к чему: кроме её текста, у
       него ничего нет. */
    var fromPlan = li && !state.own[editing.id];
    form.querySelector("[data-what]").textContent = li
      ? (fromPlan ? "Правка пункта из плана" : "Правка своего пункта")
      : "Новый пункт в этот день";
    form.querySelector("[data-title-label]").textContent = fromPlan
      ? "что это · пусто — вернуть как в плане"
      : "что это";
    field("title").value = item.title || "";
    field("time").value = item.time || "";
    field("note").value = item.note || "";
    field("map").value = item.map || "";
    form.querySelector("[data-says]").textContent = "";
    field("title").focus();
  }

  function closeForm(){
    editing = null;
    if (form && form.parentNode) form.parentNode.removeChild(form);
  }

  function submit(event){
    event.preventDefault();
    if (!editing) return;
    var body = {
      title: field("title").value,
      time: field("time").value,
      note: field("note").value,
      map: field("map").value
    };
    var save = form.querySelector(".save");
    var line = form.querySelector("[data-says]");
    save.disabled = true;
    line.textContent = "сохраняю…";
    var was = editing;
    var sending = was.id
      ? ask("PATCH", Object.assign({ id: was.id }, body))
      : ask("POST", Object.assign({ date: was.date }, body));
    sending.then(function(said){
      adopt(said);
      closeForm();
      var fresh = plan.querySelector('[data-item="' + (was.id || said.added) + '"]');
      if (fresh) {
        fresh.classList.add("fresh");
        window.setTimeout(function(){ fresh.classList.remove("fresh"); }, 2000);
      }
    }).catch(function(error){
      line.textContent = error.message;
    }).then(function(){ save.disabled = false; });
  }

  /* ── день заводит ручки при первом открытии

     Открыть день можно раньше, чем доедет хранилище (ближайший раскрывается
     сразу), — поэтому заводит ручки не только открытие, но и приезд
     расстановки. Обе дороги ведут сюда, и обе безопасны дважды: `data-wired`
     стоит и на дне, и на строке. */

  function wireDay(day){
    /* Строки перебираются на каждом заходе, а не только на первом: пункт,
       который она сейчас дописала, обязан получить ручки сразу. Дважды это не
       сработает — `data-wired` стоит на самой строке. Так и вскрылось: свежий
       пункт приезжал без кнопок и оживал только перезагрузкой. */
    var date = day.getAttribute("data-day");
    Array.prototype.forEach.call(day.querySelectorAll(".it"), function(li){
      wireItem(li);
    });
    if (day.getAttribute("data-wired") === "yes") return;
    day.setAttribute("data-wired", "yes");
    var add = el("button", "addday", "+ пункт в этот день");
    add.type = "button";
    add.addEventListener("click", function(){ openForm(date, null); });
    day.querySelector(".dbody").appendChild(add);
  }

  Array.prototype.forEach.call(plan.querySelectorAll(".day"), function(day){
    day.addEventListener("toggle", function(){
      if (day.open && state.live) wireDay(day);
      foldSays();
    });
  });

  /* ── одна кнопка на весь раздел

     Свёртка — чистая разметка, поэтому кнопка работает и тогда, когда
     расстановка не доехала: ей нечего спрашивать у хранилища.

     Разворачивая дни, разворачиваем и отрезки городов: день внутри свёрнутого
     города открыт, но не виден, и кнопка выглядела бы сработавшей наполовину.
     Что она сделает следующим нажатием — написано на ней самой, а не
     угадывается по тому, что было раньше. */

  var foldAll = document.querySelector("[data-fold-all]");

  function shutDays(){
    var shut = 0;
    Array.prototype.forEach.call(plan.querySelectorAll("details.day"), function(day){
      if (!day.open) shut++;
    });
    return shut;
  }

  function foldSays(){
    if (!foldAll) return;
    var open = shutDays() === 0;
    foldAll.textContent = open ? "свернуть все дни" : "развернуть все дни";
    foldAll.setAttribute("aria-expanded", open ? "true" : "false");
  }

  if (foldAll) {
    foldAll.addEventListener("click", function(){
      var opening = shutDays() > 0;
      if (opening) {
        Array.prototype.forEach.call(plan.querySelectorAll("details.run"), function(run){
          run.open = true;
        });
      }
      Array.prototype.forEach.call(plan.querySelectorAll("details.day"), function(day){
        day.open = opening;
      });
      foldSays();
    });
  }

  /* ── ближайший день открыт сразу

     «Ближайший» стареет каждые сутки, а страница собирается редко — поэтому
     день выбирает браузер, а не сборка. */
  var today = new Date();
  var iso = today.getFullYear() + "-"
    + String(today.getMonth() + 1).padStart(2, "0") + "-"
    + String(today.getDate()).padStart(2, "0");
  var soon = null;
  DAYS.forEach(function(day){ if (!soon && day.date >= iso) soon = day.date; });
  if (!soon && DAYS.length) soon = DAYS[DAYS.length - 1].date;
  if (soon) {
    var open = plan.querySelector('[data-day="' + soon + '"]');
    if (open) open.open = true;
  }

  counts();
  foldSays();
  ask("GET").then(adopt).catch(function(error){
    state.live = false;
    tell("твои перестановки не загрузились (" + error.message
      + ") — здесь план, как его собрали, и двигать его сейчас нечем");
  });
})();
"""


# ─────────────────────────────────────────── страница

def render(trip: dict, plan: list | None = None) -> str:
    # Курс берётся из тех же данных, что и всё остальное на странице.
    # Раньше его подставлял только `main()` через `load_fx`, а `render`
    # молча пользовался запасным числом в модуле. Пока запасное совпадало с
    # данными, разницы не было видно — и проверки всё это время сверяли
    # страницу с курсом, которого в данных уже не было. 10 сентября они
    # разошлись, и дыра открылась.
    load_fx(trip)
    plan = load_plan() if plan is None else plan
    stays = sorted(trip["stays"], key=lambda s: (s["checkin"]["date"], s["checkout"]["date"]))
    alerts = trip.get("alerts", [])
    all_legs = legs(stays)
    t = trip["trip"]
    nights = (d(t["end"]) - d(t["start"])).days

    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex, nofollow, noarchive">
<meta name="theme-color" content="#e8eef7">
<title>{e(t["title"])} {e(t["year"])} — {e(t["subtitle"])}</title>
<style>{CSS}</style>
</head>
<body style="--nights:{nights}">
<div class="sheet">
  {masthead(trip, stays, all_legs)}
  {thread(trip, all_legs)}
  {flights_block(trip)}
  {alert_block(alerts)}
  {city_cards(all_legs, alerts, trip.get("cancelled", []))}
  {adder(trip, all_legs)}
  {ledger(trip, stays, all_legs)}
  {more_block(trip, stays, alerts, plan, all_legs)}
  {reference()}
  {colophon(trip)}
</div>
{island(trip, stays, all_legs, plan)}
<script>{MONEY_JS}
{JS}
{APP_JS}
{FX_JS}
{DAYS_JS}</script>
</body>
</html>
"""


NOT_FOUND = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow"><title>Не туда</title>
<style>:root{color-scheme:light}
body{margin:0;height:100vh;display:grid;place-items:center;background:#e8eef7;
color:#161b29;font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;text-align:center}
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

    Здесь ровно те же ключи, что у городов в `#japan-data` и в списке городов
    формы: город сливает соседние брони в один отрезок, и место цепляется к
    первой из них. Совпадение этих трёх списков — не совпадение, а условие:
    принятая запись обязана иметь, чем назваться, а её правка — что выбрать.

    Мешков `data-mine` по городам, с которыми список сверялся раньше, больше
    нет: «хочу сходить» ушло из карточек 24 августа, и все места лежат одной
    стопкой в «куплено отдельно». Пропасть из-за незнакомого города запись
    теперь не может — строка назовёт его «город не найден», — но принимать в
    хранилище город, которого в поездке нет, по-прежнему незачем.
    """
    ids = [leg["stays"][0]["id"] for leg in all_legs]
    body = json.dumps(ids, ensure_ascii=False)
    (SITE / "functions" / "api" / "_stays.js").write_text(
        "/* Собирается `build.py` — руками не править.\n"
        "\n"
        "   Города, к которым можно привязать место. Список тот же, что у городов\n"
        "   в `#japan-data` и в списке городов формы: запись, принятая ручкой,\n"
        "   обязана иметь, чем назваться на странице. */\n"
        f"\nexport const STAYS = {body};\n",
        encoding="utf-8",
    )
    return ids


def write_plan(plan: list) -> int:
    """План по дням — для двери: список дней и файловый порядок пунктов.

    Ручке `/api/days` он нужен ровно для двух вещей: знать, что такой день в
    поездке есть (в несуществующий пункт не переносится), и знать файловое
    место пункта, чтобы дописанное в план встало между завтраком и музеем, а
    не в хвост дня.

    Текста здесь нет нарочно — только id. Название, время и ссылки живут в
    собранной странице, и второй их экземпляр рядом с хранилищем означал бы,
    что поправка Блэйза доезжает до неё через раз: там, где выложили обе
    копии, — доезжает, а где одну — нет.

    Собирается сборкой и лежит в git видимым куском, как `_stays.js`: рядом с
    ручкой на Cloudflare нет ни файла с данными, ни питона.
    """
    body = json.dumps(
        [{"date": x["date"], "items": [i["id"] for i in x["items"]]} for x in plan],
        ensure_ascii=False,
    )
    (SITE / "functions" / "api" / "_plan.js").write_text(
        "/* Собирается `build.py` — руками не править.\n"
        "\n"
        "   Дни поездки и файловый порядок пунктов в них. Только id: текст живёт\n"
        "   в собранной странице, а расстановка — в хранилище. */\n"
        f"\nexport const PLAN = {body};\n",
        encoding="utf-8",
    )
    return sum(len(x["items"]) for x in plan)


def main() -> int:
    trip = json.loads(DATA.read_text(encoding="utf-8"))
    plan = load_plan()
    load_fx(trip)

    try:
        said = check(trip, plan) + check_reference()
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

    # План для двери — по той же причине и в том же месте: выложить вчерашний
    # значит отбить перенос в день, который на странице уже есть.
    print(f"· дней в плане: {len(plan)}, пунктов: {write_plan(plan)}")

    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)

    (DIST / "index.html").write_text(render(trip, plan), encoding="utf-8")
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
