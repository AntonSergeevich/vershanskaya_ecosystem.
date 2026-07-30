from django.conf import settings
from django.shortcuts import render

from lms.models import Course
from quiz.models import Quiz

from .models import FAQItem, Testimonial


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
