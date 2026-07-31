from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from core.antibot import human_post

from core.constants import ARCHETYPE_CREATOR, ARCHETYPE_SAGE
from crm.models import CRMLead
from quiz.models import Option, Question, Quiz, QuizAttempt

User = get_user_model()


class QuizFixtureMixin:
    def build_quiz(self, questions=2):
        quiz = Quiz.objects.create(title='Архетип', slug='arhetip')
        for index in range(1, questions + 1):
            question = Question.objects.create(quiz=quiz, text=f'Вопрос {index}',
                                               order=index)
            Option.objects.create(question=question, text='Творец',
                                  archetype=ARCHETYPE_CREATOR, order=1)
            Option.objects.create(question=question, text='Мудрец',
                                  archetype=ARCHETYPE_SAGE, order=2)
        return quiz


class ScoringTests(QuizFixtureMixin, TestCase):
    def test_winner_is_the_heaviest_archetype(self):
        quiz = self.build_quiz(questions=3)
        attempt = QuizAttempt.objects.create(quiz=quiz)

        questions = list(quiz.questions.all())
        for question in questions[:2]:
            attempt.answers.create(question=question,
                                   option=question.options.get(archetype=ARCHETYPE_CREATOR))
        attempt.answers.create(question=questions[2],
                               option=questions[2].options.get(archetype=ARCHETYPE_SAGE))

        self.assertEqual(attempt.calculate_result(), ARCHETYPE_CREATOR)
        self.assertTrue(attempt.is_completed)
        self.assertIsNotNone(attempt.completed_at)

    def test_weights_are_respected(self):
        quiz = self.build_quiz(questions=1)
        question = quiz.questions.first()
        heavy = question.options.get(archetype=ARCHETYPE_SAGE)
        heavy.weight = 5
        heavy.save()

        attempt = QuizAttempt.objects.create(quiz=quiz)
        attempt.answers.create(question=question, option=heavy)
        self.assertEqual(attempt.calculate_result(), ARCHETYPE_SAGE)

    def test_tie_is_resolved_stably(self):
        """При равенстве весов результат не должен «прыгать» между запусками."""
        quiz = self.build_quiz(questions=2)
        questions = list(quiz.questions.all())
        results = set()
        for _ in range(3):
            attempt = QuizAttempt.objects.create(quiz=quiz)
            attempt.answers.create(question=questions[0],
                                   option=questions[0].options.get(archetype=ARCHETYPE_CREATOR))
            attempt.answers.create(question=questions[1],
                                   option=questions[1].options.get(archetype=ARCHETYPE_SAGE))
            results.add(attempt.calculate_result())
        self.assertEqual(len(results), 1)

    def test_empty_attempt_has_no_result(self):
        quiz = self.build_quiz()
        attempt = QuizAttempt.objects.create(quiz=quiz)
        self.assertEqual(attempt.calculate_result(), '')
        self.assertFalse(attempt.is_completed)

    def test_progress_percent(self):
        quiz = self.build_quiz(questions=4)
        attempt = QuizAttempt.objects.create(quiz=quiz)
        question = quiz.questions.first()
        attempt.answers.create(question=question, option=question.options.first())
        self.assertEqual(attempt.progress_percent, 25)


class FunnelFlowTests(QuizFixtureMixin, TestCase):
    def setUp(self):
        # Счётчик отправок живёт в кэше и переживает отдельный тест:
        # без очистки тесты начинают отнимать лимит друг у друга.
        cache.clear()
        self.quiz = self.build_quiz(questions=2)

    def start_attempt(self):
        self.client.post(reverse('quiz:start', args=[self.quiz.slug]))
        return QuizAttempt.objects.get()

    def answer_all(self, attempt):
        for question in self.quiz.questions.all():
            self.client.post(reverse('quiz:question', args=[attempt.pk]),
                             {'option': question.options.first().pk})

    def test_full_funnel_creates_lead(self):
        attempt = self.start_attempt()
        self.answer_all(attempt)

        response = self.client.post(reverse('quiz:contact', args=[attempt.pk]), {
            **human_post(),
            'contact_name': 'Марина',
            'contact_phone': '89991234567',
            'consent': 'on',
        })
        self.assertRedirects(response, reverse('quiz:result', args=[attempt.pk]))

        attempt.refresh_from_db()
        self.assertTrue(attempt.is_completed)
        self.assertEqual(attempt.result_archetype, ARCHETYPE_CREATOR)

        user = User.objects.get(phone='+79991234567')
        self.assertEqual(attempt.user, user)
        self.assertEqual(user.archetype, ARCHETYPE_CREATOR)

        lead = CRMLead.objects.get(user=user)
        self.assertEqual(lead.stage, 'form_filled')

    def test_contact_requires_a_way_to_reach_back(self):
        attempt = self.start_attempt()
        self.answer_all(attempt)
        response = self.client.post(reverse('quiz:contact', args=[attempt.pk]),
                                    human_post({'contact_name': 'Марина', 'consent': 'on'}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Оставьте телефон или Telegram')
        self.assertFalse(QuizAttempt.objects.get().is_completed)

    def test_contact_step_is_skipped_until_all_questions_answered(self):
        attempt = self.start_attempt()
        response = self.client.get(reverse('quiz:contact', args=[attempt.pk]))
        self.assertRedirects(response, reverse('quiz:question', args=[attempt.pk]))

    def test_answer_can_be_changed_without_breaking_the_attempt(self):
        """Кнопка «назад» в браузере не должна ломать прохождение."""
        attempt = self.start_attempt()
        question = self.quiz.questions.first()
        url = reverse('quiz:question', args=[attempt.pk])
        self.client.post(url, {'option': question.options.first().pk})
        self.client.post(url, {'option': question.options.last().pk})
        self.assertEqual(attempt.answers.filter(question=question).count(), 1)

    def test_someone_elses_attempt_is_not_reachable(self):
        attempt = self.start_attempt()
        other = self.client_class()
        self.assertEqual(other.get(reverse('quiz:result', args=[attempt.pk])).status_code, 404)
        self.assertEqual(other.get(reverse('quiz:contact', args=[attempt.pk])).status_code, 404)

    def test_result_redirects_back_if_not_finished(self):
        attempt = self.start_attempt()
        response = self.client.get(reverse('quiz:result', args=[attempt.pk]))
        self.assertRedirects(response, reverse('quiz:question', args=[attempt.pk]))

    def test_logged_in_user_keeps_their_attempt(self):
        user = User.objects.create(username='marina', phone='+79990000000')
        user.set_password('sekret123')
        user.save()
        self.client.force_login(user)

        attempt = self.start_attempt()
        self.assertEqual(attempt.user, user)
        self.answer_all(attempt)
        self.client.post(reverse('quiz:contact', args=[attempt.pk]), {
            **human_post(),
            **human_post(),
            'contact_name': 'Марина', 'contact_phone': '+79990000000', 'consent': 'on'})

        self.assertEqual(User.objects.count(), 1)
        user.refresh_from_db()
        self.assertEqual(user.archetype, ARCHETYPE_CREATOR)
