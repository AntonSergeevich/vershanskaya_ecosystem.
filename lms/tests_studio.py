"""Студия курсов: то же, что даёт админка, но руками Екатерины."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from lms.models import Course, Lesson, LessonProgress, Module
from lms.utils import slugify_ru, unique_slug

User = get_user_model()


class SlugTests(TestCase):
    def test_russian_title_becomes_a_readable_slug(self):
        """slugify из Django выбрасывает кириллицу целиком — адрес был бы пустым."""
        self.assertEqual(slugify_ru('Путь Творца'), 'put-tvortsa')
        self.assertEqual(slugify_ru('Первые шаги'), 'pervye-shagi')

    def test_title_without_letters_still_gives_a_slug(self):
        self.assertEqual(unique_slug(Course, '???'), 'kurs')

    def test_second_course_with_the_same_name_gets_its_own_address(self):
        Course.objects.create(title='Путь', slug='put', description='')
        self.assertEqual(unique_slug(Course, 'Путь'), 'put-2')

    def test_editing_a_course_keeps_its_own_slug(self):
        course = Course.objects.create(title='Путь', slug='put', description='')
        self.assertEqual(unique_slug(Course, 'Путь', exclude_pk=course.pk), 'put')


class StudioAccessTests(TestCase):
    """Студия правит содержимое сайта — посторонним туда нельзя."""

    def setUp(self):
        self.course = Course.objects.create(title='Путь', slug='put', description='')

    def test_guest_is_sent_to_the_site_login_not_to_the_admin(self):
        """Вход в студию — обычный, сайтовый: админку Екатерина не открывает."""
        response = self.client.get(reverse('lms:studio'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('users:enter'), response['Location'])

    def test_ordinary_student_cannot_open_the_studio(self):
        self.client.force_login(User.objects.create(username='marina'))
        response = self.client.get(reverse('lms:studio'))
        self.assertEqual(response.status_code, 404)

    def test_ordinary_student_cannot_delete_a_course(self):
        self.client.force_login(User.objects.create(username='marina'))
        response = self.client.post(
            reverse('lms:studio_course_delete', args=[self.course.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Course.objects.filter(pk=self.course.pk).exists())


class StudioCourseTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create(username='ekaterina', is_staff=True)
        self.client.force_login(self.staff)

    def test_course_is_created_with_an_address_made_from_the_title(self):
        response = self.client.post(reverse('lms:studio_course_create'), {
            'title': 'Путь Творца',
            'description': 'О том, как перестать ждать разрешения.',
            'access_level': 'free',
            'price': '0',
            'for_archetype': '',
            'order': '10',
            'is_published': 'on',
        })
        course = Course.objects.get()
        self.assertEqual(course.slug, 'put-tvortsa')
        self.assertRedirects(response, reverse('lms:studio_course', args=[course.pk]))

    def test_unpublished_course_is_hidden_from_the_catalogue(self):
        Course.objects.create(title='Черновик', slug='draft', description='',
                              is_published=False)
        self.client.logout()
        response = self.client.get(reverse('lms:courses'))
        self.assertNotContains(response, 'Черновик')

    def test_renaming_a_course_moves_its_address(self):
        course = Course.objects.create(title='Старое', slug='staroe', description='')
        response = self.client.post(reverse('lms:studio_course', args=[course.pk]), {
            'title': 'Новое имя', 'description': 'Тот же курс.', 'access_level': 'free',
            'price': '0', 'for_archetype': '', 'order': '10', 'is_published': 'on',
        })
        self.assertEqual(response.status_code, 302, "форма не сохранилась")
        course.refresh_from_db()
        self.assertEqual(course.slug, 'novoe-imya')


class StudioLessonTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create(username='ekaterina', is_staff=True)
        self.client.force_login(self.staff)
        self.course = Course.objects.create(title='Путь', slug='put', description='')

    def add(self, title, **extra):
        data = {'title': title, 'module': '', 'duration_minutes': '0',
                'video_url': '', 'content': ''}
        data.update(extra)
        return self.client.post(
            reverse('lms:studio_lesson_create', args=[self.course.pk]), data)

    def test_lessons_line_up_in_the_order_they_were_added(self):
        self.add('Первый')
        self.add('Второй')
        self.assertEqual([lesson.title for lesson in self.course.lessons.all()],
                         ['Первый', 'Второй'])

    def test_arrow_moves_a_lesson_up(self):
        self.add('Первый')
        self.add('Второй')
        second = Lesson.objects.get(title='Второй')

        self.client.post(reverse('lms:studio_lesson_move', args=[second.pk, 'vverh']))

        self.assertEqual([lesson.title for lesson in self.course.lessons.all()],
                         ['Второй', 'Первый'])

    def test_moving_the_first_lesson_up_changes_nothing(self):
        self.add('Первый')
        self.add('Второй')
        first = Lesson.objects.get(title='Первый')

        self.client.post(reverse('lms:studio_lesson_move', args=[first.pk, 'vverh']))

        self.assertEqual([lesson.title for lesson in self.course.lessons.all()],
                         ['Первый', 'Второй'])

    def test_equal_orders_from_the_admin_are_untangled_by_a_move(self):
        """Уроки из админки часто идут с order=1 у всех — обмен значениями
        для них ничего бы не изменил, поэтому порядок пересчитывается целиком."""
        for title in ('А', 'Б', 'В'):
            Lesson.objects.create(course=self.course, title=title, order=1)
        last = Lesson.objects.filter(title='В').get()

        self.client.post(reverse('lms:studio_lesson_move', args=[last.pk, 'vverh']))

        self.assertEqual([lesson.title for lesson in self.course.lessons.all()],
                         ['А', 'В', 'Б'])

    def test_a_lesson_cannot_have_both_a_file_and_a_link(self):
        response = self.add('С двумя видео', video_url='https://example.com/v')
        self.assertEqual(response.status_code, 302)  # ссылка одна — это нормально

        lesson = Lesson.objects.get()
        response = self.client.post(reverse('lms:studio_lesson', args=[lesson.pk]), {
            'title': lesson.title, 'module': '', 'duration_minutes': '0',
            'video_url': 'https://example.com/v', 'content': '',
            'video_file': _fake_video(),
        })
        self.assertContains(response, 'Оставьте что-то одно')

    def test_module_dropdown_shows_only_this_courses_sections(self):
        Module.objects.create(course=self.course, title='Свой раздел')
        other = Course.objects.create(title='Чужой', slug='chuzhoy', description='')
        Module.objects.create(course=other, title='Чужой раздел')

        response = self.client.get(reverse('lms:studio_lesson_create', args=[self.course.pk]))

        self.assertContains(response, 'Свой раздел')
        self.assertNotContains(response, 'Чужой раздел')

    def test_deleting_a_lesson_asks_first(self):
        self.add('Первый')
        lesson = Lesson.objects.get()

        response = self.client.get(reverse('lms:studio_lesson_delete', args=[lesson.pk]))
        self.assertContains(response, 'Удалить урок')
        self.assertTrue(Lesson.objects.filter(pk=lesson.pk).exists())

        self.client.post(reverse('lms:studio_lesson_delete', args=[lesson.pk]))
        self.assertFalse(Lesson.objects.filter(pk=lesson.pk).exists())

    def test_deleting_a_section_keeps_its_lessons(self):
        module = Module.objects.create(course=self.course, title='Раздел')
        lesson = Lesson.objects.create(course=self.course, title='Урок', module=module)

        self.client.post(reverse('lms:studio_module_delete', args=[module.pk]))

        lesson.refresh_from_db()
        self.assertIsNone(lesson.module)

    def test_the_course_page_counts_students(self):
        lesson = Lesson.objects.create(course=self.course, title='Урок')
        student = User.objects.create(username='marina')
        LessonProgress.objects.create(user=student, lesson=lesson)

        response = self.client.get(reverse('lms:studio_course', args=[self.course.pk]))
        self.assertContains(response, '1 человек начал')


def _fake_video():
    from django.core.files.uploadedfile import SimpleUploadedFile
    return SimpleUploadedFile('urok.mp4', b'\x00\x00\x00\x18ftypmp42',
                              content_type='video/mp4')
