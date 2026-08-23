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

    # 6. Никаких секретов в данных. Ключи с подчёркивания — записки самому
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


# ─────────────────────────────────────────── куски страницы

def hero(trip: dict, stays: list, alerts: list) -> str:
    t = trip["trip"]
    start, end = d(t["start"]), d(t["end"])
    days = (end - start).days + 1
    nights = sum(s["nights"] for s in stays)
    needs = sum(1 for a in alerts if a["level"] == "red")

    chips = "".join(
        f'<li class="{"transit" if r.get("transit") else ""}">'
        f'<span class="c">{e(r["city"])}</span>'
        f'<span class="a">{e(r["area"])}</span>'
        f'<span class="w">{short(r["from"])}—{short(r["to"])}</span></li>'
        for r in trip["route"]
    )

    return f"""
<header class="hero">
  <div class="kanji" aria-hidden="true">日本</div>
  <p class="eyebrow">поездка</p>
  <h1>{e(t["title"])}<span class="year">{e(t["year"])}</span></h1>
  <p class="dates">{e(t["subtitle"])}</p>
  <ul class="route">{chips}</ul>
  <ul class="tally">
    <li><b>{days}</b><span>{plural(days, "день", "дня", "дней")}</span></li>
    <li><b>{nights}</b><span>{plural(nights, "ночь", "ночи", "ночей")}</span></li>
    <li><b>{len(stays)}</b><span>{plural(len(stays), "бронь", "брони", "броней")}</span></li>
    {f'<li class="warn"><b>{needs}</b><span>требует решения</span></li>' if needs else ''}
  </ul>
</header>"""


def alert_block(alerts: list) -> str:
    """Блок про ночь, на которой сошлись две брони.

    Тон задаёт `level`. «red» — это вопрос, на который она ещё не ответила:
    сирена, варианты со сроками. «calm» — она уже ответила, и тогда всё это
    превращается в подгоняние по решённому вопросу. Что не меняется от тона:
    блок есть, ночь названа, обе брони живы. Убрать его можно только вместе с
    наложением в данных — иначе сборка не пройдёт (см. check).
    """
    if not alerts:
        return ""
    out = []
    for a in alerts:
        red = a["level"] == "red"
        facts = "".join(f"<li>{e(x)}</li>" for x in a.get("facts", []))
        options = "".join(
            f"""<li class="opt">
                  <h4>{e(o["title"])}</h4>
                  <p>{e(o["detail"])}</p>
                  <p class="watch" data-deadline="{e(o.get("deadline", ""))}">{e(o["watch"])}</p>
                </li>"""
            for o in a.get("options", [])
        )
        out.append(f"""
<section class="alert {e(a["level"])}" id="{e(a["id"])}">
  <p class="siren">{"нужно решение" if red else "как задумано"}</p>
  <h2>{e(a["title"])}</h2>
  <p class="lead">{e(a["lead"])}</p>
  <ul class="facts">{facts}</ul>
  {f'<ol class="options">{options}</ol>' if options else ''}
  <p class="closing">{e(a["closing"])}</p>
</section>""")
    return "".join(out)


def timeline(trip: dict, stays: list, alerts: list) -> str:
    flagged = {a["id"]: a["level"] for a in alerts}

    # Ночь в дороге стоит в ленте наравне с ночёвками: если её не показать,
    # лента начнётся с 5-го и будет тихо противоречить датам в шапке.
    legs = [("transit", t["date"], t) for t in trip.get("transit", [])]
    legs += [("stay", s["checkin"]["date"], s) for s in stays]
    legs.sort(key=lambda x: x[1])

    rows = []
    for kind, _when, item in legs:
        if kind == "transit":
            rows.append(f"""
<li class="transit">
  <div class="when">
    <b>{short(item["date"])}</b>
    <span>{weekday(item["date"])}</span>
  </div>
  <div class="what">
    <p class="place">{e(item["title"])}</p>
    <p class="len">{e(item["detail"])}</p>
  </div>
</li>""")
            continue

        s = item
        tone = flagged.get(s.get("conflict"))
        rows.append(f"""
<li class="{'clash' if tone == 'red' else 'noted' if tone else ''}">
  <div class="when">
    <b>{short(s["checkin"]["date"])}</b>
    <span>{weekday(s["checkin"]["date"])}</span>
  </div>
  <div class="what">
    <p class="place">{e(s["city"])} <span>· {e(s["area"])}</span></p>
    <p class="who"><a href="#{e(s["id"])}">{e(s.get("label") or s["name"])}</a></p>
    <p class="len">{s["nights"]} {plural(s["nights"], "ночь", "ночи", "ночей")}
       · до {short(s["checkout"]["date"])}</p>
    {f'<p class="clash-note"><a href="#{s["conflict"]}">пересекается с соседней бронью</a></p>' if tone else ''}
  </div>
</li>""")
    return f"""
<section id="timeline">
  <h2 class="sec">Как идёт поездка</h2>
  <ol class="timeline">{"".join(rows)}</ol>
</section>"""


