"""Тонкая обёртка над Telegram Bot API.

Если TELEGRAM_BOT_TOKEN не задан (обычный случай на локальной машине),
функции ничего не отправляют, а пишут сообщение в лог. Так весь остальной код
может дёргать уведомления, не проверяя каждый раз, настроена ли интеграция.
"""
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

API_ROOT = 'https://api.telegram.org/bot{token}/{method}'
TIMEOUT = 10


def is_configured():
    return bool(settings.TELEGRAM_BOT_TOKEN)


def _call(method, payload):
    """Вызывает метод Bot API. Возвращает результат или None при ошибке.

    Уведомления — не критичный путь: упавший Telegram не должен ломать
    оплату или прохождение квиза, поэтому исключения только логируются.
    """
    if not is_configured():
        logger.info("Telegram (заглушка) %s: %s", method, payload)
        return None

    url = API_ROOT.format(token=settings.TELEGRAM_BOT_TOKEN, method=method)
    try:
        response = requests.post(url, json=payload, timeout=TIMEOUT)
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Telegram: метод %s не выполнен (%s)", method, exc)
        return None

    if not data.get('ok'):
        logger.warning("Telegram: метод %s вернул ошибку: %s", method, data.get('description'))
        return None
    return data.get('result')


def send_message(chat_id, text, disable_notification=False):
    """Отправляет сообщение в чат (личный или групповой)."""
    if not chat_id:
        return None
    return _call('sendMessage', {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML',
        'disable_web_page_preview': True,
        'disable_notification': disable_notification,
    })


def notify_admins(text):
    """Сообщение эксперту: новый лид, оплата, запись на разбор."""
    return send_message(settings.TELEGRAM_ADMIN_CHAT_ID, text)


def create_club_invite_link(name=''):
    """Одноразовая ссылка-приглашение в закрытый чат клуба.

    Ограничение в одну заявку не даёт переслать ссылку знакомым:
    после первого входа она перестаёт работать.
    """
    if not settings.TELEGRAM_CLUB_CHAT_ID:
        return ''
    result = _call('createChatInviteLink', {
        'chat_id': settings.TELEGRAM_CLUB_CHAT_ID,
        'name': (name or 'Участник клуба')[:32],
        'member_limit': 1,
        'creates_join_request': False,
    })
    return (result or {}).get('invite_link', '')


def remove_from_club_chat(telegram_id):
    """Убирает из закрытого чата, когда подписка перестала действовать.

    Сразу же снимаем бан, иначе человек не сможет вернуться после оплаты.
    """
    if not (settings.TELEGRAM_CLUB_CHAT_ID and telegram_id):
        return None
    result = _call('banChatMember', {
        'chat_id': settings.TELEGRAM_CLUB_CHAT_ID,
        'user_id': telegram_id,
    })
    _call('unbanChatMember', {
        'chat_id': settings.TELEGRAM_CLUB_CHAT_ID,
        'user_id': telegram_id,
        'only_if_banned': True,
    })
    return result
