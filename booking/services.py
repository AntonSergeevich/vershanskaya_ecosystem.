"""Бронирование разборов: захват слота без двойных записей."""
import logging
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from core.services import telegram
from crm import services as crm

from .models import Booking, BookingSlot

logger = logging.getLogger(__name__)


class SlotUnavailable(Exception):
    """Слот успели занять, пока человек заполнял форму."""


@transaction.atomic
def book_slot(user, slot_id, notes=''):
    """Бронирует слот за пользователем.

    select_for_update держит строку до конца транзакции: двое, нажавшие
    «записаться» одновременно, не смогут занять одно окно — второй получит
    SlotUnavailable и вернётся к списку.
    """
    try:
        slot = BookingSlot.objects.select_for_update().get(pk=slot_id)
    except BookingSlot.DoesNotExist:
        raise SlotUnavailable("Этого окна больше нет.")

    if not slot.is_available:
        raise SlotUnavailable("Это время уже заняли. Выберите другое.")

    slot.is_booked = True
    slot.save(update_fields=['is_booked'])

    try:
        booking = Booking.objects.create(user=user, slot=slot, notes=notes)
    except IntegrityError:
        # OneToOne на слоте: страховка на случай гонки в обход блокировки.
        raise SlotUnavailable("Это время уже заняли. Выберите другое.")

    crm.advance_lead(user, 'slot_booked',
                     note=f"Разбор {timezone.localtime(slot.start_time):%d.%m %H:%M}")

    telegram.notify_admins(
        f"📅 <b>Запись на разбор</b>\n{user.display_name}\n"
        f"{timezone.localtime(slot.start_time):%d.%m.%Y %H:%M}\n"
        f"Телефон: {user.phone or '—'}\n"
        # Архетип из квиза — половина контекста встречи ещё до её начала.
        f"Архетип: {user.archetype_label or '—'}\n"
        f"Запрос: {notes or '—'}")
    logger.info("Бронь: %s на %s", user, slot.start_time)
    return booking


@transaction.atomic
def cancel_booking(booking):
    """Отменяет запись и возвращает слот в продажу."""
    if booking.is_canceled:
        return booking
    booking.is_canceled = True
    booking.save(update_fields=['is_canceled'])

    slot = BookingSlot.objects.select_for_update().get(pk=booking.slot_id)
    slot.is_booked = False
    slot.save(update_fields=['is_booked'])

    telegram.notify_admins(
        f"❌ <b>Отмена записи</b>\n{booking.user.display_name} — "
        f"{timezone.localtime(slot.start_time):%d.%m.%Y %H:%M}")
    return booking


def upcoming_slots(limit_days=21):
    """Свободные окна на ближайшие недели, сгруппированные по дням."""
    now = timezone.now()
    horizon = now + timedelta(days=limit_days)
    slots = BookingSlot.objects.filter(
        is_active=True, is_booked=False, start_time__gt=now, start_time__lte=horizon)

    days = {}
    for slot in slots:
        local = timezone.localtime(slot.start_time)
        days.setdefault(local.date(), []).append(slot)
    return [{'date': day, 'slots': items} for day, items in sorted(days.items())]
