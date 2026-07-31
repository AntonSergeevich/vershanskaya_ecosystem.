"""Проверка на человека для открытых форм.

Три уровня, от невидимого к заметному:

1. Ловушка — поле, спрятанное стилями. Человек его не видит и не заполняет,
   а бот заполняет всё, что найдёт в разметке.
2. Секунды — форму подписываем временем показа. Скрипт отправляет её за
   миллисекунды, человеку нужно хотя бы дотянуться до кнопки.
3. Счётчик по адресу — сколько отправок с одного IP за час.

Этого хватает против массовых рассылок, и главное — не стоит человеку ни
одного лишнего клика. Настоящая капча (Яндекс SmartCaptcha) подключается
ключами в .env и включается сама, когда они появятся: она нужна только
если пойдёт целевой спам, который эти три уровня не ловят.
"""
import logging
import time

from django import forms
from django.conf import settings
from django.core import signing
from django.core.cache import cache

logger = logging.getLogger(__name__)

HONEYPOT = 'website'
STAMP = 'form_stamp'

# Порог нарочно низкий. Скрипт отправляет форму за десятки миллисекунд, и
# полутора секунд хватает, чтобы его отсечь. Ставить «5 секунд для верности»
# нельзя: с автозаполнением браузера человек успевает отправить форму почти
# сразу, и мы потеряем живого клиента ради бота, которого и так поймает
# ловушка. Медленнее суток — форма пролежала открытой, метка протухла.
MIN_SECONDS = 1.5
MAX_AGE = 60 * 60 * 24

SALT = 'core.antibot'


def make_stamp(at=None):
    """Подписанная метка времени показа формы.

    at позволяет подставить своё время — это нужно тестам, чтобы отправить
    форму «через десять секунд после показа», не засыпая на десять секунд.
    """
    return signing.dumps({'t': at if at is not None else time.time()}, salt=SALT)


def human_post(data=None, seconds_ago=10):
    """Поля формы, как их прислал бы живой человек. Для тестов."""
    return {**(data or {}), STAMP: make_stamp(time.time() - seconds_ago)}


def stamp_age(value):
    """Сколько секунд прошло с показа формы. None — метке верить нельзя.

    Срок жизни считаем по своей метке, а не через max_age у loads: тот
    смотрит на время подписи, и получалось две разные точки отсчёта —
    возраст по одной, протухание по другой.
    """
    try:
        data = signing.loads(value, salt=SALT)
    except signing.BadSignature:
        return None

    try:
        age = time.time() - float(data['t'])
    except (KeyError, TypeError, ValueError):
        return None

    # Метка из будущего — переведённые часы или подделка.
    return None if age < 0 or age > MAX_AGE else age


def client_ip(request):
    """IP клиента. За nginx настоящий адрес приходит в X-Forwarded-For."""
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded:
        # Первый в списке — клиент, остальные прокси по пути.
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def too_many(request, action, limit=20, window=3600):
    """Не превышен ли лимит отправок с этого адреса.

    Считаем в кэше: в проде он общий для всех процессов (см. CACHES), и
    лимит получается настоящий, а не «по лимиту на каждый воркер».

    Лимиты нарочно высокие. У мобильных операторов за одним адресом сидят
    тысячи людей, и порог «5 в час» рано или поздно отрежет живого человека
    за чужие действия. Задача здесь — поймать поток в сотни отправок, а не
    пятого посетителя с того же оператора; штучный спам ловят ловушка и
    секунды, а против целевого есть капча.
    """
    ip = client_ip(request)
    if not ip:
        return False

    key = f"antibot:{action}:{ip}"
    # add ставит значение только если ключа не было — так окно начинает
    # отсчёт с первой попытки и не продлевается на каждой следующей.
    if cache.add(key, 1, window):
        return False

    try:
        count = cache.incr(key)
    except ValueError:
        # Ключ успел истечь между add и incr — считаем это первой попыткой.
        return False

    if count > limit:
        logger.warning("Антибот: %s превысил лимит «%s» (%s за %s c)",
                       ip, action, count, window)
        return True
    return False


# --- Настоящая капча (необязательная) ---------------------------------------

def captcha_enabled():
    return bool(settings.SMARTCAPTCHA_KEY and settings.SMARTCAPTCHA_SECRET)


def captcha_passed(token, ip=''):
    """Проверяет ответ Яндекс SmartCaptcha на своей стороне.

    Проверять надо именно на сервере: значение из формы присылает браузер,
    и без обращения к Яндексу его можно просто подставить.
    """
    import requests

    if not token:
        return False
    try:
        response = requests.get(
            'https://smartcaptcha.yandexcloud.net/validate',
            params={'secret': settings.SMARTCAPTCHA_SECRET, 'token': token, 'ip': ip},
            timeout=5,
        )
        return response.json().get('status') == 'ok'
    except Exception as exc:
        # Сознательно пропускаем: если у Яндекса перебои, лучше принять
        # несколько ботов, чем не принять ни одного живого человека.
        logger.error("SmartCaptcha недоступна (%s) — пропускаем проверку.", exc)
        return True


class HumanCheckMixin:
    """Подмешивается к форме и добавляет ловушку, метку времени и капчу.

    Ошибку показываем общую и не объясняющую: подсказка «вы заполнили
    скрытое поле» — это инструкция, как обойти проверку.
    """

    human_error = "Не получилось отправить форму. Обновите страницу и попробуйте ещё раз."

    def __init__(self, *args, request=None, **kwargs):
        # request нужен только капче: Яндексу полезно знать адрес клиента.
        # Без него проверка тоже работает, просто чуть менее точно.
        self.request = request
        super().__init__(*args, **kwargs)

        self.fields[HONEYPOT] = forms.CharField(
            required=False, label="Не заполняйте это поле",
            widget=forms.TextInput(attrs={
                'class': 'trap', 'tabindex': '-1', 'autocomplete': 'off',
                'aria-hidden': 'true',
            }))
        self.fields[STAMP] = forms.CharField(
            required=False, widget=forms.HiddenInput(), initial=make_stamp)

        if captcha_enabled():
            self.fields['smart-token'] = forms.CharField(
                required=False, widget=forms.HiddenInput())

    def clean(self):
        cleaned = super().clean()

        if cleaned.get(HONEYPOT):
            logger.warning("Антибот: заполнена ловушка в %s", type(self).__name__)
            raise forms.ValidationError(self.human_error)

        age = stamp_age(cleaned.get(STAMP) or '')
        if age is None or age < MIN_SECONDS:
            logger.warning("Антибот: форма %s отправлена за %s c",
                           type(self).__name__, age)
            raise forms.ValidationError(self.human_error)

        ip = client_ip(self.request) if self.request else ''
        if captcha_enabled() and not captcha_passed(cleaned.get('smart-token'), ip):
            raise forms.ValidationError(
                "Проверка не пройдена. Отметьте, что вы не робот, и попробуйте ещё раз.")

        return cleaned
