from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.services.analytics import chart_points, dashboard_data, percent_change
from core.services.insights import insights, rule_based
from payments.models import Payment
from users.models import Subscription

User = get_user_model()


def paid(user, amount, days_ago):
    """Оплата «задним числом» — paid_at выставляем в обход auto-полей."""
    payment = Payment.objects.create(user=user, kind=Payment.KIND_CLUB,
                                     amount=Decimal(amount),
                                     status=Payment.STATUS_SUCCEEDED)
    Payment.objects.filter(pk=payment.pk).update(
        paid_at=timezone.now() - timedelta(days=days_ago))
    return payment


class PercentChangeTests(TestCase):
    def test_growth_and_decline(self):
        self.assertEqual(percent_change(100, 150), 50)
        self.assertEqual(percent_change(100, 50), -50)

    def test_growth_from_zero_is_not_a_percentage(self):
        """Рост с нуля процентами не выражается — не показываем «+∞%»."""
        self.assertIsNone(percent_change(0, 500))


class MoneyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(username='marina')

    def test_revenue_splits_by_period(self):
        paid(self.user, 2900, days_ago=5)
        paid(self.user, 2900, days_ago=10)
        paid(self.user, 1000, days_ago=45)

        data = dashboard_data()['money']
        self.assertEqual(data['revenue_30'], 5800)
        self.assertEqual(data['revenue_prev_30'], 1000)
        self.assertEqual(data['payments_30'], 2)
        self.assertEqual(data['average_check'], 2900)

    def test_unpaid_attempts_are_not_revenue(self):
        Payment.objects.create(user=self.user, kind=Payment.KIND_CLUB,
                               amount=Decimal('2900'))
        self.assertEqual(dashboard_data()['money']['revenue_30'], 0)

    def test_empty_database_does_not_divide_by_zero(self):
        data = dashboard_data()
        self.assertEqual(data['money']['revenue_30'], 0)
        self.assertEqual(data['funnel']['quiz_conversion'], 0)
        self.assertEqual(data['money']['average_check'], 0)


class ClubTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(username='marina', is_club_member=True)

    def make(self, days, status='active'):
        return Subscription.objects.create(
            user=self.user, status=status,
            next_billing_date=timezone.now() + timedelta(days=days))

    def test_canceled_but_paid_counts_as_leaving(self):
        """Отменённая, но ещё действующая подписка — предупреждение, а не потеря."""
        subscription = self.make(days=10)
        subscription.cancel()

        club = dashboard_data()['club']
        self.assertEqual(club['active'], 1)
        self.assertEqual(club['leaving'], 1)

    def test_expired_subscription_is_not_active(self):
        self.make(days=-1)
        self.assertEqual(dashboard_data()['club']['active'], 0)

    def test_expiring_this_week(self):
        self.make(days=3)
        self.make(days=20)
        self.assertEqual(dashboard_data()['club']['expiring_week'], 1)


class ChartTests(TestCase):
    def test_empty_rows_give_empty_chart(self):
        chart = chart_points([])
        self.assertEqual(chart['bars'], [])
        self.assertEqual(chart['points'], '')

    def test_single_month_does_not_divide_by_zero(self):
        chart = chart_points([{'month': timezone.now(), 'total': 2900.0, 'count': 1}])
        self.assertEqual(len(chart['bars']), 1)

    def test_taller_month_sits_higher(self):
        now = timezone.now()
        rows = [
            {'month': now, 'total': 1000.0, 'count': 1},
            {'month': now, 'total': 5000.0, 'count': 2},
        ]
        low, high = chart_points(rows)['bars']
        # Ось Y в SVG растёт вниз: больше выручка — меньше координата.
        self.assertLess(high['y'], low['y'])


class InsightsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(username='marina')

    def test_rules_report_an_empty_month_honestly(self):
        notes = rule_based(dashboard_data())
        self.assertTrue(any('оплат не было' in note for note in notes))

    def test_rules_mention_growth_with_a_number(self):
        paid(self.user, 4000, days_ago=5)
        paid(self.user, 2000, days_ago=45)

        notes = rule_based(dashboard_data())
        self.assertTrue(any('100%' in note for note in notes))

    def test_never_more_than_three_notes(self):
        paid(self.user, 4000, days_ago=5)
        self.assertLessEqual(len(rule_based(dashboard_data())), 3)

    def test_without_a_key_rules_are_used(self):
        with override_settings(ANTHROPIC_API_KEY=''):
            result = insights(dashboard_data())
        self.assertFalse(result['by_ai'])
        self.assertTrue(result['notes'])


class AnalyticsPageTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create(username='admin', is_staff=True)
        self.client_user = User.objects.create(username='marina')

    def test_page_is_closed_to_regular_users(self):
        """На странице видны деньги — она не для клиентов."""
        self.client.force_login(self.client_user)
        self.assertNotEqual(
            self.client.get(reverse('crm:analytics')).status_code, 200)

    def test_staff_sees_the_numbers(self):
        paid(self.client_user, 2900, days_ago=3)
        self.client.force_login(self.staff)

        response = self.client.get(reverse('crm:analytics'))
        self.assertEqual(response.status_code, 200)
        # Русская локаль разделяет разряды неразрывным пробелом.
        self.assertContains(response, '2\xa0900 ₽')

    def test_chart_coordinates_use_dots_not_commas(self):
        """Русская локаль пишет дробные через запятую — в SVG это ломает точки."""
        paid(self.client_user, 2900, days_ago=3)
        self.client.force_login(self.staff)

        html = self.client.get(reverse('crm:analytics')).content.decode()
        self.assertIn('<circle cx="0.0"', html)
        self.assertNotIn('cx="0,0"', html)

    def test_page_opens_on_an_empty_database(self):
        """Первый запуск после деплоя — данных нет, страница обязана работать."""
        self.client.force_login(self.staff)
        response = self.client.get(reverse('crm:analytics'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'график появится после первой')
