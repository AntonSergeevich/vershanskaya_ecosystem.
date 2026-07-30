import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse

from lms.models import Course, CourseAccess, Lesson, LessonProgress, Module
from lms.services import hero_path

User = get_user_model()

# Видео пишем во временный каталог, чтобы тесты не мусорили в проекте.
TEMP_PROTECTED_ROOT = tempfile.mkdtemp(prefix='lms-test-')


class AccessTests(TestCase):
    def setUp(self):
        self.free = Course.objects.create(title='Бесплатный', slug='free',
                                          description='', access_level='free')
        self.club = Course.objects.create(title='Клубный', slug='club',
                                          description='', access_level='club')
        self.paid = Course.objects.create(title='Платный', slug='paid',
                                          description='', access_level='paid', price=5000)
        self.mage = Course.objects.create(title='Магический', slug='mage',
                                          description='', access_level='mage')
        self.guest = User.objects.create(username='guest')
        self.member = User.objects.create(username='member', is_club_member=True)

    def test_free_course_is_open_to_everyone(self):
        self.assertTrue(self.free.is_available_for(self.guest))

    def test_club_course_needs_membership(self):
        self.assertFalse(self.club.is_available_for(self.guest))
        self.assertTrue(self.club.is_available_for(self.member))

    def test_club_membership_includes_paid_courses(self):
        """Иначе подписка стоила бы дороже, чем её содержимое по частям."""
        self.assertFalse(self.paid.is_available_for(self.guest))
        self.assertTrue(self.paid.is_available_for(self.member))

    def test_individual_purchase_opens_only_that_course(self):
        CourseAccess.objects.create(user=self.guest, course=self.paid)
        self.assertTrue(self.paid.is_available_for(self.guest))
        self.assertFalse(self.club.is_available_for(self.guest))

    def test_mage_level_needs_personal_guidance(self):
        self.assertFalse(self.mage.is_available_for(self.member))
        self.member.has_personal_guidance = True
        self.assertTrue(self.mage.is_available_for(self.member))

    def test_preview_lesson_is_open_inside_a_closed_course(self):
        locked = Lesson.objects.create(course=self.club, title='Закрытый', order=1)
        preview = Lesson.objects.create(course=self.club, title='Превью', order=2,
                                        is_preview=True)
        self.assertFalse(locked.is_available_for(self.guest))
        self.assertTrue(preview.is_available_for(self.guest))


