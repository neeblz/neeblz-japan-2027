#!/usr/bin/env python3
"""Проверки данных проверяются здесь.

    python3 test/test_data.py

Половина этого файла — нарочно испорченные копии `trip.json`. Причина ровно
одна: проверка, которая ни разу не падала, и отсутствие проверки выглядят
снаружи одинаково. Поэтому на каждое правило есть поломка, которую оно обязано
поймать.
"""

from __future__ import annotations

import copy
import json
import re
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from build import (  # noqa: E402
    DATA, REF_DATA, SITE, Failed, check, check_reference, load_plan, ref_item,
    reference, render, write_plan,
)

REAL = json.loads(DATA.read_text(encoding="utf-8"))
REF = json.loads(REF_DATA.read_text(encoding="utf-8"))


def broken(**_unused):
    return copy.deepcopy(REAL)


class DataHolds(unittest.TestCase):
    """Настоящие данные проходят и говорят то, что мы про них думаем."""

    def test_real_data_passes(self):
        said = "\n".join(check(copy.deepcopy(REAL)))
        self.assertIn("суммы сходятся", said)
        self.assertIn("2027-01-14", said, "наложение 14-го обязано быть названо")

    def test_totals_are_the_expected_numbers(self):
        stays = REAL["stays"]
        # 290 675, а не 297 912: 23 августа Ни прислала новое подтверждение
        # по lyf Ginza — тариф ASR Advanced Purchase, ¥50 205 вместо ¥57 442
        # (номер 41 492 + налог 4 564 + сбор 4 149). Число живёт здесь, чтобы
        # тихая правка её денег краснела.
        self.assertEqual(sum(s["total_jpy"] for s in stays), 290_675)
        self.assertEqual(sum(s["payment"]["paid_jpy"] for s in stays), 12_010)
        self.assertEqual(sum(s["payment"]["upcoming_jpy"] for s in stays), 109_790)
        # Оплаченных ночей 15, прожитых 14: ночь 14-го оплачена дважды.
        # Разница между этими числами и есть цена наложения.
        self.assertEqual(sum(s["nights"] for s in stays), 15)
        self.assertEqual(
            len({
                date.fromisoformat(s["checkin"]["date"]) + timedelta(days=i)
                for s in stays
                for i in range(s["nights"])
            }),
            14,
        )

    def test_cancelled_bookings_never_reach_the_money(self):
        """Отменённое не идёт в суммы — ни одной иеной.

        Раздел `cancelled` пуст с 23 августа: её слово «удали» про отменённую
        бронь Моридзуи 13 → 14. Раздел оставлен на месте, чтобы следующая
        отмена не потребовала правки кода, — а проверка сторожит то же, что и
        раньше: что попавшее туда не смешивается с живыми бронями.
        """
        ids = {s["id"] for s in REAL["stays"]}
        self.assertNotIn("morizuya-cheap", ids)
        live = [s["total_jpy"] for s in REAL["stays"]]
        for gone in REAL["cancelled"]:
            self.assertNotIn(gone["total_jpy"], live,
                             "отменённая бронь не должна попасть в живые")
        if not REAL["cancelled"]:
            self.assertNotIn("class=\"cancelled\"", render(copy.deepcopy(REAL)),
                             "пустой раздел не должен рисовать пустой список")

    def test_route_matches_the_bookings(self):
        """Маршрут в шапке и брони не должны разъехаться молча."""
        cities = [r["city"] for r in REAL["route"]]
        self.assertEqual(cities, ["В дороге", "Токио", "Киото", "Киносаки", "Токио"])
        self.assertEqual(REAL["route"][0]["from"], REAL["trip"]["start"])
        self.assertEqual(REAL["route"][-1]["to"], REAL["trip"]["end"])


class ChecksCanFail(unittest.TestCase):
    """Каждое правило — со своей поломкой."""

    def test_gap_between_stays_is_caught(self):
        data = broken()
        for s in data["stays"]:
            if s["id"] == "omo5":
                s["checkin"]["date"] = "2027-01-10"
                s["nights"] = 3
        with self.assertRaises(Failed) as it:
            check(data)
        self.assertIn("без крыши", str(it.exception))

    def test_night_count_lie_is_caught(self):
        data = broken()
        data["stays"][0]["nights"] = 9
        with self.assertRaises(Failed) as it:
            check(data)
        self.assertIn("по датам", str(it.exception))

    def test_money_split_that_does_not_add_up_is_caught(self):
        data = broken()
        for s in data["stays"]:
            if s["id"] == "omo3":
                s["payment"]["upcoming_jpy"] = 100_000
        with self.assertRaises(Failed) as it:
            check(data)
        self.assertIn("не сходится", str(it.exception))

    def test_silently_dropping_the_overlap_warning_is_caught(self):
        """Главное правило: наложение нельзя убрать, оставив брони как есть."""
        data = broken()
        data["alerts"] = []
        with self.assertRaises(Failed) as it:
            check(data)
        self.assertIn("не помечена", str(it.exception))

    def test_unmarking_the_conflicting_stay_is_caught(self):
        data = broken()
        for s in data["stays"]:
            s.pop("conflict", None)
        with self.assertRaises(Failed):
            check(data)

    def test_calm_tone_does_not_disable_the_guard(self):
        """Ни сняла вопрос по 14-му — но охрана от тихой пропажи осталась.

        Тон блока и его обязательность — разные вещи. «calm» меняет голос,
        а не право убрать наложение из данных молча.
        """
        data = broken()
        self.assertEqual(data["alerts"][0]["level"], "calm")
        data["alerts"] = []
        with self.assertRaises(Failed):
            check(data)

    def test_stale_warning_without_a_real_overlap_is_caught(self):
        """И обратное: тревога, под которой уже нет наложения, тоже ошибка."""
        data = broken()
        # Так выглядел бы разрешённый конфликт: OMO3 заезжает 15-го, обе ночи
        # в онсэне остаются. Крыша над каждой ночью есть, наложения нет —
        # и красный блок обязан стать ошибкой сборки, а не остаться пугать.
        for s in data["stays"]:
            if s["id"] == "omo3":
                s["checkin"]["date"] = "2027-01-15"
                s["nights"] = 4
        with self.assertRaises(Failed) as it:
            check(data)
        self.assertIn("наложения в бронях нет", str(it.exception))

    def test_an_undeclared_gap_is_still_caught(self):
        """Ночь в дороге не должна стать дырой в проверке для всех остальных."""
        data = broken()
        data["transit"] = []
        with self.assertRaises(Failed) as it:
            check(data)
        self.assertIn("2027-01-04", str(it.exception))

    def test_transit_night_that_collides_with_a_booking_is_caught(self):
        data = broken()
        data["transit"] = [{"date": "2027-01-06", "title": "Вылет", "detail": "?"}]
        with self.assertRaises(Failed) as it:
            check(data)
        self.assertIn("есть бронь", str(it.exception))

    def test_transit_night_outside_the_trip_is_caught(self):
        data = broken()
        data["transit"][0]["date"] = "2026-12-30"
        with self.assertRaises(Failed) as it:
            check(data)
        self.assertIn("вне поездки", str(it.exception))

    def test_a_leaked_email_is_caught(self):
        data = broken()
        data["notes"].append("писать на ninogasparova@example.com")
        with self.assertRaises(Failed) as it:
            check(data)
        self.assertIn("почта", str(it.exception))

    def test_a_leaked_booking_number_is_caught(self):
        data = broken()
        data["stays"][0]["notes"] = ["номер брони 4839201"]
        with self.assertRaises(Failed) as it:
            check(data)
        self.assertIn("слово про доступ", str(it.exception))

    def test_a_leaked_card_is_caught(self):
        data = broken()
        data["notes"].append("оплата 4276 3800 1234 5678")
        with self.assertRaises(Failed) as it:
            check(data)
        self.assertIn("карт", str(it.exception))


class PageShowsIt(unittest.TestCase):
    """Проверки — про данные; здесь про то, что доехало до экрана."""

    @classmethod
    def setUpClass(cls):
        cls.html = render(copy.deepcopy(REAL))

    def test_the_settled_night_says_nothing_on_the_page_anymore(self):
        """Спокойный блок про ночь 14 → 15 больше не рисуется.

        Раньше здесь проверялось обратное: что блок есть и говорит «как
        задумано». Ни 2026-08-24 сняла это сама — «блок **как задумано**
        убивай, он действует на нервы и мешается»: страница повторяла ей
        решённое на первом экране при каждом заходе.

        Проверка перевёрнута, а не удалена, и вот почему: пропажа блока
        обязана остаться **решением**, а не случайностью следующей правки.
        Данные при этом не тронуты — наложение по-прежнему помечено в
        `trip.json`, и убрать его молча нельзя (см. класс выше).
        """
        self.assertNotIn("как задумано", self.html)
        self.assertNotIn('class="alert calm"', self.html)
        self.assertNotIn("Ночь 14 → 15 января", self.html)
        # Само наложение из данных при этом никуда не делось.
        self.assertTrue(any(a["id"] == "overlap-14" for a in REAL["alerts"]))

    def test_no_word_demands_a_decision_anymore(self):
        for gone in (
            "нужно решение",
            "требует решения",
            "Сдвинуть заезд в OMO3",
            "Отказаться от второй ночи",
            "забронирована дважды",
        ):
            self.assertNotIn(gone.lower(), self.html.lower(), gone)
        self.assertNotIn('class="alert red"', self.html)
        self.assertNotIn('class="hot"', self.html)

    def test_omo3_shows_paid_from_the_14th_and_arrival_on_the_15th(self):
        self.assertIn("приезжаешь", self.html)
        self.assertIn("15 января", self.html)
        self.assertIn("ночь 14-го — в Киносаки", self.html)
        self.assertIn("оплачена и остаётся пустой", self.html)

    def test_nothing_is_silently_resolved(self):
        """Обе оплаченные брони живы и помечены, ни одна не вычеркнута."""
        self.assertIn('id="morizuya-2"', self.html)
        self.assertIn('id="omo3"', self.html)
        self.assertEqual(self.html.count('class="stay noted"'), 2)
        self.assertEqual(self.html.count('class="stay clash"'), 0)

    def test_both_paid_nights_stay_in_the_money(self):
        """Ночь 14-го оплачена дважды и дважды же посчитана — так решила Ни."""
        # Разряды разделены узким неразрывным пробелом: сравниваем по цифрам,
        # а не по тому, каким именно пробелом их развели.
        #
        # 290675, а не 297912: итог сменился 23 августа вместе с новым
        # подтверждением lyf Ginza. Проверка этого не заметила и осталась
        # зелёной — «297 912» до сих пор стоит примером в пояснении внутри
        # `money.js`, и поиск по всей странице находил комментарий к коду
        # вместо суммы под чеком. Поэтому ищем теперь в самом чеке.
        check = re.search(r'<div class="total" id="check">(.*?)<div class="bar"',
                          self.html, re.S).group(1)
        self.assertIn("290675", re.sub(r"\s+", "", check), "итог под чеком")
        self.assertNotIn("297912", re.sub(r"\s+", "", check), "старый итог под чеком")
        digits = re.sub(r"\s+", "", self.html)
        for amount in ("290675", "27160", "121800"):
            self.assertIn(amount, digits, amount)

    def test_every_stay_has_phone_map_and_cancellation(self):
        for s in REAL["stays"]:
            self.assertIn(f'id="{s["id"]}"', self.html)
            self.assertIn(s["phone"], self.html)
            self.assertIn("maps/search", self.html)
            self.assertIn(s["cancel"]["free_until"], self.html)

    def test_deadlines_are_labelled_jst(self):
        """Каждый срок отмены назван по японскому времени, а не «до 23-го»."""
        cutoffs = re.findall(r'<p class="cancel"[^>]*>(.*?)</p>', self.html, re.S)
        self.assertEqual(len(cutoffs), len(REAL["stays"]))
        for block in cutoffs:
            self.assertIn("JST", block)

    def test_totals_are_rendered_not_typed(self):
        # Считается, а не пишется руками: сумма из данных обязана совпасть с
        # тем, что стоит под чеком. Прибитого числа здесь больше нет нарочно —
        # именно оно и протухло 23 августа, оставшись зелёным на комментарии
        # внутри money.js вместо самой суммы.
        total = sum(s["total_jpy"] for s in REAL["stays"])
        check = re.search(r'<div class="total" id="check">(.*?)<div class="bar"',
                          self.html, re.S).group(1)
        self.assertIn(str(total), re.sub(r"\s+", "", check))

    def test_every_day_of_the_trip_is_listed(self):
        """4 января — день вылета: поездка начинается им, а не прилётом.

        Разметка сменилась 24 августа: дни стали свёртками с пунктами внутри,
        потому что Ни попросила тасовать пункты и переносить их из дня в день.
        Проверяется то же самое, что и раньше, — шестнадцать дней от вылета до
        отъезда, — но по числу в заголовке свёртки.
        """
        rows = re.findall(r'<span class="dt"><b>(\d+)</b>', self.html)
        self.assertEqual(len(rows), 16)
        self.assertEqual(rows[0], "4")
        self.assertEqual(rows[-1], "19")

    def test_the_night_in_the_air_is_shown_not_hidden(self):
        """Ночь 4-го стоит в нитке отрезком, а не выпадает из поездки."""
        self.assertIn('class="bar air"', self.html)
        self.assertIn("в самолёте", self.html)
        self.assertIn("вылет", self.html)

    def test_the_thread_is_one_segment_per_city(self):
        """Нитка: четыре города плюс ночь в воздухе, ширина — это ночи.

        Ширина отрезка задана столбцами сетки, а не пикселями, поэтому её
        видно прямо в разметке: Киото занимает четыре столбца, Киносаки два.
        """
        bars = re.findall(r'<div class="bar"[^>]*grid-column:(\d+)/span (\d+)', self.html)
        self.assertEqual(len(bars), 4, "по отрезку на город")
        self.assertEqual([span for _start, span in bars], ["4", "4", "2", "4"])
        # Асакуса начинается с 15-го (12-я ночь поездки), а не с оплаченного 14-го
        self.assertEqual(bars[-1][0], "12")

    def test_kinosaki_is_one_card_but_two_deadlines(self):
        """Две брони подряд — один город, но сроки отмены у них разные.

        Слить их в одну строку значило бы показать один срок вместо двух и
        подарить ей лишний день на раздумья по первой ночи.
        """
        self.assertEqual(self.html.count('class="city"'), 4, "карточек городов четыре")
        for stay_id in ("morizuya-1", "morizuya-2"):
            self.assertIn(f'id="{stay_id}"', self.html)
        self.assertIn("2027-01-10T23:59", self.html)
        self.assertIn("2027-01-11T23:59", self.html)
        self.assertIn("2 брони по", self.html)

    def test_wishlist_places_are_marked_as_wishes(self):
        """Места из вишлиста — желания, а не брони, и это должно быть видно."""
        for place in REAL["places"]:
            self.assertIn(place["title"], self.html)
        self.assertIn("не бронь", self.html)
        self.assertEqual(self.html.count("хочу сходить"), len(REAL["stays"]) - 1,
                         "подпись стоит у каждого города, включая пустой")
        # и ни одно из них не попало в деньги
        wishes = re.search(r'class="wishes"(.*?)</div>', self.html, re.S)
        self.assertIsNotNone(wishes)
        self.assertNotIn("¥", wishes.group(1))

    def test_a_place_hung_on_a_missing_booking_is_caught(self):
        """Опечатка в «stay» — это место, которое молча не покажется."""
        data = broken()
        data["places"][0]["stay"] = "omo7"
        with self.assertRaises(Failed) as it:
            check(data)
        self.assertIn("а такой нет", str(it.exception))

    def test_the_dollar_total_is_the_sum_of_the_shown_dollars(self):
        """Столбик долларов на экране обязан сойтись с итогом под ним.

        Из общей иены вышло бы $1 875, из четырёх показанных чисел — $1 876.
        Расхождение в доллар — цена округления; в иенах всё точно.

        Чисел ровно пять: четыре города и итог за жильё. Итога за всю поездку
        среди них нет **нарочно** — он складывается с её записями уже в
        браузере, и написать его при сборке значило бы написать число, которое
        мы на этой странице ещё не знаем.
        """
        def dollars(pattern):
            return [int(re.sub(r"\s", "", x)) for x in re.findall(pattern, self.html)]

        cities = dollars(r'<p class="price">\s*<b class="usd">\$([\d\s]+)</b>')
        total = dollars(r'<b class="usd" data-usd>\$([\d\s]+)</b>')
        self.assertEqual(len(cities), 4, cities)
        self.assertEqual(len(total), 1, "итог за жильё на странице один")
        self.assertEqual(total[0], sum(cities), "итог = столбик городов")
        self.assertNotEqual(total[0], round(297_912 / 158.88),
                            "итог считается из показанного, а не из общей иены")

    def test_nothing_is_lost_from_the_long_page(self):
        """Короче — не значит меньше: списки, дни и багаж просто свёрнуты."""
        for kept in ("Решить и забронировать", "Куплено отдельно", "По дням", "Багаж",
                     "Осака — однодневная вылазка", "Yamato Transport", "TA-Q-BIN"):
            self.assertIn(kept, self.html, kept)
        self.assertEqual(self.html.count('<details class="more"'), 4)

    def test_page_is_mobile_first(self):
        self.assertIn("width=device-width", self.html)
        self.assertIn("@media (min-width:560px)", self.html.replace("\n", " "))

    def test_page_loads_nothing_from_another_host(self):
        """В дороге связь плохая: внешних **загрузок** быть не должно.

        24 августа правило пришлось развести на два, потому что оно смешивало
        разные вещи. Загрузка (`src`, стили, шрифты) происходит **без спроса** и
        ломает страницу в плохой связи — её нет и не будет. Ссылка (`href`)
        ничего не грузит: по ней переходят пальцем, и Ни попросила их сама —
        «ссылки» четвёртым пунктом, чтобы при планировании открывать сайт отеля
        и места. Запрещать их значило бы запрещать то, ради чего она просила.
        """
        loads = re.findall(r'src="(https?://[^"]+)"', self.html)
        loads += re.findall(r'<link[^>]+href="(https?://[^"]+)"', self.html)
        self.assertEqual(loads, [], "страница тянет что-то со стороны")

    def test_every_outside_link_is_a_link_and_opens_safely(self):
        """Внешняя ссылка открывается новой вкладкой и без утечки перехода."""
        for tag in re.findall(r'<a[^>]+href="https?://[^"]+"[^>]*>', self.html):
            if 'href="https://www.google.com/maps/' in tag:
                continue
            self.assertIn('target="_blank"', tag, tag)
            self.assertIn("noopener", tag, tag)

    def test_no_secret_shaped_thing_reached_the_page(self):
        for pattern in (r"[\w.+-]+@[\w-]+\.[\w.]+", r"(?i)\b(pin|пароль|номер брони)\b"):
            self.assertIsNone(re.search(pattern, self.html), pattern)


class SheWritesHereHerself(unittest.TestCase):
    """То, что Ни вносит сама, — и главное про него: этого нет в сборке.

    Запись, оказавшаяся в собранной странице, исчезла бы при первой же
    пересборке: `build.py` стирает `dist/` целиком. Поэтому страница уезжает
    с пустыми мешками, а содержимое приходит из хранилища.
    """

    @classmethod
    def setUpClass(cls):
        cls.html = render(copy.deepcopy(REAL))
        cls.island = json.loads(
            re.search(r'id="japan-data">(.*?)</script>', cls.html, re.S).group(1)
        )

    def test_the_built_page_carries_no_entries_of_hers(self):
        self.assertNotIn("entries", self.island,
                         "её записи в сборке — это записи, которые пропадут при пересборке")
        mounts = re.findall(r'<ul class="mine" data-mine="([^"]+)"></ul>', self.html)
        self.assertEqual(len(mounts), 4, "мешок под её места — у каждого города")
        self.assertIn('<ul class="mine rows-list" data-mine-booking></ul>', self.html)

    def test_every_city_she_can_choose_has_somewhere_to_show_it(self):
        """Принятая ручкой запись обязана иметь, куда показаться.

        Список городов в `_stays.js` — тот же, что мешки на странице. Разойтись
        им нельзя: место, привязанное к городу без мешка, страница примет и
        тихо не покажет — ровно та беда, от которой стоит правило №6 в check().
        """
        source = (Path(__file__).resolve().parent.parent
                  / "site" / "functions" / "api" / "_stays.js").read_text(encoding="utf-8")
        allowed = json.loads(re.search(r"STAYS = (\[.*?\]);", source, re.S).group(1))
        mounts = re.findall(r'data-mine="([^"]+)"', self.html)
        offered = re.findall(r'<option value="([^"]+)">[^<]*·', self.html)
        self.assertEqual(sorted(allowed), sorted(mounts))
        self.assertEqual(sorted(allowed), sorted(offered), "в форме предлагаются те же города")

    def test_the_money_code_on_the_page_is_the_tested_file(self):
        """Считает страница ровно тем кодом, который проверен тестом.

        `test/entries.test.mjs` читает `site/money.js` с диска и исполняет его
        как есть. Если бы страница несла свою копию, сходились бы две копии
        друг с другом, а не с тем, что видит Ни.
        """
        source = (Path(__file__).resolve().parent.parent
                  / "site" / "money.js").read_text(encoding="utf-8")
        self.assertIn(source.strip(), self.html)

    def test_the_page_gets_the_housing_numbers_already_counted(self):
        """Брони считает питон при сборке; браузер их не пересчитывает.

        Два счёта одного и того же — это два разных числа с одним именем.
        """
        housing = self.island["housing"]
        stays = REAL["stays"]
        self.assertEqual(housing["jpy"], sum(s["total_jpy"] for s in stays))
        self.assertEqual(housing["paid"], sum(s["payment"]["paid_jpy"] for s in stays))
        self.assertEqual(housing["upcoming"], sum(s["payment"]["upcoming_jpy"] for s in stays))
        self.assertEqual(housing["paid"] + housing["upcoming"] + housing["onsite"],
                         housing["jpy"], "разбивка обязана сойтись с итогом")
        shown = [int(re.sub(r"\s", "", x)) for x in
                 re.findall(r'<p class="price">\s*<b class="usd">\$([\d\s]+)</b>', self.html)]
        self.assertEqual(housing["usd"], sum(shown),
                         "доллар итога — сумма показанных городских долларов")
        self.assertEqual(self.island["fx"]["usd_per_jpy"], REAL["fx"]["usd_per_jpy"])
        self.assertEqual(self.island["fx"]["human"], "23 августа 2026",
                         "курс подписан человеческой датой, а не ГГГГ-ММ-ДД")

    def test_three_kinds_and_a_price_that_may_be_empty(self):
        for kind in ("place", "booking", "todo"):
            self.assertIn(f'data-add="{kind}"', self.html, kind)
        self.assertIn("можно пусто", self.html, "цена необязательна, и это сказано в форме")
        for state in ("уже оплачено", "предстоит", "плачу на месте"):
            self.assertIn(state, self.html, state)

    def test_ticks_no_longer_live_in_one_phone(self):
        """Список, забывающий отмеченное при смене телефона, не удержит визу."""
        for call in ("localStorage.getItem", "localStorage.setItem", "localStorage.removeItem"):
            self.assertNotIn(call, self.html, call)
        self.assertIn("хранятся на сайте, а не в телефоне", self.html)
        boxes = re.findall(r'data-todo="[^"]+"\s*\n?\s*data-built="(true|false)"', self.html)
        self.assertEqual(len(boxes), sum(len(g["items"]) for g in REAL["todo"]),
                         "у каждой галочки записано, что стоит в trip.json")

    def test_the_check_says_what_it_counts_before_it_counts_everything(self):
        """Подпись всегда про то число, которое рядом.

        Собранная страница знает только жильё — и говорит «жильё». Заголовок
        «вся поездка» появляется вместе с её записями, а не до них.
        """
        block = re.search(r'<div class="total" id="check">(.*?)</div>\s*<!--.*?-->\s*'
                          r'<div class="col">', self.html, re.S).group(1)
        cap = re.search(r'<p class="cap" data-cap>(.*?)</p>', block, re.S).group(1)
        self.assertIn("жильё", cap)
        self.assertNotIn("вся поездка", block,
                         "заголовок «вся поездка» появляется вместе с её записями, не раньше")
        self.assertIn("data-parts hidden", block, "разбивка чека пуста, пока считать нечего")


