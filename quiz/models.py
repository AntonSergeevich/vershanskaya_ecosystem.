from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from core.constants import ARCHETYPE_CHOICES, ARCHETYPE_DESCRIPTIONS, ARCHETYPE_LABELS


class Quiz(models.Model):
    """Квиз-воронка: определяет архетип и превращает трафик в лид.

    Прохождение намеренно разбито на отдельные шаги (по вопросу на экран) —
    незакрытый гештальт мотивирует дойти до результата (эффект Зейгарник).
    """
    title = models.CharField("Название", max_length=255)
    slug = models.SlugField("URL-слаг", unique=True)
    intro = models.TextField("Текст перед началом", blank=True)
    outro = models.TextField("Текст после результата", blank=True,
                             help_text="Показывается под результатом, перед призывом к действию.")
    is_published = models.BooleanField("Опубликован", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Квиз"
        verbose_name_plural = "Квизы"
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('quiz:start', kwargs={'slug': self.slug})

    @property
    def question_count(self):
        return self.questions.count()


class Question(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions',
                             verbose_name="Квиз")
    text = models.CharField("Вопрос", max_length=500)
    subtitle = models.CharField("Подсказка под вопросом", max_length=255, blank=True)
    order = models.PositiveIntegerField("Порядок", default=1)

    class Meta:
        verbose_name = "Вопрос"
        verbose_name_plural = "Вопросы"
        ordering = ['order', 'id']

    def __str__(self):
        return f"{self.order}. {self.text[:60]}"


class Option(models.Model):
    """Вариант ответа. Каждый вариант «голосует» за архетип с некоторым весом."""
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='options',
                                verbose_name="Вопрос")
    text = models.CharField("Вариант ответа", max_length=500)
    archetype = models.CharField("За какой архетип голосует", max_length=20,
                                 choices=ARCHETYPE_CHOICES)
    weight = models.PositiveSmallIntegerField("Вес голоса", default=1)
    order = models.PositiveIntegerField("Порядок", default=1)

    class Meta:
        verbose_name = "Вариант ответа"
        verbose_name_plural = "Варианты ответа"
        ordering = ['order', 'id']

    def __str__(self):
        return f"{self.text[:50]} → {self.get_archetype_display()}"


class QuizAttempt(models.Model):
    """Одно прохождение квиза. Живёт и для анонимов — по ключу сессии.

    Незавершённые попытки — это тёплая база: по ним видно, кто «залип»
    на середине, и их можно догреть рассылкой.
    """
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='attempts',
                             verbose_name="Квиз")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                             blank=True, null=True, related_name='quiz_attempts',
                             verbose_name="Пользователь")
    session_key = models.CharField("Ключ сессии", max_length=40, blank=True, db_index=True)

    # Контакты собираем на последнем шаге — до показа результата.
    contact_name = models.CharField("Имя", max_length=120, blank=True)
    contact_phone = models.CharField("Телефон", max_length=20, blank=True)
    contact_telegram = models.CharField("Telegram", max_length=64, blank=True)

    result_archetype = models.CharField("Определённый архетип", max_length=20,
                                        choices=ARCHETYPE_CHOICES, blank=True)
    is_completed = models.BooleanField("Завершён", default=False)
    source = models.CharField("Источник трафика", max_length=100, blank=True)
    created_at = models.DateTimeField("Начат", auto_now_add=True)
    completed_at = models.DateTimeField("Завершён в", blank=True, null=True)

    class Meta:
        verbose_name = "Прохождение квиза"
        verbose_name_plural = "Прохождения квиза"
        ordering = ['-created_at']

    def __str__(self):
        who = self.user or self.contact_name or self.contact_phone or 'анонимно'
        state = self.get_result_archetype_display() if self.is_completed else 'не завершён'
        return f"{self.quiz.title} — {who} [{state}]"

    # --- Прогресс ---------------------------------------------------------

    @property
    def answered_count(self):
        return self.answers.count()

    @property
    def progress_percent(self):
        total = self.quiz.question_count
        if not total:
            return 0
        return min(100, round(self.answered_count / total * 100))

    def next_question(self):
        """Первый вопрос, на который ещё нет ответа."""
        answered = self.answers.values_list('question_id', flat=True)
        return self.quiz.questions.exclude(id__in=answered).first()

    # --- Подсчёт результата ------------------------------------------------

    def score_by_archetype(self):
        """Сумма весов по каждому архетипу: {'creator': 5, 'sage': 2}."""
        scores = {}
        for answer in self.answers.select_related('option'):
            key = answer.option.archetype
            scores[key] = scores.get(key, 0) + answer.option.weight
        return scores

    def calculate_result(self):
        """Определяет архетип-победитель и фиксирует завершение попытки."""
        scores = self.score_by_archetype()
        if not scores:
            return ''
        # При равенстве весов берём порядок из справочника — результат стабилен.
        order = [code for code, _ in ARCHETYPE_CHOICES]
        winner = max(scores, key=lambda code: (scores[code], -order.index(code)))
        self.result_archetype = winner
        self.is_completed = True
        self.completed_at = timezone.now()
        self.save(update_fields=['result_archetype', 'is_completed', 'completed_at'])
        return winner

    @property
    def result_label(self):
        return ARCHETYPE_LABELS.get(self.result_archetype, '')

    @property
    def result_description(self):
        return ARCHETYPE_DESCRIPTIONS.get(self.result_archetype, '')


class Answer(models.Model):
    attempt = models.ForeignKey(QuizAttempt, on_delete=models.CASCADE, related_name='answers',
                               verbose_name="Прохождение")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, verbose_name="Вопрос")
    option = models.ForeignKey(Option, on_delete=models.CASCADE, verbose_name="Ответ")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Ответ"
        verbose_name_plural = "Ответы"
        # Один ответ на вопрос в рамках попытки — повторный выбор перезаписывается.
        constraints = [
            models.UniqueConstraint(fields=['attempt', 'question'],
                                    name='quiz_unique_answer_per_question'),
        ]

    def __str__(self):
        return f"{self.question.order}. {self.option.text[:40]}"
