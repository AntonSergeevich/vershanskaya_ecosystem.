from django.contrib import admin

from .models import FAQItem, Testimonial


@admin.register(Testimonial)
class TestimonialAdmin(admin.ModelAdmin):
    list_display = ['author', 'role', 'order', 'is_published']
    list_filter = ['is_published']
    list_editable = ['order', 'is_published']
    search_fields = ['author', 'text']


@admin.register(FAQItem)
class FAQItemAdmin(admin.ModelAdmin):
    list_display = ['question', 'order', 'is_published']
    list_filter = ['is_published']
    list_editable = ['order', 'is_published']
    search_fields = ['question', 'answer']
