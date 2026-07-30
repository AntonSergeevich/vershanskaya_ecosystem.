from datetime import timedelta

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

from core.constants import (
    ARCHETYPE_CHOICES,
    ARCHETYPE_DESCRIPTIONS,
    ARCHETYPE_LABELS,
    TIER_CREATOR,
    TIER_LABELS,
    TIER_MAGE,
    TIER_SEEKER,
)

from .utils import normalize_phone


class CustomUser(AbstractUser):
    """Кастомная модель пользователя"""
    # Телефон уникален, потому что служит логином: два аккаунта с одним номером
    # сделали бы вход неоднозначным.
    phone = models.CharField("Телефон", max_length=20, blank=True, null=True, unique=True)
    telegram_id = models.BigIntegerField("Telegram ID", blank=True, null=True, unique=True)
    archetype = models.CharField("Архетип", max_length=20, choices=ARCHETYPE_CHOICES,
                                 blank=True, null=True)
    avatar = models.ImageField("Аватар", upload_to="avatars/", blank=True, null=True)
    is_club_member = models.BooleanField("Участник закрытого клуба", default=False)
    has_personal_guidance = models.BooleanField(
        "Личное ведение («Маг»)", default=False,
        help_text="Ставится вручную после оплаты индивидуальной работы.")
    created_at = models.DateTimeField("Дата регистрации", auto_now_add=True)

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"

    def __str__(self):
        return f"{self.username} ({self.email or self.phone or 'Нет контактов'})"

    def save(self, *args, **kwargs):
        """Приводим телефон к единому виду и пустой храним как NULL.

        Пустая строка нарушила бы unique-ограничение на втором пользователе
        без номера, а разные форматы записи («8912…» и «+7912…») развели бы
        одного человека на два аккаунта.
        """
        self.phone = normalize_phone(self.phone) or None
        super().save(*args, **kwargs)

    # --- Уровень доступа ---------------------------------------------------

    @property
    def tier(self):
        """Текущий уровень: Искатель → Творец → Маг.

        Считается по флагам, а не хранится отдельным полем: иначе флаг и
        уровень рано или поздно разойдутся после ручной правки в админке.
        """
        if self.has_personal_guidance:
            return TIER_MAGE
        if self.is_club_member:
            return TIER_CREATOR
        return TIER_SEEKER

    @property
    def tier_label(self):
        return TIER_LABELS.get(self.tier, '')

    @property
    def has_club_access(self):
        """Доступ к клубному контенту. У сотрудников есть всегда — для проверки."""
        return bool(self.is_club_member or self.has_personal_guidance or self.is_staff)

    @property
    def active_subscription(self):
        """Подписка, которая прямо сейчас даёт доступ.

        Отменённая тоже считается: после отмены клуб остаётся открытым до конца
        оплаченного периода — иначе отмена выглядела бы как потеря денег.
        """
        return (self.subscriptions
                .filter(status__in=['active', 'canceled'], next_billing_date__gt=timezone.now())
                .order_by('-next_billing_date')
                .first())

    # --- Отображение -------------------------------------------------------

    @property
    def display_name(self):
        return self.get_full_name() or self.username

    @property
    def archetype_label(self):
        return ARCHETYPE_LABELS.get(self.archetype, '')

    @property
    def archetype_description(self):
        return ARCHETYPE_DESCRIPTIONS.get(self.archetype, '')


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
    auto_renew = models.BooleanField("Продлевать автоматически", default=True)
    canceled_at = models.DateTimeField("Отменена в", blank=True, null=True)
    start_date = models.DateTimeField("Начало подписки", auto_now_add=True)
    next_billing_date = models.DateTimeField("Дата следующего списания")

    class Meta:
        verbose_name = "Подписка"
        verbose_name_plural = "Подписки"
        ordering = ['-start_date']

    def __str__(self):
        return f"Подписка #{self.id} — {self.user.username} [{self.status}]"

    @property
    def is_active(self):
        """Активна и оплаченный период ещё не закончился."""
        return self.status == 'active' and self.next_billing_date > timezone.now()

    @property
    def days_left(self):
        if not self.next_billing_date:
            return 0
        return max(0, (self.next_billing_date - timezone.now()).days)

    def extend(self, days=30):
        """Продлевает оплаченный период после успешного списания.

        Отсчёт идёт от даты следующего списания, а не от «сейчас», чтобы при
        досрочной оплате не терялись уже оплаченные дни.
        """
        base = max(self.next_billing_date or timezone.now(), timezone.now())
        self.next_billing_date = base + timedelta(days=days)
        # Новая оплата отменяет прошлую отмену: человек передумал.
        self.status = 'active'
        self.auto_renew = True
        self.canceled_at = None
        self.save(update_fields=['next_billing_date', 'status', 'auto_renew', 'canceled_at'])
        return self.next_billing_date

    def cancel(self):
        """Отмена: доступ остаётся до конца оплаченного периода."""
        self.auto_renew = False
        self.status = 'canceled'
        self.canceled_at = timezone.now()
        self.save(update_fields=['auto_renew', 'status', 'canceled_at'])