class WhatCostsMoneyIsOnTop(unittest.TestCase):
    """Сроки отмены, переезды и честная строка под чеком.

    Три вещи, у которых цена ошибки одинаковая: пропущенный срок — это полная
    стоимость брони, невидимый переезд — это опоздание на поезд, а итог,
    прочитанный как полный, — это неверный расчёт всей поездки.
    """

    @classmethod
    def setUpClass(cls):
        cls.html = render(copy.deepcopy(REAL))

    # ── сроки

    def test_the_nearest_deadline_is_in_the_masthead(self):
        """Ближайший срок стоит в шапке, а не четвёртой строкой в карточке."""
        head = re.search(r'<details class="deadlines">(.*?)</details>', self.html, re.S)
        self.assertIsNotNone(head, "блока сроков в шапке нет")
        summary = re.search(r"<summary>(.*?)</summary>", head.group(1), re.S).group(1)
        earliest = min(REAL["stays"], key=lambda s: s["cancel"]["free_until"])
        self.assertIn(earliest["cancel"]["free_until"], summary,
                      "наверху обязан стоять самый ранний срок")
        # День и месяц разведены неразрывным пробелом — сравниваем по словам.
        self.assertIn("18 декабря 2026", " ".join(summary.split()),
                      "18 декабря — OMO5 Киото; дата прибита, чтобы подмена краснела")
        # Остальные никуда не делись — они под стрелкой, а не выкинуты.
        for s in REAL["stays"]:
            self.assertIn(s["cancel"]["free_until"], head.group(1), s["name"])
        self.assertEqual(head.group(1).count("<li data-deadline="),
                         len(REAL["stays"]) - 1)

    def test_the_countdown_is_not_frozen_into_the_page(self):
        """«Осталось N дней» в разметке — это число, верное ровно сутки.

        Страница живёт неделями между сборками, поэтому остаток считает
        браузер. В HTML уезжает только дата: она не стареет.
        """
        head = re.search(r'<details class="deadlines">(.*?)</details>',
                         self.html, re.S).group(1)
        self.assertNotIn("осталось", head,
                         "остаток дописывает браузер, а не сборка")
        self.assertIn("jstDay", self.html, "дни считаются по японскому календарю")
        self.assertNotIn("Math.ceil((when - Date.now())", self.html,
                         "счёт по мгновениям давал лишний день в её пользу")

    def test_a_deadline_that_is_not_the_earliest_on_top_is_caught(self):
        """Сборка обязана назвать ближайший срок вслух — иначе подмену не видно."""
        said = "\n".join(check(copy.deepcopy(REAL)))
        self.assertIn("ближайший срок отмены: 2026-12-18", said)

    # ── переезды

    def test_transfers_stand_in_the_thread(self):
        moves = re.findall(r'<div class="move has"[^>]*>(.*?)</div>', self.html, re.S)
        self.assertEqual(len(moves), len(REAL["transfers"]))
        joined = " ".join(moves)
        for t in REAL["transfers"]:
            self.assertIn(t["how"], joined, t["how"])
            self.assertIn(t["hours"], joined, t["hours"])

    def test_an_unconfirmed_price_is_a_range_and_says_it_is(self):
        """Оценка показывается вилкой и знаком ≈, а не одним удобным числом.

        24 августа Ни спросила «а посмотреть не можете что ли?» про экспресс до
        Киносаки. Посмотрел: путеводители дают ¥4 500–5 300 за место, сервис
        бронирования JR — «от ¥7 350». Выбрать одно значило бы выдать удобное
        за подтверждённое, поэтому здесь вилка. Точного `jpy` у переезда
        по-прежнему нет: подтверждением станет её касса, а не наш поиск.
        """
        kyoto_kinosaki = next(t for t in REAL["transfers"] if t["to"] == "Киносаки")
        self.assertNotIn("jpy", kyoto_kinosaki, "подтверждённой цены у нас нет")
        self.assertEqual(kyoto_kinosaki["estimate_jpy"], [5000, 7350])
        block = re.search(r'<div class="move has"[^>]*>(?:(?!</div>).)*?'
                          r'Киото → Киносаки(.*?)</div>', self.html, re.S).group(1)
        self.assertIn('class="cost guess"', block)
        self.assertIn("≈", block, "оценка обязана быть помечена знаком")
        self.assertEqual(block.count("¥"), 2, "вилка показывается обеими границами")

    def test_a_half_known_price_shows_the_hole_next_to_the_number(self):
        """15 января знаем синкансэн и не знаем экспресс — видно и то, и то."""
        back = next(t for t in REAL["transfers"] if t["from"] == "Киносаки")
        self.assertEqual(back["jpy"], 13_970)
        # `nocost` ушёл 24 августа: непокрытая половина перестала быть дырой и
        # стала оценкой. Рядом обязаны стоять оба — точное число синкансэна и
        # вилка экспресса, иначе одно прочтётся как цена всего переезда.
        self.assertEqual(back["estimate_jpy"], [5000, 7350])
        block = re.search(r'<div class="move has"[^>]*>(?:(?!</div>).)*?'
                          r'Киносаки → Токио(.*?)</div>', self.html, re.S).group(1)
        self.assertIn("13", re.sub(r"\s+", "", block))
        self.assertIn("≈", block, "оценка экспресса стоит рядом с точным числом")
        # Пустого поля здесь больше нет — на его месте оценка. Проверяем, что
        # точное и приблизительное показаны **разными** знаками, иначе одно
        # прочтётся как другое.
        self.assertIn('class="cost guess"', block)
        self.assertIn('class="cost"', block)

    def test_a_transfer_on_a_day_nobody_moves_is_caught(self):
        """Дата мимо — переезд, который тихо не покажется в нитке."""
        data = broken()
        data["transfers"][0]["date"] = "2027-01-10"
        with self.assertRaises(Failed) as it:
            check(data)
        self.assertIn("никто никуда не едет", str(it.exception))

    def test_a_transfer_naming_the_wrong_cities_is_caught(self):
        """Подпись, которая врёт рядом с верной картинкой, хуже её отсутствия."""
        data = broken()
        data["transfers"][0]["to"] = "Осака"
        with self.assertRaises(Failed) as it:
            check(data)
        self.assertIn("а по броням", str(it.exception))

    # ── чего в итоге нет

    def test_the_total_says_out_loud_that_it_is_not_everything(self):
        block = re.search(r'<p class="notall">(.*?)</p>', self.html, re.S)
        self.assertIsNotNone(block, "строки «чего в итоге нет» под чеком нет")
        said = block.group(1)
        for named in REAL["not_in_total"]:
            self.assertIn(named, said, named)
        # Строка стоит внутри чека и выше разбивки оплаты: в одном взгляде с
        # цифрой, а не четырьмя строками ниже.
        total = re.search(r'<div class="total" id="check">(.*?)<div class="bar"',
                          self.html, re.S).group(1)
        self.assertIn('class="notall"', total)

    def test_a_number_in_that_line_is_caught(self):
        """Число здесь — второй счёт рядом с первым, и разойдутся они молча."""
        data = broken()
        data["not_in_total"].append("метро — примерно ¥8 000")
        with self.assertRaises(Failed) as it:
            check(data)
        self.assertIn("числам там не место", str(it.exception))

    def test_the_suitcase_price_is_next_to_the_suitcase(self):
        """Пересылка стоит денег и в чек не идёт — цена рядом с ней самой."""
        self.assertIn(REAL["luggage"]["cost"], self.html)


