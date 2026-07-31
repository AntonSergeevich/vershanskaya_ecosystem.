"""Карта сайта для поисковиков.

Отдаём только то, что имеет смысл в выдаче: страницы-витрины, курсы,
описания архетипов и правовые документы. Всё, что за входом — кабинет,
уроки, шаги квиза, — в карту не попадает: туда поисковик всё равно не
зайдёт, а в sitemap это выглядит как обещание страницы, которой нет.
"""
from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from core.constants import ARCHETYPE_CHOICES
from core.models import LegalPage
from lms.models import Course
from quiz.models import Quiz


class StaticSitemap(Sitemap):
    """Постоянные страницы сайта."""
    changefreq = 'weekly'

    # Страницы входа здесь нет намеренно: она закрыта в robots.txt, и
    # обещать её в карте сайта — значит противоречить самому себе.
    #
    # Списка квизов тоже нет: когда квиз один, /kviz/ уводит редиректом на
    # него самого, а сам квиз уже перечислен в QuizSitemap. Адрес, который
    # отвечает редиректом, в карте только тратит обход.
    NAMES = [
        ('core:landing', 1.0),
        ('lms:courses', 0.8),
        ('payments:club', 0.8),
        ('booking:slots', 0.7),
    ]

    def items(self):
        return self.NAMES

    def location(self, item):
        return reverse(item[0])

    def priority(self, item):
        return item[1]


class QuizSitemap(Sitemap):
    changefreq = 'monthly'
    priority = 0.9

    def items(self):
        return Quiz.objects.filter(is_published=True)


class ArchetypeSitemap(Sitemap):
    """Страницы архетипов — то, чем делятся после квиза."""
    changefreq = 'monthly'
    priority = 0.7

    def items(self):
        return [code for code, _ in ARCHETYPE_CHOICES]

    def location(self, code):
        return reverse('quiz:archetype', kwargs={'code': code})


class CourseSitemap(Sitemap):
    changefreq = 'weekly'
    priority = 0.6

    def items(self):
        # Черновики в карту не отдаём: страницы ещё нет.
        return Course.objects.filter(is_published=True)

    def lastmod(self, course):
        return course.created_at


class LegalSitemap(Sitemap):
    changefreq = 'yearly'
    priority = 0.2

    def items(self):
        return LegalPage.objects.filter(is_published=True)

    def lastmod(self, page):
        return getattr(page, 'updated_at', None)


SITEMAPS = {
    'static': StaticSitemap,
    'quiz': QuizSitemap,
    'archetypes': ArchetypeSitemap,
    'courses': CourseSitemap,
    'legal': LegalSitemap,
}
