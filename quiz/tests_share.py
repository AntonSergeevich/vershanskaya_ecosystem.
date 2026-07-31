"""Кнопка «назад», превью ссылок и страница архетипа."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from quiz.models import Answer, Option, Question, Quiz, QuizAttempt

User = get_user_model()


def make_quiz(questions=3):
    quiz = Quiz.objects.create(title='Архетипы', slug='arhetipy', is_published=True)
    for number in range(1, questions + 1):
        question = Question.objects.create(quiz=quiz, text=f'Вопрос {number}',
                                           order=number)
        Option.objects.create(question=question, text=f'Творец {number}',
                              archetype='creator', order=1)
        Option.objects.create(question=question, text=f'Мудрец {number}',
                              archetype='sage', order=2)
    return quiz


class QuizBackTests(TestCase):
    def setUp(self):
        self.quiz = make_quiz()
        self.client.post(reverse('quiz:start', args=[self.quiz.slug]))
        self.attempt = QuizAttempt.objects.get()

    def answer(self, question, archetype='creator'):
        option = question.options.get(archetype=archetype)
        return self.client.post(reverse('quiz:question', args=[self.attempt.pk]),
                                {'option': option.pk})

    def first(self):
        return self.quiz.questions.first()

    def test_the_first_question_has_nowhere_to_go_back_to(self):
        response = self.client.get(reverse('quiz:question', args=[self.attempt.pk]))
        self.assertNotContains(response, 'Назад')

    def test_the_second_question_offers_a_way_back(self):
        self.answer(self.first())
        response = self.client.get(reverse('quiz:question', args=[self.attempt.pk]))
        self.assertContains(response, 'Назад')
        self.assertContains(response,
                            reverse('quiz:question_at', args=[self.attempt.pk, 1]))

    def test_going_back_shows_the_previous_answer(self):
        """Иначе человек выбирает вслепую заново и не понимает, что было."""
        self.answer(self.first())

        response = self.client.get(
            reverse('quiz:question_at', args=[self.attempt.pk, 1]))

        self.assertContains(response, 'Вопрос 1')
        self.assertContains(response, 'is-chosen')

    def test_the_answer_can_be_changed(self):
        self.answer(self.first(), 'creator')

        option = self.first().options.get(archetype='sage')
        self.client.post(reverse('quiz:question_at', args=[self.attempt.pk, 1]),
                         {'option': option.pk})

        self.assertEqual(Answer.objects.filter(question=self.first()).count(), 1)
        self.assertEqual(Answer.objects.get(question=self.first()).option, option)

    def test_changing_an_answer_returns_to_where_the_person_stopped(self):
        self.answer(self.first())
        option = self.first().options.get(archetype='sage')

        response = self.client.post(
            reverse('quiz:question_at', args=[self.attempt.pk, 1]), {'option': option.pk})

        self.assertRedirects(response, reverse('quiz:question', args=[self.attempt.pk]))
        self.assertContains(self.client.get(response['Location']), 'Вопрос 2')

    def test_you_cannot_jump_ahead_by_url(self):
        """Иначе последний вопрос открывается сразу, минуя первые два."""
        response = self.client.get(
            reverse('quiz:question_at', args=[self.attempt.pk, 3]))
        self.assertRedirects(response, reverse('quiz:question', args=[self.attempt.pk]))

    def test_a_missing_question_number_does_not_crash(self):
        response = self.client.get(
            reverse('quiz:question_at', args=[self.attempt.pk, 99]))
        self.assertRedirects(response, reverse('quiz:question', args=[self.attempt.pk]))

    def test_someone_elses_attempt_stays_closed(self):
        other = QuizAttempt.objects.create(quiz=self.quiz, session_key='chuzhaya')
        response = self.client.get(reverse('quiz:question_at', args=[other.pk, 1]))
        self.assertEqual(response.status_code, 404)


class ArchetypePageTests(TestCase):
    def setUp(self):
        self.quiz = make_quiz()

    def test_page_is_open_to_everyone(self):
        """Ссылку открывают из чужого чата — вход туда требовать нельзя."""
        response = self.client.get(reverse('quiz:archetype', args=['creator']))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Творец')
        self.assertContains(response, 'Пройти тест')

    def test_unknown_archetype_is_a_404(self):
        response = self.client.get(reverse('quiz:archetype', args=['drakon']))
        self.assertEqual(response.status_code, 404)

    def test_page_carries_its_own_preview(self):
        response = self.client.get(reverse('quiz:archetype', args=['sage']))
        self.assertContains(response, 'og:image')
        self.assertContains(response, 'img/og/sage.png')
        self.assertContains(response, 'Архетип «Мудрец»')

    def test_other_archetypes_are_linked(self):
        response = self.client.get(reverse('quiz:archetype', args=['creator']))
        self.assertContains(response, reverse('quiz:archetype', args=['hero']))
        self.assertNotContains(response,
                               f'href="{reverse("quiz:archetype", args=["creator"])}"')


class ShareOnResultTests(TestCase):
    def setUp(self):
        self.quiz = make_quiz(questions=1)
        self.client.post(reverse('quiz:start', args=[self.quiz.slug]))
        self.attempt = QuizAttempt.objects.get()
        question = self.quiz.questions.first()
        self.client.post(reverse('quiz:question', args=[self.attempt.pk]),
                         {'option': question.options.get(archetype='creator').pk})
        self.client.post(reverse('quiz:contact', args=[self.attempt.pk]),
                         {'contact_name': 'Марина', 'contact_phone': '+79991234567',
                          'contact_telegram': '', 'consent': 'on'})
        self.attempt.refresh_from_db()
        assert self.attempt.is_completed, "квиз не завершился — тест ниже проверял бы редирект"

    def test_result_shares_the_public_page_not_itself(self):
        """Адрес результата привязан к сессии — у друга он открылся бы ошибкой."""
        response = self.client.get(reverse('quiz:result', args=[self.attempt.pk]))

        public = reverse('quiz:archetype', args=['creator'])
        self.assertContains(response, f'data-share-url="http://testserver{public}"')
        self.assertNotContains(response, 'data-share-url="http://testserver/kviz/shag/')

    def test_shared_link_really_opens_for_a_stranger(self):
        response = self.client.get(reverse('quiz:result', args=[self.attempt.pk]))
        url = response.context['share_url'].replace('http://testserver', '')

        stranger = self.client_class()
        self.assertEqual(stranger.get(url).status_code, 200)

    def test_messengers_are_offered(self):
        response = self.client.get(reverse('quiz:result', args=[self.attempt.pk]))
        self.assertContains(response, 't.me/share/url')
        self.assertContains(response, 'api.whatsapp.com/send')
        self.assertContains(response, 'Скопировать ссылку')

    def test_the_preview_matches_the_archetype(self):
        response = self.client.get(reverse('quiz:result', args=[self.attempt.pk]))
        self.assertContains(response, 'img/og/creator.png')
        self.assertContains(response, 'Мой архетип — Творец')


class OpenGraphTests(TestCase):
    def test_every_public_page_has_a_preview(self):
        make_quiz()
        for name in ('core:landing', 'lms:courses', 'booking:slots',
                     'payments:club', 'quiz:list'):
            with self.subTest(page=name):
                response = self.client.get(reverse(name), follow=True)
                self.assertContains(response, 'property="og:title"')
                self.assertContains(response, 'property="og:image"')

    def test_the_image_address_is_absolute(self):
        """Относительный адрес мессенджеры не берут — превью останется пустым."""
        response = self.client.get(reverse('core:landing'))
        self.assertContains(response, 'content="http://testserver/static/img/og/default.png"')
