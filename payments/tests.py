import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from crm.models import CRMLead
from lms.models import Course, CourseAccess
from payments import services
from payments.models import Payment
from users.models import Subscription

User = get_user_model()


class GrantAccessTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(username='marina', phone='+79991234567')

    def club_payment(self):
        return services.create_payment(self.user, Payment.KIND_CLUB)

    def test_club_payment_opens_the_club_and_starts_a_subscription(self):
        payment = self.club_payment()
        self.assertTrue(services.grant_access(payment))

        self.user.refresh_from_db()
        self.assertTrue(self.user.is_club_member)
        self.assertIsNotNone(self.user.active_subscription)
        self.assertEqual(CRMLead.objects.get(user=self.user).stage, 'subscribed')

    def test_repeated_webhook_does_not_extend_twice(self):
        """Шлюзы шлют уведомление несколько раз — доступ выдаём только раз."""
        payment = self.club_payment()
        services.grant_access(payment)
        first_end = self.user.active_subscription.next_billing_date

        self.assertFalse(services.grant_access(payment))
        self.assertEqual(self.user.active_subscription.next_billing_date, first_end)

    def test_second_payment_extends_the_same_subscription(self):
        services.grant_access(self.club_payment())
        first_end = self.user.active_subscription.next_billing_date

        services.grant_access(self.club_payment())
        self.assertGreater(self.user.active_subscription.next_billing_date, first_end)
        self.assertEqual(Subscription.objects.count(), 1)

    def test_course_payment_grants_access_to_that_course_only(self):
        course = Course.objects.create(title='Курс', slug='kurs', description='',
                                       access_level='paid', price=5000)
        other = Course.objects.create(title='Другой', slug='drugoy', description='',
                                      access_level='paid', price=5000)
        payment = services.create_payment(self.user, Payment.KIND_COURSE, course=course)
        services.grant_access(payment)

        self.assertTrue(CourseAccess.objects.filter(user=self.user, course=course).exists())
        self.assertFalse(other.is_available_for(self.user))
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_club_member)

    def test_course_payment_needs_a_course(self):
        with self.assertRaises(ValueError):
            services.create_payment(self.user, Payment.KIND_COURSE)

    def test_amount_defaults_to_the_club_price(self):
        with override_settings(CLUB_PRICE=3500):
            payment = services.create_payment(self.user, Payment.KIND_CLUB)
        self.assertEqual(int(payment.amount), 3500)


class ExpireSubscriptionsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(username='marina', is_club_member=True)

    def make(self, days, status='active'):
        return Subscription.objects.create(
            user=self.user, status=status,
            next_billing_date=timezone.now() + timedelta(days=days))

    def test_expired_subscription_closes_the_club(self):
        self.make(days=-1)
        self.assertEqual(services.expire_subscriptions(), 1)

        self.user.refresh_from_db()
        self.assertFalse(self.user.is_club_member)

    def test_living_subscription_is_untouched(self):
        self.make(days=5)
        self.assertEqual(services.expire_subscriptions(), 0)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_club_member)

    def test_cancelled_subscription_expires_at_the_end_of_the_paid_period(self):
        """Отменённая подписка тоже должна однажды закрыть доступ."""
        subscription = self.make(days=5)
        subscription.cancel()
        self.assertEqual(services.expire_subscriptions(), 0)

        subscription.next_billing_date = timezone.now() - timedelta(days=1)
        subscription.save()
        self.assertEqual(services.expire_subscriptions(), 1)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_club_member)

    def test_second_living_subscription_keeps_the_access(self):
        self.make(days=-1)
        self.make(days=20)
        services.expire_subscriptions()
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_club_member)

    def test_management_command_runs(self):
        self.make(days=-1)
        call_command('expire_subscriptions', verbosity=0)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_club_member)


class CheckoutFlowTests(TestCase):
    """Без настроенного эквайринга оплата подтверждается вручную."""

    def setUp(self):
        self.user = User.objects.create(username='marina', phone='+79991234567')
        self.client.force_login(self.user)

    def test_checkout_sends_to_the_manual_confirmation_page(self):
        response = self.client.post(reverse('payments:checkout'), {'kind': 'club'})
        payment = Payment.objects.get()
        self.assertEqual(payment.provider, 'manual')
        self.assertIn(str(payment.idempotency_key), response['Location'])

    def test_manual_confirmation_opens_the_club(self):
        self.client.post(reverse('payments:checkout'), {'kind': 'club'})
        payment = Payment.objects.get()

        self.client.post(reverse('payments:manual_confirm',
                                 args=[payment.idempotency_key]))
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_club_member)

    def test_nobody_can_confirm_someone_elses_payment(self):
        self.client.post(reverse('payments:checkout'), {'kind': 'club'})
        payment = Payment.objects.get()

        self.client.force_login(User.objects.create(username='stranger'))
        response = self.client.post(reverse('payments:manual_confirm',
                                            args=[payment.idempotency_key]))
        self.assertEqual(response.status_code, 404)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_club_member)

    @override_settings(PAYMENT_PROVIDER='yookassa', YOOKASSA_SHOP_ID='1',
                       YOOKASSA_SECRET_KEY='secret')
    def test_manual_confirmation_is_closed_once_the_gateway_works(self):
        """Иначе это была бы кнопка «выдай себе подписку бесплатно»."""
        payment = services.create_payment(self.user, Payment.KIND_CLUB)
        response = self.client.get(reverse('payments:manual_confirm',
                                           args=[payment.idempotency_key]))
        self.assertEqual(response.status_code, 404)

    def test_buying_an_already_open_course_is_refused(self):
        course = Course.objects.create(title='Курс', slug='kurs', description='',
                                       access_level='free')
        response = self.client.post(reverse('payments:checkout'),
                                    {'kind': 'course', 'course': course.slug})
        self.assertRedirects(response, course.get_absolute_url())
        self.assertFalse(Payment.objects.exists())

    def test_cancelling_the_subscription_keeps_access_until_period_end(self):
        services.grant_access(services.create_payment(self.user, Payment.KIND_CLUB))
        self.client.post(reverse('payments:cancel_subscription'))

        subscription = self.user.active_subscription
        self.assertIsNotNone(subscription)
        self.assertFalse(subscription.auto_renew)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_club_member)


class WebhookTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(username='marina')
        self.payment = services.create_payment(self.user, Payment.KIND_CLUB)

    def post(self, body):
        return self.client.post(reverse('payments:webhook'), data=json.dumps(body),
                                content_type='application/json')

    def test_unknown_payment_is_acknowledged_without_side_effects(self):
        """Отвечаем 200, иначе шлюз будет повторять запрос бесконечно."""
        response = self.post({'object': {'id': 'net-takogo', 'status': 'succeeded'}})
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_club_member)

    def test_broken_body_is_rejected(self):
        response = self.client.post(reverse('payments:webhook'), data='не json',
                                    content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_succeeded_notification_opens_the_club(self):
        response = self.post({'object': {'id': 'pay-1', 'status': 'succeeded',
                                         'metadata': {'payment_id': str(self.payment.pk)}}})
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_club_member)

    def test_cancelled_notification_marks_the_payment(self):
        self.post({'object': {'id': 'pay-1', 'status': 'canceled',
                              'metadata': {'payment_id': str(self.payment.pk)}}})
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.STATUS_CANCELED)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_club_member)
