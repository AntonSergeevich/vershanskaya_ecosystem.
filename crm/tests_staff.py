"""Екатерина ходит по собственному сайту — в её же цифрах этого быть не должно."""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from booking.models import Booking, BookingSlot
from core.services.analytics import booking_summary, funnel_summary, money_summary
from crm import services as crm
from crm.models import CRMLead
from payments.models import Payment
from quiz.models import Quiz, QuizAttempt

User = get_user_model()


class StaffOutOfTheFunnelTests(TestCase):
    def setUp(self):
        self.ekaterina = User.objects.create(username='ekaterina', is_staff=True)
        self.client_user = User.objects.create(username='marina')

    def test_staff_action_does_not_create_a_lead(self):
        self.assertIsNone(crm.advance_lead(self.ekaterina, 'form_filled'))
        self.assertFalse(CRMLead.objects.exists())

    def test_client_action_still_creates_a_lead(self):
        self.assertIsNotNone(crm.advance_lead(self.client_user, 'form_filled'))
        self.assertEqual(CRMLead.objects.count(), 1)

    def test_an_old_staff_lead_is_hidden_from_the_board(self):
        """Лиды, заведённые до этой правки, тоже не должны мозолить глаза."""
        CRMLead.objects.create(user=self.ekaterina, stage='new')
        CRMLead.objects.create(user=self.client_user, stage='new')

        on_board = [lead for column in crm.board_columns() for lead in column['leads']]

        self.assertEqual([lead.user for lead in on_board], [self.client_user])
        self.assertEqual(crm.funnel_stats()['total'], 1)

    def test_conversion_is_counted_without_staff(self):
        CRMLead.objects.create(user=self.ekaterina, stage='subscribed')
        CRMLead.objects.create(user=self.client_user, stage='new')

        summary = funnel_summary()

        self.assertEqual(summary['leads'], 1)
        self.assertEqual(summary['subscribed'], 0)
        self.assertEqual(summary['lead_to_client'], 0)

    def test_campaign_does_not_write_to_staff(self):
        from unittest.mock import patch
        from crm.models import Campaign

        self.ekaterina.telegram_id = 111
        self.ekaterina.save()
        self.client_user.telegram_id = 222
        self.client_user.save()
        CRMLead.objects.create(user=self.ekaterina, stage='new')
        CRMLead.objects.create(user=self.client_user, stage='new')

        campaign = Campaign.objects.create(title='Прогрев', message_text='Привет')
        with patch('core.services.telegram.send_message') as send:
            crm.send_campaign(campaign)

        self.assertEqual([call.args[0] for call in send.call_args_list], [222])


class StaffOutOfTheNumbersTests(TestCase):
    def setUp(self):
        self.ekaterina = User.objects.create(username='ekaterina', is_staff=True)
        self.client_user = User.objects.create(username='marina')

    def pay(self, user, amount):
        return Payment.objects.create(
            user=user, kind=Payment.KIND_CLUB, amount=Decimal(amount),
            status=Payment.STATUS_SUCCEEDED, paid_at=timezone.now())

    def test_own_test_payment_is_not_revenue(self):
        """Проверочная оплата «посмотреть, как работает» — не выручка."""
        self.pay(self.ekaterina, 2900)
        self.pay(self.client_user, 2900)

        money = money_summary()

        self.assertEqual(money['revenue_30'], 2900.0)
        self.assertEqual(money['payments_30'], 1)

    def test_own_booking_is_not_counted(self):
        start = timezone.now() + timedelta(days=1)
        for user in (self.ekaterina, self.client_user):
            slot = BookingSlot.objects.create(start_time=start, end_time=start + timedelta(minutes=30))
            Booking.objects.create(user=user, slot=slot)
            start += timedelta(hours=1)

        self.assertEqual(booking_summary()['upcoming'], 1)

    def test_anonymous_quiz_attempts_are_still_counted(self):
        """Аноним — это трафик. Отсечь надо только свои прохождения."""
        quiz = Quiz.objects.create(title='Архетипы', slug='arhetipy')
        QuizAttempt.objects.create(quiz=quiz, session_key='guest')
        QuizAttempt.objects.create(quiz=quiz, user=self.client_user)
        QuizAttempt.objects.create(quiz=quiz, user=self.ekaterina)

        self.assertEqual(funnel_summary()['attempts'], 2)
