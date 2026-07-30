from django.contrib import admin, messages

from crm import services as crm

from .models import Booking, BookingSlot


@admin.register(BookingSlot)
class BookingSlotAdmin(admin.ModelAdmin):
    list_display = ['id', 'start_time', 'end_time', 'duration_minutes', 'is_booked',
                    'is_active']
    list_filter = ['is_booked', 'is_active', 'start_time']
    list_editable = ['is_active']
    date_hierarchy = 'start_time'
    ordering = ['start_time']
    search_fields = ['id']

    @admin.display(description="Длительность, мин")
    def duration_minutes(self, obj):
        return obj.duration_minutes


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'slot', 'zoom_link', 'is_completed', 'is_canceled',
                    'created_at']
    list_filter = ['is_completed', 'is_canceled', 'created_at']
    search_fields = ['user__username', 'user__email', 'user__phone', 'notes']
    list_editable = ['is_completed']
    autocomplete_fields = ['user', 'slot']
    actions = ['mark_session_done']

    @admin.action(description="Отметить разбор проведённым")
    def mark_session_done(self, request, queryset):
        """Проведённый разбор двигает лида дальше по воронке автоматически."""
        for booking in queryset.select_related('user'):
            booking.is_completed = True
            booking.save(update_fields=['is_completed'])
            crm.advance_lead(booking.user, 'session_done', note="Разбор проведён")
        self.message_user(request, f"Отмечено разборов: {queryset.count()}.", messages.SUCCESS)
