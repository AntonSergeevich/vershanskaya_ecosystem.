"""Оплаты и выдача доступа.

Правило: доступ выдаётся ровно в одном месте — grant_access(). Куда бы ни
пришло подтверждение (вебхук, ручная отметка в админке, dev-подтверждение),
дальше путь один и тот же, поэтому расхождений в правах не возникает.
"""
import logging
from datetime import timedelta
from decimal import Decimal

import requests
from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from core.services import telegram
from crm import services as crm
from lms.models import CourseAccess
from users.models import Subscription

from .models import Payment

logger = logging.getLogger(__name__)

YOOKASSA_API = 'https://api.yookassa.ru/v3/payments'
TIMEOUT = 15
SUBSCRIPTION_DAYS = 30


def is_gateway_configured():
    """Настроен ли реальный эквайринг. Если нет — работаем в ручном режиме."""
    if settings.PAYMENT_PROVIDER == 'yookassa':
        return bool(settings.YOOKASSA_SHOP_ID and settings.YOOKASSA_SECRET_KEY)
    if settings.PAYMENT_PROVIDER == 'prodamus':
        return bool(settings.PRODAMUS_FORM_URL)
    return False


# --- Создание платежа -------------------------------------------------------

def create_payment(user, kind, course=None, amount=None):
    """Создаёт запись о платеже и возвращает её вместе со ссылкой на оплату."""
    if kind == Payment.KIND_COURSE:
        if course is None:
            raise ValueError("Для покупки курса нужен сам курс.")
        amount = Decimal(amount if amount is not None else course.price)
    else:
        amount = Decimal(amount if amount is not None else settings.CLUB_PRICE)

    payment = Payment.objects.create(
        user=user,
        kind=kind,
        course=course,
        amount=amount,
        provider=settings.PAYMENT_PROVIDER if is_gateway_configured() else 'manual',
    )
    logger.info("Создан платёж #%s на %s ₽ (%s)", payment.pk, amount, payment.provider)
    return payment


def build_confirmation_url(payment, request):
    """Ссылка, куда отправить человека платить.

    Без настроенного шлюза возвращаем внутреннюю страницу подтверждения —
    так всю воронку можно прокликать на локальной машине.
    """
    return_url = request.build_absolute_uri(
        reverse('payments:success', kwargs={'key': payment.idempotency_key}))

    if not is_gateway_configured():
        payment.confirmation_url = request.build_absolute_uri(
            reverse('payments:manual_confirm', kwargs={'key': payment.idempotency_key}))
        payment.save(update_fields=['confirmation_url'])
        return payment.confirmation_url

    if settings.PAYMENT_PROVIDER == 'prodamus':
        payment.confirmation_url = (
            f"{settings.PRODAMUS_FORM_URL}?order_id={payment.idempotency_key}"
            f"&customer_phone={payment.user.phone or ''}&products[0][price]={payment.amount}"
        )
        payment.save(update_fields=['confirmation_url'])
        return payment.confirmation_url

    return _create_yookassa_payment(payment, return_url)


def _create_yookassa_payment(payment, return_url):
    """Создаёт платёж в ЮKassa и запоминает его id и ссылку на форму."""
    body = {
        'amount': {'value': f"{payment.amount:.2f}", 'currency': 'RUB'},
        'capture': True,
        'confirmation': {'type': 'redirect', 'return_url': return_url},
        'description': payment.title,
        'metadata': {'payment_id': str(payment.pk)},
    }
    if payment.kind == Payment.KIND_CLUB:
        # Сохранённый способ оплаты нужен для ежемесячного автосписания.
        body['save_payment_method'] = True

    try:
        response = requests.post(
            YOOKASSA_API,
            json=body,
            auth=(settings.YOOKASSA_SHOP_ID, settings.YOOKASSA_SECRET_KEY),
            headers={'Idempotence-Key': str(payment.idempotency_key)},
            timeout=TIMEOUT,
        )
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.error("ЮKassa: не удалось создать платёж #%s (%s)", payment.pk, exc)
        return ''

    url = (data.get('confirmation') or {}).get('confirmation_url', '')
    payment.provider_payment_id = data.get('id', '')
    payment.confirmation_url = url
    payment.save(update_fields=['provider_payment_id', 'confirmation_url'])
    if not url:
        logger.error("ЮKassa: ответ без ссылки на оплату: %s", data)
    return url


