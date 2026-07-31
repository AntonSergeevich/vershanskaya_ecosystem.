import hashlib
import hmac
import time

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from users import telegram_auth

User = get_user_model()

BOT_TOKEN = '1234567:TEST-TOKEN'


def sign(data, token=BOT_TOKEN):
    """Подписывает данные так же, как это делает Telegram."""
    payload = {key: str(value) for key, value in data.items() if key != 'hash'}
    check_string = '\n'.join(sorted(f"{k}={v}" for k, v in payload.items()))
    secret = hashlib.sha256(token.encode()).digest()
    payload['hash'] = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    return payload


def widget_data(**overrides):
    data = {'id': 555000111, 'first_name': 'Марина', 'username': 'marina',
            'auth_date': int(time.time())}
    data.update(overrides)
    return sign(data)


@override_settings(TELEGRAM_BOT_TOKEN=BOT_TOKEN, TELEGRAM_BOT_USERNAME='test_bot')
class SignatureTests(TestCase):
    def test_valid_signature_passes(self):
        self.assertTrue(telegram_auth.check_signature(widget_data()))

    def test_tampered_field_fails(self):
        """Подменить id, не зная токена, нельзя — на этом всё и держится."""
        data = widget_data()
        data['id'] = '999999999'
        self.assertFalse(telegram_auth.check_signature(data))

    def test_signature_from_another_bot_fails(self):
        data = sign({'id': 1, 'auth_date': int(time.time())}, token='9999999:OTHER')
        self.assertFalse(telegram_auth.check_signature(data))

    def test_missing_hash_fails(self):
        self.assertFalse(telegram_auth.check_signature({'id': '1'}))

    @override_settings(TELEGRAM_BOT_TOKEN='')
    def test_without_a_bot_token_nothing_is_trusted(self):
        self.assertFalse(telegram_auth.check_signature(widget_data()))

    def test_stale_data_is_rejected(self):
        """Перехваченную ссылку нельзя предъявлять вечно."""
        old = int(time.time()) - telegram_auth.MAX_AGE_SECONDS - 60
        self.assertFalse(telegram_auth.is_fresh(widget_data(auth_date=old)))

    def test_fresh_data_is_accepted(self):
        self.assertTrue(telegram_auth.is_fresh(widget_data()))


@override_settings(TELEGRAM_BOT_TOKEN=BOT_TOKEN, TELEGRAM_BOT_USERNAME='test_bot')
class TelegramLoginTests(TestCase):
    def test_first_login_creates_a_user_with_telegram_id(self):
        response = self.client.get(reverse('users:telegram_login'), widget_data())
        self.assertEqual(response.status_code, 302)

        user = User.objects.get(telegram_id=555000111)
        self.assertEqual(user.first_name, 'Марина')
        self.assertFalse(user.has_usable_password())

    def test_second_login_reuses_the_same_user(self):
        self.client.get(reverse('users:telegram_login'), widget_data())
        self.client.get(reverse('users:telegram_login'), widget_data())
        self.assertEqual(User.objects.filter(telegram_id=555000111).count(), 1)

    def test_silent_quiz_account_is_linked_not_duplicated(self):
        """Учётка из квиза заведена по нику — второй быть не должно."""
        User.objects.create(username='marina')

        self.client.get(reverse('users:telegram_login'), widget_data())

        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(User.objects.get().telegram_id, 555000111)

    def test_forged_data_does_not_log_anyone_in(self):
        data = widget_data()
        data['id'] = '999999999'

        response = self.client.get(reverse('users:telegram_login'), data, follow=True)
        self.assertFalse(User.objects.exists())
        self.assertContains(response, 'Не удалось подтвердить вход')

    def test_next_parameter_does_not_break_the_signature(self):
        """Telegram подписывает только свои поля, а ?next= дописываем мы сами."""
        data = widget_data()
        data['next'] = reverse('booking:slots')

        response = self.client.get(reverse('users:telegram_login'), data)

        self.assertEqual(response['Location'], reverse('booking:slots'))
        self.assertTrue(User.objects.filter(telegram_id=555000111).exists())

    def test_next_parameter_cannot_redirect_off_site(self):
        data = widget_data()
        data['next'] = 'https://evil.example.com/'
        response = self.client.get(reverse('users:telegram_login'), data)
        self.assertEqual(response['Location'], reverse('lms:dashboard'))

    def test_widget_is_hidden_when_the_bot_is_not_configured(self):
        with override_settings(TELEGRAM_BOT_TOKEN=''):
            response = self.client.get(reverse('users:enter'))
        self.assertNotContains(response, 'telegram-widget.js')

    def test_widget_is_shown_when_the_bot_is_configured(self):
        response = self.client.get(reverse('users:enter'))
        self.assertContains(response, 'telegram-widget.js')
        self.assertContains(response, 'data-telegram-login="test_bot"')


class ClubInviteTests(TestCase):
    """Ради чего всё затевалось: без telegram_id приглашение никуда не уходит."""

    def test_paid_member_with_telegram_gets_the_invite(self):
        from unittest.mock import patch
        from payments import services
        from payments.models import Payment

        user = User.objects.create(username='marina', telegram_id=555000111)
        payment = services.create_payment(user, Payment.KIND_CLUB)

        with patch('core.services.telegram.create_club_invite_link',
                   return_value='https://t.me/+abc') as invite, \
             patch('core.services.telegram.send_message') as send:
            services.grant_access(payment)

        self.assertTrue(invite.called)
        # send_message зовут дважды: участнику и в админский чат. Нас
        # интересует любое сообщение со ссылкой — порядок вызовов не важен.
        sent = ' '.join(str(call.args) for call in send.call_args_list)
        self.assertIn('t.me/+abc', sent, "приглашение не отправлено участнику клуба")
