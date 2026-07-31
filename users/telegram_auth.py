"""Проверка данных от виджета «Войти через Telegram».

Виджет присылает параметры прямо в браузер пользователя, поэтому подделать
их может кто угодно. Единственная защита — подпись: Telegram считает HMAC
от всех полей секретом, производным от токена бота. Кто не знает токен —
не подделает подпись.

Документация: https://core.telegram.org/widgets/login
"""
import hashlib
import hmac
import logging
import time

from django.conf import settings

from .utils import unique_username

logger = logging.getLogger(__name__)

# Данные виджета живут сутки. Более старые отвергаем: иначе перехваченную
# один раз ссылку можно было бы предъявлять сколько угодно.
MAX_AGE_SECONDS = 24 * 60 * 60

# Наши собственные параметры в адресе возврата. Telegram дописывает свои поля
# к тому адресу, который мы указали виджету, и подписывает ТОЛЬКО свои. Если
# оставить ?next= в строке проверки, подпись никогда не сойдётся, и вход с
# любой страницы, кроме голой /vhod/, молча ломается.
OUR_OWN_PARAMS = frozenset({'next'})


def check_signature(data):
    """Проверяет подпись Telegram. Возвращает True, если данным можно верить."""
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.warning("Telegram-вход: токен бота не задан.")
        return False

    received = data.get('hash', '')
    if not received:
        return False

    # Строка проверки: все поля Telegram кроме hash, отсортированные по имени.
    pairs = sorted(f"{key}={value}" for key, value in data.items()
                   if key != 'hash' and key not in OUR_OWN_PARAMS)
    check_string = '\n'.join(pairs)

    secret = hashlib.sha256(settings.TELEGRAM_BOT_TOKEN.encode()).digest()
    expected = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()

    # compare_digest, а не ==: обычное сравнение строк выходит из цикла на
    # первом несовпавшем байте и по времени ответа выдаёт правильный префикс.
    return hmac.compare_digest(expected, received)


def is_fresh(data, now=None):
    """Не устарели ли данные авторизации."""
    try:
        auth_date = int(data.get('auth_date', 0))
    except (TypeError, ValueError):
        return False
    return 0 < (now or time.time()) - auth_date < MAX_AGE_SECONDS


def find_or_create_user(data):
    """Находит пользователя по Telegram ID или заводит нового.

    Порядок поиска важен: сначала по telegram_id (человек уже входил так),
    потом по username из Telegram — так учётка, созданная квизом по нику,
    подхватывается, а не дублируется.
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()

    telegram_id = int(data['id'])
    handle = (data.get('username') or '').strip().lower()

    user = User.objects.filter(telegram_id=telegram_id).first()

    if user is None and handle:
        # Учётка из квиза: там username = ник в Telegram, но id ещё не знали.
        user = User.objects.filter(username__iexact=handle,
                                   telegram_id__isnull=True).first()

    created = False
    if user is None:
        user = User(username=unique_username(handle or f'tg{telegram_id}'))
        user.set_unusable_password()
        created = True

    user.telegram_id = telegram_id
    if not user.first_name:
        user.first_name = (data.get('first_name') or '')[:150]
    if not user.last_name:
        user.last_name = (data.get('last_name') or '')[:150]
    user.save()

    return user, created


def authenticate(data):
    """Полная проверка: подпись, свежесть, поиск пользователя.

    Возвращает (user, created) или (None, False), если данным верить нельзя.
    """
    if not data.get('id'):
        return None, False
    if not check_signature(data):
        logger.warning("Telegram-вход: подпись не сошлась.")
        return None, False
    if not is_fresh(data):
        logger.warning("Telegram-вход: данные устарели.")
        return None, False

    return find_or_create_user(data)
