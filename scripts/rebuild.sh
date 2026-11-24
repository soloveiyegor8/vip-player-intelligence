#!/bin/sh
# Бесплатная пересборка после правки кода: модель не вызывается, ответы берутся из кэша.
# Подхватывает изменения порогов, серьёзности флагов, приоритетов, действий и правил-страховок.
# Запуск из корня проекта: sh scripts/rebuild.sh
set -e
cd "$(dirname "$0")/.."
PY=.venv/bin/python

for p in claude ollama; do
  if ls out/llm"$( [ $p = ollama ] && echo _ollama )"/D*.json >/dev/null 2>&1; then
    $PY -m src.llm --provider $p --assemble
  fi
done
[ -f out/manual/raw.json ] && $PY -m src.llm --provider manual
$PY -m src.eval > /dev/null
$PY -m src.export
echo
echo "Локально: обновите страницу http://localhost:8600 (сервер: .venv/bin/python -m http.server 8600 --directory docs)"
echo "На сайт: git add -A && git commit -m 'Правка' && git push   (обновится через 1-2 минуты)"
