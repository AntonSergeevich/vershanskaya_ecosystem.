from django.contrib import admin, messages
from django.urls import reverse
from django.utils.html import format_html

from . import services
from .models import Campaign, CRMLead


@admin.register(CRMLead)
class CRMLeadAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'archetype', 'stage', 'source', 'board_link',
                    'updated_at', 'created_at']
    list_filter = ['stage', 'source', 'user__archetype', 'created_at']
    search_fields = ['user__username', 'user__email', 'user__phone', 'notes']
    list_editable = ['stage']
    autocomplete_fields = ['user']
    ordering = ['-updated_at']

    @admin.display(description="Архетип")
    def archetype(self, obj):
        return obj.user.archetype_label or '—'

    @admin.display(description="Карточка")
    def board_link(self, obj):
        return format_html('<a href="{}">открыть</a>', reverse('crm:lead', args=[obj.pk]))


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ['id', 'title', 'target_stage', 'recipients', 'is_sent', 'sent_at']
    list_filter = ['is_sent', 'target_stage']
    search_fields = ['title', 'message_text']
    ordering = ['-id']
    actions = ['send_now']

    @admin.display(description="Получателей")
    def recipients(self, obj):
        """Сколько людей реально получат сообщение — без Telegram ID не отправить."""
        leads = CRMLead.objects.filter(user__telegram_id__isnull=False)
        if obj.target_stage:
            leads = leads.filter(stage=obj.target_stage)
        return leads.count()

    @admin.action(description="Отправить рассылку")
    def send_now(self, request, queryset):
        total = sum(services.send_campaign(campaign)
                    for campaign in queryset.filter(is_sent=False))
        self.message_user(request, f"Отправлено сообщений: {total}.", messages.SUCCESS)
