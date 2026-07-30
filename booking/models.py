from django.conf import settings
from django.db import models
from django.utils import timezone


class BookingSlot(models.Model):
    """Слоты времени для консультаций и разборов"""
    start_time = models.DateTimeField("Время начала")
    end_time = models.DateTimeField("Время окончания")
    is_booked = models.BooleanField("Забронирован", default=False)
    is_active = models.BooleanField("Показывать на сайте", default=True,
                                    help_text="Снимите галочку, чтобы временно убрать окно.")

    class Meta:
        verbose_name = "Слот для записи"
        verbose_name_plural = "Слоты для записи"
        ordering = ['start_time']
        constraints = [
            # Два окна на одно время — верный способ записать двоих на один разбор.
            models.UniqueConstraint(fields=['start_time'], name='booking_unique_slot_start'),
        ]

    def __str__(self):
        status = "Занят" if self.is_booked else "Свободен"
        return f"{self.start_time.strftime('%d.%m.%Y %H:%M')} ({status})"

    @property
    def duration_minutes(self):
        return int((self.end_time - self.start_time).total_seconds() // 60)

    @property
    def is_past(self):
        return self.start_time <= timezone.now()

    @property
    def is_available(self):
        return self.is_active and not self.is_booked and not self.is_past


class Booking(models.Model):
    """Заявка на проведение разбора"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bookings', verbose_name="Клиент")
    # Не OneToOne: после отмены то же окно должно снова продаваться.
    # Уникальность держим ниже — только среди неотменённых записей.
    slot = models.ForeignKey(BookingSlot, on_delete=models.CASCADE, related_name='bookings',
                             verbose_name="Слот")
    zoom_link = models.URLField("Ссылка на Zoom / Google Meet", blank=True, null=True)
    notes = models.TextField("Заметки к встрече / Запрос клиента", blank=True, null=True)
    is_completed = models.BooleanField("Разбор проведен", default=False)
    is_canceled = models.BooleanField("Отменена", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Запись на разбор"
        verbose_name_plural = "Записи на разборы"
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['slot'], condition=models.Q(is_canceled=False),
                                    name='booking_unique_active_slot'),
        ]

    def __str__(self):
        return f"Запись: {self.user.username} на {self.slot.start_time.strftime('%d.%m %H:%M')}"

    @property
    def is_upcoming(self):
        return not self.is_canceled and not self.is_completed and not self.slot.is_past
