from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Booking
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
@require_POST
def book(request, pk):
    """Запись на разбор. Слот занимается атомарно — см. services.book_slot."""
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
