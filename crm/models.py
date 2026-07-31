from django.db import models
from django.conf import settings


class LeadQuerySet(models.QuerySet):
    def clients(self):
        """Только настоящие клиенты, без Екатерины и других сотрудников.

        Екатерина заходит на свой же сайт: проходит квиз, чтобы посмотреть,
        как он выглядит, записывается на тестовый разбор. Каждое такое
        действие заводило ей лид и портило и доску, и конверсию.
        """
        return self.filter(user__is_staff=False)


class CRMLead(models.Model):
    """Воронка продаж / Лид в Канбан-доске"""
    STAGE_CHOICES = [
        ('new', 'Новый лид'),
        ('form_filled', 'Анкета заполнена'),
        ('slot_booked', 'Слот забронирован'),
        ('session_done', 'Разбор проведен'),
        ('subscribed', 'Подписка оформлена'),
        ('closed_lost', 'Отказ / Закрыто'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='crm_leads', verbose_name="Клиент")
    stage = models.CharField("Этап воронки", max_length=20, choices=STAGE_CHOICES, default='new')
    source = models.CharField("Источник трафика", max_length=100, default="Telegram") # Telegram, Instagram, Сарафанное радио
    notes = models.TextField("Заметки менеджера", blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = LeadQuerySet.as_manager()

    class Meta:
        verbose_name = "Лид CRM"
        verbose_name_plural = "Лиды CRM"

    def __str__(self):
        return f"Лид: {self.user.username} — Этап: {self.get_stage_display()}"


class Campaign(models.Model):
    """Модель для Telegram/SMS рассылок и прогрева"""
    title = models.CharField("Название компании", max_length=255)
    message_text = models.TextField("Текст сообщения")
    target_stage = models.CharField("Целевой этап лида", max_length=20, choices=CRMLead.STAGE_CHOICES, blank=True, null=True)
    sent_at = models.DateTimeField("Время отправки", blank=True, null=True)
    is_sent = models.BooleanField("Отправлено", default=False)

    class Meta:
        verbose_name = "Рассылка"
        verbose_name_plural = "Рассылки"

    def __str__(self):
        return self.title