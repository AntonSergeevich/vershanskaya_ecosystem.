import hmac
import json
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from core.models import FAQItem, Testimonial
from core.services import telegram
from lms.models import Course

from . import getplatinum, services
from .models import Payment

logger = logging.getLogger(__name__)


def club(request):
    """Страница клуба «Творец»: что внутри, сколько стоит, кнопка оплаты."""
    return render(request, 'payments/club.html', {
        'price': settings.CLUB_PRICE,
        'testimonials': Testimonial.objects.filter(is_published=True),
        'faq': FAQItem.objects.filter(is_published=True),
        'club_courses': Course.objects.filter(is_published=True, access_level='club')[:6],
        'subscription': (request.user.active_subscription
                         if request.user.is_authenticated else None),
    })


@login_required
@require_POST
def checkout(request):
    """Создаёт платёж и отправляет на форму оплаты."""
    kind = request.POST.get('kind', Payment.KIND_CLUB)

    course = None
    if kind == Payment.KIND_COURSE:
        course = get_object_or_404(Course, slug=request.POST.get('course'), is_published=True)
        if course.is_available_for(request.user):
            messages.info(request, "Этот курс у вас уже открыт.")
            return redirect(course)

    payment = services.create_payment(request.user, kind, course=course)
    url = services.build_confirmation_url(payment, request)
    if not url:
        payment.mark_canceled()
        messages.error(request, "Платёжный сервис не отвечает. Попробуйте ещё раз чуть позже.")
        return redirect('payments:club')
    return HttpResponseRedirect(url)


@login_required
def success(request, key):
    """Возврат с формы оплаты.

    Вебхук может прийти позже, чем человек вернётся на сайт, поэтому здесь
    ещё раз спрашиваем у шлюза настоящий статус — чтобы не показывать
    «ожидаем оплату» тому, кто уже заплатил.
    """
    payment = get_object_or_404(Payment, idempotency_key=key, user=request.user)

    if not payment.is_paid and services.fetch_remote_status(payment) == 'succeeded':
        services.grant_access(payment)
        payment.refresh_from_db()

    return render(request, 'payments/success.html', {'payment': payment})


@login_required
def manual_confirm(request, key):
    """Подтверждение оплаты без эквайринга.

    Нужно в двух случаях: локальная разработка и приём денег переводом, когда
    факт оплаты подтверждает человек. Как только шлюз настроен, страница
    закрывается — иначе это была бы дыра «оплати сам себе».
    """
    if services.is_gateway_configured() and not request.user.is_staff:
        raise Http404

    payment = get_object_or_404(Payment, idempotency_key=key)
    if payment.user != request.user and not request.user.is_staff:
        raise Http404

    if request.method == 'POST':
        if services.grant_access(payment):
            messages.success(request, "Оплата подтверждена, доступ открыт.")
        return redirect('payments:success', key=payment.idempotency_key)

    return render(request, 'payments/manual_confirm.html', {'payment': payment})


@csrf_exempt
@require_POST
def webhook(request):
    """Уведомление от платёжного шлюза.

    Тело запроса берём только как подсказку «посмотри на этот платёж»:
    решение о выдаче доступа принимаем после запроса статуса в API.
    """
    try:
        body = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        return HttpResponse(status=400)

    obj = body.get('object') or {}
    provider_id = obj.get('id', '')
    local_id = (obj.get('metadata') or {}).get('payment_id')

    payment = None
    if provider_id:
        payment = Payment.objects.filter(provider_payment_id=provider_id).first()
    if payment is None and local_id:
        payment = Payment.objects.filter(pk=local_id).first()
    if payment is None:
        logger.warning("Вебхук: платёж не найден (%s / %s)", provider_id, local_id)
        # 200, чтобы шлюз не долбился повторами в несуществующий платёж.
        return HttpResponse(status=200)

    if not payment.provider_payment_id and provider_id:
        payment.provider_payment_id = provider_id
        payment.save(update_fields=['provider_payment_id'])

    status = services.fetch_remote_status(payment) or obj.get('status', '')
    if status == 'succeeded':
        services.grant_access(payment, provider_payment_id=provider_id)
    elif status == 'canceled':
        payment.mark_canceled()

    return HttpResponse(status=200)


