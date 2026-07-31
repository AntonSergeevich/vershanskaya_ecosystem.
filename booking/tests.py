from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from booking.models import Booking, BookingSlot
from booking.services import SlotUnavailable, book_slot, cancel_booking, upcoming_slots
from crm.models import CRMLead

User = get_user_model()


def make_slot(hours_ahead=24, minutes=30):
    start = timezone.now() + timedelta(hours=hours_ahead)
    return BookingSlot.objects.create(start_time=start,
                                      end_time=start + timedelta(minutes=minutes))


class SlotTests(TestCase):
    def test_past_slot_is_not_available(self):
        slot = make_slot(hours_ahead=-1)
        self.assertFalse(slot.is_available)

    def test_hidden_slot_is_not_available(self):
        slot = make_slot()
        slot.is_active = False
        self.assertFalse(slot.is_available)

    def test_duration_is_derived_from_the_times(self):
        self.assertEqual(make_slot(minutes=30).duration_minutes, 30)

    def test_upcoming_slots_are_grouped_by_day(self):
        make_slot(hours_ahead=24)
        make_slot(hours_ahead=25)
        make_slot(hours_ahead=24 * 5)
        self.assertEqual(len(upcoming_slots()), 2)

    def test_slots_beyond_the_horizon_are_hidden(self):
        make_slot(hours_ahead=24 * 40)
        self.assertEqual(upcoming_slots(limit_days=21), [])


class BookingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(username='marina', phone='+79991234567')
        self.other = User.objects.create(username='olga', phone='+79997654321')
        self.slot = make_slot()

    def test_booking_marks_the_slot_and_moves_the_lead(self):
        booking = book_slot(self.user, self.slot.pk, notes='Про работу')
        self.slot.refresh_from_db()

        self.assertTrue(self.slot.is_booked)
        self.assertEqual(booking.notes, 'Про работу')
        self.assertEqual(CRMLead.objects.get(user=self.user).stage, 'slot_booked')

    def test_the_same_slot_cannot_be_taken_twice(self):
        book_slot(self.user, self.slot.pk)
        with self.assertRaises(SlotUnavailable):
            book_slot(self.other, self.slot.pk)
        self.assertEqual(Booking.objects.count(), 1)

    def test_past_slot_cannot_be_booked(self):
        past = make_slot(hours_ahead=-2)
        with self.assertRaises(SlotUnavailable):
            book_slot(self.user, past.pk)

    def test_missing_slot_is_reported_not_crashed(self):
        with self.assertRaises(SlotUnavailable):
            book_slot(self.user, 999999)

    def test_cancelled_slot_goes_back_on_sale(self):
        """После отмены то же окно должно снова продаваться."""
        booking = book_slot(self.user, self.slot.pk)
        cancel_booking(booking)

        self.slot.refresh_from_db()
        self.assertFalse(self.slot.is_booked)

        second = book_slot(self.other, self.slot.pk)
        self.assertEqual(second.user, self.other)
        self.assertEqual(Booking.objects.filter(is_canceled=False).count(), 1)

    def test_cancelling_twice_is_harmless(self):
        booking = book_slot(self.user, self.slot.pk)
        cancel_booking(booking)
        cancel_booking(booking)
        self.assertTrue(booking.is_canceled)


class BookingViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(username='marina', phone='+79991234567')
        self.slot = make_slot()

    def test_guests_see_the_calendar_but_must_log_in_to_book(self):
        response = self.client.get(reverse('booking:slots'))
        self.assertEqual(response.status_code, 200)

        response = self.client.post(reverse('booking:book', args=[self.slot.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('users:enter'), response['Location'])

    def test_booking_through_the_site(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('booking:book', args=[self.slot.pk]))
        booking = Booking.objects.get()
        self.assertRedirects(response, reverse('booking:detail', args=[booking.pk]))

    def test_clicking_a_time_opens_confirmation_and_asks_for_the_request(self):
        """Клик по времени не бронирует сразу: сначала спрашиваем, с чем придут."""
        self.client.force_login(self.user)
        response = self.client.get(reverse('booking:book', args=[self.slot.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="notes"')
        self.assertFalse(Booking.objects.exists())

    def test_the_request_from_the_form_reaches_the_booking(self):
        """Без этого Екатерина получает «запись на 14:00» и ни слова о запросе."""
        self.client.force_login(self.user)
        self.client.post(reverse('booking:book', args=[self.slot.pk]),
                         {'notes': '  Развод, не понимаю, что дальше  '})

        self.assertEqual(Booking.objects.get().notes, 'Развод, не понимаю, что дальше')

    def test_confirmation_of_a_taken_slot_sends_back_to_the_calendar(self):
        book_slot(User.objects.create(username='first'), self.slot.pk)
        self.client.force_login(self.user)
        response = self.client.get(reverse('booking:book', args=[self.slot.pk]), follow=True)
        self.assertContains(response, 'уже заняли')

    def test_taken_slot_shows_a_message_instead_of_an_error(self):
        book_slot(User.objects.create(username='first'), self.slot.pk)
        self.client.force_login(self.user)
        response = self.client.post(reverse('booking:book', args=[self.slot.pk]),
                                    follow=True)
        self.assertContains(response, 'уже заняли')

    def test_other_peoples_bookings_are_not_visible(self):
        booking = book_slot(User.objects.create(username='first'), self.slot.pk)
        self.client.force_login(self.user)
        response = self.client.get(reverse('booking:detail', args=[booking.pk]))
        self.assertEqual(response.status_code, 404)


class GenerateSlotsCommandTests(TestCase):
    def test_command_creates_slots_and_is_idempotent(self):
        call_command('generate_slots', days=3, duration=30, verbosity=0)
        created = BookingSlot.objects.count()
        self.assertGreater(created, 0)

        call_command('generate_slots', days=3, duration=30, verbosity=0)
        self.assertEqual(BookingSlot.objects.count(), created)

    def test_command_never_creates_slots_in_the_past(self):
        call_command('generate_slots', days=3, verbosity=0)
        self.assertFalse(BookingSlot.objects.filter(start_time__lte=timezone.now()).exists())
