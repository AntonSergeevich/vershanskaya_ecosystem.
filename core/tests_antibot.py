"""Проверка на человека: ловушка, секунды, счётчик и капча."""
import time
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from core import antibot
from core.antibot import HONEYPOT, STAMP, human_post, make_stamp
from quiz.models import Option, Question, Quiz, QuizAttempt

CONTACTS = {'contact_name': 'Марина', 'contact_phone': '+79991234567',
            'contact_telegram': '', 'consent': 'on'}


class StampTests(TestCase):
    def test_a_fresh_stamp_reads_back(self):
        self.assertLess(antibot.stamp_age(make_stamp()), 2)

    def test_an_old_stamp_reads_back_its_age(self):
        self.assertGreaterEqual(antibot.stamp_age(make_stamp(time.time() - 60)), 60)

    def test_a_forged_stamp_is_worthless(self):
        """Подпись — весь смысл: иначе бот подставит любое время."""
        self.assertIsNone(antibot.stamp_age('1700000000'))
        self.assertIsNone(antibot.stamp_age(''))

    def test_a_stamp_older_than_a_day_expires(self):
        self.assertIsNone(antibot.stamp_age(make_stamp(time.time() - antibot.MAX_AGE - 60)))


class RateLimitTests(TestCase):
    def setUp(self):
        cache.clear()

    def request(self, ip='10.0.0.1', forwarded=None):
        from django.test import RequestFactory
        meta = {'REMOTE_ADDR': ip}
        if forwarded:
            meta['HTTP_X_FORWARDED_FOR'] = forwarded
        return RequestFactory().post('/', **{f'HTTP_{k}' if False else k: v
                                             for k, v in meta.items()})

    def test_the_limit_triggers_only_after_it_is_passed(self):
        request = self.request()
        for _ in range(3):
            self.assertFalse(antibot.too_many(request, 'proba', limit=3))
        self.assertTrue(antibot.too_many(request, 'proba', limit=3))

    def test_another_address_has_its_own_counter(self):
        for _ in range(4):
            antibot.too_many(self.request('10.0.0.1'), 'proba', limit=3)
        self.assertFalse(antibot.too_many(self.request('10.0.0.2'), 'proba', limit=3))

    def test_different_actions_do_not_share_a_counter(self):
        request = self.request()
        for _ in range(4):
            antibot.too_many(request, 'odno', limit=3)
        self.assertFalse(antibot.too_many(request, 'drugoe', limit=3))

    def test_the_real_address_is_taken_from_the_proxy_header(self):
        """За nginx у всех был бы один REMOTE_ADDR — лимит стал бы общим."""
        request = self.request(forwarded='203.0.113.7, 10.0.0.1')
        self.assertEqual(antibot.client_ip(request), '203.0.113.7')


