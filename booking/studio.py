"""Расписание — рабочее место Екатерины для окон под разборы.

Раньше окна создавались только командой в терминале, а закрыть день можно
было лишь через админку. Здесь всё на одной странице: видно, что занято,
что свободно и что спрятано, и любое окно переключается одной кнопкой.
"""
from datetime import date, datetime, time, timedelta

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.decorators import staff_required

from .models import Booking, BookingSlot
from .services import generate_slots

# Сколько дней показываем за раз. Две недели — обычный горизонт записи.
WINDOW_DAYS = 14

WEEKDAY_NAMES = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']


def parse_date(value, default):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return default


def parse_time(value, default):
    try:
        hours, minutes = value.split(':')
        return time(int(hours), int(minutes))
    except (TypeError, ValueError, AttributeError):
        return default


def parse_number(value, default, maximum=None):
    """Число из формы. Мусор вместо цифр не должен ронять страницу в 500."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    if number < 1:
        return default
    return min(number, maximum) if maximum else number


@staff_required
def schedule(request):
    """Две недели окон: занято, свободно, скрыто — и кто записан."""
    today = timezone.localdate()
    start = max(parse_date(request.GET.get('ot'), today), today)
    finish = start + timedelta(days=WINDOW_DAYS)

    slots = BookingSlot.objects.filter(
        start_time__gte=timezone.make_aware(datetime.combine(start, time.min)),
        start_time__lt=timezone.make_aware(datetime.combine(finish, time.min)),
    )

    # Кто записан — по неотменённым записям. Одним запросом, чтобы список
    # окон не превратился в запрос на строку.
    booked = {
        booking.slot_id: booking
        for booking in Booking.objects.filter(slot__in=slots, is_canceled=False)
                                      .select_related('user', 'slot')
    }

    days = {}
    for slot in slots:
        local = timezone.localtime(slot.start_time)
        days.setdefault(local.date(), []).append({
            'slot': slot,
            'booking': booked.get(slot.id),
            'is_past': slot.is_past,
        })

    return render(request, 'booking/studio/schedule.html', {
        'days': [
            {
                'date': day,
                'weekday': WEEKDAY_NAMES[day.weekday()],
                'is_weekend': day.weekday() >= 5,
                'slots': items,
            }
            for day, items in sorted(days.items())
        ],
        'start': start,
        'previous': max(start - timedelta(days=WINDOW_DAYS), today),
        'following': start + timedelta(days=WINDOW_DAYS),
        'has_previous': start > today,
        'today': today,
        'weekday_names': list(enumerate(WEEKDAY_NAMES)),
        'free_total': sum(1 for slot in slots if slot.is_available),
        'booked_total': len(booked),
    })


@staff_required
@require_POST
def slot_toggle(request, pk):
    """Скрыть окно или вернуть его в продажу.

    Не удаляем: спрятанное окно можно вернуть одним кликом, а удалённое
    придётся заводить заново.
    """
    slot = BookingSlot.objects.filter(pk=pk).first()
    if slot is None:
        messages.error(request, "Окна больше нет.")
    elif slot.is_booked:
        # Спрятать занятое окно нечестно: человек уже записан и ждёт.
        messages.error(request, "На это время уже записаны. Сначала отмените запись.")
    else:
        slot.is_active = not slot.is_active
        slot.save(update_fields=['is_active'])

    return redirect(_back(request))


@staff_required
@require_POST
def slot_delete(request, pk):
    slot = BookingSlot.objects.filter(pk=pk).first()
    if slot is None:
        messages.error(request, "Окна больше нет.")
    elif slot.is_booked:
        # Удаление утащило бы за собой и запись клиента.
        messages.error(request, "На это время записан человек — удалять нельзя.")
    else:
        slot.delete()

    return redirect(_back(request))


@staff_required
@require_POST
def day_toggle(request, day):
    """Закрыть или открыть целый день — «в субботу не работаю»."""
    target = parse_date(day, None)
    if target is None:
        messages.error(request, "Не понял дату.")
        return redirect('booking:schedule')

    slots = BookingSlot.objects.filter(
        start_time__gte=timezone.make_aware(datetime.combine(target, time.min)),
        start_time__lt=timezone.make_aware(datetime.combine(target + timedelta(days=1),
                                                            time.min)),
        is_booked=False)

    # Первый клик закрывает день, второй открывает: пока осталось хоть одно
    # открытое окно, кнопка закрывает. Обратное правило («открыть, если хоть
    # одно спрятано») давало бы «День открыт» там, где Екатерина только что
    # спрятала одно окно из двенадцати.
    opening = not slots.filter(is_active=True).exists()
    changed = slots.update(is_active=opening)

    if changed:
        messages.success(request, "День открыт." if opening else "День закрыт.")
    else:
        messages.error(request, "В этот день нет свободных окон.")
    return redirect(_back(request))


@staff_required
@require_POST
def slot_add(request):
    """Одно окно вне общего расписания — «приму в воскресенье в 11»."""
    day = parse_date(request.POST.get('date'), None)
    moment = parse_time(request.POST.get('time'), None)
    duration = parse_number(request.POST.get('duration'), 30, maximum=480)

    if day is None or moment is None:
        messages.error(request, "Укажите дату и время.")
        return redirect(_back(request))

    start = timezone.make_aware(datetime.combine(day, moment))
    if start <= timezone.now():
        messages.error(request, "Это время уже прошло.")
        return redirect(_back(request))

    try:
        # atomic вокруг одного запроса — это точка сохранения: после
        # IntegrityError откатывается только она. Без неё пойманная ошибка
        # оставляет всю транзакцию сломанной, и следующий же запрос падает.
        with transaction.atomic():
            BookingSlot.objects.create(start_time=start,
                                       end_time=start + timedelta(minutes=duration))
    except IntegrityError:
        # На start_time стоит уникальность: два окна на одно время — это
        # два человека на один разбор.
        messages.error(request, "Окно на это время уже есть.")
        return redirect(_back(request))

    messages.success(request, "Окно добавлено.")
    return redirect(_back(request))


@staff_required
@require_POST
def slots_generate(request):
    """Нарезать окна на период — то же, что делала команда в терминале."""
    try:
        weekdays = {int(value) for value in request.POST.getlist('weekdays')}
    except ValueError:
        weekdays = None

    if not weekdays:
        messages.error(request, "Отметьте хотя бы один день недели.")
        return redirect(_back(request))

    try:
        created, existed = generate_slots(
            days=parse_number(request.POST.get('days'), 14, maximum=90),
            start_time=parse_time(request.POST.get('from'), time(10, 0)),
            end_time=parse_time(request.POST.get('to'), time(18, 0)),
            duration=parse_number(request.POST.get('duration'), 30, maximum=480),
            weekdays=weekdays,
            start_date=parse_date(request.POST.get('start'), timezone.localdate()),
        )
    except (ValueError, TypeError) as exc:
        messages.error(request, str(exc) or "Проверьте время начала и конца.")
        return redirect(_back(request))

    if created:
        messages.success(request, f"Добавлено окон: {created}."
                                  + (f" Уже было: {existed}." if existed else ""))
    else:
        messages.error(request, "Новых окон не появилось — на это время они уже есть.")
    return redirect(_back(request))


def _back(request):
    """Возврат на тот же участок расписания, а не всегда на сегодня.

    Дату разбираем, а не подставляем как есть: в адрес уходит только то,
    что действительно оказалось датой.
    """
    url = reverse('booking:schedule')
    start = parse_date(request.POST.get('ot') or request.GET.get('ot'), None)
    return f"{url}?ot={start}" if start else url