class TheSuitcaseIsInOnePlace(unittest.TestCase):
    """Ни 2026-08-24: «в трёх местах пишем про багаж и нигде не указываем сайт».

    Про чемодан сказано в одном блоке, и в нём сказано главное: кто везёт,
    как заказать, сколько стоит и куда смотреть.
    """

    @classmethod
    def setUpClass(cls):
        cls.html = render(copy.deepcopy(REAL))

    def test_the_block_says_who_carries_it_and_where_to_press(self):
        svc = REAL["luggage"]["service"]
        block = re.search(r'<div id="luggage">(.*?)<ol class="moves">',
                          self.html, re.S).group(1)
        self.assertIn(svc["name"], block, "имя службы стоит в блоке про багаж")
        self.assertIn(svc["product"], block)
        self.assertIn(svc["site"], block, "ссылка на службу доехала до страницы")
        self.assertIn(REAL["luggage"]["cost"], block, "цена стоит рядом с именем")
        # Нажимать негде — заказывается на стойке. Это первое, что должно быть
        # сказано: иначе она будет искать кнопку заказа, которой нет.
        self.assertIn("стойке отеля", block)

    def test_the_link_names_the_thing_and_opens_in_a_new_tab(self):
        """Ссылка на главную компании называет три вида бизнеса и ни одного —

        нашу услугу. Поэтому в данных стоит страница самой услуги, а рядом с
        ней записано, чем она открывалась: правило то же, что у отелей.
        """
        svc = REAL["luggage"]["service"]
        self.assertTrue(svc["site"].startswith("https://"), svc["site"])
        self.assertIn("takkyubin", svc["site"], "ссылка ведёт на саму услугу")
        self.assertIn("TA-Q-BIN", svc["site_note"], "записано, что открылось глазами")
        tag = re.search(r'<a class="btn site" href="' + re.escape(svc["site"]) + r'"[^>]*>',
                        self.html.replace("\n", " "))
        self.assertIsNotNone(tag, "ссылка на службу — настоящая ссылка")
        self.assertIn("noopener", tag.group(0))

    def test_the_name_is_said_once_and_the_build_holds_that(self):
        """Собрать в один блок — полчаса; удержать собранным — навсегда.

        Правило существует потому, что дублируется не слово, а цена и условия:
        расходятся они молча, а замечаются на стойке в чужой стране.
        """
        data = broken()
        data["todo"][2]["items"][0]["note"] = "Yamato TA-Q-BIN, со стойки отеля"
        with self.assertRaises(Failed) as it:
            check(data)
        self.assertIn("не только в `luggage.service`", str(it.exception))

    def test_a_link_without_a_label_is_caught(self):
        data = broken()
        data["luggage"]["service"]["site_label"] = ""
        with self.assertRaises(Failed) as it:
            check(data)
        self.assertIn("подпись", str(it.exception))

    def test_the_folded_summary_says_who_and_how_much(self):
        """Свёрнутое без подписи — вопрос, который решается нажатием."""
        tag = re.search(r'<span class="tag" data-tag="luggage">(.*?)</span>',
                        self.html, re.S).group(1)
        self.assertIn(REAL["luggage"]["service"]["name"], tag)
        self.assertIn("¥4 600", tag.replace(" ", " ").replace("\xa0", " "))

    def test_the_hotel_details_no_longer_repeat_it(self):
        """Подробности OMO3 были вторым местом, где это было написано."""
        omo3 = next(s for s in REAL["stays"] if s["id"] == "omo3")
        said = " ".join(omo3["notes"])
        self.assertNotIn("доставки", said)
        self.assertIn("«Багаж»", said, "вместо копии — указание, где смотреть")


class TheRuler(unittest.TestCase):
    """Линейка: иены в доллары и обратно, и ни одного своего числа.

    Ни 2026-08-24: «мне нужен конвертер из йен в доллары и обратно. небольшой,
    где-нибудь». Счёт проверяется в браузере (`test/wide.py`) — здесь про то,
    что у неё нет собственного курса и собственной арифметики.
    """

    @classmethod
    def setUpClass(cls):
        cls.html = render(copy.deepcopy(REAL))

    def test_it_is_two_fields_and_nothing_else(self):
        block = re.search(r'<div class="convert">(.*?)</div>\s*</div>',
                          self.html, re.S).group(1)
        self.assertEqual(block.count("<input"), 2, "два поля — и всё")
        self.assertIn('data-conv="jpy"', block)
        self.assertIn('data-conv="usd"', block)
        # Ни кнопки «посчитать», ни второй валюты, ни истории.
        self.assertNotIn("<button", block)
        for field in re.findall(r"<input[^>]*>", block.replace("\n", " ")):
            self.assertIn("aria-label", field, field)

    def test_there_is_no_second_rate_on_the_page(self):
        """Второй курс — это два числа с одним именем.

        Число печатается ровно там, где его читают глазами: в подписи под
        чеком и в подписи под линейкой. Машине оно достаётся из одного места
        — `#japan-data`, — а не из атрибута рядом с полями.
        """
        rate = str(REAL["fx"]["usd_per_jpy"])
        self.assertEqual(self.html.count("$1 = ¥" + rate), 2,
                         "курс подписан у чека и у линейки, и оба раза — этот")
        self.assertNotIn("data-rate", self.html,
                         "машинного второго экземпляра курса быть не должно")
        self.assertEqual(len(set(re.findall(r"¥(\d+\.\d+)", self.html))), 1,
                         "дробное число на странице одно — курс")

    def test_the_caption_under_the_fields_is_honest(self):
        """Курс, дата и то, что платит она в иенах, — под самими полями."""
        said = " ".join(re.search(r'<p class="fx">(.*?)</p>',
                                  re.search(r'<div class="convert">(.*?)</div>\s*</div>',
                                            self.html, re.S).group(1), re.S).group(1).split())
        self.assertIn(str(REAL["fx"]["usd_per_jpy"]), said)
        self.assertIn("августа 2026", said, "курс подписан датой")
        self.assertIn("иенах", said, "сказано, чем она платит на самом деле")
        self.assertIn("округлено", said, "сказано, что доллар — мерка, а не точность")

    def test_it_counts_with_the_same_money_js_as_the_check(self):
        """Своя арифметика была бы третьим способом посчитать одно и то же."""
        script = re.search(r'var ruler = document\.querySelector\(".convert"\);(.*?)\n  }',
                           self.html, re.S).group(1)
        self.assertIn("JapanMoney.toUsd", script)
        self.assertIn("JapanMoney.yenOf", script)
        self.assertNotIn("158.88", script, "курс не вписан в скрипт руками")
        self.assertNotIn("localStorage", script, "линейка ничего не сохраняет")
        self.assertNotIn("fetch", script, "линейка никуда не ходит")


