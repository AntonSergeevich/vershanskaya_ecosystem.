from django.contrib import admin
from .models import BookingSlot, Booking


@admin.register(BookingSlot)
class BookingSlotAdmin(admin.ModelAdmin):
    list_display = ['id', 'start_time', 'end_time', 'is_booked']
    list_filter = ['is_booked', 'start_time']
    ordering = ['start_time']


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'slot', 'zoom_link', 'is_completed', 'created_at']
    list_filter = ['is_completed', 'created_at']
    search_fields = ['user__username', 'user__email', 'user__phone', 'notes']
    list_editable = ['is_completed']
    ordering = ['-created_at']