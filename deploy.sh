#!/usr/bin/env bash
# Выложить страницу Японии — с замком, а не «надеюсь, замок поехал».
#
#     python3 build.py && ./deploy.sh
#
# Почему скрипт, а не одна команда wrangler. 19 августа 2026 вишлист три
# минуты стоял открытым, потому что `wrangler pages deploy dist-cf` собирает
# `functions/` из **текущего** каталога, а не из выкладываемой папки. Каталога
# рядом не было, wrangler промолчал и выложил сайт без функций. А дверь — это
# функции.
#
# Отсюда правила, зашитые ниже:
#   1. заходим внутрь собранной папки и выкладываем «.»;
#   2. в выводе обязана быть строка про Functions bundle — нет её, значит замок
#      остался дома, и выкладка останавливается;
#   3. сначала дверь поднимается на localhost той же связкой функций — и её
#      там ломают: без печенья 401, с неверным паролем 401, с верным открывается.
#      Это заменило проверочную ветку: у нового проекта Pages несколько минут
#      нет сертификата на вложенные поддомены, и проверка падала бы с ошибкой
#      TLS, а не с «двери нет» — то есть на пустом месте. Localhost от DNS и
#      сертификатов не зависит вовсе, а функции берёт из той же папки.
#   4. на боевой — десять заходов и чистый адрес. Один заход ничего не значит:
#      край Cloudflare отвечает разными узлами. А `?knock=1` уходит мимо кэша
#      края, тогда как Ни открывает страницу без хвоста.
set -euo pipefail

cd "$(dirname "$0")"

# Только репетиция, без выкладки: ./deploy.sh --rehearse
# Дверь и ручка проверяются на localhost той же связкой функций — это стоит
# секунд и не трогает боевую.
REHEARSE=""
if [ "${1:-}" = "--rehearse" ]; then REHEARSE=1; shift; fi

DIR=${1:-dist}
PROJECT=japan-2027
LIVE_BRANCH=main
LIVE_HOST="https://japan-2027-eti.pages.dev"
WORKDIR=..

[ -d "$DIR/functions" ]   || { echo "✗ в «$DIR» нет functions/ — пересобери build.py" >&2; exit 1; }
[ -f "$DIR/_routes.json" ] || { echo "✗ в «$DIR» нет _routes.json — дверь не встанет на пути" >&2; exit 1; }
[ -f "$WORKDIR/.japan-password" ] || { echo "✗ пароля нет на диске — не с чем сверять" >&2; exit 1; }

export CLOUDFLARE_API_TOKEN="${CLOUDFLARE_API_TOKEN:-$(cat "$WORKDIR/.cloudflare-token")}"
export CLOUDFLARE_ACCOUNT_ID="${CLOUDFLARE_ACCOUNT_ID:-$(cat "$WORKDIR/.cloudflare-account")}"

deploy() {  # ветка → вывод wrangler
  local branch=$1 out
  out=$(cd "$DIR" && timeout 240 npx wrangler pages deploy . \
        --project-name "$PROJECT" --branch "$branch" --commit-dirty=true 2>&1) || true
  printf '%s\n' "$out"
  grep -q "Functions bundle" <<<"$out" \
    || { echo "✗ wrangler не собрал функции — замок остался дома, выкладка остановлена" >&2; exit 1; }
}

knocked() {  # адрес → «сколько заходов из десяти попросили пароль»
  local host=$1 got=0 i code
  for i in $(seq 1 10); do
    code=$(curl -s -o /dev/null -w '%{http_code}' "$host/?knock=$i" || echo 000)
    [ "$code" = "401" ] && got=$((got + 1))
  done
  echo "$got"
}

opens() {  # адрес → «пускает ли правильный пароль» (и виден ли за ним текст)
  local host=$1 jar body pwfile
  jar=$(mktemp); body=$(mktemp); pwfile=$(mktemp)
  chmod 600 "$pwfile"

  # Обрезанная копия, а не сам файл: `--data-urlencode "имя@файл"` отправляет
  # содержимое целиком, вместе с переводом строки в конце, — и дверь честно
  # отбивает пароль с хвостом. 23 августа это выглядело как «замок сломан»
  # ровно тогда, когда замок был исправен. Значение не идёт аргументом, чтобы
  # не всплыть в списке процессов.
  tr -d '\n' < "$WORKDIR/.japan-password" > "$pwfile"

  curl -s -o /dev/null -c "$jar" -b "$jar" -X POST "$host/login" \
       --data-urlencode "password@$pwfile" --data "next=/" >/dev/null || true
  curl -s -b "$jar" "$host/" -o "$body" || true
  local ok=no
  grep -q "Моридзуя" "$body" && ok=yes
  rm -f "$jar" "$body" "$pwfile"
  echo "$ok"
}