class LessonViewTests(TestCase):
    def setUp(self):
        self.course = Course.objects.create(title='Клубный', slug='club',
                                            description='', access_level='club')
        self.lesson = Lesson.objects.create(course=self.course, title='Урок', order=1)
        self.guest = User.objects.create(username='guest')

    def test_locked_lesson_answers_403_not_the_content(self):
        self.client.force_login(self.guest)
        response = self.client.get(self.lesson.get_absolute_url())
        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, 'lms/lesson_locked.html')

    def test_open_lesson_records_progress_on_first_visit(self):
        self.guest.is_club_member = True
        self.guest.save()
        self.client.force_login(self.guest)

        self.client.get(self.lesson.get_absolute_url())
        progress = LessonProgress.objects.get(user=self.guest, lesson=self.lesson)
        self.assertFalse(progress.is_completed)

    def test_marking_complete_updates_course_progress(self):
        Lesson.objects.create(course=self.course, title='Второй', order=2)
        self.guest.is_club_member = True
        self.guest.save()
        self.client.force_login(self.guest)

        self.client.post(reverse('lms:lesson_complete',
                                 args=[self.course.slug, self.lesson.pk]))
        self.assertEqual(self.course.progress_for(self.guest), 50)

    def test_cannot_complete_a_locked_lesson(self):
        self.client.force_login(self.guest)
        response = self.client.post(reverse('lms:lesson_complete',
                                            args=[self.course.slug, self.lesson.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertFalse(LessonProgress.objects.exists())

    def test_completion_date_is_not_moved_by_repeat_clicks(self):
        progress = LessonProgress.objects.create(user=self.guest, lesson=self.lesson)
        progress.mark_completed()
        first = progress.completed_at
        progress.mark_completed()
        self.assertEqual(progress.completed_at, first)


@override_settings(PROTECTED_MEDIA_ROOT=TEMP_PROTECTED_ROOT)
class ProtectedVideoTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TEMP_PROTECTED_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.course = Course.objects.create(title='Клубный', slug='club',
                                            description='', access_level='club')
        self.lesson = Lesson.objects.create(course=self.course, title='Урок', order=1)
        self.lesson.video_file.save('urok.mp4', ContentFile(b'0123456789'), save=True)
        self.guest = User.objects.create(username='guest')

    def open_access(self):
        self.guest.is_club_member = True
        self.guest.save()
        self.client.force_login(self.guest)

    def test_video_is_not_served_without_access(self):
        self.client.force_login(self.guest)
        response = self.client.get(reverse('lms:lesson_video', args=[self.lesson.pk]))
        self.assertEqual(response.status_code, 404)

    def test_video_is_served_to_a_member(self):
        self.open_access()
        response = self.client.get(reverse('lms:lesson_video', args=[self.lesson.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b''.join(response.streaming_content), b'0123456789')

    def test_range_request_returns_only_the_asked_bytes(self):
        """Без корректного 206 браузер не даст перематывать видео."""
        self.open_access()
        response = self.client.get(reverse('lms:lesson_video', args=[self.lesson.pk]),
                                   headers={'range': 'bytes=2-5'})
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response['Content-Range'], 'bytes 2-5/10')
        self.assertEqual(b''.join(response.streaming_content), b'2345')

    def test_suffix_range(self):
        self.open_access()
        response = self.client.get(reverse('lms:lesson_video', args=[self.lesson.pk]),
                                   headers={'range': 'bytes=-3'})
        self.assertEqual(response.status_code, 206)
        self.assertEqual(b''.join(response.streaming_content), b'789')

    def test_broken_range_falls_back_to_whole_file(self):
        self.open_access()
        response = self.client.get(reverse('lms:lesson_video', args=[self.lesson.pk]),
                                   headers={'range': 'bytes=abc'})
        self.assertEqual(response.status_code, 200)

    def test_video_file_lands_outside_media_root(self):
        """До файла не должно быть прямой ссылки в /media/."""
        self.assertTrue(self.lesson.video_file.path.startswith(TEMP_PROTECTED_ROOT))


class HeroPathTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(username='seeker')

    def test_path_starts_empty_and_points_at_the_quiz(self):
        path = hero_path(self.user)
        self.assertEqual(path['done_count'], 0)
        self.assertEqual(path['next_step']['title'], 'Узнать свой архетип')

    def test_archetype_closes_the_first_step(self):
        self.user.archetype = 'creator'
        self.user.save()
        path = hero_path(self.user)
        self.assertTrue(path['steps'][0]['done'])
        self.assertEqual(path['percent'], 25)

    def test_dashboard_renders(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('lms:dashboard'))
        self.assertEqual(response.status_code, 200)


class CourseProgrammeTests(TestCase):
    def test_course_page_shows_modules_and_loose_lessons(self):
        course = Course.objects.create(title='Курс', slug='kurs', description='',
                                       access_level='free')
        module = Module.objects.create(course=course, title='Первый раздел', order=1)
        Lesson.objects.create(course=course, module=module, title='В разделе', order=1)
        Lesson.objects.create(course=course, title='Без раздела', order=2)

        response = self.client.get(course.get_absolute_url())
        self.assertContains(response, 'Первый раздел')
        self.assertContains(response, 'В разделе')
        self.assertContains(response, 'Без раздела')

    def test_closed_course_shows_the_programme_but_locks_the_lessons(self):
        """Видимая программа продаёт подписку лучше пустой страницы."""
        course = Course.objects.create(title='Клуб', slug='klub', description='',
                                       access_level='club')
        Lesson.objects.create(course=course, title='Секретный урок', order=1)

        response = self.client.get(course.get_absolute_url())
        self.assertContains(response, 'Секретный урок')
        self.assertContains(response, 'is-locked')
