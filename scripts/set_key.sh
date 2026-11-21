#!/bin/sh
# Сохраняет ключ Anthropic API в .env проекта. Ключ не отображается при вводе и не попадает в историю.
cd "$(dirname "$0")/.." || exit 1
printf 'Вставьте ключ Anthropic API (символы не видны) и нажмите Enter: '
stty -echo
read -r KEY
stty echo
printf '\n'
case "$KEY" in
  sk-ant-*) ;;
  *) echo "Это не похоже на ключ Anthropic (он начинается с sk-ant-). Ничего не сохранено."; exit 1 ;;
esac
umask 077
printf 'ANTHROPIC_API_KEY=%s\n' "$KEY" > .env
echo "Готово: ключ сохранён в .env. Можно вернуться в чат."
