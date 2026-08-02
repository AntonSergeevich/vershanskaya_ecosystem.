"""Приём оплат через GetPlatinum.

Главное, что здесь проверяется: доступ не выдаётся ни по одному
уведомлению, в котором мы не уверены.
"""
import json
from decimal import Decimal
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from payments import getplatinum
from payments.models import Payment

User = get_user_model()

SECRET = 'ochen-dlinnyy-sekret-iz-env'

CONFIGURED = dict(
    PAYMENT_PROVIDER='getplatinum',
    GETPLATINUM_FORM_URL='https://pay.getplatinum.ru/form/abc123',
    GETPLATINUM_WEBHOOK_SECRET=SECRET,
)


@override_settings(**CONFIGURED)
class PaymentLinkTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(username='marina', phone='+79991234567')
        self.payment = Payment.objects.create(user=self.user, kind=Payment.KIND_CLUB,
                                              amount=Decimal('2900.00'))

    def query(self, **kwargs):
        return parse_qs(urlparse(getplatinum.payment_url(self.payment, **kwargs)).query)

    def test_the_link_carries_our_order_and_amount(self):
        query = self.query()
        self.assertEqual(query['order_id'], [str(self.payment.idempotency_key)])
        self.assertEqual(query['amount'], ['2900.00'])

    def test_parameters_from_the_cabinet_can_be_renamed(self):
        """Если в кабинете поля зовутся иначе — это правка .env, а не кода."""
        with override_settings(GETPLATINUM_ORDER_PARAM='oid',
                               GETPLATINUM_AMOUNT_PARAM='summa'):
            query = self.query()
        self.assertEqual(query['oid'], [str(self.payment.idempotency_key)])
        self.assertEqual(query['summa'], ['2900.00'])

    def test_parameters_already_in_the_link_survive(self):
        """В ссылке из кабинета обычно уже есть свои параметры."""
        with override_settings(
                GETPLATINUM_FORM_URL='https://pay.getplatinum.ru/f?shop=42'):
            query = self.query()
        self.assertEqual(query['shop'], ['42'])
        self.assertIn('order_id', query)

    def test_the_gateway_counts_as_configured(self):
        from payments import services
        self.assertTrue(services.is_gateway_configured())

    def test_without_a_secret_it_is_not_configured(self):
        """Без секрета некому подтвердить оплату — включать нельзя."""
        from payments import services
        with override_settings(GETPLATINUM_WEBHOOK_SECRET=''):
            self.assertFalse(services.is_gateway_configured())


