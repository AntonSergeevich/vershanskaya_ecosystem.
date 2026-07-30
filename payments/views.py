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

from . import services
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
