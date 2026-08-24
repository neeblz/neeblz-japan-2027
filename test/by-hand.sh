#!/usr/bin/env bash
# Поднять настоящий сайт с настоящей KV и пройти его руками.
#
#     ./test/by-hand.sh
#
# `round.sh` доказывает то же самое через ручку, `hands.py` — через браузер.
# Разница не в тщательности, а в том, что между ручкой и её руками лежит вся
# страница: разметка, скрипт, свёртки, перетаскивание. Ломается обычно она.
#
# Сервер поднимается здесь, а не внутри `hands.py`, по той же причине, по
# которой сборка и браузер не ходят парой: у хоста 7.7 ГБ и нет подкачки, и
# конвейер «собрать → поднять → проверить» надёжнее, чем «всё сразу».
#
# Хранилище — своё, вне `dist/`, и стирается в начале: круг обязан начинаться
# с пустого, а не с чужого.
set -euo pipefail

cd "$(dirname "$0")/.."

PORT=8974
STATE="$PWD/.wrangler/hand-state"
PW="proba-ruk-$RANDOM$RANDOM"
LOG=$(mktemp)

kill_tree() {
  local pid=$1 child
  [ -n "${pid:-}" ] && [ -d "/proc/$pid" ] || return 0
  for child in $(pgrep -P "$pid" 2>/dev/null); do kill_tree "$child"; done
  kill "$pid" 2>/dev/null || true
  local i; for i in 1 2 3; do [ -d "/proc/$pid" ] || return 0; sleep 1; done
  kill -9 "$pid" 2>/dev/null || true
}

ROOT=""
# Хранилище стирается **после** того, как сервер умер, а не до: живой wrangler
# пишет своё состояние обратно и переживает уборку. Так и вышло в первый раз —
# `hand-state` остался на диске после зелёного прогона.
cleanup() { kill_tree "$ROOT"; rm -rf "$STATE"; rm -f "$LOG"; }
trap cleanup EXIT

if ss -lptn "sport = :$PORT" 2>/dev/null | grep -q "pid="; then
  echo "✗ порт $PORT занят — прибери прошлый прогон" >&2; exit 1
fi

rm -rf "$STATE"
python3 build.py > /dev/null

(cd dist && timeout 420 npx wrangler pages dev . --port "$PORT" --ip 127.0.0.1 \
    --binding "JAPAN_PASSWORD=$PW" --kv JAPAN_KV --persist-to "$STATE" \
    >>"$LOG" 2>&1) &
ROOT=$!
for i in $(seq 1 45); do
  curl -s -o /dev/null -m 2 "http://127.0.0.1:$PORT/" && break
  sleep 1
  [ "$i" = 45 ] && { echo "✗ wrangler не поднялся:" >&2; tail -8 "$LOG" >&2; exit 1; }
done

set +e
../.venv-shot/bin/python3 test/hands.py --url "http://127.0.0.1:$PORT" --password "$PW"
code=$?
set -e

exit $code   # хранилище уберёт `cleanup`, когда сервер уже не сможет его вернуть
