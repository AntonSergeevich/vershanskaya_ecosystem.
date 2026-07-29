from django.contrib import admin
from .models import CRMLead, Campaign


@admin.register(CRMLead)
class CRMLeadAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'stage', 'source', 'updated_at', 'created_at']
    list_filter = ['stage', 'source', 'created_at']
    search_fields = ['user__username', 'user__email', 'user__phone', 'notes']
    list_editable = ['stage']
    ordering = ['-updated_at']


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ['id', 'title', 'target_stage', 'is_sent', 'sent_at']
    list_filter = ['is_sent', 'target_stage']
    search_fields = ['title', 'message_text']
    ordering = ['-id']