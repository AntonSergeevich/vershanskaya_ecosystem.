"""Студия курсов — рабочее место Екатерины.

Всё то же, что даёт админка Django, но в оформлении сайта: список курсов,
программа с перетаскиванием порядка стрелками, загрузка видео и текста.
Доступ — только сотрудникам, как и у воронки.
"""
from django.contrib import messages
from django.db import transaction
from django.db.models import Count
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from core.decorators import staff_required

from .forms import CourseForm, LessonForm, ModuleForm
from .models import Course, Lesson, LessonProgress, Module


@staff_required
def courses(request):
    """Список курсов: сколько уроков, сколько людей учится, что не опубликовано."""
    return render(request, 'lms/studio/courses.html', {
        'courses': Course.objects.annotate(lessons_total=Count('lessons')),
    })


@staff_required
def course_create(request):
    form = CourseForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        course = form.save()
        messages.success(request, "Курс создан. Теперь добавьте уроки.")
        return redirect('lms:studio_course', pk=course.pk)

    return render(request, 'lms/studio/course_form.html', {'form': form})


@staff_required
def course_edit(request, pk):
    """Курс и его программа на одной странице: настройки сверху, уроки снизу."""
    course = get_object_or_404(Course, pk=pk)
    form = CourseForm(request.POST or None, request.FILES or None, instance=course)

    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, "Сохранили.")
        return redirect('lms:studio_course', pk=course.pk)

    lessons = list(course.lessons.select_related('module'))
    return render(request, 'lms/studio/course_edit.html', {
        'course': course,
        'form': form,
        'lessons': lessons,
        'modules': course.modules.all(),
        # Программу показываем плоским списком в порядке прохождения: раздел
        # это подпись у урока, а не отдельное дерево, которое надо разворачивать.
        'students': LessonProgress.objects.filter(lesson__course=course)
                                          .values('user').distinct().count(),
    })


@staff_required
def course_delete(request, pk):
    course = get_object_or_404(Course, pk=pk)
    if request.method != 'POST':
        return render(request, 'lms/studio/confirm_delete.html', {
            'title': f"Удалить курс «{course.title}»?",
            'warning': (f"Вместе с курсом исчезнут {course.lesson_count} "
                        "уроков и весь прогресс учеников по ним. "
                        "Если курс просто не готов — снимите публикацию."),
            'cancel_url': reverse('lms:studio_course', kwargs={'pk': course.pk}),
        })
    title = course.title
    course.delete()
    messages.success(request, f"Курс «{title}» удалён.")
    return redirect('lms:studio')


# --- Уроки ------------------------------------------------------------------

@staff_required
def lesson_create(request, pk):
    course = get_object_or_404(Course, pk=pk)
    form = LessonForm(request.POST or None, request.FILES or None, course=course)

    if request.method == 'POST' and form.is_valid():
        lesson = form.save()
        messages.success(request, f"Урок «{lesson.title}» добавлен.")
        return redirect('lms:studio_course', pk=course.pk)

    return render(request, 'lms/studio/lesson_form.html', {'form': form, 'course': course})


@staff_required
def lesson_edit(request, pk):
    lesson = get_object_or_404(Lesson.objects.select_related('course'), pk=pk)
    form = LessonForm(request.POST or None, request.FILES or None,
                      instance=lesson, course=lesson.course)

    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, "Урок сохранён.")
        return redirect('lms:studio_course', pk=lesson.course.pk)

    return render(request, 'lms/studio/lesson_form.html', {
        'form': form,
        'course': lesson.course,
        'lesson': lesson,
    })


@staff_required
def lesson_delete(request, pk):
    lesson = get_object_or_404(Lesson.objects.select_related('course'), pk=pk)
    if request.method != 'POST':
        return render(request, 'lms/studio/confirm_delete.html', {
            'title': f"Удалить урок «{lesson.title}»?",
            'warning': "Отметки о прохождении этого урока тоже удалятся.",
            'cancel_url': reverse('lms:studio_course', kwargs={'pk': lesson.course.pk}),
        })
    course_pk = lesson.course.pk
    lesson.delete()
    messages.success(request, "Урок удалён.")
    return redirect('lms:studio_course', pk=course_pk)


@staff_required
@require_POST
@transaction.atomic
def lesson_move(request, pk, direction):
    """Переставляет урок на одну позицию вверх или вниз.

    Порядок пересчитываем весь целиком, а не меняем два числа местами:
    уроки, заведённые раньше через админку, спокойно могут иметь одинаковый
    order, и обмен значениями для них ничего бы не изменил.
    """
    if direction not in ('vverh', 'vniz'):
        raise Http404

    lesson = get_object_or_404(Lesson.objects.select_related('course'), pk=pk)
    siblings = list(Lesson.objects.filter(course=lesson.course))
    index = next(i for i, item in enumerate(siblings) if item.pk == lesson.pk)
    target = index - 1 if direction == 'vverh' else index + 1

    if 0 <= target < len(siblings):
        siblings[index], siblings[target] = siblings[target], siblings[index]

    for position, item in enumerate(siblings, start=1):
        if item.order != position:
            item.order = position
            item.save(update_fields=['order'])

    return redirect('lms:studio_course', pk=lesson.course.pk)


# --- Разделы ----------------------------------------------------------------

@staff_required
def module_create(request, pk):
    course = get_object_or_404(Course, pk=pk)
    form = ModuleForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        module = form.save(commit=False)
        module.course = course
        module.save()
        messages.success(request, f"Раздел «{module.title}» добавлен.")
        return redirect('lms:studio_course', pk=course.pk)

    return render(request, 'lms/studio/module_form.html', {'form': form, 'course': course})


@staff_required
def module_edit(request, pk):
    module = get_object_or_404(Module.objects.select_related('course'), pk=pk)
    form = ModuleForm(request.POST or None, instance=module)

    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, "Раздел сохранён.")
        return redirect('lms:studio_course', pk=module.course.pk)

    return render(request, 'lms/studio/module_form.html', {
        'form': form, 'course': module.course, 'module': module,
    })


@staff_required
@require_POST
def module_delete(request, pk):
    """Удаляет раздел. Уроки остаются — у них module станет пустым."""
    module = get_object_or_404(Module.objects.select_related('course'), pk=pk)
    course_pk = module.course.pk
    module.delete()
    messages.success(request, "Раздел удалён, уроки из него остались в курсе.")
    return redirect('lms:studio_course', pk=course_pk)
