from django.conf import settings

from .models import SiteProfile


def brand(request):
    """Общие для всех шаблонов данные бренда, контакты и профиль эксперта."""
    profile = SiteProfile.load()
    return {
        'CLUB_PRICE': settings.CLUB_PRICE,
        'TELEGRAM_CHANNEL_URL': settings.TELEGRAM_CHANNEL_URL,
        'INSTAGRAM_URL': settings.INSTAGRAM_URL,
        'SITE_NAME': profile.name,
        'profile': profile,
    }