class TheDaysAreHers(unittest.TestCase):
    """План по дням: её текст, вечные id и ни одного второго числа.

    Ни 2026-08-24: «вот это забери расписание. но мне нужно сделать так, чтобы
    можно было места тасовать и переносить из дня в день. и ссылки на них
    нужны».

    Тасовка живёт в хранилище и проверяется отдельно — `test/days.test.mjs`
    (правила) и `test/round.sh` (настоящий круг с настоящей KV). Здесь про то,
    что уезжает в git и на страницу: данные, ссылки и разметка.
    """

    @classmethod
    def setUpClass(cls):
        cls.plan = load_plan()
        cls.html = render(copy.deepcopy(REAL), copy.deepcopy(cls.plan))
        cls.days = re.search(r'<div id="days">(.*?)\n</div>', cls.html, re.S).group(1)

    def bent(self):
        return copy.deepcopy(self.plan)

    def block(self, item_id: str) -> str:
        """Разметка одного пункта — по вечному id, а не по порядку."""
        return re.search(
            r'<li class="it" data-item="%s".*?</li>' % re.escape(item_id),
            self.days, re.S).group(0)

    # ── данные

    def test_the_plan_covers_the_trip_day_by_day(self):
        self.assertEqual(len(self.plan), 16)
        self.assertEqual(self.plan[0]["date"], REAL["trip"]["start"])
        self.assertEqual(self.plan[-1]["date"], REAL["trip"]["end"])
        self.assertEqual(sum(len(x["items"]) for x in self.plan), 98)

    def test_ids_are_unique_because_storage_remembers_by_them(self):
        seen = [i["id"] for day in self.plan for i in day["items"]]
        self.assertEqual(len(seen), len(set(seen)))

    def test_a_repeated_id_is_caught(self):
        """Два пункта с одним id ходят парой и удаляются вместе — молча."""
        plan = self.bent()
        plan[2]["items"][0]["id"] = plan[1]["items"][0]["id"]
        with self.assertRaises(Failed) as it:
            check(copy.deepcopy(REAL), plan)
        self.assertIn("дважды", str(it.exception))

    def test_a_day_outside_the_trip_is_caught(self):
        plan = self.bent()
        plan[3]["date"] = "2027-02-01"
        with self.assertRaises(Failed) as it:
            check(copy.deepcopy(REAL), plan)
        self.assertIn("дни плана", str(it.exception))

    def test_a_missing_day_is_caught(self):
        plan = self.bent()
        del plan[5]
        with self.assertRaises(Failed):
            check(copy.deepcopy(REAL), plan)

    def test_a_place_that_is_not_in_places_is_caught(self):
        """Ссылка берётся из `places`; выдуманное имя — ссылка в никуда."""
        plan = self.bent()
        plan[4]["items"][0]["place"] = "Кафе, которого нет"
        with self.assertRaises(Failed) as it:
            check(copy.deepcopy(REAL), plan)
        self.assertIn("ссылку взять неоткуда", str(it.exception))

    def test_two_addresses_for_one_thing_are_caught(self):
        """Адрес живёт в одном месте: и `place`, и свой `site` — это два."""
        plan = self.bent()
        item = next(i for day in plan for i in day["items"] if i.get("place"))
        item["site"] = "https://example.com/"
        with self.assertRaises(Failed) as it:
            check(copy.deepcopy(REAL), plan)
        self.assertIn("в одном месте", str(it.exception))

    def test_a_site_without_https_is_caught(self):
        plan = self.bent()
        item = next(i for day in plan for i in day["items"] if i.get("site"))
        item["site"] = "http://" + item["site"][8:]
        with self.assertRaises(Failed) as it:
            check(copy.deepcopy(REAL), plan)
        self.assertIn("не https", str(it.exception))

    def test_a_transfer_on_a_day_nobody_moves_is_caught(self):
        plan = self.bent()
        item = next(i for day in plan for i in day["items"] if i.get("transfer"))
        item.pop("transfer")
        plan[6]["items"][0]["transfer"] = "tokyo-kyoto"
        with self.assertRaises(Failed) as it:
            check(copy.deepcopy(REAL), plan)
        self.assertIn("никто никуда не едет", str(it.exception))

    def test_a_lost_item_from_her_booking_list_is_caught(self):
        """Её «что обязательно бронировать» — сверка полноты разбора."""
        plan = self.bent()
        plan[2]["items"] = [i for i in plan[2]["items"] if i["id"] != "d06-6"]
        with self.assertRaises(Failed) as it:
            check(copy.deepcopy(REAL), plan)
        self.assertIn("потерялось при разборе", str(it.exception))

    def test_the_old_days_section_cannot_come_back(self):
        """Два заголовка на одну дату в двух файлах расходятся молча."""
        trip = copy.deepcopy(REAL)
        trip["days"] = {"2027-01-05": {"title": "Прилёт", "items": ["Заезд с 15:00"]}}
        with self.assertRaises(Failed) as it:
            check(trip, self.bent())
        self.assertIn("days-plan.json", str(it.exception))

    def test_the_cities_of_the_plan_match_the_bookings(self):
        """Раздел дней и нитка обязаны рассказывать один маршрут."""
        plan = self.bent()
        for day in plan:
            if day["city"] == "Киото":
                day["city"] = "Осака"
        with self.assertRaises(Failed) as it:
            render(copy.deepcopy(REAL), plan)
        self.assertIn("разошлись", str(it.exception))

    # ── страница

    def test_every_item_is_on_the_page_with_its_eternal_id(self):
        found = re.findall(r'<li class="it" data-item="([^"]+)"', self.days)
        self.assertEqual(found, [i["id"] for day in self.plan for i in day["items"]])

    def test_the_name_leads_to_the_map_and_only_where_there_is_one(self):
        """В поездке от названия нужно «где это», а не «что про это пишут»."""
        for day in self.plan:
            for item in day["items"]:
                block = self.block(item["id"])
                if item.get("spots"):
                    # Разрезанная строка проверяется отдельно: там ссылка у
                    # каждого места своя, и у проверенного в `places` она
                    # ведёт на его сайт, а не на карту.
                    continue
                if item.get("map"):
                    self.assertIn("google.com/maps/search/", block, item["id"])
                    self.assertIn('target="_blank"', block, item["id"])
                    self.assertIn('rel="noopener"', block, item["id"])
                elif not item.get("book"):
                    # «Обед» и «выезд» ссылками не притворяются. Исключение —
                    # «бронировать» с адресом: это ссылка на пометке, а не на
                    # названии, и стоит она у поездов и билетов без адреса.
                    self.assertNotIn("<a ", block, item["id"])

    def test_each_place_in_a_line_gets_its_own_link(self):
        """Ни 2026-08-24: «залинковывай каждую локацию отдельно, а не строку
        целиком, чтобы я не гадала, что же по ссылке откроется».

        «Yasaka Shrine, Maruyama Park, Chion-in» было одной ссылкой на три
        места — открывалась она на первом, а два других молча вели туда же.
        """
        split = [i for day in self.plan for i in day["items"] if i.get("spots")]
        self.assertEqual(len(split), 16, "строк с несколькими местами")
        for item in split:
            block = self.block(item["id"])
            self.assertIn("data-spots", block, item["id"])
            self.assertEqual(block.count("<a "), len(item["spots"]), item["id"])
            for spot in item["spots"]:
                self.assertIn(">" + spot["name"] + "</a>", block, item["id"])
        # Поисковая строка всей строки не пропала — ссылкой она больше не
        # становится, но правка обязана видеть тот же адрес, что и файл.
        for item in split:
            self.assertIn('data-map="%s"' % item["map"], self.block(item["id"]))

    def test_a_place_missing_from_the_line_is_caught(self):
        """Ссылка вешается на кусок названия: имя мимо строки не покраснело бы
        нигде — место просто осталось бы без ссылки."""
        plan = self.bent()
        item = next(i for day in plan for i in day["items"] if i.get("spots"))
        item["spots"][0]["name"] = "Место, которого в строке нет"
        with self.assertRaises(Failed) as it:
            check(copy.deepcopy(REAL), plan)
        self.assertIn("нет в названии", str(it.exception))

    def test_a_place_with_nothing_to_open_is_caught(self):
        plan = self.bent()
        item = next(i for day in plan for i in day["items"] if i.get("spots"))
        item["spots"][0].pop("map", None)
        item["spots"][0].pop("place", None)
        with self.assertRaises(Failed) as it:
            check(copy.deepcopy(REAL), plan)
        self.assertIn("нечего открыть", str(it.exception))

    def test_the_address_rides_inside_the_word_book(self):
        """Ни 2026-08-24: «там, где надо бронировать проставь ссылки на сайт
        прямо в надписи бронировать, **не придумывай новую**».

        Отдельной метки «сайт» больше нет: она была лишней надписью рядом с
        уже стоящей пометкой.
        """
        self.assertNotIn('class="mk site"', self.days)
        links = re.findall(r'<a class="mk bk" href="([^"]+)"', self.days)
        self.assertEqual(len(links), 5, "три билета и два стола")
        for href in links:
            self.assertTrue(href.startswith("https://"), href)
        # Где бронировать надо, а адреса нет (поезда, чемодан) — пометка
        # остаётся, но ссылкой не притворяется.
        plain = re.findall(r'<span class="mk bk">', self.days)
        booked = [i for day in self.plan for i in day["items"] if i.get("book")]
        self.assertEqual(len(links) + len(plain), len(booked))
        self.assertEqual(len(plain), 4, "четыре поезда без своей страницы")

    def test_the_verified_places_are_linked_not_copied(self):
        """Четыре места уже проверены — адрес берётся оттуда, а не пишется второй раз."""
        known = {p["title"]: p["site"] for p in REAL["places"]}
        for title, site in known.items():
            self.assertIn(site, self.days, f"{title}: ссылка из `places` не доехала")
        self.assertEqual(
            self.html.count('href="' + known["KUMONOCHA"] + '"'), 3,
            "KUMONOCHA — в карточке города и в двух днях, но адрес один",
        )

    def test_a_transfer_day_carries_no_second_price(self):
        """Цена переезда живёт в «Переездах». Второе число рядом с первым
        расходится молча, а замечается на кассе."""
        for day in self.plan:
            for item in day["items"]:
                if not item.get("transfer"):
                    continue
                block = re.search(
                    r'<li class="it" data-item="%s".*?</li>' % re.escape(item["id"]),
                    self.days, re.S).group(0)
                self.assertIn("в «Переездах»", block)
                self.assertNotIn("¥", block, item["id"])

    def test_no_prices_leak_into_the_days_at_all(self):
        """У пунктов нет цен, и придумывать их нельзя: в чек дни не идут."""
        self.assertNotIn("¥", self.days)
        self.assertNotIn("$", self.days)

    def test_the_days_are_folded_by_default(self):
        """«Слишком много листать вниз» — её слово про длинную версию."""
        self.assertEqual(self.days.count("<details"), self.days.count("</details>"))
        self.assertEqual(self.days.count('<details class="day'), 16)
        opened = re.findall(r"<details[^>]*\sopen[^>]*>", self.days)
        self.assertEqual(len(opened), 5,
                         "открыты только отрезки городов — вылет и четыре города; "
                         "дни свёрнуты, ближайший раскрывает браузер")

    def test_the_handles_appear_only_when_storage_answers(self):
        """Кнопка, которой некуда нажать, — обещание, которое не сдержать."""
        for gone in ("убрать", "правка", "+ пункт"):
            self.assertNotIn(gone, self.days, f"«{gone}» нарисовано до ответа хранилища")

    def test_the_day_picker_is_gone_from_the_page_and_from_the_script(self):
        """Ни 2026-08-24: «поэтому я попросила сделать дни в два столбца, а не
        колбасой вниз».

        Список «в день →» был обходом длинной колбасы: с 6 января на 17-е
        мышью было не дотянуться. Столбцы этот обход отменили, и список убран
        целиком — из разметки, из скрипта и из данных страницы.

        Проверяются все три конца, потому что вернуться он может любым: узел в
        `<li>`, `select` в скрипте дней и подпись дня в `japan-data`, чьим
        единственным читателем список и был.
        """
        self.assertNotIn("перенести в день", self.html)
        script = re.search(r"var box = document\.getElementById\(\"japan-data\"\);.*",
                           self.html, re.S).group(0)
        self.assertNotIn("select", script, "список дат вернулся в скрипт дней")
        days = json.loads(
            re.search(r'<script type="application/json" id="japan-data">(.*?)</script>',
                      self.html, re.S).group(1))["days"]
        self.assertEqual([sorted(x) for x in days], [["date"]] * 16,
                         "подпись дня читал только список дат — без него это мёртвые данные")

    def test_the_clock_is_gone_from_the_page_but_not_from_the_data(self):
        """Ни 2026-08-24: «часы убей, они ломаются при перетаскивании и в целом
        лишние, **не хочу жить по расписанию**».

        Из данных `time` не выброшен — её текст мы не выкидываем; он просто не
        рисуется. Проверяются оба конца: часов на странице нет, в файле есть.
        """
        self.assertNotIn('class="tm"', self.days)
        # Расписание — это вилка «с и до», а не всякое упоминание часа: «заезд
        # с 15:00» она как раз просила оставить. Ищется именно вилка.
        self.assertIsNone(re.search(r"\d{1,2}:\d{2}\s*[–—-]\s*\d{1,2}:\d{2}", self.days),
                          "часовая вилка вернулась на страницу")
        clocked = [i for day in self.plan for i in day["items"]
                   if re.search(r"\d{1,2}:\d{2}", i.get("time", ""))]
        self.assertGreater(len(clocked), 40, "часы в данных остались — её текст не выкидываем")
        for item in clocked:
            # У «Заселения» 13-го час стоит и в снятых часах, и в пометке
            # («заезд с 15:00»): пометка — её же просьба, и сверять по ней
            # значило бы требовать, чтобы час не назывался вообще.
            if re.search(r"\d{1,2}:\d{2}", item.get("when", "")):
                continue
            self.assertNotIn(item["time"], self.block(item["id"]), item["id"])

    def test_a_time_mark_stands_only_where_time_ties_something(self):
        """«а если где-то важно время — пометь, что к примеру только до 15».

        Пустая пометка не рисуется вовсе — иначе мы поменяли бы часы на пустое
        место под часы. Узел при этом стоит и пустой: дописать пометку она
        может прямо на странице, и второй способ его создать означал бы два
        описания одной вещи.
        """
        marked = [i for day in self.plan for i in day["items"] if i.get("when")]
        self.assertEqual(len(marked), 17, "пометок времени на 98 пунктов")
        for item in marked:
            self.assertIn(f'<span class="mk wn" data-part="time">{item["when"]}</span>',
                          self.block(item["id"]), item["id"])
        blank = next(i for day in self.plan for i in day["items"] if not i.get("when"))
        self.assertIn('<span class="mk wn" data-part="time" hidden></span>',
                      self.block(blank["id"]))
        # `hidden` на `.mk` погашен в CSS отдельным правилом: `inline-block`
        # перебивает его молча, и пустая пометка стала бы пустой пилюлей.
        self.assertIn(".it .mk[hidden]", self.html)

    def test_the_fold_of_the_days_carries_no_subtitle(self):
        """Ни 2026-08-24: «подпись к блоку и все кнопки убивай, они только
        мусорность создают и место занимают».

        Раньше здесь проверялось обратное — что «16 дней · 98 пунктов» стоит у
        свёртки. Проверка перевёрнута, а не удалена: подпись обязана не
        вернуться следующей правкой. У багажа своя подпись остаётся — про неё
        разговора не было, и она отвечает на вопрос «кто везёт и почём».
        """
        self.assertNotIn('data-tag="days"', self.html)
        self.assertNotIn("16 дней · 98 пунктов", self.html)
        self.assertIn('data-tag="luggage"', self.html)

    def test_one_button_folds_the_whole_section(self):
        """Свёртка — чистая разметка, поэтому кнопка стоит в собранной
        странице: она работает и тогда, когда расстановка не доехала."""
        self.assertIn('<button type="button" class="foldall" data-fold-all', self.days)
        self.assertIn("развернуть все дни", self.days)

    def test_her_notes_to_a_day_are_kept_word_for_word(self):
        for day in self.plan:
            if day.get("day_note"):
                self.assertIn(day["day_note"], self.days, day["date"])

    def test_the_door_gets_the_plan_the_page_was_built_from(self):
        """Вчерашний план у двери отбил бы перенос в день, который уже есть."""
        write_plan(copy.deepcopy(self.plan))
        made = (SITE / "functions" / "api" / "_plan.js").read_text(encoding="utf-8")
        body = json.loads(re.search(r"export const PLAN = (\[.*\]);", made, re.S).group(1))
        self.assertEqual([x["date"] for x in body], [x["date"] for x in self.plan])
        self.assertEqual(
            [i for x in body for i in x["items"]],
            [i["id"] for day in self.plan for i in day["items"]],
        )
        # Только id: текст живёт на странице, и второй его экземпляр означал бы,
        # что поправка доезжает до неё через раз.
        self.assertNotIn("Shibuya Sky", made)


