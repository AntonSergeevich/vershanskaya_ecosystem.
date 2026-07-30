from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from crm import services
from crm.models import Campaign, CRMLead

User = get_user_model()


class AdvanceLeadTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(username='marina', phone='+79991234567')

    def test_first_touch_creates_the_lead(self):
        lead = services.advance_lead(self.user, 'new', source='Квиз')
        self.assertEqual(lead.stage, 'new')
        self.assertEqual(lead.source, 'Квиз')

    def test_automation_only_moves_forward(self):
        """Заполненная анкета не должна откатывать «Разбор проведён»."""
        services.advance_lead(self.user, 'session_done')
        services.advance_lead(self.user, 'form_filled')
        self.assertEqual(CRMLead.objects.get(user=self.user).stage, 'session_done')

    def test_notes_accumulate_instead_of_overwriting(self):
        services.advance_lead(self.user, 'new', note='Пришла из квиза')
        services.advance_lead(self.user, 'form_filled', note='Оставила телефон')
        lead = CRMLead.objects.get(user=self.user)
        self.assertIn('Пришла из квиза', lead.notes)
        self.assertIn('Оставила телефон', lead.notes)

    def test_anonymous_visitor_creates_nothing(self):
        self.assertIsNone(services.advance_lead(None, 'new'))
        self.assertFalse(CRMLead.objects.exists())

    def test_manual_move_can_go_backwards(self):
        lead = services.advance_lead(self.user, 'session_done')
        self.assertTrue(services.set_stage(lead, 'new'))
        self.assertEqual(lead.stage, 'new')

    def test_manual_move_rejects_unknown_stage(self):
        lead = services.advance_lead(self.user, 'new')
        self.assertFalse(services.set_stage(lead, 'ne-suschestvuet'))
        self.assertEqual(lead.stage, 'new')


class BoardTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create(username='admin', is_staff=True)
        self.client_user = User.objects.create(username='marina')
        services.advance_lead(self.client_user, 'form_filled')

    def test_board_is_closed_to_regular_users(self):
        """На доске видны чужие телефоны — она не для клиентов."""
        self.client.force_login(self.client_user)
        response = self.client.get(reverse('crm:board'))
        self.assertNotEqual(response.status_code, 200)

    def test_staff_sees_the_board(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('crm:board'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'marina')

    def test_drag_and_drop_moves_the_lead(self):
        self.client.force_login(self.staff)
        lead = CRMLead.objects.get(user=self.client_user)
        response = self.client.post(reverse('crm:move_lead', args=[lead.pk]),
                                    {'stage': 'subscribed'},
                                    headers={'x-requested-with': 'XMLHttpRequest'})
        self.assertEqual(response.json(), {'moved': True, 'stage': 'subscribed'})

    def test_funnel_stats_count_every_stage(self):
        stats = services.funnel_stats()
        self.assertEqual(stats['total'], 1)
        self.assertEqual(stats['counts']['form_filled'], 1)


class CampaignTests(TestCase):
    def test_campaign_reaches_only_the_target_stage(self):
        reachable = User.objects.create(username='reachable', telegram_id=1)
        other_stage = User.objects.create(username='other', telegram_id=2)
        services.advance_lead(reachable, 'form_filled')
        services.advance_lead(other_stage, 'new')

        campaign = Campaign.objects.create(title='Догрев', message_text='Привет',
                                           target_stage='form_filled')
        self.assertEqual(services.send_campaign(campaign), 1)
        campaign.refresh_from_db()
        self.assertTrue(campaign.is_sent)
        self.assertIsNotNone(campaign.sent_at)

    def test_users_without_telegram_are_skipped(self):
        no_telegram = User.objects.create(username='silent')
        services.advance_lead(no_telegram, 'new')
        campaign = Campaign.objects.create(title='Всем', message_text='Привет')
        self.assertEqual(services.send_campaign(campaign), 0)