@override_settings(**CONFIGURED)
class WebhookTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(username='marina')
        self.payment = Payment.objects.create(user=self.user, kind=Payment.KIND_CLUB,
                                              amount=Decimal('2900.00'))
        self.url = reverse('payments:getplatinum_webhook', args=[SECRET])

    def notify(self, payload, url=None, as_form=False):
        if as_form:
            return self.client.post(url or self.url, payload)
        return self.client.post(url or self.url, json.dumps(payload),
                                content_type='application/json')

    def paid(self, **extra):
        return {'order_id': str(self.payment.idempotency_key),
                'amount': '2900.00', 'status': 'success', **extra}

    def is_paid(self):
        self.payment.refresh_from_db()
        return self.payment.is_paid

    # --- Подлинность ------------------------------------------------------

    def test_a_wrong_secret_in_the_url_is_a_404(self):
        """Секрет в адресе — единственное, что отделяет нас от чужих POST."""
        response = self.notify(self.paid(),
                               url=reverse('payments:getplatinum_webhook',
                                           args=['ne-tot-sekret']))
        self.assertEqual(response.status_code, 404)
        self.assertFalse(self.is_paid())

    def test_a_prefix_of_the_secret_does_not_pass(self):
        response = self.notify(self.paid(),
                               url=reverse('payments:getplatinum_webhook',
                                           args=[SECRET[:10]]))
        self.assertEqual(response.status_code, 404)

    # --- Успешная оплата --------------------------------------------------

    def test_a_good_notification_opens_access(self):
        self.assertEqual(self.notify(self.paid()).status_code, 200)
        self.assertTrue(self.is_paid())
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_club_member)

    def test_a_form_encoded_notification_works_too(self):
        """Сервисы шлют то JSON, то обычную форму."""
        self.notify(self.paid(), as_form=True)
        self.assertTrue(self.is_paid())

    def test_the_order_is_found_whatever_the_field_is_called(self):
        """Номер заказа ищем по значению: имена полей у всех свои."""
        self.notify({'kakoe_to_pole': str(self.payment.idempotency_key),
                     'status': 'paid', 'amount': '2900.00'})
        self.assertTrue(self.is_paid())

    def test_a_nested_notification_is_understood(self):
        self.notify({'object': {'order': {'id': str(self.payment.idempotency_key)},
                                'amount': '2900.00', 'status': 'paid'}})
        self.assertTrue(self.is_paid())

    def test_an_event_name_is_not_guessed_as_a_status(self):
        """«payment.success» угадывать нельзя: подстрока success есть и в
        unsuccessful, а «paid» — в not_paid. Такое зовёт человека."""
        with patch('core.services.telegram.notify_admins') as notify:
            self.notify({'event': 'payment.success',
                         'order_id': str(self.payment.idempotency_key),
                         'amount': '2900.00'})

        self.assertFalse(self.is_paid())
        self.assertIn('статус непонятен', notify.call_args.args[0])

    def test_a_repeat_notification_does_not_pay_twice(self):
        from users.models import Subscription

        self.notify(self.paid())
        self.notify(self.paid())

        self.assertEqual(Subscription.objects.count(), 1)

    # --- Всё, при чём доступ выдавать нельзя ------------------------------

    def test_a_failed_payment_does_not_open_access(self):
        self.notify(self.paid(status='failed'))
        self.assertFalse(self.is_paid())

    def test_a_wrong_amount_does_not_open_access(self):
        """Ссылка на оплату могла быть подделана или собрана вручную."""
        with patch('core.services.telegram.notify_admins') as notify:
            self.notify(self.paid(amount='1.00'))

        self.assertFalse(self.is_paid())
        self.assertIn('не сошлась', notify.call_args.args[0])

    def test_an_unknown_status_does_not_open_access_and_calls_a_human(self):
        """Пока правило успеха не настроено, наугад открывать клуб нельзя."""
        with patch('core.services.telegram.notify_admins') as notify:
            self.notify({'order_id': str(self.payment.idempotency_key),
                         'amount': '2900.00'})

        self.assertFalse(self.is_paid())
        self.assertTrue(notify.called)
        self.assertIn('статус непонятен', notify.call_args.args[0])

    def test_an_unknown_order_is_reported_not_ignored(self):
        with patch('core.services.telegram.notify_admins') as notify:
            response = self.notify({'order_id': 'chuzhoy-zakaz', 'status': 'success'})

        self.assertEqual(response.status_code, 200)
        self.assertIn('заказ не найден', notify.call_args.args[0])

    def test_broken_json_is_refused(self):
        response = self.client.post(self.url, 'не json',
                                    content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_a_canceled_payment_cannot_be_revived(self):
        """Отменённый платёж — закрытая история, оплате по нему взяться неоткуда."""
        self.payment.mark_canceled()

        with patch('core.services.telegram.notify_admins'):
            self.notify(self.paid())

        self.assertFalse(self.is_paid())


@override_settings(**CONFIGURED, GETPLATINUM_SUCCESS_FIELD='payment.state',
                   GETPLATINUM_SUCCESS_VALUES='CONFIRMED')
class ConfiguredRuleTests(TestCase):
    """После первой реальной оплаты правило успеха задаётся в .env."""

    def setUp(self):
        self.user = User.objects.create(username='marina')
        self.payment = Payment.objects.create(user=self.user, kind=Payment.KIND_CLUB,
                                              amount=Decimal('2900.00'))
        self.url = reverse('payments:getplatinum_webhook', args=[SECRET])

    def notify(self, state):
        return self.client.post(self.url, json.dumps({
            'order_id': str(self.payment.idempotency_key),
            'amount': '2900.00',
            'payment': {'state': state},
        }), content_type='application/json')

    def test_the_configured_value_opens_access(self):
        self.notify('CONFIRMED')
        self.payment.refresh_from_db()
        self.assertTrue(self.payment.is_paid)

    def test_any_other_value_does_not(self):
        self.notify('DECLINED')
        self.payment.refresh_from_db()
        self.assertFalse(self.payment.is_paid)

    def test_the_guessing_mode_is_off_once_the_rule_is_set(self):
        """Иначе «status: success» в соседнем поле открыл бы доступ мимо правила."""
        self.client.post(self.url, json.dumps({
            'order_id': str(self.payment.idempotency_key),
            'amount': '2900.00',
            'status': 'success',
            'payment': {'state': 'DECLINED'},
        }), content_type='application/json')

        self.payment.refresh_from_db()
        self.assertFalse(self.payment.is_paid)
