"""Точка входа для Beget (обычный хостинг, Passenger).

Скопируйте этот файл в корень сайта на хостинге — туда, куда Beget смотрит
как на «директорию Python-приложения». Passenger сам импортирует из него
переменную `application`.

Если у вас VPS с root-доступом, этот файл не нужен: там приложение поднимает
gunicorn (см. gunicorn.service).
"""
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Passenger запускает файл с чужим рабочим каталогом, поэтому путь к проекту
# добавляем руками — иначе `import config` не найдётся.
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

from django.core.wsgi import get_wsgi_application  # noqa: E402  (после sys.path)

application = get_wsgi_application()
