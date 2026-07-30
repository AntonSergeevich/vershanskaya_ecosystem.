from django.contrib import admin, messages

from . import services
from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'title', 'amount', 'status', 'provider', 'created_at',
                    'paid_at']
    list_filter = ['status', 'kind', 'provider', 'created_at']
    search_fields = ['user__username', 'user__phone', 'provider_payment_id']
    autocomplete_fields = ['user', 'course']
    readonly_fields = ['idempotency_key', 'confirmation_url', 'created_at', 'paid_at',
                       'subscription']
    actions = ['confirm_payments']

    @admin.display(description="Назначение")
    def title(self, obj):
        return obj.title

    @admin.action(description="Подтвердить оплату и выдать доступ")
    def confirm_payments(self, request, queryset):
        """Ручное подтверждение — для оплат переводом и разбора спорных случаев."""
        granted = sum(1 for payment in queryset if services.grant_access(payment))
        self.message_user(
            request,
            f"Доступ выдан по {granted} платежам (остальные уже были подтверждены).",
            messages.SUCCESS)