def fetch_remote_status(payment):
    """Спрашивает у ЮKassa настоящий статус платежа.

    Вебхуку на слово не верим: тело запроса может подделать кто угодно, кто
    знает адрес. Источник истины — ответ API по id платежа.
    """
    if not (is_gateway_configured() and settings.PAYMENT_PROVIDER == 'yookassa'
            and payment.provider_payment_id):
        return ''
    try:
        response = requests.get(
            f"{YOOKASSA_API}/{payment.provider_payment_id}",
            auth=(settings.YOOKASSA_SHOP_ID, settings.YOOKASSA_SECRET_KEY),
            timeout=TIMEOUT,
        )
        return response.json().get('status', '')
    except (requests.RequestException, ValueError) as exc:
        logger.error("ЮKassa: не удалось проверить платёж #%s (%s)", payment.pk, exc)
        return ''


# --- Выдача доступа ---------------------------------------------------------

@transaction.atomic
def grant_access(payment, provider_payment_id=''):
    """Единственная точка выдачи доступа после успешной оплаты.

    Возвращает True, если это первое подтверждение (значит, доступ выдан
    только что), и False на повторных вебхуках.
    """
    if not payment.mark_succeeded(provider_payment_id):
        return False

    if payment.kind == Payment.KIND_COURSE and payment.course:
        CourseAccess.objects.get_or_create(
            user=payment.user, course=payment.course,
            defaults={'comment': f"оплата #{payment.pk}"})
        crm.advance_lead(payment.user, 'form_filled',
                         note=f"Купил курс «{payment.course.title}»")
        telegram.notify_admins(
            f"💳 <b>Оплата курса</b>\n{payment.user.display_name} — "
            f"«{payment.course.title}», {payment.amount} ₽")
        return True

    _activate_club(payment)
    return True


def _activate_club(payment):
    """Продлевает или заводит подписку и открывает клуб."""
    user = payment.user
    subscription = user.active_subscription
    if subscription is None:
        subscription = Subscription.objects.create(
            user=user,
            amount=payment.amount,
            payment_provider=payment.provider,
            payment_id=payment.provider_payment_id,
            next_billing_date=timezone.now() + timedelta(days=SUBSCRIPTION_DAYS),
        )
    else:
        subscription.extend(SUBSCRIPTION_DAYS)

    payment.subscription = subscription
    payment.save(update_fields=['subscription'])

    if not user.is_club_member:
        user.is_club_member = True
        user.save(update_fields=['is_club_member'])

    crm.advance_lead(user, 'subscribed', note=f"Оплата клуба #{payment.pk}")

    invite = telegram.create_club_invite_link(user.display_name)
    if invite and user.telegram_id:
        telegram.send_message(
            user.telegram_id,
            f"Добро пожаловать в клуб «Творец» 🌿\nВаша ссылка в закрытый чат: {invite}")
    telegram.notify_admins(
        f"💎 <b>Оплата клуба</b>\n{user.display_name} — {payment.amount} ₽\n"
        f"Активна до {subscription.next_billing_date:%d.%m.%Y}")


def revoke_club_access(user):
    """Закрывает клуб, когда подписка истекла. Вызывается командой expire_subscriptions."""
    if user.is_club_member:
        user.is_club_member = False
        user.save(update_fields=['is_club_member'])
    telegram.remove_from_club_chat(user.telegram_id)
    logger.info("Клубный доступ закрыт: %s", user)


def expire_subscriptions(now=None):
    """Переводит просроченные подписки в expired и снимает доступ.

    Возвращает число закрытых подписок — удобно для вывода в cron-логе.
    """
    now = now or timezone.now()
    # «canceled» здесь тоже нужен: отменённая подписка доживает оплаченный
    # период, и снять доступ надо именно в момент её окончания.
    stale = Subscription.objects.filter(
        status__in=['active', 'past_due', 'canceled'],
        next_billing_date__lt=now).select_related('user')

    closed = 0
    for subscription in stale:
        subscription.status = 'expired'
        subscription.save(update_fields=['status'])
        # Доступ снимаем, только если у человека не осталось другой живой подписки.
        if subscription.user.active_subscription is None:
            revoke_club_access(subscription.user)
        closed += 1
    return closed
