from django.conf import settings
from django.http import Http404
from django.shortcuts import get_object_or_404, render

from lms.models import Course
from quiz.models import Quiz

from .models import FAQItem, LegalInfo, LegalPage, Testimonial


def landing(request):
    """Главная страница — вход в воронку.

    Первый экран ведёт в квиз: разговор начинается не с «купите подписку»,
    а с вопроса про самого человека.
    """
    return render(request, 'core/landing.html', {
        'quiz': Quiz.objects.filter(is_published=True).first(),
        'free_courses': Course.objects.filter(is_published=True, access_level='free')[:3],
        'club_courses': Course.objects.filter(is_published=True, access_level='club')[:3],
        'testimonials': Testimonial.objects.filter(is_published=True)[:6],
        'faq': FAQItem.objects.filter(is_published=True),
        'price': settings.CLUB_PRICE,
    })


def legal_page(request, slug):
    """Оферта, политика и прочие документы.

    Черновик показываем только сотрудникам: неготовый текст оферты на
    публичной странице хуже, чем её отсутствие.
    """
    page = get_object_or_404(LegalPage, slug=slug)
    if not page.is_published and not request.user.is_staff:
        raise Http404

    return render(request, 'core/legal_page.html', {
        'page': page,
        'legal': LegalInfo.load(),
    })


def requisites(request):
    """Реквизиты продавца — отдельной страницей, её просит эквайринг."""
    return render(request, 'core/requisites.html', {
        'legal': LegalInfo.load(),
    })
