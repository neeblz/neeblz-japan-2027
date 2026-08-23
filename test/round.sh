#!/usr/bin/env bash
# Настоящий круг: внесла → пересобрал → на месте.
#
#     ./test/round.sh
#
# Всё остальное проверяется без сети (`node --test`, `test_data.py`). Одну
# вещь так проверить нельзя: что её запись лежит **не в файлах сборки**.
# Собранная папка стирается каждой сборкой целиком — значит запись, попавшая
# в неё, исчезнет при первой же выкладке, и увидит это Ни, а не тест.
#
# Поэтому здесь поднимается настоящий рантайм Workers с настоящей KV на диске
# (`wrangler pages dev --kv`), в него вносится запись, потом `dist/` стирается
# и собирается заново, сервер поднимается снова — и запись обязана быть на
# месте. Хранилище нарочно лежит **вне** `dist/`: внутри оно было бы стёрто
# вместе с папкой, и круг доказывал бы ровно ничего.
#
# Заодно проверяется дверь перед ручкой: без печенья 401, и никакого списка.
set -euo pipefail

cd "$(dirname "$0")/.."

PORT=8973
STATE="$PWD/.wrangler/round-state"     # вне dist/ — переживает пересборку
PW="proba-kruga-$RANDOM$RANDOM"        # латиница: кириллица не переживает --binding
JAR=$(mktemp); OUT=$(mktemp); LOG=$(mktemp)
ok=0; bad=0

say() { if [ "$1" = y ]; then ok=$((ok+1)); echo "✓ $2"; else bad=$((bad+1)); echo "✗ $2"; fi; }

kill_tree() {  # pid → снять его и всё, что он породил
  local pid=$1 child
  [ -n "${pid:-}" ] && [ -d "/proc/$pid" ] || return 0
  for child in $(pgrep -P "$pid" 2>/dev/null); do kill_tree "$child"; done
  kill "$pid" 2>/dev/null || true
  # workerd переживает TERM, а node над ним поднимает его заново.
  local i; for i in 1 2 3; do [ -d "/proc/$pid" ] || return 0; sleep 1; done
  kill -9 "$pid" 2>/dev/null || true
}

ROOT=""
start() {
  (cd dist && timeout 180 npx wrangler pages dev . --port "$PORT" --ip 127.0.0.1 \
      --binding "JAPAN_PASSWORD=$PW" --kv JAPAN_KV --persist-to "$STATE" \
      >>"$LOG" 2>&1) &
  ROOT=$!
  local i
  for i in $(seq 1 45); do
    curl -s -o /dev/null -m 2 "http://127.0.0.1:$PORT/" && return 0
    sleep 1
  done
  echo "✗ wrangler не поднялся; хвост лога:" >&2; tail -8 "$LOG" >&2; exit 1
}
stop() { kill_tree "$ROOT"; ROOT=""; }
cleanup() { stop; rm -f "$JAR" "$OUT" "$LOG"; }
trap cleanup EXIT

# Порт мог остаться занятым прошлым прогоном — тогда мы проверяли бы не то,
# что собрали сейчас, а вчерашний сервер с вчерашним паролем.
if ss -lptn "sport = :$PORT" 2>/dev/null | grep -q "pid="; then
  echo "✗ порт $PORT занят — прибери прошлый прогон" >&2; exit 1
fi

rm -rf "$STATE"          # круг начинается с пустого хранилища, а не с чужого
echo "— поднимаю сайт с настоящей KV"
start

# ── дверь стоит и перед ручкой
code=$(curl -s -o "$OUT" -w '%{http_code}' "http://127.0.0.1:$PORT/api/entries")
say "$([ "$code" = 401 ] && echo y || echo n)" "без пароля ручка записей отвечает $code (ждали 401)"
grep -q '"entries"' "$OUT" && say n "за 401 виден список записей" || say y "за 401 списка не видно"

curl -s -o /dev/null -c "$JAR" -b "$JAR" -X POST "http://127.0.0.1:$PORT/login" \
     --data-urlencode "password=$PW" --data "next=/"

# ── пусто до первой записи
curl -s -b "$JAR" -o "$OUT" "http://127.0.0.1:$PORT/api/entries"
python3 -c "
import json,sys; d=json.load(open('$OUT'))
sys.exit(0 if d.get('ok') and d['entries']==[] else 1)" \
  && say y "с паролем ручка отвечает пустым списком" \
  || { say n "пустой список не получен: $(cat "$OUT")"; }

