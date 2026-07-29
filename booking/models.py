from django.db import models
from django.conf import settings

class BookingSlot(models.Model):
    """Слоты времени для консультаций и разборов"""
    start_time = models.DateTimeField("Время начала")
    end_time = models.DateTimeField("Время окончания")
    is_booked = models.BooleanField("Забронирован", default=False)

    class Meta:
        verbose_name = "Слот для записи"
        verbose_name_plural = "Слоты для записи"
        ordering = ['start_time']

    def __str__(self):
        status = "Занят" if self.is_booked else "Свободен"
        return f"{self.start_time.strftime('%d.%m.%Y %H:%M')} ({status})"


class Booking(models.Model):
    """Заявка на проведение разбора"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bookings', verbose_name="Клиент")
    slot = models.OneToOneField(BookingSlot, on_delete=models.CASCADE, verbose_name="Слот")
    zoom_link = models.URLField("Ссылка на Zoom / Google Meet", blank=True, null=True)
    notes = models.TextField("Заметки к встрече / Запрос клиента", blank=True, null=True)
    is_completed = models.BooleanField("Разбор проведен", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Запись на разбор"
        verbose_name_plural = "Записи на разборы"

    def __str__(self):
        return f"Запись: {self.user.username} на {self.slot.start_time.strftime('%d.%m %H:%M')}"