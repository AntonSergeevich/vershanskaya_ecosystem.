"""Логика вокруг обучения: путь героя и подбор следующего шага."""
from django.urls import reverse

from .models import Course, Lesson, LessonProgress


def hero_path(user):
    """«Путь героя» в кабинете: четыре шага от первого касания до клуба.

    Незакрытые шаги видны всегда — открытый список дел тянет продолжить
    сильнее, чем поздравление с уже сделанным (эффект Зейгарник).
    """
    has_archetype = bool(getattr(user, 'archetype', ''))
    started_learning = LessonProgress.objects.filter(user=user).exists()
    had_session = user.bookings.filter(is_completed=True).exists()
    in_club = user.has_club_access

    steps = [
        {
            'title': 'Узнать свой архетип',
            'hint': 'Семь вопросов — и понятно, с чего начинать.',
            'done': has_archetype,
            'url': reverse('quiz:list'),
            'action': 'Пройти квиз',
        },
        {
            'title': 'Пройти первый урок',
            'hint': 'Бесплатные материалы уровня «Искатель» открыты сразу.',
            'done': started_learning,
            'url': reverse('lms:courses'),
            'action': 'Открыть курсы',
        },
        {
            'title': 'Разобрать свой запрос',
            'hint': '30 минут один на один — точка, где всё складывается.',
            'done': had_session,
            'url': reverse('booking:slots'),
            'action': 'Выбрать время',
        },
        {
            'title': 'Войти в клуб «Творец»',
            'hint': 'Закрытые разборы, чат и новые материалы каждый месяц.',
            'done': in_club,
            'url': reverse('payments:club'),
            'action': 'Присоединиться',
        },
    ]

    done_count = sum(1 for step in steps if step['done'])
    return {
        'steps': steps,
        'done_count': done_count,
        'total': len(steps),
        'percent': round(done_count / len(steps) * 100),
        'next_step': next((step for step in steps if not step['done']), None),
    }


def visible_courses(user):
    """Опубликованные курсы, отсортированные под архетип пользователя.

    Курс «для моего архетипа» поднимаем наверх: так первый экран кабинета
    выглядит собранным лично под человека.
    """
    courses = Course.objects.filter(is_published=True).prefetch_related('lessons')
    archetype = getattr(user, 'archetype', '') or ''
    if not archetype:
        return list(courses)
    return sorted(courses, key=lambda course: (course.for_archetype != archetype,))


def continue_lesson(user):
    """Урок, с которого стоит продолжить: первый непройденный в начатом курсе."""
    last = (LessonProgress.objects
            .filter(user=user)
            .select_related('lesson', 'lesson__course')
            .order_by('-updated_at')
            .first())
    if last is None:
        return None

    course = last.lesson.course
    done_ids = LessonProgress.objects.filter(
        user=user, lesson__course=course, is_completed=True).values_list('lesson_id', flat=True)
    return (Lesson.objects.filter(course=course)
            .exclude(id__in=list(done_ids))
            .first() or last.lesson)