class QuizFormTests(TestCase):
    """Форма контактов — главный вход лида, по ней и бьют."""

    def setUp(self):
        cache.clear()
        quiz = Quiz.objects.create(title='Архетипы', slug='arhetipy', is_published=True)
        question = Question.objects.create(quiz=quiz, text='Вопрос', order=1)
        Option.objects.create(question=question, text='Ответ', archetype='creator')

        self.client.post(reverse('quiz:start', args=[quiz.slug]))
        self.attempt = QuizAttempt.objects.get()
        self.client.post(reverse('quiz:question', args=[self.attempt.pk]),
                         {'option': question.options.first().pk})
        self.url = reverse('quiz:contact', args=[self.attempt.pk])

    def test_a_human_gets_through(self):
        self.client.post(self.url, human_post(CONTACTS))
        self.attempt.refresh_from_db()
        self.assertTrue(self.attempt.is_completed)

    def test_the_trap_field_stops_the_form(self):
        """Человек этого поля не видит, бот заполняет всё подряд."""
        response = self.client.post(self.url, human_post({**CONTACTS, HONEYPOT: 'http://spam'}))

        self.attempt.refresh_from_db()
        self.assertFalse(self.attempt.is_completed)
        self.assertContains(response, 'Не получилось отправить форму')

    def test_the_error_does_not_explain_what_went_wrong(self):
        """Подсказка «вы заполнили скрытое поле» — инструкция по обходу."""
        response = self.client.post(self.url, human_post({**CONTACTS, HONEYPOT: 'x'}))

        page = response.content.decode().lower()
        for hint in ('ловуш', 'honeypot', 'скрыт', 'слишком быстро'):
            self.assertNotIn(hint, page)

    def test_an_instant_submit_is_not_a_human(self):
        response = self.client.post(self.url, {**CONTACTS, STAMP: make_stamp()})

        self.attempt.refresh_from_db()
        self.assertFalse(self.attempt.is_completed)
        self.assertContains(response, 'Не получилось отправить форму')

    def test_a_submit_without_any_stamp_is_refused(self):
        """Так выглядит скрипт, который постит прямо на адрес формы."""
        self.client.post(self.url, CONTACTS)
        self.attempt.refresh_from_db()
        self.assertFalse(self.attempt.is_completed)

    def test_the_form_carries_a_stamp_and_a_trap(self):
        response = self.client.get(self.url)
        self.assertContains(response, f'name="{STAMP}"')
        self.assertContains(response, f'name="{HONEYPOT}"')
        # Ловушка спрятана стилями, а не полем hidden: часть скриптов
        # hidden-поля пропускает, и ловушка бы не сработала.
        self.assertContains(response, 'class="trap"')

    def test_a_flood_from_one_address_is_cut_off(self):
        # Отправляем заведомо неполную форму: удачная отправка завершила бы
        # квиз, и дальше вьюха просто уводила бы на результат, не доходя
        # до счётчика.
        junk = human_post({'contact_name': ''})
        for _ in range(30):
            self.client.post(self.url, junk)

        response = self.client.post(self.url, junk, follow=True)
        self.assertContains(response, 'Слишком много попыток')


class RegistrationTests(TestCase):
    def setUp(self):
        cache.clear()

    def register(self, extra=None):
        return self.client.post(reverse('users:enter'), human_post({
            'action': 'register', 'first_name': 'Ольга',
            'phone': '+79990001122', 'password1': 'sekret123',
            'password2': 'sekret123', **(extra or {}),
        }))

    def test_a_human_registers(self):
        self.assertEqual(self.register().status_code, 302)

    def test_a_bot_filling_the_trap_does_not(self):
        from django.contrib.auth import get_user_model

        self.register({HONEYPOT: 'http://spam'})
        self.assertFalse(get_user_model().objects.exists())


@override_settings(SMARTCAPTCHA_KEY='client-key', SMARTCAPTCHA_SECRET='secret-key')
class CaptchaTests(TestCase):
    """Капча включается ключами в .env и до этого не показывается."""

    def setUp(self):
        cache.clear()

    def test_without_keys_the_captcha_field_is_absent(self):
        with override_settings(SMARTCAPTCHA_KEY='', SMARTCAPTCHA_SECRET=''):
            self.assertFalse(antibot.captcha_enabled())

    def test_with_keys_it_turns_on(self):
        self.assertTrue(antibot.captcha_enabled())

    def test_a_failed_check_stops_the_form(self):
        from quiz.forms import ContactForm

        with patch('core.antibot.captcha_passed', return_value=False):
            form = ContactForm(human_post(CONTACTS))
            self.assertFalse(form.is_valid())
            self.assertIn('Проверка не пройдена', str(form.errors))

    def test_a_passed_check_lets_the_form_through(self):
        from quiz.forms import ContactForm

        with patch('core.antibot.captcha_passed', return_value=True):
            self.assertTrue(ContactForm(human_post(CONTACTS)).is_valid())

    def test_an_empty_answer_never_passes(self):
        """Проверять надо на сервере: значение присылает браузер."""
        self.assertFalse(antibot.captcha_passed(''))

    def test_yandex_being_down_does_not_block_live_people(self):
        """Осознанный размен: лучше пропустить ботов, чем потерять клиентов."""
        import requests

        with patch('requests.get', side_effect=requests.RequestException('нет связи')):
            self.assertTrue(antibot.captcha_passed('token'))

    def test_a_bad_answer_is_rejected(self):
        with patch('requests.get') as get:
            get.return_value.json.return_value = {'status': 'failed'}
            self.assertFalse(antibot.captcha_passed('token'))
