from django.conf import settings


def brand(request):
    """Общие для всех шаблонов данные бренда и контакты."""
    return {
        'CLUB_PRICE': settings.CLUB_PRICE,
        'TELEGRAM_CHANNEL_URL': settings.TELEGRAM_CHANNEL_URL,
        'INSTAGRAM_URL': settings.INSTAGRAM_URL,
        'SITE_NAME': 'Екатерина Вершанская',
    }
