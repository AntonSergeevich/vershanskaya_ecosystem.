"""Расписание в кабинете и нарезка окон."""
from datetime import date, time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from booking.models import Booking, BookingSlot
from booking.services import book_slot, generate_slots

User = get_user_model()


class GenerateSlotsTests(TestCase):
    def setUp(self):
        # Понедельник, чтобы неделя считалась предсказуемо.
        self.monday = timezone.localdate() + timedelta(days=(7 - timezone.localdate().weekday()))

    def test_weekend_is_included_when_asked(self):
        """Из-за этого субботы и воскресенья не было на сайте вообще."""
        generate_slots(days=7, weekdays={5, 6}, start_date=self.monday,
                       start_time=time(11, 0), end_time=time(12, 0))

        weekdays = {timezone.localtime(slot.start_time).weekday()
                    for slot in BookingSlot.objects.all()}
        self.assertEqual(weekdays, {5, 6})

    def test_by_default_all_seven_days_are_cut(self):
        created, _ = generate_slots(days=7, start_date=self.monday,
                                    start_time=time(11, 0), end_time=time(12, 0))
        self.assertEqual(created, 14)  # два окна по 30 минут на каждый из 7 дней

    def test_running_twice_creates_nothing_new(self):
        generate_slots(days=3, start_date=self.monday,
                       start_time=time(11, 0), end_time=time(12, 0))
        created, existed = generate_slots(days=3, start_date=self.monday,
                                          start_time=time(11, 0), end_time=time(12, 0))
        self.assertEqual(created, 0)
        self.assertGreater(existed, 0)

    def test_past_time_is_never_offered(self):
        generate_slots(days=1, start_date=timezone.localdate(),
                       start_time=time(0, 1), end_time=time(23, 59))
        self.assertFalse(
            BookingSlot.objects.filter(start_time__lte=timezone.now()).exists())

    def test_backwards_working_hours_are_rejected(self):
        with self.assertRaises(ValueError):
            generate_slots(start_time=time(18, 0), end_time=time(10, 0))


class ScheduleAccessTests(TestCase):
    def test_stranger_does_not_even_see_that_it_exists(self):
        self.client.force_login(User.objects.create(username='marina'))
        self.assertEqual(self.client.get(reverse('booking:schedule')).status_code, 404)

    def test_stranger_cannot_hide_a_slot(self):
        slot = _slot()
        self.client.force_login(User.objects.create(username='marina'))

        self.client.post(reverse('booking:slot_toggle', args=[slot.pk]))

        slot.refresh_from_db()
        self.assertTrue(slot.is_active)


class ScheduleTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create(username='ekaterina', is_staff=True)
        self.client.force_login(self.staff)

    def test_page_shows_free_hidden_and_booked(self):
        free = _slot(hours=24)
        hidden = _slot(hours=25, is_active=False)
        taken = _slot(hours=26)
        book_slot(User.objects.create(username='marina', first_name='Марина'), taken.pk)

        response = self.client.get(reverse('booking:schedule'))

        self.assertContains(response, 'is-hidden')
        self.assertContains(response, 'is-booked')
        self.assertContains(response, 'Марина')
        self.assertContains(response, free.start_time.astimezone().strftime('%H:%M'))

    def test_a_slot_is_hidden_and_returned_by_the_same_button(self):
        slot = _slot()

        self.client.post(reverse('booking:slot_toggle', args=[slot.pk]))
        slot.refresh_from_db()
        self.assertFalse(slot.is_active)

        self.client.post(reverse('booking:slot_toggle', args=[slot.pk]))
        slot.refresh_from_db()
        self.assertTrue(slot.is_active)

    def test_hidden_slot_disappears_from_the_public_calendar(self):
        slot = _slot()
        self.client.post(reverse('booking:slot_toggle', args=[slot.pk]))

        page = self.client_class().get(reverse('booking:slots'))
        self.assertNotContains(page, reverse('booking:book', args=[slot.pk]))

    def test_a_booked_slot_cannot_be_hidden(self):
        """Человек уже записан и ждёт — прятать его время нечестно."""
        slot = _slot()
        book_slot(User.objects.create(username='marina'), slot.pk)

        response = self.client.post(reverse('booking:slot_toggle', args=[slot.pk]),
                                    follow=True)

        slot.refresh_from_db()
        self.assertTrue(slot.is_active)
        self.assertContains(response, 'уже записаны')

    def test_a_booked_slot_cannot_be_deleted(self):
        """Удаление утащило бы за собой и запись клиента."""
        slot = _slot()
        book_slot(User.objects.create(username='marina'), slot.pk)

        self.client.post(reverse('booking:slot_delete', args=[slot.pk]))

        self.assertTrue(BookingSlot.objects.filter(pk=slot.pk).exists())
        self.assertTrue(Booking.objects.exists())

    def test_a_free_slot_is_deleted(self):
        slot = _slot()
        self.client.post(reverse('booking:slot_delete', args=[slot.pk]))
        self.assertFalse(BookingSlot.objects.filter(pk=slot.pk).exists())

    def test_a_whole_day_closes_and_opens(self):
        day = (timezone.localtime() + timedelta(days=2)).date()
        for hour in (10, 11, 12):
            _slot(at=timezone.make_aware(
                timezone.datetime.combine(day, time(hour, 0))))

        url = reverse('booking:day_toggle', args=[day.isoformat()])
        self.client.post(url)
        self.assertEqual(BookingSlot.objects.filter(is_active=False).count(), 3)

        self.client.post(url)
        self.assertEqual(BookingSlot.objects.filter(is_active=True).count(), 3)

    def test_one_hidden_slot_does_not_flip_the_day_button(self):
        """Спрятала одно окно — кнопка всё ещё должна закрывать день, а не
        открывать его обратно вместе со спрятанным."""
        day = (timezone.localtime() + timedelta(days=2)).date()
        for hour in (10, 11, 12):
            _slot(at=timezone.make_aware(
                timezone.datetime.combine(day, time(hour, 0))))
        BookingSlot.objects.filter(start_time__hour=10).update(is_active=False)

        self.client.post(reverse('booking:day_toggle', args=[day.isoformat()]))

        self.assertEqual(BookingSlot.objects.filter(is_active=True).count(), 0)

    def test_closing_a_day_leaves_booked_time_alone(self):
        day = (timezone.localtime() + timedelta(days=2)).date()
        taken = _slot(at=timezone.make_aware(
            timezone.datetime.combine(day, time(10, 0))))
        book_slot(User.objects.create(username='marina'), taken.pk)

        self.client.post(reverse('booking:day_toggle', args=[day.isoformat()]))

        taken.refresh_from_db()
        self.assertTrue(taken.is_active)

    def test_a_single_slot_is_added(self):
        day = timezone.localdate() + timedelta(days=3)
        self.client.post(reverse('booking:slot_add'),
                         {'date': day.isoformat(), 'time': '11:00', 'duration': '45'})

        slot = BookingSlot.objects.get()
        self.assertEqual(timezone.localtime(slot.start_time).hour, 11)
        self.assertEqual(slot.duration_minutes, 45)

    def test_a_slot_in_the_past_is_refused(self):
        response = self.client.post(
            reverse('booking:slot_add'),
            {'date': (timezone.localdate() - timedelta(days=1)).isoformat(),
             'time': '11:00'}, follow=True)

        self.assertFalse(BookingSlot.objects.exists())
        self.assertContains(response, 'уже прошло')

    def test_a_duplicate_slot_is_refused_not_crashed(self):
        day = timezone.localdate() + timedelta(days=3)
        data = {'date': day.isoformat(), 'time': '11:00'}
        self.client.post(reverse('booking:slot_add'), data)

        response = self.client.post(reverse('booking:slot_add'), data, follow=True)

        self.assertEqual(BookingSlot.objects.count(), 1)
        self.assertContains(response, 'уже есть')

    def test_generating_from_the_cabinet_covers_the_weekend(self):
        monday = timezone.localdate() + timedelta(days=(7 - timezone.localdate().weekday()))
        self.client.post(reverse('booking:slots_generate'), {
            'start': monday.isoformat(), 'days': '7',
            'from': '11:00', 'to': '12:00', 'duration': '30',
            'weekdays': ['5', '6'],
        })

        weekdays = {timezone.localtime(slot.start_time).weekday()
                    for slot in BookingSlot.objects.all()}
        self.assertEqual(weekdays, {5, 6})

    def test_generating_without_weekdays_is_refused(self):
        response = self.client.post(reverse('booking:slots_generate'),
                                    {'days': '7'}, follow=True)
        self.assertFalse(BookingSlot.objects.exists())
        self.assertContains(response, 'хотя бы один день')

    def test_garbage_numbers_do_not_break_the_page(self):
        """Поле «минут» можно очистить или вписать туда что угодно."""
        response = self.client.post(reverse('booking:slots_generate'), {
            'days': 'много', 'from': 'утром', 'to': '',
            'duration': '', 'weekdays': ['0', '1', '2', '3', '4', '5', '6'],
        }, follow=True)
        self.assertEqual(response.status_code, 200)

    def test_the_view_keeps_the_page_the_person_was_on(self):
        later = timezone.localdate() + timedelta(days=14)
        slot = _slot()

        response = self.client.post(reverse('booking:slot_toggle', args=[slot.pk]),
                                    {'ot': later.isoformat()})

        self.assertEqual(response['Location'],
                         f"{reverse('booking:schedule')}?ot={later}")

    def test_a_forged_date_in_the_return_address_is_dropped(self):
        slot = _slot()
        response = self.client.post(reverse('booking:slot_toggle', args=[slot.pk]),
                                    {'ot': 'https://evil.example.com'})
        self.assertEqual(response['Location'], reverse('booking:schedule'))


class ErrorPageTests(TestCase):
    def test_the_404_page_offers_a_way_out(self):
        response = self.client.get('/takoy-stranicy-net/')

        self.assertEqual(response.status_code, 404)
        self.assertContains(response, 'Такой страницы нет', status_code=404)
        self.assertContains(response, reverse('quiz:list'), status_code=404)

    def test_the_500_page_does_not_depend_on_anything(self):
        """Она рисуется, когда сайт уже сломан: ни базы, ни контекста."""
        from django.template.loader import get_template

        html = get_template('500.html').render({})

        self.assertIn('Что-то сломалось', html)
        self.assertNotIn('{{', html)


def _slot(hours=24, is_active=True, at=None):
    start = at or (timezone.now() + timedelta(hours=hours))
    return BookingSlot.objects.create(start_time=start,
                                      end_time=start + timedelta(minutes=30),
                                      is_active=is_active)
