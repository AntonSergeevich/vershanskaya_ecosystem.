#!/usr/bin/env bash
# Выкатка новой версии на сервер.
#
#   cd /srv/vershanskaya && ./deploy/update.sh
#
# Скрипт намеренно останавливается на первой же ошибке: половина применённой
# выкатки хуже, чем невыкаченная.
set -euo pipefail

cd "$(dirname "$0")/.."
PYTHON=venv/bin/python

echo "→ Забираю изменения"
git pull --ff-only

echo "→ Обновляю зависимости"
venv/bin/pip install -q -r requirements.txt

echo "→ Проверяю, что миграции не забыты"
# --check падает, если в моделях есть изменения без миграции: лучше узнать
# об этом здесь, чем поймать 500 на проде.
$PYTHON manage.py makemigrations --check --dry-run

echo "→ Применяю миграции"
$PYTHON manage.py migrate --noinput

echo "→ Проверяю таблицу кэша"
# Кэш держит счётчик отправок форм. Команда идемпотентна: если таблица уже
# есть, она просто скажет об этом и ничего не сломает.
$PYTHON manage.py createcachetable

echo "→ Собираю статику"
$PYTHON manage.py collectstatic --noinput

echo "→ Проверяю конфигурацию"
$PYTHON manage.py check --deploy

echo "→ Перезапускаю приложение"
if systemctl is-active --quiet vershanskaya; then
    sudo systemctl restart vershanskaya
else
    # На хостинге с Passenger перезапуск делается касанием этого файла.
    mkdir -p tmp && touch tmp/restart.txt
fi

echo "✓ Готово"
