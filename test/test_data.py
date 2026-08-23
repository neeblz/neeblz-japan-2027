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

from build import DATA, Failed, check, render  # noqa: E402

REAL = json.loads(DATA.read_text(encoding="utf-8"))


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
        self.assertEqual(sum(s["total_jpy"] for s in stays), 297_912)
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

    def test_the_fourteenth_is_a_calm_note_not_an_alarm(self):
        """Ни решила: так и задумано. Страница не должна с ней спорить."""
        self.assertIn('class="alert calm"', self.html)
        self.assertIn("Ночь 14 → 15 января", self.html)
        self.assertIn("как задумано", self.html)
        self.assertIn(
            "14 → 15 ночуешь в Киносаки; OMO3 оплачен с 14-го, заезд 15-го.",
            self.html,
        )

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
        digits = re.sub(r"\s+", "", self.html)
        for amount in ("297912", "27160", "121800"):
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
        self.assertIn("297 912", self.html.replace(" ", " "))

    def test_every_day_of_the_trip_is_listed(self):
        """4 января — день вылета: поездка начинается им, а не прилётом."""
        rows = re.findall(r'<div class="date">\s*<b>(\d+)</b>', self.html)
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
                     "Осака — однодневная вылазка", "Yamato TA-Q-BIN"):
            self.assertIn(kept, self.html, kept)
        self.assertEqual(self.html.count('<details class="more"'), 4)

    def test_page_is_mobile_first(self):
        self.assertIn("width=device-width", self.html)
        self.assertIn("@media (min-width:560px)", self.html.replace("\n", " "))

    def test_page_asks_no_other_host_for_anything(self):
        """В дороге связь плохая: внешних загрузок быть не должно."""
        outside = re.findall(r'(?:src|href)="(https?://[^"]+)"', self.html)
        for url in outside:
            self.assertTrue(
                url.startswith("https://www.google.com/maps/"),
                f"страница тянет что-то со стороны: {url}",
            )

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
        block = re.search(r'<div class="total" id="check">(.*?)</div>\s*<div class="beyond">',
                          self.html, re.S).group(1)
        cap = re.search(r'<p class="cap" data-cap>(.*?)</p>', block, re.S).group(1)
        self.assertIn("жильё", cap)
        self.assertNotIn("вся поездка", block,
                         "заголовок «вся поездка» появляется вместе с её записями, не раньше")
        self.assertIn("data-parts hidden", block, "разбивка чека пуста, пока считать нечего")


if __name__ == "__main__":
    unittest.main(verbosity=2)