@login_required
@require_POST
def cancel_subscription(request):
    """Отмена автопродления. Доступ остаётся до конца оплаченного периода."""
    subscription = request.user.active_subscription
    if subscription is None:
        messages.info(request, "Активной подписки нет.")
    else:
        subscription.cancel()
        # Отмена — это сигнал к действию: человек ещё внутри, и с ним
        # можно поговорить до конца оплаченного периода.
        telegram.notify_admins(
            f"⚠️ <b>Отключено продление</b>\n{request.user.display_name}\n"
            f"Телефон: {request.user.phone or '—'}\n"
            f"Клуб открыт до {subscription.next_billing_date:%d.%m.%Y}")
        messages.success(
            request,
            "Автопродление отключено. Клуб остаётся открытым до "
            f"{subscription.next_billing_date:%d.%m.%Y}.")
    return redirect('users:profile')


@csrf_exempt
@require_POST
def getplatinum_webhook(request, secret):
    """Уведомление об оплате от GetPlatinum.

    Подлинность подтверждает секрет в самом адресе: его знают только мы и
    GetPlatinum (он указывается в их кабинете). Когда появится описание их
    подписи, проверку можно будет ужесточить, не трогая остальное.

    Отвечаем 200 почти всегда: на 4xx и 5xx сервисы шлют повторы, а нам
    повтор не поможет — проблема не в сети, а в содержимом.
    """
    if not hmac.compare_digest(secret, settings.GETPLATINUM_WEBHOOK_SECRET or '\x00'):
        logger.warning("GetPlatinum: уведомление с чужим секретом в адресе.")
        raise Http404

    data = getplatinum.parse_body(request)
    if data is None:
        logger.error("GetPlatinum: не разобрал тело уведомления.")
        return HttpResponse(status=400)

    pending = {str(key).lower(): pk for key, pk in
               Payment.objects.exclude(status=Payment.STATUS_CANCELED)
                              .values_list('idempotency_key', 'pk')}
    order = getplatinum.find_order_key(data, pending)

    if order is None:
        logger.warning("GetPlatinum: не нашёл наш номер заказа. Поля: %s",
                       ', '.join(sorted(data)))
        telegram.notify_admins(
            "⚠️ <b>Оплата пришла, но заказ не найден</b>\n"
            f"Поля уведомления: {', '.join(sorted(data)) or '—'}\n"
            "Проверьте GETPLATINUM_ORDER_PARAM в .env.")
        return HttpResponse(status=200)

    payment = Payment.objects.get(pk=pending[order])

    # Сумма: если она в уведомлении есть и не сошлась — это либо чужой
    # платёж, либо ошибка в ссылке. В обоих случаях доступ не выдаём.
    amount = getplatinum.find_amount(data)
    if amount is not None and amount != payment.amount:
        logger.error("GetPlatinum: сумма не сошлась (%s вместо %s) по платежу #%s",
                     amount, payment.amount, payment.pk)
        telegram.notify_admins(
            f"🚫 <b>Сумма оплаты не сошлась</b>\n{payment.user.display_name}\n"
            f"Пришло {amount} ₽ вместо {payment.amount} ₽. Доступ не выдан.")
        return HttpResponse(status=200)

    outcome = getplatinum.is_success(data)

    if outcome is None:
        # Правило успеха ещё не настроено. Открывать клуб наугад нельзя:
        # уведомление может быть и об отказе.
        logger.warning("GetPlatinum: не понял статус платежа #%s. Поля: %s",
                       payment.pk, ', '.join(sorted(data)))
        telegram.notify_admins(
            f"❓ <b>Уведомление об оплате, статус непонятен</b>\n"
            f"{payment.user.display_name} — {payment.amount} ₽\n"
            f"Поля: {', '.join(sorted(data))}\n"
            "Доступ пока не выдан. Подтвердите вручную и пропишите "
            "GETPLATINUM_SUCCESS_FIELD в .env.")
        return HttpResponse(status=200)

    if outcome:
        services.grant_access(payment)
    else:
        logger.info("GetPlatinum: платёж #%s не прошёл.", payment.pk)

    return HttpResponse(status=200)
