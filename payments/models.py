import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class Payment(models.Model):
    """Одна попытка оплаты — клуба или отдельного курса.

    Запись создаётся до похода в платёжный шлюз: если человек не вернулся с
    формы оплаты, у нас всё равно остаётся след «пытался купить» — это самый
    горячий сегмент для догрева.
    """
    KIND_CLUB = 'club'
    KIND_COURSE = 'course'
    KIND_CHOICES = [
        (KIND_CLUB, 'Подписка на клуб «Творец»'),
        (KIND_COURSE, 'Разовая покупка курса'),
    ]

    STATUS_PENDING = 'pending'
    STATUS_SUCCEEDED = 'succeeded'
    STATUS_CANCELED = 'canceled'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Ожидает оплаты'),
        (STATUS_SUCCEEDED, 'Оплачен'),
        (STATUS_CANCELED, 'Отменён'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name='payments', verbose_name="Плательщик")
    kind = models.CharField("Что оплачивается", max_length=20, choices=KIND_CHOICES,
                            default=KIND_CLUB)
    course = models.ForeignKey('lms.Course', on_delete=models.SET_NULL, blank=True, null=True,
                               related_name='payments', verbose_name="Курс")
    amount = models.DecimalField("Сумма", max_digits=10, decimal_places=2)
    status = models.CharField("Статус", max_length=20, choices=STATUS_CHOICES,
                              default=STATUS_PENDING)
    provider = models.CharField("Провайдер", max_length=50, default='manual')
    provider_payment_id = models.CharField("ID платежа у провайдера", max_length=255,
                                           blank=True, db_index=True)
    # Ключ идемпотентности: защищает от двойного списания при повторной отправке
    # формы и служит секретом в ссылке возврата.
    idempotency_key = models.UUIDField("Ключ идемпотентности", default=uuid.uuid4,
                                       unique=True, editable=False)
    confirmation_url = models.URLField("Ссылка на оплату", blank=True)
    subscription = models.ForeignKey('users.Subscription', on_delete=models.SET_NULL,
                                     blank=True, null=True, related_name='payments',
                                     verbose_name="Подписка")
    created_at = models.DateTimeField("Создан", auto_now_add=True)
    paid_at = models.DateTimeField("Оплачен в", blank=True, null=True)

    class Meta:
        verbose_name = "Платёж"
        verbose_name_plural = "Платежи"
        ordering = ['-created_at']

    def __str__(self):
        return f"Платёж #{self.pk} — {self.user} — {self.amount} ₽ [{self.get_status_display()}]"

    @property
    def is_paid(self):
        return self.status == self.STATUS_SUCCEEDED

    @property
    def title(self):
        if self.kind == self.KIND_COURSE and self.course:
            return f"Курс «{self.course.title}»"
        return 'Подписка на клуб «Творец»'

    def mark_succeeded(self, provider_payment_id=''):
        """Отмечает оплату успешной. Повторный вызов ничего не меняет.

        Идемпотентность здесь обязательна: платёжные шлюзы шлют вебхук
        несколько раз, и второй заход не должен продлевать подписку дважды.
        """
        if self.is_paid:
            return False
        self.status = self.STATUS_SUCCEEDED
        self.paid_at = timezone.now()
        if provider_payment_id:
            self.provider_payment_id = provider_payment_id
        self.save(update_fields=['status', 'paid_at', 'provider_payment_id'])
        return True

    def mark_canceled(self):
        if self.status != self.STATUS_PENDING:
            return False
        self.status = self.STATUS_CANCELED
        self.save(update_fields=['status'])
        return True
