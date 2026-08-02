"""Реквизиты продавца."""
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from core.models import LegalInfo


class SeedRequisitesTests(TestCase):
    def test_it_fills_the_requisites(self):
        call_command('seed_requisites', verbosity=0)

        info = LegalInfo.load()
        self.assertEqual(info.inn, '245012342898')
        self.assertEqual(info.bank_bik, '044525974')
        self.assertTrue(info.has_bank_details)

    def test_the_entity_type_is_really_changed(self):
        """У формы собственности есть значение по умолчанию, и «пустой» она
        не бывает — из-за этого она однажды осталась «самозанятым»."""
        self.assertEqual(LegalInfo.load().entity_type, 'self_employed')

        call_command('seed_requisites', verbosity=0)

        self.assertEqual(LegalInfo.load().entity_type, 'ip')

    def test_it_does_not_overwrite_manual_edits(self):
        """Команда запускается при каждой выкатке — правки в админке важнее."""
        info = LegalInfo.load()
        info.legal_name = 'ИП Вершанская Е. Ф.'
        info.email = 'info@example.com'
        info.save()

        call_command('seed_requisites', verbosity=0)

        info.refresh_from_db()
        self.assertEqual(info.legal_name, 'ИП Вершанская Е. Ф.')
        self.assertEqual(info.email, 'info@example.com')

    def test_force_overwrites_everything(self):
        info = LegalInfo.load()
        info.inn = '000000000000'
        info.save()

        call_command('seed_requisites', force=True, verbosity=0)

        self.assertEqual(LegalInfo.load().inn, '245012342898')

    def test_running_twice_changes_nothing_the_second_time(self):
        call_command('seed_requisites', verbosity=0)
        before = LegalInfo.load().updated_at

        call_command('seed_requisites', verbosity=0)

        self.assertEqual(LegalInfo.load().updated_at, before)


class RequisitesPageTests(TestCase):
    def setUp(self):
        call_command('seed_requisites', verbosity=0)

    def test_the_page_shows_the_seller_and_the_bank(self):
        response = self.client.get(reverse('core:requisites'))

        self.assertContains(response, 'Индивидуальный предприниматель')
        self.assertContains(response, '245012342898')
        self.assertContains(response, 'Банковские реквизиты')
        self.assertContains(response, '40802810200002731604')

    def test_the_bank_block_is_hidden_until_it_is_filled(self):
        info = LegalInfo.load()
        info.bank_account = ''
        info.save()

        response = self.client.get(reverse('core:requisites'))
        self.assertNotContains(response, 'Банковские реквизиты')

    def test_the_bank_details_reach_the_documents(self):
        """Оферта подставляет реквизиты токенами — они не должны разъезжаться."""
        tokens = LegalInfo.load().tokens()
        self.assertEqual(tokens['{БИК}'], '044525974')
        self.assertEqual(tokens['{БАНК}'], 'АО «ТБанк»')
