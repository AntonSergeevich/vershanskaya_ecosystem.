from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.urls import reverse

from core.constants import ARCHETYPE_CHOICES, ARCHETYPE_DESCRIPTIONS, ARCHETYPE_LABELS
from lms.services import visible_courses

from .forms import ContactForm
from .models import Answer, Option, Quiz, QuizAttempt
from .services import complete_attempt


def _session_key(request):
    """Гарантированный ключ сессии: у анонима его может ещё не быть."""
    if not request.session.session_key:
        request.session.save()
    return request.session.session_key


def _get_attempt(request, pk):
    """Попытка, принадлежащая этому посетителю.

    Привязка идёт по пользователю или по ключу сессии — иначе по прямой ссылке
    можно было бы дописать ответы в чужое прохождение и увидеть чужие контакты.
    """
    attempt = get_object_or_404(QuizAttempt.objects.select_related('quiz'), pk=pk)
    if request.user.is_authenticated and attempt.user_id == request.user.id:
        return attempt
    if attempt.session_key and attempt.session_key == request.session.session_key:
        return attempt
    raise Http404


def quiz_list(request):
    """Все опубликованные квизы. Обычно их один, но список дешевле хардкода."""
    quizzes = Quiz.objects.filter(is_published=True).prefetch_related('questions')
    if quizzes.count() == 1:
        return redirect(quizzes.first())
    return render(request, 'quiz/list.html', {'quizzes': quizzes})


def start(request, slug):
    """Экран «до начала»: обещание результата и кнопка старта."""
    quiz = get_object_or_404(Quiz.objects.prefetch_related('questions'),
                             slug=slug, is_published=True)

    if request.method == 'POST':
        if not quiz.questions.exists():
            messages.error(request, "Квиз ещё наполняется — заглядывайте позже.")
            return redirect('core:landing')

        attempt = QuizAttempt.objects.create(
            quiz=quiz,
            user=request.user if request.user.is_authenticated else None,
            session_key=_session_key(request),
            source=request.GET.get('utm_source', '') or request.session.get('source', ''),
        )
        return redirect('quiz:question', pk=attempt.pk)

    return render(request, 'quiz/start.html', {'quiz': quiz})


def question(request, pk, order=None):
    """Один вопрос на экран: короткий шаг легче сделать, чем длинную анкету.

    Без order показываем первый неотвеченный вопрос — обычный ход квиза.
    С order человек вернулся назад, чтобы поменять ответ.
    """
    attempt = _get_attempt(request, pk)

    if attempt.is_completed:
        return redirect('quiz:result', pk=attempt.pk)

    questions = list(attempt.quiz.questions.all())
    answered = set(attempt.answers.values_list('question_id', flat=True))

    if order is None:
        current = attempt.next_question()
        if current is None:
            return redirect('quiz:contact', pk=attempt.pk)
    else:
        current = next((item for item in questions if item.order == order), None)
        # Вперёд по ссылке не перепрыгнуть: вопрос должен быть либо уже
        # отвечен, либо тот самый, до которого человек дошёл честно.
        if current is None or (current.id not in answered
                               and current != attempt.next_question()):
            return redirect('quiz:question', pk=attempt.pk)

    if request.method == 'POST':
        option = Option.objects.filter(pk=request.POST.get('option'),
                                       question=current).first()
        if option is None:
            messages.error(request, "Выберите один из вариантов.")
        else:
            # update_or_create, а не create: и кнопка «назад» в браузере, и
            # наша собственная не должны ломать прохождение уникальным
            # ограничением — ответ просто перезаписывается.
            Answer.objects.update_or_create(
                attempt=attempt, question=current, defaults={'option': option})
            return redirect('quiz:question', pk=attempt.pk)

    index = questions.index(current)
    return render(request, 'quiz/question.html', {
        'attempt': attempt,
        'quiz': attempt.quiz,
        'question': current,
        'options': current.options.all(),
        'number': index + 1,
        'total': attempt.quiz.question_count,
        'previous_question': questions[index - 1] if index else None,
        # Свой ответ подсвечиваем: вернувшись, человек должен видеть, что
        # он выбрал в прошлый раз, а не выбирать вслепую заново.
        'chosen_id': attempt.answers.filter(question=current)
                                    .values_list('option_id', flat=True).first(),
    })


