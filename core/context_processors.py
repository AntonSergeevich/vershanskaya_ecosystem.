from django.conf import settings

from .models import LegalPage, SiteProfile

COOKIE_CONSENT = 'cookie_consent'
PRIVACY_SLUG = 'politika'


def brand(request):
    """Общие для всех шаблонов данные бренда, контакты и профиль эксперта."""
    profile = SiteProfile.load()
    return {
        'CLUB_PRICE': settings.CLUB_PRICE,
        'TELEGRAM_CHANNEL_URL': settings.TELEGRAM_CHANNEL_URL,
        'INSTAGRAM_URL': settings.INSTAGRAM_URL,
        'SITE_NAME': profile.name,
        'profile': profile,
        'footer_legal': LegalPage.objects.filter(is_published=True, show_in_footer=True),
        # Ссылка на политику нужна и в баннере кук, и под формами согласия.
        'privacy_page': LegalPage.objects.filter(slug=PRIVACY_SLUG,
                                                 is_published=True).first(),
        # Баннер показываем, пока согласие не сохранено в куке. Проверка на
        # сервере, а не в JS: иначе баннер моргает при каждой загрузке.
        'show_cookie_banner': request.COOKIES.get(COOKIE_CONSENT) != 'yes',
        # Пусто, пока в .env нет ключей: тогда виджет капчи не рисуется,
        # и у человека нет лишнего шага.
        'captcha_key': settings.SMARTCAPTCHA_KEY if settings.SMARTCAPTCHA_SECRET else '',
    }