class TheReferenceCannotPassAGuessOffAsAFact(unittest.TestCase):
    """Справка внизу: виза, документы до вылета, такс-фри.

    Половина этого класса — про одну-единственную ошибку: непроверенное,
    нарисованное как факт. Она дороже любой вёрстки на этой странице, потому
    что ошибиться в ней нельзя заметить глазами: неверная строка выглядит
    ровно как верная, и разница вылезает в консульстве.

    Три пункта про визу — порядок записи, срок рассмотрения, пошлина — взяты
    из вторичных источников: сайт посольства Японии в Грузии отвечает нашему
    серверу 403 на все страницы, включая главную. День, когда они молча
    станут обычными строками, обязан здесь покраснеть.
    """

    @classmethod
    def setUpClass(cls):
        cls.html = reference()

    # ── как выглядит нарисованный пункт
    #
    # Классы читаются из разметки, а не угадываются по тексту: `li.fact`,
    # `li.unsure`, `li.think` — это и есть три вида происхождения, и тест
    # обязан ловить именно подмену вида, а не пропажу слова.
    ROW = re.compile(r'<li class="(fact|unsure|think)">(.*?)</li>', re.S)

    def rows(self, html=None):
        return {
            re.sub(r"<[^>]+>", "", body): kind
            for kind, body in self.ROW.findall(html if html is not None else self.html)
        }

    def test_the_real_reference_counts_up(self):
        said = "\n".join(check_reference(copy.deepcopy(REF)))
        # Числа прибиты нарочно: догадка, тихо ставшая фактом, меняет их —
        # и именно этого мы здесь и ждём.
        self.assertIn("справка, виза: 4 подтверждено, 3 нет, 0 от нас", said)
        self.assertIn("справка, до вылета: 2 подтверждено, 0 нет, 1 от нас", said)
        self.assertIn("6 подтверждено, 0 нет, 0 от нас", said)
        self.assertIn("16 пунктов", said)

    def test_every_item_is_drawn_as_what_it_is(self):
        """Сверка экрана с данными: у каждого пункта свой вид, и он тот самый."""
        drawn = self.rows()
        for block in REF["blocks"]:
            for item in block["items"]:
                found = [k for text, k in drawn.items() if item["text"] in text]
                self.assertEqual(len(found), 1,
                                 f'пункт нарисован один раз: «{item["text"][:40]}…»')
                want = ("think" if item.get("mine") is True
                        else "fact" if item.get("verified") is True else "unsure")
                self.assertEqual(found[0], want,
                                 f'«{item["text"][:40]}…» нарисован как {found[0]}, '
                                 f"а он {want}")

    def test_the_unconfirmed_say_so_and_say_what_to_ask(self):
        """Пометки мало: рядом должно стоять, что именно спросить в посольстве.

        Сноской внизу это читают уже после того, как поверили.
        """
        unsure = [i for b in REF["blocks"] for i in b["items"]
                  if i.get("verified") is False]
        self.assertEqual(len(unsure), 3, "непроверенных три — порядок, срок, пошлина")
        drawn = re.findall(r'<li class="unsure">(.*?)</li>', self.html, re.S)
        self.assertEqual(len(drawn), len(unsure))
        for item in unsure:
            row = [x for x in drawn if item["text"] in x]
            self.assertEqual(len(row), 1, f'«{item["text"][:40]}…» нарисован один раз')
            self.assertIn("не подтверждено", row[0])
            self.assertIn(item["how"], row[0],
                          f'сказано, что спросить: «{item["text"][:40]}…»')

    def test_our_own_thinking_is_never_dressed_as_a_rule(self):
        mine = [i for b in REF["blocks"] for i in b["items"] if i.get("mine") is True]
        self.assertTrue(mine)
        for item in mine:
            self.assertIn("наше соображение", self.html)
            self.assertEqual(
                [k for text, k in self.rows().items() if item["text"] in text], ["think"])
        # И то же снаружи: соображение про новогодние каникулы стоит вне свёртки,
        # где его видно не открывая, — и там оно тоже помечено.
        warn = REF["blocks"][0]["warning"]
        self.assertIs(warn["mine"], True)
        outside = self.html[:self.html.index('<details class="visa-more"')]
        self.assertIn(warn["text"], outside, "соображение видно, не открывая")
        self.assertIn("наше соображение", outside)

    # ── а теперь — умеет ли всё это краснеть
    #
    # Проверка, которая ни разу не падала, и отсутствие проверки выглядят
    # снаружи одинаково. Поэтому на каждое правило — своя поломка.

    def test_a_guess_wearing_the_word_verified_is_refused(self):
        """Ровно та ошибка, ради которой раздел устроен именно так."""
        for item in ({"text": "Пошлина — около ¥3 000.", "verified": True,
                      "mine": True},
                     {"text": "Пошлина — около ¥3 000."}):
            with self.assertRaises(Failed) as it:
                ref_item(item)
            self.assertIn("происхожден", str(it.exception))

    def test_an_unconfirmed_item_that_stays_silent_is_refused(self):
        """Не подтверждено — половина ответа. Вторая: что с этим делать."""
        with self.assertRaises(Failed) as it:
            ref_item({"text": "Подача по записи.", "verified": False, "how": "  "})
        self.assertIn("молчит", str(it.exception))

    def test_the_count_of_guesses_is_checked_too(self):
        data = copy.deepcopy(REF)
        del data["blocks"][0]["items"][2]["verified"]
        with self.assertRaises(Failed) as it:
            check_reference(data)
        self.assertIn("происхождения", str(it.exception))

    def test_a_reference_without_a_date_is_refused(self):
        """Правила меняются, а страница живёт месяцами.

        Цифра без даты через полгода читается как сегодняшняя — поэтому дата
        проверки не необязательное поле, а условие показа.
        """
        data = copy.deepcopy(REF)
        data["checked"] = "недавно"
        with self.assertRaises(Failed) as it:
            check_reference(data)
        self.assertIn("даты проверки", str(it.exception))

    def test_the_date_is_not_in_the_future(self):
        self.assertLessEqual(date.fromisoformat(REF["checked"]), date.today(),
                             "проверено задним числом — значит не проверено")

    # ── и то, что видно, не открывая
    #
    # Виза — самый срочный срок на странице: вылет 4 января, подача только
    # очно, конец декабря у японских учреждений нерабочий. Свёрнутая наравне с
    # такс-фри, она читается как «ещё одна справка» и открывается в феврале.

    def test_the_visa_is_not_hidden_under_the_same_arrow(self):
        outside = self.html[:self.html.index('<details class="visa-more"')]
        self.assertIn("самое срочное", outside)
        self.assertIn(REF["blocks"][0]["lead"], outside, "повод виден снаружи")
        self.assertIn("4 января", outside)
        # А подробности — под своей стрелкой, не под общей с такс-фри.
        self.assertNotIn('data-ref="taxfree"', outside)

    def test_the_tax_free_flip_is_in_the_headline(self):
        """Кто помнит старые правила, ничего открывать не станет.

        Поэтому «работает наоборот» стоит в строке заголовка, а подпись
        свёртки говорит, что именно перевернулось.
        """
        tax = [b for b in REF["blocks"] if b["id"] == "taxfree"][0]
        self.assertIn("наоборот", tax["title"], "переворот назван в самих данных")
        head = re.search(r'data-ref="taxfree">\s*<summary>(.*?)</summary>',
                         self.html, re.S).group(1)
        self.assertIn(tax["title"], head)
        self.assertIn("возвращаешь в аэропорту", head)
        # Подпись — сжатие пункта, а не отдельное утверждение. Разойтись они
        # успеют молча: правила меняются, а строка в коде остаётся.
        items = " ".join(i["text"] for i in tax["items"])
        self.assertIn("возврат получаешь при вылете", items)
        self.assertIn("Теперь платишь полную цену с налогом", items)

    def test_the_only_link_is_one_we_opened(self):
        links = re.findall(r'<a class="btn" href="([^"]+)"', self.html)
        self.assertEqual(links, ["https://services.digital.go.jp/en/visit-japan-web/"])
        self.assertIn('rel="noreferrer noopener"', self.html)

    def test_the_check_date_stands_in_the_footer(self):
        """Отдельной строкой под справкой она стоила 37 точек высоты.

        В подвале — ноль: строка там уже есть, и «обновлено» с «проверено»
        врозь всё равно читаются как разные вещи.
        """
        html = render(copy.deepcopy(REAL))
        foot = re.search(r'<footer class="colophon">(.*?)</footer>', html, re.S).group(1)
        # Разряды и даты на этой странице разведены неразрывными пробелами —
        # сравниваем по словам, а не по тому, каким пробелом они разделены.
        said = " ".join(foot.split())
        self.assertIn("Справка внизу проверена", said)
        self.assertIn("24 августа 2026", said)
        self.assertNotIn('class="ref-checked"', html[:html.index("<footer")])


if __name__ == "__main__":
    unittest.main(verbosity=2)
