from django.contrib import admin
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.html import format_html

from .models import FAQItem, LegalInfo, LegalPage, SiteProfile, Testimonial


@admin.register(LegalInfo)
class LegalInfoAdmin(admin.ModelAdmin):
    """Реквизиты — тоже одна запись на весь сайт."""
    fieldsets = (
        ('Продавец', {'fields': ('entity_type', 'legal_name', 'inn', 'ogrn', 'address')}),
        ('Контакты', {'fields': ('email', 'phone', 'site_url')}),
        ('Банк', {
            'fields': ('bank_account', 'bank_name', 'bank_bik',
                       'bank_corr_account', 'bank_inn', 'bank_address'),
            'description': "Нужны для оферты и для оплаты по счёту. "
                           "Заполняются командой seed_requisites.",
        }),
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        return redirect(reverse('admin:core_legalinfo_change', args=[LegalInfo.load().pk]))


@admin.register(LegalPage)
class LegalPageAdmin(admin.ModelAdmin):
    list_display = ['title', 'slug', 'is_published', 'show_in_footer', 'order', 'updated_at']
    list_filter = ['is_published']
    list_editable = ['is_published', 'show_in_footer', 'order']
    prepopulated_fields = {'slug': ('title',)}
    search_fields = ['title', 'body']


@admin.register(SiteProfile)
class SiteProfileAdmin(admin.ModelAdmin):
    """Профиль всегда один, поэтому списка и кнопки «добавить» здесь нет."""
    readonly_fields = ['portrait_preview', 'updated_at']

    fieldsets = (
        ('Кто вы', {'fields': ('name', 'role')}),
        ('Первый экран', {
            'fields': ('headline', 'lead', 'portrait', 'portrait_preview', 'portrait_note'),
            'description': 'В заголовке слова в *звёздочках* выделяются курсивом.',
        }),
        ('Блок «обо мне»', {'fields': ('about_title', 'about_text', 'about_photo')}),
        (None, {'fields': ('updated_at',)}),
    )

    def has_add_permission(self, request):
        # Запись создаётся сама через SiteProfile.load().
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        """Открываем сразу единственную запись — список из одной строки не нужен."""
        profile = SiteProfile.load()
        return redirect(reverse('admin:core_siteprofile_change', args=[profile.pk]))

    @admin.display(description="Как выглядит сейчас")
    def portrait_preview(self, obj):
        if not obj.portrait:
            return "Портрет не загружен"
        return format_html(
            '<img src="{}" style="max-width:220px;border-radius:16px">', obj.portrait.url)


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
