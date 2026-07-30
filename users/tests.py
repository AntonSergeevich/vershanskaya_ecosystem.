from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from users.models import Subscription
from users.utils import find_or_create_lead_user, normalize_phone, normalize_telegram

User = get_user_model()


class NormalizePhoneTests(TestCase):
    def test_different_formats_collapse_to_one(self):
        """Один и тот же номер, записанный по-разному, — один человек."""
        for raw in ['+7 (999) 123-45-67', '89991234567', '79991234567', '9991234567']:
            self.assertEqual(normalize_phone(raw), '+79991234567', msg=raw)

    def test_empty_stays_empty(self):
        self.assertEqual(normalize_phone(''), '')
        self.assertEqual(normalize_phone(None), '')

    def test_telegram_handles(self):
        for raw in ['@Nick', 'nick', 'https://t.me/Nick', 'T.ME/nick']:
            self.assertEqual(normalize_telegram(raw), 'nick', msg=raw)


class LeadUserTests(TestCase):
    def test_creates_silent_account_without_password(self):
        user = find_or_create_lead_user(phone='8 999 111-22-33', name='Марина')
        self.assertIsNotNone(user)
        self.assertEqual(user.phone, '+79991112233')
        self.assertEqual(user.first_name, 'Марина')
        self.assertFalse(user.has_usable_password())

    def test_same_phone_reuses_account(self):
        first = find_or_create_lead_user(phone='+79991112233', name='Марина')
        second = find_or_create_lead_user(phone='8(999)111-22-33', name='Марина В.')
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(User.objects.count(), 1)

    def test_no_contacts_no_user(self):
        self.assertIsNone(find_or_create_lead_user())

    def test_existing_profile_fields_are_not_overwritten(self):
        user = User.objects.create(username='marina', phone='+79991112233',
                                   first_name='Марина')
        find_or_create_lead_user(phone='+79991112233', name='Кто-то другой')
        user.refresh_from_db()
        self.assertEqual(user.first_name, 'Марина')


class PhoneNormalisationOnSaveTests(TestCase):
    def test_blank_phone_saved_as_null(self):
        """Пустые телефоны не должны конфликтовать по unique-ограничению."""
        User.objects.create(username='one', phone='')
        User.objects.create(username='two', phone='')
        self.assertEqual(User.objects.filter(phone__isnull=True).count(), 2)


class TierTests(TestCase):
    def test_tier_follows_flags(self):
        user = User.objects.create(username='seeker')
        self.assertEqual(user.tier, 'seeker')
        self.assertFalse(user.has_club_access)

        user.is_club_member = True
        self.assertEqual(user.tier, 'creator')
        self.assertTrue(user.has_club_access)

        user.has_personal_guidance = True
        self.assertEqual(user.tier, 'mage')


class SubscriptionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(username='creator', is_club_member=True)

    def make(self, days=10, status='active'):
        return Subscription.objects.create(
            user=self.user, status=status,
            next_billing_date=timezone.now() + timedelta(days=days))

    def test_extend_adds_to_paid_period_not_to_now(self):
        """Досрочная оплата не должна съедать уже оплаченные дни."""
        subscription = self.make(days=10)
        subscription.extend(30)
        self.assertAlmostEqual((subscription.next_billing_date - timezone.now()).days, 40,
                               delta=1)

    def test_cancel_keeps_access_until_period_end(self):
        subscription = self.make(days=10)
        subscription.cancel()
        self.assertFalse(subscription.auto_renew)
        # Отменённая, но ещё оплаченная подписка продолжает давать доступ.
        self.assertEqual(self.user.active_subscription, subscription)

    def test_expired_subscription_is_not_active(self):
        self.make(days=-1)
        self.assertIsNone(self.user.active_subscription)

    def test_repayment_after_cancel_restores_autorenew(self):
        subscription = self.make(days=10)
        subscription.cancel()
        subscription.extend(30)
        self.assertTrue(subscription.auto_renew)
        self.assertEqual(subscription.status, 'active')


class AuthFlowTests(TestCase):
    def test_registration_creates_user_and_logs_in(self):
        response = self.client.post(reverse('users:enter'), {
            'action': 'register',
            'first_name': 'Ольга',
            'phone': '+7 999 000 11 22',
            'password1': 'sekret123',
            'password2': 'sekret123',
        })
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(phone='+79990001122')
        self.assertTrue(user.has_usable_password())

    def test_login_by_phone_in_any_format(self):
        user = User.objects.create(username='olga', phone='+79990001122')
        user.set_password('sekret123')
        user.save()

        response = self.client.post(reverse('users:enter'), {
            'action': 'login',
            'username': '8 (999) 000-11-22',
            'password': 'sekret123',
        })
        self.assertEqual(response.status_code, 302)

    def test_silent_lead_account_can_be_claimed(self):
        """Учётку, созданную квизом, человек может «присвоить», задав пароль."""
        lead = find_or_create_lead_user(phone='+79990001122', name='Ольга')
        response = self.client.post(reverse('users:enter'), {
            'action': 'register',
            'first_name': 'Ольга',
            'phone': '+79990001122',
            'password1': 'sekret123',
            'password2': 'sekret123',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(User.objects.count(), 1)
        lead.refresh_from_db()
        self.assertTrue(lead.has_usable_password())

    def test_registered_phone_cannot_be_taken_over(self):
        user = User.objects.create(username='olga', phone='+79990001122')
        user.set_password('sekret123')
        user.save()

        response = self.client.post(reverse('users:enter'), {
            'action': 'register',
            'first_name': 'Чужой',
            'phone': '+79990001122',
            'password1': 'drugoy123',
            'password2': 'drugoy123',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'уже зарегистрирован')

    def test_login_next_ignores_external_host(self):
        user = User.objects.create(username='olga', phone='+79990001122')
        user.set_password('sekret123')
        user.save()

        response = self.client.post(
            reverse('users:enter'),
            {'action': 'login', 'username': 'olga', 'password': 'sekret123',
             'next': 'https://evil.example.com/'})
        self.assertEqual(response['Location'], reverse('lms:dashboard'))
