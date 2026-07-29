from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, Subscription


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ['username', 'email', 'phone', 'telegram_id', 'archetype', 'is_club_member', 'is_staff']
    list_filter = ['is_club_member', 'is_staff', 'is_superuser', 'created_at']
    search_fields = ['username', 'email', 'phone', 'telegram_id', 'archetype']
    ordering = ['-created_at']

    fieldsets = UserAdmin.fieldsets + (
        ('Данные воронки и экосистемы', {
            'fields': ('phone', 'telegram_id', 'archetype', 'avatar', 'is_club_member')
        }),
    )


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'status', 'amount', 'payment_provider', 'next_billing_date', 'start_date']
    list_filter = ['status', 'payment_provider', 'start_date']
    search_fields = ['user__username', 'user__email', 'user__phone', 'payment_id']
    readonly_fields = ['start_date']
    ordering = ['-start_date']