def stay_cards(stays: list, alerts: list, cancelled: list) -> str:
    flagged = {a["id"]: a["level"] for a in alerts}
    cards = []
    for s in stays:
        pay = s["payment"]
        if pay["mode"] == "prepaid":
            money = (
                f'<span class="paid">списано {yen(pay["paid_jpy"])}</span>'
                f'<span class="due">спишется {yen(pay["upcoming_jpy"])}</span>'
            )
        else:
            money = '<span class="onsite">оплата на месте</span>'

        extras = "".join(f"<li>{e(x)}</li>" for x in s.get("extras", []))
        notes = "".join(f"<li>{e(x)}</li>" for x in s.get("notes", []))

        cards.append(f"""
<article class="stay {'clash' if flagged.get(s.get('conflict')) == 'red' else 'noted' if s.get('conflict') in flagged else ''}" id="{e(s["id"])}">
  <div class="head">
    <p class="city">{e(s["city"])} <span>· {e(s["area"])}</span></p>
    <h3>{e(s["name"])}</h3>
    {f'<p class="label">{e(s["label"])}</p>' if s.get("label") else ''}
  </div>

  <div class="stayline">
    <div><span class="k">заезд</span><b>{day_month(s["checkin"]["date"])}</b>
         <span class="t">{weekday(s["checkin"]["date"])}, {e(s["checkin"]["time"])}</span></div>
    <div class="arrow" aria-hidden="true">→</div>
    <div><span class="k">выезд</span><b>{day_month(s["checkout"]["date"])}</b>
         <span class="t">{weekday(s["checkout"]["date"])}, {e(s["checkout"]["time"])}</span></div>
  </div>

  {f'''<p class="arriving"><span class="k">приезжаешь</span>
       <b>{day_month(s["arriving"]["date"])}</b>
       <span class="t">{e(s["arriving"]["why"])} · ночь {short(s["checkin"]["date"])} оплачена и остаётся пустой</span></p>''' if s.get("arriving") else ''}

  <dl class="facts">
    <div><dt>номер</dt><dd>{e(s["room"])}</dd></div>
    <div><dt>гостей</dt><dd>{e(s["guests"])}</dd></div>
    <div><dt>еда</dt><dd>{e(s["meals"])}</dd></div>
    <div><dt>стоимость</dt><dd class="money">{yen(s["total_jpy"])} <span class="split">{money}</span></dd></div>
  </dl>

  <p class="cancel" data-deadline="{e(s["cancel"]["free_until"])}">
    <span class="k">бесплатная отмена</span>
    <b>до {day_month(s["cancel"]["free_until"])} {d(s["cancel"]["free_until"]).year}, {e(s["cancel"]["free_until"][11:16])} JST</b>
    <span class="t">{e(s["cancel"]["note"])}</span>
  </p>

  {f'<ul class="extras">{extras}</ul>' if extras else ''}
  {f'<ul class="hotelnotes">{notes}</ul>' if notes else ''}

  <div class="links">
    <a class="btn" href="{e(maplink(s["address"]))}" target="_blank" rel="noreferrer noopener">На карте</a>
    <a class="btn" href="{e(tellink(s["phone"]))}">{e(s["phone"])}</a>
  </div>
  <p class="addr">{e(s["address"])}</p>
</article>""")

    gone = ""
    if cancelled:
        items = "".join(
            f'<li><b>{e(c["name"])}</b> — {yen(c["total_jpy"])}<span>{e(c["note"])}</span></li>'
            for c in cancelled
        )
        gone = f'<div class="cancelled"><p class="sec-note">Отменённое</p><ul>{items}</ul></div>'

    return f"""
<section id="stays">
  <h2 class="sec">Где живём</h2>
  {"".join(cards)}
  {gone}
</section>"""


