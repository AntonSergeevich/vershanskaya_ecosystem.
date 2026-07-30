"""
Django settings for the Vershanskaya Ecosystem project.

Все секреты читаются из окружения (.env). Смотрите .env.example.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Читаем .env до обращения к os.getenv
load_dotenv(BASE_DIR / '.env')


def env_bool(name, default=False):
    return os.getenv(name, str(default)).strip().lower() in ('1', 'true', 'yes', 'on')


def env_list(name, default=''):
    return [item.strip() for item in os.getenv(name, default).split(',') if item.strip()]


DEBUG = env_bool('DEBUG', True)

# В разработке допускаем небезопасный ключ по умолчанию, в проде — падаем, если ключа нет.
SECRET_KEY = os.getenv('SECRET_KEY') or ('django-insecure-dev-key-change-me' if DEBUG else '')
if not SECRET_KEY:
    raise RuntimeError('SECRET_KEY не задан. Добавьте его в .env перед запуском с DEBUG=False.')

ALLOWED_HOSTS = env_list('ALLOWED_HOSTS', 'localhost,127.0.0.1,[::1]' if DEBUG else '')
CSRF_TRUSTED_ORIGINS = env_list('CSRF_TRUSTED_ORIGINS')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',

    # Сторонние библиотеки
    'rest_framework',

    # Наши сервисы
    'core.apps.CoreConfig',
    'users.apps.UsersConfig',
    'crm.apps.CrmConfig',
    'quiz.apps.QuizConfig',
    'lms.apps.LmsConfig',
    'booking.apps.BookingConfig',
    'payments.apps.PaymentsConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.brand',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# База данных: PostgreSQL, если заданы переменные, иначе SQLite для быстрой разработки.
if os.getenv('POSTGRES_DB'):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.getenv('POSTGRES_DB'),
            'USER': os.getenv('POSTGRES_USER', 'postgres'),
            'PASSWORD': os.getenv('POSTGRES_PASSWORD', ''),
            'HOST': os.getenv('POSTGRES_HOST', 'localhost'),
            'PORT': os.getenv('POSTGRES_PORT', '5432'),
            'CONN_MAX_AGE': 60,
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'ru-ru'
TIME_ZONE = 'Asia/Krasnoyarsk'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {
        # Манифест с хешами нужен только в проде: в разработке он требовал бы
        # collectstatic после каждой правки CSS.
        'BACKEND': ('django.contrib.staticfiles.storage.StaticFilesStorage' if DEBUG
                    else 'whitenoise.storage.CompressedManifestStaticFilesStorage'),
    },
}

# Пути для сохранения медиа-файлов (обложек, аватаров) — раздаются напрямую.
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Видео уроков лежат ВНЕ MEDIA_ROOT: их нельзя получить по прямой ссылке,
# только через lms.views.lesson_video, который проверяет уровень доступа.
PROTECTED_MEDIA_ROOT = Path(os.getenv('PROTECTED_MEDIA_ROOT', BASE_DIR / 'protected_media'))

# Если раздачей файлов занимается nginx, включите X-Accel-Redirect: Django
# только проверит доступ, а тяжёлый файл отдаст веб-сервер.
PROTECTED_MEDIA_USE_NGINX = env_bool('PROTECTED_MEDIA_USE_NGINX', False)
PROTECTED_MEDIA_NGINX_LOCATION = os.getenv('PROTECTED_MEDIA_NGINX_LOCATION', '/protected-media/')

# Максимальный размер загружаемого видео (500 МБ)
DATA_UPLOAD_MAX_MEMORY_SIZE = 524288000
FILE_UPLOAD_MAX_MEMORY_SIZE = 524288000

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_USER_MODEL = 'users.CustomUser'

LOGIN_URL = 'users:enter'
LOGIN_REDIRECT_URL = 'lms:dashboard'
LOGOUT_REDIRECT_URL = 'core:landing'

# --- Настройки экосистемы ---------------------------------------------------

# Цена подписки в закрытый клуб «Творец» (₽/мес)
CLUB_PRICE = int(os.getenv('CLUB_PRICE', '2900'))

# Интеграции. Пустые значения = режим заглушки (dev), платежи подтверждаются вручную.
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_BOT_USERNAME = os.getenv('TELEGRAM_BOT_USERNAME', '')
TELEGRAM_CLUB_CHAT_ID = os.getenv('TELEGRAM_CLUB_CHAT_ID', '')
TELEGRAM_ADMIN_CHAT_ID = os.getenv('TELEGRAM_ADMIN_CHAT_ID', '')
TELEGRAM_CHANNEL_URL = os.getenv('TELEGRAM_CHANNEL_URL', 'https://t.me/ekaterinavershanskaya')
INSTAGRAM_URL = os.getenv('INSTAGRAM_URL', 'https://www.instagram.com/ekaterina_arhetypes/')

PAYMENT_PROVIDER = os.getenv('PAYMENT_PROVIDER', 'yookassa')
YOOKASSA_SHOP_ID = os.getenv('YOOKASSA_SHOP_ID', '')
YOOKASSA_SECRET_KEY = os.getenv('YOOKASSA_SECRET_KEY', '')
PRODAMUS_FORM_URL = os.getenv('PRODAMUS_FORM_URL', '')

# Безопасность за реверс-прокси (включается только в проде)
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = env_bool('SECURE_SSL_REDIRECT', True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    X_FRAME_OPTIONS = 'DENY'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    # LOG_LEVEL=WARNING заглушает шум воронки при прогоне тестов.
    'root': {'handlers': ['console'], 'level': os.getenv('LOG_LEVEL', 'INFO').upper()},
}