kill_tree() {  # pid → снять его и всё, что он породил, до конца
  local pid=$1 child
  [ -n "$pid" ] && [ -d "/proc/$pid" ] || return 0
  for child in $(pgrep -P "$pid" 2>/dev/null); do
    kill_tree "$child"
  done
  kill "$pid" 2>/dev/null || true
  # workerd не умирает по TERM: 23 августа такая сирота прожила шестнадцать
  # минут и продолжала слушать порт со старым паролем — репетиция мигала через
  # раз и выглядела как «замок сломался сам по себе». Добиваем.
  local i
  for i in 1 2 3; do
    [ -d "/proc/$pid" ] || return 0
    sleep 1
  done
  kill -9 "$pid" 2>/dev/null || true
}

port_free() {  # порт → «свободен ли», с попыткой прибрать своё же старое
  local port=$1 i pid top
  for i in 1 2 3 4 5 6; do
    pid=$(ss -lptn "sport = :$port" 2>/dev/null | grep -oP 'pid=\K[0-9]+' | head -1)
    [ -z "$pid" ] && return 0

    # Убивать слушателя бесполезно: порт держит `workerd`, а node над ним
    # поднимает его заново — 23 августа так родились две сироты подряд, и
    # `kill -9` по слушателю честно отработал вхолостую шесть раз. Поэтому
    # идём вверх до самого верхнего предка, который всё ещё наш wrangler,
    # и валим оттуда. Чужой процесс на этом порту не трогаем вовсе.
    top=$(topmost_wrangler "$pid") || {
      echo "  ✗ порт $port занят посторонним (pid $pid)" >&2
      return 1
    }
    kill_tree "$top"
    kill -9 "$top" 2>/dev/null || true
    sleep 2
  done
  return 1
}

topmost_wrangler() {  # pid → самый верхний предок, всё ещё принадлежащий wrangler
  local pid=$1 top="" cmd parent
  while [ -n "$pid" ] && [ "$pid" != "1" ] && [ -d "/proc/$pid" ]; do
    cmd=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null)
    case "$cmd" in
      *wrangler*|*workerd*|*"npm exec"*) top=$pid ;;
      *) break ;;
    esac
    # Родитель — не четвёртое поле: имя процесса в /proc/pid/stat стоит в
    # скобках и бывает с пробелами («npm exec wrangl»), и тогда $4 — это
    # «wrangl)», а не число. Обход останавливался на полпути, порт оставался
    # занятым осиротевшим workerd, и выкладка отказывалась стартовать на
    # пустом месте. Читаем то, что после последней скобки: state, потом ppid.
    parent=$(sed 's/.*) //' "/proc/$pid/stat" 2>/dev/null | awk '{print $2}')
    pid=$parent
  done
  [ -n "$top" ] || return 1
  printf '%s\n' "$top"
}


# ── дверь на localhost, до всякой выкладки ────────────────────────────────
#
# Гасится через `kill_tree` по своему же PID, а не `pkill`: шаблон `-f wrangler`
# есть в командной строке самой этой оболочки и убил бы вызвавшего, а `-x` не
# сработает — `comm` обрезан до 15 знаков («npm exec wrangl»).
local_door() {
  # Пароль репетиции — латиница нарочно: кириллица не переживает дорогу через
  # `wrangler --binding`, и дверь начинает отбивать верный пароль. Проверяем
  # механизм, а не алфавит; настоящий пароль в `.japan-password` тоже латинский.
  local port=8971 pw="proba-dveri-$RANDOM$RANDOM" log jar code ok=0

  # Занятый порт — не мелочь: на нём мог остаться сервер прошлого прогона со
  # своим паролем, и тогда репетиция проверяет не то, что собрали сейчас.
  port_free "$port" || { echo "  ✗ не удалось освободить порт $port" >&2; return 1; }

  log=$(mktemp); jar=$(mktemp)

  # KV поднимается своя, на диске и во временной папке: репетиция не должна
  # ни читать её записи, ни тем более их править.
  local store; store=$(mktemp -d)
  (cd "$DIR" && timeout 120 npx wrangler pages dev . --port "$port" --ip 127.0.0.1 \
      --binding "JAPAN_PASSWORD=$pw" --kv JAPAN_KV --persist-to "$store" >"$log" 2>&1) &
  local root=$!

  local i
  for i in $(seq 1 40); do
    curl -s -o /dev/null -m 2 "http://127.0.0.1:$port/" && break
    sleep 1
  done

  code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$port/")
  [ "$code" = "401" ] && ok=$((ok + 1)) || echo "  ✗ закрытая страница ответила $code вместо 401" >&2

  code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "http://127.0.0.1:$port/login" \
         --data "password=не-тот&next=/")
  [ "$code" = "401" ] && ok=$((ok + 1)) || echo "  ✗ неверный пароль ответил $code вместо 401" >&2

  curl -s -o /dev/null -c "$jar" -b "$jar" -X POST "http://127.0.0.1:$port/login" \
       --data-urlencode "password=$pw" --data "next=/"

  # Сначала в файл, потом grep — а не `curl | grep -q`. При `set -o pipefail`
  # такой конвейер падает **оттого, что совпадение нашлось**: grep -q выходит
  # на первом же попадании, закрывает трубу, curl получает SIGPIPE и возвращает
  # ненулевой код, который pipefail поднимает наверх. 23 августа это трижды
  # выглядело как «замок отбивает верный пароль», хотя wrangler в тот же миг
  # писал в лог «POST /login 303» и «GET / 200 OK». Гонка, поэтому и мигало.
  local page
  page=$(mktemp)
  curl -s -b "$jar" -o "$page" "http://127.0.0.1:$port/" || true
  if grep -q "Моридзуя" "$page"; then
    ok=$((ok + 1))
  else
    echo "  ✗ верный пароль не открыл страницу" >&2
  fi
  rm -f "$page"

  # Ручка, которой Ни вносит записи, закрыта той же дверью — и это надо
  # проверить, а не предположить: своего замка у неё нет нарочно.
  code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$port/api/entries")
  [ "$code" = "401" ] && ok=$((ok + 1)) \
    || echo "  ✗ ручка записей без печенья ответила $code вместо 401" >&2

  local answer
  answer=$(mktemp)
  curl -s -b "$jar" -o "$answer" "http://127.0.0.1:$port/api/entries" || true
  if grep -q '"ok":true' "$answer"; then
    ok=$((ok + 1))
  else
    echo "  ✗ с паролем ручка записей не ответила списком: $(head -c 120 "$answer")" >&2
  fi
  rm -f "$answer"

  kill_tree "$root"
  rm -rf "$store"
  if [ "$ok" != "5" ]; then
    echo "  — последние строки wrangler:" >&2
    tail -6 "$log" | sed 's/^/    /' >&2
  fi
  rm -f "$log" "$jar"

  [ "$ok" = "5" ]
}

