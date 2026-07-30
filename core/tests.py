"""Проверка, что все публичные страницы открываются.

Задача этих тестов — ловить опечатки в шаблонах и оборванные {% url %}:
такие ошибки не видны при импорте и вылезают только на живой странице.
"""
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from core.models import FAQItem, Testimonial

User = get_user_model()


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