def checklist(trip: dict) -> str:
    groups = []
    for g in trip["todo"]:
        items = "".join(
            f"""<li>
              <label>
                <input type="checkbox" data-todo="{e(g["group"])}::{e(i["text"])}" {'checked' if i.get('done') else ''}>
                <span class="tick" aria-hidden="true"></span>
                <span class="txt">{e(i["text"])}
                  {f'<em>{e(i["note"])}</em>' if i.get("note") else ''}
                </span>
              </label>
            </li>"""
            for i in g["items"]
        )
        groups.append(f'<div class="todo-group"><h3>{e(g["group"])}</h3><ul>{items}</ul></div>')
    return f"""
<section id="todo">
  <h2 class="sec">Решить и забронировать</h2>
  <p class="sec-note">Галочки живут в этом телефоне. Что решено окончательно —
     переносим в <code>trip.json</code>, чтобы не потерялось.</p>
  {"".join(groups)}
  <button class="reset" type="button" data-reset>Снять галочки на этом устройстве</button>
</section>"""


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
<section id="days">
  <h2 class="sec">По дням</h2>
  <p class="sec-note">Города подставляются из броней. Планы на день —
     раздел <code>days</code> в <code>trip.json</code>.</p>
  <ol class="days">{"".join(rows)}</ol>
</section>"""


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
    return f"""
<section id="luggage">
  <h2 class="sec">Багаж</h2>
  <p class="lead">{e(lug["lead"])}</p>
  <ol class="moves">{moves}</ol>
  <ul class="always">{always}</ul>
</section>"""


def budget(stays: list, notes: list) -> str:
    total = sum(s["total_jpy"] for s in stays)
    # Ночей в поездке, а не сумма ночей по бронам: на 14-е их две, и написать
    # здесь 15 значило бы посчитать наложение как ещё один день отдыха.
    slept = len({
        d(s["checkin"]["date"]) + timedelta(days=i)
        for s in stays
        for i in range(s["nights"])
    })
    paid = sum(s["payment"].get("paid_jpy", 0) for s in stays)
    upcoming = sum(s["payment"].get("upcoming_jpy", 0) for s in stays)
    onsite = sum(s["total_jpy"] for s in stays if s["payment"]["mode"] == "at_property")

    def bar(part: int) -> str:
        return f"{part / total * 100:.1f}%"

    lines = "".join(
        f'<li><span>{e(s.get("label") or s["name"])}</span><b>{yen(s["total_jpy"])}</b></li>'
        for s in stays
    )
    extra = "".join(f"<li>{e(x)}</li>" for x in notes)

    return f"""
<section id="budget">
  <h2 class="sec">Деньги</h2>
  <p class="grand">{yen(total)}<span>за жильё, {slept} {plural(slept, "ночь", "ночи", "ночей")}</span></p>
  <div class="bar" role="img" aria-label="как разделена оплата">
    <span class="seg paid" style="width:{bar(paid)}"></span>
    <span class="seg due" style="width:{bar(upcoming)}"></span>
    <span class="seg onsite" style="width:{bar(onsite)}"></span>
  </div>
  <ul class="legend">
    <li class="paid"><b>{yen(paid)}</b><span>уже списано</span></li>
    <li class="due"><b>{yen(upcoming)}</b><span>спишется автоматически</span></li>
    <li class="onsite"><b>{yen(onsite)}</b><span>на месте, при заезде</span></li>
  </ul>
  <ul class="breakdown">{lines}</ul>
  <p class="sec-note">Сверх этого — считается на месте:</p>
  <ul class="caveats">{extra}</ul>
</section>"""


def notes_block(trip: dict) -> str:
    return f"""
<section id="notes">
  <h2 class="sec">Заметки</h2>
  <ul class="notes">{"".join(f"<li>{e(x)}</li>" for x in trip["notes"])}</ul>
  <p class="colophon">Обновлено {day_month(trip["trip"]["updated"])} {d(trip["trip"]["updated"]).year}.
     Страница собирается из одного файла с данными — попроси Блэйза внести правку,
     и она появится здесь.</p>
