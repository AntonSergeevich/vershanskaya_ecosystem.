from django.contrib.auth.models import AbstractUser
from django.db import models


class CustomUser(AbstractUser):
    """Кастомная модель пользователя"""
    phone = models.CharField("Телефон", max_length=20, blank=True, null=True)
    telegram_id = models.BigIntegerField("Telegram ID", blank=True, null=True, unique=True)
    archetype = models.CharField("Архетип", max_length=100, blank=True, null=True)
    avatar = models.ImageField("Аватар", upload_to="avatars/", blank=True, null=True)
    is_club_member = models.BooleanField("Участник закрытого клуба", default=False)
    created_at = models.DateTimeField("Дата регистрации", auto_now_add=True)

    def __str__(self):
        return f"{self.username} ({self.email or self.phone or 'Нет контактов'})"


class Subscription(models.Model):
    """Модель подписки в closed-клубе (Рекуррентные платежи 2900 ₽/мес)"""
    STATUS_CHOICES = [
        ('active', 'Активна'),
        ('past_due', 'Просрочена'),
        ('canceled', 'Отменена'),
        ('expired', 'Истекла'),
    ]

    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='subscriptions', verbose_name="Пользователь")
    status = models.CharField("Статус", max_length=20, choices=STATUS_CHOICES, default='active')
    amount = models.DecimalField("Сумма", max_digits=10, decimal_places=2, default=2900.00)  # Исправлено на max_digits
    payment_provider = models.CharField("Провайдер платежей", max_length=50, default="YooKassa")
    payment_id = models.CharField("ID транзакции/подписки", max_length=255, blank=True, null=True)
    start_date = models.DateTimeField("Начало подписки", auto_now_add=True)
    next_billing_date = models.DateTimeField("Дата следующего списания")

    class Meta:
        verbose_name = "Подписка"
        verbose_name_plural = "Подписки"

    def __str__(self):
        return f"Подписка #{self.id} — {self.user.username} [{self.status}]"