def contact(request, pk):
    """Шаг с контактами. Результат уже готов, но показываем его после отправки."""
    attempt = _get_attempt(request, pk)

    if attempt.is_completed:
        return redirect('quiz:result', pk=attempt.pk)
    if attempt.next_question() is not None:
        return redirect('quiz:question', pk=attempt.pk)

    initial = {}
    if request.user.is_authenticated:
        initial = {
            'contact_name': request.user.display_name,
            'contact_phone': request.user.phone or '',
        }

    form = ContactForm(request.POST or None, initial=initial)
    if request.method == 'POST' and form.is_valid():
        attempt.contact_name = form.cleaned_data['contact_name']
        attempt.contact_phone = form.cleaned_data['contact_phone']
        attempt.contact_telegram = form.cleaned_data['contact_telegram']
        attempt.save(update_fields=['contact_name', 'contact_phone', 'contact_telegram'])
        complete_attempt(attempt, request)
        return redirect('quiz:result', pk=attempt.pk)

    return render(request, 'quiz/contact.html', {
        'attempt': attempt,
        'quiz': attempt.quiz,
        'form': form,
    })


def result(request, pk):
    """Результат: архетип, объяснение и следующий шаг воронки."""
    attempt = _get_attempt(request, pk)
    if not attempt.is_completed:
        return redirect('quiz:question', pk=attempt.pk)

    # Показываем не только победителя: вторая-третья строка объясняют человеку,
    # почему он «и то, и это», и делают результат достовернее.
    scores = attempt.score_by_archetype()
    total = sum(scores.values()) or 1
    breakdown = sorted(
        ({'code': code,
          'label': ARCHETYPE_LABELS.get(code, code),
          'percent': round(value / total * 100),
          'value': value,
          'is_winner': code == attempt.result_archetype}
         for code, value in scores.items()),
        key=lambda row: -row['value'])

    recommended = [course for course in visible_courses(request.user)
                   if course.for_archetype == attempt.result_archetype][:3]

    return render(request, 'quiz/result.html', {
        'attempt': attempt,
        'quiz': attempt.quiz,
        'breakdown': breakdown,
        'recommended': recommended,
        # Делимся публичной страницей архетипа, а не этой: адрес результата
        # привязан к сессии, и у друга он открылся бы ошибкой 404.
        'share_url': request.build_absolute_uri(
            reverse('quiz:archetype', kwargs={'code': attempt.result_archetype})),
        'share_text': f"Мой архетип — {attempt.result_label}. "
                      f"Семь вопросов, чтобы узнать свой:",
        'share_image': archetype_image(attempt.result_archetype),
    })


def archetype_image(code):
    """Адрес картинки-превью для архетипа.

    Считаем в Python, а не шаблоном: в проде статика раздаётся по манифесту
    с хешем в имени, и собрать путь из кусочков в шаблоне уже нельзя.
    """
    return static(f'img/og/{code}.png')


def archetype(request, code):
    """Публичная страница архетипа — то, что открывается по ссылке из чата.

    Отдельная страница нужна ровно потому, что результатом поделиться
    нельзя: он привязан к сессии автора. Здесь же всё открыто, и главное
    действие — пройти квиз самому.
    """
    label = ARCHETYPE_LABELS.get(code)
    if label is None:
        raise Http404

    return render(request, 'quiz/archetype.html', {
        'code': code,
        'label': label,
        'description': ARCHETYPE_DESCRIPTIONS.get(code, ''),
        'quiz': Quiz.objects.filter(is_published=True).first(),
        'recommended': [course for course in visible_courses(request.user)
                        if course.for_archetype == code][:3],
        'others': [(other, other_label) for other, other_label in ARCHETYPE_CHOICES
                   if other != code],
        'share_image': archetype_image(code),
    })
