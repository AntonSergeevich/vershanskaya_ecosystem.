"""Приём оплат через GetPlatinum.

Про этот модуль важно понимать одно: у меня не было их технической
документации, когда я его писал. Поэтому здесь нет ни одного выдуманного
адреса эндпоинта и ни одной выдуманной схемы подписи — вместо этого
сделано так, чтобы интеграция работала при любом наборе имён полей, а всё
непонятное честно останавливалось и звало человека.

Как это устроено.

Ссылка на оплату. Берём ссылку на форму из кабинета GetPlatinum и
дописываем к ней номер заказа и сумму. Имена параметров задаются в .env —
если в кабинете они называются иначе, это правка одной строки, а не кода.

Номер заказа. Это наш UUID (Payment.idempotency_key). Он уникален и ни на
что не похож, поэтому в уведомлении мы находим его перебором значений, не
зная, как называется поле. Это снимает главную неопределённость.

Подтверждение оплаты. Адрес уведомления содержит длинный секрет
(/webhook/getplatinum/<секрет>/), который знают только мы и GetPlatinum, —
это и есть проверка подлинности, пока не известна их схема подписи.
Дополнительно сверяем сумму.

Решение о выдаче доступа. Принимается, только если в уведомлении нашёлся
явный признак успеха. Если признак неизвестен — доступ НЕ выдаём, а пишем
Екатерине в Telegram с перечнем полей уведомления: настроить правило
GETPLATINUM_SUCCESS_FIELD одной строкой можно после первой же реальной
оплаты. Молча открыть клуб по неоплаченному счёту хуже, чем один раз
подтвердить оплату руками.
"""
import json
import logging
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from django.conf import settings

logger = logging.getLogger(__name__)

# Значения, которые платёжные сервисы обычно шлют при успешной оплате.
# Используются, пока GETPLATINUM_SUCCESS_FIELD не задан явно.
SUCCESS_WORDS = {'success', 'succeeded', 'successful', 'paid', 'payed',
                 'completed', 'complete', 'confirmed', 'done', 'ok',
                 'оплачен', 'оплачено', 'успешно'}

# Значения, которые точно означают «денег нет». Нужны отдельным списком:
# иначе незнакомое слово пришлось бы считать отказом, и если у GetPlatinum
# успех называется как-то по-своему, каждая реальная оплата молча
# пропадала бы. Незнакомое значение — повод спросить человека, а не решать.
FAILURE_WORDS = {'fail', 'failed', 'failure', 'declined', 'decline',
                 'canceled', 'cancelled', 'rejected', 'error', 'expired',
                 'pending', 'waiting', 'new', 'created',
                 'отказ', 'отклонен', 'отменен', 'ошибка', 'ожидание'}

# Как обычно называется поле со статусом. Только для подсказки в логе и
# для режима «правило не настроено».
STATUS_HINTS = ('status', 'state', 'payment_status', 'paymentstatus',
                'result', 'event', 'статус')

AMOUNT_HINTS = ('amount', 'sum', 'summ', 'price', 'total', 'сумма')


def is_configured():
    return bool(settings.GETPLATINUM_FORM_URL and settings.GETPLATINUM_WEBHOOK_SECRET)


# --- Ссылка на оплату -------------------------------------------------------

def payment_url(payment, return_url=''):
    """Ссылка на форму оплаты с нашим номером заказа и суммой."""
    parts = urlparse(settings.GETPLATINUM_FORM_URL)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))

    query[settings.GETPLATINUM_ORDER_PARAM] = str(payment.idempotency_key)
    query[settings.GETPLATINUM_AMOUNT_PARAM] = f"{payment.amount:.2f}"
    if settings.GETPLATINUM_DESCRIPTION_PARAM:
        query[settings.GETPLATINUM_DESCRIPTION_PARAM] = payment.title
    if return_url and settings.GETPLATINUM_RETURN_PARAM:
        query[settings.GETPLATINUM_RETURN_PARAM] = return_url
    if payment.user.phone and settings.GETPLATINUM_PHONE_PARAM:
        query[settings.GETPLATINUM_PHONE_PARAM] = payment.user.phone

    return urlunparse(parts._replace(query=urlencode(query)))


# --- Разбор уведомления -----------------------------------------------------

def parse_body(request):
    """Тело уведомления как плоский словарь.

    Сервис может слать и JSON, и обычную форму — разбираем оба варианта,
    вложенность разворачиваем в «родитель.потомок».
    """
    content_type = request.META.get('CONTENT_TYPE', '')

    if 'json' in content_type:
        try:
            data = json.loads(request.body or b'{}')
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None
    else:
        data = request.POST.dict()
        if not data:
            # Иногда JSON приходит без правильного заголовка.
            try:
                data = json.loads(request.body or b'{}')
            except (json.JSONDecodeError, UnicodeDecodeError):
                return None

    return flatten(data) if isinstance(data, dict) else None


def flatten(data, prefix=''):
    flat = {}
    for key, value in data.items():
        name = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            flat.update(flatten(value, name))
        elif isinstance(value, list):
            flat[name] = ','.join(str(item) for item in value)
        else:
            flat[name] = value
    return flat


def find_order_key(data, known_keys):
    """Ищет наш номер заказа среди значений уведомления.

    Перебором, а не по имени поля: UUID уникален и ни с чем не спутается,
    зато имя поля в каждом сервисе своё.
    """
    for value in data.values():
        candidate = str(value).strip().lower()
        if candidate in known_keys:
            return candidate
    return None


def find_amount(data):
    """Сумма из уведомления, если её удалось узнать."""
    for key, value in data.items():
        if any(hint in key.lower() for hint in AMOUNT_HINTS):
            try:
                return Decimal(str(value).replace(',', '.').replace(' ', ''))
            except (InvalidOperation, AttributeError):
                continue
    return None


def is_success(data):
    """Успешная ли это оплата.

    Возвращает True, False или None. None значит «не понял» — и тогда
    доступ не выдаётся, а зовётся человек.
    """
    field = settings.GETPLATINUM_SUCCESS_FIELD
    if field:
        # Правило настроено — верим только ему.
        value = str(data.get(field, '')).strip().lower()
        return value in success_values()

    # Правило не настроено: угадываем только то, что узнали наверняка.
    # Сравниваем значение целиком, а не по вхождению: подстрока «success»
    # есть и в «unsuccessful», а «paid» — в «not_paid».
    for key, value in data.items():
        if not any(hint in key.lower() for hint in STATUS_HINTS):
            continue
        word = str(value).strip().lower()
        if word in SUCCESS_WORDS:
            return True
        if word in FAILURE_WORDS:
            return False

    return None


def success_values():
    configured = {value.strip().lower()
                  for value in settings.GETPLATINUM_SUCCESS_VALUES.split(',')
                  if value.strip()}
    return configured or SUCCESS_WORDS