echo "— дверь на localhost"
local_door || { echo "✗ дверь не держит ещё до выкладки — на боевую не пускаю" >&2; exit 1; }
echo "✓ дверь на localhost: закрыта, неверный пароль отбит, верный открывает,"
echo "  ручка записей закрыта без печенья и отвечает списком с ним"

if [ -n "$REHEARSE" ]; then
  echo "✓ репетиция и только репетиция — на боевую не ходил"
  exit 0
fi

echo "— боевая"
deploy "$LIVE_BRANCH" | tail -3
sleep 12
got=$(knocked "$LIVE_HOST")
[ "$got" = "10" ] || { echo "✗ ДВЕРЬ НА БОЕВОЙ НЕ ОТВЕЧАЕТ: 401 получили $got из 10 — откатывай немедленно" >&2; exit 1; }

# Чистый адрес — тот, что откроет Ни. `?knock=` ходит мимо края и однажды уже
# скрыл удалённую страницу, отвечавшую 200 тридцать один час.
clean=$(curl -s -o /dev/null -w '%{http_code}' "$LIVE_HOST/")
[ "$clean" = "401" ] || { echo "✗ чистый адрес отвечает $clean вместо 401" >&2; exit 1; }
echo "✓ дверь на боевой: 10 из 10, чистый адрес тоже"

[ "$(opens "$LIVE_HOST")" = "yes" ] \
  || { echo "✗ замок закрыт и для Ни: правильный пароль не открывает страницу" >&2; exit 1; }
echo "✓ правильный пароль открывает — выложено: $LIVE_HOST"

# Хранилище её записей — привязка `JAPAN_KV` в панели Cloudflare, и ставит её
# человек, а не эта выкладка. Поэтому здесь не отказ, а слова: страница без
# привязки работает и честно говорит «не сохранилось», но записывать в неё
# нельзя, и знать об этом нужно сразу, а не от Ни.
store_says() {
  local host=$1 jar body pwfile out
  jar=$(mktemp); body=$(mktemp); pwfile=$(mktemp); chmod 600 "$pwfile"
  tr -d '\n' < "$WORKDIR/.japan-password" > "$pwfile"
  curl -s -o /dev/null -c "$jar" -b "$jar" -X POST "$host/login" \
       --data-urlencode "password@$pwfile" --data "next=/" >/dev/null || true
  curl -s -b "$jar" -o "$body" "$host/api/entries" || true
  out=$(head -c 200 "$body")
  rm -f "$jar" "$body" "$pwfile"
  printf '%s\n' "$out"
}
said=$(store_says "$LIVE_HOST")
case "$said" in
  *'"ok":true'*) echo "✓ хранилище на месте: записей $(printf '%s' "$said" | grep -o '"id"' | wc -l)" ;;
  *"не настроено"*) echo "⚠ привязки JAPAN_KV на проекте нет — страница открывается, но её записи сохранить некуда" ;;
  *) echo "⚠ ручка записей ответила непонятным: $said" ;;
esac
