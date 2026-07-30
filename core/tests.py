"""Проверка, что все публичные страницы открываются.

Задача этих тестов — ловить опечатки в шаблонах и оборванные {% url %}:
такие ошибки не видны при импорте и вылезают только на живой странице.
"""
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from core.models import FAQItem, SiteProfile, Testimonial

User = get_user_model()


class SiteProfileTests(TestCase):
    def test_load_creates_and_then_reuses_one_record(self):
        first = SiteProfile.load()
        second = SiteProfile.load()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(SiteProfile.objects.count(), 1)

    def test_saving_a_new_instance_overwrites_the_only_one(self):
        """Второй профиль означал бы, что часть страниц показывает старое фото."""
        SiteProfile.load()
        SiteProfile(name='Другое имя').save()
        self.assertEqual(SiteProfile.objects.count(), 1)
        self.assertEqual(SiteProfile.load().name, 'Другое имя')

    def test_landing_shows_the_profile_texts(self):
        profile = SiteProfile.load()
        profile.headline = 'Понять, *кто вы*'
        profile.role = 'Психолог'
        profile.save()

        response = self.client.get(reverse('core:landing'))
        self.assertContains(response, '<em>кто вы</em>', html=False)
        self.assertContains(response, 'Психолог')

    def test_landing_survives_a_missing_portrait(self):
        """Фото могут загрузить не сразу — страница обязана работать и без него."""
        response = self.client.get(reverse('core:landing'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'portrait-placeholder')

    def test_admin_profile_page_opens_the_single_record(self):
        staff = User.objects.create(username='admin', is_staff=True, is_superuser=True)
        self.client.force_login(staff)
        response = self.client.get('/admin/core/siteprofile/', follow=True)
        self.assertEqual(response.status_code, 200)


class StickyHeaderTests(SimpleTestCase):
    """Сторож против уже случившейся регрессии.

    `overflow-x: hidden` на html или body делает элемент контейнером прокрутки,
    и закреплённая шапка начинает липнуть к нему, а не к экрану — при скролле
    меню уезжает вверх. Ловится только глазами в браузере, поэтому фиксируем
    правило здесь: страховка от горизонтальной прокрутки должна быть clip.
    """

    def setUp(self):
        self.css = (Path(settings.BASE_DIR) / 'static' / 'css' / 'main.css').read_text()

    def test_page_root_does_not_use_overflow_hidden(self):
        for rule in ('html { overflow-x: hidden', 'overflow-x: hidden;'):
            self.assertNotIn(rule, self.css,
                             "overflow-x: hidden ломает закреплённую шапку — нужен clip")

    def test_header_is_still_sticky(self):
        self.assertIn('position: sticky', self.css)


class PhoneWidgetTests(TestCase):
    def test_phone_inputs_are_marked_for_the_mask(self):
        """data-phone — единственная связь формы со скриптом маски."""
        response = self.client.get(reverse('users:enter'))
        self.assertContains(response, 'data-phone')
        self.assertContains(response, 'js/phone.js')


class PublicPagesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Демо-контент даёт непустые страницы: пустой шаблон легко «проходит»
        # мимо ошибки, которая проявится только на реальных данных.
        call_command('seed_demo', '--with-slots', verbosity=0)

    def test_pages_open_for_a_guest(self):
        pages = [
            reverse('core:landing'),
            reverse('quiz:list'),
            reverse('lms:courses'),
            reverse('lms:course', args=['pervye-shagi']),
            reverse('lms:course', args=['tvorets-praktika']),
            reverse('booking:slots'),
            reverse('payments:club'),
            reverse('users:enter'),
        ]
        for page in pages:
            with self.subTest(page=page):
                self.assertEqual(self.client.get(page, follow=True).status_code, 200)

    def test_pages_open_for_a_member(self):
        user = User.objects.create(username='member', is_club_member=True,
                                   archetype='creator')
        self.client.force_login(user)
        pages = [
            reverse('lms:dashboard'),
            reverse('users:profile'),
            reverse('payments:club'),
            reverse('lms:course', args=['tvorets-praktika']),
        ]
        for page in pages:
            with self.subTest(page=page):
                self.assertEqual(self.client.get(page).status_code, 200)

    def test_staff_pages_open(self):
        staff = User.objects.create(username='admin', is_staff=True, is_superuser=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get(reverse('crm:board')).status_code, 200)
        self.assertEqual(self.client.get('/admin/').status_code, 200)

    def test_no_template_syntax_leaks_into_the_html(self):
        """Многострочный {# … #} Django комментарием не считает.

        Такой «комментарий» молча уезжает на страницу как текст — заметить
        это можно только глазами, поэтому проверяем автоматически.
        """
        pages = [
            reverse('core:landing'),
            reverse('lms:courses'),
            reverse('lms:course', args=['pervye-shagi']),
            reverse('booking:slots'),
            reverse('payments:club'),
            reverse('users:enter'),
            reverse('quiz:list'),
        ]
        for page in pages:
            with self.subTest(page=page):
                html = self.client.get(page, follow=True).content.decode()
                self.assertNotIn('{#', html)
                self.assertNotIn('{%', html)

    def test_landing_shows_seeded_content(self):
        Testimonial.objects.create(author='Марина', text='Очень помогло')
        FAQItem.objects.create(question='Как оплатить?', answer='Картой.')

        response = self.client.get(reverse('core:landing'))
        self.assertContains(response, 'Марина')
        self.assertContains(response, 'Как оплатить?')
        self.assertContains(response, 'Первые шаги')

    def test_unpublished_course_is_hidden(self):
        from lms.models import Course
        Course.objects.filter(slug='pervye-shagi').update(is_published=False)
        self.assertEqual(
            self.client.get(reverse('lms:course', args=['pervye-shagi'])).status_code, 404)


class SeedCommandTests(TestCase):
    def test_seed_is_idempotent(self):
        from lms.models import Course
        from quiz.models import Quiz

        call_command('seed_demo', verbosity=0)
        courses, quizzes = Course.objects.count(), Quiz.objects.count()

        call_command('seed_demo', verbosity=0)
        self.assertEqual(Course.objects.count(), courses)
        self.assertEqual(Quiz.objects.count(), quizzes)