post() {  # тело → ответ в $OUT, код возврата curl
  curl -s -b "$JAR" -o "$OUT" -w '%{http_code}' -X POST "http://127.0.0.1:$PORT/api/entries" \
       -H "content-type: application/json" --data "$1"
}

# ── три вида записей, включая одну без цены и одну в долларах
code=$(post '{"kind":"place","title":"Кофейня у Асакусы","stay":"omo3","amount":"1 800","note":"проба круга"}')
say "$([ "$code" = 200 ] && echo y || echo n)" "место записалось ($code)"
code=$(post '{"kind":"booking","title":"Перелёт туда-обратно","amount":980,"currency":"usd","state":"paid"}')
say "$([ "$code" = 200 ] && echo y || echo n)" "бронь в долларах записалась ($code)"
code=$(post '{"kind":"todo","title":"Виза","group":"Дорога"}')
say "$([ "$code" = 200 ] && echo y || echo n)" "пункт то-до без цены записался ($code)"

# ── и то, что записаться не должно
code=$(post '{"kind":"place","title":"Кафе","stay":"omo7"}')
say "$([ "$code" = 422 ] && echo y || echo n)" "место в несуществующем городе отбито ($code)"
code=$(post '{"kind":"todo","title":"   "}')
say "$([ "$code" = 422 ] && echo y || echo n)" "запись без названия отбита ($code)"
code=$(post '{"kind":"todo","title":"Дорого","amount":"-5"}')
say "$([ "$code" = 422 ] && echo y || echo n)" "отрицательная цена отбита ($code)"

# ── галочка на пункте из trip.json
curl -s -b "$JAR" -o "$OUT" -X PATCH "http://127.0.0.1:$PORT/api/entries" \
     -H "content-type: application/json" \
     --data '{"tick":"Поезда::Токио → Киото, 9 января","done":true,"built":false}'
python3 -c "
import json,sys; d=json.load(open('$OUT'))
sys.exit(0 if d['ticks'].get('Поезда::Токио → Киото, 9 января') is True else 1)" \
  && say y "галочка легла в хранилище" || say n "галочка не сохранилась: $(cat "$OUT")"

# ── ПЕРЕСБОРКА: dist/ стирается целиком и собирается заново
echo "— пересобираю страницу (dist/ стирается целиком)"
stop
sleep 1
python3 build.py > /dev/null
say y "страница пересобрана"
start

curl -s -b "$JAR" -o "$OUT" "http://127.0.0.1:$PORT/api/entries"
python3 - "$OUT" <<'PY' && say y "после пересборки все записи и галочка на месте" \
                        || say n "после пересборки что-то потерялось"
import json, sys
d = json.load(open(sys.argv[1]))
kinds = sorted(x["kind"] for x in d.get("entries", []))
titles = {x["title"] for x in d.get("entries", [])}
tick = d.get("ticks", {}).get("Поезда::Токио → Киото, 9 января")
usd = [x for x in d["entries"] if x.get("currency") == "usd"]
free = [x for x in d["entries"] if x.get("amount") is None]
sys.exit(0 if kinds == ["booking", "place", "todo"]
         and "Кофейня у Асакусы" in titles
         and tick is True
         and usd and usd[0]["amount"] == 980
         and free and free[0]["title"] == "Виза" else 1)
PY

# ── и печенье пережило пересборку тоже: пароль тот же, замок тот же
code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/api/entries")
say "$([ "$code" = 401 ] && echo y || echo n)" "после пересборки дверь по-прежнему закрыта ($code)"

# ── убрать за собой: круг не оставляет своих записей в хранилище
ids=$(curl -s -b "$JAR" "http://127.0.0.1:$PORT/api/entries" \
      | python3 -c "import json,sys; print(' '.join(x['id'] for x in json.load(sys.stdin)['entries']))")
for id in $ids; do
  curl -s -b "$JAR" -o /dev/null -X DELETE "http://127.0.0.1:$PORT/api/entries" \
       -H "content-type: application/json" --data "{\"id\":\"$id\"}"
done
curl -s -b "$JAR" -o "$OUT" "http://127.0.0.1:$PORT/api/entries"
python3 -c "
import json,sys; d=json.load(open('$OUT')); sys.exit(0 if d['entries']==[] else 1)" \
  && say y "записи убираются по одной, список снова пуст" || say n "удаление не сработало"

stop
rm -rf "$STATE"
echo
echo "круг: $ok сошлось, $bad не сошлось"
[ "$bad" = 0 ]
