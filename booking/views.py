from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from quiz import services as quiz_services

from .models import Booking, BookingSlot
from .services import SlotUnavailable, book_slot, cancel_booking, upcoming_slots


def slots(request):
    """Календарь свободных окон. Виден всем — записаться можно после входа."""
    my_bookings = []
    if request.user.is_authenticated:
        my_bookings = [booking for booking
                       in request.user.bookings.select_related('slot')
                       if booking.is_upcoming]

    return render(request, 'booking/slots.html', {
        'days': upcoming_slots(),
        'my_bookings': my_bookings,
    })


@login_required
def book(request, pk):
    """Подтверждение записи: показываем время и спрашиваем, с чем человек придёт.

    Раньше клик по времени бронировал сразу. Так было на клик быстрее, но
    Екатерина получала «запись на 14:00» без единого слова о запросе, а
    человек не имел шанса передумать.
    """
    slot = get_object_or_404(BookingSlot, pk=pk)

    if request.method != 'POST':
        if not slot.is_available:
            messages.error(request, "Это время уже заняли. Выберите другое.")
            return redirect('booking:slots')
        # Показываем, что Екатерина уже знает из квиза: человеку не нужно
        # пересказывать то, что он уже отвечал, а поле «с чем придёте»
        # перестаёт выглядеть анкетой с чистого листа.
        return render(request, 'booking/confirm.html', {
            'slot': slot,
            'attempt': quiz_services.latest_result(request.user),
        })

    try:
        booking = book_slot(request.user, pk, notes=request.POST.get('notes', '').strip())
    except SlotUnavailable as exc:
        messages.error(request, str(exc))
        return redirect('booking:slots')

    messages.success(
        request,
        "Записали вас на разбор. Напишем в Telegram или позвоним — подтвердим детали.")
    return redirect('booking:detail', pk=booking.pk)


@login_required
def detail(request, pk):
    booking = get_object_or_404(
        Booking.objects.select_related('slot'), pk=pk, user=request.user)
    return render(request, 'booking/detail.html', {'booking': booking})


@login_required
@require_POST
def cancel(request, pk):
    booking = get_object_or_404(Booking, pk=pk, user=request.user)
    cancel_booking(booking)
    messages.success(request, "Запись отменена, время снова свободно.")
    return redirect('booking:slots')