</section>"""


# ─────────────────────────────────────────── стиль

CSS = """
:root{
  --paper:#f7f3ec; --card:#fffdf9; --ink:#1e2329; --quiet:#5d6570;
  --rule:rgba(30,35,41,.12); --deep:#2f4a5c; --deep-soft:#eaf0f3;
  --fire:#b23a29; --fire-soft:#fbeeec; --moss:#4e6b4a;
  --gold:#a8834b;
  --serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,"Times New Roman",serif;
  --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
  --wide:640px;
}
@media (prefers-color-scheme:dark){
  :root{
    --paper:#14181c; --card:#1b2026; --ink:#e8e4dc; --quiet:#9aa3ad;
    --rule:rgba(232,228,220,.14); --deep:#8fb6cc; --deep-soft:#1e2a33;
    --fire:#e8836f; --fire-soft:#2b1c19; --moss:#8fb488; --gold:#c9a874;
  }
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{
  margin:0; background:var(--paper); color:var(--ink);
  font-family:var(--sans); font-size:16px; line-height:1.55;
  -webkit-font-smoothing:antialiased;
  padding-bottom:64px;
}
.wrap{max-width:var(--wide); margin:0 auto; padding:0 18px}
a{color:inherit}
h1,h2,h3,h4{font-family:var(--serif); font-weight:600; letter-spacing:-.01em; margin:0}
code{font-size:.88em; background:var(--deep-soft); padding:1px 5px; border-radius:4px}

/* ── шапка */
.hero{position:relative; padding:44px 0 26px; overflow:hidden}
.hero .kanji{
  position:absolute; right:-14px; top:8px; font-family:var(--serif);
  font-size:132px; line-height:1; color:var(--ink); opacity:.055;
  pointer-events:none; user-select:none;
}
.eyebrow{margin:0; font-size:11px; letter-spacing:.24em; text-transform:uppercase; color:var(--quiet)}
.hero h1{font-size:46px; line-height:1.02; margin:6px 0 0}
.hero h1 .year{display:block; font-size:22px; color:var(--gold); letter-spacing:.14em; margin-top:4px}
.hero .dates{margin:14px 0 0; font-size:19px; font-family:var(--serif); color:var(--quiet)}
.route{list-style:none; margin:20px 0 0; padding:0; display:flex; flex-wrap:wrap; gap:7px}
.route li{
  background:var(--card); border:1px solid var(--rule); border-radius:10px;
  padding:7px 11px; line-height:1.25;
}
.route .c{font-weight:600; font-size:14px}
.route .a{font-size:14px; color:var(--quiet)}
.route .a::before{content:"·"; margin:0 5px; opacity:.45}
.route .w{display:block; font-size:11px; color:var(--quiet); letter-spacing:.05em; margin-top:2px}
.tally{list-style:none; display:flex; gap:22px; margin:22px 0 0; padding:0; flex-wrap:wrap}
.tally b{display:block; font-family:var(--serif); font-size:27px; line-height:1}
.tally span{font-size:11px; letter-spacing:.1em; text-transform:uppercase; color:var(--quiet)}
.tally .warn b{color:var(--fire)}

/* ── навигация */
nav.jump{
  position:sticky; top:0; z-index:9; background:var(--paper);
  border-bottom:1px solid var(--rule); margin-bottom:8px;
}
nav.jump ul{
  list-style:none; display:flex; gap:4px; margin:0; padding:5px 18px;
  overflow-x:auto; -webkit-overflow-scrolling:touch; scrollbar-width:none;
  max-width:var(--wide); margin:0 auto;
}
nav.jump ul::-webkit-scrollbar{display:none}
nav.jump a{
  display:flex; align-items:center; min-height:40px; white-space:nowrap;
  font-size:13px; padding:0 13px; border-radius:999px;
  text-decoration:none; color:var(--quiet);
}
nav.jump a.hot{color:var(--fire); background:var(--fire-soft); font-weight:600}

/* ── тревога */
.alert{
  background:var(--fire-soft); border:1.5px solid var(--fire); border-radius:14px;
  padding:20px 17px; margin:22px 0 34px;
}
/* «calm» — вопрос, на который Ни уже ответила. Форма та же, голос другой:
   песок вместо киновари, точка вместо восклицания. Блок остаётся, потому что
   ночь с двумя бронями надо видеть; сирена уходит, потому что решение принято. */
.alert.calm{ background:var(--deep-soft); border-color:var(--gold); border-width:1px }
.alert.calm .siren{ color:var(--gold) }
.alert.calm .siren::before{ content:"◆"; font-size:8px; vertical-align:2px }
.alert.calm h2{ color:var(--ink) }
.alert.calm .facts li::before{ color:var(--gold) }
.alert .siren{
  margin:0 0 9px; font-size:11px; letter-spacing:.2em; text-transform:uppercase;
  color:var(--fire); font-weight:700;
}
.alert .siren::before{content:"●"; margin-right:7px; font-size:9px; vertical-align:2px}
.alert h2{font-size:25px; line-height:1.16; color:var(--fire)}
.alert .lead{margin:11px 0 0; font-size:15.5px}
.alert .facts{list-style:none; margin:15px 0 0; padding:0; font-size:14.5px}
.alert .facts li{padding:5px 0 5px 17px; position:relative; color:var(--quiet)}
.alert .facts li::before{content:"—"; position:absolute; left:0; color:var(--fire)}
.alert .options{list-style:none; counter-reset:o; margin:17px 0 0; padding:0; display:grid; gap:11px}
.alert .opt{
  background:var(--card); border-radius:11px; padding:14px 15px 13px;
  counter-increment:o; position:relative;
}
.alert .opt h4{font-size:16.5px; padding-left:26px}
.alert .opt h4::before{
  content:counter(o); position:absolute; left:15px; width:19px; height:19px;
  border-radius:50%; background:var(--fire); color:#fff; font-family:var(--sans);
  font-size:11px; font-weight:700; display:grid; place-items:center; margin-top:2px;
}
.alert .opt p{margin:7px 0 0; font-size:14.5px}
.alert .watch{color:var(--fire); font-weight:600}
.alert .watch .left{display:block; font-weight:400; color:var(--quiet); font-size:13px; margin-top:3px}
.alert .closing{
  margin:16px 0 0; font-size:14.5px; font-family:var(--serif); font-style:italic;
  border-top:1px solid var(--rule); padding-top:13px;
}

/* ── секции */
section{margin:0 0 40px; scroll-margin-top:56px}
h2.sec{
  font-size:13px; letter-spacing:.18em; text-transform:uppercase; color:var(--quiet);
  font-family:var(--sans); font-weight:700; margin-bottom:14px;
  padding-bottom:8px; border-bottom:1px solid var(--rule);
}
.sec-note{font-size:13px; color:var(--quiet); margin:-6px 0 14px}
.lead{font-size:15.5px; margin:0 0 15px}

/* ── лента */
.timeline{list-style:none; margin:0; padding:0; position:relative}
.timeline::before{
  content:""; position:absolute; left:33px; top:12px; bottom:12px;
  width:1px; background:var(--rule);
}
.timeline li{display:flex; gap:16px; padding:0 0 18px; position:relative}
.timeline .when{width:52px; flex:none; text-align:center; position:relative; z-index:1}
.timeline .when b{
  display:grid; place-items:center; width:44px; height:44px; margin:0 auto;
  border-radius:50%; background:var(--card); border:1px solid var(--rule);
  font-family:var(--serif); font-size:14px;
}
.timeline .when span{display:block; font-size:10.5px; color:var(--quiet); margin-top:4px; letter-spacing:.08em}
.timeline .what{padding-top:3px}
.timeline .place{margin:0; font-size:16px; font-weight:600}
.timeline .place span{color:var(--quiet); font-weight:400}
.timeline .who{margin:2px 0 0; font-size:14.5px}
.timeline .who a{color:var(--deep); text-decoration-color:var(--rule); text-underline-offset:3px}
.timeline .len{margin:2px 0 0; font-size:12.5px; color:var(--quiet)}
.timeline .clash .when b{border-color:var(--fire); color:var(--fire); border-width:1.5px}
.timeline .noted .when b{border-color:var(--gold); color:var(--gold)}
.timeline .transit .when b{background:transparent; border-style:dashed; color:var(--quiet)}
.timeline .transit .place{font-size:15px; color:var(--quiet); font-weight:500}
.route .transit{border-style:dashed; opacity:.8}
.clash-note{
  margin:6px 0 0; font-size:12px; color:var(--fire); font-weight:600;
  background:var(--fire-soft); display:inline-block; padding:3px 8px; border-radius:6px;
}
.clash-note a{ text-decoration:none; color:inherit }
.noted .clash-note{ color:var(--gold); background:var(--deep-soft) }

/* ── карточки жилья */
.stay{
  background:var(--card); border:1px solid var(--rule); border-radius:14px;
  padding:18px 16px; margin:0 0 14px;
}
.stay.clash{border-color:var(--fire); border-width:1.5px}
.stay.noted{border-color:var(--gold)}
.arriving{
  margin:13px 0 0; padding:11px 13px; border-radius:10px; background:var(--deep-soft);
  border-left:3px solid var(--gold);
}
.arriving .k{display:block; font-size:10.5px; letter-spacing:.12em; text-transform:uppercase; color:var(--quiet)}
.arriving b{display:block; font-family:var(--serif); font-size:17px; margin-top:2px}
.arriving .t{display:block; font-size:12.5px; color:var(--quiet); margin-top:2px}
.stay .city{margin:0; font-size:11.5px; letter-spacing:.14em; text-transform:uppercase; color:var(--quiet)}
.stay .city span{color:var(--gold)}
.stay h3{font-size:21px; line-height:1.2; margin-top:5px}
.stay .label{margin:4px 0 0; font-size:13px; color:var(--quiet); font-style:italic}
.stayline{
  display:flex; align-items:flex-start; gap:10px; margin:15px 0 0;
  padding:13px 0; border-top:1px solid var(--rule); border-bottom:1px solid var(--rule);
}
.stayline > div{flex:1}
.stayline .arrow{flex:none; color:var(--quiet); align-self:center; font-size:15px}
.stayline .k{display:block; font-size:10.5px; letter-spacing:.12em; text-transform:uppercase; color:var(--quiet)}
.stayline b{display:block; font-family:var(--serif); font-size:18px; margin-top:2px}
.stayline .t{display:block; font-size:12.5px; color:var(--quiet)}
.stay dl.facts{margin:13px 0 0; display:grid; gap:8px}
.stay dl.facts > div{display:flex; gap:12px; align-items:baseline}
.stay dt{
  flex:none; width:82px; font-size:11px; letter-spacing:.1em; text-transform:uppercase;
  color:var(--quiet);
}
.stay dd{margin:0; font-size:14.5px}
.stay .money{font-family:var(--serif); font-size:18px}
.stay .split{display:block; font-family:var(--sans); font-size:12.5px; margin-top:2px}
.stay .split span{display:inline-block; margin-right:9px}
.stay .paid{color:var(--moss)}
.stay .due{color:var(--fire)}
.stay .onsite{color:var(--quiet)}
.cancel{
  margin:14px 0 0; padding:11px 13px; border-radius:10px; background:var(--deep-soft);
}
.cancel .k{display:block; font-size:10.5px; letter-spacing:.12em; text-transform:uppercase; color:var(--quiet)}
.cancel b{display:block; font-size:14.5px; margin-top:2px}
.cancel .t{display:block; font-size:12.5px; color:var(--quiet); margin-top:2px}
.cancel .left{display:block; font-size:12.5px; margin-top:4px; font-weight:600; color:var(--deep)}
.cancel.soon{background:var(--fire-soft)}
.cancel.soon .left{color:var(--fire)}
.extras,.hotelnotes{list-style:none; margin:12px 0 0; padding:0; font-size:13px; color:var(--quiet)}
.extras li,.hotelnotes li{padding:3px 0 3px 16px; position:relative}
.extras li::before,.hotelnotes li::before{content:"·"; position:absolute; left:5px; font-weight:700}
.hotelnotes{border-top:1px dashed var(--rule); padding-top:9px; margin-top:12px}
.links{display:flex; gap:9px; margin:15px 0 0}
.btn{
  flex:1; text-align:center; text-decoration:none; font-size:14px; padding:10px 8px;
  border-radius:9px; border:1px solid var(--rule); background:var(--paper); color:var(--deep);
  font-weight:600; white-space:nowrap;
}
.btn:active{background:var(--deep-soft)}
.addr{margin:9px 0 0; font-size:12px; color:var(--quiet); text-align:center}
.cancelled{margin-top:20px; opacity:.72}
.cancelled ul{list-style:none; margin:0; padding:0}
.cancelled li{font-size:13.5px; text-decoration:line-through; color:var(--quiet)}
.cancelled li span{display:block; font-size:12px; text-decoration:none; margin-top:2px}

/* ── чеклист */
.todo-group{margin:0 0 20px}
.todo-group h3{font-size:15px; margin-bottom:7px; color:var(--deep)}
.todo-group ul{list-style:none; margin:0; padding:0}
.todo-group li{border-bottom:1px solid var(--rule)}
.todo-group label{display:flex; gap:11px; align-items:flex-start; padding:11px 2px; cursor:pointer}
.todo-group input{position:absolute; opacity:0; width:0; height:0}
.tick{
  flex:none; width:20px; height:20px; margin-top:1px; border-radius:6px;
  border:1.5px solid var(--rule); background:var(--card); position:relative;
}
input:checked + .tick{background:var(--moss); border-color:var(--moss)}
input:checked + .tick::after{
  content:""; position:absolute; left:6px; top:2px; width:5px; height:10px;
  border:solid #fff; border-width:0 2px 2px 0; transform:rotate(42deg);
}
input:focus-visible + .tick{outline:2px solid var(--deep); outline-offset:2px}
.txt{font-size:15px}
input:checked ~ .txt{color:var(--quiet); text-decoration:line-through}
.txt em{display:block; font-size:12.5px; color:var(--quiet); font-style:normal; text-decoration:none}
.reset{
  margin-top:6px; background:none; border:1px solid var(--rule); border-radius:9px;
  padding:9px 14px; font-size:13px; color:var(--quiet); font-family:inherit; cursor:pointer;
}

/* ── по дням */
.days{list-style:none; margin:0; padding:0}
.days li{display:flex; gap:14px; padding:11px 0; border-bottom:1px solid var(--rule)}
.days .date{width:38px; flex:none; text-align:center}
.days .date b{display:block; font-family:var(--serif); font-size:21px; line-height:1}
.days .date span{font-size:10.5px; color:var(--quiet); letter-spacing:.06em}
.days .body{flex:1; min-width:0}
.days .base{margin:0; font-size:14.5px; font-weight:600}
.days .title{margin:1px 0 0; font-size:13px; color:var(--gold); font-weight:600}
.days ul{list-style:none; margin:5px 0 0; padding:0}
.days ul li{display:block; border:0; padding:1px 0 1px 14px; font-size:13px; color:var(--quiet); position:relative}
.days ul li::before{content:"·"; position:absolute; left:4px; font-weight:700}
.days .empty{margin:3px 0 0; font-size:12.5px; color:var(--quiet); opacity:.6}
.days .move .date b{color:var(--deep)}
.days .move{background:linear-gradient(90deg,var(--deep-soft),transparent 62%)}
.days .clash .date b{color:var(--fire)}
.days .clash{background:linear-gradient(90deg,var(--fire-soft),transparent 62%)}
.days .noted .date b{color:var(--gold)}

/* ── багаж */
.moves{list-style:none; margin:0 0 16px; padding:0; display:grid; gap:11px}
.moves li{background:var(--card); border:1px solid var(--rule); border-radius:12px; padding:13px 15px}
.moves .when{margin:0; font-size:11px; letter-spacing:.12em; text-transform:uppercase; color:var(--gold)}
.moves .path{margin:6px 0 0; font-size:15.5px; font-family:var(--serif); display:flex; gap:8px; flex-wrap:wrap; align-items:baseline}
.moves .path i{color:var(--deep); font-style:normal}
.moves .how{margin:5px 0 0; font-size:13.5px; color:var(--deep); font-weight:600}
.moves .note{margin:2px 0 0; font-size:12.5px; color:var(--quiet)}
.always{list-style:none; margin:0; padding:0; font-size:13.5px; color:var(--quiet)}
.always li{padding:4px 0 4px 18px; position:relative}
.always li::before{content:"✓"; position:absolute; left:0; color:var(--moss); font-size:12px}

/* ── деньги */
.grand{margin:0; font-family:var(--serif); font-size:38px; line-height:1}
.grand span{display:block; font-family:var(--sans); font-size:12px; letter-spacing:.1em;
  text-transform:uppercase; color:var(--quiet); margin-top:5px}
.bar{display:flex; height:9px; border-radius:99px; overflow:hidden; margin:16px 0 13px; background:var(--rule)}
.seg.paid{background:var(--moss)}
.seg.due{background:var(--fire)}
.seg.onsite{background:var(--deep)}
.legend{list-style:none; margin:0 0 18px; padding:0; display:grid; gap:9px}
.legend li{display:flex; align-items:baseline; gap:10px; padding-left:16px; position:relative; font-size:13.5px}
.legend li::before{content:""; position:absolute; left:0; top:6px; width:9px; height:9px; border-radius:3px}
.legend .paid::before{background:var(--moss)}
.legend .due::before{background:var(--fire)}
.legend .onsite::before{background:var(--deep)}
.legend b{font-family:var(--serif); font-size:16px}
.legend span{color:var(--quiet)}
.breakdown{list-style:none; margin:0; padding:0; border-top:1px solid var(--rule)}
.breakdown li{display:flex; justify-content:space-between; gap:14px; padding:8px 0;
  border-bottom:1px solid var(--rule); font-size:14px}
.breakdown b{font-family:var(--serif); font-size:15px; white-space:nowrap}
.caveats{list-style:none; margin:0; padding:0; font-size:13px; color:var(--quiet)}
.caveats li{padding:3px 0 3px 16px; position:relative}
.caveats li::before{content:"+"; position:absolute; left:2px; color:var(--gold)}

/* ── заметки */
.notes{list-style:none; margin:0; padding:0; font-size:14px; color:var(--quiet)}
.notes li{padding:6px 0 6px 18px; position:relative; border-bottom:1px solid var(--rule)}
.notes li::before{content:"※"; position:absolute; left:0; font-size:11px; color:var(--gold)}
.colophon{margin:18px 0 0; font-size:12.5px; color:var(--quiet); font-style:italic; line-height:1.6}

@media (min-width:560px){
  .hero h1{font-size:60px}
  .hero .kanji{font-size:170px}
  .stay dl.facts{grid-template-columns:1fr 1fr}
  .stay dl.facts > div{flex-direction:column; gap:1px}
  .stay dt{width:auto}
}
@media (prefers-reduced-motion:no-preference){
  html{scroll-behavior:smooth}
}
"""

JS = """
(function(){
  "use strict";
  var KEY = "japan2027.todo.v1";

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
  function leftText(iso){
    /* Срок объявлен по японскому времени; сравниваем в UTC, добавив +09:00. */
    var when = new Date(iso + ":00+09:00");
    if (isNaN(when)) return null;
    var days = Math.ceil((when - Date.now()) / DAY);
    if (days < 0) return { text: "срок прошёл", soon: true };
    if (days === 0) return { text: "сегодня последний день", soon: true };
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
  });

  /* Галочки. Источник правды — trip.json; здесь только то, что Ни отметила
     на этом телефоне, поверх него. Поэтому хранится разница, а не состояние:
     когда решение переедет в файл, галочка не начнёт спорить сама с собой. */
  var boxes = Array.prototype.slice.call(document.querySelectorAll("[data-todo]"));
  var flipped = {};
  try { flipped = JSON.parse(localStorage.getItem(KEY) || "{}") || {}; } catch (err) { flipped = {}; }

  boxes.forEach(function(box){
    var id = box.getAttribute("data-todo");
    if (Object.prototype.hasOwnProperty.call(flipped, id)) box.checked = !!flipped[id];
    var built = box.defaultChecked;
    box.addEventListener("change", function(){
      if (box.checked === built) delete flipped[id];
      else flipped[id] = box.checked;
      try { localStorage.setItem(KEY, JSON.stringify(flipped)); } catch (err) {}
    });
  });

  var reset = document.querySelector("[data-reset]");
  if (reset) reset.addEventListener("click", function(){
    flipped = {};
    try { localStorage.removeItem(KEY); } catch (err) {}
    boxes.forEach(function(box){ box.checked = box.defaultChecked; });
  });
})();
"""


# ─────────────────────────────────────────── страница

def render(trip: dict) -> str:
    stays = sorted(trip["stays"], key=lambda s: (s["checkin"]["date"], s["checkout"]["date"]))
    alerts = trip.get("alerts", [])
    t = trip["trip"]

    nav_items = [("timeline", "Маршрут"), ("stays", "Жильё"), ("todo", "Решить"),
                 ("days", "По дням"), ("luggage", "Багаж"), ("budget", "Деньги")]
    nav = "".join(f'<li><a href="#{i}">{e(n)}</a></li>' for i, n in nav_items)
    if alerts:
        first = alerts[0]
        hot = first["level"] == "red"
        label = "Нужно решение" if hot else e(first["title"])
        nav = (
            f'<li><a class="{"hot" if hot else ""}" href="#{e(first["id"])}">{label}</a></li>'
            + nav
        )

    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex, nofollow, noarchive">
<meta name="theme-color" content="#f7f3ec" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#14181c" media="(prefers-color-scheme: dark)">
<title>{e(t["title"])} {e(t["year"])} — {e(t["subtitle"])}</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">{hero(trip, stays, alerts)}</div>
<nav class="jump"><ul>{nav}</ul></nav>
<main class="wrap">
  {alert_block(alerts)}
  {timeline(trip, stays, alerts)}
  {stay_cards(stays, alerts, trip.get("cancelled", []))}
  {checklist(trip)}
  {by_day(trip, stays, alerts)}
  {luggage(trip)}
  {budget(stays, trip["notes"])}
  {notes_block(trip)}
</main>
<script>{JS}</script>
</body>
</html>
"""


NOT_FOUND = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow"><title>Не туда</title>
<style>body{margin:0;height:100vh;display:grid;place-items:center;background:#f7f3ec;
color:#1e2329;font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;text-align:center}
a{color:#2f4a5c}@media(prefers-color-scheme:dark){body{background:#14181c;color:#e8e4dc}a{color:#8fb6cc}}
</style></head><body><div><p style="font-size:44px;margin:0;font-family:Georgia,serif">迷</p>
<p>Такой страницы здесь нет.</p><p><a href="/">На главную</a></p></div></body></html>
"""


def main() -> int:
    trip = json.loads(DATA.read_text(encoding="utf-8"))

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

    size = sum(f.stat().st_size for f in DIST.rglob("*") if f.is_file())
    pages = len(list(DIST.rglob("*.html")))
    print(f"✓ собрано в dist/ — {pages} страницы, {size / 1024:.0f} КБ, "
          f"дверь на месте ({len(list((DIST / 'functions').rglob('*.js')))} файла)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
