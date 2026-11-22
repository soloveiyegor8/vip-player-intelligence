#!/bin/sh
# Полный прогон через Claude API: ключ → пробный диалог → все 40 → метрики → второй проход → итог.
# Запуск из корня проекта: sh scripts/run_claude.sh
set -e
cd "$(dirname "$0")/.."
PY=.venv/bin/python

if [ -z "$ANTHROPIC_API_KEY" ] && ! grep -q '^ANTHROPIC_API_KEY=sk-ant-' .env 2>/dev/null; then
  echo "Ключа нет. Сначала: sh scripts/set_key.sh"
  exit 1
fi

echo "1/4 Пробный диалог D010 — проверка ключа и формата ответа"
$PY -m src.llm --only D010

echo
echo "2/4 Все 40 диалогов (готовые берутся из кэша, повторный запуск бесплатен)"
$PY -m src.llm

echo
echo "3/4 Сравнение с разметкой — без второго прохода"
$PY -m src.eval --source claude | sed -n '5,15p'

echo
echo "4/4 Второй проход-проверка критичных нарушений (7 коротких вопросов на диалог) и итог"
$PY -m src.verify --provider claude
$PY -m src.eval > /dev/null
cat out/eval_compare.md
$PY -m src.export
echo
echo "Подробно по диалогам: out/eval.md. Сайт (docs/) и Streamlit показывают «Claude API» по умолчанию."
echo "Чтобы обновить опубликованный сайт: git add -A && git commit -m 'Прогон Claude API' && git push"
