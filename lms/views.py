import mimetypes

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.models import FAQItem

from .models import Course, Lesson, LessonProgress
from .services import continue_lesson, hero_path, visible_courses


@login_required
def dashboard(request):
    """Кабинет ученика: путь героя, продолжение обучения и доступные курсы."""
    courses = visible_courses(request.user)
    return render(request, 'lms/dashboard.html', {
        'path': hero_path(request.user),
        'continue_lesson': continue_lesson(request.user),
        'courses': [
            {
                'course': course,
                'available': course.is_available_for(request.user),
                'progress': course.progress_for(request.user),
            }
            for course in courses
        ],
    })


def course_list(request):
    """Каталог курсов. Открыт и гостям — закрытые курсы видны как витрина."""
    courses = Course.objects.filter(is_published=True).prefetch_related('lessons')
    return render(request, 'lms/course_list.html', {
        'courses': [
            {
                'course': course,
                'available': course.is_available_for(request.user),
                'progress': course.progress_for(request.user),
            }
            for course in courses
        ],
        'faq': FAQItem.objects.filter(is_published=True),
    })


def course_detail(request, slug):
    """Программа курса. Закрытые уроки показываем с замком, а не скрываем:
    видимая программа продаёт подписку лучше пустой страницы."""
    course = get_object_or_404(
        Course.objects.prefetch_related('modules', 'lessons'), slug=slug, is_published=True)

    completed_ids = set()
    if request.user.is_authenticated:
        completed_ids = set(LessonProgress.objects
                            .filter(user=request.user, lesson__course=course, is_completed=True)
                            .values_list('lesson_id', flat=True))

    def wrap(lessons):
        return [
            {
                'lesson': lesson,
                'available': lesson.is_available_for(request.user),
                'completed': lesson.id in completed_ids,
            }
            for lesson in lessons
        ]

    modules = [
        {'module': module, 'lessons': wrap(module.lessons.all())}
        for module in course.modules.all()
    ]
    return render(request, 'lms/course_detail.html', {
        'course': course,
        'available': course.is_available_for(request.user),
        'locked_reason': course.locked_reason(request.user),
        'progress': course.progress_for(request.user),
        'modules': modules,
        # Уроки без раздела показываем отдельным плоским списком.
        'loose_lessons': wrap(course.lessons.filter(module__isnull=True)),
    })


def lesson_detail(request, slug, pk):
    """Страница урока. Доступ проверяем здесь, а видео отдаёт lesson_video."""
    lesson = get_object_or_404(Lesson.objects.select_related('course', 'module'),
                               pk=pk, course__slug=slug, course__is_published=True)

    if not lesson.is_available_for(request.user):
        return render(request, 'lms/lesson_locked.html', {
            'lesson': lesson,
            'course': lesson.course,
            'locked_reason': lesson.course.locked_reason(request.user),
        }, status=403)

    progress = None
    if request.user.is_authenticated:
        # Сам факт открытия — уже прогресс: по нему видно, кто начал и не дошёл.
        progress, _ = LessonProgress.objects.get_or_create(user=request.user, lesson=lesson)

    previous_lesson, next_lesson = lesson.neighbours()
    return render(request, 'lms/lesson_detail.html', {
        'lesson': lesson,
        'course': lesson.course,
        'progress': progress,
        'previous_lesson': previous_lesson,
        'next_lesson': next_lesson,
        'course_progress': lesson.course.progress_for(request.user),
    })


@login_required
@require_POST
def lesson_complete(request, slug, pk):
    """Отметка «урок пройден». Отвечает JSON для fetch и редиректом для формы."""
    lesson = get_object_or_404(Lesson, pk=pk, course__slug=slug)
    if not lesson.is_available_for(request.user):
        raise Http404

    progress, _ = LessonProgress.objects.get_or_create(user=request.user, lesson=lesson)
    progress.mark_completed()

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'completed': True,
            'course_progress': lesson.course.progress_for(request.user),
        })

    _, next_lesson = lesson.neighbours()
    return redirect(next_lesson or lesson.course)


def lesson_video(request, pk):
    """Отдаёт видеофайл урока только тем, у кого есть доступ.

    Файл лежит вне MEDIA_ROOT, так что ссылку нельзя ни угадать, ни переслать
    в обход проверки. В проде включите PROTECTED_MEDIA_USE_NGINX: тогда Django
    только проверит права, а сам файл отдаст nginx.
    """
    lesson = get_object_or_404(Lesson.objects.select_related('course'), pk=pk)
    if not lesson.is_available_for(request.user):
        raise Http404
    if not lesson.video_file:
        raise Http404

    content_type = mimetypes.guess_type(lesson.video_file.name)[0] or 'application/octet-stream'

    if settings.PROTECTED_MEDIA_USE_NGINX:
        response = HttpResponse(content_type=content_type)
        location = settings.PROTECTED_MEDIA_NGINX_LOCATION.rstrip('/')
        response['X-Accel-Redirect'] = f"{location}/{lesson.video_file.name}"
        return response

    try:
        size = lesson.video_file.size
        handle = lesson.video_file.open('rb')
    except (FileNotFoundError, OSError):
        raise Http404("Видеофайл не найден на диске.")

    span = parse_byte_range(request.headers.get('range'), size)
    if span is None:
        response = FileResponse(handle, content_type=content_type)
    else:
        start, end = span
        handle.seek(start)
        response = FileResponse(iter_range(handle, end - start + 1), status=206,
                                content_type=content_type)
        response['Content-Range'] = f'bytes {start}-{end}/{size}'
        response['Content-Length'] = str(end - start + 1)

    response['Content-Disposition'] = 'inline'
    # Без этого заголовка браузер не даст перематывать видео.
    response['Accept-Ranges'] = 'bytes'
    return response


def parse_byte_range(header, size):
    """Разбирает «Range: bytes=START-END». None — отдаём файл целиком.

    Поддерживаем только один диапазон: плееры больше и не просят, а составные
    ответы (multipart/byteranges) потребовали бы отдельной сборки.
    """
    if not header or not header.startswith('bytes=') or ',' in header:
        return None

    raw_start, _, raw_end = header[len('bytes='):].partition('-')
    try:
        if raw_start:
            start = int(raw_start)
            end = int(raw_end) if raw_end else size - 1
        elif raw_end:
            # «bytes=-500» — последние 500 байт.
            start, end = max(0, size - int(raw_end)), size - 1
        else:
            return None
    except ValueError:
        return None

    end = min(end, size - 1)
    if start > end or start >= size:
        return None
    return start, end


def iter_range(handle, length, chunk_size=8192):
    """Читает не больше length байт — иначе в 206-ответ попадёт весь хвост файла."""
    remaining = length
    with handle:
        while remaining > 0:
            chunk = handle.read(min(chunk_size, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk
